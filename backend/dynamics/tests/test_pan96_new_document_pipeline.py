"""PAN-96 — a document never in the Keystone corpus, ingest through projection.

Runs the real evidence-admission endpoint against an isolated bundle (never
the live keystone case) so a genuinely new document's claims can be driven
through identity -> relations -> projection without polluting real deal data.
Confirms: a resolvable claim binds to a canonical registry question/workstream
through the real binder; a deliberately unresolvable claim is never dropped
-- it stays visible in the semantic graph and is explicitly flagged by
compute_operative_claims' declared coverage limit; and no step in the chain
raises an unhandled exception (the HTTP-facing equivalent of a 500).
"""

import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

DYNAMICS_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = DYNAMICS_ROOT.parents[1]
sys.path.insert(0, str(DYNAMICS_ROOT))
sys.path.insert(0, str(PROJECT_ROOT))

import app.v20_router as router  # noqa: E402
from runtime import compute_operative_claims  # noqa: E402
from tools.object_identity import is_resolvable  # noqa: E402


class PAN96NewDocumentPipelineTests(unittest.TestCase):
    """Never touches vault/deals/keystone or pipeline_out/e3/K-IC -- isolated bundle only."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.bundle = self.root / "bundle"
        self.bundle.mkdir()

        self.previous_pipeline_out = router.PIPELINE_OUT
        self.previous_vault = router.VAULT
        self.previous_jobs = dict(router._jobs)
        self.previous_runs = dict(router._runs)
        router.PIPELINE_OUT = self.bundle
        router.VAULT = self.root / "vault"
        router._jobs.clear()
        router._runs.clear()
        self.index_patch = patch.object(router, "_rebuild_index", return_value=None)
        self.index_patch.start()

    def tearDown(self):
        self.index_patch.stop()
        router.PIPELINE_OUT = self.previous_pipeline_out
        router.VAULT = self.previous_vault
        router._jobs.clear()
        router._jobs.update(self.previous_jobs)
        router._runs.clear()
        router._runs.update(self.previous_runs)
        self.temporary.cleanup()

    def test_new_document_claims_bind_canonically_and_unresolvable_claim_is_a_declared_limit(self):
        filename = "never_before_seen_interview_transcript.pdf"
        resolvable_claim = {
            "claim_id": "pan96-resolvable-001",
            "statement": "Management stated third-quarter EBITDA for Alderstone standalone was $14.2 million.",
            "source_id": filename,
            "locator": "page 2, paragraph 3",
            "epistemic_class": "asserted",
            "value": "14.2",
            "unit": "$m",
            "entity": "Alderstone",
            "period": "Q3 FY2026",
            "perimeter": "Alderstone standalone",
            "metric": "EBITDA",
            "known_at": "2026-09-01T16:47:53Z",
            "topic": "EBITDA",
        }
        unresolvable_claim = {
            "claim_id": "pan96-unresolvable-001",
            "statement": "Management believes overall performance remains strong heading into next year.",
            "source_id": filename,
            "locator": "page 5, paragraph 1",
            "epistemic_class": "asserted",
            "value": "",
            "unit": "",
            "entity": "Alderstone",
            "period": "",       # deliberately missing -- vague forward-looking color commentary
            "perimeter": "",
            "metric": "",       # deliberately missing -- no quantified metric named
            "subject": "general business outlook",
            "known_at": "2026-09-01T16:47:53Z",
            "topic": "Management commentary",
        }
        self.assertTrue(is_resolvable(resolvable_claim))
        self.assertFalse(is_resolvable(unresolvable_claim))

        fund_lens = router._registry_fund_lens("keystone")
        self.assertIsNotNone(fund_lens, "keystone always has a repository-default Fund Lens")
        bound_claims, _fund_lens, review_blockers = router._bind_extracted_claims(
            "keystone",
            router._normalise_v1_claims([resolvable_claim, unresolvable_claim], filename),
            {},
        )
        self.assertEqual(review_blockers, [])
        by_id = {c["claim_id"]: c for c in bound_claims}
        # The real deterministic binder must find a real registry question for
        # the resolvable claim and must not fabricate one for the vague claim.
        self.assertTrue(by_id["pan96-resolvable-001"]["bears_on"])
        self.assertEqual(by_id["pan96-unresolvable-001"]["bears_on"], [])

        # The bound question's own workstream must already be canonical, not
        # the Fund Lens's legacy vocabulary ("financial" etc. -- forbidden
        # per CLAUDE.md). _ensure_question_registry (called inside
        # _bind_extracted_claims) is what normalizes it; check its output.
        LEGACY_WORKSTREAMS = {"commercial", "financial", "underwriting", "deal-emergent"}
        bound_question_id = by_id["pan96-resolvable-001"]["bears_on"][0]
        question_path = router.VAULT / "deals" / "keystone" / "questions" / f"{bound_question_id.lower()}.md"
        self.assertTrue(question_path.exists())
        workstream = router._read_frontmatter(question_path).get("workstream")
        self.assertNotIn(workstream, LEGACY_WORKSTREAMS)
        self.assertTrue(workstream)

        router._write_evidence_proposal("pan96-job", "keystone", filename, bound_claims)

        admitted = asyncio.run(
            router.admit_evidence(
                "keystone", "pan96-job", {"decision": "ADMIT", "actor_id": "pan96-test"}
            )
        )
        self.assertEqual(admitted["status"], "ADMITTED")
        self.assertEqual(admitted["new_claim_count"], 2)
        self.assertEqual(admitted["persisted_claim_count"], 2)

        # Neither claim disappears -- both persist in the admitted corpus.
        persisted = json.loads((self.bundle / "claims.json").read_text())
        persisted_ids = {c["claim_id"] for c in persisted}
        self.assertIn("pan96-resolvable-001", persisted_ids)
        self.assertIn("pan96-unresolvable-001", persisted_ids)

        # The unresolvable claim is a declared coverage limit, not silence:
        # compute_operative_claims must list it by id, and the resolvable
        # claim must form its own operative group.
        report = compute_operative_claims({"claims": persisted})
        self.assertIn("pan96-unresolvable-001", report["unresolvable"])
        self.assertNotIn("pan96-resolvable-001", report["unresolvable"])
        resolved_group = next(
            g for g in report["groups"] if g["operative_claim_id"] == "pan96-resolvable-001"
        )
        self.assertEqual(resolved_group["rule_applied"], "SOLE_CLAIM")

        # The projection endpoint (the real HTTP-facing read path) must not
        # raise, and both claims must be visible as real graph nodes.
        result = router.projection("keystone")
        nodes = result["projection"]["deal"]["semantic_current_graph"]["nodes"]
        node_claim_ids = {n.get("claim_id") for n in nodes if n.get("type") == "claim"}
        self.assertIn("pan96-resolvable-001", node_claim_ids)
        self.assertIn("pan96-unresolvable-001", node_claim_ids)

    def test_characterisation_claim_is_rejected_and_inspectable_on_disk(self):
        """A CHARACTERISATION-labelled claim never becomes evidence, and the
        rejection is a file a human can open, not a silent drop.

        No live LLM call is available in this environment (no API key), so
        this drives extract_v2's real deterministic post-extraction filter
        directly instead of the full extraction CLI -- the same real
        validate()/assemble()/_w() functions the CLI itself calls, just
        without the LLM chunking/extraction stage ahead of them.
        """
        from tools.extract_v2 import RawClaim, assemble, validate, _w

        seller_adjective = validate(RawClaim(
            metric="EBITDA",
            value=None,
            unit=None,
            period="FY2026",
            perimeter="Company",
            epistemic_class="asserted",
            direction="SUPPORTIVE",
            topic="commercial",
            definition_id=None,
            statement="Capital expenditure has been kept impressively low.",
            locator="page 7",
            source_id="SOURCE-CIM",
            source_path="cim.pdf",
            known_at="2026-09-01T08:00:00Z",
            claim_kind="CHARACTERISATION",
        ))
        self.assertTrue(seller_adjective.validation_errors)

        graph = assemble([seller_adjective])
        self.assertEqual(graph.admitted_count, 0)
        self.assertEqual(graph.rejected_count, 1)

        out_dir = self.root / "extract_out"
        _w(out_dir / "rejected_claims.json", graph.rejected)
        on_disk = json.loads((out_dir / "rejected_claims.json").read_text())
        self.assertEqual(len(on_disk), 1)
        self.assertTrue(any("characterisation" in e.lower() for e in on_disk[0]["errors"]))
        self.assertEqual(on_disk[0]["metric"], "EBITDA")


if __name__ == "__main__":
    unittest.main()
