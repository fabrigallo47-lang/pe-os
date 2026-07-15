---
type: workstream-output
id: wso-astrelia-financial_qoe-001
deal: "[[astrelia]]"
workstream: financial_qoe
tied-to: []
uses: ["[[c-astrelia-003]]", "[[c-astrelia-004]]", "[[c-astrelia-015]]", "[[c-astrelia-016]]", "[[c-astrelia-017]]", "[[c-astrelia-018]]", "[[c-astrelia-019]]", "[[c-astrelia-020]]", "[[c-astrelia-021]]", "[[c-astrelia-022]]", "[[c-astrelia-024]]", "[[c-astrelia-025]]", "[[c-astrelia-026]]", "[[c-astrelia-027]]", "[[c-astrelia-030]]", "[[c-astrelia-031]]", "[[c-astrelia-032]]"]
stale: false
supersedes: null
written-by: workstream-runner
produced: 2026-07-15
---

# Financial QoE — findings

> **Note on tied-to:** `assumptions/` is empty for this deal — no `a-astrelia-*` object exists, so `tied-to` is empty and no staleness edge can attach to these findings. Each finding instead names the *implied* plan assumption it bears on and the open question it serves ([[q-astrelia-financial]], [[q-astrelia-u3-nebulaos-margins-65-80-assumed-vs]]). Making those assumptions first-class is the first open item below.

## F1 — The plan's FY30E revenue does not reconcile with its own segment detail: tranches sum to €922.93m against €996.76m in the P&L, a €73.83m gap
- Tied to: *(no assumption on file)* — implied assumption "the business plan is internally consistent"; bears on [[q-astrelia-financial]] · direction: challenges · materiality: high
- Established from: [[c-astrelia-027]] (derived, inspectable arithmetic), [[c-astrelia-026]], [[c-astrelia-017]]
- This is a live contradiction inside a single artifact: [[c-astrelia-027]] (derived) contradicts [[c-astrelia-017]] (asserted). The derived claim shows its working over management's own tranche figures; the asserted headline does not. This run does not adjudicate which is right — it records that the plan's terminal-year revenue cannot currently be rebuilt from its own segment detail.
- Missing evidence that would settle it: the full financial model (not the extract) showing the bridge from segment tranches to the P&L revenue line — what, if anything, fills the €73.83m.

## F2 — FY30E EBITDA is contested within the artifact itself: the P&L says €323.94m, the Base Case scenario says €288m at a stated 31% margin, and neither margin figure reconciles
- Tied to: *(no assumption on file)* — implied assumption "FY30E EBITDA ≈ €288–324m at ~31% margin"; bears on [[q-astrelia-financial]] · direction: challenges · materiality: high
- Established from: [[c-astrelia-020]], [[c-astrelia-021]], [[c-astrelia-031]], [[c-astrelia-032]]
- The finding is contested by construction: [[c-astrelia-020]] (P&L, €323.94m) and [[c-astrelia-021]] (Base Case, €288m) are both asserted by the same management/deal-team artifact and differ by €35.94m. On margin, three values circulate: 31% stated ([[c-astrelia-031]]), 28.9% implied by the Base Case's own figures (288/996.76), and 32.5% implied by the P&L ([[c-astrelia-032]], derived with shown arithmetic). All inputs are asserted management figures; no observed or attested claim bears on FY30E EBITDA. Who is right cannot be established from the claims present.
- Missing evidence that would settle it: the model's scenario tab showing which EBITDA line the Base Case actually draws from, and the definition difference (if any) between the P&L EBITDA row and the scenario EBITDA.

