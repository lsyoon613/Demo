"""Standalone orchestration of installed AiZynthFinder, catalog, ASKCOS and ADMET-AI.

Neither third-party package is patched. Each external result carries its own status.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import json
import math
import sqlite3
import subprocess

import requests
from rdkit import Chem
import natural_origin

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "price_db" / "catalog.sqlite"
STOCKS = {"Enamine (2026-09)": ROOT / "price_db" / "enamine_inchikeys.txt",
          "ZINC": ROOT / "models" / "zinc_stock.hdf5"}
ASKCOS_URL = "http://127.0.0.1:9100"


def canonical(smiles: str) -> str:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"유효하지 않은 SMILES: {smiles}")
    for atom in mol.GetAtoms():
        atom.SetAtomMapNum(0)
    return Chem.MolToSmiles(mol, isomericSmiles=True)


def _same_structure(smiles: object, expected: str) -> bool:
    if not isinstance(smiles, str):
        return False
    try:
        return canonical(smiles) == expected
    except ValueError:
        return False


def _same_connectivity(smiles: object, expected: str) -> bool:
    """Constitution only; never treat an unspecified stereo result as target confirmed."""
    if not isinstance(smiles, str):
        return False
    try:
        candidates = [Chem.MolFromSmiles(smiles), Chem.MolFromSmiles(expected)]
        if any(mol is None for mol in candidates):
            return False
        for mol in candidates:
            Chem.RemoveStereochemistry(mol)
        return Chem.MolToSmiles(candidates[0]) == Chem.MolToSmiles(candidates[1])
    except (ValueError, RuntimeError):
        return False


def tree_steps(node: dict) -> list[dict]:
    """Walk molecule/reaction tree from precursors to product, preserving branches."""
    if node.get("type") != "mol":
        raise ValueError("AiZynthFinder molecule tree expected")
    steps = []
    for reaction in node.get("children", []):
        if reaction.get("type") != "reaction" or not reaction.get("children"):
            raise ValueError("AiZynthFinder reaction tree expected")
        precursors = reaction["children"]
        for precursor in precursors:
            steps.extend(tree_steps(precursor))
        steps.append({"reactants": [canonical(p["smiles"]) for p in precursors],
                      "product": canonical(node["smiles"])})
    return steps


def search(target: str, stock_name="Enamine (2026-09)", time_limit=30, iteration_limit=30) -> list[dict]:
    """Configure a fresh upstream finder for this request; no global stock mutation."""
    target = canonical(target)
    if stock_name not in STOCKS:
        raise ValueError("지원하지 않는 재고입니다")
    if not 1 <= time_limit <= 120 or not 1 <= iteration_limit <= 200:
        raise ValueError("탐색 한도 범위 초과")
    models = ROOT / "models"
    needed = [models / "uspto_model.onnx", models / "uspto_templates.csv.gz",
              models / "uspto_filter_model.onnx", STOCKS[stock_name]]
    missing = [str(path) for path in needed if not path.is_file()]
    if missing:
        raise FileNotFoundError("모델/재고 파일 없음: " + ", ".join(missing))
    from aizynthfinder.aizynthfinder import AiZynthFinder
    finder = AiZynthFinder(configdict={
        "expansion": {"uspto": [str(needed[0]), str(needed[1])]},
        "filter": {"uspto": str(needed[2])}, "stock": {stock_name: str(needed[3])}})
    finder.stock.select_first()
    finder.expansion_policy.select_first()
    finder.filter_policy.select("uspto")
    finder.config.search.time_limit = time_limit
    finder.config.search.iteration_limit = iteration_limit
    finder.target_smiles = target
    finder.tree_search()
    finder.build_routes()
    completed_at = datetime.now(timezone.utc).isoformat()
    return [{"id": f"aizynth-{i+1}", "target": target, "stock": stock_name,
             "origin": "live_search", "searched_at_utc": completed_at,
             "steps": tree_steps(tree.to_dict())}
            for i, tree in enumerate(finder.routes.reaction_trees) if tree.to_dict().get("children")]


def route_leaves(route: dict) -> list[str]:
    products = {canonical(step["product"]) for step in route["steps"]}
    return list(dict.fromkeys(canonical(s) for step in route["steps"]
                              for s in step["reactants"] if canonical(s) not in products))


def route_signature(route: dict) -> tuple:
    """Compare reaction edges independently of precursor order and step numbering."""
    return tuple(sorted((tuple(sorted(canonical(s) for s in step["reactants"])),
                         canonical(step["product"])) for step in route["steps"]))


def distinct_routes(routes: list[dict]) -> dict:
    groups = {}
    for route in routes:
        groups.setdefault(route_signature(route), []).append(route["id"])
    return {"returned": len(routes), "unique_reaction_sets": len(groups),
            "duplicate_groups": [ids for ids in groups.values() if len(ids) > 1],
            "definition": "정규화된 반응물 조합→생성물 단계들의 집합이 동일한 경로를 중복으로 계산"}


def step_materials(route: dict) -> list[dict]:
    """Label recorded intermediates; no atom mapping or chemical validation implied."""
    products = {canonical(step["product"]) for step in route["steps"]}
    final = canonical(route["target"])
    return [{"number": i, "reactants": [
                {"smiles": canonical(s), "role": "이전 단계 중간체" if canonical(s) in products else "외부 출발물질"}
                for s in step["reactants"]],
             "product": {"smiles": canonical(step["product"]),
                         "role": "최종 목표물" if canonical(step["product"]) == final else "중간체"}}
            for i, step in enumerate(route["steps"], 1)]


def yield_scenario(route: dict, entered: list[float | None]) -> dict:
    """Only multiply stated step yields for a single linear intermediate chain.

    No mass, stoichiometry, limiting reagent, or predicted yield is inferred.
    Branched/convergent routes require a separate material balance.
    """
    if len(entered) != len(route["steps"]):
        raise ValueError("단계별 수율 입력 개수가 일치하지 않습니다")
    if any(value is not None and (not isinstance(value, (float, int)) or not 0 < value <= 100)
           for value in entered):
        raise ValueError("명시된 단계 수율은 0 초과 100 이하로 입력하세요")
    steps = route["steps"]
    products = [canonical(step["product"]) for step in steps]
    linear = (bool(steps) and len(set(products)) == len(products)
              and all(sum(canonical(s) == products[i-1] for s in steps[i]["reactants"]) == 1
                      and not any(canonical(s) in products[:i-1] for s in steps[i]["reactants"])
                      for i in range(1, len(steps)))
              and all(not any(canonical(s) in products[i+1:] for s in step["reactants"])
                      for i, step in enumerate(steps)))
    # A step consuming another branch's intermediate is not a linear chain.
    if linear:
        linear = all(not any(canonical(s) in products and canonical(s) != products[i-1]
                             for s in steps[i]["reactants"]) for i in range(1, len(steps)))
    overall = math.prod(y / 100 for y in entered) * 100 if linear and all(y is not None for y in entered) else None
    return {"step_yields_pct": entered, "linear_chain": linear,
            "overall_relative_yield_pct": overall,
            "reason": "사용자 입력 단계 수율의 단순 곱 (직렬 1:1 경로 가정; 질량 산출 아님)" if overall is not None else
                      "분기 경로이거나 단계 수율 미입력: 전체 수율 미산정"}


def lookup(smiles: str, db: sqlite3.Connection) -> dict:
    smiles = canonical(smiles)
    key = Chem.MolToInchiKey(Chem.MolFromSmiles(smiles))
    matches = []
    for cid, stored, url in db.execute("SELECT catalog_id,smiles,url FROM stock WHERE inchikey=?", (key,)):
        if canonical(stored) != smiles:
            continue
        quotes = [dict(amount=a, unit=u, currency=c, price=p, availability=v,
                       observed_at=t, source=src) for a, u, c, p, v, t, src in db.execute(
                           "SELECT package_amount,package_unit,currency,package_price,availability,observed_at,source "
                           "FROM quotes WHERE catalog_id=? ORDER BY package_amount,package_price", (cid,))]
        matches.append({"catalog_id": cid, "url": url, "quotes": quotes})
    return {"smiles": smiles, "matches": matches, "status": "exact_catalog_match" if matches else "no_exact_match"}


def compare(target: str, routes: list[dict], natural_start="", extraction_reference="", natural_reference="",
            occurrence_evidence: dict[str, dict] | None = None) -> dict:
    target = canonical(target)
    natural = canonical(natural_start) if natural_start.strip() else None
    occurrence_evidence = occurrence_evidence or {}
    db_connection = (sqlite3.connect(f"file:{DB.resolve().as_posix()}?mode=ro", uri=True)
                     if DB.is_file() else sqlite3.connect(":memory:"))
    with closing(db_connection) as db:
        if not DB.is_file():
            db.executescript("CREATE TABLE stock (catalog_id TEXT, inchikey TEXT, smiles TEXT, url TEXT); "
                              "CREATE TABLE quotes (catalog_id TEXT, package_amount REAL, package_unit TEXT, "
                              "currency TEXT, package_price REAL, availability TEXT, observed_at TEXT, source TEXT);")
        purchase = lookup(target, db)
        results = []
        for route in routes:
            leaves = [lookup(s, db) for s in route_leaves(route)]
            for leaf in leaves:
                leaf["origin"] = natural_origin.leaf_origin(
                    leaf["smiles"], annotated_smiles=natural or "", annotated_reference=natural_reference,
                    target=target, occurrence=occurrence_evidence.get(leaf["smiles"]))
                salicylic_product = (leaf["smiles"] == canonical("O=C(O)c1ccccc1O") and
                                     any(match["catalog_id"] == "EN300-16723" for match in leaf["matches"]))
                leaf["supply_origin"] = {
                    "status": ("manufacturer_origin_not_disclosed" if salicylic_product else
                               "manufacturer_origin_unverified" if leaf["matches"] else "supplier_not_identified"),
                    "note": ("Enamine EN300-16723 공개 제품 페이지에 식물 추출/화학 합성 제조 기원 표시 없음"
                             if salicylic_product else
                             "Enamine 카탈로그 구조 일치 · 제품 제조 기원 별도 검증 필요" if leaf["matches"] else
                             "이 카탈로그에서 정확 구조 일치 공급 제품 미확인")}
            classification = natural_origin.classify(leaves)
            natural_occurrence = [leaf for leaf in leaves if leaf["origin"]["status"] in
                                  {"documented_natural_occurrence", "database_occurrence_record"}]
            options = ([{"assumption": "자연계에도 존재하는 원료를 화학 합성품으로 조달", "classification": "전합성 후보 (조건부)",
                         "evidence_needed": "해당 원료 로트의 제조/공급 기원"},
                        {"assumption": "동일 원료를 실제 식물·생물 원료에서 추출해 조달", "classification": "반합성 후보 (조건부)",
                         "evidence_needed": "추출 원료·문헌·공급 로트 및 경로 연결"}]
                       if natural_occurrence and classification["status"] in
                       {"natural_occurrence_review", "database_occurrence_review"} else [])
            results.append({"id": route["id"], "mode": classification["label"],
                            "origin_status": classification["status"], "origin_note": classification["note"],
                            "origin_options": options,
                            "steps": len(route["steps"]), "leaves": leaves,
                            "catalog_coverage": sum(bool(l["matches"]) for l in leaves),
                            "price_coverage": sum(any(m["quotes"] for m in l["matches"]) for l in leaves)})
    if any(m["quotes"] for m in purchase["matches"]):
        recommendation = "목표물 직접 구매: 실제 포장 견적이 있으므로 현재 판매 가능성·필요량 확인을 우선 권장"
    else:
        covered = [r for r in results if r["leaves"] and r["price_coverage"] == len(r["leaves"])]
        if covered:
            candidate = min(covered, key=lambda r: (r["steps"], len(r["leaves"])))
            recommendation = f"{candidate['id']}: 출발물질 전부의 포장 견적을 확인했으므로 반응 타당성·당량·수율 검토를 우선 권장 (최저비용 판정 아님)"
        else:
            recommendation = "가격 커버리지가 완전한 경로 없음: 출발물질 견적을 먼저 보강하고 구매/추출/합성 우열 판단 보류"
    return {"target": target, "purchase": purchase,
            "extraction": {"status": "제공 근거 검토 필요" if extraction_reference.strip() else "근거 없음",
                           "reference": extraction_reference.strip()}, "routes": results, "next_check": recommendation,
            "catalog_status": "local_snapshot_available" if DB.is_file() else "catalog_not_installed",
            "note": ("Enamine 카탈로그 미설치 · 가격/구매 가능 여부 미확인. " if not DB.is_file() else "") +
                    "PubChem 구조·이름만으로 천연물 유래는 판정할 수 없습니다. 문헌/사용자 근거와 구조 유사성은 별도 표시하며, 근거가 없으면 전합성으로 단정하지 않습니다. 수율·소요량 없이 전체 경로 비용은 미산정입니다."}


def askcos_step(step: dict, modules=("context", "forward", "impurity"), base_url=ASKCOS_URL, timeout=180,
                reagents="", solvent="") -> dict:
    """Call locally hosted ASKCOS modules; preserve request, reply and failure separately."""
    if not base_url.startswith(("http://127.0.0.1:", "http://localhost:")):
        raise ValueError("로컬 ASKCOS 서버 주소만 지원합니다")
    reactants = ".".join(step["reactants"])
    product = step["product"]
    if reagents:
        reagents = canonical(reagents)
    if solvent:
        solvent = canonical(solvent)
    endpoints = {
        "context": ("/api/context/quarc/call-sync", {"smiles": [reactants + ">>" + product], "top_k": 3}),
        "forward": ("/api/forward/controller/call-sync", {"backend": "wldn5", "model_name": "pistachio",
                                                    "smiles": [reactants], "reagents": reagents, "solvent": solvent}),
        "impurity": ("/api/impurity-predictor/call-sync", {"rct_smi": reactants, "prd_smi": product,
             "rea_smi": reagents, "sol_smi": solvent, "predictor_backend": "wldn5", "predictor_model_name": "pistachio",
             "inspector": "Reaxys inspector", "topn_outcome": 3, "insp_threshold": 0.1, "check_mapping": False})}
    if any(module not in endpoints for module in modules):
        raise ValueError("알 수 없는 ASKCOS 모듈")
    results = {}
    for module in modules:
        path, payload = endpoints[module]
        row = {"url": base_url + path, "request": payload, "status": "failed", "response": None}
        try:
            response = requests.post(row["url"], json=payload, timeout=(15, timeout))
            row["http_status"] = response.status_code
            row["response"] = response.json()
            body = row["response"]
            if response.ok and isinstance(body, dict) and body.get("status_code", 200) == 200 and body.get("result") is not None:
                row["status"] = "success"
            else:
                row["error"] = "HTTP/API error or missing result"
        except requests.ConnectionError as exc:
            row["error"] = ("이 PC의 ASKCOS 계산 서버에 연결할 수 없습니다 (" + base_url +
                            "). 앱 서버와 별도입니다. ASKCOS 설치 후 실행하세요: docs/ASKCOS_LOCAL.md")
            row["diagnostic"] = str(exc)
        except (requests.RequestException, ValueError) as exc:
            row["error"] = str(exc)
        results[module] = row
    return results


def propagate_impurities(route: dict, step_calls: dict[int, dict], *, max_per_source=2, max_calls=18,
                         reagents=None, solvents=None) -> dict:
    """Trace predicted minor products into downstream steps that consume their parent.

    Replace the parent intermediate in a *hypothetical* reaction, run ASKCOS
    forward/impurity, and retain raw requests. This is bounded beam exploration,
    not mechanistic proof, yield, or exhaustive impurity fate prediction.
    """
    if not 1 <= max_per_source <= 5 or not 1 <= max_calls <= 60:
        raise ValueError("전파 한도 범위 초과")
    reagents = reagents or {}
    solvents = solvents or {}
    if not any(call.get("impurity", {}).get("status") == "success" for call in step_calls.values()):
        return {"status": "not_run", "traces": [],
                "note": "성공한 ASKCOS 부산물 예측이 없어 전파 계산을 실행하지 못했습니다. 부산물 없음 또는 안전 판정이 아닙니다."}
    beams = {}
    traces = []
    attempted = set()
    truncated = False
    for index, step in enumerate(route["steps"]):
        expected = canonical(step["product"])
        own = step_calls.get(index, {}).get("impurity", {})
        products = ((own.get("response") or {}).get("result") or {}).get("predict_expand", []) if own.get("status") == "success" else []
        direct = []
        for item in products if isinstance(products, list) else []:
            if not isinstance(item, dict) or not isinstance(item.get("prd_smiles"), str):
                continue
            try:
                value = canonical(item["prd_smiles"])
            except ValueError:
                continue
            if value != expected and value not in direct:
                direct.append(value)
        beams[index] = [{"smiles": value, "path": [index + 1], "source": "direct_prediction"}
                        for value in direct[:max_per_source]]
        for previous in range(index):
            parent = canonical(route["steps"][previous]["product"])
            if parent not in (canonical(s) for s in step["reactants"]):
                continue
            available = beams.get(previous, [])
            propagated = [h for h in available if h["source"] == "propagated_scenario"]
            direct_hypotheses = [h for h in available if h["source"] == "direct_prediction"]
            selected_hypotheses = (propagated[:1] + direct_hypotheses[:max_per_source-1]
                                   if propagated and max_per_source > 1 else
                                   propagated[:1] if propagated else direct_hypotheses[:max_per_source])
            for hypothesis in selected_hypotheses:
                changed = [hypothesis["smiles"] if canonical(s) == parent else s for s in step["reactants"]]
                signature = (index, tuple(changed))
                if signature in attempted or hypothesis["smiles"] == parent:
                    continue
                attempted.add(signature)
                if len(traces) >= max_calls:
                    truncated = True
                    break
                scenario = {"reactants": changed, "product": step["product"]}
                calls = askcos_step(scenario, modules=("forward", "impurity"),
                                    reagents=reagents.get(index, ""), solvent=solvents.get(index, ""))
                summary = summarize_askcos(calls, expected)
                outputs = [{"smiles": p["smiles"], "mode": p.get("mode"), "inspector_score": p.get("inspector_score")}
                           for p in summary["modules"]["impurity"].get("candidates", [])]
                traces.append({"from_step": previous + 1, "to_step": index + 1,
                               "parent_intermediate": parent, "hypothetical_input": hypothesis["smiles"],
                               "modified_reactants": changed, "hypothesis_path": hypothesis["path"] + [index + 1],
                               "status": "predicted_scenario" if any(c["status"] == "success" for c in calls.values()) else "failed",
                               "calls": calls, "products": outputs, "summary": summary})
                for item in outputs:
                    if item["smiles"] not in (b["smiles"] for b in beams[index]) and item["smiles"] != expected:
                        beams[index].append({"smiles": item["smiles"], "path": hypothesis["path"] + [index + 1],
                                             "source": "propagated_scenario"})
            if truncated:
                break
        if truncated:
            break
    return {"status": "truncated" if truncated else "completed", "traces": traces,
            "max_per_source": max_per_source, "max_calls": max_calls,
            "note": "소수 ASKCOS 예측 후보만 제한적으로 다음 단계에 대체 투입한 가정 시나리오. 원래 최종 생성물을 조건부 참조로 제공; 실제 전파·생성·잔류량/NDMA 부재 입증 아님."}


def recommended_propagation_limits(route: dict, step_calls: dict[int, dict] | None = None) -> dict:
    """Computational starting budget from connected steps and observed candidates.

    This is a reproducible workload heuristic, never a chemical optimum or an
    exhaustive impurity coverage claim. No predictions means budget is provisional.
    """
    step_calls = step_calls or {}
    edges = []
    for index, step in enumerate(route["steps"]):
        reactants = {canonical(s) for s in step["reactants"]}
        for previous in range(index):
            if canonical(route["steps"][previous]["product"]) in reactants:
                edges.append((previous, index))
    if not edges:
        return {"max_per_source": 1, "max_calls": 1,
                "reason": "이어지는 중간체 단계가 없어 전파 호출 예상 0건", "connected_edges": 0}
    counts = []
    for source, _ in edges:
        record = step_calls.get(source, {}).get("impurity", {})
        response = record.get("response") or {}
        data = response.get("result") or {} if isinstance(response, dict) else {}
        rows = data.get("predict_expand", []) if isinstance(data, dict) else []
        counts.append(len(rows) if record.get("status") == "success" and isinstance(rows, list) else None)
    observed = [n for n in counts if n is not None]
    width = 2 if any(n >= 2 for n in observed) or not observed else 1
    budget = min(12, max(1, len(edges) * width))
    return {"max_per_source": width, "max_calls": budget,
            "reason": f"연결 단계 {len(edges)}개 · 예측 후보 " + ("관측값 기반" if observed else "미실행으로 임시값") +
                      f" · 추가 호출 최대 {budget}회 (계산량 기준 추천)", "connected_edges": len(edges)}


def summarize_askcos(calls: dict, expected_product: str) -> dict:
    """Present native ASKCOS outputs without converting probabilities to yields."""
    expected = canonical(expected_product)
    result = {"modules": {}, "limitations": "투입량·당량·수율·생성량은 입력하지 않았습니다. QUARC의 상대량 범위는 모델 제안이며 실측 투입량이 아닙니다."}
    for name in ("context", "forward", "impurity"):
        record = calls.get(name)
        if not record:
            result["modules"][name] = {"status": "not_run"}
            continue
        summary = {"status": record.get("status", "failed"), "error": record.get("error")}
        if summary["status"] != "success":
            result["modules"][name] = summary
            continue
        body = record.get("response", {})
        data = body.get("result") if isinstance(body, dict) else None
        if name == "context":
            first = data[0] if isinstance(data, list) and data and isinstance(data[0], dict) else {}
            summary["conditions"] = [
                {"rank": item.get("rank"), "temperature_range": item.get("temperature"),
                 "agents": item.get("agents", []), "reactant_relative_ranges": item.get("reactant_amounts", []),
                 "agent_relative_ranges": item.get("agent_amounts", []), "model_score": item.get("score")}
                for item in first.get("predictions", []) if isinstance(item, dict)]
            summary["interpretation_status"] = "조건 후보 · 실험 검증 전" if summary["conditions"] else "조건 후보 미확인"
        elif name == "forward":
            predictions = data[0] if isinstance(data, list) and data and isinstance(data[0], list) else []
            summary["top_products"] = [{"rank": item.get("rank"), "smiles": item.get("outcome"),
                                        "model_probability": item.get("prob")}
                                       for item in predictions[:5] if isinstance(item, dict)]
            summary["expected_product_rank"] = next(
                (item.get("rank") for item in predictions if isinstance(item, dict)
                 and _same_structure(item.get("outcome"), expected)), None)
            summary["connectivity_only_rank"] = next(
                (item.get("rank") for item in predictions if isinstance(item, dict)
                 and _same_connectivity(item.get("outcome"), expected)), None)
            rank = summary["expected_product_rank"]
            summary["interpretation_status"] = ("목표 생성물 모델 상위 후보 · 수율 미확인" if rank is not None and rank <= 3 else
                                               "목표 생성물 모델 후순위 · 타당성 검토" if rank is not None else
                                               "동일 골격 후보 있음 · 입체화학 불일치/미확인, 성공 판정 불가" if summary["connectivity_only_rank"] is not None else
                                               "목표 생성물 반환 후보에서 미확인 · 성공 판정 불가")
        else:
            expanded = data.get("predict_expand", []) if isinstance(data, dict) else []
            candidates = []
            for item in expanded if isinstance(expanded, list) else []:
                if not isinstance(item, dict) or not isinstance(item.get("prd_smiles"), str):
                    continue
                try:
                    smiles = canonical(item["prd_smiles"])
                except ValueError:
                    continue
                if smiles != expected:
                    candidates.append({"smiles": smiles, "mode": item.get("modes_name"),
                                       "inspector_score": item.get("avg_insp_score")})
            summary["candidates"] = candidates
            summary["candidate_count"] = len(candidates)
            summary["interpretation_status"] = ("부산물 모델 후보 있음 · 위험/잔류 미평가" if candidates else
                                               "부산물 모델 후보 없음 · 안전 입증 아님")
        result["modules"][name] = summary
    return result


def admet_ames(smiles: list[str]) -> dict:
    """Optional local ADMET-AI AMES inference. Missing model means unknown, not safe."""
    requested = list(dict.fromkeys(canonical(s) for s in smiles))
    skipped = [{"smiles": s, "reason": "단원자 이온/비유기 구조 · AMES 모델 해석에서 제외"}
               for s in requested if not any(atom.GetAtomicNum() == 6 for atom in Chem.MolFromSmiles(s).GetAtoms())
               or Chem.MolFromSmiles(s).GetNumHeavyAtoms() < 3]
    excluded = {row["smiles"] for row in skipped}
    structures = [s for s in requested if s not in excluded]
    if not structures or len(structures) > 256:
        return {"status": "failed", "reason": "평가할 유기 구조가 없거나 256개를 초과했습니다", "assessments": [],
                "skipped": skipped}
    python = ROOT / ".admet-venv" / "Scripts" / "python.exe"
    if not python.is_file():
        return {"status": "unavailable", "reason": "ADMET-AI 별도 환경 미설치", "assessments": [], "skipped": skipped}
    try:
        completed = subprocess.run([str(python), str(ROOT / "src" / "admet_worker.py")],
                                   input=json.dumps({"smiles": structures}), text=True, encoding="utf-8", errors="replace",
                                   capture_output=True, timeout=300, check=False)
        if completed.returncode != 0:
            raise RuntimeError(f"worker exited {completed.returncode}: {completed.stderr[-500:]}")
        output = json.loads(completed.stdout)
        if output.get("status") == "failed" and "ModuleNotFoundError" in output.get("reason", ""):
            output["status"] = "unavailable"
        output["skipped"] = skipped
        return output
    except (OSError, ValueError, subprocess.TimeoutExpired, RuntimeError) as exc:
        return {"status": "failed", "reason": str(exc), "assessments": [], "skipped": skipped}


def impurity_candidates(askcos_results: dict, target: str, *, route=None) -> list[dict]:
    """Take only successful expanded-product predictions; never infer measured impurities."""
    target = canonical(target)
    candidates = {}
    for stage_key, step_results in askcos_results.items():
        expected = target
        if route is not None:
            try:
                index = int(str(stage_key).rsplit(":", 1)[-1])
                expected = canonical(route["steps"][index]["product"])
            except (ValueError, IndexError, KeyError):
                continue
        record = step_results.get("impurity", {})
        if record.get("status") != "success":
            continue
        response = record.get("response", {})
        result = response.get("result", {}) if isinstance(response, dict) else {}
        rows = result.get("predict_expand", []) if isinstance(result, dict) else []
        if not isinstance(rows, list):
            continue
        for row in rows[:100]:
            if not isinstance(row, dict) or not isinstance(row.get("prd_smiles"), str):
                continue
            try:
                structure = canonical(row["prd_smiles"])
            except ValueError:
                continue
            if structure != expected:
                candidates.setdefault(structure, {"smiles": structure, "source": "ASKCOS predict_expand",
                                                   "modes": row.get("modes_name"), "avg_insp_score": row.get("avg_insp_score")})
    return list(candidates.values())[:200]


def save_report(report: dict) -> Path:
    from identifiers import report_stem
    directory = ROOT / "runs" / datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    directory.mkdir(parents=True, exist_ok=False)
    path = directory / (report_stem(report.get("target_identity"), str(report.get("selected_route", "all-routes"))) + ".json")
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    return path
