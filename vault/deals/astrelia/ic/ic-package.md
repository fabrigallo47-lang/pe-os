---
type: ic-package
id: ic-package-astrelia
deal: "[[astrelia]]"
version: 1
produced: 2026-07-15
written-by: ic-assembler
state: S0_INTAKE
---

# IC Package — astrelia

_(ic-assembler, 2026-07-15 19:59, v1)_

# IC Package — Project Astrelia
*Assembled by ic-assembler · epistemic only · the human decides · state: S0_INTAKE · 15 Jul 2026 context date; claim dates per graph*

---

## Recommendation-neutral decision basis

**Thesis under test:** Profitable European space tech — €62.1m FY25A revenue (+62% YoY, 25% EBITDA margin), ESA-qualified with zero critical-anomaly deliveries across 14 programs, and the €1.3bn METEOR programme (22 satellites) anchoring the growth case.

**Epistemic weight of the graph (32 claims):**

| Type | Count | What they cover |
|---|---|---|
| attested | 0 | — |
| observed | 9 (c-006–c-014) | Process provenance only: origination via Renna family relationship, NDA execution, Cassian Partners mandate, receipt of Management Presentation (24 Jun 2025) and Business Plan extract (8 Jul 2025) |
| derived | 5 (c-027–c-030, c-032) | Arithmetic on the plan itself: segment-sum vs P&L revenue, pipeline shares, implied margins |
| asserted | 18 (c-001–c-005, c-015–c-026, c-031) | **Every financial fact in the deal** — FY24A/FY25A actuals, the full FY30E trajectory, scenario cases, segment tranches — all from the unaudited management plan extract |

**What the basis actually supports:**
- The strongest (observed) claims establish only that the process happened and what documents Meridian holds. No third-party has verified any number.
- FY24A→FY25A growth in the thesis is internally consistent with the asserted plan: €38.23m → €62.06m (c-015, c-016) is +62.3%. Implied FY25A EBITDA margin is 26.1% (c-019/c-016), versus the thesis's stated 25% — close, but both figures rest on the same unaudited extract.
- **Three thesis anchors have no claims bearing on them at all:** ESA qualification, the zero-critical-anomaly delivery record across 14 programs, and the €1.3bn METEOR programme. As of this package they are thesis assertions without graph support.
- The growth case rests on asserted plan figures whose internal arithmetic does not close (see Contradictions): pipeline tranches account for ~92.3% of FY30E plan revenue (c-028, derived) and ~77.4% of cumulative FY25–30E revenue (c-029, derived), of which ~61.2% has no named counterparty (c-001, asserted).
- The deal team's own recorded position: base case not yet supported (c-005, asserted, 8 Jul 2025).
- Process pressure: Meridian is registered as a serious potential investor and **owes a valuation indication that remains open** (c-014, observed) while q-astrelia-valuation is itself open.

---

## Resolved questions (with strongest epistemic chain)

**None.** All 9 questions are open, including all 5 CRITICAL:

- q-astrelia-commercial [CRITICAL] — open. Strongest bearing evidence is asserted (c-001, c-004, c-005) plus derived pipeline-concentration arithmetic (c-028, c-029). No observed or attested claim bears on revenue reality.
- q-astrelia-financial [CRITICAL] — open. All inputs asserted from the unaudited extract; the only independent work is derived arithmetic that exposes inconsistencies (c-027, c-030, c-032).
- q-astrelia-tech [CRITICAL] — open. Sole bearing claim is asserted (c-002: 14 historical units).
- q-astrelia-u1 / u2 / u3 [CRITICAL] — open; each rests on a single asserted claim (c-001, c-002, c-003 respectively).
- q-astrelia-market, q-astrelia-process, q-astrelia-valuation — open; process facts (observed c-006–c-014) bear on q-astrelia-process but do not resolve it.

No question has a chain stronger than *asserted* on its substance. The only observed chain in the graph (c-006→c-014) establishes process provenance, not any thesis fact.

---

## Accepted-unresolved ledger (what proceeding accepts; exposure)

**Ledger is empty.** No `accepted-unresolved` transitions exist (these are human-only, policy rows 7–8), and no prior decisions exist to have created them.

Exposure if a decision were taken from the current basis — stated for visibility, not as a recommendation:
- Proceeding now would implicitly accept **all 5 CRITICAL questions unresolved**, including the three unknowns the deal team itself flagged: 61.2% unnamed-counterparty plan revenue (q-u1), 14 delivered units vs serial-production assumptions (q-u2), and 65–80% assumed NebulaOS margins with **zero disclosed NebulaOS customer contracts** (q-u3, c-003, c-004).
- It would also accept a decision basis containing **zero attested and zero observed claims on any financial or technical fact**, and three unreconciled internal contradictions in the plan itself.
- No exposure quantification is possible: no assumptions objects exist, so no staleness or exposure edges can be computed (see all three workstream output notes).

