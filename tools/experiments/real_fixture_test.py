#!/usr/bin/env python3
"""Run the two GraphIC prototypes against REAL Keystone fixture text,
not the synthetic TEST_CHUNK -- claim/information extraction only, no
relation to the physical (PDF/PPTX/etc) extraction work.

Three real fragments from sources/keystone-fixture/layer1-ingest/, each an
actual EBITDA bridge or margin calculation with a real stated total to
check the extraction against:

  qoe_bridge   keystone_qoe_report.md        Reported EBITDA 10.2 + nine
                                              QoE adjustments -> Normalized
                                              EBITDA 11.9 (QoEView)
  firm_bridge  keystone_firm_model_summary.md Reported EBITDA 10.20 + four
                                              Firm adjustments (two of them
                                              negative reserves) ->
                                              Firm-underwritten EBITDA
                                              11.40 (FirmView)
  cim_margin   keystone_seller_cim.md        seller-adjusted EBITDA 12.7 /
                                              revenue 74.0 -> 17.2% margin
                                              (SellerView, one hop, simpler)

For each fragment, runs three ways and prints them side by side:
  (a) baseline   -- annotate_chunk's real CLAIM_TOOL/SYSTEM_PROMPT, untouched
  (b) graph      -- document_logic_extractor's own depends_on extraction
  (c) assisted   -- (a) again, with (b)'s rendered summary as extra context

Run: python3 -m tools.experiments.real_fixture_test
Needs ANTHROPIC_API_KEY (reads .env at repo root if present).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.extract_v2_physical import MODEL  # noqa: E402
from tools.llm_provider import anthropic_client_kwargs, configured_api_key  # noqa: E402
from tools.experiments.document_logic_extractor import (  # noqa: E402
    extract_document_graph, render_graph_summary, run_main_extractor,
)

FIXTURE_DIR = ROOT / "sources/keystone-fixture/layer1-ingest"

FRAGMENTS: dict[str, dict[str, object]] = {
    "qoe_bridge": {
        "source_doc": "keystone_qoe_report.md",
        "expected_total": 11.9,
        "expected_label": "Normalized EBITDA (QoEView)",
        "text": """\
Alderstone generated FY2025 reported revenue of $74.0m and reported EBITDA of $10.2m. Based on the procedures performed and the adjustments below, normalized FY2025 EBITDA is $11.9m.

## Normalized EBITDA schedule

| Adjustment | Amount | Treatment / support |
| --- | --- | --- |
| Reported EBITDA | 10.2 | Historical accounts |
| Founder / executive compensation | 0.35 | QoE accepted at market replacement cost |
| Transaction-readiness and professional fees | 0.25 | Recurring audit/compliance retained |
| Integration and systems costs | 0.3 | Firm retains $0.10m recurring cost |
| Legal and settlement expense | 0.2 | Supported non-recurring item |
| Duplicate occupancy / facility move | 0.15 | Implemented closure |
| Implemented headcount savings | 0.25 | Additional covenant-certified savings |
| Pricing and utilization initiatives | 0 | Forecast only; no historical add-back |
| Revenue cut-off | -0.1 | QoE correction |
| Bonus accrual normalization | 0.2 | Approved plan support |
| Related-party rent normalization | 0.1 | Not recognized in covenant definition |""",
    },
    "firm_bridge": {
        "source_doc": "keystone_firm_model_summary.md",
        "expected_total": 11.40,
        "expected_label": "Firm-underwritten EBITDA (FirmView)",
        "text": """\
## Firm-underwritten EBITDA adjustments

| Item | Amount |
| --- | --- |
| Reported EBITDA | $10.20m |
| Accepted historical adjustments | 1.70 |
| Revenue / WIP quality reserve | (0.20) |
| Customer / project run-rate reserve | (0.15) |
| Residual recurring integration requirement | (0.10) |
| Incremental finance and reporting cost | (0.05) |
| Firm-underwritten EBITDA | $11.40m |""",
    },
    "cim_margin": {
        "source_doc": "keystone_seller_cim.md",
        "expected_total": 17.2,
        "expected_label": "seller-adjusted EBITDA margin (SellerView, %)",
        "text": (
            "Management expects FY2025E revenue of $74.0m and seller-adjusted "
            "EBITDA of $12.7m, representing a 17.2% margin."
        ),
    },
    "covenant_ebitda_dispute": {
        "source_doc": "keystone_monitoring_junecompliance2027.md",
        "expected_total": 10.80,
        "expected_label": "Lender-accepted covenant EBITDA (controlling figure)",
        "text": """\
June 30, 2027 covenant EBITDA bridge. Lender-accepted basis.

| LTM item | Amount |
| --- | --- |
| Reported EBITDA | $9.40m |
| Permitted integration and remediation | 0.45 |
| Severance and reorganization | 0.25 |
| Temporary duplicate systems | 0.20 |
| Certified cost savings | 0.50 |
| Lender-accepted covenant EBITDA | $10.80m |

