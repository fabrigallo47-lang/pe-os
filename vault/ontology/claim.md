# Schema: Claim

A statement extracted from an artifact, with an epistemic type and provenance. The unit of meaning — the artifact is just its container.

## Frontmatter

```yaml
---
type: claim
id: c-<deal>-<nnn>
epistemic: asserted            # asserted | derived | observed | attested
subject: "FY25 revenue growth" # normalized quantity/topic — contradiction detection groups on this
value: "34%"                   # the content of the claim, atomic if possible
bears-on: ["[[q-...]]"]        # questions this bears on. NEVER a deal. May be empty at extraction; binder fills it.
direction: supports            # supports | contradicts | context  (relative to first bears-on question)
source:
  artifact: "path/or/url"      # artifact stays where it is
  locator: "slide 14"          # slide, cell (Sheet1!D42), timestamp (00:31:12), page
  author: "management"         # who asserted/produced it
  date: 2026-05-01             # when the statement was made (not extracted)
derivation: null               # REQUIRED if epistemic: derived — the inspectable chain
                               # e.g. "D42 = D41/D40-1; D41 ← 'Bookings' pivot; inputs asserted by mgmt"
rests-on: []                   # claims this derivation consumes — the composition chain.
                               # derived-over-asserted = assertion with arithmetic on top; the system sees this.
supersedes: null               # link to claim this replaces (never edit claims; supersede them)
extracted-by: <agent> | human
extracted: 2026-07-10
---
```

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
