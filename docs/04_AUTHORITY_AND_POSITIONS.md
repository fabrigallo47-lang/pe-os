# Authority + Human Views — V4 FINAL

## Actor

The kernel identity is `Actor` (person, team, committee, organisation or system principal). Session state returns `actorId` + UI entitlements. Roles/authority remain separately governed and time-bounded in the backend.

Every governed command is actor-attributed through `PantaCommand`.

## HumanPosition

A HumanPosition is what an identified human/body actually expressed:

- `authorActorId`
- `recordedAt`
- `text`
- `scopeObjectId`
- institutional-state projection where applicable
- exact source locator when available

It carries **no CaseReading epistemic status**. The UI calls it **Human view**.

PANTA may find and attribute a position; it may never invent one or rewrite what the human said.

If new evidence challenges it, the position remains historically intact. The affected CaseReading may become contested/invalidated/stale under the runtime contract.

## Contextual projection

Human views appear only where meaningful:

- Deal Home — when relevant to the current workstream/reading;
- Workstream Focus — beside the selected Question/Reading;
- Trace — beside the exact proposition it bears on;
- Outputs — human-authored/position blocks remain protected from silent synchronization.

There is no mandatory “Firm View” column.

## Authority

Frontend entitlement checks are UX. Backend AuthorityPolicy is definitive for decisions, risk acceptance, waivers, capital commitment, external/irreversible action and other governed acts.
