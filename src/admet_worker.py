"""Run local ADMET-AI in its own environment to avoid AiZynthFinder dependency conflicts."""
import json
import importlib.metadata
import math
from contextlib import redirect_stdout
from numbers import Real
import sys


def main():
    smiles = json.load(sys.stdin)["smiles"]
    try:
        with redirect_stdout(sys.stderr):
            from admet_ai import ADMETModel
            frame = ADMETModel(include_physchem=False, drugbank_path=None, num_workers=0).predict(smiles)
        if list(frame.columns).count("AMES") != 1:
            raise ValueError("AMES endpoint missing or duplicated")
        scores = frame["AMES"]
        if len(scores) != len(smiles) or set(scores.index) != set(smiles) or scores.index.has_duplicates:
            raise ValueError("AMES structure-result mismatch")
        rows = []
        for structure in smiles:
            raw = scores.loc[structure]
            if isinstance(raw, bool) or not isinstance(raw, Real):
                raise ValueError("Invalid AMES score type")
            value = float(raw)
            if not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError("Invalid AMES score")
            rows.append({"smiles": structure, "ames_score": value, "status": "prediction_only"})
        result = {"status": "success", "model": "ADMET-AI", "version": importlib.metadata.version("admet-ai"),
                  "endpoint": "AMES", "assessments": rows,
                  "note": "AMES score is not an ICH M7 classification or safety determination."}
    except Exception as exc:
        result = {"status": "failed", "reason": type(exc).__name__ + ": " + str(exc)[:300], "assessments": []}
    print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    main()
