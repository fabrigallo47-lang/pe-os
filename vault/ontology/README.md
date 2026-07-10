# Ontology

This directory **is the product**. Every entity in the system is a markdown file whose YAML frontmatter conforms to one of these schemas. Wikilinks are the edges of the graph. Git history is the provenance and audit layer.

## Entity types

| Type | Schema | One file per | Lives in |
|---|---|---|---|
| `question` | [question.md](question.md) | question instance | `vault/deals/<deal>/questions/` |
| `claim` | [claim.md](claim.md) | extracted claim | `vault/deals/<deal>/claims/` |
| `decision` | [decision.md](decision.md) | decision moment | `vault/deals/<deal>/decisions/` |
| `outcome` | [outcome.md](outcome.md) | realized outcome | `vault/deals/<deal>/decisions/` |
| `deal` | [deal.md](deal.md) | deal | `vault/deals/<deal>/deal.md` |
| `question-type` | [question-type.md](question-type.md) | reusable question class | `vault/library/question-types/` |
| `company`, `person` | [entity.md](entity.md) | real-world entity | `vault/entities/` |

## Rules (invariants — don't break these)

1. **Evidence attaches to questions, not to deals.** A claim's `bears-on` field links questions; the deal is derivable, never the anchor.
2. **Artifacts are never copied into the vault.** Claims carry a `source` pointer (path + locator) into wherever the artifact lives.
3. **Every claim has exactly one `epistemic` type**: `asserted | derived | observed | attested`. If `derived`, the `derivation` field is mandatory — a derived claim without an inspectable derivation is an asserted claim and must be typed as such.
4. **`accepted-unresolved` is a first-class question state**, not a failure mode. It requires a written rationale (why tolerable).
5. **Nothing here is human-maintained after creation** except: the thesis correction at deal open, and the decision record at the decision moment. Everything else is written by agents under the [policy table](../policy/policy-table.md).
6. **Machine-written files are marked** `written-by: <agent>` in frontmatter. Append-only files (decision records, audit entries) are never edited — corrections are new files that `supersedes` the old.
