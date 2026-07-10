---
name: ingest
description: Perceive an artifact (deck, transcript, Excel model, email) — extract claims with epistemic types and provenance, bind them to the questions they bear on, and surface what contradicts. Run when something lands in vault/inbox/ or the user points at an artifact.
---

# Agents: extractor → binder (kept separate — binding is the accuracy-critical problem)

**Input (typed):** path to one artifact + the deal it arrived in.
**Output (typed):** claim files in `vault/deals/<deal>/claims/`, updated `## Evidence` sections on bound questions, refreshed `## State of the deal`, contradiction report if any.
**Authority:** policy rows 1–5. The artifact is read in place, never copied or moved out of the user's control (inbox files may be left where they are; record the path).

## Procedure — extraction

1. Read `vault/ontology/claim.md` and the deal's question tree.
2. Read the artifact. Extract discrete claims: statements of fact, quantity, or intention. For each, capture `subject` (normalized — same quantity ⇒ same subject string across the whole deal; check existing claims' subjects first), `value`, `source.locator`, `source.author`, `source.date`.
3. Type each claim:
   - deck/memo statement → `asserted`
   - model cell with formula → `derived`, with `derivation` (the formula chain in words) and `rests-on` (claims for its inputs — create input claims if needed; model inputs typed by *their* origin, usually `asserted`)
   - transcript/recording statement → `observed` for what happened, `asserted` for what the speaker claims about the world
   - audited/contractual figure → `attested`
   - When uncertain, type DOWN the hierarchy (asserted), never up.
4. Write one file per claim per `vault/ontology/claim.md`. `written-by: extractor`.

## Procedure — binding

5. For each claim, find the question(s) it bears on by reading the question tree — bind by meaning, not keyword. Fill `bears-on` and `direction`; append the link under the question's `## Evidence`.
6. A claim that bears on no open question is a signal, not noise: leave `bears-on` empty and list it in the session report under "unbound claims — possible missing question." Propose the missing question; do not create it without the user.
7. Advance question states where evidence warrants (`open → reducing`, `reducing → resolved` only when the user confirms). Never set `accepted-unresolved` (policy row 7).

## Procedure — surface

8. Invoke the `contradictions` skill scoped to the subjects just written.
9. Regenerate `## State of the deal` in `deal.md`. Run `make index`.
10. Report to the user: claims extracted (by epistemic type), bindings, state changes, contradictions, unbound claims. **Push, not pull — lead with what they didn't know to ask.**
