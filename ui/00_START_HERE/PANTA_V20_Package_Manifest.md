---
title: "PANTA V20 Package Manifest"
author: "PANTA Product and Engineering"
date: "27 August 2026"
lang: en-GB
geometry: margin=0.72in
fontsize: 10pt
colorlinks: true
linkcolor: blue
urlcolor: blue
toc: true
toc-depth: 2
numbersections: true
---

# Release identity

- **Product:** PANTA Deal World
- **Release:** V20
- **Semantic version:** 20.0.0
- **Base:** V19.B / 19.1.0
- **Release class:** additive venture/deep-tech product extension with V19.B integrity non-regression
- **Status:** complete product-experience, frontend, synthetic fixture and integration-handoff release

V20 extends the one Live Investment Case kernel to conversation-heavy, sparse-evidence, early-stage venture diligence. It preserves the V19.B rooms, state model, authority, execution, settlement, bitemporal replay, fixture-free Connected core and explicit operating modes.

# Package entry points

- macOS launcher: `01_PRODUCT_BUILD/launchers/START_PANTA_V20.command`
- Windows launcher: `01_PRODUCT_BUILD/launchers/START_PANTA_V20_WINDOWS.bat`
- Offline demo: `01_PRODUCT_BUILD/launchers/OPEN_OFFLINE_DEMO.html`
- Start guide: `00_START_HERE/README_START_HERE.md`
- Release report: `00_START_HERE/PANTA_V20_Release_and_Acceptance_Report.pdf`

# Principal deliverables

1. `PANTA_V20_Release_and_Acceptance_Report.pdf`
2. `PANTA_V20_Package_Manifest.pdf`
3. `02_PRODUCT_EXPERIENCE/PANTA_V20_Product_Experience_Specification.pdf`
4. `02_PRODUCT_EXPERIENCE/PANTA_V20_Product_User_Guide.pdf`
5. `03_SCREEN_ATLAS/PANTA_V20_Annotated_Screen_Atlas.pdf`
6. `04_INFORMATION_ARCHITECTURE_AND_FLOWS/PANTA_V20_Navigation_Flows_and_State_Model.pdf`
7. `05_DESIGN_SYSTEM_AND_INTERACTION/PANTA_V20_UI_System_and_Engineering_Handoff.pdf`
8. `06_RESEARCH_AND_VALIDATION/PANTA_V20_UX_Research_and_Validation_Plan.pdf`
9. `07_ENGINEERING_CONTRACTS_AND_ADAPTERS/PANTA_V20_Venture_Integration_Contract.pdf`
10. `07_ENGINEERING_CONTRACTS_AND_ADAPTERS/API/PANTA_V20_API_REFERENCE.pdf`
11. `08_TEST_EVIDENCE/PANTA_V20_Test_Evidence_Report.pdf`

Editable Markdown sources are packaged beside or beneath the corresponding PDFs.

# Implemented product layer

## New V20 objects

- Interaction, Participant and Utterance;
- hierarchical venture archetype and governed Lens;
- Candidate Discrepancy;
- deterministic Derivation;
- AI Hypothesis;
- Agent Mission;
- Spine Change Proposal;
- Condition Edge;
- Validation Envelope;
- venture financing, cap table, dilution, runway, milestones, governance and reserves.

## Synthetic benchmark cases

- **PROJECT-KEYSTONE:** buyout benchmark;
- **PROJECT-ORION:** growth-equity benchmark;
- **PROJECT-TETHYS:** pre-revenue deep-tech venture benchmark.

Tethys is wholly synthetic and resynthesized. It contains no actual Pelagon, ACE or confidential deal material.

# Product evidence

- 51 packaged screen states: 40 inherited V19/V19.B core surfaces and 11 V20 venture-extension states;
- 20 rendered architecture/flow diagrams, including six V20 diagrams;
- one 1920x1080 V20 venture walkthrough;
- three fixture packs served through the same generic frontend;
- 23 typed public JSON Schemas;
- pure compiler-bundle and Transition Engine adapters;
- stateful synthetic Mock Connected API;
- date-driven bitemporal projections and event-derived read-only replay.

# Acceptance evidence

The packaged suite reports **49/49 passing checks**. Coverage includes:

- fixture independence and confidential-safe resynthesis;
- transcript epistemic boundaries;
- generated discrepancies and deterministic derivations;
- hypothesis admission boundaries;
- mission authority and data-egress policy;
- Lens facts-hash purity;
- governed spine changes;
- venture-financing reconciliation;
- bitemporality and replay;
- Human Stop and blocked-region behavior;
- authority, execution, settlement and idempotency negative paths;
- browser rendering, mobile read/review and console cleanliness.

Machine-readable results are in `08_TEST_EVIDENCE/V20_TEST_RESULTS.json`.

# Package topology

| Directory | Role |
|---|---|
| `00_START_HERE` | release identity, reading order, manifest and integrity controls |
| `01_PRODUCT_BUILD` | runnable frontend, synthetic reference API, fixtures and launchers |
| `02_PRODUCT_EXPERIENCE` | product specification and user guide |
| `03_SCREEN_ATLAS` | inherited core screens, V20 screens, contact sheets and manifests |
| `04_INFORMATION_ARCHITECTURE_AND_FLOWS` | diagrams, editable sources and state/navigation model |
| `05_DESIGN_SYSTEM_AND_INTERACTION` | UI system, components, accessibility, responsive and motion |
| `06_RESEARCH_AND_VALIDATION` | validation plan, audits, metrics and protocols |
| `07_ENGINEERING_CONTRACTS_AND_ADAPTERS` | schemas, API, adapters, samples and integration contract |
| `08_TEST_EVIDENCE` | executable suite, results and browser evidence |
| `09_DEMO` | fixture mirrors, golden path and V20 walkthrough |
| `10_REFERENCE_ARCHIVE` | superseded V16-V19.B material, clearly separated from the active release |

# Authority and precedence

The precedence hierarchy remains:

1. frozen versioned machine contracts and conformance tests;
2. the latest applicable Engineering Source of Truth;
3. V18/V19.B integrity contracts;
4. V20 product and integration specifications;
5. screenshots, walkthroughs and synthetic runtime behavior.

No mock behavior may weaken a stricter frozen contract.

# Production boundary

The release does not certify:

- production authentication, SSO or enterprise RBAC;
- tenant-aware production Case Store persistence;
- a live autonomous research service;
- human outreach or physical-test execution;
- real external delivery or write-back;
- Fabrizio's production compiler/Case Store;
- Anto's independently deployed production Transition Engine or its separate full conformance evidence.

Connected mode deliberately refuses fixture-backed data. Mock Connected and Offline Demo are persistently disclosed as synthetic and without external effects.

# Integrity controls

- `PACKAGE_MANIFEST.json` records release facts and principal artifacts.
- `PACKAGE_INVENTORY.csv` lists substantive payload files, sizes, MIME types, roles and hashes.
- `CHECKSUMS.sha256` covers every regular package file except itself.
- `INTEGRITY_SUMMARY.json` records the verification rule and acceptance baseline.
- No nested ZIP archives, symlinks, runtime sessions, uploads, bytecode or cache files are included.
