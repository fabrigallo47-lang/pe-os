# Schema: Question

The atomic unit of reasoning. A deal is a view over its question tree.

## Frontmatter

```yaml
---
type: question
id: q-<deal>-<slug>            # stable, never renamed
deal: "[[<deal>]]"
parent: "[[q-<deal>-<slug>]]"  # null for thesis-level questions
question-type: "[[qt-<slug>]]" # link into library/ — the reuse mechanism
state: open                    # open | reducing | resolved | accepted-unresolved
resolution: null               # null | supported | refuted | mixed  (set when resolved)
depends-on: []                 # question links: resolving those changes this one's meaning or weight
owner: "[[<person>]]"          # accountable human, not the agent
opened: 2026-07-10
state-changed: 2026-07-10
written-by: human | <agent>
---
```

## State machine

```
open ──> reducing ──> resolved(supported | refuted | mixed)
  │          │
  └──────────┴──────> accepted-unresolved   (requires rationale; only a human sets this)
```

- `open` — no evidence bound yet, or evidence does not move it.
- `reducing` — evidence is accumulating and narrowing the answer.
- `resolved` — evidence supports a conclusion; `resolution` says which way.
- `accepted-unresolved` — a human judged the deal can proceed without resolving this. **The state in which most capital is deployed.** Requires the `## Acceptance rationale` section filled by the human (or drafted by agent, confirmed by human).

Transitions are made by agents except into `accepted-unresolved`, which is human-only (see policy table).

## Body sections

```markdown
# <The question, as a question. "Is the revenue plan real?" — never an activity name.>

## Bearing
Why this matters to the thesis; what changes if it resolves each way.

## Evidence
(maintained by agents: links to claims that bear on this, grouped by direction)
- supports: [[c-...]]
- contradicts: [[c-...]]
- context: [[c-...]]

## Resolution note | Acceptance rationale
(filled at state change; for accepted-unresolved: why this was tolerable, written before the decision)
```
