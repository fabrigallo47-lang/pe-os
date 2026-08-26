# Navigation and Rooms

## Navigation model

V17 has two scales and six lenses.

### Scales

- Fund: portfolio-level allocation of attention.
- Deal: one Live Investment Case.

### Lenses

- Command: orientation, material change and next action;
- Evidence: sources, provenance, support and contradiction;
- Economics: model objects, scenarios and consequences;
- Work: tasks, owners, closure paths and gates;
- Relationships: comments, people, authority and coordination;
- Time: bitemporal state and replay.

A lens changes the projection of the same underlying state. It does not create another copy of the case.

## Persistent navigation

The context rail contains:

- Fund / Deal scale control;
- Deal Command;
- Work;
- What the deal rests on;
- Everything we still do not know;
- Shadow IC;
- Artifacts;
- Registry;
- Replay;
- Scenario Lab;
- Decision and Execution rooms when active;
- command palette shortcut.

## Room contracts

### What the deal rests on

Shows minimal support sets for load-bearing Case Positions. Each member is clickable. Weak, contested and accepted-risk floors are visually distinct. The room answers: "What has to remain true for the case to hold?"

### Everything we still do not know

Shows unknowns ordered by expected decision value, not document order. Every row includes closure path, owner and associated underwriting question. The room answers: "Which missing fact is worth resolving next?"

### Shadow IC

Maintains the strongest case for and against the investment, current strength and recorded dissent. It does not manufacture consensus. The room answers: "What would the best skeptical and supportive IC members say now?"

### Registry

Shows an append-only sequence of source arrival, compiler binding, professional admission, transition, propagation, comment, authority, execution and settlement events. Human and system actions are visibly distinct.

### Scenario Lab

Creates governed hypothetical branches without mutating Current. A scenario has explicit drivers, assumptions, economics and coverage. The user can compare Base, Downside, Upside and Acquisition branches.

### Decision Room

Opens only when an engine output contains a human stop or authority request. One room contains one authority verb, one holder and a bounded set of courses of action.

### Execution Room

Opens only after an attested course requires an external action. It is the final pre-flight surface before a message, offer, approval or system write leaves PANTA.

## Command palette

The command palette navigates to objects rather than folders. V17 includes examples such as:

- What changed since the last review?
- What does the deal rest on?
- Show every unresolved risk accepted by IC.
- Which artifact is stale?
- What should we do next?

In production, search results must be returned by the backend as clickable object references. The frontend does not answer these questions independently.
