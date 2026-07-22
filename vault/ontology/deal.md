# Schema: Deal

Not a folder of documents — a view over a question structure plus lifecycle state. The `deal.md` file is the root; agents keep its dashboard section current (machine-written, so it does not violate zero-maintenance).

## Frontmatter

```yaml
---
type: deal
id: <deal-slug>
company: "[[<company>]]"
state: S0_INTAKE   # backbone state machine: S0_INTAKE … S13_CLOSED_ARCHIVE | SX_TERMINATED_STALLED_DECLINED
                   # DERIVED, never hand-set: resolved from events, exposure, and unresolved
                   # blockers per the priority rules in sources/workflow-backbone-v1 (spec §4).
                   # Agents update this field only as the output of running the resolution rule.
lead: "[[<person>]]"
thesis: "One-sentence investment thesis"
opened: 2026-07-10
written-by: human   # created at deal open — the one 20-minute structured input
---
```

## Body

```markdown
# <Deal name>

## Thesis
What must be true for this to work — the human states it once at deal open;
the decomposer proposes the question tree from it; the human corrects. That's
the only structured input this deal will ever ask for.

## State of the deal   <!-- agent-maintained -->
(generated: open questions ranked by how much the structure depends on them,
unresolved contradictions, evidence arrived since last session)

## Questions
Links to thesis-level questions (the tree hangs off these):
- [[q-<deal>-...]]

## Decisions
- [[d-<deal>-001]]
```

## Directory layout per deal

```
vault/deals/<deal-slug>/
  deal.md
  questions/    one file per question
  claims/       one file per claim
  decisions/    decision + outcome records, append-only
```
