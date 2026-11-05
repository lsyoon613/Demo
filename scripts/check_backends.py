"""Exit nonzero unless the required prediction backend is actually ready."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

import requests

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {"context_quarc", "forward_wldn5", "impurity_predictor", "fast_filter", "atom_map_indigo"}


def askcos_ready(payload):
    modules = {row["name"]: row for row in payload.get("modules", [])}
    return all(modules.get(name, {}).get("ready") is True and
               modules.get(name, {}).get("to_start") is True for name in REQUIRED)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("backend", choices=["askcos", "ames"])
    args = parser.parse_args()
    if args.backend == "askcos":
        response = requests.get("http://127.0.0.1:9100/api/admin/get-backend-status", timeout=5)
        response.raise_for_status()
        if not askcos_ready(response.json()):
            raise RuntimeError("ASKCOS required modules are not all ready")
    else:
        python = ROOT / ".admet-venv/Scripts/python.exe"
        run = subprocess.run([str(python), str(ROOT / "src/admet_worker.py")],
                             input=json.dumps({"smiles": ["CCO"]}), capture_output=True,
                             text=True, encoding="utf8", timeout=600)
        if run.returncode != 0:
            raise RuntimeError(run.stderr[-1500:])
        result = json.loads(run.stdout)
        rows = result.get("assessments", [])
        if result.get("status") != "success" or len(rows) != 1 or not 0 <= rows[0]["ames_score"] <= 1:
            raise RuntimeError(str(result))
    print(f"{args.backend.upper()} ready")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Backend not ready: {exc}", file=sys.stderr)
        sys.exit(1)
