# Anto / Fabri — Start Here — V4 FINAL

## What this is

A fixture-free React frontend projection for the PANTA Live Investment Case. It contains the complete product surface and one adapter boundary; it contains **no named-deal fixture data in production source**.

## Read first

1. `15_TARGET_CONTRACT_MANIFEST.md`
2. `14_KERNEL_ALIGNMENT.md`
3. `02_FRONTEND_BACKEND_CONTRACT.md`
4. `03_NO_ORPHAN_INFORMATION.md`
5. `04_AUTHORITY_AND_POSITIONS.md`
6. `08_INTEGRATION_PLAN_ANTO_FABRI.md`
7. `10_RELEASE_GATES.md`
8. `11_VALIDATION_REPORT.md`

## First command

```bash
npm ci
npm run validate
npm run typecheck
npm run build
```

## Integration law

**Kernel/runtime contracts define meaning and state. The frontend is a projection.**

Existing versioned runtime contracts/conformance tests remain binding until migration. Target semantic design contracts are Universal Investment Kernel 0.1.0 + Relation/Update Contract 0.1.0.

Implement `PantaBackendAdapter`; do not add a second ontology or hard-code deal facts into components.

## Integration order

1. Actor/session/authority
2. listCases/loadCase
3. ledger-driven `loadCase(caseId,{asOf})`
4. canonical objects + target relation vocabulary
5. inspectObject structured facts
6. quantities with perimeter
7. governed commands
8. real bounded propagation
9. artifacts create/sync/diff/version
10. findings/background orchestration

## Hard product constraints

- UI labels are not ontology;
- PANTA never fabricates a HumanPosition;
- CaseReading is system synthesis, never human-attributed;
- decisions arise only from authorized Decision events;
- no orphan visible information;
- no guessed numbers/relations;
- backend never authors Object Lens prose;
- affected does not mean changed;
- room semantics are not to be redesigned during integration.
