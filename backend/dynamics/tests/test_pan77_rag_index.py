from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.rag_index import (
    INDEX_SCHEMA_VERSION,
    PROPOSAL_SCHEMA_VERSION,
    build_index,
    load_payload,
    main,
    propose_gap_candidates,
)


def _claim(
    claim_id: str,
    statement: str,
    *,
    metric: str = "Customer Concentration",
    period: str = "FY2025",
    entity: str = "Keystone",
    source_id: str = "NEW-CUSTOMER-DD",
    locator: str = "p. 12",
) -> dict:
    return {
        "claim_id": claim_id,
        "statement": statement,
        "entity": entity,
        "metric": metric,
        "period": period,
        "perimeter": f"{entity} consolidated customer diligence",
        "source_id": source_id,
        "locator": locator,
        "value": "18%",
        "unit": "%",
        "epistemic_class": "attested",
    }


class Pan77RagIndexTests(unittest.TestCase):
    def setUp(self) -> None:
        self.existing_claim = _claim(
            "CLAIM-OLD",
            "Historical customer concentration was reviewed for FY2024.",
            period="FY2024",
            source_id="OLD-QOE",
            locator="p. 3",
        )
        self.index = build_index([{"source": "old.json", "claims": [self.existing_claim]}])
        self.open_gap = {
            "gap_id": "GAP-CUSTOMER",
            "area": "Customer diligence",
            "statement": (
                "Missing customer concentration and retention evidence from "
                "customer interviews."
            ),
            "effect": "Largest customer risk remains unverified.",
            "status": "OPEN",
            "expected_identity": {
                "entity": "Keystone",
                "metric": "Customer Concentration",
                "period": "FY2025",
            },
        }
        self.closed_gap = {
            "gap_id": "GAP-LEGAL",
            "area": "Legal",
            "statement": "Missing signed customer contracts.",
            "status": "CLOSED",
            "perimeter": "Keystone customer contracts",
        }
        self.best_claim = _claim(
            "CLAIM-BEST",
            (
                "Customer interviews confirm customer concentration and retention; "
                "the largest customer represents 18% of revenue."
            ),
            locator="interview 4, paragraph 7",
        )
        self.weaker_claim = _claim(
            "CLAIM-WEAKER",
            "The customer concentration analysis reports an 18% share.",
            locator="appendix A",
        )

    def test_build_index_is_deduplicated_deterministic_and_auditable(self) -> None:
        unresolved = _claim(
            "CLAIM-NO-PERIOD",
            "Customer concentration is discussed without a period.",
            period="",
            locator="p. 8",
        )
        payloads = [
            {"claims": [unresolved, self.existing_claim]},
            {"claims": [self.existing_claim]},
        ]

        first = build_index(payloads)
        second = build_index(reversed(payloads))

        self.assertEqual(first, second)
        self.assertEqual(first["schema_version"], INDEX_SCHEMA_VERSION)
        self.assertTrue(first["index_digest"].startswith("sha256:"))
        self.assertEqual(first["statistics"]["input_claims"], 3)
        self.assertEqual(first["statistics"]["indexed_claims"], 2)
        self.assertEqual(first["statistics"]["resolvable_claims"], 1)
        self.assertEqual(first["statistics"]["unresolvable_claims"], 1)
        self.assertEqual(
            [claim["claim_id"] for claim in first["claims"]],
            ["CLAIM-NO-PERIOD", "CLAIM-OLD"],
        )

    def test_ranking_is_deterministic_and_exposes_score_factors(self) -> None:
        source = {"claims": [self.weaker_claim, self.best_claim]}

        first = propose_gap_candidates(
            self.index, source, [self.open_gap], top_k=2, min_score=0.05
        )
        second = propose_gap_candidates(
            self.index, source, [self.open_gap], top_k=2, min_score=0.05
        )

        self.assertEqual(first, second)
        self.assertEqual(first["schema_version"], PROPOSAL_SCHEMA_VERSION)
        self.assertEqual(
            [proposal["candidate_claim"]["claim_id"] for proposal in first["proposals"]],
            ["CLAIM-BEST", "CLAIM-WEAKER"],
        )
        self.assertGreater(first["proposals"][0]["score"], first["proposals"][1]["score"])
        factors = first["proposals"][0]["score_factors"]
        self.assertGreater(factors["lexical_cosine"], 0)
        self.assertEqual(factors["identity_match"], 1.0)
        self.assertEqual(
            factors["identity_dimensions_matched"],
            ["entity", "metric", "period"],
        )
        self.assertIn("customer", factors["shared_terms"])
        self.assertEqual(
            first["proposals"][0]["source"],
            {
                "source_id": "NEW-CUSTOMER-DD",
                "source_version": "",
                "locator": "interview 4, paragraph 7",
            },
        )

    def test_only_explicit_active_gaps_are_in_scope(self) -> None:
        source = {"claims": [self.best_claim]}
        result = propose_gap_candidates(
            self.index,
            source,
            {"coverage_gaps": [self.open_gap, self.closed_gap]},
            min_score=0.05,
        )

        self.assertEqual({item["gap_id"] for item in result["proposals"]}, {"GAP-CUSTOMER"})
        snapshots = {item["gap_id"]: item for item in result["gap_snapshots"]}
        self.assertTrue(snapshots["GAP-CUSTOMER"]["active_for_proposals"])
        self.assertFalse(snapshots["GAP-LEGAL"]["active_for_proposals"])
        self.assertEqual(snapshots["GAP-LEGAL"]["proposal_count"], 0)

        no_declaration = propose_gap_candidates(self.index, source, [])
        self.assertEqual(no_declaration["proposals"], [])
        self.assertEqual(no_declaration["statistics"]["declared_gaps"], 0)

    def test_structured_gap_identity_is_a_hard_scope_not_a_guess(self) -> None:
        wrong_metric = _claim(
            "CLAIM-EBITDA",
            "Customer interviews discuss customer concentration and retention.",
            metric="EBITDA",
        )
        wrong_period = _claim(
            "CLAIM-OLD-PERIOD",
            "Customer interviews discuss customer concentration and retention.",
            period="FY2024",
        )

        result = propose_gap_candidates(
            self.index,
            {"claims": [wrong_metric, wrong_period]},
            [self.open_gap],
            min_score=0.0,
        )

        self.assertEqual(result["proposals"], [])
        self.assertEqual(result["statistics"]["eligible_claims"], 2)

    def test_unit_and_currency_are_hard_identity_boundaries(self) -> None:
        gap = copy.deepcopy(self.open_gap)
        gap["expected_identity"] = {
            "entity": "Keystone",
            "metric": "Revenue",
            "period": "FY2025",
            "unit": "$mm",
            "currency": "USD",
        }
        eur_claim = _claim(
            "CLAIM-EUR-REVENUE",
            "Revenue evidence addresses the declared revenue gap.",
            metric="Revenue",
        )
        eur_claim.update({"unit": "€mm", "currency": "EUR"})

        result = propose_gap_candidates(
            self.index,
            {"claims": [eur_claim]},
            [gap],
            min_score=0.0,
        )

        self.assertEqual(result["proposals"], [])
        self.assertEqual(result["statistics"]["eligible_claims"], 1)

    def test_unresolvable_claim_is_visible_but_never_matched(self) -> None:
        no_period = _claim(
            "CLAIM-NO-PERIOD",
            "Customer interviews confirm customer concentration and retention.",
            period="",
        )

        result = propose_gap_candidates(
            self.index, {"claims": [no_period]}, [self.open_gap], min_score=0.0
        )

        self.assertEqual(result["proposals"], [])
        self.assertEqual(result["statistics"]["eligible_claims"], 0)
        self.assertEqual(result["statistics"]["excluded_claims"], 1)
        self.assertEqual(
            result["excluded_candidates"][0]["reason_code"],
            "UNRESOLVABLE_IDENTITY",
        )
        self.assertIn("nessun accoppiamento", result["excluded_candidates"][0]["reason"])

    def test_missing_provenance_and_already_indexed_claims_are_not_proposed(self) -> None:
        missing_locator = _claim(
            "CLAIM-NO-LOCATOR",
            "Customer concentration is confirmed by interviews.",
            locator="",
        )
        result = propose_gap_candidates(
            self.index,
            {"claims": [missing_locator, self.existing_claim]},
            [self.open_gap],
            min_score=0.0,
        )

        self.assertEqual(result["proposals"], [])
        self.assertEqual(
            {item["reason_code"] for item in result["excluded_candidates"]},
            {"MISSING_PROVENANCE", "ALREADY_INDEXED"},
        )

    def test_proposals_never_mutate_or_admit_the_gap(self) -> None:
        gaps = [self.open_gap, self.closed_gap]
        before = copy.deepcopy(gaps)

        result = propose_gap_candidates(
            self.index, {"claims": [self.best_claim]}, gaps, min_score=0.05
        )

        self.assertEqual(gaps, before)
        self.assertEqual(result["declared_gaps"], before)
        self.assertEqual(
            result["declared_gap_digest_before"],
            result["declared_gap_digest_after"],
        )
        self.assertTrue(all(item["unchanged"] for item in result["gap_snapshots"]))
        proposal = result["proposals"][0]
        self.assertEqual(proposal["status"], "PROPOSED")
        self.assertEqual(proposal["review_status"], "HUMAN_REVIEW")
        self.assertEqual(proposal["admission_status"], "PENDING")
        self.assertFalse(proposal["auto_admitted"])
        self.assertEqual(
            result["governance"],
            {
                "auto_admission": False,
                "required_next_step": "HUMAN_REVIEW",
                "gap_mutation_performed": False,
            },
        )

    def test_cli_accepts_json_yaml_and_live_store_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            live_dir = tmp_path / "live" / "keystone"
            live_dir.mkdir(parents=True)
            (live_dir / "claims.json").write_text(
                json.dumps([self.existing_claim]), encoding="utf-8"
            )
            source_path = tmp_path / "new-source.yaml"
            source_path.write_text(
                yaml.safe_dump({"claims": [self.best_claim]}, sort_keys=True),
                encoding="utf-8",
            )
            gaps_path = tmp_path / "gaps.yaml"
            gaps_path.write_text(
                yaml.safe_dump({"coverage_gaps": [self.open_gap]}, sort_keys=True),
                encoding="utf-8",
            )
            index_path = tmp_path / "index.json"
            proposals_path = tmp_path / "proposals.json"

            self.assertEqual(
                main(["index", "--input", str(live_dir), "--out", str(index_path)]),
                0,
            )
            self.assertEqual(
                main(
                    [
                        "propose",
                        "--index",
                        str(index_path),
                        "--source",
                        str(source_path),
                        "--gaps",
                        str(gaps_path),
                        "--out",
                        str(proposals_path),
                        "--min-score",
                        "0.05",
                    ]
                ),
                0,
            )

            saved_index = load_payload(index_path)
            saved_proposals = load_payload(proposals_path)
            self.assertEqual(saved_index["schema_version"], INDEX_SCHEMA_VERSION)
            self.assertEqual(saved_proposals["statistics"]["proposals"], 1)
            self.assertEqual(
                saved_proposals["proposals"][0]["candidate_claim"]["claim_id"],
                "CLAIM-BEST",
            )

    def test_gap_identifier_is_mandatory(self) -> None:
        undeclared = {"statement": "Missing customer concentration evidence."}
        with self.assertRaisesRegex(ValueError, "gap_id"):
            propose_gap_candidates(
                self.index,
                {"claims": [self.best_claim]},
                {"coverage_gaps": [undeclared]},
            )

    def test_markdown_frontmatter_claim_is_loaded_without_inference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            note = Path(tmp) / "claim.md"
            note.write_text(
                "---\n"
                "claim_id: CLAIM-MD\n"
                "entity: Keystone\n"
                "metric: Customer Concentration\n"
                "period: FY2025\n"
                "perimeter: Keystone consolidated customers\n"
                "source_id: SRC-MD\n"
                "locator: paragraph 2\n"
                "---\n"
                "Customer concentration is documented in the source.\n",
                encoding="utf-8",
            )

            loaded = load_payload(note)
            indexed = build_index([loaded])

        self.assertEqual(loaded["statement"], "Customer concentration is documented in the source.")
        self.assertEqual(indexed["statistics"]["resolvable_claims"], 1)
        self.assertEqual(indexed["claims"][0]["claim_id"], "CLAIM-MD")


if __name__ == "__main__":
    unittest.main()
