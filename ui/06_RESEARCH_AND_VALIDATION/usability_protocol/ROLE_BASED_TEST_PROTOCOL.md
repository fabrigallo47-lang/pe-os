# Role-Based Usability Test Protocol

Tasks, prompts and success criteria for investment professionals.

**Release:** V19.0.0  
**Date:** 27 August 2026

## 1. Research objective

Validate that investment professionals can understand source grounding, institutional state and required action quickly enough to trust PANTA in live underwriting and re-underwriting.

## 2. Target participants

| Role | Sample | Critical perspective |
| --- | --- | --- |
| Associate / analyst | 4-6 | Source inspection, corrections, work queue and artifact updates. |
| Principal / deal lead | 3-4 | Economic consequence, exception handling and authority routing. |
| Partner / IC member | 3-4 | Situation awareness, dissent, decision boundary and attestation. |
| Operating / portfolio lead | 2-3 | Post-underwriting state, intervention and replay. |
| Modeling / finance specialist | 2-3 | Cell/formula fidelity, lineage and scenario mechanics. |

## 3. Critical task set

- Ingest a new PDF and find its extracted claim.
- Correct a mis-bound claim and verify persistence.
- Locate every claim supporting a question.
- Inspect a workbook cell, formula and precedent.
- Switch as-of state and explain what changed.
- Complete the material-change golden path.
- Attempt an illegal Decision Room access and explain the block.
- Switch cases and confirm no residual data contamination.

## 4. Metrics

| Metric | Target |
| --- | --- |
| Time to orient in Fund Command | < 30 seconds |
| Time to trace a claim to source | < 20 seconds |
| Question-binding comprehension | >= 90% correct |
| State distinction: Working/Current/Approved | >= 90% correct |
| Authority-gate comprehension | >= 95% correct |
| Source-ingest completion awareness | >= 90% notice correct stage/result |
| Critical-task completion | >= 85% unassisted |
| Severe trust error | 0 |

## 5. Test protocol

- Use think-aloud without explaining the architecture in advance.
- Run one connected-like synthetic session and one negative path.
- Capture task time, error, hesitation, recovery, confidence and correction burden.
- Replay the session and ask participants to reconstruct what was known, believed, approved and open.
- Separate product confusion from missing backend capability.

## 6. Accessibility validation

- Keyboard-only complete path.
- Screen reader on mode chooser, Source Center, Object Aperture, Decision Room and status announcements.
- Zoom 200% and text spacing.
- prefers-reduced-motion and manual override.
- Contrast and non-color state labels.
- Viewport matrix: 1920, 1600, 1440, 1280, 1051, 1050, 1024, 768 and 390.

## 7. Research outputs

- Prioritized findings with severity and affected role.
- Task-flow failure map.
- Terminology/copy corrections.
- Component and contract changes.
- Validated demo sequence.
- Go/no-go recommendation for ACE and Scout pilots.
