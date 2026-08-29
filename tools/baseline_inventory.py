#!/usr/bin/env python3
"""Inventory the reproducible PANTA baseline without copying private inputs.

The command checks the versioned repository contracts plus the external
Keystone, transition-handoff, and independent-validator packages. Scout and
Replay inputs are inventoried as governed future inputs: their absence does not
invalidate the current Keystone baseline, but their access status is explicit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parent.parent
WORKSPACE = ROOT.parent

REPO_CONTRACTS = (
    "backend/dynamics/schemas/canonical_investment_case.schema.json",
    "backend/dynamics/schemas/state_transition_engine_output.schema.json",
    "backend/dynamics/schemas/state_transition_event.schema.json",
    "backend/dynamics/schemas/state_transition_execution_mapping.schema.json",
    "backend/dynamics/benchmark/transition_engine_conformance_cases_v1.json",
    "backend/dynamics/canonical/PANTA_Keystone_Initial_IC_State_2026-03-10.json",
    "tools/fixtures/pan36_synthetic_model.xlsx",
    "tools/fixtures/pan51_formula_model.xlsx",
    "tools/fixtures/pan51_formula_expectations.json",
)

PACKAGE_SPECS = {
    "keystone": {
        "marker": "CHECKSUMS.sha256",
        "required": (
            "CHECKSUMS.sha256",
            "benchmark/BENCHMARK_MANIFEST.json",
            "canonical/PANTA_Keystone_Canonical_Investment_Case_v1.1.json",
            "source_materials/layer_1_ingested/keystone_seller_cim.md",
            "source_materials/layer_1_ingested/keystone_lbo_model_working.xlsx",
        ),
        "candidates": (
            WORKSPACE / "PANTA_Keystone_Canonical_Investment_Case_v1_1",
            Path.home() / "Downloads" / "PANTA_CIC_v1.1" /
            "PANTA_Keystone_Canonical_Investment_Case_v1_1",
        ),
    },
    "handoff": {
        "marker": "PACKAGE_MANIFEST.json",
        "required": (
            "PACKAGE_MANIFEST.json",
            "benchmark/transition_engine_conformance_cases_v1.json",
            "canonical/PANTA_Keystone_Canonical_Investment_Case_v1.1.json",
            "schemas/state_transition_engine_output.schema.json",
        ),
        "candidates": (
            WORKSPACE / "PANTA_STATE_TRANSITION_ENGINE_HANDOFF_V1",
            Path.home() / "Downloads" / "PANTA_STATE_TRANSITION_ENGINE_HANDOFF_V1" /
            "PANTA_STATE_TRANSITION_ENGINE_HANDOFF_V1",
        ),
    },
    "validator": {
        "marker": "KIT_VERSION.json",
        "required": (
            "KIT_VERSION.json",
            "RELEASE_MANIFEST.json",
            "validate_bundle.py",
            "run_validator_tests.py",
        ),
        "candidates": (
            WORKSPACE / "PANTA_V7_INDEPENDENT_VALIDATOR",
            Path.home() / "Downloads" / "PANTA_V7_INDEPENDENT_VALIDATOR",
        ),
    },
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def resolve_package_root(
    explicit: Path | None,
    candidates: Iterable[Path],
    marker: str,
) -> Path | None:
    ordered = ([explicit] if explicit else []) + list(candidates)
    for candidate in ordered:
        if candidate is None:
            continue
        root = candidate.expanduser().resolve()
        if (root / marker).is_file():
            return root
    return None


def package_record(name: str, root: Path | None, required: Iterable[str]) -> dict:
    required = tuple(required)
    missing = [] if root else list(required)
    files = []
    if root:
        for relative in required:
            path = root / relative
            if path.is_file():
                files.append({"path": relative, "sha256": sha256_file(path)})
            else:
                missing.append(relative)
    return {
        "name": name,
        "status": "ready" if root and not missing else "missing",
        "root": str(root) if root else None,
        "files": files,
        "missing": missing,
    }


def repo_contract_record() -> dict:
    return package_record("repository_contracts", ROOT, REPO_CONTRACTS)


def governed_input_record(
    name: str,
    path: Path | None,
    environment_variable: str,
    target_gate: str,
) -> dict:
    available = bool(path and path.expanduser().exists())
    return {
        "name": name,
        "status": "ready" if available else "access-planned",
        "path": str(path.expanduser().resolve()) if available and path else None,
        "environment_variable": environment_variable,
        "target_gate": target_gate,
        "access_policy": (
            "Obtain owner permission, store outside Git, set the environment variable, "
            "then run the same schema and provenance gates used for Keystone."
        ),
    }


def build_inventory(args: argparse.Namespace) -> dict:
    packages = [repo_contract_record()]
    explicit_roots = {
        "keystone": args.keystone_root,
        "handoff": args.handoff_root,
        "validator": args.validator_root,
    }
    for name, spec in PACKAGE_SPECS.items():
        root = resolve_package_root(
            explicit_roots[name],
            spec["candidates"],
            spec["marker"],
        )
        packages.append(package_record(name, root, spec["required"]))

    external_inputs = [
        governed_input_record(
            "scout",
            args.scout_input,
            "PANTA_SCOUT_INPUT",
            "Gate 2 — 2026-09-02",
        ),
        governed_input_record(
            "replay",
            args.replay_input,
            "PANTA_REPLAY_INPUT",
            "Gate 3 — 2026-09-07",
        ),
    ]
    return {
        "schema_version": "panta-baseline-inventory-1.0",
        "core_ready": all(item["status"] == "ready" for item in packages),
        "packages": packages,
        "external_inputs": external_inputs,
        "validation_commands": [
            "make baseline",
            "make verify",
            ".venv/bin/python tools/test_baseline_inventory.py",
        ],
    }


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--keystone-root", type=Path)
    ap.add_argument("--handoff-root", type=Path)
    ap.add_argument("--validator-root", type=Path)
    ap.add_argument(
        "--scout-input",
        type=Path,
        default=Path(os.environ["PANTA_SCOUT_INPUT"])
        if os.environ.get("PANTA_SCOUT_INPUT") else None,
    )
    ap.add_argument(
        "--replay-input",
        type=Path,
        default=Path(os.environ["PANTA_REPLAY_INPUT"])
        if os.environ.get("PANTA_REPLAY_INPUT") else None,
    )
    ap.add_argument("--json", action="store_true", help="Print the full machine inventory")
    ap.add_argument(
        "--require-core",
        action="store_true",
        help="Exit non-zero unless repository, Keystone, handoff and validator are ready",
    )
    return ap


def main() -> int:
    args = parser().parse_args()
    inventory = build_inventory(args)
    if args.json:
        print(json.dumps(inventory, indent=2, ensure_ascii=False))
    else:
        print("PANTA reproducible baseline")
        for item in inventory["packages"]:
            print(f"  {item['name']:<24} {item['status'].upper()}")
        for item in inventory["external_inputs"]:
            print(f"  {item['name']:<24} {item['status'].upper()} ({item['target_gate']})")
    return 1 if args.require_core and not inventory["core_ready"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
