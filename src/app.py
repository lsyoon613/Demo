"""One workflow: route discovery -> real quotes -> optional step analysis -> export."""
import importlib
import json

import streamlit as st

import service
import reporting
import route_views
import identifiers
import natural_origin
import risk_flags
import remote_enamine

# Streamlit reruns app.py in a persistent interpreter. Refresh our own small
# modules too, so editing an adapter cannot leave old functions in sys.modules.
service = importlib.reload(service)
reporting = importlib.reload(reporting)
route_views = importlib.reload(route_views)
identifiers = importlib.reload(identifiers)
natural_origin = importlib.reload(natural_origin)
risk_flags = importlib.reload(risk_flags)


@st.cache_data(ttl=86400, show_spinner=False)
def coconut_lookup(smiles: str) -> dict:
    result = natural_origin.coconut_occurrence(smiles)
    if result["status"] == "lookup_failed":
        raise ValueError(result["note"])
    return result


st.set_page_config(page_title="합성 경로 통합 검토", layout="wide")
st.title("합성 경로 통합 검토")
st.caption("독립 연구 도구 · AiZynthFinder / Enamine 포장 견적 / 로컬 ASKCOS / ADMET-AI")

target = st.text_input("목표물 식별자 · SMILES / CAS / InChI / InChIKey / CID / 화합물명",
                       value="CC(C)NCC(O)COc1cccc2ccccc12")
available_stocks = [name for name, path in service.STOCKS.items()
                    if path.is_file() or name == "Enamine (2026-09)" and remote_enamine.configured()]
stock = st.selectbox("AiZynthFinder 탐색 재고", available_stocks or ["ZINC"])
if not service.DB.is_file() and not remote_enamine.configured():
    st.warning("Enamine 카탈로그 DB가 설치되지 않았습니다. 구조·가격 일치 여부는 미확인입니다. ZINC 경로 탐색은 모델 설치 후 사용할 수 있습니다.")
if not available_stocks:
    st.info("탐색용 모델/재고를 먼저 설치하세요: python setup_models.py")
st.caption("새 경로 탐색 = 현재 입력 구조로 AiZynthFinder 실시간 계산 · 저장된 예시 = 이전에 계산한 프로프라놀롤 경로만 불러오기")
if st.button("입력 구조 표준화 · PubChem 정보 조회"):
    try:
        st.session_state.identity = identifiers.resolve(target)
        st.session_state.pubchem_synonyms = []
        if st.session_state.identity["status"] == "resolved":
            try:
                st.session_state.pubchem_synonyms = identifiers.synonyms(st.session_state.identity["compound"]["cid"])
            except ValueError as exc:
                st.warning(f"동의어 조회 실패 (구조 조회 결과는 유지): {exc}")
    except ValueError as exc:
        st.error(f"식별자 조회 실패: {exc}")
identity = st.session_state.get("identity") if st.session_state.get("identity", {}).get("input") == target.strip() else None
if identity and identity["status"] == "ambiguous":
    st.warning(identity["note"])
    chosen_cid = st.selectbox("PubChem 후보 CID 선택", identity["candidate_cids"])
    if st.button("선택한 CID 구조 확정"):
        compound = identifiers.properties(chosen_cid)
        st.session_state.identity = {"status": "resolved", "input_type": identity["input_type"],
                                     "input": target.strip(), "candidate_cids": identity["candidate_cids"], "compound": compound}
        st.rerun()
elif identity and identity["status"] == "structure_mismatch":
    st.warning("PubChem 구조와 입력 구조가 다릅니다. 자동 치환하지 않았습니다.")
    if st.button("입력한 RDKit 구조 유지"):
        st.session_state.identity = {"status": "local_only", "input": target.strip(),
                                     "input_type": identity["input_type"], "candidate_cids": identity["candidate_cids"],
                                     "compound": {"smiles": identity["local_smiles"], "name": None, "cid": None,
                                                  "source": "입력 RDKit 구조 (PubChem과 불일치)"}}
        st.rerun()
