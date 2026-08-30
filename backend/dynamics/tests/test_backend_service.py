import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


DYNAMICS_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = DYNAMICS_ROOT.parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.dynamics import (  # noqa: E402
    DynamicsBundleError,
    load_event_batch,
    run_bundle_transition,
    settle_candidate_state,
)
import backend.dynamics.service as dynamics_service  # noqa: E402


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


class BackendDynamicsServiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.bundle = Path(self.temporary.name)
        inputs = {
            "current_graph.json": DYNAMICS_ROOT
            / "canonical/PANTA_Keystone_Initial_IC_State_2026-03-10.json",
            "execution_mapping.json": DYNAMICS_ROOT
            / "benchmark/keystone_execution_mapping_v0.json",
            "keystone_materiality_policy_v0.json": DYNAMICS_ROOT
            / "benchmark/keystone_materiality_policy_v0.json",
            "keystone_authority_matrix_v0.json": DYNAMICS_ROOT
            / "benchmark/keystone_authority_matrix_v0.json",
        }
        for name, source in inputs.items():
            (self.bundle / name).write_bytes(source.read_bytes())
        suite = load_json(
            DYNAMICS_ROOT / "benchmark/transition_engine_conformance_cases_v1.json"
        )
        case = next(
            item
            for item in suite["cases"]
            if item["test_id"] == "TCE-001-KEYSTONE-FIRM-EBITDA-CORRECTION"
        )
        self.events = case["event_batch"]
        (self.bundle / "event_tce001.json").write_text(
            json.dumps(self.events[0]), encoding="utf-8"
        )

    def tearDown(self):
        self.temporary.cleanup()

    def test_run_persists_exact_candidate_and_settlement_replay_state(self):
        current_before = load_json(self.bundle / "current_graph.json")
        result = run_bundle_transition(
            self.bundle, self.events, persist_outputs=True
        )
        self.assertEqual(load_json(self.bundle / "current_graph.json"), current_before)
        self.assertEqual(
            load_json(self.bundle / "candidate_graph.json"),
            result["candidate_graph"],
        )
        self.assertEqual(
            load_json(self.bundle / "candidate_state.json"),
            result["candidate_state"],
        )

        settled = settle_candidate_state(
            self.bundle,
            result["candidate_state"],
            result["history_append"],
            current_state_id="STATE-TEST-ADOPTED",
        )
        self.assertEqual(settled["state_id"], "STATE-TEST-ADOPTED")
        self.assertEqual(settled, load_json(self.bundle / "runtime_state.json"))
        self.assertEqual(load_json(self.bundle / "current_graph.json"), result["candidate_graph"])
        self.assertEqual(load_json(self.bundle / "candidate_graph.json"), {})

        replay = run_bundle_transition(self.bundle, self.events)
        self.assertEqual(replay["history_append"], [])
        self.assertEqual(
            replay["transition_output"]["candidate_current_approved_delta"]["candidate"],
            [],
        )

    def test_event_resolution_requires_exact_compiled_event_id(self):
        event_id = self.events[0]["event_id"]
        self.assertEqual(
            load_event_batch(self.bundle, event_id), self.events
        )
        with self.assertRaises(DynamicsBundleError):
            load_event_batch(self.bundle, "EVENT-DOES-NOT-EXIST")

    def test_expected_candidate_envelope_rejects_persisted_tampering(self):
        current_before = load_json(self.bundle / "current_graph.json")
        result = run_bundle_transition(self.bundle, self.events, persist_outputs=True)
        state_hash = dynamics_service._canonical_hash(result["candidate_state"])
        graph_hash = dynamics_service._canonical_hash(result["candidate_graph"])
        tampered = load_json(self.bundle / "candidate_state.json")
        tampered["approved_snapshot"] = {"tampered": True}
        (self.bundle / "candidate_state.json").write_text(
            json.dumps(tampered), encoding="utf-8"
        )

        with self.assertRaisesRegex(DynamicsBundleError, "modified"):
            settle_candidate_state(
                self.bundle,
                result["candidate_state"],
                result["history_append"],
                current_state_id="STATE-TAMPER-REFUSED",
                expected_prior_state_id=result["transition_output"]["prior_state_id"],
                expected_prior_graph_hash=dynamics_service._canonical_hash(current_before),
                expected_candidate_state_id=result["candidate_state"]["state_id"],
                expected_candidate_state_hash=state_hash,
                expected_candidate_graph_hash=graph_hash,
            )
        self.assertEqual(load_json(self.bundle / "current_graph.json"), current_before)
        self.assertFalse((self.bundle / "settlement_journal.json").exists())

    def test_interrupted_multi_file_commit_recovers_on_same_retry(self):
        current_before = load_json(self.bundle / "current_graph.json")
        result = run_bundle_transition(self.bundle, self.events, persist_outputs=True)
        kwargs = {
            "current_state_id": "STATE-RECOVERED",
            "expected_prior_state_id": result["transition_output"]["prior_state_id"],
            "expected_prior_graph_hash": dynamics_service._canonical_hash(current_before),
            "expected_candidate_state_id": result["candidate_state"]["state_id"],
            "expected_candidate_state_hash": dynamics_service._canonical_hash(
                result["candidate_state"]
            ),
            "expected_candidate_graph_hash": dynamics_service._canonical_hash(
                result["candidate_graph"]
            ),
        }
        original_write = dynamics_service._atomic_write_json
        failed = False

        def fail_runtime_once(path, payload):
            nonlocal failed
            if Path(path).name == "runtime_state.json" and not failed:
                failed = True
                raise OSError("injected runtime-state write failure")
            return original_write(path, payload)

        with patch.object(
            dynamics_service, "_atomic_write_json", side_effect=fail_runtime_once
        ):
            with self.assertRaisesRegex(DynamicsBundleError, "interrupted"):
                settle_candidate_state(
                    self.bundle,
                    result["candidate_state"],
                    result["history_append"],
                    **kwargs,
                )

        self.assertTrue((self.bundle / "settlement_journal.json").exists())
        recovered = settle_candidate_state(
            self.bundle,
            result["candidate_state"],
            result["history_append"],
            **kwargs,
        )
        self.assertEqual(recovered["state_id"], "STATE-RECOVERED")
        self.assertEqual(
            load_json(self.bundle / "current_graph.json"), result["candidate_graph"]
        )
        self.assertFalse((self.bundle / "settlement_journal.json").exists())
        self.assertFalse((self.bundle / "candidate_state.json").exists())


if __name__ == "__main__":
    unittest.main()
