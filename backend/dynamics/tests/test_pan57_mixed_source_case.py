"""PAN-57 — a second archetype survives mixed-source intake and settlement."""

from __future__ import annotations

import asyncio
import base64
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import BackgroundTasks
from openpyxl import Workbook
from starlette.requests import Request


PROJECT_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_PATH = Path(__file__).parent / "fixtures" / "pan57_growth_case.json"
sys.path.insert(0, str(PROJECT_ROOT))

import app.v20_router as router  # noqa: E402
from tools import bridge_v7, deal_profile  # noqa: E402


class PAN57MixedSourceCaseTests(unittest.TestCase):
    """Credential-free regression for one sanitized growth-equity case."""

    def setUp(self):
        self.fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        self.case_id = self.fixture["case_id"]
        self.sources_by_name = {
            source["file_name"]: source for source in self.fixture["sources"]
        }
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.previous_router_state = {
            "PIPELINE_OUT": router.PIPELINE_OUT,
            "CASE_PIPELINE_ROOT": router.CASE_PIPELINE_ROOT,
            "VAULT": router.VAULT,
            "INDEX_DB": router.INDEX_DB,
            "INGEST_JOBS_LOG": router.INGEST_JOBS_LOG,
            "INGEST_BATCHES_LOG": router.INGEST_BATCHES_LOG,
            "RUNS_LOG": router.RUNS_LOG,
            "jobs": dict(router._jobs),
            "batches": dict(router._batches),
            "runs": dict(router._runs),
        }
        self.previous_profile_vault = deal_profile.VAULT
        self.previous_active_profile = bridge_v7._ACTIVE_PROFILE

        router.PIPELINE_OUT = self.root / "keystone-bundle"
        router.CASE_PIPELINE_ROOT = self.root / "case-bundles"
        router.VAULT = self.root / "vault"
        router.INDEX_DB = self.root / "missing-index.db"
        router.INGEST_JOBS_LOG = self.root / "logs" / "ingest_jobs.json"
        router.INGEST_BATCHES_LOG = self.root / "logs" / "ingest_batches.json"
        router.RUNS_LOG = self.root / "logs" / "runs.json"
        router._jobs.clear()
        router._batches.clear()
        router._runs.clear()
        deal_profile.VAULT = router.VAULT
        self.index_patch = patch.object(router, "_rebuild_index", return_value=None)
        self.index_patch.start()

        case_dir = router.VAULT / "deals" / self.case_id
        case_dir.mkdir(parents=True)
        (case_dir / "deal.md").write_text(
            "---\n"
            f"id: {self.case_id}\n"
            f"entity: {self.fixture['entity']}\n"
            "---\n",
            encoding="utf-8",
        )
        (case_dir / "deal_profile.json").write_text(
            json.dumps(self.fixture["deal_profile"], indent=2) + "\n",
            encoding="utf-8",
        )
        fund_lens = json.loads(
            (PROJECT_ROOT / self.fixture["fund_lens_path"]).read_text(
                encoding="utf-8"
            )
        )
        router.configure_fund_lens(self.case_id, fund_lens)

        bundle = router._pipeline_out_for_case(self.case_id)
        bundle.mkdir(parents=True)
        (bundle / "execution_graph_v7.json").write_text(
            json.dumps(self.fixture["runtime_template"], indent=2) + "\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.index_patch.stop()
        deal_profile.VAULT = self.previous_profile_vault
        bridge_v7._set_active_profile(self.previous_active_profile)
        for name in (
            "PIPELINE_OUT",
            "CASE_PIPELINE_ROOT",
            "VAULT",
            "INDEX_DB",
            "INGEST_JOBS_LOG",
            "INGEST_BATCHES_LOG",
            "RUNS_LOG",
        ):
            setattr(router, name, self.previous_router_state[name])
        router._jobs.clear()
        router._jobs.update(self.previous_router_state["jobs"])
        router._batches.clear()
        router._batches.update(self.previous_router_state["batches"])
        router._runs.clear()
        router._runs.update(self.previous_router_state["runs"])
        self.temporary.cleanup()

    @staticmethod
    def _request(case_id: str, source: dict, content: bytes) -> Request:
        payload = {
            "file_name": source["file_name"],
            "purpose": "PAN-57 sanitized mixed-source regression",
            "source_metadata": {
                "media_type": source["media_type"],
                "sanitized": True,
            },
            "content_b64": base64.b64encode(content).decode("ascii"),
        }
        body = json.dumps(payload).encode("utf-8")
        delivered = False

        async def receive():
            nonlocal delivered
            if delivered:
                return {"type": "http.request", "body": b"", "more_body": False}
            delivered = True
            return {"type": "http.request", "body": body, "more_body": False}

        return Request(
            {
                "type": "http",
                "method": "POST",
                "path": f"/api/v20/cases/{case_id}/ingest",
                "headers": [(b"content-type", b"application/json")],
            },
            receive,
        )

    @staticmethod
    def _source_bytes(source: dict) -> bytes:
        workbook = source.get("workbook")
        if not workbook:
            return source["content"].encode("utf-8")
        output = io.BytesIO()
        book = Workbook()
        sheet = book.active
        sheet.title = workbook["sheet"]
        for row in workbook["rows"]:
            sheet.append(row)
        book.save(output)
        return output.getvalue()

    def _fake_extractor(self, command, **_kwargs):
        source_path = Path(command[command.index("--source") + 1])
        source = self.sources_by_name[source_path.name]
        output_dir = Path(command[command.index("--output") + 1]) / "SINGLE"
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "e3_claims.json").write_text(
            json.dumps(
                {
                    "schema_version": "e3/pan57-fixture-v1",
                    "deal": self.case_id,
                    "claims": source["claims"],
                    "extraction_metadata": {
                        "compiler_fields_per_claim": [
                            {
                                key: claim.get(key)
                                for key in (
                                    "claim_id",
                                    "metric",
                                    "direction",
                                    "topic",
                                    "author",
                                    "derivation",
                                )
                            }
                            for claim in source["claims"]
                        ]
                    },
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return SimpleNamespace(returncode=0, stdout="PAN-57 fixture", stderr="")

    def _ingest(self, source: dict) -> str:
        tasks = BackgroundTasks()
        queued = asyncio.run(
            router.ingest(
                self.case_id,
                self._request(self.case_id, source, self._source_bytes(source)),
                tasks,
            )
        )
        for task in tasks.tasks:
            asyncio.run(task())
        job_id = queued["job_id"]
        self.assertEqual(router.get_job(job_id)["status"], "COMPLETE")
        proposal = router.get_evidence_proposal(self.case_id, job_id)
        self.assertEqual(proposal["proposal"]["status"], "PENDING_REVIEW")
        self.assertFalse(proposal["semantic_preview"]["current_mutated"])
        return job_id

    def _settle_event(self, event_id: str) -> tuple[dict, dict]:
        candidate = asyncio.run(
            router.admit(self.case_id, event_id, BackgroundTasks(), {})
        )
        run_id = candidate["run"]["run_id"]
        transition = candidate["transition"]
        selected_change_ids = [
            item["artifact_id"] for item in transition["artifact_change_sets"]
        ]
        self.assertTrue(selected_change_ids)
        prepared = asyncio.run(
            router.prepare_run(
                run_id,
                {
                    "actor_id": "partner-001",
                    "candidate_state_id": transition["candidate_state_id"],
                    "selected_change_ids": selected_change_ids,
                },
            )
        )
        self.assertEqual(prepared["status"], "PREPARED")

        authority_record_ids = []
        execution_package_ids = []
        connected = router.projection(self.case_id)["projection"]
        course = next(
            item
            for item in connected["deal"]["decisionRoom"]["courses"]
            if item.get("effect_type") == "INTERNAL"
        )
        actors = connected["actor_directory"]
        for human_stop in transition["human_stops"]:
            actor = next(
                item
                for item in actors
                if human_stop["required_role"]
                in {item.get("role"), *item.get("authority_roles", [])}
                and human_stop["authority_verb"] in item.get("authority_verbs", [])
                and str(
                    item.get("actor_id")
                    or item.get("participant_id")
                    or item.get("id")
                )
                != human_stop.get("required_actor_distinct_from")
            )
            actor_id = str(
                actor.get("actor_id")
                or actor.get("participant_id")
                or actor["id"]
            )
            attested = asyncio.run(
                router.attest(
                    run_id,
                    {
                        "actor_id": actor_id,
                        "candidate_state_id": transition["candidate_state_id"],
                        "human_stop_id": human_stop["stop_id"],
                        "course_id": course["id"],
                        "artifact_hash": transition["replay_hash"],
                    },
                )
            )
            authority_record_ids.append(
                attested["authority_record"]["authority_record_id"]
            )
            if attested.get("execution_package"):
                execution_package_ids.append(
                    attested["execution_package"]["execution_package_id"]
                )

        partial_status = transition.get("partial_settlement_status", {})
        partial = bool(
            partial_status.get("candidate") != "FULL"
            or partial_status.get("unsettled_component_ids")
            or transition["blocked_components"]
            or any(
                item.get("partial") for item in transition["artifact_change_sets"]
            )
        )
        settled = asyncio.run(
            router.settle_run(
                run_id,
                BackgroundTasks(),
                {
                    "actor_id": "partner-001",
                    "candidate_state_id": transition["candidate_state_id"],
                    "selected_change_ids": selected_change_ids,
                    "human_stop_ids": [
                        item["stop_id"] for item in transition["human_stops"]
                    ],
                    "authority_record_ids": authority_record_ids,
                    "execution_package_ids": execution_package_ids,
                    "allow_partial_settlement": partial,
                    "idempotency_key": f"SETTLE-{run_id}",
                },
            )
        )
        self.assertEqual(settled["runtime_state_id"], settled["current_state_id"])
        return candidate, settled

    @staticmethod
    def _claim_provenance(graph: dict, claim_id: str) -> set[str]:
        claim_node = next(
            node["id"]
            for node in graph["nodes"]
            if node.get("type") == "claim" and node.get("claim_id") == claim_id
        )
        return {
            str(edge["source"]).removeprefix("source:")
            for edge in graph["edges"]
            if edge.get("target") == claim_node
            and edge.get("rel") == "CONTAINS_CLAIM"
        }

    def test_growth_case_mixed_sources_settle_cumulatively_and_survive_refresh(self):
        board, qoe, workbook = self.fixture["sources"]
        bundle = router._pipeline_out_for_case(self.case_id)

        with patch.object(router.subprocess, "run", side_effect=self._fake_extractor):
            board_job = self._ingest(board)
            board_admitted = asyncio.run(
                router.admit_evidence(
                    self.case_id,
                    board_job,
                    {"decision": "ADMIT", "actor_id": "growth-reviewer"},
                )
            )
            self.assertEqual(board_admitted["new_claim_count"], 1)
            first_candidate, first_current = self._settle_event(
                board_admitted["event_id"]
            )
            self.assertIsInstance(first_candidate["transition"]["human_stops"], list)

            before_overlap = json.loads(
                (bundle / "semantic_current_graph.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                self._claim_provenance(
                    before_overlap, "northstar-revenue-fy25-base"
                ),
                {"SRC-NORTHSTAR-BOARD"},
            )

            qoe_job = self._ingest(qoe)
            qoe_admitted = asyncio.run(
                router.admit_evidence(
                    self.case_id,
                    qoe_job,
                    {"decision": "ADMIT", "actor_id": "growth-reviewer"},
                )
            )
            self.assertEqual(qoe_admitted["new_claim_count"], 0)
            self.assertIsNone(qoe_admitted["runtime_event"])
            after_overlap = json.loads(
                (bundle / "semantic_current_graph.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                self._claim_provenance(
                    after_overlap, "northstar-revenue-fy25-base"
                ),
                {"SRC-NORTHSTAR-BOARD", "SRC-NORTHSTAR-QOE"},
            )
            self.assertEqual(
                len(
                    [
                        node
                        for node in before_overlap["nodes"]
                        if node.get("type") == "claim"
                    ]
                ),
                len(
                    [
                        node
                        for node in after_overlap["nodes"]
                        if node.get("type") == "claim"
                    ]
                ),
                "overlap must add provenance without replacing the admitted claim",
            )

            workbook_job = self._ingest(workbook)
            workbook_admitted = asyncio.run(
                router.admit_evidence(
                    self.case_id,
                    workbook_job,
                    {"decision": "ADMIT", "actor_id": "growth-reviewer"},
                )
            )
            self.assertEqual(workbook_admitted["new_claim_count"], 1)
            self.assertEqual(workbook_admitted["semantic_graph"]["formula_nodes"], 1)
            self.assertEqual(len(router._load_excel_model_graphs(self.case_id)), 1)
            final_candidate, final_current = self._settle_event(
                workbook_admitted["event_id"]
            )

        final_claim_ids = {
            claim["claim_id"] for claim in final_candidate["candidate_graph"]["claims"]
        }
        self.assertEqual(
            final_claim_ids,
            {"northstar-revenue-fy25-base", "northstar-revenue-fy25-plan"},
        )
        self.assertNotEqual(
            first_current["current_state_id"], final_current["current_state_id"]
        )

        source_view = router.sources(self.case_id)
        self.assertEqual(len(source_view["inbox"]), 3)
        self.assertEqual(
            {item["source_id"] for item in source_view["sources"]},
            {
                "SRC-NORTHSTAR-BOARD",
                "SRC-NORTHSTAR-QOE",
                "SRC-NORTHSTAR-MODEL",
            },
        )

        router._runs.clear()
        router._load_durable_registries()
        refreshed = router.projection(self.case_id)
        deal = refreshed["projection"]["deal"]
        self.assertEqual(deal["archetype"]["id"], "growth-equity")
        self.assertFalse(deal["archetype"]["is_default"])
        self.assertEqual(deal["active_lens_id"], "FL-GROWTH-EQUITY-V1")
        self.assertEqual(
            {item["id"] for item in deal["question_spine"]},
            {"GE-Q-01", "GE-Q-02", "GE-Q-03", "GE-Q-04"},
        )
        revenue_question = next(
            item for item in deal["question_spine"] if item["id"] == "GE-Q-02"
        )
        self.assertEqual(revenue_question["claim_count"], 2)
        self.assertEqual(revenue_question["coverage"], "partial")
        self.assertIsInstance(deal["rooms"]["foundations"]["sets"], list)
        self.assertIsInstance(deal["rooms"]["unknowns"]["items"], list)
        self.assertEqual(
            {claim["claim_id"] for claim in deal["claims"]}, final_claim_ids
        )
        self.assertEqual(deal["candidate_graph"], {})
        self.assertEqual(deal["current_graph"]["state"], "CURRENT")
        versions = deal["graph_versions"]
        self.assertEqual(versions[-1]["kind"], "CURRENT")
        self.assertEqual(len({item["version_id"] for item in versions}), len(versions))
        self.assertEqual(
            refreshed["context"]["as_of_state_id"], final_current["current_state_id"]
        )


if __name__ == "__main__":
    unittest.main()
