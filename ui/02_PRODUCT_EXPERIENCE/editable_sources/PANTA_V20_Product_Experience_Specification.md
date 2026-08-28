---
title: "PANTA V20 Product Experience Specification"
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

# Release definition

PANTA V20 extends the existing Live Investment Case from document-heavy buyout and growth underwriting to conversation-heavy, sparse-evidence, early-stage venture diligence. It does not create a separate venture product and it does not redesign V19.B. The same rooms, institutional states, authority chain, fixture-free core and deterministic transition boundary remain in force.

**Release:** V20 / 20.0.0  
**Base:** V19.B / 19.1.0  
**Release class:** venture/deep-tech extension with V19.B non-regression  
**Reference venture fixture:** Project Tethys, fully synthetic and resynthesised  
**Executable evidence:** 49/49 bundled acceptance and regression checks

## Product promise

> PANTA builds the investment case and keeps it alive.

The promise now applies across three structurally distinct packaged cases:

| Case | Archetype | Primary grammar | Purpose |
|---|---|---|---|
| Keystone | Buyout | EBITDA definitions, leverage, support sets, approved EV ceiling | Canonical LBO benchmark |
| Orion | Growth equity | ARR, retention, onboarding, runway, milestone-linked primary financing | Growth generalisation |
| Tethys | Pre-revenue deep-tech venture | Interactions, technical validation, procurement, runway, dilution and milestone risk | Sparse-evidence venture generalisation |

No case may determine generic frontend behaviour. Connected mode never imports fixture data and the bundled server refuses Connected mode unless a real backend is supplied.

# Product thesis

## One kernel, multiple archetypes

![Archetype hierarchy](../04_INFORMATION_ARCHITECTURE_AND_FLOWS/DIAGRAMS/15_V20_Archetype_Hierarchy.png)

The hierarchy is:

1. Universal PANTA kernel - one persistent Live Investment Case.
2. Deal archetype - buyout, growth or venture.
3. Stage overlay - for example pre-revenue seed.
4. Sector overlay - for example deep-tech maritime security.
5. Fund Lens - policies, gates, authority, evidence requirements and ranking.
6. Deal instance - the concrete investment case.
7. Governed question spine - the current institutional decomposition of the decision.

The archetype proposes a starting grammar. It does not become a compulsory questionnaire. A professional may add, split, merge, promote, demote or retire questions through a governed spine-change proposal.

## Universal evidence-to-decision chain

`Source -> Claim -> Underwriting Question -> Case Position -> Model or Economic Object -> Decision or Condition -> Outcome`

V20 adds native operating objects before and around that chain:

`Interaction -> Utterance -> observed speech act + asserted content -> discrepancy or derivation -> professional review -> admitted event`

# Institutional state model

The existing distinctions remain mandatory:

`Source Object -> Proposed interpretation -> Admitted Event -> Candidate -> Current -> Approved`

Parallel states include Working, Historical, Blocked, Unknown, Rejected and Superseded. The browser may project validated state; it may not invent authority, economics, causal edges, coverage or settlement.

| Distinction | V20 rule |
|---|---|
| Proposed vs admitted | A compiler or AI proposal does not propagate until reviewed and admitted. |
| Candidate vs Current | A deterministic transition result is not institutional state until settlement. |
| Current vs Approved | Current may move while historical Approved states remain immutable. |
| Observed speech act vs asserted content | A transcript can prove that a person said something without proving the proposition stated. |
| Derived result vs AI hypothesis | Arithmetic is deterministic; an explanatory hypothesis is not. |
| Lens vs facts | A Lens changes ranking, gates and required work, never source facts. |
| Replay vs Current | Historical reconstruction is read-only and may not create an institutional event. |

# Native interactions and speaker-level provenance

![Interaction provenance](../04_INFORMATION_ARCHITECTURE_AND_FLOWS/DIAGRAMS/16_V20_Interaction_Provenance.png)

V20 treats calls, meetings, customer references, expert interviews, IC discussions and uploaded transcripts as native Interactions rather than undifferentiated documents.

## Interaction object

Required fields include interaction type, start/end time, participants, organiser, channel, source and source version, transcript status, speaker-identification confidence, consent status, confidentiality class, model-processing permission, export permission, effective date and known-at timestamp.

## Utterance object

Required fields include speaker, role, party, interaction, timestamp locator, verbatim and normalised text, attribution confidence, text status, effective date and known-at timestamp.

## Epistemic split

For a statement such as “one node may not cover the site”, PANTA records two different propositions:

1. **Observed speech act:** the transcript records that the named speaker made the statement.
2. **Asserted domain proposition:** one node may not cover the site.

The first may be `observed`. The second remains `asserted` unless independently demonstrated. An institutional decision recorded in an IC transcript is classified `institutional_act`, not asserted or attested.

# Venture and deep-tech question grammar

The Tethys fixture instantiates nine starting questions:

