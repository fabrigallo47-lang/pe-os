import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import BackgroundTasks


PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

import app.v20_router as router  # noqa: E402
from tools import bridge_v7  # noqa: E402
from tools import deal_profile  # noqa: E402


class V20ScoutBackendSmokeTests(unittest.TestCase):
    """Credential-free proof of the connected backend contract for a second deal."""

    case_id = "scout"
    job_id = "job-scout-synthetic-001"
    claim_id = "scout-claim-dso-001"

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.previous_pipeline_out = router.PIPELINE_OUT
        self.previous_case_pipeline_root = router.CASE_PIPELINE_ROOT
        self.previous_vault = router.VAULT
        self.previous_index_db = router.INDEX_DB
        self.previous_jobs_log = router.INGEST_JOBS_LOG
        self.previous_runs_log = router.RUNS_LOG
        self.previous_jobs = dict(router._jobs)
        self.previous_runs = dict(router._runs)
        self.previous_profile_vault = deal_profile.VAULT
        self.previous_active_profile = bridge_v7._ACTIVE_PROFILE

        router.PIPELINE_OUT = self.root / "keystone-bundle"
        router.CASE_PIPELINE_ROOT = self.root / "case-bundles"
        router.VAULT = self.root / "vault"
        router.INDEX_DB = self.root / "missing-index.db"
        router.INGEST_JOBS_LOG = self.root / "logs" / "ingest_jobs.json"
        router.RUNS_LOG = self.root / "logs" / "runs.json"
        router._jobs.clear()
        router._runs.clear()
        deal_profile.VAULT = router.VAULT
        self.index_patch = patch.object(router, "_rebuild_index", return_value=None)
        self.index_patch.start()

        deal_dir = router.VAULT / "deals" / self.case_id
        deal_dir.mkdir(parents=True)
        (deal_dir / "deal.md").write_text(
            "---\nid: scout\nentity: Scout Systems\n---\n",
            encoding="utf-8",
        )
        (deal_dir / "deal_profile.json").write_text(
            json.dumps(self._deal_profile(), indent=2) + "\n",
            encoding="utf-8",
        )

        bundle = router._pipeline_out_for_case(self.case_id)
        bundle.mkdir(parents=True)
        (bundle / "execution_graph_v7.json").write_text(
            json.dumps(self._execution_graph(), indent=2) + "\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.index_patch.stop()
        deal_profile.VAULT = self.previous_profile_vault
        bridge_v7._set_active_profile(self.previous_active_profile)
        router.PIPELINE_OUT = self.previous_pipeline_out
        router.CASE_PIPELINE_ROOT = self.previous_case_pipeline_root
        router.VAULT = self.previous_vault
        router.INDEX_DB = self.previous_index_db
        router.INGEST_JOBS_LOG = self.previous_jobs_log
        router.RUNS_LOG = self.previous_runs_log
        router._jobs.clear()
        router._jobs.update(self.previous_jobs)
        router._runs.clear()
        router._runs.update(self.previous_runs)
        self.temporary.cleanup()

    @staticmethod
    def _deal_profile() -> dict:
        return {
            "entity": "Scout Systems",
            "case_id": "scout",
            "state_id": "STATE-SCOUT-BASELINE",
            "claim_id_prefix": "scout",
            "default_perimeter": "Scout standalone",
            "entity_aliases": ["Scout"],
            "perimeter_vocabulary": ["Scout standalone"],
            "underwriting_cutoff": "2026-03-10",
            "cp_institutional": {
                "CP-DSO": {"perimeter": "Scout standalone", "unit": "days"}
            },
            "mn_unit_canonical": {
                "MN-BASE-DSO": "days",
                "MN-SCOUT-LIQUIDITY": "$mm",
            },
        }

    @staticmethod
    def _execution_graph() -> dict:
        return {
            "format_version": "v7",
            "schema_version": "1.0",
            "deal": {
                "name": "Synthetic Scout",
                "company": "Scout Systems",
                "slug": "scout",
            },
            "compiler": {
                "source": "synthetic-test",
                "source_hash": "synthetic-scout-v1",
                "compiled_at": "2026-03-10T00:00:00Z",
            },
            "model_nodes": {
                "MN-BASE-DSO": {
                    "id": "MN-BASE-DSO",
                    "label": "Synthetic DSO input",
                    "computational_form": "INPUT",
                    "unit": "days",
                    "period": "2025-12-31",
                    "effective_date": "2025-12-31",
                    "perimeter": "Scout standalone",
                    "epistemic_class": "observed",
                    "value_current": 52.0,
                    "workbook_ref": "synthetic://scout/model/dso",
                    "known_at": "2026-03-10T00:00:00Z",
                    "directed_deps": [],
                    "formula_id": None,
                    "coverage_limits": [],
                },
                "MN-SCOUT-LIQUIDITY": {
                    "id": "MN-SCOUT-LIQUIDITY",
                    "label": "Synthetic liquidity proxy",
                    "computational_form": "DERIVED",
                    "unit": "$mm",
                    "period": "2025-12-31",
                    "effective_date": "2025-12-31",
                    "perimeter": "Scout standalone",
                    "epistemic_class": "derived",
                    "value_current": 48.0,
                    "workbook_ref": "synthetic://scout/model/liquidity",
                    "known_at": "2026-03-10T00:00:00Z",
                    "directed_deps": ["MN-BASE-DSO"],
                    "formula_id": "F-SCOUT-LIQUIDITY",
                    "coverage_limits": [],
                },
            },
            "directed_model_edges": [
                {
                    "edge_id": "E-SCOUT-DSO-LIQUIDITY",
                    "from_model_node_id": "MN-BASE-DSO",
                    "to_model_node_id": "MN-SCOUT-LIQUIDITY",
                    "formula_or_function_ref": "F-SCOUT-LIQUIDITY",
                    "control_ids": [],
                    "scenario": "synthetic_base",
                }
            ],
            "formulas": [
                {
                    "formula_id": "F-SCOUT-LIQUIDITY",
                    "description": "Synthetic liquidity proxy equals 100 less DSO.",
                    "input_ids": ["MN-BASE-DSO"],
                    "output_id": "MN-SCOUT-LIQUIDITY",
                    "expression_or_function_ref": "100 - dso",
                    "operand_bindings": {"dso": "MN-BASE-DSO"},
                    "evaluation_type": "ARITHMETIC",
                    "unit": "$mm",
                    "period": "2025-12-31",
                    "perimeter": "Scout standalone",
                    "scenario": "synthetic_base",
                    "source_ref": "synthetic://scout/formulas/liquidity",
                    "variable_binding": {"dso": "MN-BASE-DSO"},
                    "tolerances": {"abs": 0.001},
                    "control_ids": [],
                }
            ],
            "rule_switches": [
                {
                    "rule_switch_id": "RS-SCOUT-DSO",
                    "description": "Synthetic DSO watch band.",
                    "selector_input_ids": ["MN-BASE-DSO"],
                    "branches": [
                        {
                            "branch_id": "RS-SCOUT-DSO-NORMAL",
                            "condition": "dso <= 60",
                            "output_expression": "watch = 0",
                        },
                        {
                            "branch_id": "RS-SCOUT-DSO-WATCH",
                            "condition": "dso > 60",
                            "output_expression": "watch = 1",
                        },
                    ],
                    "dependent_ids": ["MN-SCOUT-LIQUIDITY"],
                    "source_ref": "synthetic://scout/rules/dso-watch",
                    "no_branch_behavior": "RAISE_UNDEFINED",
                    "multi_branch_behavior": "RAISE_AMBIGUOUS",
                }
            ],
            "model_controls": [
                {
                    "control_id": "CTRL-SCOUT-LIQUIDITY",
                    "description": "Synthetic liquidity output must remain numeric.",
                    "pass_condition_type": "range_check",
                    "expression": "liquidity >= 0",
                    "input_ids": ["MN-SCOUT-LIQUIDITY"],
                    "scope_ids": ["MN-SCOUT-LIQUIDITY"],
                    "unit": "$mm",
                    "period": "2025-12-31",
                    "perimeter": "Scout standalone",
                    "source_ref": "synthetic://scout/controls/liquidity",
                    "pass_condition": "liquidity is non-negative",
                    "fail_outcome": "FAIL",
                    "pass_outcome": "PASS",
                    "unknown_condition": "input unresolved",
                    "blocks_on_fail": ["MN-SCOUT-LIQUIDITY"],
                    "resolution": "REQUIRES_MANUAL_REVIEW",
                }
            ],
            "cyclic_component_solver_configs": [],
            "inverse_solver_configs": [],
            "admission_manifest": {
                "manifest_id": "SCOUT-SYNTHETIC-V1",
                "coverage_limits": [],
            },
        }

    @classmethod
    def _claim(cls) -> dict:
        return {
            "claim_id": cls.claim_id,
            "statement": "Synthetic Scout DSO was 52 days at FY2025.",
            "source_id": "scout-synthetic-ledger",
            "source_ids": ["scout-synthetic-ledger"],
            "locator": "synthetic://scout/ledger#dso",
            "epistemic_class": "observed",
            "metric": "dso",
            "value": "52",
            "unit": "days",
            "period": "2025-12-31",
            "perimeter": "Scout standalone",
            "ground_truth_flag": False,
            "validation_only": False,
            "bears_on": [],
        }

    def test_scout_proposal_to_replay_and_reunderwrite_contract(self):
        bundle = router._pipeline_out_for_case(self.case_id)
        proposal_path = router._write_evidence_proposal(
            self.job_id,
            self.case_id,
            "scout-synthetic-source.json",
            [self._claim()],
        )

        proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
        self.assertEqual(proposal["case_id"], self.case_id)
        self.assertEqual(proposal["status"], "PENDING_REVIEW")
        self.assertFalse((bundle / "current_graph.json").exists())

        admitted = asyncio.run(
            router.admit_evidence(
                self.case_id,
                self.job_id,
                {"decision": "ADMIT", "actor_id": "scout-reviewer"},
            )
        )
        event_id = admitted["event_id"]
        self.assertEqual(admitted["status"], "ADMITTED")
        self.assertEqual(admitted["runtime_event"]["mapped_claim_count"], 1)
        self.assertEqual(admitted["runtime_event"]["unmapped_claim_count"], 0)
        baseline = json.loads((bundle / "current_graph.json").read_text())
        self.assertNotIn(
            self.claim_id,
            {item["claim_id"] for item in baseline["claims"]},
        )

        candidate = asyncio.run(
            router.admit(self.case_id, event_id, BackgroundTasks(), {})
        )
        run_id = candidate["run"]["run_id"]
        candidate_graph = candidate["candidate_graph"]
        affected_ids = {
            item["object_id"] for item in candidate["transition"]["affected_set"]
        }
        self.assertIn(self.claim_id, affected_ids)
        self.assertIn("CP-DSO", affected_ids)
        self.assertIn("MN-BASE-DSO", affected_ids)
        self.assertIn("MN-SCOUT-LIQUIDITY", affected_ids)
        self.assertIn(
            self.claim_id,
            {item["claim_id"] for item in candidate_graph["claims"]},
        )
        self.assertNotEqual(candidate_graph, baseline)
        self.assertEqual(
            [item["kind"] for item in router.list_graph_versions(self.case_id)["versions"]],
            ["CURRENT", "CANDIDATE"],
        )

        settled = asyncio.run(
            router.settle_run(
                run_id,
                BackgroundTasks(),
                {
                    "actor_id": "scout-reviewer",
                    "selected_change_ids": [self.claim_id],
                },
            )
        )
        self.assertEqual(settled["runtime_state_id"], settled["current_state_id"])
        self.assertFalse((bundle / "candidate_state.json").exists())
        self.assertEqual(json.loads((bundle / "candidate_graph.json").read_text()), {})

        versions = router.list_graph_versions(self.case_id)["versions"]
        self.assertEqual([item["kind"] for item in versions], ["CURRENT", "CANDIDATE", "CURRENT"])
        self.assertEqual(len({item["version_id"] for item in versions}), 3)
        first_current = router.get_graph_version(
            self.case_id, versions[0]["version_id"]
        )["graph"]
        latest_current = router.get_graph_version(
            self.case_id, versions[-1]["version_id"]
        )["graph"]
        self.assertNotIn(self.claim_id, {item["claim_id"] for item in first_current["claims"]})
        self.assertIn(self.claim_id, {item["claim_id"] for item in latest_current["claims"]})

        projection = router.projection(self.case_id)
        deal = projection["projection"]["deal"]
        self.assertEqual(projection["context"]["case_id"], self.case_id)
        self.assertEqual(deal["current_graph"]["state"], "CURRENT")
        self.assertEqual(deal["candidate_graph"], {})
        self.assertEqual(deal["graph_versions"], versions)
        self.assertEqual(
            deal["load_bearing_assumptions"][0]["position_id"], "CP-DSO"
        )
        self.assertEqual(deal["load_bearing_assumptions"][0]["rank"], 1)
        self.assertTrue(deal["next_best_work"]["label"])

        replayed = router.replay(self.case_id, as_of_date=router._today())
        replay_deal = replayed["projection"]["projection"]["deal"]
        self.assertTrue(replayed["read_only"])
        self.assertEqual(replayed["result_state_id"], settled["current_state_id"])
        self.assertEqual(replay_deal["candidate_graph"], {})
        self.assertIn(
            self.claim_id,
            {item["claim_id"] for item in replay_deal["claims"]},
        )

        reunderwrite = router.reunderwrite(self.case_id)
        self.assertTrue(reunderwrite["read_only"])
        self.assertEqual(
            reunderwrite["comparison"]["baseline_state_id"],
            versions[0]["state_id"],
        )
        self.assertEqual(
            reunderwrite["comparison"]["current_state_id"],
            versions[-1]["state_id"],
        )
        self.assertEqual(
            reunderwrite["comparison"]["collections"]["claims"]["added_ids"],
            [self.claim_id],
        )

        # No artifact from this second deal may fall back into Keystone's bundle.
        self.assertFalse(router.PIPELINE_OUT.exists())


if __name__ == "__main__":
    unittest.main()
