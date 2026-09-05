# Why extraction degrades on venture-shaped deals

**Status:** diagnosis. Written after running the pipeline over the Silexara corpus
(a synthetic venture case) and comparing against the buyout benchmark.
**Short version:** the claim object can express roughly a tenth of the identity the
domain declares, and the benchmark cannot see this because gold was written
against the same field set.

## The symptom

Two documents, same pipeline, buyout vocabulary:

| document | raw claims | admitted | resolvable (not `Other`) |
|---|---|---|---|
| SRC-02 founder call | 27 | 9 | ~1 |
| SRC-09 IC notes | 7 | 1 | ~0 |

Selecting the venture archetype (commit `Select the extraction vocabulary by
archetype`) roughly doubles admission — 9→12 and 1→6, with resolvable claims
going ~1→~8. Real, but it treats a third of the problem.

## The wrong diagnosis: "the vocabulary is buyout-shaped"

True, and insufficient. Widening `METRIC_ENUM` per archetype recovers the claims
that *were* metrics all along. It does nothing for the majority of venture
evidence, which was never going to be a metric.

## The real diagnosis: one identity axis where the domain has many

The archetype packs declare, per concept, the identity a claim must carry. Counted:

| archetype | concepts | distinct `required_identity` names | of which definition/state-type |
|---|---|---|---|
| buyout | 40 | **63** | 25 |
| venture | 49 | **122** | 23 |
| growth | 53 | **103** | 37 |

The claim schema can carry **7**: `entity`, `period`, `scenario`, `perimeter`,
`basis`, `scope`, `unit`. Everything else has nowhere to go.

This is not a venture problem. Look at what buyout alone asks for:

- `EBITDA_REPORTED` → `accounting_basis`
- `EBITDA_ADJUSTED_PROPOSED` → `adjustment_basis`
- `EBITDA_NORMALIZED_ACCEPTED` → `accepted_basis`
- `CASH_CONVERSION` → `numerator_definition` + `denominator_definition`
- `NET_DEBT` → `debt_cash_definition`
- `CAPEX_MAINTENANCE` → `classification_basis`

We collapse all of these into one `basis` field with six values
(`SellerView`/`QoEView`/`FirmView`/`CovenantView`/`ReportedView`/`unspecified`).
But that field answers **whose view it is**, not **which definition was used** —
and in QoE work two EBITDA figures usually differ because of add-back definitions,
not because of whose opinion they are. Today that distinction survives only as
free text inside `perimeter`, untyped and uncomparable.

## The specific missing axis: evidence state

Dictionary §9 types evidence as ordered progressions rather than numbers
("*queste sono categorie/progressioni di evidenza, non universal numeric scores*"):

- **venture, commercial:** stated interest → design participation → unpaid test →
  paid pilot → production deployment → repeat purchase → expansion → repeatable cohort
- **venture, technical:** concept → bench/prototype → independent test →
  relevant-environment demonstration → reliable production use → scaled delivery
- **growth:** reported growth → reconciled economic unit → durable repeat → …
- **buyout (§9.4, explicitly *not* one ladder):** `commercial_commitment_state`
  (lead·qualified·pipeline·contracted·backlog·delivered·recognized·collected) ·
  `recurrence_state` · `recognition_state` · `evidence_attestation`

A proof state has no `value`. "The first paid permanent site goes into the ground
in May" is a position on the commercial ladder; "classification is not solved for
quiet activity" is a position on the technical one. Forced through
`metric`+`value`+`unit`, each becomes either a null-valued claim or free text
under `Other`, and in both cases it can no longer be **ordered** — which is the
one operation that makes a ladder useful.

§9.4 matters most here: buyout needs these axes too. "Is this revenue contracted,
delivered, recognized or collected?" is the central QoE question and the schema
cannot state it. Buyout hides the gap because its evidence *looks* numeric;
venture exposes it because its evidence is mostly state.

## Why the benchmark cannot see any of this

The semantic benchmark's gold claims carry exactly our fields — `entity`,
`metric`, `measurement`, `period_canonical`, `scope`, `basis`, `scenario`,
`bound`, `epistemic_class`, `claim_kind`. Gold was authored against the same
object model the extractor implements.

So 76.2% measures **fidelity to our own model**, not coverage of the domain. A
schema that cannot express `recognition_state` loses no points for it, because
gold never asks. Silexara is the first corpus in this session that was not
co-designed with the schema, which is precisely why it exposed the gap — and why
a higher benchmark score would not have predicted it.

## What generalizes

1. **Archetype-selected vocabulary** (done) helps every archetype and is not
   Silexara-specific. It recovers metrics only.
2. **A typed evidence-state axis** is the next structural fix, and it is
   cross-archetype: venture/growth get the progression ladders, buyout gets the
   four separate states from §9.4. The packs already carry the vocabulary
   (`proof_ladder`), so this is parameterization, not invention — the same shape
   as `metric_vocabulary()`.
3. **Split `basis`** into whose-view versus which-definition. The pack names the
   definitional axes per concept (`accounting_basis`, `adjustment_basis`,
   `numerator_definition`); today they are collapsed into one six-value enum.
4. **Do not measure any of this on the current benchmark.** It cannot move the
   score by construction. Measure it on Silexara, or on the blind spec
   (`09_blind_benchmark_spec_v0_1.yaml`), whose gold was authored independently.

## Sequencing note

This supersedes the ordering in `06-semantic-axis-migration-plan.md`. Splitting
`epistemic_class` into modality/attestation axes is worth doing, but it refines
labels on claims we already keep. The evidence-state and definitional-basis axes
determine whether the claim exists at all. Object and identity model first;
epistemic axes second.
