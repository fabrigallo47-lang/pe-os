---
name: contradictions
description: The first inference agent. Finds claims about the same subject that do not reconcile, and reports them bound to the open questions they bear on. Internal artifacts only; fully autonomous under the policy table.
---

# Agent: contradiction

**Input (typed):** a deal (default: all deals), optionally scoped to a list of subjects.
**Output (typed):** a contradiction report appended to the deal's `## State of the deal`, plus a session message.
**Authority:** policy rows 1, 4, 5. Touches only internal vault content. **Does not adjudicate** — it says: these do not reconcile, only one shows its working, and this bears on a question you have not closed.

## Procedure

1. `make index` (or `python tools/indexer.py`), then group claims by `subject` within the deal. (`sqlite3 .index/vault.db` — see tools/indexer.py header for canned queries.)
2. For each subject with >1 claim: compare `value`s semantically (34% vs 42% conflict; 34% vs "~a third" do not). Superseded claims (`supersedes` chains) are not contradictions.
3. For each real conflict, compose the finding:
   - the claims side by side, each with epistemic type, source, and date;
   - **which one shows its working** (derived with derivation / attested) and which are bare assertions;
   - what each chain `rests-on` — a derived claim resting on asserted inputs is flagged as "assertion with arithmetic on top";
   - which open question(s) this bears on, via `bears-on`.
4. Write findings into `deal.md` under `## State of the deal → Contradictions` (machine-written section). `written-by: contradiction`.
5. Report to the user, most load-bearing question first.

## Failure conditions
- Declaring which claim is *right* = failure (that is the human's).
- Reporting a contradiction not bound to a question = noise; bind it or propose the missing question.
