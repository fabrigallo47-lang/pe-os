---
type: workstream-output
id: wso-astrelia-commercial_market-001
deal: "[[astrelia]]"
workstream: commercial_market
tied-to: []
uses: ["[[c-astrelia-001]]", "[[c-astrelia-005]]", "[[c-astrelia-017]]", "[[c-astrelia-018]]", "[[c-astrelia-023]]", "[[c-astrelia-026]]", "[[c-astrelia-027]]", "[[c-astrelia-028]]", "[[c-astrelia-029]]"]
stale: false
supersedes: null
written-by: workstream-runner
produced: 2026-07-15
---

# Commercial / Market — findings

> **Note on tied-to:** `assumptions/` is empty for this deal — no `a-astrelia-*` object exists, so `tied-to` is empty and no staleness edge can attach to these findings. Each finding instead names the *implied* plan assumption it bears on and the open question it serves ([[q-astrelia-commercial]], [[q-astrelia-u1-61-2-of-plan-revenue-has-no-named]], [[q-astrelia-market]]). Making those assumptions first-class remains the first open item, as flagged by [[wso-astrelia-financial_qoe-001]].

## F1 — The revenue plan is predominantly uncontracted: two independent measures put the unsecured share of cumulative FY25–30E plan revenue between 61.2% and 77.4%
- Tied to: *(no assumption on file)* — implied assumption "plan revenue is substantially secured by named counterparties"; bears on [[q-astrelia-u1-61-2-of-plan-revenue-has-no-named]] and [[q-astrelia-commercial]] · direction: challenges · materiality: high
- Established from: [[c-astrelia-001]] (asserted: ~61.2% of cumulative plan revenue in unnamed "Others" lines, 14 of 21 pipeline lines opaque — computation not shown), [[c-astrelia-029]] (derived, inspectable arithmetic: ~77.4% of cumulative FY25–30E revenue sits in the pipeline tranche, €1,859.46m of €2,403.71m), [[c-astrelia-026]], [[c-astrelia-018]], [[c-astrelia-005]] (asserted: the deal team's own recorded belief that the base case is not yet supported)
- The two percentages measure different things — unnamed counterparties (deal-team figure, working not shown) vs the pipeline tranche (derived from management's own segment arrays, working shown) — and cannot be reconciled from the claims present, but both point the same direction. Weighing epistemic types, the derived 77.4% is the stronger figure, and it is *larger* than the headline risk the deal team quoted.
- Missing evidence that would settle it: the contract-by-contract pipeline list with counterparty names, contract status, and probability weighting per line — enough to rebuild both the 61.2% and the tranche split from primary detail.

## F2 — The terminal year the growth case rests on is almost entirely pipeline: ~92.3% of FY30E plan revenue is neither backlog nor high-probability, and backlog is zero in every segment by FY30E
- Tied to: *(no assumption on file)* — implied assumption "the FY30E revenue base (€996.76m) is anchored by contracted or near-contracted work"; bears on [[q-astrelia-commercial]] · direction: challenges · materiality: high
- Established from: [[c-astrelia-028]] (derived: €919.55m of €996.76m FY30E revenue in the pipeline tranche = ~92.3%), [[c-astrelia-026]] (asserted: segment tranche arrays — every segment's backlog is 0 in FY30E), [[c-astrelia-017]]
- Concentration compounds the risk: within the FY30E pipeline, Earth Observation alone is €480m (~48% of the headline year) and Defense €288.75m — two uncontracted bets carry the terminal year. Note also that the thesis names the €1.3bn METEOR programme (22 satellites) as the growth anchor, yet no claim in the vault mentions METEOR; nothing extracted so far connects any pipeline line to it.
- Missing evidence that would settle it: the pipeline detail behind the FY30E Earth Observation and Defense tranches — programme names (METEOR or otherwise), tender stage, award probability, and expected contract dates.

## F3 — The commercial plan is contested within its own artifact: FY30E segment tranches sum to €922.93m against the €996.76m P&L revenue line, a €73.83m gap
- Tied to: *(no assumption on file)* — implied assumption "the business plan is internally consistent"; bears on [[q-astrelia-commercial]] · direction: challenges · materiality: high
- Established from: [[c-astrelia-027]] (derived, inspectable arithmetic), [[c-astrelia-026]], [[c-astrelia-017]]
- This finding is contested by construction: [[c-astrelia-027]] (derived, working shown over management's own tranche figures) contradicts [[c-astrelia-017]] (asserted headline, working not shown). This run does not adjudicate which is right — it records that contract-by-contract verification of the plan cannot even start from a segment detail that fails to rebuild the headline it is supposed to decompose. The same gap is flagged from the QoE side in [[wso-astrelia-financial_qoe-001]] F1.
- Missing evidence that would settle it: the full financial model showing the bridge from segment tranches to the P&L revenue line — what, if anything, fills the €73.83m.

## F4 — One narrow point of internal consistency: the Base Case's stated 16× growth multiple does reconcile with the P&L revenue line
- Tied to: *(no assumption on file)* — implied assumption "scenario headlines reflect the underlying P&L"; bears on [[q-astrelia-commercial]] · direction: supports · materiality: low
- Established from: [[c-astrelia-023]] (asserted, with the reconciliation shown: 996.76 / 62.06 = 16.1×), [[c-astrelia-018]], [[c-astrelia-017]]
- This establishes only that the scenario *headline* matches the P&L top line — it says nothing about whether either is achievable, and it does not offset F3, where the segment detail beneath that same line fails to reconcile.
- Missing evidence that would settle it: nothing further for the multiple itself; achievability is F1/F2's evidence ask.

## Open per this workstream
- **[[q-astrelia-market]] is entirely unevidenced:** no claim in the vault bears on market size or on the "unicum in the Italian space industry" positioning from the Cassian Partners call ([[c-astrelia-011]] records the call happened, not what was claimed on positioning). Independent market sizing and a competitive map cannot start from the claims present.
- **METEOR is absent from the evidence base:** the thesis's €1.3bn / 22-satellite growth anchor appears in zero claims. Whether any pipeline tranche line corresponds to METEOR is unknown.
- **The 61.2% figure cannot be rebuilt:** [[c-astrelia-001]] shows no working; the 21-line pipeline detail it summarizes is not in the vault.
- **No assumption objects exist** (`assumptions/` empty), so these findings have no staleness edges — `tied-to` cannot be populated until the implied assumptions above are made first-class.
