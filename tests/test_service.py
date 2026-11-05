"""Offline integration checks against the actual catalog and saved AiZynthFinder run."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import service
import identifiers
import natural_origin
import risk_flags
from reporting import route_report_html, ames_source


class ServiceTests(unittest.TestCase):
    def test_missing_catalog_is_explicit_unknown_not_false_unavailable(self):
        route = {"id": "one", "target": "CCO", "stock": "ZINC", "steps": [
            {"reactants": ["CC"], "product": "CCO"}]}
        with patch.object(service, "DB", Path("missing-private-catalog.sqlite")):
            result = service.compare("CCO", [route])
        self.assertEqual(result["catalog_status"], "catalog_not_installed")
        self.assertFalse(result["routes"][0]["leaves"][0]["matches"])
        self.assertIn("미설치", result["note"])

    def test_propranolol_reactants_have_real_package_quotes(self):
        if not service.DB.is_file():
            self.skipTest("Optional local Enamine catalog and quote data not installed")
        data = json.loads((service.ROOT / "data/propranolol_enamine_routes.json").read_text(encoding="utf-8"))
        route = data["routes"][0]
        converted = {"id": route["id"], "steps": [
            {"reactants": step["reactants"], "product": step["products"][0]}
            for step in route["steps"]]}
        result = service.compare(route["target"], [converted])
        self.assertEqual(result["routes"][0]["price_coverage"], 2)
        self.assertIn("aizynth-1", result["next_check"])
        ids = {match["catalog_id"] for leaf in result["routes"][0]["leaves"] for match in leaf["matches"]}
        self.assertEqual(ids, {"EN300-177530", "EN300-19501"})
        for leaf in result["routes"][0]["leaves"]:
            self.assertTrue(any(q["currency"] == "USD" and q["price"] > 0
                                and q["observed_at"] for m in leaf["matches"] for q in m["quotes"]))
        self.assertNotIn("total_cost", result["routes"][0])

    def test_branched_route_leaves_and_semisynthesis_label(self):
        route = {"id": "branched", "steps": [
            {"reactants": ["CCO", "O"], "product": "CC=O"},
            {"reactants": ["CC=O", "N"], "product": "CC(=O)N"}]}
        self.assertEqual(service.route_leaves(route), ["CCO", "O", "N"])
        result = service.compare("CC(=O)N", [route], natural_start="CCO")
        self.assertEqual(result["routes"][0]["origin_status"], "origin_unknown")
        documented = service.compare("CC(=O)N", [route], natural_start="CCO",
                                      natural_reference="https://example.org/cited-extraction")
        self.assertEqual(documented["routes"][0]["origin_status"], "semisynthesis_candidate")
        self.assertEqual(result["extraction"]["status"], "근거 없음")

    def test_taxane_similarity_requires_origin_review_not_false_total(self):
        protected = "COc1ccc(CO[C@@H](C(=O)O[C@H]2C[C@@]3(O)[C@@H](OC(=O)c4ccccc4)[C@@H]4[C@]5(OC(C)=O)CO[C@@H]5C[C@H](O)[C@@]4(C)C(=O)[C@H](OC(C)=O)C(=C2C)C3(C)C)[C@@H](N=[N+]=[N-])c2ccccc2)cc1"
        origin = natural_origin.leaf_origin(protected)
        self.assertEqual(origin["status"], "taxane_structure_review")
        self.assertEqual(natural_origin.classify([{"origin": origin}])["status"], "origin_review_required")
        exact = natural_origin.leaf_origin(natural_origin.TAXANE_REFERENCE)
        self.assertEqual(exact["status"], "curated_natural_origin")

    def test_aspirin_salicylic_acid_occurrence_is_not_claimed_as_extracted_feedstock(self):
        aspirin = "CC(=O)Oc1ccccc1C(=O)O"
        route = {"id": "aspirin", "stock": "ZINC", "target": aspirin,
                 "steps": [{"reactants": ["CC(=O)Cl", "O=C(O)c1ccccc1O"], "product": aspirin}]}
        row = service.compare(aspirin, [route])["routes"][0]
        self.assertEqual(row["origin_status"], "natural_occurrence_review")
        self.assertIn("실제 공급 유래 미확인", row["mode"])
        self.assertEqual(next(leaf for leaf in row["leaves"] if leaf["smiles"] == "O=C(O)c1ccccc1O")["origin"]["status"],
                         "documented_natural_occurrence")
        self.assertEqual({option["classification"] for option in row["origin_options"]},
                         {"전합성 후보 (조건부)", "반합성 후보 (조건부)"})
        salicylic = next(leaf for leaf in row["leaves"] if leaf["smiles"] == "O=C(O)c1ccccc1O")
        if service.DB.is_file():
            self.assertIn("EN300-16723", [match["catalog_id"] for match in salicylic["matches"]])
            self.assertEqual(salicylic["supply_origin"]["status"], "manufacturer_origin_not_disclosed")
            self.assertTrue(any(quote["price"] > 0 and quote["observed_at"]
                                for match in salicylic["matches"] for quote in match["quotes"]))
        html = route_report_html(route, service.step_materials(route),
                                 [service.summarize_askcos({}, aspirin)], service.yield_scenario(route, [None]),
                                 origin=row, occurrence_lookups={"O=C(O)c1ccccc1O": {
                                     "status": "database_occurrence_record", "id": "CNP0230203.0",
                                     "evidence": "https://coconut.naturalproducts.net/compounds/CNP0230203.0"}})
        self.assertIn("CNP0230203.0", html)
        self.assertIn("실제 공급 유래 미확인", html)
        self.assertIn("전합성 후보 (조건부)", html)

    def test_coconut_exact_query_only_signals_database_occurrence(self):
        row = {"identifier": "CNP0230203.0", "canonical_smiles": "O=C(O)C1=CC=CC=C1O", "active": True,
               "name": "salicylic acid", "organism_count": 189, "citation_count": 20}
        response = Mock()
        response.json.return_value = {"data": {"data": [row]}}
        session = Mock()
        session.post.return_value = response
        result = natural_origin.coconut_occurrence("O=C(O)c1ccccc1O", session=session)
        self.assertEqual(result["status"], "database_occurrence_record")
        self.assertIn("CNP0230203.0", result["evidence"])
        self.assertEqual(session.post.call_args.kwargs["json"]["type"], "inchikey")
        row["active"] = False
        self.assertEqual(natural_origin.coconut_occurrence("O=C(O)c1ccccc1O", session=session)["status"], "inactive_record")

    def test_input_identifier_validation_and_safe_report_name(self):
        self.assertTrue(identifiers.cas_valid("50-78-2"))
        self.assertFalse(identifiers.cas_valid("50-78-3"))
        self.assertEqual(identifiers.normalize("OC(=O)c1ccccc1OC(C)=O"), "CC(=O)Oc1ccccc1C(=O)O")
        self.assertEqual(identifiers.report_stem({"compound": {"name": "Aspirin", "cid": 2244}}, "aizynth-4"),
                         "Aspirin_CID2244_aizynth-4")
        self.assertIn("BSYNRYMUTXBXSQ", identifiers.report_stem({"compound": {"name": "Aspirin", "smiles": "CC(=O)Oc1ccccc1C(=O)O"}}, "aizynth-4"))
        self.assertIn("CAS50-78-2", identifiers.report_stem({"input_type": "cas", "input": "50-78-2",
                          "compound": {"name": "Aspirin", "cid": 2244}}, "aizynth-4"))

    def test_ndma_flag_is_not_a_negative_safety_result(self):
        route = {"target": "CCO", "steps": [{"reactants": ["CCO"], "product": "CCO"}]}
        self.assertEqual(risk_flags.ndma_review(route)["status"], "not_established")
        flagged = risk_flags.ndma_review(route, {0: {"impurity": {"status": "success", "response": {
            "result": {"predict_expand": [{"prd_smiles": "CN(C)N=O"}]}}}}})
        self.assertEqual(flagged["status"], "model_candidate_review")
        precursor = risk_flags.ndma_review({"steps": [{"reactants": ["CNC"], "product": "CCN"}]},
                                          reagents={0: "[Na+].[O-]N=O"})
        self.assertEqual(precursor["status"], "precursor_scenario_review")
        self.assertEqual(risk_flags.ames_flag(0.6)["status"], "model_flagged")
        self.assertEqual(risk_flags.ames_flag(0.5)["label"], "0.5 이상 · 검토 필요")
        self.assertEqual(risk_flags.ames_flag(0.2)["status"], "below_model_threshold")

    def test_propagation_recommends_budget_from_connected_edges(self):
        linear = {"steps": [{"reactants": ["CCO"], "product": "CC=O"},
                            {"reactants": ["CC=O"], "product": "CC(=O)O"},
                            {"reactants": ["CC(=O)O"], "product": "CC(=O)N"}]}
        provisional = service.recommended_propagation_limits(linear)
        self.assertEqual((provisional["connected_edges"], provisional["max_calls"]), (2, 4))
        observed = service.recommended_propagation_limits(linear, {0: {"impurity": {
            "status": "success", "response": {"result": {"predict_expand": [{"prd_smiles": "CO"}]}}}}})
        self.assertEqual(observed["max_per_source"], 1)
        self.assertEqual(service.recommended_propagation_limits({"steps": [linear["steps"][0]]})["connected_edges"], 0)

    def test_propagation_follows_only_connected_intermediate_and_preserves_hypothesis(self):
        route = {"target": "CC(=O)N", "steps": [
            {"reactants": ["CCO"], "product": "CC=O"},
            {"reactants": ["CC=O", "N"], "product": "CC(=O)N"}]}
        calls = {0: {"impurity": {"status": "success", "response": {"result": {"predict_expand": [
            {"prd_smiles": "CC=O"}, {"prd_smiles": "CCCO"}]}}}}}
        fake = {"forward": {"status": "success", "response": {"result": [[{"rank": 1, "outcome": "CC(=O)N", "prob": 0.4}]]}},
                "impurity": {"status": "success", "response": {"result": {"predict_expand": [
                    {"prd_smiles": "CC(=O)N"}, {"prd_smiles": "CN(C)N=O"}]}}}}
        with patch.object(service, "askcos_step", return_value=fake) as mocked:
            propagation = service.propagate_impurities(route, calls, max_per_source=2)
        self.assertEqual(len(propagation["traces"]), 1)
        self.assertEqual(propagation["traces"][0]["hypothetical_input"], "CCCO")
        self.assertEqual(mocked.call_args.args[0]["reactants"], ["CCCO", "N"])
        self.assertEqual(risk_flags.ndma_review(route, calls, propagation)["status"], "model_candidate_review")

    def test_html_preserves_identity_origin_and_propagated_product(self):
        route = {"id": "aizynth-1", "stock": "ZINC", "target": "CC(=O)N", "steps": [
            {"reactants": ["CCO"], "product": "CC(=O)N"}]}
        origin = {"mode": "유래 미확인", "origin_note": "출발 원료 근거 미확인", "leaves": [{"smiles": "CCO",
                  "origin": {"status": "unknown", "note": "추출 출처 미확인", "evidence": None}}]}
        propagation = {"status": "completed", "traces": [{"from_step": 1, "to_step": 2,
                       "parent_intermediate": "CCO", "hypothetical_input": "CCCO", "modified_reactants": ["CCCO", "N"],
                       "status": "predicted_scenario", "products": [{"smiles": "CN(C)N=O", "mode": "prediction",
                                                               "inspector_score": 0.2}]}]}
        html = route_report_html(route, service.step_materials(route),
                                 [service.summarize_askcos({}, route["target"])],
                                 service.yield_scenario(route, [None]),
                                 identity={"compound": {"name": "Example", "cid": 123, "inchikey": "FAKE"}},
                                 origin=origin, propagation=propagation,
                                 ndma_flag=risk_flags.ndma_review(route, propagation=propagation))
        for expected in ("CID: 123", "출발물질 유래 검토", "추출 출처 미확인", "CCCO", "CN(C)N=O", "NDMA 검토 플래그"):
            self.assertIn(expected, html)

    def test_askcos_failure_retains_request_and_does_not_fake_result(self):
        step = {"reactants": ["CCO"], "product": "CC=O"}
        with patch.object(service.requests, "post", side_effect=service.requests.ConnectionError("offline")):
            result = service.askcos_step(step, modules=("forward",))
        self.assertEqual(result["forward"]["status"], "failed")
        self.assertEqual(result["forward"]["request"]["smiles"], ["CCO"])
        self.assertIsNone(result["forward"]["response"])

    def test_askcos_candidates_exclude_target_and_failed_calls(self):
        results = {"0:0": {"impurity": {"status": "success", "response": {"result": {"predict_expand": [
            {"prd_smiles": "CCO", "modes_name": "Normal reaction"},
            {"prd_smiles": "CC=O", "modes_name": "Oxidation", "avg_insp_score": 0.2}]}}}},
                   "0:1": {"impurity": {"status": "failed", "response": {"result": {"predict_expand": [{"prd_smiles": "N"}]}}}}}
        rows = service.impurity_candidates(results, "CCO")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["smiles"], "CC=O")

    def test_route_distinctness_and_linear_vs_branched_yield(self):
        linear = {"id": "one", "target": "CC(=O)N", "stock": "test", "steps": [
            {"reactants": ["CCO", "O"], "product": "CC=O"},
            {"reactants": ["CC=O", "N"], "product": "CC(=O)N"}]}
        reordered = {"id": "two", "target": linear["target"], "stock": "test", "steps": [
            {"reactants": ["N", "CC=O"], "product": "CC(=O)N"},
            {"reactants": ["O", "CCO"], "product": "CC=O"}]}
        self.assertEqual(service.distinct_routes([linear, reordered])["duplicate_groups"], [["one", "two"]])
        self.assertIsNone(service.yield_scenario(linear, [80, None])["overall_relative_yield_pct"])
        self.assertAlmostEqual(service.yield_scenario(linear, [80, 50])["overall_relative_yield_pct"], 40)
        branched = {"id": "branches", "target": "CC(=O)N", "stock": "test", "steps": [
            {"reactants": ["CCO"], "product": "CC=O"},
            {"reactants": ["N"], "product": "[NH2-]"},
            {"reactants": ["CC=O", "[NH2-]"], "product": "CC(=O)N"}]}
        self.assertFalse(service.yield_scenario(branched, [80, 90, 50])["linear_chain"])
        self.assertIsNone(service.yield_scenario(branched, [80, 90, 50])["overall_relative_yield_pct"])

    def test_human_askcos_summary_and_html_keep_relative_scores_separate(self):
        calls = {"context": {"status": "success", "response": {"result": [{"predictions": [
            {"rank": 1, "agents": ["O"], "temperature": "[20, 30)",
             "reactant_amounts": [{"reactant": "CCO", "amount_range": "[0.9, 1.1)"}],
             "agent_amounts": [], "score": 0.4}]}]}},
                 "forward": {"status": "success", "response": {"result": [[
                     {"rank": 1, "outcome": "CC=O", "prob": 0.8}]]}},
                 "impurity": {"status": "success", "response": {"result": {"predict_expand": [
                     {"prd_smiles": "CC=O"}, {"prd_smiles": "CCO", "modes_name": "<script>", "avg_insp_score": 0.2}]}}}}
        summary = service.summarize_askcos(calls, "CC=O")
        self.assertEqual(summary["modules"]["forward"]["expected_product_rank"], 1)
        self.assertEqual(summary["modules"]["impurity"]["candidate_count"], 1)
        route = {"id": "test", "target": "CC=O", "stock": "test", "steps": [{"reactants": ["CCO"], "product": "CC=O"}]}
        html = route_report_html(route, service.step_materials(route), [summary], service.yield_scenario(route, [None]))
        self.assertIn("전체", service.yield_scenario(route, [None])["reason"])
        self.assertIn("미산정", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertNotIn("<script>", html)

    def test_forward_constitution_match_does_not_claim_stereochemical_success(self):
        expected = "CC(C)[C@H](N)C(=O)O"
        forward = {"forward": {"status": "success", "response": {"result": [[
            {"rank": 1, "outcome": "CC(C)C(N)C(=O)O", "prob": 0.8}]]}}}
        result = service.summarize_askcos(forward, expected)["modules"]["forward"]
        self.assertIsNone(result["expected_product_rank"])
        self.assertEqual(result["connectivity_only_rank"], 1)
        self.assertIn("입체화학", result["interpretation_status"])

    def test_ames_source_distinguishes_byproduct_from_starting_material(self):
        route = {"steps": [{"reactants": ["CCO"], "product": "CC=O"}]}
        summary = service.summarize_askcos({"impurity": {"status": "success", "response": {
            "result": {"predict_expand": [{"prd_smiles": "CCO"}, {"prd_smiles": "CCCO"}]}}}}, "CC=O")
        self.assertIn("경로 반응물", ames_source("CCO", route, [summary]))
        self.assertIn("ASKCOS 직접 부산물", ames_source("CCCO", route, [summary]))
        self.assertNotIn("경로 반응물", ames_source("CCCO", route, [summary]))

    def test_inorganic_ion_is_not_labeled_ames_positive(self):
        result = service.admet_ames(["[Br-]"])
        self.assertEqual(result["status"], "failed")
        self.assertEqual(result["assessments"], [])
        self.assertEqual(result["skipped"][0]["smiles"], "[Br-]")


if __name__ == "__main__":
    unittest.main()
