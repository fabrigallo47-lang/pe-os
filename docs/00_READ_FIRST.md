# PANTA Frontend V4 FINAL — Kernel-Aligned Closed Loop

## What this package is

The canonical fixture-free frontend integration baseline.

It is one React application, not a set of screenshots. All rooms share one adapter, one Actor/authority context, one Object Lens, one Global Shell, one target kernel projection contract and one action model.

## Hard architectural rule

**UI = structure + behavior. Runtime deal content = backend/compiler/runtime state.**

No named-deal fixture or demo content belongs in production `src/`.

## Authority rule

Read `15_TARGET_CONTRACT_MANIFEST.md` before integration.

Existing versioned runtime contracts/conformance tests remain binding until explicitly migrated. The target design interface is Universal Investment Kernel 0.1.0 + Relation/Update Contract 0.1.0. The frontend is a projection of those contracts; it is never the ontology/source of truth.

## Core rooms

- Deal Home
- Workstream Focus
- Trace
- Simulate
- Review changes
- Resolve
- Formation
- Replay & Decision

## Artifact layer

- Outputs / IC Memo
- Outputs / Model
- Outputs / Decision Pack

## Persistent utilities

- Case switcher
- Add Material
- Sources
- Find in Case
- Universal Object Lens

## V4 closure

V4 reconciles the frontend against the current target kernel/relation handoff and closes the remaining handoff-risk issues:

1. canonical Actor / object / relation vocabulary;
2. separate kernel state axes;
3. HumanPosition never epistemically graded;
4. Workstream/Finding/Quantity explicitly projection-only;
5. bitemporal ledger-event projection and as-of replay;
6. no-orphan workstream lifecycle refs;
7. Object Lens facts/refs from backend, investor language composed in frontend;
8. numeric propagation coverage + explicit survivors;
9. governed commands carry Actor;
10. executable synthetic adapter behavior test ships with the package.

## First command

```bash
npm ci
npm run validate
npm run typecheck
npm run build
```

Then implement `PantaBackendAdapter` without changing room semantics or hard-coding case data.
