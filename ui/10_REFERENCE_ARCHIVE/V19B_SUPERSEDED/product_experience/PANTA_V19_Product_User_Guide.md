# Product User Guide

A practical guide from source ingestion and claim review to governed settlement and causal replay.

**Release:** V19.0.0  
**Date:** 27 August 2026

## 1. Start here

PANTA V19 is a command center for one persistent investment case. It helps an investment professional move from source arrival to grounded evidence, case state, economic consequences, governed decisions, execution and replay.

The fastest complete path is: choose Mock Connected -> open Sources -> inspect Claims -> return to Deal Command -> review a material change -> read Change Impact -> select change sets -> attest -> review the package -> settle -> replay.

## 2. Choose a system mode

| Mode | Use | What V19 guarantees |
| --- | --- | --- |
| Connected | Real compiler, Case Store and Transition Engine are available | No fixture fallback. Failure is explicit. |
| Mock Connected | Full governed walkthrough and extractor-to-screen demo | Stateful synthetic API; simulated authority; no external effects. |
| Offline Demo | Portable read/review demonstration | Explicit fixture; formal writes and settlement are unavailable. |

## 3. Ingest a source

- Open Sources from the navigation.
- Choose Ingest.
- Select File, Local path or URL; or open Vault Inbox.
- Add the purpose/expected content.
- Start the ingest job.
- Read stage, progress and any fix message.
- When complete, V19 refreshes the projection and Source Library.

## 4. Inspect compiler output

- Claims Explorer shows each statement and question binding.
- Use seven filters and search to narrow the result.
- Open a claim to inspect source, locator, definition, period, perimeter and Bears on.
- Use Action to accept, correct or reject.
- Open Compiler Review for ungrounded or unmapped pipeline items.

## 5. Open or switch a deal

The case switcher loads another frontend projection. Use Case Setup & IC Record to record a new deal objective/thesis decomposition or an IC decision, conditions and dissent. These are structured institutional inputs, not ordinary claims.

## 6. Orient in Fund and Deal Command

### Fund Command

- Read Morning Delta.
- Select a material situation.
- Read why now, owner, deadline and required action.
- Open Deal World.

### Deal Command

- Read Working, Current and Approved separately.
- Use the underwriting-question spine.
- Open any question into Object Aperture.
- Use the action rail for next-best work and current run context.

## 7. Use supporting rooms

| Room | Use |
| --- | --- |
| Work | Prepare case-wide closure work. |
| What the Deal Rests On | Inspect competing values and weak floors. |
| Unknowns | Prioritize decision unknowns; switch to Pipeline Review for compiler issues. |
| Shadow IC | Preserve the strongest supportive and skeptical cases. |
| Scenario Lab | Compare explicit projected trajectories. |
| Artifacts | Inspect files, versions, cells and bindings. |
| Registry | Read server-acknowledged events. |
| Causal Replay | Reconstruct historical state read-only. |

## 8. Review a new change

- Open the source arrival.
- Read the exact passage and semantic applicability.
- In Change Review, edit, reject or admit the proposed treatment.
- Admission creates a Candidate; it never overwrites the source.

## 9. Read Change Impact

Change Impact plays the ordered affected set. Each object is labeled Recomputes, Survives, Falls, Rule Switch, Human or Blocked. Use Skip to complete the visualization or Replay to see the sequence again; neither action changes the Registry.

## 10. Select the response

Action Frontier lists prepared artifact change sets. Select explicitly or use Select all. Zero selected items block the CTA. The payload and preview contain only the selected IDs.

## 11. Authority and execution

- Decision Room opens only for a valid Candidate and Human Stop.
- Viewer projection does not change authenticated authority.
- Select one course of action and attest.
- Defer ends without an execution package.
- An external course creates a course-specific immutable package.
- Execution success appears only after server acknowledgment.

## 12. Settlement and replay

Settlement is server-side and returns one new Current state. Deal Command, Registry and Replay are updated from the same result. Causal Replay remains read-only and preserves the prior Approved state unless the relevant authority created a successor.

## 13. Keyboard, responsive and errors

- Cmd/Ctrl+K opens Quick Navigation.
- Escape closes the active dialog/drawer and returns focus.
- Reduced-motion follows the system preference.
- At mobile width the interface is read/review-only.
- Errors state the operation, reason and recovery path.
- Connected failure never injects synthetic data.
