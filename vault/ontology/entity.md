# Schema: Entity (company | person)

Real-world objects the graph hangs on. Deliberately thin in v1 — the relationship graph is *observed* (from artifacts and claims), not maintained. A graph you maintain is wrong by the end of the quarter; a graph that is observed is correct by construction.

## Frontmatter

```yaml
---
type: company    # or: person
id: <slug>
aliases: []      # for entity resolution during extraction
role: target | portfolio | competitor | customer | expert | counterparty   # company
# role: partner | associate | founder | management | expert | lp           # person
written-by: <agent> | human
---
```

## Body

Free prose. Agents append observations with claim links; nothing here is a field a human must maintain.
