# Schema: Assumption

A proposition the deal *proceeds on* — what must be true, quantified. Assumptions sit between the thesis and the evidence: questions test them, workstream outputs and models rest on them. When an assumption changes, everything that depends on it is stale by definition (PR_022) — that propagation is the point of making assumptions first-class.

## Frontmatter

```yaml
---
type: assumption
id: a-<deal>-<nnn>
deal: "[[<deal>]]"
statement: "NRR stays at or above 115% through the hold"   # what must be true
value: "NRR ≥ 115%"          # the current quantified belief — editing THIS triggers staleness
basis: ["[[c-...]]"]         # claims this belief currently rests on
state: proposed              # proposed | accepted | revised | rejected
version: 1                   # bumped on every value/statement change
proposed-by: proposer | human
proposed: 2026-07-13
---
```

Questions link back via their `tests: ["[[a-...]]"]` field; workstream outputs via `tied-to`. The staleness agent watches `value` — any change flags every dependent object `stale: true` and emits `ANALYTICAL_OBJECT_SUPERSEDED`.

## Body

```markdown
# <statement>

## Why the deal rests on this
## Revision history
- v1 (date): <value> — <rationale>
```
