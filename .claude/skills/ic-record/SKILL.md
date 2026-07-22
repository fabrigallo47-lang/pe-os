---
name: ic-record
description: Capture a decision record at the decision moment — what was resolved on what strength, and what was accepted as unresolved and why that was tolerable. Drafted by the agent from the question structure; authored and confirmed by the human. Ship this first — everything downstream starts when this starts.
---

# Agent: recorder (draft) + human (author)

**Input (typed):** the deal, and the human in the room.
**Output (typed):** `vault/deals/<deal>/decisions/d-<deal>-<nnn>.md` per `vault/ontology/decision.md`. Append-only forever.
**Authority:** policy rows 1, 4, 6 for the draft. Rows 7–8: the acceptance of unresolved questions and the final record are **human-only**.

## Procedure

1. Read the deal's full question tree and current states.
2. Draft the two halves from structure:
   - **Resolved:** every `resolved` question with its strongest evidence chain, noting the epistemic type the chain bottoms out in.
   - **Accepted as unresolved:** every question still `open`/`reducing` — because proceeding *is* accepting them. This list is usually longer than anyone expects; that is the product working.
3. Walk the human through the unresolved list, one question at a time: *accept, resolve now, or block the decision?* For each accepted: capture why tolerable, exposure if wrong, protective response (term, milestone, none) — in their words.
4. Capture: commitment, decided-by, dissent (who, on which question, what stance), and the Basis section (what the return depends on that has no evidence at all — draft it from questions with empty Evidence sections).
5. Human confirms the final text. Write the file, `written-by: human`. Transition accepted questions to `accepted-unresolved` with rationale — the one transition only this moment may perform.
6. `make index`. Remind: when a term moves in negotiation, run this deal through `contradictions` — the term maps to an accepted-unresolved question being re-exposed.
