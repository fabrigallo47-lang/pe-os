"""PAN-97 — prove the compiler/runtime hand-offs, including declared gaps.

The two expected failures are intentional documentation of seams that have no
contract yet.  They run the real admission/projection path and will become
unexpected successes when a claim-identity gate is added to CaseReading.
"""

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


DYNAMICS_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = DYNAMICS_ROOT.parents[1]
sys.path.insert(0, str(DYNAMICS_ROOT))
sys.path.insert(0, str(PROJECT_ROOT))

import app.v20_router as router  # noqa: E402
from runtime import apply_state_transition, compute_operative_claims  # noqa: E402
from tools.execution_mapping_compiler import populate_execution_mapping  # noqa: E402
from tools.extract_v2 import RawClaim, assemble, validate  # noqa: E402
from tools.identity_resolver import score_pair  # noqa: E402
from tools.object_identity import is_resolvable  # noqa: E402


def load_json(relative_path):
    return json.loads((DYNAMICS_ROOT / relative_path).read_text(encoding="utf-8"))


def policies():
    return (
        load_json("benchmark/keystone_materiality_policy_v0.json"),
        load_json("benchmark/keystone_authority_matrix_v0.json"),
    )


def graph(*, claims=None, model_nodes=None, bindings=None):
    return {
        "schema_version": "1.1.0",
        "case_id": "PAN97-CASE",
        "canonical_as_of": "2026-09-01",
        "claims": list(claims or []),
        "case_positions": [
            {
                "position_id": "READING-1",
                "statement": "The runtime reading is pending review.",
                "question_id": "Q-1",
                "epistemic_status_at_ic": "OPEN",
                "decision_status_at_ic": "PENDING",
                "freshness_status_at_ic": "CURRENT",
                "outcome_status_at_ic": "NOT_TESTED",
                "model_binding_status": "UNMAPPED",
            }
        ],
        "stated_positions": [],
        "model_nodes": list(model_nodes or []),
        "support_routes": [],
        "claim_position_edges": [],
        "position_dependencies": [],
        "position_model_bindings": list(bindings or []),
        "coverage_gaps": [],
        "decision_snapshot": {},
    }


def empty_mapping():
    return {
        "mapping_version": "PAN97-TEST",
        "canonical_graph_hash": "sha256:" + "0" * 64,
        "model_nodes": [],
        "directed_model_edges": [],
        "position_model_directions": [],
        "formulas": [],
        "rule_switches": [],
        "inverse_solver_configs": [],
        "model_controls": [],
        "cyclic_component_solver_configs": [],
        "coverage_limits": [],
    }


def stated_event(object_id, *, direction="SUPPORTIVE", supersedes=None, claim_id=None):
    mutation = {
        "operation": "ADD",
        "object_type": "STATED_POSITION",
        "object_id": object_id,
        "stated_by": "PERSON-PARTNER-1",
        "source_id": "SOURCE-IC-NOTES",
        "locator": "page 3, paragraph 2",
        "statement": f"{object_id} view",
        "direction": direction,
        "effective_date": "2026-09-01",
        "known_at": "2026-09-01T08:00:00Z",
        "question_ids": ["Q-1"],
        "relation_type": "SUPPORTS",
        "target_position_id": "READING-1",
    }
    if supersedes:
        mutation["supersedes_stated_position_id"] = supersedes
    # This is intentionally supplied by the integration caller.  The current
    # StatedPosition admission contract discards it, which is PAN-97's first
    # unresolved seam.
    if claim_id:
        mutation["claim_id"] = claim_id
    return {
        "event_id": f"EVENT-{object_id}",
        "event": "Attributed human view recorded",
        "effective_date": "2026-09-01",
        "known_at": "2026-09-01T08:00:00Z",
        "source_ids": ["SOURCE-IC-NOTES"],
        "trigger_claim_ids": [],
        "mutations": [mutation],
    }


