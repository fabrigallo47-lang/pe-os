---
title: "PANTA V20 UI System and Engineering Handoff"
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

# Scope

V20 is an additive extension of the V19.B design system. The universal shell, room geometry, semantic colours, typography, responsive rules and motion grammar remain intact. New venture objects use generic components and projection data.

# New component inventory

| Component | Data contract | Primary surfaces |
|---|---|---|
| Archetype card | `deal.archetype` | Deal Command |
| Lens selector | `deal.lenses`, context `active_lens_id` | Global top bar |
| Criticality decomposition | question/unknown `decision_axes` | Deal Command, Unknowns |
| Interaction card | Interaction + Participant | Sources |
| Utterance list and aperture | Utterance + Participant | Sources, Object Aperture |
| Discrepancy proposal | Discrepancy Candidate | Compiler Review |
| Derivation formula card | Derivation | Compiler Review, Object Aperture |
| Hypothesis proposal | Hypothesis | Compiler Review |
| Spine-change card | Spine Change Proposal | Compiler Review |
| Mission card | Agent Mission | Work, Unknowns, Object Aperture |
| Validation envelope | Validation Envelope | Foundations |
| Condition edge | Condition Edge | Foundations |
| Venture financing summary | Venture Financing | Scenario Lab |
| Cap-table table | Venture Financing cap-table arrays | Scenario Lab |

# Generic rendering rule

No component contains a case ID, company name, fixed claim ID, fixed economics or hardcoded question. All V20 components read the validated projection. The core-purity regression test scans frontend and server core code for fixture-specific facts.

# Interaction semantics

- Clicking an Interaction or Utterance opens Object Aperture.
- Compiler proposal buttons write through the API adapter.
- Lens change requests a new server projection; it never mutates local facts.
- Mission Prepare and Run are separate controls.
- Human-contact and physical-test missions use refusal copy rather than a disabled-looking success path.
- All material state changes return a Registry update.

# Epistemic content design

The UI must use distinct labels:

| Object | Label |
|---|---|
| Statement occurrence | Observed speech act |
| Domain content | Asserted claim |
| Arithmetic | Deterministic derivation |
| AI explanation | AI hypothesis - not a derived fact |
| Firm decision | Institutional act |
| External attestation | Attested |

No colour alone may carry this distinction.

# Lens implementation

The server returns question order, ranking weights, required questions, controls and a facts hash. The UI displays the active Lens and facts-hash stability. A Lens selector is hidden at fund scale and on mobile where it would displace critical reading space.

# Responsive behavior

- At 1440 px and above, full command-centre composition.
- At 1024-1439 px, rails collapse or overlay.
- Below 768 px, read/review-first mode.
- The four-axis grid becomes two columns, then a compact stack.
- Compiler Review moves from two columns to one.
- Venture financing summary moves from six columns to three, then two.
- Cap table and instrument details stack on mobile.

# Accessibility

- Lens selector has a programmatic label.
- Proposal and mission controls remain native buttons.
- Object Aperture retains focus trapping and restoration.
- Utterance quotes are text, not image-only evidence.
- Effective and known-at dates remain visible in text.
- Status pills contain text labels.
- Reduced-motion mode removes semantic animation without hiding causal order.
- Mobile authority remains unavailable rather than inaccessible.

# Motion

The existing Reveal, Bind, Ripple, Branch, Route, Attest and Settle verbs remain. New proposal objects use Reveal and Bind; they do not Ripple until admitted. Mission preparation uses Route. Human outreach never animates as completed in the packaged runtime.

# Frontend files

| File | V20 responsibility |
|---|---|
| `src/v20_extension.js` | Venture object rendering, Lens, proposals, missions and Object Aperture branches |
| `v20.css` | Additive component and responsive styles |
| `src/contracts.js` | Runtime validation of V20 projection references and epistemic rule |
| `src/api.js` | Lens, compiler-proposal and mission API methods |
| `src/projection_adapter.js` | Pure transition mapping contract 20.0.0 |
| `src/selftest.js` | In-browser V20 checks |

# Backend boundary

The frontend never:

- computes authoritative economics;
- declares a contradiction resolved;
- upgrades an utterance-content claim to observed;
- creates authority records;
- creates execution packages;
- settles state;
- contacts a person or external service;
- falls back to fixtures in Connected mode.

# QA checklist

- All three cases render through the same components.
- Lens changes question order and preserves facts hash.
- Every Utterance resolves to Participant and Interaction.
- Compiler proposal states survive refresh.
- Hypothesis propagation remains false before admission.
- Human Stop and blocked component render from transition data.
- No success appears before server acknowledgement.
- All target viewports pass without clipping.
