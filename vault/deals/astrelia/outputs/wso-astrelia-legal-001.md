---
type: workstream-output
id: wso-astrelia-legal-001
deal: "[[astrelia]]"
workstream: legal
tied-to: []
uses: ["[[c-astrelia-001]]", "[[c-astrelia-003]]", "[[c-astrelia-004]]", "[[c-astrelia-005]]", "[[c-astrelia-009]]", "[[c-astrelia-026]]", "[[c-astrelia-028]]", "[[c-astrelia-029]]"]
stale: false
supersedes: null
written-by: workstream-runner
produced: 2026-07-15
---

# Legal — findings

> **Note on tied-to:** `assumptions/` is empty for this deal — no `a-astrelia-*` object exists, so `tied-to` is empty and no staleness edge can attach to these findings. Each finding instead names the *implied* assumption it bears on and the nearest open question. No question carries `target-workstream: legal`; findings are bound to the questions their claims already bear on ([[q-astrelia-process]], [[q-astrelia-u1-61-2-of-plan-revenue-has-no-named]], [[q-astrelia-u3-nebulaos-margins-65-80-assumed-vs]], [[q-astrelia-commercial]]). Making the assumptions first-class and opening a legal-targeted question are the first open items below.

## F1 — The only executed legal instrument evidenced for this deal is the NDA; the confidentiality basis for receiving diligence materials is established and well-evidenced
- Tied to: *(no assumption on file)* — implied assumption "Meridian has a valid legal basis to receive and hold Astrelia's diligence materials"; bears on [[q-astrelia-process]] · direction: supports · materiality: low
- Established from: [[c-astrelia-009]]
- This is the strongest-typed legal claim in the vault: `observed` — NDA negotiated 20 May – 12 June 2025, Astrelia legal drafted, Meridian legal (Elena Bassi) redlined, Giulia Conti counter-signed. Nothing contradicts it. Note the NDA's *terms* are not on file as claims — only the fact of its negotiation and execution.
- Missing evidence that would settle it: the executed NDA itself as an artifact (term, scope, standstill or non-solicit provisions, residuals clause), so its constraints on Meridian's process conduct can be read rather than presumed.

## F2 — The 65–80%-margin NebulaOS software line has no contractual substrate on file: not one customer contract is disclosed
- Tied to: *(no assumption on file)* — implied assumption "NebulaOS revenue is contractually attainable on software-like terms"; bears on [[q-astrelia-u3-nebulaos-margins-65-80-assumed-vs]] · direction: challenges · materiality: high
- Established from: [[c-astrelia-004]] (asserted: no NebulaOS customer contract disclosed as of 8 Jul 2025), [[c-astrelia-003]] (asserted: 65–80% margin assumed vs 17–25% hardware)
- From a legal-diligence standpoint there is nothing to review: no license terms, no pricing schedule, no IP-ownership or escrow provisions, no term/termination structure for the product carrying the plan's margin expansion. [[c-astrelia-004]] is `asserted` by the deal team (an absence statement, not an observed data-room sweep), but no claim in the vault contradicts it.
- Missing evidence that would settle it: any executed or negotiated NebulaOS customer agreement — or, failing that, a data-room contract register confirming the absence as observed rather than asserted.

## F3 — Executed-contract diligence can substantiate at most a thin slice of plan revenue: ~92.3% of FY30E and ~77.4% of cumulative FY25–30E plan revenue sits in the uncontracted pipeline tranche
- Tied to: *(no assumption on file)* — implied assumption "the plan's revenue is meaningfully secured by contract (backlog)"; bears on [[q-astrelia-commercial]] and [[q-astrelia-u1-61-2-of-plan-revenue-has-no-named]] · direction: challenges · materiality: high
- Established from: [[c-astrelia-028]] (derived, arithmetic shown: FY30E pipeline tranche €919.55m of €996.76m = 92.3%), [[c-astrelia-029]] (derived, arithmetic shown: cumulative pipeline €1,859.46m of €2,403.71m = 77.4%), [[c-astrelia-026]] (asserted tranche detail these rest on)
- Backlog is the only tranche a contract review can verify against signed paper; by the plan's own tranche structure, backlog contributes nothing to FY30E revenue. The derived claims show their working but rest entirely on management-asserted tranche figures — no observed contract data exists in the vault.
- Missing evidence that would settle it: the actual backlog contract files (order values, delivery schedules, termination-for-convenience and milestone-payment terms) reconciled against the backlog tranche arrays.

## F4 — Counterparty legal review is impossible for the majority of plan revenue: 14 of 21 pipeline lines (~61.2% of cumulative FY25–30E plan revenue) have no named counterparty
- Tied to: *(no assumption on file)* — implied assumption "pipeline counterparties exist and can be diligenced"; bears on [[q-astrelia-u1-61-2-of-plan-revenue-has-no-named]] · direction: challenges · materiality: high
- Established from: [[c-astrelia-001]] (asserted: ~61.2%, 14 of 21 lines unnamed; computation not shown), [[c-astrelia-005]] (asserted deal-team belief: base case not yet supported for the same reason)
- With no named counterparty there is no entity to check for creditworthiness, sanctions/export-control exposure, or contract terms (assignment, change-of-control, termination). Both supporting claims are `asserted` by the same deal team and the 61.2% computation is not shown; note this is a *distinct* measure from the 77.4% pipeline-tranche share in F3 ([[c-astrelia-029]] states so explicitly) — the two do not contradict.
- Missing evidence that would settle it: the pipeline register with counterparties named under the executed NDA ([[c-astrelia-009]]), or letters of intent / framework agreements evidencing that the unnamed lines correspond to real entities.

## Open per this workstream
- No question carries `target-workstream: legal` and no assumptions exist; this run could not tie findings to first-class assumption objects. Opening a legal question set and instantiating assumptions is prerequisite to staleness tracking.
- The thesis anchors — ESA qualification, "zero critical-anomaly deliveries across 14 programs", and the €1.3bn METEOR programme (22 satellites) — have **zero claims bearing on them**: no programme award, prime/subcontract, or qualification certificate is evidenced anywhere in the vault. The thesis's central legal objects are entirely unexamined.
- No claims exist on corporate structure, cap table, ownership (the Renna family's role per [[q-astrelia-process]] claims is relational, not documented), IP ownership/registrations, litigation, employment, or regulatory posture — including export-control/dual-use exposure, which the plan's Defense segment ([[c-astrelia-026]]) makes unavoidable for a European space-tech target.
- The NDA's terms (F1) are unexamined; whether they constrain Meridian's outreach to pipeline counterparties or use of materials is unknown.
