"""Human-readable structures, conditions and predicted products for the standalone UI."""
from rdkit import Chem
from rdkit.Chem import Draw
import streamlit as st

import service


def molecule_card(smiles: str, role: str) -> None:
    st.write(f"**{role}**")
    mol = Chem.MolFromSmiles(smiles)
    if mol is not None:
        st.image(Draw.MolToImage(mol, size=(340, 200)), width="content")
    else:
        st.warning("구조를 그릴 수 없습니다")
    st.code(smiles, language=None)


def show_step_structures(step: dict, number: int) -> None:
    st.markdown(f"#### {number}단계 · 반응물 → 생성물")
    reactants = step["reactants"]
    st.caption("외부 출발물질은 별도 공급 근거가 필요하고, 중간체는 이전 단계 생성물과 SMILES가 일치할 때만 표시됩니다.")
    columns = st.columns(min(len(reactants) + 1, 3))
    for index, reactant in enumerate(reactants):
        with columns[index % len(columns)]:
            molecule_card(reactant["smiles"], f"반응물 {index + 1} · {reactant['role']}")
    with columns[len(reactants) % len(columns)]:
        molecule_card(step["product"]["smiles"], f"생성물 · {step['product']['role']}")


def show_askcos_results(calls: dict, expected: str) -> dict:
    summary = service.summarize_askcos(calls, expected)
    labels = {"context": "QUARC 실험 조건 후보", "forward": "WLDN5 정방향 생성물 예측",
              "impurity": "불순물 예측 후보"}
    for name, label in labels.items():
        block = summary["modules"][name]
        if block["status"] == "not_run":
            st.caption(f"{label}: 미실행")
            continue
        if block["status"] != "success":
            st.warning(f"{label}: 실패 · {block.get('error') or '응답 형식 확인 필요'}")
            continue
        st.write(f"**{label}**")
        st.info("해석 상태: " + block.get("interpretation_status", "모델 결과 · 독립 검증 필요"))
        if name == "context":
            conditions = block.get("conditions", [])
            if not conditions:
                st.info("조건 후보 없음")
            for condition in conditions:
                with st.expander(f"조건 {condition['rank']}위 · 온도 {condition['temperature_range'] or '미제공'} · 모델 점수 {condition['model_score']}"):
                    st.write("모델 제안 시약/용매 SMILES:", ", ".join(condition["agents"]) or "미제공")
                    st.write("반응물의 모델 제안 상대량 범위")
                    st.dataframe(condition["reactant_relative_ranges"], hide_index=True)
                    if condition["agent_relative_ranges"]:
                        st.write("시약/용매의 모델 제안 상대량 범위")
                        st.dataframe(condition["agent_relative_ranges"], hide_index=True)
            st.caption("상대량 범위의 단위·스케일과 실제 투입량은 확인되지 않았습니다. 온도·시약도 제안일 뿐 실험 조건으로 확정되지 않았습니다.")
        elif name == "forward":
            rank = block.get("expected_product_rank")
            st.write(f"입력한 목표 생성물 순위: {rank if rank is not None else '반환된 후보에서 미확인'}")
            st.dataframe([{"순위": p["rank"], "예측 생성물 SMILES": p["smiles"],
                           "모델 상대 확률": p["model_probability"]} for p in block.get("top_products", [])], hide_index=True)
            st.caption("모델 상대 확률은 실험 수율이나 생성량이 아닙니다. 반응물 투입량·조건을 지정하지 않은 모델 입력입니다.")
        else:
            st.write(f"목표 생성물을 제외한 예측 후보: {block.get('candidate_count', 0)}개")
            st.dataframe([{"후보 SMILES": p["smiles"], "모드": p["mode"],
                           "Inspector 모델 점수": p["inspector_score"]} for p in block.get("candidates", [])],
                         hide_index=True)
            st.caption("후보는 실제 검출·잔류·농도 측정이 아닙니다. Inspector 점수는 AMES/생성량/수율이 아닙니다.")
    return summary
