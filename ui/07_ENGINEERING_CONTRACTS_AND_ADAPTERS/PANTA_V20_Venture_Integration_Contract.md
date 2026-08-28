---
title: "PANTA V20 Venture Integration Contract"
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

# Contract status

This document defines the integration boundary added by V20. Frozen Transition Engine contracts and conformance tests continue to outrank this prose. The frontend consumes validated projections; it does not invent domain facts or institutional state.

# Service boundaries

| Producer | Output | Consumer |
|---|---|---|
| Interaction ingestion | Interaction, Participant, Utterance and source version | Compiler/Case Store |
| Semantic compiler | Claims, bindings, derivation specs, discrepancy rules, validation envelopes | Proposal service/frontend |
| Proposal service | Discrepancy candidates, deterministic derivations, AI hypotheses, spine proposals | Professional review |
| Case Store | Validated bitemporal frontend projection | Browser |
| Transition Engine | Frozen output plus `source_event_id` | Transition adapter/browser |
| Authority service | Scoped authority record | Execution/settlement |
| Mission service | New source and review-required claims | Case Store |

# Compiler bundle

`schema_version` must equal `compiler-bundle/20.0` and `case_id` must match the base projection. Collections include participants, interactions, utterances, claims, derivation specs, discrepancy rules, missions, spine proposals, condition edges, validation envelopes, sources, lenses, archetype and venture financing.

The pure adapter is:

`07_ENGINEERING_CONTRACTS_AND_ADAPTERS/adapters/compiler_projection_adapter.py`

It performs no model inference, discrepancy detection, economics, authority or settlement.

# Transition integration

The frozen engine output has eighteen required fields. V20 requires `source_event_id` as the nineteenth integration-binding field. The pure adapter preserves engine order and may only add direct display aliases.

`07_ENGINEERING_CONTRACTS_AND_ADAPTERS/adapters/transition_runtime_adapter.py`

# New object invariants

## Interaction

- every participant ID resolves;
- source and version are immutable references;
- effective and known-at dates are present;
- confidentiality, consent and model/export permissions are explicit.

## Utterance

- interaction and speaker resolve;
- locator and verbatim text are present;
- attribution confidence is explicit;
- an utterance does not itself set domain-content epistemic class.

## Discrepancy Candidate

- carries source object IDs and semantic dimensions;
- `automatic_truth_change` is false;
- remains proposed until reviewed.

## Derivation

- carries input IDs, formula, units, assumptions, method version and hash;
- must be reproducible;
- remains ineligible for propagation until admitted.

## Hypothesis

- origin is AI reasoning proposal;
- epistemic class is asserted;
- is not labelled derived;
- remains ineligible for propagation until admitted.

## Mission

- declares authority, allowed/prohibited sources, egress and stop condition;
- preparation has no external effect;
- human contact and physical tests cannot auto-run;
- result is a new source, never a silent fact update.

## Spine Change

- declares migration and affected artifacts;
- preserves aliases/history;
- material acceptance requires Lens-provided authority.

# Bitemporal contract

All material V20 objects carry `effective_date` and `known_at`. Historical projection filters by `known_at`; replay resolves to Registry events and is read-only.

# Lens contract

A Lens may alter ranking, question order, required questions, controls, materiality and authority policies. It may not modify source facts or Registry events. The projection returns `lens_projection.facts_hash` for non-regression.

# Mission boundary

The packaged server supports only synthetic no-external-effect mission output. Production mission execution requires:

- authenticated actor and authority;
- tenant and confidentiality policy;
- provider allowlist;
- prompt/context redaction;
- data-egress logging;
- source retrieval trace;
- legal and regulatory controls;
- idempotency and durable event storage.

# Error codes

| Code | Meaning |
|---|---|
| `CONNECTED_BACKEND_NOT_CONFIGURED` | Bundled runtime refuses Connected mode |
| `SPINE_AUTHORITY_REQUIRED` | Actor lacks authority to admit material spine change |
| `MISSION_AUTHORITY_REQUIRED` | Human/physical/external mission cannot auto-run |
| `CANDIDATE_CONTEXT_MISMATCH` | Authority request is not scoped to the run Candidate |
| `UNKNOWN_CHANGE_ID` | Prepared change is outside transition output |
| `IDEMPOTENCY_CONFLICT` | Key reused with a different payload |
| `SETTLEMENT_INVARIANT_FAILED` | Settlement gate rejected the request |

# Samples

- `sample_v20_compiler_bundle.json`
- `sample_v20_base_projection_shell.json`
- `sample_v20_compiler_projection.json`
- `sample_venture_engine_output.json`
- `sample_venture_frontend_transition.json`

The sample compiler bundle passes the pure adapter and the resulting projection validates with zero schema errors. The sample engine output passes the 19-field transition adapter and validates with zero schema errors.
