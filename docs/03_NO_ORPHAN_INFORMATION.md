# No-Orphan Information Rule

Anything meaningful shown as **case content** must resolve to a canonical object or an explicit UI projection over canonical refs.

## Workstream projection

A Workstream contains refs:
- `currentCaseReadingId`
- `ownerActorId`
- `latestChangeEventId`
- `activeWorkItemIds`
- `openUnknownIds`
- `questionIds`

It does not carry free-text `owner`, `latestChange`, `activeWork` or `stillOpen` case facts.

## Artifact blocks

Every artifact block is one of:
- `CASE_BACKED` — bound to canonical case object ids
- `HUMAN_AUTHORED` — attributed to an Actor
- `PANTA_SUGGESTION` — explicit proposal, not accepted truth

No anonymous generated prose.

## Quantities

Every quantity/model value exposed as operative must preserve enough semantic perimeter to identify what it means:
- metric/concept
- entity / target where relevant
- scope/perimeter
- basis / measurement
- period
- scenario
- unit/currency
- source refs
- assumption refs
- formula/derivation where applicable

Unknown values remain unknown.

## UI-copy exemption

Navigation, action labels and generic empty-state copy are UI language rather than case facts and do not require object ids. They must still not pretend backend state exists when it does not.
