# PANTA V4 FINAL — Source Reconciliation

## Final Figma bundle reviewed
The merged export supplied the final Figma source families for:

- `src (7)` — Workstream Focus
- `src (8)` — Trace
- `src (9)` — Simulate
- `src (10)` — Review & Admit
- `src (11)` — Resolve
- `src (12)` — Formation
- `src (13)` — Replay & Decision
- `src (14)` — Outputs

Deal Home was reconciled from the previously archived Deal Home source/reference plus the approved final Deal Home direction.

## Reconciliation method
V4 is deliberately **not** a concatenation of Figma-generated React apps.

The final sources were used to preserve:
- approved information hierarchy;
- room-specific geometry;
- interaction intent;
- visual rhythm;
- approved copy/terminology where it remains generic.

The consolidated frontend then replaces duplicated/generated implementation with:
- one Global Shell;
- one design-token system;
- one domain contract;
- one backend adapter boundary;
- one Object Lens primitive;
- one actor/authority model;
- shared provenance/action grammar;
- room-specific screen components.

## Deliberate product corrections made during reconciliation
The V4 refactor also closes issues that were not safely solvable by simply preserving Figma source:

- Positions are first-class and actually rendered.
- Deal Home exposes independent-evidence quality.
- Object Lens prose is composed by the frontend from structured refs/counts.
- Replay consumes time-aware case state rather than pre-baked historical snapshots.
- governed actions carry an actor.
- workstream lifecycle data uses refs rather than orphan strings.
- state vocabulary is typed.
- coverage is numeric.
- dead controls were removed/wired.
- fixture data is absent from production source.

## Visual-system rule
Consistency is centralized in shell, typography, materials, spacing, Object Lens, actions and truthful provenance.

Room geometry remains intentionally different:
- Deal Home = situational command
- Workstream = structured reasoning
- Trace = inspection
- Simulate = sensitivity / propagation
- Review = judgment
- Resolve = evidence-route design
- Formation = assembly
- Replay/Decision = time + commitment
- Outputs Memo = live document
- Outputs Model = spreadsheet-like instrument
- Decision Pack = decision artifact

This is a refactor to a real product frontend, not a screenshot reproduction exercise.


## Kernel reconciliation

V4 additionally reconciles the consolidated frontend projection against the current target Universal Investment Kernel 0.1.0 and Relation/Update Contract 0.1.0. Existing versioned runtime contracts/conformance tests remain binding until explicit migration. Workstream/Finding/Quantity remain UI projections rather than ontology additions.
