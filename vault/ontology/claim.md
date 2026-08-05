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
| `asserted` | someone said it | growth rate on slide 14 of the deck |
| `derived` | follows from something; derivation inspectable | growth rate computed in model cell D42 |
| `observed` | it happened and was recorded | customer said "we'd churn if the founder left" on a recorded call |
| `attested` | a third party stands behind it, with consequences if wrong | audited revenue figure |

Strip the type: two identical numbers. Keep it: a hierarchy of trust. It **composes** through `rests-on` — a conclusion is only as strong as the weakest epistemic type in its chain.

## Body

```markdown
One-sentence statement of the claim in plain language.

> Exact quote, formula, or excerpt from the source.
```
