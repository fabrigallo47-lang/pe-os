# Schema: Role (a "desk")

The orchestration layer between real-life roles and functional agents. A role is **not** an AI copy of a job — it is a standing activation: the events it watches, the functional agents it may invoke, the authority profile it operates under, and the human it serves. Functional agents stay small and auditable; roles bundle them into something a firm recognizes.

Design rule: roles must never own data or questions. All desks read and write the same deal structures — a role is a *lens plus triggers*, so the cross-workstream visibility the org chart destroys is preserved by construction.

## Frontmatter

```yaml
---
type: role
id: role-<slug>
serves: partner | deal-lead | associate | operating-team | ic | counsel   # the HUMAN counterpart
activates-on:                      # events, not requests — "activates to do the work"
  - artifact-arrives
  - question-state-change
  - schedule:weekly
invokes: ["[[agent-extractor]]", "[[agent-contradiction]]"]   # functional agents only
authority-profile: [1, 2, 4, 5]    # policy-table rows this desk may use; superset requires approval
reports: "session digest into deal.md § State of the deal, addressed to `serves`"
written-by: human
---
```

## Body

```markdown
# <Desk name, e.g. "Analyst desk">

## Standing responsibilities
What this desk is accountable for keeping true, continuously.

## Activation → action map
For each event in `activates-on`: which agents run, in what order, and what is produced.

## What it must never do
The explicit negative space (e.g. "never advances a question to resolved without its human").
```

## v1 desks (instances live in `vault/roles/`)

| Desk | Serves | Watches | Invokes |
|---|---|---|---|
| Analyst | associate / deal lead | inbox artifacts | extractor, binder, contradiction |
| Diligence coordinator | deal lead | question-state changes | contradiction, dependency ranking |
| Portfolio desk | operating team | monthly packs, portfolio events | extractor, binder, falsification checks |
| IC secretary | committee | decision moments | recorder (draft), question-tree views |
| Librarian | the firm brain itself | resolved questions, outcomes | retrieval, question-type archive upkeep |
```