def run(current_graph, events, mapping=None):
    materiality, authority = policies()
    return apply_state_transition(
        current_graph, events, mapping or empty_mapping(), materiality, authority
    )


def question():
    return {"id": "Q-1", "question_id": "Q-1", "label": "Is the case supported?"}


class PAN97CrossLayerIntegrationTests(unittest.TestCase):
    @unittest.expectedFailure
    def test_unresolvable_claim_identity_cannot_silently_form_case_reading(self):
        """Missing claim identity must block the reading, not be erased at admission.

        Deliberately not fixed here: the required claim-to-StatedPosition link is
        absent from both the runtime schema and the router projection contract,
        and changing it belongs to the compiler/platform owner rather than a
        speculative kernel change.
        """
        unresolvable_claim = {
            "claim_id": "CLAIM-UNRESOLVABLE",
            "statement": "Management says the business is excellent.",
            "subject": "excellent business",
            "metric": "",
            "period": "",
            "perimeter": "",
            "source_id": "SOURCE-MANAGEMENT",
            "locator": "page 1",
            "epistemic_class": "asserted",
            "bears_on": ["Q-1"],
        }
        self.assertFalse(is_resolvable(unresolvable_claim))
        self.assertEqual(
            score_pair(unresolvable_claim, {**unresolvable_claim, "claim_id": "OTHER", "subject": "unrelated topic"}).verdict,
            "distinct",
        )

        with patch.object(router, "_load_questions", return_value=[question()]):
            semantic = router._semantic_graph_from_claims(
                [unresolvable_claim], "PAN97-CASE", excel_models=[]
            )
        transitioned = run(
            graph(claims=[unresolvable_claim]),
            [stated_event("STATED-UNRESOLVABLE", claim_id="CLAIM-UNRESOLVABLE")],
        )
        foundations, unknowns, positions = router._semantic_rooms(
            semantic, [question()], transitioned["candidate_state"]["current_graph"]
        )

        # Required result once the contract exists: a declared human-stop/not-
        # formed reading.  Today the claim_id is discarded and a reading is
        # silently projected, so this test is an expected failure.
        self.assertEqual(positions, [])
        self.assertIn("identity", unknowns["items"][0]["value"].lower())
        self.assertEqual(foundations, [])

    def test_conflicting_stated_positions_return_declared_human_stop_limit(self):
        first = run(graph(), [stated_event("STATED-SUPPORT", direction="SUPPORTIVE")])
        second = run(
            first["candidate_state"]["current_graph"],
            [stated_event("STATED-ADVERSE", direction="ADVERSE")],
        )

        report = compute_operative_claims(second["candidate_state"]["current_graph"])

        self.assertEqual(report["groups"], [])
        self.assertEqual(len(report["coverage_limits"]), 1)
        limit = report["coverage_limits"][0]
        self.assertEqual(limit["reason_code"], "STATED_POSITION_OPERATIVE_RESOLUTION_UNSUPPORTED")
        self.assertEqual(limit["resolution"], "HUMAN_STOP")
        self.assertEqual(limit["scope_ids"], ["STATED-ADVERSE", "STATED-SUPPORT"])

    def test_pan67_drives_chain_with_superseded_pending_reading_is_declared(self):
        """A PAN-67 DRIVES edge remains traversable after stated supersession.

        There is no separate ``PENDING`` supersession state in the admitted
        StatedPosition contract: supersession is append-only and immediately
        operative.  The CaseReading itself remains decision-status PENDING, so
        the runtime must expose its unevaluated scope rather than crash or claim
        settlement.
        """
        source = {
            "schema": "source-graph-1",
            "workbook": "pan97.xlsx",
            "digest": "sha256:pan97-fixture",
            "defined_names": {},
            "cells": {
                "INPUTS!A1": {"kind": "number", "value": 100},
                "MODEL!B1": {
                    "kind": "formula",
                    "value": "=INPUTS!A1+1",
                    "evaluated_value": 101,
                    "precedents": ["INPUTS!A1"],
                },
            },
        }
        node = lambda locator: "MN-" + locator.replace("!", "-")
        bindings = {
            "schema_version": "model-binding-resolution/1.0",
            "input_digest": "sha256:pan97-bindings",
            "status": "RESOLVED",
            "bindings": [
                {
                    "binding_id": f"BIND-{index}",
                    "locator": locator,
                    "model_node_id": node(locator),
                    "concept_id": f"CONCEPT-{index}",
                    "identity": {"period": "FY2026", "scope": "TEST"},
                    "unit": "USD_M",
                    "reason_codes": ["RESOLVED"],
                }
                for index, locator in enumerate(source["cells"], start=1)
            ],
            "coverage_limits": [],
        }
        base = empty_mapping()
        base["position_model_directions"] = [
            {
                "binding_id": "PMB-PAN97",
                "position_id": "READING-1",
                "model_node_id": node("INPUTS!A1"),
                "direction": "POSITION_DRIVES_MODEL",
            }
        ]
        mapping = populate_execution_mapping(source, bindings, base)
        model_nodes = [
            {
                "model_node_id": item["model_node_id"],
                "name": item["label"],
                "period": item.get("period", "FY2026"),
                "perimeter": item.get("perimeter", "TEST"),
                "value": item.get("initial_value"),
                "unit": item.get("unit"),
            }
            for item in mapping["model_nodes"]
        ]
        first = run(graph(model_nodes=model_nodes), [stated_event("STATED-OLD")], mapping)
        second = run(
            first["candidate_state"]["current_graph"],
            [stated_event("STATED-NEW", supersedes="STATED-OLD")],
            mapping,
        )

        output = second["transition_output"]
        reached = {item["object_id"] for item in output["affected_set"]}
        self.assertTrue({"STATED-NEW", "READING-1", node("INPUTS!A1"), node("MODEL!B1")} <= reached)
        self.assertNotIn("STATED-OLD", reached)
        self.assertIn(
            "EVALUATION_STAGE_NOT_IMPLEMENTED",
            {item["reason_code"] for item in output["coverage_limits"]},
        )
        self.assertEqual(
            second["candidate_state"]["current_graph"]["case_positions"][0]["decision_status_at_ic"],
            "PENDING",
        )

    @unittest.expectedFailure
    def test_characterisation_rejection_cannot_silently_form_case_reading(self):
        """A rejected descriptor must leave the CaseReading not formed.

        Deliberately not fixed: the projection currently permits an attributed
        view plus pre-existing runtime POSITION to form a reading even when the
        extractor admitted zero evidence.  Resolving whether a stated view may
        independently form a reading is a kernel semantic decision, not one to
        guess in this integration ticket.
        """
        rejected = assemble([
            validate(RawClaim(
                metric="Market Position",
                value=None,
                unit=None,
                period="FY2026",
                perimeter="Company",
                epistemic_class="asserted",
                direction="SUPPORTIVE",
                topic="commercial",
                definition_id=None,
                statement="The company has a strong market position.",
                locator="page 4",
                source_id="SOURCE-CIM",
                source_path="cim.pdf",
                known_at="2026-09-01T08:00:00Z",
                claim_kind="CHARACTERISATION",
            ))
        ])
        self.assertEqual(rejected.admitted_count, 0)
        self.assertEqual(rejected.rejected_count, 1)

        with patch.object(router, "_load_questions", return_value=[question()]):
            semantic = router._semantic_graph_from_claims([], "PAN97-CASE", excel_models=[])
        transitioned = run(graph(), [stated_event("STATED-CHARACTERISATION")])
        foundations, unknowns, positions = router._semantic_rooms(
            semantic, [question()], transitioned["candidate_state"]["current_graph"]
        )

        # Required result: a not-formed reading plus a declared rejection gap.
        self.assertEqual(positions, [])
        self.assertEqual(foundations, [])
        self.assertIn("not formed", unknowns["items"][0]["value"].lower())


if __name__ == "__main__":
    unittest.main()