---

## Unresolved contradictions (verbatim from the graph)

```
FY30E plan EBITDA: c-astrelia-020 [asserted]=€323.94m (P&L table) | c-astrelia-021 [asserted]=€288m at 31% margin (Base Case scenario)
FY30E plan EBITDA margin: c-astrelia-031 [asserted]=31% (Base Case, stated) | c-astrelia-032 [derived]=32.5% implied by the P&L table (323.94 / 996.76)
FY30E plan revenue: c-astrelia-017 [asserted]=€996.76m (P&L table) | c-astrelia-027 [derived]=€922.93m implied by summing FY30E segment tranches — €73.83m below the €996.76m P&L revenue line
```

All three concern the same subject area — the FY30E plan year — and all three set the company's own stated figures against either another company-stated figure or arithmetic derived from its own tables. Per invariant 8, this package reports what does not reconcile; it does not adjudicate which figure is right. Resolution path runs through q-astrelia-financial (management/Cassian to show their working on the €73.83m revenue gap and the €35.94m EBITDA gap between P&L table and Base Case).

---

## Assumptions table (id | value | version | stale)

| id | value | version | stale |
|---|---|---|---|
| *(none)* | — | — | — |

`assumptions/` is empty for this deal. All three workstream outputs (commercial_market, financial_qoe, legal) flag the same structural gap: no `a-astrelia-*` object exists, so `tied-to` is empty and **no staleness edge can attach to any finding**. The plan assumptions the findings implicitly bear on (unnamed-counterparty conversion, serial-production ramp, NebulaOS margin structure) exist only as prose inside findings, not as tracked objects. Until they are instantiated, staleness tracking for this deal is inoperative.

---

## IC Shadowing (likely objections inferred from question types + past decisions)

No past decision records exist to pattern-match against; the following is inferred from the question-type structure and the claim graph.

1. **"Is any of this audited?"** — Every financial claim, including the FY24A/FY25A "actuals" in the thesis, traces to a single unaudited management plan extract (c-015–c-026). Expect the IC to ask what, if anything, has been independently verified. Currently: nothing.
2. **"The plan doesn't add up internally — why should we trust its trajectory?"** — Three contradictions inside management's own document (revenue line vs segment sum; two different FY30E EBITDA figures; two different margins). An IC will likely treat internal inconsistency as a credibility signal on the whole extract, not just the FY30E year.
3. **"92% of the FY30 number is pipeline, and 61% of the pipeline has no name on it."** — c-028/c-029 (derived) plus c-001 (asserted). This is the deal, per q-astrelia-commercial's own framing. Expect demand for counterparty-level evidence before any resolution.
4. **"Where is METEOR in the evidence?"** — The thesis's €1.3bn anchor programme, the ESA qualification, and the zero-critical-anomaly record appear in no claim. Expect the objection that the thesis's strongest selling points are currently unevidenced.
5. **"Software margins with no software customers."** — NebulaOS at 65–80% assumed margin (c-003) against 17–25% hardware margins, with no disclosed NebulaOS contracts (c-004). Expect a challenge to any valuation that capitalizes the mix-shift.
6. **"14 units ever, serial production assumed."** — c-002. Expect operational-DD objections on capacity, supply chain, and hiring before the ramp is credited.
7. **"Your own team says the base case isn't supported."** — c-005 is on the record (8 Jul 2025). Expect the IC to ask what has changed since.
8. **"Why are we being asked for a valuation indication before QoE?"** — c-014: an indication is owed to Cassian Partners while q-astrelia-financial and q-astrelia-valuation are open. Expect a process-discipline objection about anchoring a number on an unaudited, internally inconsistent extract, and a related-party question on the Renna-family origination channel (c-006, c-007).

---

## Footer: changed / opened since previous package

**First IC package for this deal — no previous package exists; everything below is new.**

- **Opened:** 9 questions (5 CRITICAL), all open: commercial, financial, market, process, tech, u1-unnamed-counterparty, u2-serial-production, u3-nebulaos-margins, valuation.
- **Added:** 32 claims — 9 observed (process provenance, c-006–c-014), 5 derived (plan arithmetic, c-027–c-030 + c-032), 18 asserted (plan financials and deal-team flags), 0 attested.
- **Opened contradictions:** 3, all on FY30E plan figures, all unresolved.
- **Changed:** nothing — no resolutions, no accepted-unresolved transitions, no decisions, no assumptions instantiated.
- **State:** S0_INTAKE, unchanged.
