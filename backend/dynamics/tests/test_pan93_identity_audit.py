import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from tools import document_store  # noqa: E402
from tools.object_identity import audit_claims, claims_from_e3  # noqa: E402


def structured_claim(
    claim_id: str,
    statement: str,
    *,
    period: str = "none",
    claim_kind: str = "QUANTITATIVE",
):
    return {
        "claim_id": claim_id,
        "statement": statement,
        "locator": f"synthetic.md::{claim_id}",
        "entity": "Keystone",
        "metric": "Revenue" if claim_kind == "QUANTITATIVE" else "Market Position",
        "period_canonical": period,
        "scope": "consolidated",
        "basis": "ReportedView",
        "measurement": "total",
        "scenario": "base",
        "unit": "$m" if claim_kind == "QUANTITATIVE" else "",
        "bound": "EXACT",
        "claim_kind": claim_kind,
    }


class Pan93IdentityAuditTests(unittest.TestCase):
    def test_missing_period_is_classified_from_source_evidence(self):
        claims = [
            structured_claim("complete", "FY2025 revenue was $74m.", period="FY2025"),
            structured_claim("defect", "FY2025 revenue was $75m."),
            structured_claim("omitted", "The company has more than 600 accounts."),
            structured_claim(
                "qualitative",
                "The company has a defensible market position.",
                claim_kind="QUALITATIVE",
            ),
        ]

        audit = audit_claims(claims)

        self.assertEqual(audit["resolvable"], 1)
        self.assertEqual(audit["resolvable_pct"], 25.0)
        self.assertEqual(
            audit["identity_dimensions"]["period"]["classifications"],
            {
                "extractor_defect": 1,
                "legitimate_qualitative_claim": 1,
                "legitimate_source_omission": 1,
            },
        )

        claims[0]["bound"] = "NONE"
        self.assertEqual(audit_claims(claims)["structured_extraction_fields"]["bound"]["missing"], 0)

    def test_e3_sidecar_populates_document_store_vocabulary_for_its_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            e3_dir = root / "pipeline_out" / "e3" / "K-IC"
            e3_dir.mkdir(parents=True)
            payload = {
                "deal": "keystone",
                "claims": [{"claim_id": "c-1", "statement": "Revenue was $74m."}],
                "extraction_metadata": {
                    "compiler_fields_per_claim": [{
                        "claim_id": "c-1",
                        "entity": "Keystone",
                        "basis": "ReportedView",
                        "period_canonical": "FY2025",
                    }]
                },
            }
            (e3_dir / "e3_claims.json").write_text(json.dumps(payload), encoding="utf-8")

            with (
                patch.object(document_store, "ROOT", root),
                patch.object(document_store, "KNOWLEDGE_ROOT", root / "pipeline_out" / "knowledge"),
            ):
                vocabulary = document_store.vocabulary_context("keystone", "revenue")

        self.assertEqual(vocabulary["entities"], ["Keystone"])
        self.assertEqual(vocabulary["definitions"], ["ReportedView"])
        self.assertEqual(vocabulary["periods"], ["FY2025"])

    def test_claims_from_e3_joins_frozen_claim_and_sidecar(self):
        payload = {
            "claims": [{"claim_id": "c-1", "statement": "Revenue was $74m."}],
            "extraction_metadata": {
                "compiler_fields_per_claim": [{"claim_id": "c-1", "entity": "Keystone"}]
            },
        }
        self.assertEqual(claims_from_e3(payload)[0]["entity"], "Keystone")


if __name__ == "__main__":
    unittest.main()
