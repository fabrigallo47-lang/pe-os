import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from tools.graph_trace import build_trace  # noqa: E402


def claim(
    claim_id: str,
    value: float,
    *,
    measurement: str = "total",
    bound: str = "EXACT",
    source_id: str | None = None,
):
    return {
        "claim_id": claim_id,
        "source_id": source_id or f"source-{claim_id}",
        "statement": f"Revenue is {bound} {value}.",
        "entity": "Keystone",
        "metric": "Revenue",
        "period_canonical": "FY2025",
        "scope": "consolidated",
        "basis": "ReportedView",
        "measurement": measurement,
        "scenario": "base",
        "unit": "$m",
        "value": value,
        "bound": bound,
    }


class Pan89GraphTraceTests(unittest.TestCase):
    def test_measurement_and_bound_ablation_is_explicit(self):
        claims = [
            claim("total", 100),
            claim("service-a", 40, measurement="service a"),
            claim("service-b", 60, measurement="service b"),
            claim("accounts-lower", 600, measurement="accounts", bound="AT_LEAST"),
            claim("accounts-exact", 640, measurement="accounts"),
        ]

        trace = build_trace(claims)

        self.assertEqual(trace["final"]["contradictions"], 0)
        self.assertEqual(
            trace["conflict_ablation"],
            {
                "without_measurement_or_bound": 4,
                "with_measurement_without_bound": 1,
                "with_measurement_and_bound": 0,
                "cross_source_residuals": 0,
                "removed_by_measurement": 3,
                "removed_by_bound": 1,
                "removed_as_same_source_detail": 0,
            },
        )

    def test_residual_conflict_carries_complete_inspectable_identity(self):
        trace = build_trace([claim("a", 100), claim("b", 90)])

        self.assertEqual(trace["final"]["contradictions"], 1)
        self.assertEqual(len(trace["residual_conflicts"]), 1)
        residual = trace["residual_conflicts"][0]
        self.assertEqual(residual["measurement"], "total")
        self.assertEqual(len(residual["identity"]), 9)
        self.assertNotIn("", residual["identity"])
        self.assertEqual(residual["peer_claim_ids"], ["a"])

    def test_trace_is_deterministic_for_same_ordered_input(self):
        claims = [claim("a", 100), claim("b", 90)]
        self.assertEqual(build_trace(claims), build_trace(claims))

    def test_same_source_rows_are_visible_but_not_independent_conflicts(self):
        claims = [
            claim("row-a", 100, source_id="SRC-DR"),
            claim("row-b", 90, source_id="SRC-DR"),
        ]

        trace = build_trace(claims)

        self.assertEqual(trace["final"]["contradictions"], 0)
        self.assertEqual(trace["final"]["same_source_details"], 1)
        self.assertEqual(trace["conflict_ablation"]["with_measurement_and_bound"], 1)
        self.assertEqual(trace["conflict_ablation"]["cross_source_residuals"], 0)
        self.assertEqual(trace["conflict_ablation"]["removed_as_same_source_detail"], 1)


if __name__ == "__main__":
    unittest.main()
