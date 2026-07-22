# Schema: Question-type

The reuse mechanism. An expert call on manufacturing scale-up filed under the deal that paid for it becomes unfindable when that deal dies. Attached to a question-type — *does this ramp hold?* — any future deal raising the same question retrieves it. Not by keyword; by what it bears on.

Question-types are also the Category-2 methodology layer: the 80% shared across firms plus the 20% specific to yours, expressed as decomposition templates.

## Frontmatter

```yaml
---
type: question-type
id: qt-<slug>
domain: revenue | market | team | unit-economics | legal | ops | exit
decomposes-into: ["[[qt-...]]"]   # standard sub-questions the decomposer proposes
written-by: human | <agent>
---
```

## Body

```markdown
# <The question class, e.g. "Is the revenue plan real?">

## What resolves it
Which epistemic types typically settle this class (e.g. observed customer
behavior beats asserted pipeline; attested backlog beats both).

## Evidence archive   <!-- agent-maintained -->
Cross-deal links to evidence and outcomes bearing on this class:
- [[c-...]] (deal X, 2026) — <one line>
- [[o-...]] (deal Y) — the accepted-unresolved risk materialized
```
