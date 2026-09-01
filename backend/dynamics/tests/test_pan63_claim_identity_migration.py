import sys
import unittest
from pathlib import Path


DYNAMICS_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = DYNAMICS_ROOT.parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from tools.extract_v2 import METRIC_ENUM, RawClaim, assemble, validate  # noqa: E402
from tools.object_identity import METRIC_VOCABULARY, claim_id  # noqa: E402
from vercel.api._claim_graph import claims_to_graph  # noqa: E402


def raw_claim(
    *,
    value=74,
    source_id="SRC-CIM",
    source_version_id="SV-CIM-1",
    locator="cim.md::Revenue",
    statement="Revenue was $74m.",
):
    return RawClaim(
        metric="Revenue",
        value=value,
        unit="$m",
        period="FY2025A",
        perimeter="Keystone consolidated reported revenue",
        epistemic_class="asserted",
        direction="supports",
        topic="FINANCIAL_QOE",
        definition_id=None,
        statement=statement,
        locator=locator,
        source_id=source_id,
        source_path="cim.md",
        known_at="2026-01-01",
        source_version_id=source_version_id,
        entity="Keystone",
        period_canonical="FY2025A",
        scope="consolidated",
        measurement="total",
        basis="ReportedView",
        scenario="base",
    )


def graph_claim(*, subject="Keystone", claim_id_value=None):
    claim = {
        "subject": subject,
        "metric": "Revenue",
        "value": "74",
        "unit": "$m",
        "period": "FY2025A",
        "period_canonical": "FY2025A",
        "perimeter": "Keystone consolidated reported revenue",
        "entity": "Keystone",
        "scope": "consolidated",
        "measurement": "total",
        "basis": "ReportedView",
        "scenario": "base",
        "source_id": "SRC-CIM",
        "source_doc": "cim.md",
        "source_version_id": "SV-CIM-1",
        "locator": "cim.md::Revenue",
        "epistemic": "asserted",
        "statement": "Revenue was $74m.",
        "direction": "supports",
    }
    if claim_id_value:
        claim["claim_id"] = claim_id_value
    return claim


class Pan63ClaimIdentityMigrationTests(unittest.TestCase):
    def test_identity_metric_vocabulary_cannot_drift_from_extractor_enum(self):
        self.assertEqual(set(METRIC_VOCABULARY), set(METRIC_ENUM))

    def test_source_and_source_version_are_part_of_claim_identity(self):
        base = validate(raw_claim())
        other_source = validate(raw_claim(source_id="SRC-QOE"))
        other_version = validate(raw_claim(source_version_id="SV-CIM-2"))

        self.assertNotEqual(base.claim_id, other_source.claim_id)
        self.assertNotEqual(base.claim_id, other_version.claim_id)

    def test_extractor_uses_the_canonical_identity_owner(self):
        raw = raw_claim()
        canonical = validate(raw)
        expected = claim_id({
            "entity": raw.entity,
            "metric": raw.metric,
            "period": raw.period,
            "period_canonical": raw.period_canonical,
            "scope": raw.scope,
            "basis": raw.basis,
            "measurement": raw.measurement,
            "scenario": raw.scenario,
            "unit": raw.unit,
            "source_id": raw.source_id,
            "source_version_id": raw.source_version_id,
            "locator": raw.locator,
            "epistemic_class": raw.epistemic_class,
            "value": 74.0,
            "perimeter": raw.perimeter,
        })

        self.assertEqual(canonical.claim_id, expected)
        self.assertRegex(canonical.claim_id, r"^claim:[0-9a-f]{16}$")

    def test_rewording_statement_does_not_change_structured_identity(self):
        original = validate(raw_claim(statement="Revenue was $74m."))
        reworded = validate(raw_claim(statement="Reported sales totalled $74m."))

        self.assertEqual(original.claim_id, reworded.claim_id)

    def test_non_numeric_value_id_is_reproducible_from_emitted_e3_value(self):
        raw = raw_claim(value="30-60 days")
        canonical = validate(raw)
        emitted = graph_claim(claim_id_value=canonical.claim_id)
        emitted["value"] = canonical.value_raw

        self.assertIsNone(canonical.value)
        self.assertEqual(canonical.claim_id, claim_id(emitted))

    def test_zero_value_id_is_reproducible_from_emitted_e3_value(self):
        raw = raw_claim(value=0)
        canonical = validate(raw)
        emitted = graph_claim(claim_id_value=canonical.claim_id)
        emitted["value"] = str(canonical.value)

        self.assertEqual(canonical.value, 0.0)
        self.assertEqual(canonical.claim_id, claim_id(emitted))

    def test_independent_sources_are_not_deduplicated_by_assembler(self):
        claims = [
            validate(raw_claim()),
            validate(raw_claim(
                source_id="SRC-QOE",
                source_version_id="SV-QOE-1",
                locator="qoe.md::Revenue",
            )),
        ]

        graph = assemble(claims)

        self.assertEqual(graph.admitted_count, 2)
        self.assertEqual(graph.conflict_count, 0)

    def test_claim_graph_uses_canonical_id_not_subject_prose(self):
        first = graph_claim(subject="Keystone")
        second = graph_claim(subject="The Target Company")
        expected = claim_id(first)

        ids = []
        for item in (first, second):
            graph = claims_to_graph([item])
            node = next(
                node for node in graph["nodes"] if node.get("type") == "claim"
            )
            ids.append(node["stable_id"])

        self.assertEqual(ids, [expected, expected])

    def test_claim_graph_preserves_precomputed_canonical_id(self):
        expected = claim_id(graph_claim())
        graph = claims_to_graph([graph_claim(claim_id_value=expected)])
        node = next(
            node for node in graph["nodes"] if node.get("type") == "claim"
        )

        self.assertEqual(node["stable_id"], expected)


if __name__ == "__main__":
    unittest.main()
