# PANTA Frontend V4 — Release Gates

A handoff is releasable only if all gates below pass.

## Fixture / data separation
- [ ] production `src/` contains no named-deal/demo fixture or fallback data
- [ ] synthetic test data exists only outside production `src/`

## Kernel alignment
- [ ] target contract authority order is explicit
- [ ] Workstream/Finding/Quantity are projection types, not ontology
- [ ] HumanPosition has no system epistemic status
- [ ] exact 13 target relation names only
- [ ] separate canonical state axes are represented
- [ ] Actor, not Person, is the authority identity
- [ ] ledger event projection is bitemporal/attributed

## No-orphan / auditability
- [ ] workstream owner/change/work/open items are refs
- [ ] Object Lens backend payload contains refs/facts, not explanatory prose
- [ ] Deal Home exposes independent-evidence quality
- [ ] Positions render contextually
- [ ] important controls open real frontend paths

## Closed-loop frontend wiring
- [ ] Replay invokes `loadCase(...,{asOf})`
- [ ] Test without this uses temporary inspection only
- [ ] Open source opens Sources drawer
- [ ] simulation returns numeric coverage + explicit survivors
- [ ] governed mutations carry actorId
- [ ] artifact sync is explicit
- [ ] no visible primary control is dead

## Reproducible tests shipped
- [ ] fixture-free scan passes
- [ ] syntax check passes
- [ ] contract check passes
- [ ] kernel-alignment static check passes
- [ ] dead-control check passes
- [ ] closed-loop static wiring check passes
- [ ] synthetic adapter behavior test passes
- [ ] frontend projection behavior test passes
- [ ] TypeScript typecheck passes
- [ ] Vite production build passes

## Backend integration gates (not replaceable by frontend tests)
- [ ] authoritative runtime/kernel conformance suite passes
- [ ] same ledger/configuration replay is deterministic
- [ ] no propagation over absent/unadmitted relation
- [ ] affected-but-held objects remain explicit
- [ ] Decisions/HumanPositions cannot be machine-created
- [ ] missing executable mapping yields stale/review/coverage limitation