if identity and identity.get("compound"):
    compound = identity["compound"]
    with st.expander("확인된 목표 화합물 정보 · PubChem 원문 열기", expanded=False):
        st.write("**입력 종류:**", identity["input_type"], "· **식별 상태:**", identity["status"])
        st.write("**명칭:**", compound.get("name") or "미확인", "· **PubChem CID:**", compound.get("cid") or "미확인")
        st.write("**분자식:**", compound.get("formula") or "미확인", "· **분자량:**", compound.get("molecular_weight") or compound.get("rdkit_molecular_weight") or "미확인")
        st.write("**InChIKey:**", compound.get("inchikey") or "미확인")
        st.write("**InChI:**", compound.get("inchi") or "미확인")
        st.write("**표준화된 구조 (입체/염 유지):**")
        st.code(compound["smiles"], language=None)
        if compound.get("url"):
            st.link_button("PubChem 상세 페이지 열기", compound["url"])
        synonyms = st.session_state.get("pubchem_synonyms", [])
        cas_numbers = [item for item in synonyms if identifiers.cas_valid(item)]
        st.write("**PubChem 동의어 중 CAS 표기 (공식 CAS 검증 아님):**", ", ".join(cas_numbers[:8]) or "미확인")
        st.caption("입체화학, 염·프로톤화 상태를 보존합니다. PubChem 명칭/동의어만으로 천연 유래·규제 분류는 판정하지 않습니다.")
left, right = st.columns(2)
with left:
    if st.button("새 경로 탐색", type="primary"):
        try:
            resolved = identity or identifiers.resolve(target)
            st.session_state.identity = resolved
            if resolved["status"] not in ("resolved", "local_only"):
                raise ValueError("PubChem 후보가 여러 개이거나 입력 구조와 다릅니다. 먼저 구조를 선택·확정하세요.")
            normalized_target = resolved["compound"]["smiles"]
            with st.spinner("AiZynthFinder 탐색 중"):
                routes = service.search(normalized_target, stock)
            st.session_state.routes = routes
            st.session_state.askcos = {}
            st.session_state.propagation = {}
            st.session_state.origin_lookups = {}
            st.session_state.admet = None
            st.session_state.admet_scope = None
            st.session_state.target = normalized_target
            st.session_state.input_identity = target.strip()
            st.session_state.search_origin = "실시간 AiZynthFinder 탐색"
            st.session_state.run_epoch = st.session_state.get("run_epoch", 0) + 1
            st.success(f"{len(routes)}개 경로 검색")
        except Exception as exc:
            st.error(f"경로 탐색 실패: {exc}")
with right:
    if st.button("저장된 프로프라놀롤 예시 불러오기"):
        if target.strip() != "CC(C)NCC(O)COc1cccc2ccccc12":
            st.warning("저장 예시는 프로프라놀롤 전용입니다. 목표물 입력을 기본 프로프라놀롤 SMILES로 바꾸거나 현재 식별자로 새 경로를 탐색하세요.")
            st.stop()
        payload = json.loads((service.ROOT / "data" / "propranolol_enamine_routes.json").read_text(encoding="utf-8"))
        st.session_state.routes = [
            {"id": r["id"], "target": service.canonical(r["target"]), "stock": "Enamine (2026-09)",
             "origin": "stored_example", "searched_at_utc": None,
             "steps": [{"reactants": s["reactants"], "product": s["products"][0]} for s in r["steps"]]}
            for r in payload["routes"]]
        st.session_state.target = service.canonical(payload["routes"][0]["target"])
        st.session_state.input_identity = target.strip()
        st.session_state.identity = {"status": "local_only", "input": target.strip(), "input_type": "stored_example",
                                     "compound": {"smiles": st.session_state.target, "name": "Propranolol (stored example)", "cid": None}}
        st.session_state.search_origin = "저장된 프로프라놀롤 Enamine 탐색 결과"
        st.session_state.run_epoch = st.session_state.get("run_epoch", 0) + 1
        st.session_state.askcos = {}
        st.session_state.propagation = {}
        st.session_state.origin_lookups = {}
        st.session_state.admet = None
        st.session_state.admet_scope = None

