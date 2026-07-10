---
type: policy
id: policy-table
version: 1
written-by: human
---

# Policy table — operation → authority

**The boundary is a table, not a judgement, which is why it can be audited.** Written before anything runs. Every agent action must map to a row; if an operation is not listed, its authority is `approval`.

| # | Operation | Authority | Audit trail |
|---|---|---|---|
| 1 | Read vault content | autonomous | — |
| 2 | Read local artifacts (inbox, linked paths) | autonomous | — |
| 3 | Send artifact/vault content to model API for extraction or reasoning | autonomous **within pilot scope** (see note) | session log |
| 4 | Write claims, question-state transitions (except → accepted-unresolved), evidence bindings, dashboard sections | autonomous | git commit, `written-by` |
| 5 | Flag a contradiction | autonomous | git commit |
| 6 | Draft a decision record from question states | autonomous (draft only) | git commit |
| 7 | Set a question to `accepted-unresolved` | **human only** | git commit, human-authored rationale |
| 8 | Author/confirm a decision record | **human only** | git commit |
| 9 | Query a connected external system (data providers, web) | approval (none connected in v1) | session log |
| 10 | Contact an external party (email, message — anyone) | **approval, always** | session log |
| 11 | Commit the firm's position in any form | **never** — belongs to whoever bears the consequence | — |
| 12 | Edit or delete a decision record, outcome, or audit entry | **forbidden** — append-only; supersede instead | — |

**Note on row 3 (the confidentiality boundary):** in the pilot, model API calls carry deal content off-machine to the inference provider. This is a listed operation precisely so it is a *decision*, not a default. Before any deployment on a firm's real VDR content: zero-data-retention agreement or private endpoint, and this row's scope re-authorized.

An agent may notice three sources disagree (row 5). It may not email the counterparty to find out which is right (row 10). The first is perception. The second is the firm speaking.