## F3 — The margin-recovery path the thesis rests on (trough 17.3% FY26E → 31–32.5% FY30E) is carried by NebulaOS margins of 65–80% for which no customer contract is disclosed
- Tied to: *(no assumption on file)* — implied assumption "NebulaOS earns software-like margins at scale"; bears on [[q-astrelia-u3-nebulaos-margins-65-80-assumed-vs]] and [[q-astrelia-financial]] · direction: challenges · materiality: high
- Established from: [[c-astrelia-030]] (derived: FY26E margin 17.3%, down from 26.1% FY25A), [[c-astrelia-022]], [[c-astrelia-018]], [[c-astrelia-003]] (asserted: 65–80% NebulaOS margin vs 17–25% hardware), [[c-astrelia-004]] (asserted: no disclosed NebulaOS contract)
- The recovery from the FY26E trough to the terminal margin is, per the claims present, an assumption without a single disclosed contract behind it. [[c-astrelia-004]] is asserted by the deal team (absence as of 8 Jul 2025), not observed from a data-room sweep — but nothing in the vault contradicts it.
- Missing evidence that would settle it: any executed or negotiated NebulaOS customer contract with pricing, or unit economics from a comparable deployment, establishing an observed margin for the software line.

## F4 — Every historical financial the thesis quotes (FY25A €62.06m revenue, €16.19m EBITDA, FY24A €38.23m) is an unaudited management-plan figure; no observed or attested financial claim exists for this deal
- Tied to: *(no assumption on file)* — implied assumption "FY25A actuals (€62.1m revenue, ~25% EBITDA margin) are real"; bears on [[q-astrelia-financial]] · direction: challenges · materiality: high
- Established from: [[c-astrelia-015]], [[c-astrelia-016]], [[c-astrelia-019]], [[c-astrelia-018]]
- All three historical anchors are epistemically `asserted` (management plan extract, explicitly flagged unaudited in each claim). Weighing epistemic types, the QoE baseline currently rests on the weakest tier available. Note also the claims imply an FY25A EBITDA margin of 26.1% (16.19/62.06), slightly above the 25% quoted in the deal thesis.
- Missing evidence that would settle it: audited FY24/FY25 statements (or auditor's report), which would convert these to attested claims and let quality-of-earnings work (revenue recognition, add-backs, working capital, cash conversion) actually begin.

## F5 — The plan's own downside still assumes ~10× revenue growth: the Bear Case is €554m revenue / €138m EBITDA at 25% margin by FY30E, so no disclosed scenario tests a non-transformational outcome
- Tied to: *(no assumption on file)* — implied assumption "the scenario range brackets the realistic outcomes"; bears on [[q-astrelia-financial]] · direction: challenges · materiality: medium
- Established from: [[c-astrelia-025]] (Bear: €554m / €138m), [[c-astrelia-021]] (Base: €997m / €288m), [[c-astrelia-024]] (Bull: €1,154m / €381m), [[c-astrelia-016]] (FY25A base of €62.06m)
- All three scenarios are asserted management/deal-team figures. Rebuilding under Meridian's own assumptions (the question's bearing) has no floor case to anchor on: the artifact provides no scenario in which growth is merely strong rather than 10–20×.
- Missing evidence that would settle it: a contracted-only / backlog-plus-high-probability case — which the tranche data in [[c-astrelia-026]] would support constructing — showing revenue and margin if the pipeline tranche does not convert.

## Open per this workstream
- **No assumptions exist.** `assumptions/` is empty, so nothing here has a `tied-to` staleness edge. The implied assumptions named in F1–F5 (plan internal consistency; FY30E EBITDA level; NebulaOS software margins; unaudited actuals being real; scenario range adequacy) should be proposed as first-class `a-astrelia-*` objects so this output can be re-tied and the staleness engine can watch them.
- **No QoE substance is yet possible.** The vault holds plan-level P&L rows and scenarios only — zero claims on revenue recognition policy, EBITDA adjustments/add-backs, one-time items, working-capital normalization, customer-level revenue, or cash conversion. The full financial model, audited statements, and management accounts have not been ingested.
- **The two internal contradictions (F1 revenue gap, F2 EBITDA gap) cannot be resolved from the claims present** — both sides are management-asserted within one artifact; only the underlying model or management Q&A settles them.
- **An independent rebuild (the question's core ask) is not yet performable:** with 92%+ of terminal-year revenue in unnamed pipeline per the companion commercial claims and no cost build-up disclosed, there is no independent basis on which to re-derive the margin path.
