"""Interpretation flags, not mutagenicity diagnoses or process impurity measurements."""
import math

from rdkit import Chem

from identifiers import normalize

NDMA = normalize("CN(C)N=O")
DIMETHYLAMINE = normalize("CNC")
DMF = normalize("CN(C)C=O")
NITRITE = Chem.MolFromSmarts("[N](=O)[O-]")
NITROUS_ACID = Chem.MolFromSmarts("[N](=O)[OH]")


AMES_SCREENING_THRESHOLD = 0.5


def ames_flag(score):
    if score is None or not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= 1:
        return {"status": "unknown", "label": "판정 보류 · 유효한 AMES 예측값 없음"}
    if score >= AMES_SCREENING_THRESHOLD:
        return {"status": "model_flagged", "label": "0.5 이상 · 검토 필요"}
    return {"status": "below_model_threshold", "label": "0.5 미만 · 안전 입증 아님"}


def ndma_review(route, stage_results=None, propagation=None, reagents=None):
    stage_results = stage_results or {}
    propagation = propagation or {}
    reagents = reagents or {}
    inputs = set()
    nitrite = False
    for index, step in enumerate(route["steps"]):
        for raw in step["reactants"] + ([reagents[index]] if index in reagents and reagents[index] else []):
            mol = Chem.MolFromSmiles(raw)
            if mol is None:
                continue
            inputs.update(normalize(Chem.MolToSmiles(part)) for part in Chem.GetMolFrags(mol, asMols=True))
            nitrite |= mol.HasSubstructMatch(NITRITE) or mol.HasSubstructMatch(NITROUS_ACID)
    direct = []
    for index, step in enumerate(route["steps"]):
        record = stage_results.get(index, {}).get("impurity", {})
        if record.get("status") != "success":
            continue
        result = record.get("response", {}).get("result", {})
        if isinstance(result, dict):
            direct.extend((index + 1, item.get("prd_smiles")) for item in result.get("predict_expand", []) if isinstance(item, dict))
    traced = []
    for record in propagation.get("traces", []):
        for item in record.get("products", []):
            traced.append((record["to_step"], item.get("smiles")))
    detected = [(step, source) for source, rows in (("직접 단계 예측", direct), ("전파 시나리오", traced))
                for step, smiles in rows if smiles and _matches_ndma(smiles)]
    if detected:
        return {"status": "model_candidate_review", "label": "NDMA 구조가 ASKCOS 예측 후보에 나타남 · 확인 필요",
                "evidence": [{"step": step, "source": source} for step, source in detected],
                "note": "생성·잔류·노출량의 실험 증거가 아님"}
    precursor = DIMETHYLAMINE in inputs or DMF in inputs
    if nitrite and precursor:
        return {"status": "precursor_scenario_review", "label": "니트로소화 조건·아민 전구체 검토 필요",
                "evidence": ["입력 구조에 nitrite/nitrous acid 및 dimethylamine 또는 DMF가 함께 있음"],
                "note": "DMF→dimethylamine 분해 및 NDMA 생성 여부·농도는 모델링/검증되지 않음"}
    missing = (["아질산염/아질산 등 니트로소화 관련 실제 투입·불순물 정보"] if not nitrite else []) + (
        ["dimethylamine/DMF 투입·분해·불순물 정보"] if not precursor else [])
    return {"status": "not_established", "label": "NDMA 예측 후보 미검출 · 안전 판정 아님",
            "evidence": [], "missing_process_inputs": missing,
            "note": "현재 모델에 제공된 경로/조건에서는 NDMA 후보 미검출. " +
                    ("미입력 공정 정보: " + ", ".join(missing) + ". " if missing else "") +
                    "공정 조건·불순물·정제 및 잔류량 미검증; 모델 미검출은 NDMA 생성 불가의 증거가 아님."}


def _matches_ndma(value):
    try:
        return normalize(value) == NDMA
    except (ValueError, TypeError):
        return False
