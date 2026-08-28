---
title: "PANTA V20 Product User Guide"
author: "PANTA Product and Engineering"
date: "27 August 2026"
lang: en-GB
geometry: margin=0.72in
fontsize: 10pt
colorlinks: true
linkcolor: blue
urlcolor: blue
toc: true
toc-depth: 3
numbersections: true
---

# Purpose

This guide explains how an investment professional uses PANTA V20 across buyout, growth and early-stage venture cases. The venture example is Project Tethys, a fully synthetic deep-tech seed case.

# Start the product

## Mock Connected on macOS

1. Open `01_PRODUCT_BUILD/launchers/START_PANTA_V20.command`.
2. Select **Project Tethys** in the case switcher.
3. Confirm the mode strip reads **MOCK CONNECTED** and **no external effects**.

## Mock Connected on Windows

Run `01_PRODUCT_BUILD/launchers/START_PANTA_V20_WINDOWS.bat`.

## Offline Demo

Open `01_PRODUCT_BUILD/launchers/OPEN_OFFLINE_DEMO.html`. Offline mode is an explicit fixture and is read/review-first.

Connected mode is intentionally unavailable in the bundled runtime. It requires a real compiler, Case Store and Transition Engine service.

# Orient in Deal Command

Deal Command shows the current institutional view of the case.

1. Read the **Case Grammar** card to confirm archetype, stage and sector overlay.
2. Check the **Active Governed Lens**. A Lens changes question order, required work and gates; it never changes facts.
3. Review the question spine.
4. Use the **Auditable Criticality** section to inspect load-bearingness, fragility, severity and gate proximity rather than relying on a black-box score.
5. Open an object to inspect its Basis, Dependents, Action and History.

# Inspect conversations and transcripts

Go to **Sources -> Source Library** or **Claims Explorer**.

- An Interaction shows participants, roles, channel, consent, confidentiality, attribution confidence and both dates.
- An Utterance shows the exact speaker, timestamp and text.
- The Utterance Object Aperture states the epistemic boundary: PANTA may know that the statement occurred while the content remains asserted.
- A separate observed-speech-act claim records the occurrence of the statement.

When reviewing an extracted claim, confirm:

1. speaker identity and party;
2. transcript version and locator;
3. whether the content is verbatim, normalised or reconstructed;
4. effective date and known-at timestamp;
5. definition, period, perimeter and operating envelope;
6. linked questions and positions;
7. whether an independent route corroborates the content.

# Review compiler proposals

Open **Sources -> Compiler Review**.

## Candidate discrepancy

A discrepancy is a comparison proposal, not an automatic contradiction. Inspect:

- compared claims or derivations;
- aligned and non-aligned dimensions;
- values, units, period and perimeter;
- detector reason and confidence;
- whether a definition, time or operating-envelope difference explains the variance.

Choose **Admit discrepancy**, **Correct** or **Reject**. Admission acknowledges the inconsistency; it does not select one value as true.

## Deterministic derivation

Inspect the input claims, formula, units, assumptions, method version and hash. Admit the result only when the method and perimeter are appropriate.

## AI hypothesis

Treat an AI hypothesis as an explanation proposal. It remains ineligible for propagation before professional admission. Never use it as a derived fact.

## Spine change

A proposed question-spine change shows why the current decomposition is inadequate, which bindings migrate and which artifacts are affected. Material changes require the authority declared by the active Lens.

# Work with technical validation envelopes

Open **What the Deal Rests On**.

For each validation envelope, compare:

- target class;
- environment;
- configuration;
- test status;
- detection and classification ranges;
- evidence claims;
- uncovered dimensions.

A test in benign shallow water does not automatically support a claim for another target or environment. Condition edges show where support only survives if an explicit condition holds.

# Close unknowns through governed missions

Open **Everything We Still Do Not Know** or **Work**.

Each mission declares its objective, allowed and prohibited sources, data-egress rule, expected output, stop condition, authority class and reviewer.

- **Prepare** creates a mission draft and Registry event. It performs no research or outreach.
- **Run synthetic mission** is available only for policy-safe internal/read-only mock missions. It creates a synthetic source and review-required claim.
- **Request authority / cannot auto-run** indicates human contact, a physical test or another external effect. The bundled runtime will not perform it.

Do not interpret a prepared mission as completed work.

# Use the venture Scenario Lab

Open **Scenario Lab**.

The V20 financing section displays:

- pre-money, new money and post-money;
- pre- and post-round cap table;
- new-investor and founder ownership;
- instrument and governance terms;
- milestone tranches;
- follow-on reserve;
- base, delay and staged-financing scenarios.

Use Working scenarios to test runway, delayed technical proof, bridge need, dilution and ownership. Working never changes Current until a governed event is admitted and settled.

# Review a material change

The Tethys golden path uses the customer-scale coverage discrepancy.

1. Open **Change Arrival**.
2. Inspect the source passage and treatment proposal.
3. In **Change Review**, admit, edit or reject the professional treatment.
4. After admission, inspect **Change Impact**.
5. Confirm that the engine preserves both the asserted range and the pilot-implied value rather than overwriting either.
6. Inspect the open Human Stop and required authority verb.
7. Select explicit change sets in **Action Frontier**.

The maintenance scenario demonstrates a different path: maintenance economics are blocked because pilot evidence is not transferable to ports or cable routes. An independent region may settle only through explicit bounded partial settlement, and the blocked component remains visible.

# Use Decision Room and Execution Room

Decision Room opens only for a valid run and Candidate when the policy gate is satisfied.

- Compare admissible courses.
- Verify the Human Stop, Candidate, selected changes and authority scope.
- The attesting actor must be separate from viewer projection and must hold the required verb.
- A Defer course has no execution package.
- An external course creates an immutable, course-specific package only after attestation.

Execution Room shows READY until the server returns acknowledgement. A failure remains FAILED; the UI never reports optimistic success.

# Settle and replay

Settlement verifies:

- run and Candidate;
- as-of state;
- explicit selected changes;
- Human Stops and authority records;
- execution acknowledgement for external courses;
- blocked scope and partial-settlement choice;
- idempotency.

After settlement, open **Registry** for the append-only institutional trace and **Causal Replay** for historical reconstruction. Replay is read-only and event-derived.

# Change the as-of date

Use the date selector in the top bar. PANTA renders only information whose `known_at` is no later than the selected date. The historical projection may fall back to the Lens that was valid at that time; a future Lens cannot leak into a past view.

# Object Aperture reference

| Object | Basis highlights |
|---|---|
| Interaction | Participants, channel, consent, confidentiality and transcript state |
| Utterance | Speaker, locator, verbatim text and epistemic boundary |
| Claim | Source, definition, period, perimeter, class and question binding |
| Discrepancy | Compared objects, dimensions, values and review state |
| Derivation | Formula, inputs, assumptions, method hash and propagation eligibility |
| Hypothesis | AI origin, inputs, review state and non-deterministic status |
| Mission | Authority, allowed/prohibited sources, egress and stop condition |
| Spine Change | Proposed question, migration, affected artifacts and authority |
| Validation Envelope | Target, environment, configuration, test status and coverage |

# Mode and safety reminders

- Project Tethys is synthetic and contains no actual deal material.
- Mock Connected creates no external effects.
- The packaged mission runner does not contact a person or a live research service.
- Connected mode has no fixture fallback.
- Mobile is read/review-first; execute formal authority on an appropriate desktop surface.
- Production SSO/RBAC, Case Store persistence, external delivery and live compiler/runtime services are not included.
