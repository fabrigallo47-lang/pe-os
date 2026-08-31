# PANTA Semantic Handoff v0.2 — Release Notes

## Decisions now fixed

- Backend vocabulary is `StatedPosition` and `CaseReading`.
- UI vocabulary is **Position** and **Reading**.
- Economic/portfolio positions use `ExposurePosition`.
- The implementation hierarchy is now only:
  1. Universal Investment Kernel
  2. Strategy Archetype Pack with transaction flags
  3. Provisional Fund Lens
  4. Deal Frame
  5. Live Case State and Execution Mapping
- `CHALLENGES` is a semantic Compiler relation, not a frozen Dynamic relation.
- The Fund Lens schema is included as a provisional shape only.
- A blind benchmark specification is included; gold annotations remain a separate next artifact.

## Archetype versus Lens correction

The Buyout Pack now excludes institution-specific:
- thresholds and weights;
- evidence bars;
- return hurdles and supported-price policy;
- authority bodies and approval thresholds;
- mandatory artifacts and cadence;
- tool cost/duration and provider preferences;
- automatic-admission thresholds;
- operative-value selection policy.

Deal Frame and Question Engine were moved out of the Buyout Pack into the Universal Kernel because they are cross-strategy functions.

## Compatibility

This package is an upstream semantic handoff. It does not replace the frozen Dynamic contracts or conformance suite. A versioned adapter remains required.
