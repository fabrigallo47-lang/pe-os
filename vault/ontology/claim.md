# Schema: Claim

A single atomic fact extracted from an artifact. One claim = one statement. If a sentence asserts two things, write two claims.

## Frontmatter

```yaml
---
type: claim
id: c-<deal>-<nnn>
epistemic: asserted            # asserted | derived | observed | attested
subject: "FY25 revenue growth" # normalized quantity/topic — contradiction detection groups on this
value: "34%"                   # ONE fact. Never pack multiple metrics into one value.
period: "FY2025A"              # time reference — when the claim was valid (e.g. "FY2025A", "As of 2025-10-27")
perimeter: "Alderstone consolidated revenue"  # economic scope — WHAT entity/definition this covers
bears-on: ["[[q-...]]"]        # questions this bears on. May be empty at extraction; binder fills it.
direction: supports            # supports | contradicts | context  (relative to first bears-on question)

# ── provenance (where this came from) ─────────────────────────────
source:
  artifact: "path/or/url"        # raw path/URL — kept for backward compat
  locator: "slide 14, cell D42"  # slide, cell (Sheet1!D42), timestamp (00:31:12), page, line
  author: "Big4 Advisory LLP"    # free-text who produced/asserted it
  date: 2026-05-01               # when the statement was made (not when extracted)

# ── graph links — these become edges in the index ─────────────────
artifact-id: "[[art-<deal>-<slug>]]"  # link to artifact node (canonical source document)
company: "[[company-id]]"             # entity node for the company being described
author-entity: "[[entity-id]]"        # entity node for who wrote/said it (person or firm)
digital-source: null                  # permanent external URL (VDR permalink, SEC filing URL, etc.)

# ── metric tagging (for numeric claims) ───────────────────────────
metric-category: null  # revenue | ebitda | debt | equity | irr | leverage | multiple |
                       # headcount | margin | growth | cash | capex | working-capital |
                       # customer-concentration | churn | price | volume | null

# ── derivation (required for epistemic: derived) ──────────────────
derivation: null       # inspectable formula chain in plain English
rests-on: []           # wikilinks to claims this derivation consumes

supersedes: null       # link to claim this replaces (never edit; supersede)
part-of: null          # wikilink to parent aggregate claim this micro-claim contributes to
                       # (e.g. "[[c-keystone-076]]" when this is a line-item in that bridge)

# ── temporal audit trail ──────────────────────────────────────────
extracted-by: <agent> | human
extracted: 2026-07-10  # when this claim file was FIRST written — never changes
last-seen: 2026-07-10  # last time any ingestion pass confirmed this (subject+value) is
                       # still current. Updated in-place; never supersedes the claim.
                       # If last-seen << today, no recent document has reconfirmed this fact.
stale: false           # true when a rests-on input has changed and this needs review
---
```

## Temporal invariant

Every claim has two dates:

| Field | Meaning | Changes? |
|---|---|---|
| `extracted` | When the claim file was first written | Never — immutable |
| `last-seen` | Last ingestion pass that confirmed this (subject+value) exists | Updated in-place each time |

A claim with `extracted = last-seen` was first seen exactly once. A claim whose `last-seen` is months behind the latest board pack likely needs human review — the fact may have changed but no agent noticed.

The **graph intake timestamp** lives in `vault/manifest.md` — written by the indexer on every `make index` run.

## Micro-claim hierarchy

When a table or Excel row asserts N facts, write N micro-claims plus one parent aggregate:

```
parent claim  → epistemic: derived, rests-on: [child-1, child-2, ...]
child claim 1 → part-of: [[parent]], metric-category: ebitda, locator: "Sheet1!B5"
child claim 2 → part-of: [[parent]], metric-category: ebitda, locator: "Sheet1!C5"
```

`rests-on` drives the recalculation engine. `part-of` drives display hierarchy — the UI can show "all components of this claim" without traversing the computation graph.

## Epistemic types — the trust hierarchy

| Type | Meaning | Example |
|---|---|---|
| `asserted` | the SELLER or MANAGEMENT claims it without external verification | seller CIM narrative, management forecast |
| `derived` | follows from other stated values; derivation inspectable | concentration ratio computed from customer schedule |
| `observed` | a qualified party directly measured or recorded it | QoE walkthrough of a workpaper; data room files |
| `attested` | a qualified THIRD PARTY formally certifies, underwrites, or decides | QoE firm EBITDA; IC decision; Firm underwriting memo |

**Common mistakes:** IC memo claims are `attested` (not `asserted`). QoE conclusions are `attested`. Seller CIM is `asserted`. Derived concentrations (computed from a schedule) are `derived`.

Strip the type: two identical numbers. Keep it: a hierarchy of trust. It **composes** through `rests-on` — a conclusion is only as strong as the weakest epistemic type in its chain.

## Period and perimeter — the economic scope

`period` and `perimeter` together define **what** a claim measures and **when**. Without them, a 74.0 revenue figure is ambiguous. With them:
- `period: "FY2025A / FY2025E seller presentation"` — the time reference, using the document's own language
- `perimeter: "Alderstone consolidated revenue"` — the economic boundary (entity + definition basis)

Perimeter is the most important disambiguation dimension. Two claims with the same value but different perimeters describe different facts (e.g. EBITDA on billing-account basis vs ultimate-parent basis).

## Body

```markdown
One-sentence statement of the claim in plain language.

> Exact quote, formula, or excerpt from the source.
```
