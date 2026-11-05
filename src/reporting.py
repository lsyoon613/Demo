"""Self-contained readable HTML for one selected route, with inline 2D depictions."""
from html import escape

from rdkit import Chem
from rdkit.Chem.Draw import rdMolDraw2D


def _text(value) -> str:
    return escape("미확인" if value is None else str(value))


def _status(value) -> str:
    return _text({"success": "모델 응답 완료", "failed": "호출 실패", "not_run": "미실행"}.get(value, value))


def ames_source(smiles: str, route: dict, summaries: list[dict], propagation: dict | None = None) -> str:
    """Attribute screened structures before calling any flagged result a byproduct."""
    from identifiers import normalize
    structure = normalize(smiles)
    route_structures = {normalize(s) for step in route["steps"] for s in step["reactants"] + [step["product"]]}
    direct = {normalize(p["smiles"]) for summary in summaries
              for p in summary["modules"]["impurity"].get("candidates", [])}
    traced = {normalize(p["smiles"]) for trace in (propagation or {}).get("traces", [])
              for p in trace.get("products", [])}
    labels = []
    if structure in route_structures:
        labels.append("경로 반응물·중간체·목표물")
    if structure in direct:
        labels.append("ASKCOS 직접 부산물 후보")
    if structure in traced:
        labels.append("ASKCOS 전파 가정 후보")
    return " / ".join(labels) if labels else "출처 미확인"


def _structure(smiles: str) -> str:
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return "<p>구조 표시 불가</p>"
    drawer = rdMolDraw2D.MolDraw2DSVG(260, 170)
    drawer.DrawMolecule(mol)
    drawer.FinishDrawing()
    return drawer.GetDrawingText().replace("<?xml version='1.0' encoding='iso-8859-1'?>", "")


def _table(headers, rows) -> str:
    head = "".join("<th>" + _text(label) + "</th>" for label in headers)
    body = "".join("<tr>" + "".join("<td>" + _text(value) + "</td>" for value in row) + "</tr>" for row in rows)
    return "<table><thead><tr>" + head + "</tr></thead><tbody>" + body + "</tbody></table>"


