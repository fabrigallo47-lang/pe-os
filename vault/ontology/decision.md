# Schema: Decision

The moment a human judges that what is established supports the commitment, given what is not. Records **both halves** — the second half has never appeared in any memo. Append-only: never edited, only superseded.

## Frontmatter

```yaml
---
type: decision
id: d-<deal>-<nnn>
deal: "[[<deal>]]"
date: 2026-07-10
decided-by: ["[[<person>]]"]   # who bears the consequence
commitment: "Proceed to term sheet at €XXm pre"   # what was actually committed
dissent: ["[[<person>]]"]      # who disagreed, if anyone
supersedes: null
written-by: human              # agent may DRAFT from question states; human authors the final
---
```

## Body — both halves, mandatory

```markdown
# Decision: <commitment, one line>

## Resolved — on what strength
For each load-bearing question:
- [[q-...]] — resolved supported. Strongest evidence: [[c-...]] (attested). Chain bottoms out in: attested/observed.

## Accepted as unresolved — and why tolerable
For each question knowingly left open:
- [[q-...]] — accepted unresolved because <rationale>. Exposure if wrong: <what breaks>.
  Protective response: <term / milestone / none>.

## Dissent
Who dissented, on which question, with what stance. (This is the firm's judgment function becoming data.)

## Basis
What the return depends on that has no evidence behind it at all.
```

The `## Accepted as unresolved` section is the compounding asset: when a negotiated term later moves, the system knows which unresolved question is being re-exposed; when the outcome lands, it attaches back to exactly these entries.
