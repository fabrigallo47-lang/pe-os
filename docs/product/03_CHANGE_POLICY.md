# Product Change Policy

## Before implementation
Every task must state:
1. user/investor problem;
2. room affected;
3. desired behavior;
4. what must not change.

## Default scope
Prefer one meaningful behavior/composition change per task.
Do not combine unrelated cleanup with product changes unless necessary.

## Contract safety
Do not change kernel nouns, relation vocabulary, authority semantics, or adapter contract as a side-effect of a visual task.
Contract migrations require an explicit task and updated docs/tests.

## Fixture-free production
Real/synthetic deal facts never enter production `src/`.
Development fixtures stay in `tests/`, `lab/`, or another explicitly non-production directory.

## Interaction truthfulness
- no dead controls;
- no fake autonomous behavior;
- no simulation effects without mapped relationships;
- no source links without source refs;
- no decision recording without actor/authority;
- no HumanPosition authored by PANTA.

## Shared-component rule
Create a shared primitive when behavior/meaning is genuinely shared, not merely because two elements look similar.

## Acceptance
A product change is accepted only if:
- the running product is clearly better;
- room identity remains intact;
- copy remains investor-simple;
- `npm run check:all` passes;
- material decisions are logged.