def route_report_html(route: dict, materials: list[dict], summaries: list[dict], yield_result: dict,
                      *, identity=None, propagation=None, ndma_flag=None, ames=None,
                      origin=None, user_conditions=None, occurrence_lookups=None) -> str:
    if len(materials) != len(summaries) or len(materials) != len(yield_result["step_yields_pct"]):
        raise ValueError("경로 보고서의 단계 수가 일치하지 않습니다")
    compound = (identity or {}).get("compound") or {}
    out = ["<!doctype html><html lang='ko'><meta charset='utf-8'><title>합성 경로 검토</title>",
           "<style>body{font:16px system-ui;max-width:1100px;margin:2rem auto;padding:0 1rem;line-height:1.5}"
           "table{border-collapse:collapse;width:100%;margin:1rem 0}td,th{border:1px solid #bbb;padding:.5rem;vertical-align:top}"
           "svg{max-width:260px}code{overflow-wrap:anywhere}section{border-top:2px solid #bbb;padding:1rem 0}"
           "small{color:#444}</style>",
           "<h1>경로 " + _text(route["id"]) + " · " + _text(route["stock"]) + "</h1>",
            "<p><strong>목표 화합물:</strong> " + _text(compound.get("name")) + " · PubChem CID: " + _text(compound.get("cid")) +
            " · InChIKey: " + _text(compound.get("inchikey")) + "</p>",
            "<p>원래 입력 식별자: <code>" + _text((identity or {}).get("input")) + "</code> (" +
            _text((identity or {}).get("input_type")) + ")</p>",
           ("<p><a href='" + _text(compound["url"]) + "'>PubChem 상세 정보</a></p>" if compound.get("url") else ""),
           "<p>목표 SMILES: <code>" + _text(route["target"]) + "</code></p>",
           "<p><strong>경로 상대 수율:</strong> " +
           (_text(f"{yield_result['overall_relative_yield_pct']:.3g}%") if yield_result["overall_relative_yield_pct"] is not None else "미산정") +
           " · " + _text(yield_result["reason"]) + "</p>",
            "<p><strong>최종 산출량:</strong> 미산정 (실제 투입량·당량·수율 근거 없음). 아래 조건과 부산물은 예측 결과이며 실험 검증/잔류량 측정이 아닙니다.</p>"]
    if origin:
        out.append("<section><h2>출발물질 유래 검토</h2><p>" + _text(origin.get("mode")) + " · " +
                   _text(origin.get("origin_note")) + "</p>")
        if origin.get("origin_options"):
            out.append("<h3>원료 조달 시나리오별 조건부 분류 (현재 제조 기원 확인 전)</h3>")
            out.append(_table(["가정", "합성 분류", "추가 확인 자료"],
                              [(option["assumption"], option["classification"], option["evidence_needed"])
                               for option in origin["origin_options"]]))
        out.append(_table(["출발물질 SMILES", "유래 상태", "근거", "설명"],
                          [(leaf["smiles"], leaf["origin"]["status"], leaf["origin"].get("evidence"),
                            leaf["origin"].get("note")) for leaf in origin.get("leaves", [])]))
        out.append(_table(["SMILES", "Enamine 제품 ID", "제품 페이지", "표시 포장", "실제 표시 가격", "조회 시점", "제조 기원"],
                          [(leaf["smiles"], match["catalog_id"], match["url"], f"{quote['amount']} {quote['unit']}",
                            f"{quote['currency']} {quote['price']}", quote["observed_at"],
                            leaf.get("supply_origin", {}).get("note", "제조 기원 미확인"))
                           for leaf in origin.get("leaves", []) for match in leaf.get("matches", [])
                           for quote in match.get("quotes", [])]))
        if occurrence_lookups:
            out.append("<h3>선택 경로 COCONUT 조회 (동일 구조 DB 기록 ≠ 해당 원료의 추출 증거)</h3>")
            out.append(_table(["SMILES", "조회 상태", "COCONUT ID", "출처 URL", "설명"],
                              [(smiles, item.get("status"), item.get("id"), item.get("evidence"), item.get("note"))
                               for smiles, item in occurrence_lookups.items()]))
        out.append("</section>")
    user_conditions = user_conditions or {}
    for index, (step, summary, user_yield) in enumerate(zip(materials, summaries, yield_result["step_yields_pct"]), 1):
        out.append("<section><h2>" + str(index) + "단계 · 사용자 입력 수율: " +
                   (_text(f"{user_yield:g}%") if user_yield is not None else "미확인") + "</h2>")
        out.append("<h3>반응물 · 외부 출발물질 / 이전 단계 중간체</h3><div>")
        for reactant in step["reactants"]:
            out.append("<div style='display:inline-block;vertical-align:top;max-width:280px'><b>" + _text(reactant["role"]) +
                       "</b><br>" + _structure(reactant["smiles"]) + "<br><code>" + _text(reactant["smiles"]) + "</code></div>")
        product = step["product"]
        out.append("</div><h3>" + _text(product["role"]) + "</h3>" + _structure(product["smiles"]) +
                   "<p><code>" + _text(product["smiles"]) + "</code></p>")
        out.append("<p>사용자 입력 시약: " + _text(user_conditions.get("reagents", {}).get(index - 1) or "미입력") +
                   " · 사용자 입력 용매: " + _text(user_conditions.get("solvents", {}).get(index - 1) or "미입력") + "</p>")
        modules = summary["modules"]
        context = modules["context"]
        out.append("<h3>QUARC 조건 후보 (" + _status(context["status"]) + ")</h3>")
        conditions = context.get("conditions", [])
        if conditions:
            out.append(_table(["순위", "온도 범위 (모델 출력)", "제안 시약/용매 SMILES", "모델 점수"],
                              [(c["rank"], c["temperature_range"], ", ".join(c["agents"]), c["model_score"]) for c in conditions]))
            for condition in conditions:
                out.append("<p>조건 " + _text(condition["rank"]) + "위 · 모델 제안 상대량: " +
                           _text(condition["reactant_relative_ranges"]) + " / 시약 상대량: " +
                           _text(condition["agent_relative_ranges"]) + "</p>")
        else:
            out.append("<p>조건 미확인 · " + _text(context.get("error")) + "</p>")
        forward = modules["forward"]
        out.append("<h3>정방향 예측 (" + _status(forward["status"]) + ")</h3>")
        out.append("<p>해석 상태: " + _text(forward.get("interpretation_status") or "실행 결과 미확인") + "</p>")
        out.append("<p>입력 기대 생성물 반환 순위: " + _text(forward.get("expected_product_rank")) + " (모델 상대 확률 ≠ 수율)</p>")
        if forward.get("expected_product_rank") is None and forward.get("connectivity_only_rank") is not None:
            out.append("<p>입체화학을 무시한 골격만 일치하는 후보 순위: " +
                       _text(forward["connectivity_only_rank"]) + " · 목표 입체구조 생성 확인 아님</p>")
        if forward.get("top_products"):
            out.append(_table(["순위", "생성물 SMILES", "모델 상대 확률"],
                              [(p["rank"], p["smiles"], p["model_probability"]) for p in forward["top_products"]]))
        impurity = modules["impurity"]
        out.append("<h3>부산물/불순물 예측 (" + _status(impurity["status"]) + ")</h3>")
        out.append("<p>해석 상태: " + _text(impurity.get("interpretation_status") or "실행 결과 미확인") + "</p>")
        out.append("<p>목표물 제외 후보: " + _text(impurity.get("candidate_count")) + "개. 실제 검출/농도/잔류량이 아닙니다.</p>")
        if impurity.get("candidates"):
            out.append(_table(["후보 SMILES", "예측 모드", "Inspector 모델 점수"],
                              [(p["smiles"], p["mode"], p["inspector_score"]) for p in impurity["candidates"]]))
        out.append("</section>")
    out.append("<section><h2>단계 간 부산물 전파 검토</h2>")
    if propagation and propagation.get("traces"):
        out.append("<p>ASKCOS 대체 투입 가정 " + _text(len(propagation["traces"])) + "건 · " +
                   _text(propagation.get("status")) + " · 실제 전파/잔류 증거가 아닙니다.</p>")
        out.append(_table(["출처 단계", "후속 단계", "기존 중간체", "가정한 부산물 SMILES", "후속 단계 예측 후보 수", "상태"],
                          [(t["from_step"], t["to_step"], t["parent_intermediate"], t["hypothetical_input"], len(t["products"]), t["status"])
                           for t in propagation["traces"]]))
        for trace in propagation["traces"]:
            out.append("<h3>" + _text(trace["from_step"]) + " → " + _text(trace["to_step"]) +
                       "단계 가정 후보 · " + _text(trace["hypothetical_input"]) + "</h3>")
            out.append("<p>가정한 반응물 조합: " + _text(" . ".join(trace["modified_reactants"])) + "</p>")
            out.append(_table(["예측 생성물 SMILES", "예측 모드", "Inspector 모델 점수"],
                              [(p["smiles"], p.get("mode"), p.get("inspector_score")) for p in trace["products"]]))
    else:
        out.append("<p>전파 시나리오 미실행 또는 선택한 후보/연결된 중간체 없음. 생성 불가를 뜻하지 않습니다.</p>")
    if ndma_flag:
        out.append("<p><strong>NDMA 검토 플래그:</strong> " + _text(ndma_flag["label"]) +
                   " · " + _text(ndma_flag["note"]) + "</p>")
    if ames:
        out.append("<h3>ADMET-AI AMES · 예측값 (상태 표시 기준 0.5)</h3>")
        out.append("<p>0.5 이상이면 검토 필요. 0.5 미만이어도 모델 추정치이므로 안전이 입증된 것은 아닙니다. 규제상 판정 기준이 아닙니다.</p>")
        if ames.get("skipped"):
            out.append("<p>모델 해석에서 제외된 구조 (미평가 ≠ 안전):</p>" +
                       _table(["SMILES", "평가 제외 사유"],
                              [(r["smiles"], r["reason"]) for r in ames["skipped"]]))
        if ames.get("status") == "success":
            from risk_flags import ames_flag
            out.append(_table(["SMILES", "예측 대상 출처", "AMES 모델 점수", "모델 기준 상태"],
                              [(r["smiles"], ames_source(r["smiles"], route, summaries, propagation),
                                r["ames_score"], ames_flag(r["ames_score"])["label"])
                               for r in ames.get("assessments", [])]))
        else:
            out.append("<p>AMES 평가 미완료 · " + _text(ames.get("status")) + "</p>")
    out.append("</section><small>AiZynthFinder 경로와 ASKCOS 제안은 실험적으로 검증된 합성법이 아닙니다. 사용자 입력 단계 수율 외에는 수율을 추정하지 않습니다.</small></html>")
    return "".join(out)
