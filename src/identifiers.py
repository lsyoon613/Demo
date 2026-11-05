"""Strict, request-bound PubChem identity resolution with local RDKit normalization."""
from __future__ import annotations

import re
from urllib.parse import quote

import requests
from rdkit import Chem, rdBase
from rdkit.Chem import Descriptors

BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound"
INCHIKEY = re.compile(r"^[A-Z]{14}-[A-Z]{10}-[A-Z]$")
CAS = re.compile(r"^(\d{2,7})-(\d{2})-(\d)$")


def normalize(smiles: str) -> str:
    """RDKit SMILES -> sanitized molecule -> isomeric SMILES; no salt/tautomer rewriting."""
    mol = Chem.MolFromSmiles(smiles)
    if mol is None or mol.GetNumAtoms() == 0:
        raise ValueError("SMILES 구조를 RDKit으로 해석할 수 없습니다.")
    for atom in mol.GetAtoms():
        atom.SetAtomMapNum(0)
    return Chem.MolToSmiles(mol, canonical=True, isomericSmiles=True)


def cas_valid(value: str) -> bool:
    match = CAS.fullmatch(value)
    if not match:
        return False
    digits = match[1] + match[2]
    return sum(int(digit) * i for i, digit in enumerate(reversed(digits), 1)) % 10 == int(match[3])


def _json(session, path, *, form=None):
    url = BASE + path
    try:
        response = (session.post(url, data=form, timeout=(5, 20)) if form is not None else
                    session.get(url, timeout=(5, 20)))
    except requests.RequestException as exc:
        raise ValueError(f"PubChem 연결 실패: {exc}") from exc
    if response.status_code == 404:
        return None
    if response.status_code != 200:
        raise ValueError(f"PubChem HTTP {response.status_code} · 잠시 뒤 다시 조회하세요.")
    try:
        return response.json()
    except ValueError as exc:
        raise ValueError("PubChem JSON 응답을 해석할 수 없습니다.") from exc


def properties(cid: int, *, session=None) -> dict:
    if not isinstance(cid, int) or cid < 1:
        raise ValueError("양의 정수 CID가 필요합니다.")
    session = session or requests.Session()
    payload = _json(session, f"/cid/{cid}/property/Title,MolecularFormula,MolecularWeight,InChI,InChIKey,CanonicalSMILES,IsomericSMILES/JSON")
    rows = (payload or {}).get("PropertyTable", {}).get("Properties", [])
    if len(rows) != 1 or rows[0].get("CID") != cid:
        raise ValueError("PubChem CID의 구조 정보가 확인되지 않았습니다.")
    raw = rows[0]
    smiles = raw.get("SMILES") or raw.get("CanonicalSMILES") or raw.get("IsomericSMILES")
    structure = normalize(smiles)
    mol = Chem.MolFromSmiles(structure)
    inchi_key = Chem.MolToInchiKey(mol)
    if raw.get("InChIKey") and inchi_key != raw["InChIKey"]:
        raise ValueError("PubChem 구조와 InChIKey가 일치하지 않아 선택을 중단했습니다.")
    return {"cid": cid, "name": raw.get("Title"), "smiles": structure,
            "inchi": raw.get("InChI"), "inchikey": inchi_key,
            "formula": raw.get("MolecularFormula"), "molecular_weight": raw.get("MolecularWeight"),
            "rdkit_molecular_weight": round(Descriptors.MolWt(mol), 3),
            "url": f"https://pubchem.ncbi.nlm.nih.gov/compound/{cid}", "source": "PubChem PUG REST"}