identity = st.session_state.get("identity") if st.session_state.get("identity", {}).get("input") == target.strip() else None
routes = st.session_state.get("routes", [])
if routes:
    if target.strip() != st.session_state.get("input_identity"):
        st.warning("입력 식별자가 현재 경로를 탐색할 때와 다릅니다. 새 경로 탐색을 누르세요.")
        st.stop()
    target_smiles = st.session_state.target
    distinct = service.distinct_routes(routes)
    st.write(f"**경로 출처: {st.session_state.get('search_origin', '이전 세션 · 출처 미기록')}** · 반환 {distinct['returned']}개 / 반응 단계 구성상 서로 다른 경로 {distinct['unique_reaction_sets']}개")
    if routes[0].get("searched_at_utc"):
        st.caption("탐색 완료(UTC): " + routes[0]["searched_at_utc"])
    if distinct["duplicate_groups"]:
        st.warning(f"중복 반응 조합: {distinct['duplicate_groups']}")
    st.caption("서로 다른 경로는 정규화된 반응물→생성물 단계 구성 기준입니다. 합성 가능성·실험적 독립성 검증은 아닙니다.")
    selected = st.selectbox("상세 경로", range(len(routes)), format_func=lambda i: f"{routes[i]['id']} · {len(routes[i]['steps'])}단계")
    origin_key = (st.session_state.get("run_epoch", 0), selected)
    if st.button("선택 경로 출발물질 COCONUT 자연계 존재 기록 조회 (선택)"):
        lookups = {}
        with st.spinner("COCONUT에서 이 경로의 출발물질만 구조별 조회 중"):
            for smiles in service.route_leaves(routes[selected])[:12]:
                try:
                    lookups[smiles] = coconut_lookup(smiles)
                except ValueError as exc:
                    lookups[smiles] = {"status": "lookup_failed", "note": str(exc)}
        st.session_state.setdefault("origin_lookups", {})[origin_key] = lookups
    selected_lookups = st.session_state.get("origin_lookups", {}).get(origin_key, {})
    if selected_lookups:
        st.dataframe([{"출발물질": smiles, "조회 상태": result["status"],
                       "COCONUT ID": result.get("id"), "근거 URL": result.get("evidence"),
                       "설명": result.get("note")} for smiles, result in selected_lookups.items()], hide_index=True)
        st.caption("COCONUT 등재/생물 출처 연결은 이 경로에서 실제 사용한 원료가 추출품이라는 증거가 아닙니다. 미등재도 합성 원료의 증거가 아닙니다. 동일 구조 1일 캐시, 선택 경로에서만 조회합니다.")
    natural = st.text_input("천연물 유래 출발 원료 SMILES (선택)")
    natural_reference = st.text_input("그 원료의 천연 유래 근거 URL/문헌 (지정할 경우 입력)")
    extraction = st.text_input("목표물 직접 추출에 관한 문헌·공급 근거 (선택)")
    try:
        report = service.compare(target_smiles, routes, natural, extraction, natural_reference, selected_lookups)
    except Exception as exc:
        st.error(f"비교 오류: {exc}")
        st.stop()
    st.subheader("구매·추출·합성·반합성 후보 비교")
    st.info("우선 검토 제안: " + report["next_check"])
    st.write("**목표물 직접 구매**:", "Enamine 카탈로그 미설치 · 미확인" if report["catalog_status"] == "catalog_not_installed" else
             "Enamine 구조 정확 일치" if report["purchase"]["matches"] else "Enamine 스냅샷 미일치 · 다른 공급사 미확인")
    for match in report["purchase"]["matches"]:
        st.write(match["catalog_id"], match["quotes"])
    st.write("**직접 추출**:", report["extraction"]["status"])
    st.caption(report["note"])
    st.dataframe([{"경로": r["id"], "방식": r["mode"], "단계": r["steps"],
                   "출발물질 수": len(r["leaves"]), "Enamine 일치": r["catalog_coverage"],
                   "포장 가격 확인": r["price_coverage"]} for r in report["routes"]], hide_index=True)
    route = routes[selected]
    row = report["routes"][selected]
    st.caption("출발물질 유래: " + row["origin_note"])
    if row.get("origin_options"):
        st.write("**원료 실제 출처에 따른 조건부 분류:**")
        st.dataframe(row["origin_options"], hide_index=True)
        for leaf in row["leaves"]:
            if leaf["origin"]["status"] not in {"documented_natural_occurrence", "database_occurrence_record"}:
                continue
            for match in leaf["matches"]:
                st.write(f"**출발물질 구매 일치:** {leaf['smiles']} · Enamine {match['catalog_id']} · {match['url']}")
                if match["quotes"]:
                    quote = match["quotes"][0]
                    st.write("최소 표시 포장 견적:", f"{quote['amount']:g} {quote['unit']} · {quote['currency']} {quote['price']:g}",
                             "· 조회 시점:", quote["observed_at"])
                st.caption(leaf["supply_origin"]["note"])
    materials = service.step_materials(route)
    st.subheader("선택 경로의 전체 반응 · 구조와 SMILES")
    st.caption("생성물과 다음 단계 반응물이 같은 구조인 경우만 중간체로 표기합니다. 그림은 SMILES의 2D 표시입니다.")
    for material_step in materials:
        with st.expander(f"{material_step['number']}단계 · {', '.join(p['smiles'] for p in material_step['reactants'])} → {material_step['product']['smiles']}", expanded=len(materials) == 1):
            route_views.show_step_structures(material_step, material_step["number"])
    st.subheader("말단 출발물질 · 실제 포장 견적")
    leaf_key = (st.session_state.get("run_epoch", 0), selected)
    if st.button("선택 경로 출발물질 PubChem 일괄 조회"):
        found = []
        for leaf in row["leaves"][:30]:
            try:
                item = identifiers.resolve(leaf["smiles"])
                compound = item.get("compound") or {}
                found.append({"smiles": leaf["smiles"], "status": item["status"],
                              "name": compound.get("name"), "cid": compound.get("cid"),
                              "formula": compound.get("formula"), "url": compound.get("url"),
                              "origin_flag": leaf["origin"]["status"]})
            except ValueError as exc:
                found.append({"smiles": leaf["smiles"], "status": "lookup_failed", "error": str(exc),
                              "origin_flag": leaf["origin"]["status"]})
        st.session_state.setdefault("leaf_pubchem", {})[leaf_key] = found
    if st.session_state.get("leaf_pubchem", {}).get(leaf_key):
        st.dataframe(st.session_state.leaf_pubchem[leaf_key], hide_index=True)
        st.caption("PubChem의 화합물명·구조 매칭은 자연 유래 인증이 아닙니다. 유래 플래그는 별도 문헌/구조 유사성 기준으로 표시합니다.")
    for leaf in row["leaves"]:
        with st.expander(leaf["smiles"] + " · " + leaf["status"], expanded=True):
            st.write("유래 판정:", leaf["origin"]["status"], "·", leaf["origin"]["note"])
            st.caption("원료 공급 기원: " + leaf["supply_origin"]["note"])
            if leaf["origin"].get("evidence"):
                st.write("유래 근거:", leaf["origin"]["evidence"])
            for match in leaf["matches"]:
                st.write(match["catalog_id"], match["url"])
                if match["quotes"]:
                    st.dataframe(match["quotes"], hide_index=True)
                else:
                    st.info("가격 미확인 (0원이 아님)")
            if not leaf["matches"]:
                st.info("Enamine DB 미설치 · 미확인" if report["catalog_status"] == "catalog_not_installed"
                        else "Enamine 스냅샷 미일치; 다른 공급처 미확인")
    st.subheader("경로별 ASKCOS · 정방향 반응 단계 지정")
    user_reagents = {}
    user_solvents = {}
    with st.expander("각 단계에 실제로 사용할 시약·용매 구조 입력 (선택 · 미입력은 미확인)"):
        for i in range(len(route["steps"])):
            user_reagents[i] = st.text_input(f"{i + 1}단계 시약 SMILES (선택)",
                                             key=f"reagent_{st.session_state.get('run_epoch', 0)}_{selected}_{i}").strip()
            user_solvents[i] = st.text_input(f"{i + 1}단계 용매 SMILES (선택)",
                                             key=f"solvent_{st.session_state.get('run_epoch', 0)}_{selected}_{i}").strip()
        st.caption("빈칸은 실험 시약·용매를 모른다는 뜻입니다. QUARC 추천 조건을 실제 투입 조건으로 자동 적용하지 않습니다.")
    step_index = st.selectbox("분석할 단계", range(len(route["steps"])), format_func=lambda i: f"{i+1}단계 · 생성물 {route['steps'][i]['product']}")
    step = route["steps"][step_index]
    st.caption("현재 단계: " + ".".join(step["reactants"]) + " → " + step["product"])
    st.info("ASKCOS에는 이 단계의 반응물/기대 생성물 구조만 보냅니다. 실제 투입량·당량·수율은 보내지 않으며, 아래 상대량 범위는 QUARC가 예측한 조건 후보입니다.")
    modules = st.multiselect("요청할 로컬 모듈", ["context", "forward", "impurity"], default=["context", "forward", "impurity"])
    current_step_calls = {i: st.session_state.get("askcos", {}).get(f"{selected}:{i}", {})
                          for i in range(len(route["steps"]))}
    recommended = service.recommended_propagation_limits(route, current_step_calls)
    st.caption("전파 계산 상한 권장 초기값: " + recommended["reason"] +
               ". 계산량을 제한하기 위한 설정이며 화학적으로 최적이거나 모든 부산물을 포괄한다는 뜻은 아닙니다.")
    customize_limits = st.checkbox("전파 계산 상한 직접 조정", value=False)
    max_per_source = (st.slider("단계당 부산물 후보 상한", 1, 5, recommended["max_per_source"])
                      if customize_limits else recommended["max_per_source"])
    max_calls = (st.slider("ASKCOS 추가 호출 상한", 1, 60, recommended["max_calls"])
                 if customize_limits else recommended["max_calls"])
    if st.button("선택 단계 ASKCOS 호출", disabled=not modules):
        try:
            with st.spinner("로컬 ASKCOS 호출 중 (모듈별 최대 180초)"):
                st.session_state.askcos.setdefault(f"{selected}:{step_index}", {}).update(service.askcos_step(
                    step, modules, reagents=user_reagents[step_index], solvent=user_solvents[step_index]))
            st.session_state.propagation.pop(selected, None)
        except ValueError as exc:
            st.warning(f"시약·용매 구조 확인: {exc}")
    if st.button("선택 경로의 모든 단계 ASKCOS 실행", disabled=not modules):
        try:
            progress = st.progress(0, text="경로 단계 분석 시작")
            for index, current in enumerate(route["steps"]):
                with st.spinner(f"{index + 1}/{len(route['steps'])}단계 분석 중"):
                    st.session_state.askcos.setdefault(f"{selected}:{index}", {}).update(service.askcos_step(
                        current, modules, reagents=user_reagents[index], solvent=user_solvents[index]))
                progress.progress((index + 1) / len(route["steps"]), text=f"{index + 1}/{len(route['steps'])}단계 완료")
            if "impurity" in modules:
                st.info("이전 단계의 예측 부산물을 다음 단계의 해당 중간체 대신 넣는 제한적 가정 시나리오를 추가 계산 중입니다. 실제 전파·노출 검증은 아닙니다.")
                calls_by_step = {i: st.session_state.askcos.get(f"{selected}:{i}", {}) for i in range(len(route["steps"]))}
                with st.spinner("ASKCOS 부산물 전파 시나리오 계산 중"):
                    st.session_state.propagation[selected] = service.propagate_impurities(
                        route, calls_by_step, max_per_source=max_per_source, max_calls=max_calls,
                        reagents=user_reagents, solvents=user_solvents)
        except ValueError as exc:
            st.warning(f"단계 입력/전파 확인: {exc}")
    route_views.show_askcos_results(st.session_state.get("askcos", {}).get(f"{selected}:{step_index}", {}), step["product"])
    propagation = st.session_state.get("propagation", {}).get(selected, {})
    if propagation:
        st.write(f"**단계 간 부산물 전파 가정:** {len(propagation['traces'])}개 추가 시나리오 · " +
                 ("설정 상한으로 중단" if propagation["status"] == "truncated" else "설정 범위 실행 완료"))
        st.caption(propagation["note"])
        st.dataframe([{"출처 단계": p["from_step"], "다음 단계": p["to_step"],
                       "대체한 중간체": p["parent_intermediate"], "가정 부산물": p["hypothetical_input"],
                       "입력 변경 후 후보 수": len(p["products"]), "실행 상태": p["status"]}
                      for p in propagation["traces"]], hide_index=True)
        with st.expander("단계 간 전파 가정의 후속 생성물 후보 상세"):
            st.dataframe([{"전파": f"{trace['from_step']}→{trace['to_step']}",
                           "가정 부산물": trace["hypothetical_input"], "후속 생성물": product["smiles"],
                           "예측 모드": product.get("mode"), "Inspector 모델 점수": product.get("inspector_score")}
                          for trace in propagation["traces"] for product in trace["products"]], hide_index=True)
    ndma_flag = risk_flags.ndma_review(route,
        {i: st.session_state.askcos.get(f"{selected}:{i}", {}) for i in range(len(route["steps"]))},
        propagation, user_reagents)
    st.write("**NDMA 경로 검토 플래그:**", ndma_flag["label"])
    st.caption(ndma_flag["note"])
    if ndma_flag["evidence"]:
        st.write("검토 근거:", ndma_flag["evidence"])
    st.subheader("ADMET-AI · AMES 예측")
    st.caption("AMES 상태 표시 기준: 예측 점수 0.5 이상이면 검토 필요. 0.5 미만이어도 모델 추정치이므로 안전이 입증된 것은 아닙니다. 이는 규제상 판정 기준이 아닙니다.")
    selected_askcos = {k: v for k, v in st.session_state.get("askcos", {}).items() if k.startswith(f"{selected}:")}
    predicted_impurities = service.impurity_candidates(selected_askcos, target_smiles, route=route)
    propagated_impurities = list({product["smiles"] for trace in propagation.get("traces", [])
                                   for product in trace.get("products", [])})
    include_impurities = st.checkbox(f"ASKCOS 후보 구조 {len(predicted_impurities)}개도 AMES 입력에 포함 (예측 부산물; 검출/잔류 미확인)",
                                      disabled=not predicted_impurities)
    include_propagated = st.checkbox(f"단계 간 전파 가정 후보 구조 {len(propagated_impurities)}개도 AMES 입력에 포함",
                                     disabled=not propagated_impurities)
    molecules = [s for item in route["steps"] for s in item["reactants"] + [item["product"]]]
    if include_impurities:
        molecules.extend(item["smiles"] for item in predicted_impurities)
    if include_propagated:
        molecules.extend(propagated_impurities)
    current_scope = (selected, tuple(service.canonical(s) for s in molecules))
    if st.button("선택 경로의 출발물질·생성물 AMES 평가"):
        with st.spinner("ADMET-AI 실행 중"):
            st.session_state.admet = service.admet_ames(molecules)
        st.session_state.admet_scope = current_scope
    current_admet = st.session_state.get("admet") if st.session_state.get("admet_scope") == current_scope else None
    if current_admet:
        if current_admet.get("skipped"):
            st.info(f"비유기/단원자 이온 {len(current_admet['skipped'])}개를 AMES 해석에서 제외했습니다. 미평가 ≠ 안전.")
            with st.expander("AMES 평가 제외 구조"):
                st.dataframe(current_admet["skipped"], hide_index=True)
        if current_admet["status"] == "success":
            st.write(f"ADMET-AI {current_admet.get('version', '')} · AMES 모델 점수 (예측값)")
            flagged_ames = sum(risk_flags.ames_flag(item["ames_score"])["status"] == "model_flagged"
                               for item in current_admet["assessments"])
            if flagged_ames:
                st.warning(f"AMES 모델 점수 0.5 이상 {flagged_ames}개 구조 · 검토 필요 (예측값, 안전/규제 확정 아님)")
            ames_summaries = [service.summarize_askcos(st.session_state.get("askcos", {}).get(f"{selected}:{i}", {}), stage["product"])
                              for i, stage in enumerate(route["steps"])]
            st.dataframe([{"구조 SMILES": item["smiles"], "예측 대상 출처": reporting.ames_source(item["smiles"], route, ames_summaries, propagation),
                           "AMES 예측 점수": item["ames_score"],
                           "모델 기준 상태": risk_flags.ames_flag(item["ames_score"])["label"]}
                          for item in current_admet["assessments"]], hide_index=True)
        else:
            st.warning("AMES 평가 불가: " + current_admet.get("reason", current_admet["status"]))
    st.caption("AMES 예측은 구조 검토 자료이며 ICH M7 규제 분류나 사용 금지 판정이 아닙니다.")
    st.subheader("선택 경로 전체 · 조건·부산물·수율 요약")
    st.caption("실제 측정하거나 별도 근거로 정한 단계 수율만 입력하세요. 빈칸은 미확인입니다. ASKCOS 모델 점수·확률에서 수율을 만들지 않습니다.")
    entered = []
    bad_yield = False
    for index in range(len(route["steps"])):
        raw = st.text_input(f"{index + 1}단계 수율 % (선택 · 사용자 입력)",
                            key=f"yield_{st.session_state.get('run_epoch', 0)}_{selected}_{index}")
        try:
            value = float(raw) if raw.strip() else None
            if value is not None and not 0 < value <= 100:
                raise ValueError()
        except ValueError:
            bad_yield = True
            value = None
            st.warning(f"{index + 1}단계: 0 초과 100 이하의 숫자를 입력하세요.")
        entered.append(value)
    yield_result = service.yield_scenario(route, entered)
    if yield_result["overall_relative_yield_pct"] is not None and not bad_yield:
        st.metric("직렬 경로 · 입력 수율의 누적 상대 비율", f"{yield_result['overall_relative_yield_pct']:.3g}%")
    else:
        st.info("전체 수율: 미산정 · " + yield_result["reason"])
    st.caption("최종 산출 **질량/몰수**는 출발물질 실제 투입량, 단계별 당량·제한반응물, 분자량과 수율의 근거가 없으므로 계산하지 않습니다.")
    step_summaries = [service.summarize_askcos(st.session_state.get("askcos", {}).get(f"{selected}:{i}", {}), item["product"])
                      for i, item in enumerate(route["steps"])]
    summary_rows = []
    for index, (item, summary) in enumerate(zip(route["steps"], step_summaries)):
        info = summary["modules"]
        conditions = info["context"].get("conditions", [])
        summary_rows.append({"단계": index + 1, "생성물 SMILES": item["product"],
                             "사용자 입력 수율 %": f"{entered[index]:g}" if entered[index] is not None else "미입력",
                             "조건 추천": f"{len(conditions)}건 (모델 제안)" if conditions else {"not_run": "미실행", "failed": "실패"}.get(info["context"]["status"], "미확인"),
                             "정방향 목표물 순위": (str(info["forward"]["expected_product_rank"]) + " (입체구조 일치)" if info["forward"].get("expected_product_rank") is not None
                                             else str(info["forward"]["connectivity_only_rank"]) + " (골격만 일치 · 입체 미확인)" if info["forward"].get("connectivity_only_rank") is not None
                                             else "반환 후보에서 미확인" if info["forward"]["status"] == "success" else
                                                  {"not_run": "미실행", "failed": "실패"}.get(info["forward"]["status"], "미확인")),
                             "불순물 후보 수": str(info["impurity"]["candidate_count"]) if "candidate_count" in info["impurity"] else "미확인",
                             "불순물 실행 상태": {"not_run": "미실행", "failed": "실패", "success": "예측 완료"}.get(info["impurity"]["status"], "미확인")})
    st.dataframe(summary_rows, hide_index=True)
    st.caption("불순물 후보 수는 검출·잔류량이 아닙니다. 경로가 분기되면 단계 수율의 단순 곱은 전체 공정 수율로 사용하지 않습니다.")
    html = reporting.route_report_html(route, materials, step_summaries, yield_result,
                                       identity=identity, propagation=propagation,
                                       ndma_flag=ndma_flag, ames=current_admet,
                                       origin=row, occurrence_lookups=selected_lookups,
                                       user_conditions={"reagents": user_reagents, "solvents": user_solvents})
    report_stem = identifiers.report_stem(identity, route["id"])
    st.download_button("선택 경로 사람이 읽는 HTML 보고서", html, report_stem + ".html", "text/html")
    report["route_steps"] = routes
    report["stock"] = route["stock"]
    report["askcos"] = st.session_state.get("askcos", {})
    report["askcos_impurity_candidates"] = predicted_impurities
    report["admet"] = current_admet
    report["ames_screening_threshold"] = risk_flags.AMES_SCREENING_THRESHOLD
    report["target_identity"] = identity
    report["selected_route_coconut_lookups"] = selected_lookups
    report["selected_route_leaf_pubchem"] = st.session_state.get("leaf_pubchem", {}).get(leaf_key)
    report["selected_route_ndma_flag"] = ndma_flag
    report["selected_route_propagation"] = propagation
    report["selected_route_user_conditions"] = {"reagents": user_reagents, "solvents": user_solvents}
    report["selected_route"] = route["id"]
    report["selected_route_step_summaries"] = step_summaries
    report["selected_route_yield_scenario"] = yield_result
    if st.button("현재 결과 JSON 저장"):
        st.success(f"저장: {service.save_report(report)}")
    st.download_button("현재 결과 JSON 다운로드", json.dumps(report, ensure_ascii=False, indent=2),
                       report_stem + ".json", "application/json")
else:
    st.info("경로를 탐색하거나 저장된 예시를 불러오세요. 가격 DB는 검색 요청마다 SDF를 다시 읽지 않습니다.")
