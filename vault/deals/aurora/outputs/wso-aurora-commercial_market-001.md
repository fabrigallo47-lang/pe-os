---
type: workstream-output
id: wso-aurora-commercial_market-001
deal: "[[aurora]]"
workstream: commercial_market
tied-to: ["[[a-aurora-001]]", "[[a-aurora-003]]", "[[a-aurora-005]]"]
uses: ["[[c-aurora-003]]", "[[c-aurora-004]]", "[[c-aurora-005]]", "[[c-aurora-007]]", "[[c-aurora-008]]", "[[c-aurora-009]]", "[[c-aurora-010]]"]
stale: true
supersedes: null
written-by: workstream-runner
produced: 2026-07-13
---

# Commercial / market — findings

## F1 — Gross churn is contested, and the observed side points materially above the underwritten level: management asserts 12% while direct customer testimony puts recent-cohort churn near 18%
- Tied to: [[a-aurora-001]] · direction: challenges · materiality: high
- Established from: [[c-aurora-005]], [[c-aurora-003]], [[c-aurora-008]], [[c-aurora-009]]
- The finding is contested: the CIM's blended 12% ([[c-aurora-005]], asserted) does not reconcile with a top-20 reference customer's ~18% in their segment ([[c-aurora-003]], [[c-aurora-008]], both observed) and their report that half their onboarding cohort has already left ([[c-aurora-009]], observed). The observed claims carry more epistemic weight than the assertion, but they come from a single account's vantage point, not company-wide data. At churn near 18%, NRR ≥ 115% is arithmetically strained unless expansion is exceptional — no claim in the vault speaks to expansion at all.
- Missing evidence that would settle it: company-system cohort-level churn / ARR waterfall (logo and gross-revenue churn by cohort and segment), plus expansion revenue data sufficient to compute NRR directly rather than infer it from gross churn.

## F2 — The FY26 new-bookings plan of €12.4m is contradicted by the observed Q2 run-rate, which implies €9.8m
- Tied to: [[a-aurora-003]] · direction: challenges · materiality: high
- Established from: [[c-aurora-004]], [[c-aurora-007]]
- The finding is contested: management's data-pack figure of €12.4m ([[c-aurora-004]], asserted) does not reconcile with the Q2 trading update's run-rate implying €9.8m ([[c-aurora-007]], observed — company reporting, not a management projection). The observed run-rate outweighs the asserted plan. The gap matters beyond this workstream: at NRR of 115% supplying ~15 growth points, bookings at run-rate rather than plan removes the points [[a-aurora-002]] needs to clear 25% — so the "new logos are optional" framing in the thesis is not what the underwritten numbers actually do.
- Missing evidence that would settle it: pipeline coverage and stage-weighted detail for H2 FY26, historical H1/H2 bookings seasonality, and signed-but-not-live backlog that would justify plan over run-rate.

## F3 — Key-account retention is observed to be founder-contingent, not institutional: a top-20 customer tied their renewal directly to the founder
- Tied to: [[a-aurora-005]] · direction: challenges · materiality: high
- Established from: [[c-aurora-003]], [[c-aurora-010]]
- A top-20 reference customer, on recorded calls, tied their own renewal to the founder personally ([[c-aurora-003]], observed) and said they would immediately reconsider the contract if he left ([[c-aurora-010]], observed). This is direct observed testimony against the CIM's product-criticality framing of retention. It also bears on [[a-aurora-001]]: if the pattern generalizes across key accounts, the NRR assumption only holds conditional on founder continuity through the 5-year hold — a condition the assumption does not state. Sample is one account; generalization is not established.
- Missing evidence that would settle it: reference calls across a broader sample of top-20 accounts probing renewal drivers, and any contractual or organizational evidence (key-person clauses, account-team structure) showing whether relationships are institutionalized beyond the founder.

## Open per this workstream
- No claim in the vault measures NRR itself — only gross churn and one cohort-attrition anecdote. NRR ≥ 115% ([[a-aurora-001]]) can currently be neither supported nor refuted from commercial evidence; expansion revenue is entirely unevidenced.
- [[q-aurora-pipeline]] has no pipeline-quality evidence bound at all (coverage ratios, win rates, sales-cycle data); this run could only test the bookings plan against the Q2 run-rate, not the pipeline behind it.
- All observed churn and founder-dependence evidence traces to a single reference customer across two calls; whether it generalizes across the base is unestablished.
- This run does not resolve [[q-aurora-retention]] or [[q-aurora-pipeline]]; both remain open with contested evidence.
