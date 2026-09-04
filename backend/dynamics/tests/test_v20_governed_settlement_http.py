import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx


DYNAMICS_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = DYNAMICS_ROOT.parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.server import app  # noqa: E402
import app.v20_router as router  # noqa: E402
from backend.dynamics.runtime import build_runtime_state  # noqa: E402


class V20GovernedSettlementHTTPTests(unittest.IsolatedAsyncioTestCase):
    """Settlement invariants exercised through the real FastAPI application.

    The fixture deliberately has one independently settleable claim and one
    claim that can be placed in a blocked component.  This makes a successful
    partial settlement observable in the persisted graph: the first claim must
    advance to Candidate while the blocked claim must retain its Current value.
    """

    case_id = "governed-settlement-test"
    candidate_state_id = "STATE-GOVERNED-CANDIDATE"
    prior_state_id = "STATE-GOVERNED-CURRENT"
    settled_change_id = "CHANGE-SETTLED"
    other_change_id = "CHANGE-OTHER"

    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.bundle = self.root / "cases" / self.case_id
        self.bundle.mkdir(parents=True)

        self.previous_router_state = {
            "VAULT": router.VAULT,
            "PIPELINE_OUT": router.PIPELINE_OUT,
            "CASE_PIPELINE_ROOT": router.CASE_PIPELINE_ROOT,
            "RUNS_LOG": router.RUNS_LOG,
            "runs": copy.deepcopy(router._runs),
        }
        router.VAULT = self.root / "vault"
        router.PIPELINE_OUT = self.root / "keystone"
        router.CASE_PIPELINE_ROOT = self.root / "cases"
        router.RUNS_LOG = self.root / "logs" / "runs.json"
        router._runs.clear()

        self.patches = [
            patch.object(router, "_rebuild_index", return_value=None),
            patch.object(
                router,
                "_build_projection",
                return_value={"deal": {"case_id": self.case_id}},
            ),
            patch.object(
                router,
                "_make_context",
                side_effect=lambda case_id, state_id, as_of_date: {
                    "mode": "CONNECTED",
                    "case_id": case_id,
                    "as_of_state_id": state_id,
                    "as_of_date": as_of_date,
                },
            ),
        ]
        for active_patch in self.patches:
            active_patch.start()

        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://panta.test",
        )

    async def asyncTearDown(self):
        await self.client.aclose()
        for active_patch in reversed(self.patches):
            active_patch.stop()

        router.VAULT = self.previous_router_state["VAULT"]
        router.PIPELINE_OUT = self.previous_router_state["PIPELINE_OUT"]
        router.CASE_PIPELINE_ROOT = self.previous_router_state["CASE_PIPELINE_ROOT"]
        router.RUNS_LOG = self.previous_router_state["RUNS_LOG"]
        router._runs.clear()
        router._runs.update(self.previous_router_state["runs"])
        self.temporary.cleanup()

    @staticmethod
    def _base_graph() -> dict:
        return {
            "case_id": V20GovernedSettlementHTTPTests.case_id,
            "claims": [
                {"claim_id": "CL-SETTLED", "value": 1, "status": "CURRENT"},
                {"claim_id": "CL-OTHER", "value": 10, "status": "CURRENT"},
            ],
            "case_positions": [],
            "model_nodes": [],
            "support_routes": [],
            "claim_position_edges": [],
            "position_dependencies": [],
            "position_model_bindings": [],
            "artifacts": [],
            "decision_snapshot": {},
        }

    @classmethod
    def _candidate_graph(cls) -> dict:
        graph = cls._base_graph()
        graph["claims"][0].update(value=2, status="CANDIDATE")
        graph["claims"][1].update(value=20, status="CANDIDATE")
        return graph

    @staticmethod
    def _write_json(path: Path, value: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(value, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def _write_current(self, graph: dict, state_id: str) -> None:
        self._write_json(self.bundle / "current_graph.json", graph)
        self._write_json(
            self.bundle / "runtime_state.json",
            build_runtime_state(graph, state_id=state_id),
        )

    def _seed_run(
        self,
        run_id: str,
        *,
        blocked: bool = False,
        multiple_change_sets: bool = False,
        status: str = "CANDIDATE_READY",
    ) -> dict:
        current_graph = self._base_graph()
        candidate_graph = self._candidate_graph()
        candidate_state = build_runtime_state(
            candidate_graph,
            state_id=self.candidate_state_id,
        )
        candidate_graph_hash = router._graph_content_hash(candidate_graph)
        candidate_state["candidate_graph_hash"] = candidate_graph_hash

        self._write_current(current_graph, self.prior_state_id)
        self._write_json(self.bundle / "candidate_graph.json", candidate_graph)
        self._write_json(self.bundle / "candidate_state.json", candidate_state)

        blocked_components = []
        if blocked:
            blocked_components = [
                {
                    "component_id": "COMP-BLOCKED",
                    "member_ids": ["CL-OTHER"],
                    "dependent_ids": [],
                    "reason_code": "NO_ADMISSIBLE_SOLUTION",
                    "missing_assumption_or_condition": "Resolve CL-OTHER",
                }
            ]

        human_stops = []
        if blocked:
            human_stops = [
                {
                    "stop_id": "STOP-BLOCKED-SCOPE",
                    "object_or_component_id": "CL-OTHER",
                    "reason_code": "NO_ADMISSIBLE_SOLUTION",
                    "requested_action": "Correct the blocked scope and replay.",
                    "required_role": "PREPARER",
                    "downstream_scope": ["CL-OTHER"],
                }
            ]

        transition_output = {
            "prior_state_id": self.prior_state_id,
            "policy_refs": {
                "canonical_graph_hash": router._graph_content_hash(current_graph)
            },
            "replay_hash": "sha256:governed-settlement-replay",
            "human_stops": human_stops,
            "blocked_components": blocked_components,
            "ordered_transitions": [
                {
                    "component_id": "COMP-SETTLED",
                    "member_ids": ["CL-SETTLED"],
                    "result": "SETTLED",
                },
                {
                    "component_id": "COMP-OTHER",
                    "member_ids": ["CL-OTHER"],
                    "result": "BLOCKED" if blocked else "SETTLED",
                },
            ],
            "candidate_current_approved_delta": {
                "candidate": [
                    {
                        "object_type": "CLAIM",
                        "object_id": "CL-SETTLED",
                        "field": "value",
                        "from": 1,
                        "to": 2,
                        "status": "APPLIED",
                    },
                    {
                        "object_type": "CLAIM",
                        "object_id": "CL-OTHER",
                        "field": "value",
                        "from": 10,
                        "to": 20,
                        "status": "BLOCKED" if blocked else "APPLIED",
                    },
                ],
                "current": [],
                "approved": [],
            },
            "partial_settlement_status": {
                "candidate": "PARTIAL" if blocked else "FULL",
                "current": "PARTIAL" if blocked else "UNCHANGED",
                "approved": "UNCHANGED",
            },
        }
        change_sets = [
            {
                "artifact_id": self.settled_change_id,
                "change_set_id": self.settled_change_id,
                "object_ids": (
                    ["CL-SETTLED"]
                    if blocked or multiple_change_sets
                    else ["CL-SETTLED", "CL-OTHER"]
                ),
                "status": "PARTIAL_READY" if blocked else "READY",
            }
        ]
        if multiple_change_sets and not blocked:
            change_sets.append(
                {
                    "artifact_id": self.other_change_id,
                    "change_set_id": self.other_change_id,
                    "object_ids": ["CL-OTHER"],
                    "status": "READY",
                }
            )

        run = {
            "run_id": run_id,
            "case_id": self.case_id,
            "event_id": f"EVENT-{run_id}",
            "candidate_graph": candidate_graph,
            "candidate_state": candidate_state,
            "history_append": [],
            "transition_output": transition_output,
            "candidate_state_id": self.candidate_state_id,
            "prior_state_id": self.prior_state_id,
            "prior_graph_hash": router._graph_content_hash(current_graph),
            "candidate_graph_hash": candidate_graph_hash,
            "artifact_change_sets": change_sets,
            "bundle_dir": str(self.bundle),
            "authority_records": [],
            "status": status,
            "created_at": "2026-08-30T10:00:00Z",
        }
        router._store_run(run_id, run)
        return run

    async def _prepare(self, run_id: str, selected: list[str] | None = None):
        return await self.client.post(
            f"/api/v20/runs/{run_id}/prepare",
            json={
                "selected_change_ids": selected or [self.settled_change_id],
                "actor_id": "preparer-001",
            },
        )

    def _settlement_payload(
        self,
        run_id: str,
        *,
        candidate_state_id: str | None = None,
        selected_change_ids: list[str] | None = None,
        allow_partial: bool = False,
    ) -> dict:
        return {
            "run_id": run_id,
            "candidate_state_id": candidate_state_id or self.candidate_state_id,
            "prior_state_id": self.prior_state_id,
            "as_of_state_id": self.prior_state_id,
            "selected_change_ids": selected_change_ids or [self.settled_change_id],
            "human_stop_ids": [],
            "authority_record_ids": [],
            "execution_package_ids": [],
            "actor_id": "reviewer-001",
            "allow_partial_settlement": allow_partial,
            "idempotency_key": f"SETTLE-{run_id}",
        }

    @staticmethod
    def _error_text(response: httpx.Response) -> str:
        body = response.json()
        error = body.get("error", body.get("detail", body))
        if isinstance(error, dict):
            return str(error.get("message") or error.get("detail") or error)
        return str(error)

    def _assert_conflict(self, response: httpx.Response, *expected_words: str) -> None:
        self.assertEqual(response.status_code, 409, response.text)
        if expected_words:
            text = self._error_text(response).lower()
            self.assertTrue(
                any(word.lower() in text for word in expected_words),
                f"expected one of {expected_words!r} in {text!r}",
            )

    def _current_graph(self) -> dict:
        return json.loads((self.bundle / "current_graph.json").read_text(encoding="utf-8"))

    @staticmethod
    def _claim_values(graph: dict) -> dict[str, int]:
        return {item["claim_id"]: item["value"] for item in graph["claims"]}

    def _settlement_files(self) -> list[Path]:
        return list(
            (router.VAULT / "deals" / self.case_id / "events").glob(
                f"e-{self.case_id}-settle-*.md"
            )
        )

    async def test_prepare_rejects_empty_unknown_and_duplicate_change_ids(self):
        cases = (
            ("RUN-PREPARE-EMPTY", [], ("select", "empty", "one change")),
            ("RUN-PREPARE-UNKNOWN", ["CHANGE-UNKNOWN"], ("unknown", "outside")),
            (
                "RUN-PREPARE-DUPLICATE",
                [self.settled_change_id, self.settled_change_id],
                ("duplicate",),
            ),
        )
        for run_id, selected, words in cases:
            with self.subTest(run_id=run_id):
                self._seed_run(run_id)
                response = await self.client.post(
                    f"/api/v20/runs/{run_id}/prepare",
                    json={"selected_change_ids": selected},
                )
                self._assert_conflict(response, *words)
                self.assertEqual(router._runs[run_id]["status"], "CANDIDATE_READY")
                event_dir = router.VAULT / "deals" / self.case_id / "events"
                self.assertEqual(list(event_dir.glob("*run-prepared*.md")), [])

        valid_run_id = "RUN-PREPARE-VALID"
        self._seed_run(valid_run_id)
        accepted = await self._prepare(valid_run_id)
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(router._runs[valid_run_id]["status"], "PREPARED")
        self.assertEqual(
            router._runs[valid_run_id]["selected_change_ids"],
            [self.settled_change_id],
        )

    async def test_prepare_audit_failure_does_not_advance_run_and_retry_repairs_it(self):
        run_id = "RUN-PREPARE-AUDIT-FAILURE"
        self._seed_run(run_id)

        with patch.object(
            router,
            "_write_text_atomic",
            side_effect=OSError("synthetic audit storage failure"),
        ):
            failed = await self._prepare(run_id)

        self.assertEqual(failed.status_code, 503, failed.text)
        self.assertEqual(router._runs[run_id]["status"], "CANDIDATE_READY")

        accepted = await self._prepare(run_id)
        self.assertEqual(accepted.status_code, 200, accepted.text)
        prepared_run = router._runs[run_id]
        event_path = (
            router.VAULT
            / "deals"
            / self.case_id
            / "events"
            / f"{prepared_run['prepared_event_id']}.md"
        )
        self.assertTrue(event_path.exists())

        # An idempotent retry also repairs an event missing from an older run.
        event_path.unlink()
        replay = await self._prepare(run_id)
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertTrue(event_path.exists())

    async def test_settlement_requires_prepared_run_without_mutating_current(self):
        run_id = "RUN-NOT-PREPARED"
        self._seed_run(run_id)
        current_before = self._current_graph()

        response = await self.client.post(
            f"/api/v20/runs/{run_id}/settle",
            json=self._settlement_payload(run_id),
        )

        self._assert_conflict(response, "prepared")
        self.assertEqual(self._current_graph(), current_before)
        self.assertEqual(router._runs[run_id]["status"], "CANDIDATE_READY")
        self.assertEqual(self._settlement_files(), [])

    async def test_settlement_requires_nonempty_idempotency_key_before_commit(self):
        run_id = "RUN-IDEMPOTENCY-REQUIRED"
        self._seed_run(run_id)
        prepared = await self._prepare(run_id)
        self.assertEqual(prepared.status_code, 200, prepared.text)
        current_before = self._current_graph()

        for supplied_key in (None, "   "):
            with self.subTest(idempotency_key=supplied_key):
                payload = self._settlement_payload(run_id)
                if supplied_key is None:
                    payload.pop("idempotency_key")
                else:
                    payload["idempotency_key"] = supplied_key
                response = await self.client.post(
                    f"/api/v20/runs/{run_id}/settle",
                    json=payload,
                )
                self._assert_conflict(response, "idempotency")

        self.assertEqual(router._runs[run_id]["status"], "PREPARED")
        self.assertEqual(self._current_graph(), current_before)
        self.assertFalse((self.bundle / "settlement_journal.json").exists())

    async def test_settlement_reference_arrays_require_unique_nonempty_strings(self):
        run_id = "RUN-STRICT-REFERENCE-ARRAYS"
        self._seed_run(run_id)
        prepared = await self._prepare(run_id)
        self.assertEqual(prepared.status_code, 200, prepared.text)
        current_before = self._current_graph()

        for field in (
            "authority_record_ids",
            "human_stop_ids",
            "execution_package_ids",
        ):
            with self.subTest(field=field):
                payload = self._settlement_payload(run_id)
                payload[field] = [None]
                response = await self.client.post(
                    f"/api/v20/runs/{run_id}/settle", json=payload
                )
                self.assertEqual(response.status_code, 400, response.text)

            with self.subTest(field=field, case="duplicate"):
                payload = self._settlement_payload(run_id)
                payload[field] = ["DUPLICATE-ID", "DUPLICATE-ID"]
                response = await self.client.post(
                    f"/api/v20/runs/{run_id}/settle", json=payload
                )
                self.assertEqual(response.status_code, 409, response.text)

        self.assertEqual(router._runs[run_id]["status"], "PREPARED")
        self.assertEqual(self._current_graph(), current_before)
        self.assertEqual(self._settlement_files(), [])

    async def test_settlement_rejects_candidate_and_prepared_scope_mismatch(self):
        candidate_run_id = "RUN-CANDIDATE-MISMATCH"
        self._seed_run(candidate_run_id)
        prepared = await self._prepare(candidate_run_id)
        self.assertEqual(prepared.status_code, 200, prepared.text)
        current_before = self._current_graph()

        wrong_candidate = await self.client.post(
            f"/api/v20/runs/{candidate_run_id}/settle",
            json=self._settlement_payload(
                candidate_run_id,
                candidate_state_id="STATE-OTHER-CANDIDATE",
            ),
        )
        self._assert_conflict(wrong_candidate, "candidate")
        self.assertEqual(self._current_graph(), current_before)

        scope_run_id = "RUN-SCOPE-MISMATCH"
        self._seed_run(scope_run_id, multiple_change_sets=True)
        prepared = await self._prepare(scope_run_id)
        self.assertEqual(prepared.status_code, 200, prepared.text)
        wrong_scope = await self.client.post(
            f"/api/v20/runs/{scope_run_id}/settle",
            json=self._settlement_payload(
                scope_run_id,
                selected_change_ids=[self.other_change_id],
            ),
        )
        self._assert_conflict(wrong_scope, "prepared", "selection", "scope")
        self.assertEqual(self._current_graph(), current_before)
        self.assertEqual(self._settlement_files(), [])

    async def test_blocked_candidate_requires_explicit_partial_settlement(self):
        run_id = "RUN-PARTIAL-OPT-IN"
        self._seed_run(run_id, blocked=True)
        prepared = await self._prepare(run_id)
        self.assertEqual(prepared.status_code, 200, prepared.text)
        current_before = self._current_graph()

        response = await self.client.post(
            f"/api/v20/runs/{run_id}/settle",
            json=self._settlement_payload(run_id, allow_partial=False),
        )

        self._assert_conflict(response, "partial", "blocked")
        self.assertEqual(self._current_graph(), current_before)
        self.assertTrue((self.bundle / "candidate_state.json").exists())
        self.assertEqual(router._runs[run_id]["status"], "PREPARED")
        self.assertEqual(self._settlement_files(), [])

    async def test_bounded_partial_settlement_promotes_only_unblocked_scope(self):
        run_id = "RUN-BOUNDED-PARTIAL"
        self._seed_run(run_id, blocked=True)
        prepared = await self._prepare(run_id)
        self.assertEqual(prepared.status_code, 200, prepared.text)

        response = await self.client.post(
            f"/api/v20/runs/{run_id}/settle",
            json=self._settlement_payload(run_id, allow_partial=True),
        )

        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertTrue(result["partial"])
        self.assertEqual(result["selected_change_ids"], [self.settled_change_id])
        self.assertEqual(result["blocked_components"][0]["component_id"], "COMP-BLOCKED")

        values = self._claim_values(self._current_graph())
        self.assertEqual(values["CL-SETTLED"], 2)
        self.assertEqual(values["CL-OTHER"], 10)

        runtime_state = json.loads(
            (self.bundle / "runtime_state.json").read_text(encoding="utf-8")
        )
        self.assertIn("pending_settlement", runtime_state)
        self.assertIn("COMP-BLOCKED", json.dumps(runtime_state["pending_settlement"]))
        self.assertEqual(
            runtime_state["pending_settlement"]["unresolved_human_stop_ids"],
            ["STOP-BLOCKED-SCOPE"],
        )
        self.assertFalse((self.bundle / "candidate_state.json").exists())
        self.assertEqual(json.loads((self.bundle / "candidate_graph.json").read_text()), {})
        self.assertEqual(router._runs[run_id]["status"], "SETTLED")
        self.assertEqual(len(self._settlement_files()), 1)

    async def test_settlement_compare_and_swap_rejects_stale_state_or_graph(self):
        cases = (
            ("RUN-CAS-STATE", "STATE-NEWER", 101),
            ("RUN-CAS-GRAPH", self.prior_state_id, 102),
        )
        for run_id, concurrent_state_id, concurrent_value in cases:
            with self.subTest(run_id=run_id):
                self._seed_run(run_id)
                prepared = await self._prepare(run_id)
                self.assertEqual(prepared.status_code, 200, prepared.text)

                concurrent_graph = self._base_graph()
                concurrent_graph["claims"][0]["value"] = concurrent_value
                self._write_current(concurrent_graph, concurrent_state_id)

                response = await self.client.post(
                    f"/api/v20/runs/{run_id}/settle",
                    json=self._settlement_payload(run_id),
                )

                self._assert_conflict(response, "stale", "current", "base")
                self.assertEqual(self._current_graph(), concurrent_graph)
                self.assertEqual(router._runs[run_id]["status"], "PREPARED")
                self.assertTrue((self.bundle / "candidate_state.json").exists())
                self.assertEqual(self._settlement_files(), [])

    async def test_settlement_idempotency_replays_only_the_same_request(self):
        run_id = "RUN-IDEMPOTENT"
        self._seed_run(run_id)
        prepared = await self._prepare(run_id)
        self.assertEqual(prepared.status_code, 200, prepared.text)
        payload = self._settlement_payload(run_id)

        first = await self.client.post(
            f"/api/v20/runs/{run_id}/settle", json=payload
        )
        self.assertEqual(first.status_code, 200, first.text)
        replay = await self.client.post(
            f"/api/v20/runs/{run_id}/settle", json=payload
        )
        self.assertEqual(replay.status_code, 200, replay.text)
        self.assertEqual(
            replay.json()["current_state_id"], first.json()["current_state_id"]
        )
        self.assertEqual(len(self._settlement_files()), 1)

        different = {**payload, "idempotency_key": "SETTLE-DIFFERENT"}
        conflict = await self.client.post(
            f"/api/v20/runs/{run_id}/settle", json=different
        )
        self._assert_conflict(conflict, "already settled")


if __name__ == "__main__":
    unittest.main()
