# Semantic axis migration — plan

**Status:** proposal, not started. Needs decisions marked **[DECIDE]** before any code moves.
**Source:** `PANTA_DIZIONARIO_ESTRAZIONE_FINALE_V1_0` §3 (assi semantici), §4 (concept registry).
**Companion:** `vault/policy/archetypes/semantic_handoff_v0_2/10_legacy_to_v0_2_mapping.yaml`
already maps *entities* (`NON_BINDING_MIGRATION_AID`). §3 is the missing *field* half.

## What the migration is

Today one enum answers several unrelated questions at once. `epistemic_class` is
simultaneously asking *who said it*, *how sure are they*, *was it certified*, and
*was it computed*. The dictionary splits that into orthogonal axes:

| Legacy field | Target axes |
|---|---|
| `epistemic_class` | `modality` · `attestation_type` · `evidence_origin_role` · `derivation_mode` |
| `claim_kind` | `claim_kind` (reduced) · `polarity` · provenance fields (`stated_by_entity_id`) |
| `direction` | `direction` (SUPPORTIVE/ADVERSE/…) — no longer implies SUPPORTS/CONTRADICTS edges |

The gain is real and specific: today `attested` cannot distinguish "an auditor
certified it" from "the IC decided it", so we invented a fifth class this session
(`institutional_act`) to paper over exactly that collision. Under the target model
that distinction falls out of two independent axes instead of a new enum value.

## Why it can't be done in one commit

Three hard constraints, all measured, not assumed:

1. **The eval scores against the legacy enums.** `semantic_exact_match` compares
   `epistemic_class` and `claim_kind` directly against gold. Changing the emitted
   vocabulary scores 0 on every case until gold is regenerated. Current: 76.2%.
2. **Live consumers hard-code the legacy 4-value list.** `app/server.py` (the
   product server) 422-rejects an unknown class; `tools/extract.py` validates
   against its own copy; `backend/dynamics/runtime/panta_transition_engine.py`
   ranks by `_EPISTEMIC_TIER`. Already true today for `institutional_act` — a
   known, filed gap.
3. **The identity model is a bigger gap than the enums.** Measured: the buyout
   pack declares **63 distinct `required_identity` field names**; the claim schema
   can carry **7**. Concepts routinely require `numerator_definition`,
   `covenant_basis`, `valuation_date`, `cash_flow_dates` — the schema has nowhere
   to put them. Enum-splitting alone leaves that untouched.

Constraint 3 is the one that matters: **this is not an enum rename, it is a claim
object that needs more structure.** Doing (1) and (2) without (3) buys ceremony.

## Phases

**Phase 0 — instrument (small, no behaviour change).**
`unrepresentable_required_identity()` already reports, per concept, which identity
fields the schema cannot express. Run it across a real extraction and publish the
histogram. That converts "the schema is too flat" into a ranked list of the
specific fields worth adding first. Do this before designing anything.

**Phase 1 — additive dual-write.**
Add the new axes as optional fields alongside the legacy enums. Nothing reads them
yet. `validate()` populates both: legacy as today, new axes derived by a single
documented projection function. One place to change, one place to test.

**Phase 2 — projection under test.**
Freeze the legacy↔axis projection as a tested contract, both directions, using
§3.1/§3.2's tables. This is the safety net: as long as legacy can be reconstructed
from the axes, no reader has to move on anyone else's schedule.

**Phase 3 — move readers one at a time.**
`app/server.py`, `tools/extract.py`, the dynamics tier table, the vault ontology
doc. Each flips independently because Phase 2 guarantees both views agree.

**Phase 4 — regenerate gold, then drop legacy.**
Only once readers are moved. Gold regeneration is the point of no return and is
Anto's call, not a side effect of a refactor.

## Decisions needed

- **[DECIDE] `institutional_act`.** We added it this session (CLAUDE.md invariant
  #3, `EPISTEMIC_CLASS_ENUM`, gold in v1/v2/v3). §3.1's table does not list it —
  it predates or omits it. Under the target model an IC decision is
  `modality=DECIDED` + `evidence_origin_role=INVESTOR_TEAM`. Is it a stepping
  stone the migration absorbs, or does it stay? Affects whether to keep
  propagating it to the live consumers now or wait.
- **[DECIDE] Gold regeneration owner and timing.** Phase 4 invalidates every
  fixture's `epistemic_class`/`claim_kind`. Anto owns those fixtures.
- **[BLOCKED] `01_canonical_concepts_registry.csv`.** §4.1's registry record
  includes `aliases[]`; the repo pack has every field except that one. Without it
  only 12 of 69 metric labels resolve to a concept. §4.1 forbids hand-rolling the
  bridge ("il codice non deve mantenere una seconda lista piatta divergente"), so
  this is genuinely blocked on the file, not on effort.
- **[DECIDE] Archetype scope.** Only the buyout pack (40 seeds) is in the repo.
  The dictionary cites venture (49) and growth (53). Migrating the axes without
  those packs means designing against a third of the evidence.

## What this plan is not

It is not a reason to stop improving extraction now. Phases 0–2 are additive and
can run alongside ordinary work. Phase 3 onward should wait for the decisions
above — particularly the registry CSV, since a migration that leaves 57 of 69
metrics unresolvable to a concept has not actually bought the determinism it was
supposed to buy.
