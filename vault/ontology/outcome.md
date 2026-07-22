# Schema: Outcome

Assumed against realized. The one backward arrow in an otherwise linear process: outcome → decision → the question-types that were accepted as unresolved. Works from the first decision recorded; requires no historical archive.

## Frontmatter

```yaml
---
type: outcome
id: o-<deal>-<nnn>
deal: "[[<deal>]]"
decision: "[[d-<deal>-<nnn>]]"   # the decision this outcome tests
date: 2029-07-10
kind: exit | milestone | falsification | validation
  # milestone/falsification/validation allow outcome capture DURING ownership,
  # not only at exit — an assumption quietly stopping being true is an outcome.
realized: "2.1x MOIC" | "pipeline conversion missed 3 consecutive quarters"
written-by: <agent> | human
---
```

## Body

```markdown
# Outcome: <one line>

## Assumed vs realized
Per load-bearing question of the decision:
- [[q-...]] (was: resolved supported) — held / did not hold: <what actually happened>
- [[q-...]] (was: accepted-unresolved) — the accepted risk materialized / did not: <detail>

## Teaching
Which question-TYPE ([[qt-...]]) this outcome informs, and how. This is the entry
future deals retrieve — not by keyword, by what it bears on.
```
