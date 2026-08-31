from __future__ import annotations

import copy
import json
import math
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.model_semantics import (  # noqa: E402
    ConceptProposal,
    ProposalConfidence,
    SemanticProposer,
)


def _cell(
    ref: str,
    row: int,
    col: int,
    kind: str,
    value: object,
    *,
    number_format: str = "General",
    precedents: list[str] | None = None,
    evaluated_value: object = None,
) -> dict:
    return {
        "locator": f"MODEL!{ref}",
        "sheet": "MODEL",
        "ref": ref,
        "row": row,
        "col": col,
        "kind": kind,
        "value": value,
        "number_format": number_format,
        "precedents": list(precedents or []),
        "evaluated_value": evaluated_value,
    }


def _fully_signalled_graph() -> dict:
    cells = [
        _cell("A1", 1, 1, "text", "Metric"),
        _cell("B1", 1, 2, "text", "FY2025"),
        _cell("A2", 2, 1, "text", "Revenue"),
        _cell("B2", 2, 2, "number", 12.5, number_format="$#,##0.0"),
    ]
    return {"cells": {cell["locator"]: cell for cell in cells}}


def _weak_identity_graph() -> dict:
    cells = [
        _cell("A2", 2, 1, "text", "EBITDA"),
        _cell(
            "B2",
            2,
            2,
            "formula",
            "=Z9",
            precedents=["MODEL!Z9"],
            evaluated_value=10.0,
        ),
        _cell("A3", 3, 1, "text", "Dependent output"),
        _cell(
            "B3",
            3,
            2,
            "formula",
            "=B2+1",
            precedents=["MODEL!B2"],
            evaluated_value=11.0,
        ),
    ]
    return {"cells": {cell["locator"]: cell for cell in cells}}


def _proposal_at(graph: dict, locator: str) -> ConceptProposal:
    proposals = SemanticProposer(graph).propose()
    return next(proposal for proposal in proposals if proposal.locator == locator)


class Pan84ModelSemanticsConfidenceTests(unittest.TestCase):
    def test_serialized_contract_has_exactly_four_confidence_dimensions(self) -> None:
        proposal = _proposal_at(_fully_signalled_graph(), "MODEL!B2")

        serialized = proposal.to_dict()
        self.assertEqual(
            set(serialized["confidence"]),
            {"extraction", "identity", "binding", "relation"},
        )
        self.assertEqual(
            serialized["confidence"],
            {
                "extraction": 1.0,
                "identity": 1.0,
                "binding": 0.0,
                "relation": 0.0,
            },
        )
        self.assertNotIn("overall", serialized["confidence"])
        self.assertEqual(json.loads(json.dumps(serialized)), serialized)

    def test_high_extraction_confidence_does_not_inflate_other_stages(self) -> None:
        proposal = _proposal_at(_weak_identity_graph(), "MODEL!B2")

        self.assertEqual(proposal.confidence.extraction, 1.0)
        self.assertEqual(proposal.confidence.identity, 0.25)
        self.assertEqual(proposal.confidence.binding, 0.0)
        self.assertEqual(proposal.confidence.relation, 0.0)
        self.assertEqual(
            proposal.signals["confidence_basis"]["identity"],
            {
                "label": True,
                "header": False,
                "unit": False,
                "decided_topology": False,
            },
        )

    def test_identity_signals_do_not_create_binding_or_relation_evidence(self) -> None:
        proposal = _proposal_at(_fully_signalled_graph(), "MODEL!B2")

        self.assertEqual(proposal.confidence.identity, 1.0)
        self.assertEqual(proposal.confidence.binding, 0.0)
        self.assertEqual(proposal.confidence.relation, 0.0)
        basis = proposal.signals["confidence_basis"]
        self.assertEqual(basis["binding"], {"candidate_binding_evidence": False})
        self.assertEqual(basis["relation"], {"relation_evidence": False})

    def test_confidence_dimensions_are_finite_numbers_in_closed_unit_interval(self) -> None:
        invalid_values = [True, -0.01, 1.01, math.nan, math.inf, "0.5", None]

        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    ProposalConfidence(extraction=value)  # type: ignore[arg-type]

        self.assertEqual(
            ProposalConfidence(0, 1, 0.5, 0.25),
            ProposalConfidence(
                extraction=0,
                identity=1,
                binding=0.5,
                relation=0.25,
            ),
        )

    def test_legacy_scalar_confidence_is_rejected_as_ambiguous(self) -> None:
        with self.assertRaisesRegex(TypeError, "separate extraction"):
            ConceptProposal(
                sheet="MODEL",
                cells="B2",
                label="Revenue",
                header="FY2025",
                kind="input",
                unit="$",
                values=12.5,
                confidence=0.9,  # type: ignore[arg-type]
            )

    def test_proposer_does_not_mutate_the_source_graph(self) -> None:
        graph = _fully_signalled_graph()
        before = copy.deepcopy(graph)

        SemanticProposer(graph).propose()

        self.assertEqual(graph, before)


if __name__ == "__main__":
    unittest.main()
