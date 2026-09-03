# V3.2 → V4 FINAL Reconciliation

V4 starts from the externally reconciled V3.2 package and applies one additional contract-closure pass against the current target kernel/relation handoff.

## Additional fixes made in V4

1. **Exact latest 13-relation vocabulary**
   - added/kept: ABOUT, BEARS_ON, SUPPORTS, CHALLENGES, CONTRADICTS, CORROBORATES, DERIVES_FROM, DRIVES, CONDITIONS, RESOLVES, ADOPTS, SUPERSEDES, PRODUCES
   - removed old alternate relation names from the frontend contract

2. **Actor identity**
   - canonical Actor ids are used throughout governed UI commands and attribution

3. **Separate target state axes**
   - institutional / epistemic / freshness / question / work / condition / decision-link are distinct

4. **Independent support is reading-relative**
   - independence is not a global boolean on Claim
   - `CaseReading.independentSupportObjectIds` carries the UI projection needed for Deal Home / Trace
   - this prevents the same Claim from being treated as absolutely “independent” outside the proposition/support route it is supporting

5. **Relation endpoints are typed**
   - Relation projection includes canonical source/target object type as well as ids

6. **Connected auditability covers more canonical object families**
   - snapshot contract can address MetricDefinition, MetricObservation, Assumption, Risk, ModelNode and Outcome directly
   - Workstream/Finding/Quantity remain explicit UI projections

7. **Decision conditions are refs once recorded**
   - canonical Decision projection stores `conditionIds`
   - free text exists only as human command input before backend canonicalization

8. **Claim audit identity strengthened**
   - Claim projection requires SourceVersion + locator + normalized statement

9. **Testing is reproducible and layered**
   - static fixture/contract/kernel/dead-control/wiring gates
   - synthetic adapter behavior test
   - frontend projection behavior test using actual selector code
   - authoritative backend conformance remains a separate mandatory gate

## No visual/product redesign

This pass intentionally does not redesign the approved room architecture or visual system. It removes semantic ambiguity at the frontend/backend boundary so integration does not create a second ontology by accident.
