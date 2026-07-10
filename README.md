# PE OS

The operating system for private markets: deals held as living question structures, evidence epistemically typed and bound to what it bears on, decisions recording what was accepted as unresolved, outcomes closing the loop.

- **Why / strategy:** `sources/manifesto.md`, `sources/ospm-extracted.txt`, `docs/00-problem-structure.md`
- **Spec & stack:** `docs/01-spec.md`
- **The product:** `vault/ontology/` (schemas) + `vault/policy/policy-table.md` + `.claude/skills/` (the agents)
- **Operating manual:** `AI_HARNESS.md` · **agent instructions:** `CLAUDE.md`

## Quick start

```bash
make setup                 # PyYAML
claude                     # in this directory, then:
#   /open-deal             # open a deal as a question structure (the one 20-min input)
#   drop artifacts into vault/inbox/, then /ingest
#   /contradictions        # what doesn't reconcile, bound to open questions
#   /ic-record             # capture the decision — both halves
make report                # open questions · contradiction candidates · unbound claims
```

Open `vault/` in Obsidian for the graph and backlink views. The vault is canonical; `.index/` is a disposable projection.
