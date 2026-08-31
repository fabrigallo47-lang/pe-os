# PANTA Semantic Extraction Contract v0.2

## Boundary

The AI Semantic Compiler interprets sources and emits structured proposals. The Dynamic receives only canonical events and runtime-ready assertions.

```text
Source / utterance / cell
→ context retrieval
→ AI extraction proposal
→ identity and binding validation
→ automatic admission under policy or exceptional review
→ append-only canonical event
→ Dynamic adapter filters runtime-ready assertions
→ Dynamic
```

## Vocabulary

Backend:
- `StatedPosition`: a view actually expressed by an identified person or decision body.
- `CaseReading`: PANTA's system synthesis for a Question.

UI:
- `Position`
- `Reading`

An economic or portfolio position is an `ExposurePosition`, never a `StatedPosition`.

## Important rules

- Record the atomic Claim even when identity or binding remains uncertain.
- Category routes extraction; it never establishes identity.
- Similarity may retrieve candidates and is retained only as trace metadata.
- A fragment may create several objects: Claim, StatedPosition, Condition, MetricObservation or DecisionObservation.
- Human review is exceptional and reason-coded, not required for every extraction.
- The provisional Fund Lens may shape materiality, evidence and admission policy, but an unvalidated Lens is never institutional truth.

## CHALLENGES in v0.2

`CHALLENGES` means adverse evidence that weakens a proposition without logically negating it. It is stored as a semantic Compiler relation only.

It is not a frozen Dynamic relation in v0.2. Therefore:
- it carries `relation_class = SEMANTIC`;
- it carries `runtime_mapping_status = PENDING_ADAPTER`;
- it is excluded from Dynamic input until a versioned adapter is approved.

Clear logical negation or same-identity quantitative divergence uses `CONTRADICTS`, which may be runtime-ready.

## Confidence separation

Extraction, identity, binding and relation confidence are separate. High extraction confidence does not establish identity or a runtime relation.

## Compatibility

This contract sits upstream of the frozen Dynamic. It does not replace frozen machine contracts or conformance tests.
