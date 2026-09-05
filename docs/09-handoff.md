# Handoff — semantic extraction, model bindings, and the precision question

**Living document.** Updated as work proceeds; the "Open right now" section is the
only part that goes stale by design.

Session branch: `dev` · baseline for attribution: `abe3e4e`

**Extraction now runs on GLM 5.2 via OpenRouter** (`PEOS_LLM_PROVIDER=openrouter`
→ `z-ai/glm-5.2`), with `zdr: true` and `data_collection: "deny"` sent on every
call. Anthropic/Haiku remains the fallback provider. Resolve the model through
`llm_provider.configured_model()` — never hardcode one.

---

## 1. What this session set out to do

Raise semantic-extraction quality, then work the V1 Linear tasks. The benchmark
moved **53.1% → 77.2%**. The decisive method was measuring per-field and
per-metric loss rather than guessing at prompts — every improvement below came
from a measurement first, and two planned improvements were *cancelled* by
measurement, which is the more valuable outcome.

---

## 2. Research findings that changed the plan

### 2.1 Over-extraction is not repetition (this cancelled a planned build)

The blind Silexara run produced **259 claims against a 76-claim answer key** —
3.4×. The obvious repair is a uniqueness filter, and the literature supplies one:
**CORE** ([arXiv:2407.03572](https://arxiv.org/abs/2407.03572)) filters sub-claims
"according to their uniqueness and informativeness", because decompose-then-verify
precision metrics "can be manipulated by adding obvious or repetitive subclaims".

Measured before building it (`tools/claim_redundancy.py`):

| corpus | claims | exact dupes | subsumed | near pairs |
|---|---|---|---|---|
| blind_silexara | 259 | 4 (1.5%) | 0 | 2 |
| blind_keystone | 26 | 0 | 0 | 9 |
| K-IC raw cache | 1252 | 6 (0.5%) | 20 | 187 |

A uniqueness filter would have removed **about four claims** and left the 3.4×
intact. The gap is **granularity, not repetition** — and that is precisely the
confound the same literature names: claims extracted more atomically *"may not
match reference claims simply because the reference set uses a less granular
approach"* ([Ragas, factual correctness](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/factual_correctness/)).

**Consequence: "attack precision" is the wrong next project.** Building the filter
would have deleted correct, distinct facts to improve a number. The real next step
is a **cross-schema matcher** (gold's `subject/predicate/value` ↔ our
`entity/metric/measurement/value`), without which no precision or recall figure
from this corpus means anything.

[Decomposition Dilemmas](https://www.alphaxiv.org/audio/2411.02400) names four
decomposition failure modes — context omission, ambiguity, over-decomposition,
meaning alteration — and recommends adaptive granularity. Ours is
over-decomposition relative to the key's convention, not relative to the source.

### 2.2 A Reddit thread on PDF→GraphRAG: mostly corroboration

Low signal overall, but it independently confirms things we found empirically:
per-source-type tool routing and per-source metadata (= our `source_capabilities`
+ G8), asking the model for exact page/line (= our locators), and testing on a
small known-answer subset (= our gold fixtures). The one problem it names that we
had not closed is **cross-references across chunks** — "a requirement on page 230
references something on page 10" — see §3.1.

**GraphRAG itself is a step down for us.** GraphRAG builds a graph to retrieve
answers; here the typed graph *is* the institutional memory. An untyped similarity
graph is what the dictionary's §12.3 anti-decorative-graph rule forbids.

### 2.3 Obsidian's graph view: a free lens, not a product surface

The vault is Obsidian-compatible, but `bears-on` is written as plain YAML strings,
so **1,191 real claim→question edges (74 questions, zero dangling) draw nothing**
in the graph view, while `plan.md` and `events/` — which use `[[wiki-links]]` —
render fine. Writing those values as `"[[q-03]]"` would light all of them up for
free, with node size (incoming links) showing which questions carry the most
evidence.

**Limit:** Obsidian colours *nodes*, never *edges*, so `BEARS_ON`, `CONTRADICTS`
and `DERIVED_FROM` all render identically. To make relation type visible you must
**reify the edge as a node** (`rel-contradicts-c001-c047.md` linking both ends) —
the vault already does this for `events/`. Good debugging lens; not the UI.

---

## 3. Defects found and fixed

### 3.0 ⚠️ There are TWO divergent claim-graph modules — read this first

This is the most important structural finding of the session.

| module | tracked? | used by | prose-derivation handling |
|---|---|---|---|
| `vercel/api/_claim_graph.py` | **yes** | `app/v20_router.py` (the running app) | **already correct** |
| `tools/claim_graph.py` | **no** (gitignored) | offline `pipeline_out/graph/*` builds | had the defect in §3.1 |

The tracked module already separates the two cases properly: an explicit
`derivation_claim_ids` input becomes `DERIVES_FROM` with `canonical: True`
(`EXPLICIT_DERIVATION_INPUT`, DETERMINISTIC), while a prose metric-name match
becomes a **proposal** — `canonical: False`, `proposal_status:
PENDING_HUMAN_REVIEW`, `llm_authority: PROPOSE_ONLY`, `adjudication:
HUMAN_REQUIRED`.

**So the §3.1 fix was applied to the stale, gitignored duplicate, and the
production path was never broken.** The fix there is still correct, but the real
issue is the divergence itself: two copies of the graph logic, one of them
invisible to git. **Decide whether `tools/claim_graph.py` should be deleted,
re-pointed at the tracked module, or brought under version control.**

### 3.1 `DERIVES_FROM` edges bound by metric *name*, not by operand
*(in `tools/claim_graph.py` only — see §3.0)*

`claim_graph.py` matched an operand by substring of the metric name against the
derivation prose. `"Gross profit $1.455m ÷ Revenue $4.26m"` names Revenue once, so
it emitted an edge to **every Revenue claim in the deal** (74.0, 5.624, 1.618,
0.754 — none of them the operand).

Replaying current code: **155 edges, only 12 survive value verification.** 92% of
what the engine traversed could not be reconciled with the method it claimed.

Fixed: the name is now only a candidate filter; the operand's value must be
confirmable in the stated method (scale-aware: `$4.26m` ↔ `4.26` ↔ `4260000`,
`34.15%` ↔ `0.3415`). Verified edges stay canonical; name-only matches become
`canonical=False` — visible, never traversed. Nothing deleted.

⚠️ **`tools/claim_graph.py` is gitignored** (`.gitignore:68`, "Proprietary
algorithms"). **This fix is not version-controlled.** Backup:
`scratchpad/claim_graph.FIXED.py`. **This needs a decision.**

Note this closes §2.2's cross-chunk problem structurally: the global pass sees all
claims at once, unlike L2's in-batch `derive_relations`.

### 3.2 Five workbook refs pointed at unit cells; four values genuinely disagree

The Inputs sheet uses **two layouts** — row 3 is `label|value|unit`, row 46 is
`label|unit|value` — so refs written as column B land on the unit cell in every
scenario block. All five exit-multiple refs pointed at `'x'`, `'%'` or `'days'`.
The rows were wrong too: multiples sit at 46/53/60/67/74, not five consecutive rows.

Fixed the refs in `compiler_v7.py`. **No value was changed**, and with correct refs
four disagreements now surface in the open:

| concept | declared | workbook |
|---|---|---|
| Standalone Downside | 7.5 | **8.0** |
| Standalone Upside | 10.0 | **9.5** |
| Acquisition Base | 9.5 | **9.0** |
| Combined Risk | 8.0 | **8.5** |

**→ Needs a human.** Is the workbook stale, or is the underwriting deliberately
more conservative? Overwriting either side destroys the evidence they disagreed.
`verify_refs()` in `workbook_concept_binder.py` now checks this generally.

### 3.3 Metric vocabulary drift (caught by the repo's own guard)

Three metrics added to `METRIC_ENUM` this session (`Total Net Leverage Ratio`,
`Minimum Liquidity`, `Customer Churn`) never reached `object_identity.METRIC_VOCABULARY`,
so claims about them silently became unresolvable and stopped being comparable.
PAN-63's drift guard caught it. Fixed.

---

## 4. Tasks completed

| task | what landed |
|---|---|
| **G5** | Archetype vocabulary **replaces** the menu instead of appending. venture 69→25 labels; the six buyout structural metrics become unofferable. Verified on a frozen run the model *was* taking them (Sponsor Equity ×2 on a Seed round). |
| **G8** | Per-deal source ledger. 9 of 18 Silexara sources now arrive as `Call Transcript`/`Meeting Notes` instead of `Other`, so the prompt's own "call transcript → observed" rule finally fires; 18/18 carry real dates. `company_materials` stays deliberately unmapped and reported. |
| **G1** | Expression↔binding contract **enforced**, not just reported. 10 of 12 `ARITHMETIC` formulas on K-PRE fail it (ticket estimated 5). Hand-written mappings get reclassified with reasons; compiler-generated ones raise. |
| **G2** | `build_overrides()` feeds `DIRECT_INPUT` nodes from admitted claims. Honest result **1 of 28** — see §5.1. |
| **G7** | Deterministic cell→concept proposer. Agreement **28.6% → 71.4%** on one insight: a units column sits between label and numbers, so 10 of 28 rows resolved to `$mm`/`days`/`%`. Nothing is ever auto-admitted. |

---

## 5. Open right now

### 5.1 G2 is blocked, and the block is structural
The claim→model_node link **does not exist as an artifact**:
- `bindings.json` → claim → **question** (1127 rows, no `model_node_id`)
- `position_model_directions` → **position** → node (14 rows)
- claim → position → only as `claim_graph` `SUPPORTS` edges (126 on K-IC)

`build_overrides` already resolves that chain *when given such records*; nothing
supplies them. Wiring it is **G7/R6** work. Faking it means inventing numbers into
a financial model.

### 5.2 Dynamics suite: 393/393 — all four failures fixed

Started at 4 failures. **Attribution matters here and I got it wrong twice
before running it down properly**, so the method is recorded: a worktree at the
session baseline, then at Anto's `5910515`, then a commit-by-commit sweep.

| test | cause | status |
|---|---|---|
| `test_pan63_claim_identity_migration` | **real bug, mine.** Three metrics added to `METRIC_ENUM` never reached `METRIC_VOCABULARY`, so claims about them became unresolvable. | **fixed** |
| `test_llm_provider` | **mine, deliberate.** Pinned `max_tokens == 4096`; it is 8192 because 4096 silently truncated (3/3: `stop_reason=max_tokens`, 0 claims, no exception). Test now asserts against the module constant. | **fixed** |
| `test_pan58_clean_case_bootstrap` | **not a code regression.** Test-isolation bug: it repoints `PIPELINE_OUT` but `_pipeline_out_for_case()` uses `PIPELINE_OUT` only for keystone and `CASE_PIPELINE_ROOT / case_id` otherwise — so it read the developer's real `pipeline_out/cases/clean/` (a gitignored artifact dated **Aug 31**, before this session). Now isolates `CASE_PIPELINE_ROOT`. | **fixed** |
| `test_v20_live_evidence_loop` | **real contract-boundary bug.** The bridge had already emitted a governed claim→position edge, but the router and runtime rechecked the extractor's descriptive perimeter against the canonical position perimeter. The event now carries explicit `mapping_target_semantics`: applicability is checked against the canonical target identity while the admitted claim retains its own source period/perimeter/unit. | **fixed** |

**Method note worth keeping:** `make verify` reported "suite failed" both before
and after my changes, so an identical `make verify` result could **not**
distinguish "no new failure" from "one more failure inside an already-failing
suite". Comparing whole-suite pass/fail is not attribution. Run the suite
directly and diff the failure list.

**Worktree caveat:** a `git worktree` does **not** carry gitignored files, so
`tools/claim_graph.py` and local `pipeline_out/cases/*` are absent there. A test
can pass in a worktree and fail in the main tree for that reason alone — which is
exactly what happened with `pan58`.

### 5.2b `make verify`: 4 failing stages → 1

Three were fixed; the fourth is a data question, not a code one.

- **PAN-36** and **dynamics bundle run** were *harness* bugs, same root cause:
  `panta_transition_engine` imports its siblings as a top-level `runtime`
  package (for standalone serverless packaging), which resolves only with
  `backend/dynamics` on `sys.path`. The suite gets that from
  `cwd=backend/dynamics`; anything launched from the repo root does not. After a
  **third** tool hit it (`bundle_assemble.py`), the fix moved to the package
  boundary in `backend/dynamics/__init__.py` — one place, all callers, flat
  imports untouched.
- **Dynamics unit suite** — now **394/394**. The last failure
  (`test_v20`, `mapped_claim_count 0 != 1`) was fixed properly:
  `_claim_mapping_is_applicable` compared the RAW CLAIM against the profiled
  position, which is redundant *and* wrong — the bridge has already applied the
  governed binding rule, and extractor perimeter text is more descriptive than
  the canonical position perimeter, so correct claims never matched.
  `_position_mapping_is_applicable` now compares compiled vs baseline position
  identity. The test was strengthened, not relaxed.

**Still failing — needs a decision, not a fix:** `PANTA independent validation`,
`PASS=44 FAIL=2`. The bundle's declared `transition_output.json` diverges from
the independent runtime on `[affected_set, engine_version, policy_refs,
semantic_result_hash]`. `engine_version` is in that list, so the engine moved and
the bundle was never regenerated — and it moved again with the
`_position_mapping_is_applicable` fix.

Regenerating is the right repair, but `bundle_assemble.py` refuses to run
standalone (*"richiede il dict del bridge; usare adapter_alpha.py"*): it must be
driven by a full `adapter_alpha` run, which rewrites all 16 sealed files. The V7
acceptance stage (176/176) hashes that bundle. **Not done here** — rewriting a
sealed bundle other passing tests depend on belongs to whoever owns the engine
change. Anto regenerated it last on 2026-09-02 alongside their engine work.

### 5.3 Other open items
- **Two divergent claim-graph modules (§3.0)** — the highest-value decision here.
  `tools/claim_graph.py` is gitignored and holds an unversioned fix; the tracked
  `vercel/api/_claim_graph.py` already implements the correct discipline.
- **Four exit-multiple value disagreements** need a modelling decision (§3.2).
- **G3 stays Todo on purpose** — its "done when" needs G7 bindings *admitted*, and
  admission is a human act.
- **The answer key is corrupted**: 57 of 76 gold records carry an anonymiser bug
  (`asserted` → `asseContinental Grid Operatord`). `SCORING_RUBRIC.md` too.
  Worth reporting upstream; `epistemic_class` is unusable for scoring as shipped.
- **Full-coverage Silexara rerun** still owed — the earlier glob missed SRC-08
  (`.txt`), SRC-11 (`.eml`), SRC-18 (`.html`); two PDFs need the GPU pod.
- `AI_HARNESS.md`, which `CLAUDE.md` says to update at task end, is **gitignored
  and absent** from this tree. The Linear import CSV is the only local status record.

---

## 6. Standing constraints

- **Haiku for extraction**, always (`claude-haiku-4-5-20251001`). Never silently upgrade.
- **Nothing is admitted by a machine.** Proposals carry evidence; humans admit.
- **Report, never adjudicate.** Contradictions say what doesn't reconcile, not who is right.
- **Never invent a value.** A missing input stays dark with a written reason.
- stdlib + PyYAML only in `tools/`.

---

## 7. GLM 5.2 through OpenRouter — first real calls, and what they showed

Everything before 2026-09-05 verified request **shape** with mocks. These were the
first live calls. The round trip works, and it exposed a bug worth a quarter of
the benchmark.

### 7.1 Reasoning models burn the output budget before answering

GLM 5.2 is a reasoning model. On a tool-use call it spends the ENTIRE output
budget thinking and never emits the tool block:

| | stop_reason | out tokens | blocks | claims |
|---|---|---|---|---|
| default | `max_tokens` | 8192 | `['thinking']` | **0** |
| `thinking: {"type":"disabled"}` | `tool_use` | 3255 | `['text','tool_use']` | **17** |

Input was 483 tokens — never a size problem. **It must be the Anthropic-native
`thinking` field**: through OpenRouter's `/v1/messages` skin,
`reasoning={"effort":"low"}` and `reasoning={"enabled":False}` were both ignored,
and forcing `tool_choice` did not help either.

### 7.2 Benchmark (Anto's 11 cases), same pipeline, GLM 5.2

| run | mean | statuses |
|---|---|---|
| GLM, before the fix | 51.6% | 7 success, 4 abstained |
| **GLM, after the fix** | **65.0%** | 9 success, 2 abstained |
| GLM via the teacher adapter (`semantic_openrouter.py`) | 40.2% | 5 success, 5 abstained, 1 error |

**Do not compare 65.0% to the old 77.2% as a model verdict.** The two numbers are
not commensurable yet:
- 77.2% was Haiku on a pipeline that has since changed (G5 vocabulary
  replacement, G8 source catalog, evidence_state, QUALITATIVE).
- Haiku **cannot be re-measured right now — the Anthropic key is out of credit**
  (`"Your credit balance is too low"`). An attempted Haiku baseline scored 12.9%
  with **11/11 abstained at ~1.3 s latency**; that is the API failing, not a model
  result, and it must not be quoted as one.
- The teacher-adapter run is a different *system*, not a different model.

A real head-to-head needs Anthropic credit, then one Haiku run on today's code.

### 7.3 One case still abstains, and it is ours, not GLM's

`panta-semantic.identity.periods-003`. The model returns 3 claims to a raw call
(`stop=tool_use`, 526 output tokens, temperature irrelevant), but the adapter
consistently reports `status=abstained, claims=0, rejected_count=0` — claims
disappearing without being counted as rejected. The difference is the fuller
prompt `annotate_chunk` builds versus the bare chunk body. Reproducible, two runs
identical. **Open.**

### 7.4 Cost

GLM 5.2 $0.97/M in, $3.04/M out vs Haiku 4.5 $1.00 / $5.00 — cheaper, though not
dramatically. Full Keystone K-IC (351 chunks) is roughly $2-4.


### 7.5 Raising GLM: 51.6% → 78.0%, three measured steps

Two of the three levers were provider bugs, not model limits. Each was found by
reading the RAW response instead of the adapter's summary.

| step | change | score |
|---|---|---|
| 0 | GLM as first wired | 51.6% |
| 1 | `thinking: {"type":"disabled"}` — it burned the whole budget reasoning | 65.0% |
| 2 | stop pinning `tool_choice` — pinned, GLM never terminates the tool call | 75.1% |
| 3 | context padding — read wider than you write | **78.0%** |

Step 3 hit exactly what it was designed to hit:

    derivation_accuracy   25.0% -> 100.0%
    identity_accuracy     50.0% ->  66.7%
    measurement_accuracy  37.0% ->  52.6%
    relation_recall       10.0% ->  20.0%

A derivation cannot be stated without its operands in view, and before the
padding they were routinely in the next chunk.

**Reasoning space, tested separately (`PEOS_OPENROUTER_THINKING=true`):** 77.6%
against 78.0%, at 28s per case instead of 9s. A trade, not a win — it buys
relation_precision (22.2% -> 100%) and scenario accuracy, and loses exact_match
(48.5% -> 43.8%) and identity accuracy. Default stays off; the switch is real.
The follow-up worth trying is selective rather than global: reason about
relations, not about the identity tuple.

**Where GLM still loses** (per-field, on the extracted cases): `exact_match`
48.5% is the ceiling on everything, dragged by `measurement` 52.6% and
`identity` 66.7%. `relation_f1` 40.2%. Claim finding itself is not the problem —
precision and recall are both 100%.

**Not yet comparable to Haiku.** Haiku cannot be re-measured while the Anthropic
key is out of credit; 78.0% vs the old 77.2% is suggestive, not a verdict.
