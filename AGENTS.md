# PANTA repository instructions for Codex

## Read first
Before changing code, read:
1. `docs/15_TARGET_CONTRACT_MANIFEST.md`
2. `docs/14_KERNEL_ALIGNMENT.md`
3. `docs/product/00_PRODUCT_DOCTRINE.md`
4. `docs/product/01_ROOM_JOBS.md`
5. `docs/product/02_VISUAL_SYSTEM_AND_UX.md`
6. `docs/product/03_CHANGE_POLICY.md`

`AGENTS.md` is a map, not the encyclopedia. The documents above are the persistent product context.

## Source-of-truth hierarchy
1. Existing versioned runtime contracts and conformance tests remain binding until explicitly migrated.
2. Target semantic contract: `panta.universal_investment_kernel@0.1.0`.
3. Target relation/update contract: `panta.relation_and_update_contract@0.1.0`.
4. `src/types/domain.ts` is a frontend projection contract only; never create a parallel ontology in the UI.
5. Product/UX doctrine in `docs/product/` governs experience and language, but never overrides kernel identity, attribution, lineage, or authority.

## Non-negotiable product rules
- Production `src/` must remain fixture-free and contain no named real-deal data.
- UI = structure + behavior. Runtime case content comes through `PantaBackendAdapter`.
- The ledger/kernel is authoritative. Screens are projections.
- HumanPosition is attributed human judgment. PANTA never fabricates or silently rewrites it.
- CaseReading is system synthesis and is not attributed to a human.
- Every important visible object should be inspectable or explicitly documented as non-interactive.
- No orphan information: visible lifecycle content must resolve to canonical objects/refs.
- Frontend language must sound like an excellent investor, never like ontology or philosophy.
- Never expose engine terms such as bindings, dependents, epistemic, DRIVES, CONDITIONS in ordinary UI copy.
- No dead controls. If backend support is not available, disable the control with a clear reason rather than faking behavior.
- No agent console, `SYSTEM ACTIVE`, chatbot-first UI, generic findings inbox, or task-manager drift unless a future explicit product decision changes this.
- Outputs are live writable projections of the case, not disconnected generated files.
- A visual line exists only when it encodes a real relationship.

## Visual-system rule
Consistency lives in shared shell, typography, materials, controls, Object Lens, provenance, spacing, and motion grammar.
Identity lives in the room interaction.
Do NOT make every room use the same geometry.

## Room mentality
- Deal Home: situational command.
- Workstream Focus: structured reasoning inside one part of the case.
- Trace: evidence inspection.
- Simulate: case sensitivity / propagation.
- Review changes: exceptional human governance over material, ambiguous, or judgment-bearing case changes.
- Resolve: evidence-path / mission design.
- Formation: case assembly.
- Replay & Decision: meaningful ledger replay + question-led accountable commitment.
- Outputs: live artifact authoring, sync, auditability, and exploration.

## Change discipline
For every product change:
1. State the user problem before editing code.
2. Preserve the room's job and authority boundaries.
3. Prefer shared primitives only when the behavior is genuinely shared.
4. Do not introduce case facts into components.
5. Run `npm run check:all` after changes.
6. For material UX changes, update `docs/product/07_DESIGN_DECISIONS.md`.
7. Summarize changed files, user-visible effect, tests run, and any backend dependency.

## Required validation
Run:
`npm run check:all`

This includes production validation, TypeScript, production build, and the synthetic lab build.
