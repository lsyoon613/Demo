"""Evidence-backed origin flags; structural resemblance never proves natural sourcing."""
import json
import re
from pathlib import Path

import requests
from rdkit import Chem, DataStructs
from rdkit.Chem import rdFingerprintGenerator

from identifiers import normalize

HERE = Path(__file__).resolve().parent.parent
EVIDENCE = HERE / "data" / "natural_origin_evidence.json"
TAXANE_REFERENCE = "CC(=O)O[C@@]12CO[C@@H]1C[C@H](O)[C@@]1(C)C(=O)[C@H](O)C3=C(C)[C@@H](O)C[C@@](O)([C@@H](OC(=O)c4ccccc4)[C@H]21)C3(C)C"
PACLITAXEL_REFERENCE = "CC(=O)O[C@H]1C(=O)[C@@]2(C)[C@H]([C@H](OC(=O)c3ccccc3)[C@]3(O)C[C@H](OC(=O)[C@H](O)[C@@H](NC(=O)c4ccccc4)c4ccccc4)C(C)=C1C3(C)C)[C@]1(OC(C)=O)CO[C@@H]1C[C@@H]2O"


def coconut_occurrence(smiles: str, *, session=None) -> dict:
    """On-demand exact COCONUT record lookup; neither sourcing nor isolation proof."""
    structure = normalize(smiles)
    mol = Chem.MolFromSmiles(structure)
    if mol.GetNumHeavyAtoms() < 8:
        return {"status": "small_feedstock_not_queried", "note": "소분자 원료의 자연계 존재 여부만으로 합성 방식은 판정 불가"}
    key = Chem.MolToInchiKey(mol)
    try:
        response = (session or requests.Session()).post(
            "https://coconut.naturalproducts.net/api/search",
            json={"type": "inchikey", "query": key, "limit": 3, "page": 1}, timeout=(5, 20))
        response.raise_for_status()
        data = response.json().get("data", {}).get("data", [])
    except (requests.RequestException, ValueError, AttributeError, TypeError) as exc:
        return {"status": "lookup_failed", "note": f"COCONUT 조회 실패: {str(exc)[:160]}"}
    for row in data if isinstance(data, list) else []:
        if not isinstance(row, dict):
            continue
        try:
            if normalize(row["canonical_smiles"]) != structure:
                continue
        except (KeyError, ValueError, TypeError):
            continue
        identifier = row.get("identifier", "")
        if not re.fullmatch(r"CNP\d+\.\d+", identifier):
            continue
        if not row.get("active"):
            return {"status": "inactive_record", "id": identifier,
                    "note": "구조 일치 기록이 비활성 상태; 자연 유래 근거로 사용하지 않음"}
        if int(row.get("organism_count") or 0) < 1:
            continue
        return {"status": "database_occurrence_record", "id": identifier, "name": row.get("name"),
                "organism_count": int(row.get("organism_count") or 0),
                "citation_count": int(row.get("citation_count") or 0),
                "evidence": f"https://coconut.naturalproducts.net/compounds/{identifier}",
                "note": "COCONUT의 동일 입체구조·생물 출처 연결 기록; 개별 출처 문헌의 신뢰도와 원료 실제 공급 방식은 별도 확인"}
    return {"status": "no_exact_record", "note": "해당 조회에서 활성 상태의 동일 구조·생물 출처 기록을 확인하지 못함; 비천연물 증거 아님"}


def leaf_origin(smiles: str, *, annotated_smiles="", annotated_reference="", target="", occurrence=None) -> dict:
    structure = normalize(smiles)
    key = Chem.MolToInchiKey(Chem.MolFromSmiles(structure))
    if annotated_smiles and normalize(annotated_smiles) == structure and annotated_reference.strip():
        return {"status": "user_documented_natural_origin", "evidence": annotated_reference.strip(),
                "note": "사용자 제공 자연 유래 자료 · 출처 내용 별도 검토 필요"}
    for record in json.loads(EVIDENCE.read_text(encoding="utf-8")):
        if key == record["inchikey"]:
            return {"status": ("documented_natural_occurrence" if record["origin"] == "documented_natural_occurrence"
                               else "curated_natural_origin"), "evidence": record["evidence_url"],
                    "name": record["name"], "note": record["evidence_summary"]}
    if occurrence and occurrence.get("status") == "database_occurrence_record":
        return {"status": "database_occurrence_record", "evidence": occurrence["evidence"],
                "name": occurrence.get("name"), "note": occurrence["note"],
                "coconut_id": occurrence["id"], "organism_count": occurrence["organism_count"]}
    generator = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)
    mol = Chem.MolFromSmiles(structure)
    taxane = Chem.MolFromSmiles(TAXANE_REFERENCE)
    similarity = DataStructs.TanimotoSimilarity(generator.GetFingerprint(mol), generator.GetFingerprint(taxane))
    paclitaxel_related = False
    if target and normalize(target) == normalize(PACLITAXEL_REFERENCE):
        paclitaxel_related = DataStructs.TanimotoSimilarity(
            generator.GetFingerprint(mol), generator.GetFingerprint(Chem.MolFromSmiles(PACLITAXEL_REFERENCE))) >= 0.5
    if mol.GetNumHeavyAtoms() >= 30 and (similarity >= 0.5 or paclitaxel_related):
        return {"status": "taxane_structure_review", "evidence": None, "similarity": round(similarity, 3),
                "note": "Taxane/Paclitaxel 골격 유사성 신호만 있음; 해당 출발물질의 식물 유래·반합성 여부는 입증하지 않음"}
    return {"status": "unknown", "evidence": None, "note": "출발물질의 천연/합성 유래 근거 없음"}


def classify(leaves: list[dict]) -> dict:
    states = {item["origin"]["status"] for item in leaves}
    if states & {"curated_natural_origin", "user_documented_natural_origin"}:
        return {"label": "반합성 후보 · 천연 유래 출발물질 근거 있음", "status": "semisynthesis_candidate",
                "note": "경로와 실제 천연물 추출·공급 경위의 연결은 확인 필요"}
    if "taxane_structure_review" in states:
        return {"label": "반합성 가능성 검토 필요 · Taxane 유사 구조", "status": "origin_review_required",
                "note": "유사 구조만으로 자연 유래를 확정하거나 전합성으로 분류하지 않음"}
    if "documented_natural_occurrence" in states:
        return {"label": "화학 합성 경로 · 천연계에도 존재하는 원료 포함 (실제 공급 유래 미확인)",
                "status": "natural_occurrence_review", "note": "천연계에 존재한다는 기록과 이 경로의 원료가 실제 추출품이라는 증거는 다름. 화학 합성 원료일 수도 있어 전합성/반합성 확정 불가"}
    if "database_occurrence_record" in states:
        return {"label": "화학 합성 경로 · 천연물 DB 등재 원료 검토 필요", "status": "database_occurrence_review",
                "note": "COCONUT 기록의 생물 출처 문헌과 실제 투입 원료의 확보 경로를 검증해야 전합성/반합성 판정 가능"}
    return {"label": "화학 합성 경로 · 출발원료 유래 미확인", "status": "origin_unknown",
            "note": "화학적 반응 단계가 제시되었으나 출발원료의 생산/추출 출처가 없어 전합성/반합성 확정 불가"}
