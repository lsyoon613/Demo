"""Run three real end-to-end local examples and retain human/JSON reports.

Invoke after all services are installed: .venv/Scripts/python.exe -X utf8 scripts/verify_targets.py
This deliberately performs live external predictions and can take many minutes.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import identifiers
import reporting
import risk_flags
import service

OUTPUT = ROOT / "verified_reports"
CASES = (
    ("propranolol", "Enamine (2026-09)", 2),
    ("paclitaxel", "Enamine (2026-09)", 5),
    ("valsartan", "ZINC", 3),
)


def run_case(name: str, stock: str, desired_steps: int) -> dict:
    identity = identifiers.resolve(name)
    if identity["status"] != "resolved":
        raise RuntimeError(f"PubChem identity not resolved: {identity['status']}")
    compound = identity["compound"]
    target = compound["smiles"]
    print(f"[{name}] PubChem CID {compound['cid']} · live search {stock}", flush=True)
    routes = service.search(target, stock)
    if not routes:
        raise RuntimeError("AiZynthFinder returned no routes")
    comparison = service.compare(target, routes)
    ranked = sorted(enumerate(routes), key=lambda item: (
        0 if name != "paclitaxel" or comparison["routes"][item[0]]["origin_status"] == "origin_review_required" else 1,
        abs(len(item[1]["steps"]) - desired_steps), item[0]))
    index, route = ranked[0]
    row = comparison["routes"][index]
    print(f"[{name}] returned {len(routes)}, selected {route['id']} · {len(route['steps'])} steps · {row['origin_status']}", flush=True)
    calls = {}
    for step_index, step in enumerate(route["steps"]):
        print(f"[{name}] ASKCOS {step_index + 1}/{len(route['steps'])}", flush=True)
        calls[step_index] = service.askcos_step(step)
        print(f"[{name}] modules { {k: v['status'] for k, v in calls[step_index].items()} }", flush=True)
        if any(record["status"] != "success" for record in calls[step_index].values()):
            raise RuntimeError(f"ASKCOS unavailable/failed at step {step_index + 1}; restart local backend and rerun")
    recommended = service.recommended_propagation_limits(route, calls)
    print(f"[{name}] propagation recommendation {recommended}", flush=True)
    propagation = service.propagate_impurities(route, calls, max_per_source=recommended["max_per_source"],
                                               max_calls=recommended["max_calls"])
    ndma = risk_flags.ndma_review(route, calls, propagation)
    summaries = [service.summarize_askcos(calls[i], step["product"]) for i, step in enumerate(route["steps"])]
    direct = service.impurity_candidates({f"0:{k}": v for k, v in calls.items()}, target, route=route)
    propagated = list(dict.fromkeys(p["smiles"] for trace in propagation["traces"] for p in trace["products"]))
    # Bound optional AMES run for high-volume routes. No unanalysed structure is labelled safe.
    molecules = list(dict.fromkeys([s for step in route["steps"] for s in step["reactants"] + [step["product"]]] +
                                    [p["smiles"] for p in direct[:15]] + propagated[:10]))
    print(f"[{name}] ADMET-AI AMES {len(molecules)} unique inputs", flush=True)
    ames = service.admet_ames(molecules)
    materials = service.step_materials(route)
    scenario = service.yield_scenario(route, [None] * len(route["steps"]))
    html = reporting.route_report_html(route, materials, summaries, scenario, identity=identity,
                                       origin=row, propagation=propagation, ndma_flag=ndma, ames=ames)
    stem = identifiers.report_stem(identity, route["id"])
    if name == "propranolol" and stock == "ZINC":
        stem += "_ZINC"
    html_path = OUTPUT / (stem + ".html")
    json_path = OUTPUT / (stem + ".json")
    result = {"run_at_utc": datetime.now(timezone.utc).isoformat(), "input": name, "stock": stock,
              "identity": identity, "returned_routes": len(routes), "route": route,
              "route_comparison": row, "askcos": calls, "propagation": propagation,
              "propagation_recommendation": recommended, "ndma": ndma, "admet": ames,
              "admet_scope": {"direct_candidates_total": len(direct), "propagated_candidates_total": len(propagated),
                              "direct_tested_limit": 15, "propagated_tested_limit": 10},
              "summaries": summaries, "yield_scenario": scenario, "html_path": str(html_path)}
    html_path.write_text(html, encoding="utf-8")
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    print(f"[{name}] saved {html_path.name}; NDMA {ndma['status']}; AMES {ames['status']}", flush=True)
    return {"compound": name, "html": html_path.name, "json": json_path.name,
            "steps": len(route["steps"]), "route_id": route["id"],
            "module_statuses": [{k: v["status"] for k, v in record.items()} for record in calls.values()],
            "propagation_status": propagation["status"], "propagation_traces": len(propagation["traces"]),
            "origin_status": row["origin_status"], "ndma_status": ndma["status"], "ames_status": ames["status"],
            "ames_inputs": len(molecules)}


def main() -> int:
    OUTPUT.mkdir(exist_ok=True)
    results = []
    for case in CASES:
        try:
            results.append(run_case(*case))
        except Exception as exc:
            print(f"[{case[0]}] FAILED: {exc}", flush=True)
            traceback.print_exc()
            results.append({"compound": case[0], "status": "failed", "error": str(exc)})
        (OUTPUT / "verification_summary.json").write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return 1 if any(row.get("status") == "failed" for row in results) else 0


if __name__ == "__main__":
    sys.exit(main())
