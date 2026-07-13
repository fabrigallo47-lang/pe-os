# Schema: Workstream output

The structured deliverable of one workstream run — findings, each tied to the assumption it bears on. Not a memo: a typed object the staleness engine can reason about. Reopening a workstream creates a successor output; it never edits the old one.

## Frontmatter

```yaml
---
type: workstream-output
id: wso-<deal>-<workstream>-<nnn>
deal: "[[<deal>]]"
workstream: commercial_market      # node from the dependency graph
tied-to: ["[[a-...]]"]             # assumptions the findings bear on — staleness follows these edges
uses: ["[[c-...]]"]                # claims consumed
stale: false                       # set true by the staleness agent when a tied assumption changes
supersedes: null
written-by: workstream-runner
produced: 2026-07-13
---
```

## Body

```markdown
# <Workstream> — findings

## F1 — <one-line finding>
- Tied to: [[a-...]] · direction: supports | challenges · materiality: high | medium | low
- Established from: [[c-...]], [[c-...]]
- Missing evidence that would settle it: <what>

## Open per this workstream
<what this run could not establish>
```
