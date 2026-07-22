---
name: open-deal
description: Open a deal as a question structure. The human states the thesis; this skill proposes the question decomposition from the question-type library; the human corrects. The ONLY structured input the system ever asks for (~20 minutes, once).
---

# Agent: decomposer

**Input (typed):** deal name, company, thesis statement (one paragraph max) — from the user.
**Output (typed):** `vault/deals/<slug>/` with `deal.md` and one file per question, conforming to `vault/ontology/`.
**Authority:** policy rows 1, 4. Creates structure; sets every question `state: open`.

## Procedure

1. Read `vault/ontology/question.md`, `vault/ontology/deal.md`, and every file in `vault/library/question-types/`.
2. Ask the user for: deal name, company, thesis, deal lead. Nothing else, ever.
3. Decompose the thesis into thesis-level questions: *what must be true for this thesis to hold?* Each must be phrased as a question ("Is the revenue plan real?"), never an activity ("financial diligence").
4. For each, match against the question-type library; link `question-type` where a type exists, propose a new `qt-` file where one doesn't (domain-tagged, so it compounds).
5. Propose nested sub-questions per the types' `decomposes-into`, plus deal-specific ones from the thesis. Mark `depends-on` edges where resolving one question changes another's weight.
6. **Present the full tree to the user for correction before writing anything.** Apply corrections verbatim — this is the human's twenty minutes; their edits are the point.
7. Write `deal.md` and `questions/*.md`. Set `written-by: human` on the thesis, `written-by: decomposer` on proposed questions the human kept.
8. Run `make index` to refresh the derived index.

## Failure conditions
- Asking the user for any structured input beyond step 2 = failure.
- A question file whose title is an activity, not a question = failure.
