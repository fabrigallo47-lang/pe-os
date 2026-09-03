# Reproducible baseline and input access plan

This document is the operating record for PAN-5. It freezes the current
Keystone baseline without committing deal material or credentials to Git.

## One-command checks

```bash
make setup
make baseline
make verify
```

`make baseline` hashes the versioned schemas, conformance suite, canonical
state and synthetic workbook in the repository. It also discovers and hashes
the required marker files from the external Keystone package, transition
handoff and independent validator. Use `--json` for a machine-readable record:

```bash
.venv/bin/python tools/baseline_inventory.py --require-core --json
```

Absolute local paths are reported at runtime only. They are never written into
the repository.

## Frozen core

| Component | Contract | Validation |
|---|---|---|
| Repository schemas | `backend/dynamics/schemas/*.json` | `make baseline` |
| Transition behavior | versioned conformance cases and canonical IC state | `make verify` |
| Extraction integration | synthetic `.xlsx` fixtures with stable cell locators and formula/dependency Human Stops | `tools/test_pan36.py`; `backend/dynamics/tests/test_pan51_excel_formulas.py` |
| Keystone package | package checksum file, benchmark manifest, canonical CIC and source markers | `make baseline` |
| Runtime handoff | package manifest, conformance suite, canonical CIC and output schema | `make baseline` |
| Independent validator | version marker, release manifest and validator entrypoints | `make baseline` and `make verify` |

The schema-valid integration example is the versioned PAN-36 synthetic
workbook plus its E3-to-runtime contract test. The definitive validation
command remains `make verify`, which exercises regressions, the extraction
adapter, runtime behavior, persistence and the independent bundle validator.

## External-input inventory and access plan

| Input | Repository policy | Access mechanism | Target |
|---|---|---|---|
| Keystone | Never commit source files or derived deal memory | Keep the approved package outside Git; pass its root to the inventory/extractor | Current baseline |
| State-transition handoff | Never fork a private copy into application code | Keep the approved package outside Git; verify its package manifest and conformance suite | Current baseline |
| Scout proof source | Do not ingest until the source owner authorizes evaluation use | Store outside Git and set `PANTA_SCOUT_INPUT`; run the Keystone schema, provenance and grounding gates | Gate 2 — 2 Sep 2026 |
| Replay case | Do not ingest validation-only or answer-key material as evidence | Store outside Git and set `PANTA_REPLAY_INPUT`; validate temporal boundaries before admission | Gate 3 — 7 Sep 2026 |

Missing Scout or Replay material is reported as `ACCESS-PLANNED`, not silently
treated as available. It does not invalidate the frozen Keystone baseline, but
the corresponding roadmap gate cannot close until permission and material are
present.

## Reproduction sequence

1. Run `make baseline` and retain the JSON output with the test evidence.
2. Run `make verify`; no skipped core package may be represented as executed.
3. For a fresh extraction, point `extract_v2_physical.py --input-dir` at the approved
   external source directory. Do not copy sensitive sources into `vault/inbox`
   merely to satisfy a test.
4. Compare hashes and manifests before admitting evidence into Current.
5. Record any package replacement as a new baseline; never overwrite the prior
   checksum record.
