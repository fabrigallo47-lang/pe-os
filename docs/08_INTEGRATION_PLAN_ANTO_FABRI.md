# Integration Plan — Anto / Fabri — V4 FINAL

## First principle

Do not translate between a “frontend ontology” and the kernel. There is no frontend ontology.

`src/types/domain.ts` is a projection contract over the target kernel. Existing versioned runtime contracts/conformance tests remain binding until explicitly migrated.

## Sequence

1. **Run the package gates**
   ```bash
   npm ci
   npm run validate
   npm run typecheck
   npm run build
   ```

2. **Implement `PantaBackendAdapter` without changing room semantics**
   - `getSession`
   - `listCases`
   - `loadCase`
   - `inspectObject`
   - `searchCase`
   - `runSimulation`
   - `execute`

3. **Ledger / replay**
   `loadCase(caseId,{asOf})` must reduce authoritative ledger state; no pre-baked snapshots.

4. **Canonical objects / relations**
   Emit stable ids for canonical objects and exact target relations:
   `ABOUT, BEARS_ON, SUPPORTS, CHALLENGES, CONTRADICTS, CORROBORATES, DERIVES_FROM, DRIVES, CONDITIONS, RESOLVES, ADOPTS, SUPERSEDES, PRODUCES`.

5. **Inspection**
   Return structured refs/facts only. Frontend composes investor language.

6. **Quantities**
   Populate semantic perimeter before enabling model comparison/simulation.

7. **Human authority**
   Resolve Actor identity and enforce AuthorityPolicy server-side for governed commands.

8. **Propagation**
   Use authoritative relation/execution contracts. Missing executable mapping means stale/review/coverage limit — never a guessed value.

9. **Artifacts**
   Implement create/sync/diff/version behavior over canonical Artifact objects and case basis refs.

10. **Real conformance**
    Run the authoritative runtime relation/kernel conformance suite, including affected-but-held survivors, decision/human stops, replay determinism and artifact write-back.

## What not to do

- do not hard-code deal data into React;
- do not create a translation layer from legacy frontend nouns;
- do not let UI labels become ontology;
- do not let backend generate Object Lens prose;
- do not infer propagation edges from similarity;
- do not let AI create HumanPositions or Decisions;
- do not redesign room semantics during backend wiring.