def resolve(value: str, *, session=None) -> dict:
    text = value.strip()
    if not text or len(text) > 2048:
        raise ValueError("식별자는 1~2048자여야 합니다.")
    session = session or requests.Session()
    kind = None
    local = None
    if text.startswith("InChI="):
        kind = "inchi"
        mol = Chem.MolFromInchi(text)
        if mol is None:
            raise ValueError("InChI를 RDKit으로 해석할 수 없습니다.")
        local = normalize(Chem.MolToSmiles(mol, isomericSmiles=True))
        try:
            response = _json(session, "/inchi/cids/JSON", form={"inchi": text})
        except ValueError as exc:
            response = None
            offline_reason = str(exc)
    elif INCHIKEY.fullmatch(text.upper()):
        kind = "inchikey"
        response = _json(session, f"/inchikey/{text.upper()}/cids/JSON")
    elif CAS.fullmatch(text):
        if not cas_valid(text):
            raise ValueError("CAS 등록번호의 검사 숫자가 올바르지 않습니다.")
        kind = "cas"
        response = _json(session, f"/name/{quote(text, safe='')}/cids/JSON")
    elif re.fullmatch(r"(?:CID[: ]*)?\d+", text, flags=re.IGNORECASE):
        kind = "cid"
        cid = int(re.sub(r"\D", "", text))
        return {"status": "resolved", "input_type": kind, "input": text,
                "candidate_cids": [cid], "compound": properties(cid, session=session)}
    else:
        try:
            with rdBase.BlockLogs():
                local = normalize(text)
            kind = "smiles"
        except ValueError:
            kind = "name"
        if kind == "smiles":
            key = Chem.MolToInchiKey(Chem.MolFromSmiles(local))
            try:
                response = _json(session, f"/inchikey/{key}/cids/JSON")
            except ValueError as exc:
                response = None
                offline_reason = str(exc)
        else:
            response = _json(session, f"/name/{quote(text, safe='')}/cids/JSON")
    cids = list(dict.fromkeys((response or {}).get("IdentifierList", {}).get("CID", [])))
    if len(cids) > 1:
        return {"status": "ambiguous", "input_type": kind, "input": text, "candidate_cids": cids[:20],
                "local_smiles": local, "note": "PubChem 후보가 여러 개입니다. CID를 직접 선택한 뒤 구조를 확인하세요."}
    if not cids:
        if local is None:
            return {"status": "not_found", "input_type": kind, "input": text, "candidate_cids": [], "local_smiles": None}
        return {"status": "local_only", "input_type": kind, "input": text,
                "candidate_cids": [], "compound": {"smiles": local, "inchikey": Chem.MolToInchiKey(Chem.MolFromSmiles(local)),
                "source": "RDKit (PubChem 미조회/미등재)", "cid": None, "name": None, "url": None},
                "note": locals().get("offline_reason", "PubChem 구조 미등재; RDKit 입력 구조 유지")}
    compound = properties(cids[0], session=session)
    if kind == "inchikey" and compound["inchikey"] != text.upper():
        raise ValueError("입력 InChIKey와 PubChem 구조가 일치하지 않습니다.")
    if local and normalize(compound["smiles"]) != local:
        # Return the input structure unchanged; do not silently change salts or stereochemistry.
        return {"status": "structure_mismatch", "input_type": kind, "input": text,
                "local_smiles": local, "candidate_cids": cids, "compound": compound}
    return {"status": "resolved", "input_type": kind, "input": text,
            "candidate_cids": cids, "compound": compound}


def synonyms(cid: int, *, session=None) -> list[str]:
    data = _json(session or requests.Session(), f"/cid/{cid}/synonyms/JSON")
    rows = (data or {}).get("InformationList", {}).get("Information", [])
    if not rows or rows[0].get("CID") != cid:
        return []
    return list(dict.fromkeys(rows[0].get("Synonym", [])))[:30]


def report_stem(identity: dict | None, route_id: str) -> str:
    compound = (identity or {}).get("compound") or {}
    name = re.sub(r"[^A-Za-z0-9_-]+", "-", (compound.get("name") or "compound"))[:35].strip("-") or "compound"
    key = compound.get("inchikey")
    if not key and compound.get("smiles"):
        key = Chem.MolToInchiKey(Chem.MolFromSmiles(normalize(compound["smiles"])))
    identifier = f"CID{compound['cid']}" if compound.get("cid") else "compound"
    if key:
        identifier += "_" + key.split("-")[0]
    if (identity or {}).get("input_type") == "cas" and cas_valid((identity or {}).get("input", "")):
        identifier += "_CAS" + identity["input"]
    safe_route = re.sub(r"[^A-Za-z0-9_-]+", "-", route_id)[:30]
    return f"{name}_{identifier}_{safe_route}"