| Management-proposed item | Amount | Lender treatment |
| --- | --- | --- |
| Billing disruption / lost margin | $0.45m | Rejected - revenue recovery |
| Expected pricing recovery | 0.15 | Rejected - prospective |
| Unimplemented staffing savings | 0.20 | Rejected - not implemented |
| Management proposed covenant EBITDA | $11.60m | Not accepted |

The lender's $10.8m figure is controlling. The $1.4m bridge from reported to covenant EBITDA is within the amended 15% cap when measured against reported EBITDA.""",
    },
    "leverage_covenant_test": {
        "source_doc": "keystone_monitoring_junecompliance2027.md",
        "expected_total": 4.70,
        "expected_label": "Total net leverage (Net debt / Covenant EBITDA, a two-hop ratio)",
        "text": """\
June 30 debt, leverage and liquidity. Two covenant breaches.

| Debt / liquidity item | Amount |
| --- | --- |
| First-lien term loan | $42.265m |
| DDTL | 5.955 |
| Revolver | 4.780 |
| Gross funded debt | $53.000m |
| Cash | (2.200) |
| Net debt | $50.800m |
| Letters of credit | $2.000m |
| Undrawn revolver availability | 0.720 |
| Total liquidity | $2.920m |

Total net leverage: 4.70x. Maximum 4.25x.
Minimum liquidity: $2.92m. Minimum $3.00m.
FCCR: 0.85x. Minimum 1.25x.
Covenant EBITDA: $10.8m. Lender accepted.

Conclusion: the borrower is not in compliance with total net leverage, fixed-charge coverage or minimum liquidity.

| Requirement | Actual | Status |
| --- | --- | --- |
| Total net leverage ≤ 4.25x | 4.70x | Breach |
| FCCR ≥ 1.25x | 0.85x | Breach |
| Minimum liquidity ≥ $3.0m | $2.92m | Breach |""",
    },
}


def _summarize(claims: list[dict]) -> None:
    if not claims:
        print("  (no claims)")
        return
    for c in claims:
        print(f"  {c.get('metric', ''):<22} {c.get('value')!s:<8} "
              f"epistemic={c.get('epistemic_class', ''):<10} "
              f"basis={c.get('basis', ''):<12} "
              f"measurement={c.get('measurement', '')}")


def _found_total(claims: list[dict], expected: float) -> bool:
    for c in claims:
        try:
            if abs(float(c.get("value")) - expected) < 0.05:
                return True
        except (TypeError, ValueError):
            continue
    return False


def _identity_collisions(claims: list[dict]) -> list[str]:
    """The real risk on real documents, per CLAUDE.md: two claims sharing
    metric+basis (+period+perimeter, not tracked in this prototype) but NOT
    distinguished by `measurement` collide -- looking only at `derived`
    claims (this prototype's earlier, synthetic-test framing) misses this
    entirely, since real documents mostly state their totals directly."""
    groups: dict[tuple, list[dict]] = {}
    for c in claims:
        groups.setdefault((c.get("metric"), c.get("basis")), []).append(c)
    collisions = []
    for (metric, basis), group in groups.items():
        if len(group) < 2:
            continue
        measurements = [c.get("measurement") for c in group]
        if len(set(measurements)) < len(measurements):
            collisions.append(f"{metric} / {basis}: {len(group)} claims, "
                               f"measurements not all distinct: {measurements}")
    return collisions


def run_one(name: str, spec: dict, client) -> None:
    print("\n" + "=" * 78)
    print(f"{name}  (source: {spec['source_doc']}, expected total: "
          f"{spec['expected_total']} = {spec['expected_label']})")
    print("=" * 78)
    print(spec["text"][:300] + ("..." if len(spec["text"]) > 300 else ""))

    baseline = run_main_extractor(spec["text"], client, extra_context=None)
    graph_claims, g = extract_document_graph(spec["text"], client)
    summary = render_graph_summary(graph_claims)
    assisted = run_main_extractor(spec["text"], client, extra_context=summary)

    for label, claims in (("(a) baseline: main extractor alone", baseline),
                          (f"(b) document_logic_extractor's own graph "
                           f"({g.number_of_nodes()} nodes, {g.number_of_edges()} edges)", graph_claims),
                          ("(c) main extractor + document-graph context (assisted)", assisted)):
        print(f"\n--- {label} ---")
        _summarize(claims)
        collisions = _identity_collisions(claims)
        print(f"  total {spec['expected_total']} found: {_found_total(claims, spec['expected_total'])}  |  "
              f"identity collisions (same metric+basis, measurement not distinct): {len(collisions)}")
        for c in collisions:
            print(f"    ! {c}")


def main() -> int:
    api_key = configured_api_key()
    if not api_key:
        print("ANTHROPIC_API_KEY not configured -- nothing to run.")
        return 1
    import anthropic
    client = anthropic.Anthropic(**anthropic_client_kwargs(api_key))
    print(f"model: {MODEL}")

    for name, spec in FRAGMENTS.items():
        run_one(name, spec, client)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