1. Is the problem important, funded and actionable?
2. Does the product perform against the relevant target, environment and operating envelope?
3. Can it be deployed, operated and maintained economically?
4. Is there a credible customer and procurement path?
5. Can the company reach commercial proof before capital or strategic time expires?
6. Does differentiation survive realistic product and market conditions?
7. Can the team reach the next value-inflecting milestone?
8. What financing, ownership and governance structure appropriately funds that path?
9. Which regulatory, security or export-control constraints can block adoption?

Every question exposes decision axes rather than an opaque score:

- load-bearingness;
- epistemic fragility;
- severity if wrong;
- decision criticality and gate proximity;
- closure cost, time and probability of resolution.

# Compiler proposals

![Proposal boundaries](../04_INFORMATION_ARCHITECTURE_AND_FLOWS/DIAGRAMS/17_V20_Compiler_Proposal_Boundaries.png)

## Candidate discrepancies

The compiler generates discrepancy candidates from declarative rules. A candidate may identify:

- exact contradiction;
- numeric incompatibility;
- definition mismatch;
- perimeter mismatch;
- temporal supersession;
- conditional invalidation;
- magnitude or unit anomaly;
- missing reconciliation.

A discrepancy carries its compared objects, aligned and non-aligned dimensions, confidence, detector version, reason and review state. It never changes truth automatically.

## Deterministic derivations

A Derivation contains input claim IDs, formula, units, assumptions, perimeter, method version and method hash. Tethys demonstrates:

- nominal circular coverage area;
- implied radius from area and node count;
- runway from cash and burn;
- post-money ownership from pre-money and new money.

The result may only propagate after professional admission.

## AI hypotheses

AI explanations are separate proposal objects. They use `AI_REASONING_PROPOSAL` origin, remain `asserted`, show their input objects and are ineligible for propagation before admission.

## Governed spine changes

A Spine Change Proposal can create, promote, demote, split, merge, reformulate, retire or rebind a question. It records rationale, source objects, binding migration, affected artifacts, required authority and preserved historical aliases.

# Technical validation envelopes and conditions

A technical performance figure is not a scalar detached from operating conditions. The V20 validation envelope can carry:

- target class;
- environment;
- configuration;
- test status;
- detection and classification range;
- false-positive/false-negative context;
- evidence claims;
- coverage status.

Condition edges explicitly represent that one object only supports another when a stated condition holds. Failure may weaken, block or invalidate the downstream position without deleting the original evidence.

# Governed missions

![Governed missions](../04_INFORMATION_ARCHITECTURE_AND_FLOWS/DIAGRAMS/18_V20_Governed_Missions.png)

A Mission is linked to an Unknown or Question and declares objective, allowed sources, prohibited sources, confidential-context policy, data-egress policy, expected output, stop condition, authority class and reviewer.

| Mission class | Packaged behaviour |
|---|---|
| Deterministic internal analysis | May run synthetically; result requires review. |
| Policy-safe public research | Mock Connected produces an explicitly synthetic research source; no live service is contacted. |
| Confidential-context research | Requires an authorised service and egress policy; not claimed in V20. |
| Human outreach | May be prepared but never auto-runs. |
| Physical or controlled test | May be scheduled/prepared but never auto-runs. |

Every mission result enters as a new source with provenance and review-required claims. It is never silently admitted.

# Venture financing and Scenario Lab

![Venture financing](../04_INFORMATION_ARCHITECTURE_AND_FLOWS/DIAGRAMS/19_V20_Venture_Financing.png)

V20 adds native venture financing objects:

- pre-money, new money and post-money;
- pre- and post-round cap table;
- new-investor ownership;
- option-pool effects;
- liquidation preference, anti-dilution and board composition;
- milestone tranches;
- runway and delayed-milestone scenarios;
- follow-on reserve policy;
- next-round ownership sensitivity.

Scenario Lab keeps Working scenarios separate from Current. The reference case demonstrates base, six-month-delay and staged-tranche paths.

# Information architecture

No new top-level product is introduced.

| Existing surface | V20 extension |
|---|---|
| Sources | Interactions, transcripts, utterances, confidentiality and attribution |
| Claims Explorer | Speaker/party, utterance locator and assertion/observation split |
| Compiler Review | Discrepancies, derivations, hypotheses and spine changes |
| Deal Command | Venture archetype, governed Lens and decomposed criticality |
| Foundations | Validation envelopes and explicit condition edges |
| Unknowns and Work | Governed missions and closure-value decomposition |
| Scenario Lab | Round, dilution, runway, milestones and reserves |
| Decision Room | Invest, resize, tranche, condition, decline or defer |
| Registry | Interactions, reviews, missions, authority and settlement events |
| Causal Replay | What was known, believed, approved and open at a past date |
| Object Aperture | Interaction, Utterance, Derivation, Discrepancy, Hypothesis, Mission, Spine Change and Validation Envelope branches |

# Primary V20 operating flow

