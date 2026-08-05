---
name: ingest
description: Perceive an artifact (deck, transcript, Excel model, email) — register it as a graph node, extract atomic micro-claims with provenance and hierarchy, run dedup/last-seen stamping, bind to questions, surface contradictions.
---

# Agents: extractor → binder (kept separate — binding is the accuracy-critical problem)

**Input (typed):** path to one artifact + the deal it arrived in.
**Output (typed):** one artifact node, claim files with temporal stamps and hierarchy links, updated question evidence sections, contradiction report.
**Authority:** policy rows 1–5.

## Step 0 — Read schemas

Read `vault/ontology/artifact.md` and `vault/ontology/claim.md` before writing anything.

## Step 1 — Register the artifact node (always first)

Write `vault/deals/<deal>/artifacts/art-<deal>-<slug>.md`:
- `digital-source`: the file path or permanent URL
- `kind`: deck | model | transcript | email | report | contract | vdr-document
- `company`: wikilink to company entity if resolvable from `vault/entities/companies/`
- `author-entity`: wikilink to person/firm entity if resolvable from `vault/entities/`
- `source-date`: when the document was produced; `received`: today

## Step 2 — Dedup check before extracting

For each candidate fact you are about to extract, first check if a claim with the same `subject` + `value` already exists in `vault/deals/<deal>/claims/`:

```
grep -r 'subject: "<normalized-subject>"' vault/deals/<deal>/claims/
```

- **Match found** → stamp `last-seen: <today>` on the existing claim file (update in-place, do NOT create a new file). Record it as "confirmed".
- **No match** → extract and write a new claim file (Step 3).

This means `extracted` is the birth date of the claim; `last-seen` is the last time any document confirmed it. Two dates always present on every claim.

## Step 3 — Extract ATOMIC micro-claims (hierarchy-aware)

**Atomicity:** one claim = one fact. Never pack multiple numbers into one `value`.

**For tables and bridges (EBITDA bridge, revenue bridge, debt schedule, etc.):**

Extract a hierarchy:
```
PARENT claim  → epistemic: derived
  subject: "Firm View EBITDA"
  value: "$11.4m"
  derivation: "QoE EBITDA $11.9m minus WIP reserve ($0.20m) minus run-rate reserve ($0.15m) minus integration ($0.10m) minus finance cost ($0.05m)"
  rests-on: [c-NNN-qoe, c-NNN-wip, c-NNN-rr, c-NNN-int, c-NNN-fin]

CHILD claim 1 → epistemic: asserted (or attested if audited)
  subject: "QoE starting EBITDA"
  value: "$11.9m"
  locator: "QoE bridge / row 1"
  metric-category: ebitda
  part-of: "[[c-NNN-parent]]"   ← link to parent aggregate

CHILD claim 2 → epistemic: asserted
  subject: "WIP / revenue quality reserve"
  value: "($0.20m)"
  locator: "QoE bridge / row 2"
  metric-category: ebitda
  part-of: "[[c-NNN-parent]]"
```

Write children first, then the parent (so you have their IDs for `rests-on`).

**For plain statements:** one claim per fact, no parent needed. If a bullet point says "revenue grew 34% to $12.4m", write two claims: "revenue growth rate: 34%" and "FY25 revenue: $12.4m".

**For every claim, write:**
- `artifact-id: "[[art-<deal>-<slug>]]"` — link to this artifact node (REQUIRED)
- `company: "[[<entity>]]"` — company being described
- `author-entity: "[[<entity>]]"` — who produced the document
- `digital-source: "<path-or-url>"`
- `metric-category: <category>` — for numeric claims
- `extracted: <today>` — birth date, never changes
- `last-seen: <today>` — set to today on creation; will be updated by future ingestion passes
- `written-by: extractor`

## Step 4 — Epistemic typing

- deck/memo statement → `asserted`
- model cell with formula → `derived`, with `derivation` (formula chain) and `rests-on`
- transcript/recording statement → `observed` for what happened, `asserted` for what speaker claims
- audited/contractual/signed figure → `attested`
- When uncertain, type DOWN (asserted), never up.

## Step 5 — Binding

For each new claim, find the question(s) it bears on (read the question tree, bind by meaning not keyword). Fill `bears-on` and `direction`; append the link under the question's `## Evidence`.

A claim bearing on no open question = "unbound". List these in the report; propose the missing question; do not create it without user confirmation.

## Step 6 — Surface

Run the `contradictions` skill scoped to the subjects just written. Regenerate `## State of the deal` in `deal.md`. Run `make index` (this updates the manifest with the new intake timestamp).

## Step 7 — Report

Report:
- Artifact registered: `art-<deal>-<slug>`
- Claims confirmed (last-seen stamped): N
- Claims new: N (by epistemic type and metric-category)
- Hierarchies written: N parent/child trees
- Bindings: N claims → M questions
- Contradictions: N subjects with conflicts
- Unbound claims: list them
- **Lead with what they didn't know to ask.**
