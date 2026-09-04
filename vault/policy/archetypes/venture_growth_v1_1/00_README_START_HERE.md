# PANTA Venture & Growth Archetypes v1.1

## Release status

**Implementation candidate pending blind performance validation.**

The semantic architecture has been re-audited, strengthened and stripped of identifiable source material. It contains
no named institution, fund, person, company, deal, portfolio, proprietary document or source reference.

The package is designed to help PANTA form a bounded, live underwriting case. It is not a universal questionnaire
and it is not a populated Fund Lens.

## Architecture

```text
Universal Kernel
    ↓
Archetype configuration
    ├─ primary Archetype + optional secondary modules
    ├─ maturity module
    ├─ business-model modules
    ├─ sector overlays
    └─ transaction modules
    ↓
Provisional or validated Fund Lens
    ↓
Deal Frame
    ↓
Live Investment Case
```

The Runtime remains separate:

```text
Sources and interactions
    ↓
Physical extraction
    ↓
Context retrieval
    ↓
AI Semantic Compiler
    ↓
Canonical ledger event
    ↓
Live Case projection + dependency graph
    ↓
Dynamic
    ↓
Agents, artifacts and user surfaces
```

## Core packs

### `01_venture_archetype_pack_v1_1.yaml`

Venture grammar:

> Underwrite a proof-and-financing path toward an enterprise state that does not yet exist at repeatable scale.

Contains:

- 10 workstreams;
- 50 reusable Question families;
- 49 concept seeds;
- technical and commercial proof ladders;
- milestone, runway, financing, dilution and security-outcome model grammar;
- Compiler, open-world and human-boundary rules.

### `02_growth_archetype_pack_v1_1.yaml`

Growth grammar:

> Underwrite the durability, repeatability, scalability and financing of an observable operating engine.

Contains:

- 10 workstreams;
- 50 reusable Question families;
- 53 concept seeds;
- exact revenue/customer identity;
- GTM, capacity, unit-economics, operating-leverage, capital and liquidity grammar;
- Compiler, open-world and human-boundary rules.

## Shared configuration

### `03_archetype_selection_and_shared_grammar_v1_1.yaml`

Defines:

- the common private-growth-capital grammar;
- Venture, Growth and Hybrid selection;
- prohibited shortcuts;
- workstream correspondence;
- the Question Activation Contract.

### `04_maturity_modules_v1_1.yaml`

Defines evidence-based maturity states:

- pre-product concept;
- product or technical proof;
- early commercial proof;
- early repeatability;
- scale and replication;
- institutional scale.

Maturity is selected from observable evidence, not financing-round labels. Different products or programs may carry separate scoped maturity assignments.

### `05_business_model_modules_v1_1.yaml`

Defines the economic unit, concepts, model grammar, evidence and failure mechanisms for:

- recurring subscription;
- usage or consumption;
- transaction processing or take-rate;
- marketplace or network;
- asset- or volume-based fee;
- commerce or inventory;
- hardware or equipment;
- installed base plus recurring;
- services or tech-enabled services;
- project or contracted program;
- licensing, royalty or milestone;
- advertising or data monetization;
- balance-sheet or risk-bearing models.

### `06_sector_overlay_candidates_v1_1.yaml`

Contains abstract candidate overlays for domain-specific technical, regulatory, physical or procurement evidence.

They remain candidate-only until dedicated validation.

### `07_transaction_modules_v1_1.yaml`

Contains 16 reusable modules covering primary, follow-on, bridge/recapitalization, secondary transactions, convertible and priced equity, governance, intermediated exposure, public transition, inorganic growth, exit processes, tranched financing, structured preferred terms and cross-border structures.

### `08_provisional_fund_lens_surface_v1_1.yaml`

Defines only the categories through which an institution may configure PANTA.

It contains no institutional values and is not an approved or populated Lens.

## Assurance and implementation

- `09_archetype_vs_fund_lens_audit_v1_1.yaml`
- `10_quality_assurance_report_v1_1.md`
- `11_compiler_integration_contract_v1_1.md`
- `12_blind_benchmark_spec_v1_1.yaml`
- `13_kernel_compatibility_matrix_v1_1.yaml`
- `14_confidentiality_audit_v1_1.json`
- `schemas/`
- `examples/`
- `VALIDATION_RESULTS.txt`
- `CONTENT_AUDIT.txt`
- `CHECKSUMS.sha256`

## Critical operating rules

1. Archetype membership follows economic necessity, not observed frequency.
2. The packs are Question libraries, not compulsory questionnaires.
3. The Deal Frame and scope-aware active modules select a bounded Question spine.
4. Category never establishes identity.
5. Business model and sector are separate dimensions.
6. A completed diligence method does not close a Question.
7. Similarity proposes context; it does not create canonical state.
8. The Compiler interprets; only canonical events enter the Dynamic.
9. No model output creates a human Position or Decision.
10. Material content that does not fit the configured pack remains visible as open-world residue.

## What “ready” means

Ready now:

- implementation of formation and routing;
- Compiler integration;
- synthetic and blind benchmark construction;
- client-like pilot testing.

Not yet proven:

- exceptional client performance;
- cross-institution universality;
- complete domain coverage for every sector and transaction;
- production precision, recall and correction burden.

Those claims require the blind benchmark in `12_blind_benchmark_spec_v1_1.yaml`.