![End-to-end flow](../04_INFORMATION_ARCHITECTURE_AND_FLOWS/DIAGRAMS/20_V20_End_to_End.png)

1. An interaction or document enters as an immutable source version.
2. The compiler proposes claims and speaker-level bindings.
3. Declarative rules generate discrepancies and deterministic derivations.
4. AI hypotheses remain explicitly separate.
5. A professional admits, corrects or rejects proposals.
6. The admitted event is passed to the Transition Engine.
7. The engine returns affected set, dispositions, recomputations, Human Stops, blocked components and Candidate.
8. Work is ranked and missions may be prepared.
9. Authority is required where policy demands it.
10. External execution packages exist only for external-effect courses and require acknowledgement.
11. Canonical settlement moves selected consequences into Current while preserving blocked scope and Approved history.
12. Registry and Replay preserve the bitemporal path.

# Authority, execution and settlement

All V19.B invariants remain binding.

- Decision Room is unavailable without a valid run, Candidate and open Human Stop where required.
- Viewer projection, authenticated actor, authority assignment and attesting actor are separate.
- Authority is scoped to the same run, Candidate, Human Stop and course.
- Conflicting courses cannot coexist.
- Idempotency keys reject payload conflicts.
- Execution packages are server-derived and course-specific.
- Defer creates no package.
- No success state appears before positive acknowledgement.
- Settlement accepts only explicitly prepared change IDs from the transition output.
- A Human Stop cannot settle without a scoped authority record.
- Blocked scope requires explicit bounded partial settlement and remains visible afterward.

# Bitemporality and replay

Every material claim, interaction, utterance, mission, spine proposal, source event and Registry event carries:

- `effective_date`: when the underlying fact or act applies;
- `known_at`: when the case could legitimately know it.

The global as-of selector uses the knowledge axis. Replay snapshots are derived from the Registry event log, resolve to events carrying both dates and are read-only.

# Operating modes and truthfulness

| Mode | V20 behaviour |
|---|---|
| Connected | Requires a real backend; bundled server refuses to return fixtures. |
| Mock Connected | Stateful synthetic API; server-gated authority and settlement; no external effects. |
| Offline Demo | Explicit fixture; read/review-first; local synthetic calculations only. |
| Empty System | No injected case and no silent fallback. |

The packaged Mock Connected runtime does not claim production identity, production persistence, live research, human outreach, physical testing, external delivery, Fabri's production compiler or Anto's separate production runtime.

# Responsive and accessibility contract

- Desktop preserves the command-centre composition.
- Contextual rails collapse or overlay at intermediate widths.
- Below 768 px the product is read/review-first; formal authority is not compressed into mobile.
- Focus is preserved across regional renders.
- Object Aperture and command dialogs trap and restore focus.
- Semantic state uses text, icon and colour.
- Reduced motion follows system preference.
- No root-level live region is used.
- Operational typography remains at or above the existing V19.B baseline.

# Fixture and generalisation contract

Tethys is fully synthetic and resynthesised. It contains no actual company, founder, customer, expert or confidential practice material. Exact normalised statement overlap with Keystone and Orion is 0.0%. The venture case contains no LBO-specific quantities.

The same generic frontend renders all three cases without case-specific branches in core code. Fixture facts remain outside the connected core.

# Acceptance summary

The executable V20 suite passes 49/49 checks. It covers:

- three-case generalisation and core purity;
- interaction and utterance provenance;
- observed-speech-act epistemic separation;
- venture bitemporality;
- generated discrepancies and derivations;
- AI-hypothesis admission gate;
- governed missions and spine changes;
- venture financing arithmetic;
- Lens facts-hash stability;
- typed schemas and pure adapters;
- Connected-mode honesty;
- historical projection and read-only replay;
- Human Stop, authority, execution, blocked scope and settlement;
- idempotency and negative paths;
- eleven representative browser states.

# Production boundary and ownership

| Subsystem | V20 package | Production owner/boundary |
|---|---|---|
| Product experience and generic renderer | Implemented | Frontend/product |
| Synthetic fixture compiler behaviour | Implemented for Mock/Offline | Not a production compiler |
| Compiler bundle adapter | Pure and executable | Fabri/Case Store transport remains external |
| Transition output adapter | Pure and executable | Anto runtime remains external |
| Authority and settlement | Stateful synthetic server | Production identity/policy/store remains external |
| Research missions | Contracts plus synthetic results | Live research service and egress controls remain external |
| External execution | Simulated acknowledgement only | Real delivery integrations remain external |

# Non-negotiable continuation rules

Future releases must not:

- create a venture-specific frontend fork;
- promote transcript content to observed truth merely because it was independently spoken;
- label AI explanations as deterministic derivations;
- declare discrepancy candidates to be resolved contradictions automatically;
- let a Lens rewrite evidence;
- auto-run human contact or physical tests;
- silently import fixtures into Connected mode;
- weaken V19.B authority, settlement, bitemporal or replay invariants.
