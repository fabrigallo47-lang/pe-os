# PAN-36 extraction fixtures

`pan36_synthetic_model.xlsx` is a small, non-sensitive financial model used to
pin the Excel V2 extraction contract. It contains:

- scenario inputs with period, unit, and perimeter context;
- formula-backed model outputs on a separate sheet;
- no Keystone source data, names, or confidential values.

The `.xlsm` test copies this Open XML package to a temporary `.xlsm` path. The
extractor is read-only and intentionally treats `.xlsx` and `.xlsm` through the
same formula/cached-value parser; macro execution is out of scope.

`pan51_formula_model.xlsx` expands the formula contract with arithmetic,
cross-sheet and range references, a defined name, `IF`, `VLOOKUP`, an external
workbook link, an unsupported function, and a formula feeding a key underwriting
output. It intentionally has no calculated cache: the bounded evaluator must
recompute the six supported acyclic formulas, while the external link and
unsupported function remain unknown/Human Stop. `pan51_formula_expectations.json`
pins the exact formulas, dependencies and classifications. Rebuild the synthetic workbook with
`python tools/build_pan51_fixture.py`; no private deal data is embedded.
