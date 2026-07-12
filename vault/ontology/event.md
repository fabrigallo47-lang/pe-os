# Schema: Event (WorkflowEvent)

The only mechanism by which anything affects the flow. Immutable, append-only: an event is never edited or deleted; a wrong event is superseded by a correcting event. State resolution and agent activation read events — never file recency, never labels.

## Frontmatter

```yaml
---
type: event
id: ev-<deal>-<nnn>
deal: "[[<deal>]]"          # omit for firm-level events
kind: ARTIFACT_ARRIVED       # controlled enum: transition triggers from
                             # sources/workflow-backbone-v1/state_transitions_v1.csv
                             # (DEAL_REGISTERED, ACCESS_GRANTED, CASE_MATERIAL_INDEXED,
                             #  SCREENING_APPROVED, IC_APPROVED, DOCUMENTS_SIGNED, ...)
                             # plus perception kinds: ARTIFACT_ARRIVED, QUESTION_STATE_CHANGED,
                             # CONTRADICTION_FLAGGED, DECISION_RECORDED, SIGNAL_DETECTED
actor: <agent> | "[[<person>]]"
at: 2026-07-12T18:53:00
relates-to: ["[[c-...]]", "[[q-...]]", "[[d-...]]"]
supersedes: null             # correcting a wrong event; never edit
---
```

## Body

One line: what occurred, in plain language. Optional payload details below.

## Rules

- Written under policy row 4 (autonomous, audited) — but events that *are* authority decisions (IC_APPROVED, RISK_ACCEPTED) may only be emitted by a human or by the recorder desk transcribing one.
- The deal's primary state is **derived** from events via the resolution rule (spec §4, priority order, conflict rule). No file, agent, or human sets state directly.
- v1 has no daemon: skills emit events as files and evaluate guards when run. The semantics are identical; only the scheduling is manual.
