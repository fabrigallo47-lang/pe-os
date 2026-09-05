# Why extraction degrades on venture-shaped deals

**Status:** diagnosis. Written after running the pipeline over the Silexara corpus
(a synthetic venture case) and comparing against the buyout benchmark.
**Short version:** the claim object can express roughly a tenth of the identity the
domain declares, and the benchmark cannot see this because gold was written
against the same field set.

## The symptom, measured

103 claims extracted across five Silexara documents (founder call, technical
deployment call, IC notes, customer reference, competitor analysis), **with the
venture archetype already selected**:

| | count | share |
|---|---|---|
| extracted | 103 | |
| admitted | 61 | 59% |
| **lost** | **42** | **41%** — every one to the same filter |
| admitted **and** resolvable (not `Other`) | **8** | **8%** |

So roughly **eight percent of venture evidence survives as a usable, resolvable
claim**, and archetype vocabulary selection did not fix it.

`claim_kind` across all 103:

| kind | n |
|---|---|
| CHARACTERISATION | 42 |
| NEGATIVE | 20 |
| QUANTITATIVE | **19** |
| ATTRIBUTION | 11 |
| CONDITION | 7 |
| DEFINITION | 4 |

**Only 18% of venture evidence is quantitative.** 36% of admitted claims carry a
value at all; 5% of the lost ones do.

## The wrong diagnosis: "the vocabulary is buyout-shaped"

True, and insufficient. Widening `METRIC_ENUM` per archetype recovers the claims
that *were* metrics all along. With venture vocabulary active, 87% of admitted
claims are still `Other`, because 82% of the evidence was never going to be a
metric. Vocabulary cannot fix a missing object type.

## The immediate cause: CHARACTERISATION is the residual bucket, and we delete it

All 42 losses came through one filter. The model has six `claim_kind` values, and
for a sentence like *"the current deployment state is installed and streaming with
no customer notifications, validation pending"* none of them fit — so it falls
back to CHARACTERISATION. That is the one kind `validate()` rejects.

Sampling the rejects, they are not the seller's adjectives:

- *"…a separate prototype that drove autonomously on a test field but has no
  deployment"* — a position on the technical ladder (`bench/prototype result` →
  `relevant-environment demonstration`)
- *"Customer views the loss problem as real but not urgent; already has guards and
  cameras; will not redesign"* — buyer urgency, the most consequential finding a
  reference call can produce, and `V_BUYER_URGENCY` is a canonical venture concept
- *"Proof-of-concept requirements in the next three months include range by target
  class, false alarms per day"* — milestone conditions
- *"Silexara's current Identify capability is rated as Partly, with strong
  performance on heavy vehicles"* — a capability assessment

Every one is confirmable or refutable. They are being deleted because they have
nowhere to go, not because they are noise.

**The fix is to add the missing kinds, not to loosen the filter.** Making
CHARACTERISATION non-blocking would admit genuine puffery and break the
abstention behaviour the buyout benchmark checks. Give proof states and
capability assessments a kind that fits — §3.2's `qualitative`, plus an evidence
state — and CHARACTERISATION returns to meaning only "un-checkable adjectives",
where deleting it is correct again.

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
