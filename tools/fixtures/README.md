# PAN-36 extraction fixtures

`pan36_synthetic_model.xlsx` is a small, non-sensitive financial model used to
pin the Excel V2 extraction contract. It contains:

- scenario inputs with period, unit, and perimeter context;
- formula-backed model outputs on a separate sheet;
- no Keystone source data, names, or confidential values.

The `.xlsm` test copies this Open XML package to a temporary `.xlsm` path. The
extractor is read-only and intentionally treats `.xlsx` and `.xlsm` through the
same formula/cached-value parser; macro execution is out of scope.
