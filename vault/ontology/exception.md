# Schema: Exception (ExceptionRecord)

"A dead or stalled opportunity is a terminal or paused workflow outcome with reason-coded evidence, not missing data." Exceptions make skips, backtracks, declines, and stalls first-class — so dead deals compound too, and revival is a governed path instead of a vague reopening.

## Frontmatter

```yaml
---
type: exception
id: x-<deal>-<nnn>
deal: "[[<deal>]]"
reason-code: screening_declined
  # controlled enum (spec §7): access_denied | out_of_scope | screening_declined |
  # diligence_red_flag | unresolved_critical_question | valuation_fail |
  # approval_declined | terms_changed | process_lost | execution_failed |
  # stalled | support_declined | data_insufficient
scope: deal | state-skip | backtrack | branch    # what this exception covers
last-active-state: S5_DILIGENCE_ACTIVE           # from the backbone state machine
authority: "[[<person>]]"                        # who authorized the deviation
revival-condition: "new process access or materially revised terms"
at: 2026-07-12
supersedes: null                                 # append-only; supersede to correct
---
```

## Body

```markdown
# Exception: <one line>

## Rationale / evidence
Why, with links to the claims or events that support it.

## Revival
What new evidence, terms, access, or authority would reopen this (spec rule:
revival requires a NEW material trigger — SX blocks re-entry without one).
```

## Rules

- **Skip rule:** a lifecycle state may be skipped only with an exception naming the skipped state, reason, authority, materiality, and downstream risk acceptance.
- **Backtrack rule:** a finding that invalidates a critical assumption reopens the *earliest affected* state, recorded as an exception + event.
- **Live-position rule:** a declined action on a live position is a branch-level exception; the deal returns to monitoring/re-underwriting, never to terminal.
- Every exception emits a corresponding immutable event ([[event]]).
