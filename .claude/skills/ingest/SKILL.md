---
name: ingest
description: Perceive an artifact (deck, transcript, Excel model, email) — extract atomic claims with epistemic types and provenance, register the artifact as a graph node, bind claims to questions, and surface contradictions. Run when something lands in vault/inbox/ or the user points at an artifact.
---

# Agents: extractor → binder (kept separate — binding is the accuracy-critical problem)

**Input (typed):** path to one artifact + the deal it arrived in.
**Output (typed):** one artifact node in `vault/deals/<deal>/artifacts/`, claim files in `vault/deals/<deal>/claims/`, updated `## Evidence` sections on bound questions, refreshed `## State of the deal`, contradiction report if any.
**Authority:** policy rows 1–5. The artifact is read in place, never copied or moved out of the user's control.

## Procedure — artifact registration (do this first)

0. Read `vault/ontology/artifact.md` and `vault/ontology/claim.md`.
1. Before extracting any claims, register the source document as an artifact node:
   - ID: `art-<deal>-<slug>` where slug is a short kebab-case description (e.g. `art-keystone-qoe-jan2026`)
   - Write to `vault/deals/<deal>/artifacts/art-<deal>-<slug>.md` using the artifact schema
   - Set `digital-source` to the file path or URL; set `kind` (deck/model/transcript/email/report/contract/vdr-document)
   - Set `company`, `author-entity` as wikilinks if you can resolve the entity (check `vault/entities/`)
   - Set `source-date` (when the document was produced) and `received` (today)
2. Claims extracted from this artifact will carry `artifact-id: "[[art-<deal>-<slug>]]"` — the graph edge from claim to document.

## Procedure — extraction

3. Read the artifact fully. Extract ATOMIC claims: **one claim = one fact**. If a sentence asserts two things, write two claims. Never pack multiple metrics into one value.
   - For each claim: `subject` (normalized — same quantity ⇒ same subject string across the whole deal; check existing claims first), `value` (one number or assertion), `source.locator` (slide N / page N / cell Sheet1!D42 / timestamp HH:MM:SS), `source.author`, `source.date`.
   - Numeric claims: assign `metric-category` from: revenue | ebitda | debt | equity | irr | leverage | multiple | headcount | margin | growth | cash | capex | working-capital | customer-concentration | churn | price | volume
4. Type each claim:
   - deck/memo statement → `asserted`
   - model cell with formula → `derived`, with `derivation` (formula chain in plain English) and `rests-on` (claims for inputs — create input claims if needed)
   - transcript/recording statement → `observed` for what happened, `asserted` for what the speaker claims about the world
   - audited/contractual/signed figure → `attested`
   - When uncertain, type DOWN the hierarchy (asserted), never up.
5. Write one file per claim per `vault/ontology/claim.md`. Include:
   - `artifact-id: "[[art-<deal>-<slug>]]"` — link to artifact node (REQUIRED)
   - `company: "[[<entity-id>]]"` — company being described (if resolvable)
   - `author-entity: "[[<entity-id>]]"` — entity who produced it (if resolvable)
   - `digital-source: "<path-or-url>"` — the document path or URL
   - `metric-category: <category>` — for numeric claims
   - `written-by: extractor`

## Procedure — binding

6. For each claim, find the question(s) it bears on by reading the question tree — bind by meaning, not keyword. Fill `bears-on` and `direction`; append the link under the question's `## Evidence`.
7. A claim that bears on no open question is a signal, not noise: leave `bears-on` empty and list it in the session report under "unbound claims — possible missing question." Propose the missing question; do not create it without the user.
8. Advance question states where evidence warrants (`open → reducing`, `reducing → resolved` only when the user confirms). Never set `accepted-unresolved` (policy row 7).
9. After writing all claims, append the claim list to the artifact node's `### Claims extracted` section.

## Procedure — surface

10. Invoke the `contradictions` skill scoped to the subjects just written.
11. Regenerate `## State of the deal` in `deal.md`. Run `make index`.
12. Report to the user: artifact registered, claims extracted (by epistemic type and metric-category), bindings, state changes, contradictions, unbound claims. **Push, not pull — lead with what they didn't know to ask.**
