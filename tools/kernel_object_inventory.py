#!/usr/bin/env python3
"""Audit the PAN-82 kernel-object map against live repository contracts."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parent.parent
INVENTORY_PATH = ROOT / "vault/policy/kernel_object_coverage_v0_2.json"
ALLOWED_CLASSIFICATIONS = {"ALREADY_COVERED", "RUNTIME_GAP", "SEMANTIC_ONLY"}
ALLOWED_IMPLEMENTATION_STATUSES = {"COMPLETE", "PARTIAL", "ABSENT"}


def load_inventory(path: Path = INVENTORY_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_json(relative: str) -> dict[str, Any]:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def _kernel_object_types(inventory: dict[str, Any]) -> set[str]:
    kernel_path = ROOT / inventory["kernel"]["source"]
    source = kernel_path.read_bytes()
    expected_hash = inventory["kernel"].get("source_sha256")
    actual_hash = hashlib.sha256(source).hexdigest()
    if expected_hash != actual_hash:
        raise ValueError(
            "kernel source changed; review every object classification before updating source_sha256"
        )
    kernel = yaml.safe_load(source.decode("utf-8"))
    return set(kernel["object_types"])


def _dynamic_output_types(inventory: dict[str, Any]) -> set[str]:
    schema = _load_json(inventory["frozen_contracts"]["dynamic_output_schema"])
    return set(schema["$defs"]["object_type"]["enum"])


def audit_inventory(inventory: dict[str, Any]) -> list[str]:
    """Return deterministic validation errors without changing any contract."""
    errors: list[str] = []
    if inventory.get("schema_version") != "kernel-object-coverage/1.0":
        errors.append("unsupported inventory schema_version")
    if inventory.get("status") != "ENGINEERING_AUDIT_NON_BINDING":
        errors.append("inventory must remain a non-binding engineering audit")

    try:
        kernel_types = _kernel_object_types(inventory)
    except (KeyError, OSError, ValueError, yaml.YAMLError) as exc:
        return [f"cannot load kernel object types: {exc}"]
    if len(kernel_types) != inventory.get("kernel", {}).get("object_type_count"):
        errors.append("kernel object_type_count does not match the source contract")

    entries = inventory.get("objects")
    if not isinstance(entries, list):
        return errors + ["objects must be an array"]
    names = [entry.get("kernel_type") for entry in entries if isinstance(entry, dict)]
    duplicates = sorted(name for name, count in Counter(names).items() if count > 1)
    if duplicates:
        errors.append("duplicate kernel mappings: " + ", ".join(duplicates))
    missing = sorted(kernel_types - set(names))
    extra = sorted(set(names) - kernel_types)
    if missing:
        errors.append("unmapped kernel types: " + ", ".join(missing))
    if extra:
        errors.append("unknown mapped kernel types: " + ", ".join(extra))

    contracts = inventory.get("frozen_contracts", {})
    try:
        canonical = _load_json(contracts["canonical_case_schema"])
        actual_defs = set(canonical["$defs"])
    except (KeyError, OSError, json.JSONDecodeError) as exc:
        errors.append(f"cannot load frozen canonical schema: {exc}")
        actual_defs = set()
    declared_defs = set(contracts.get("canonical_case_defs", []))
    if actual_defs != declared_defs:
        errors.append("canonical_case_defs drifted from the frozen schema")
    aliases = contracts.get("kernel_object_aliases", {})
    aliased_defs = {
        schema_def
        for mapped_defs in aliases.values()
        for schema_def in mapped_defs
    }
    non_kernel_defs = set(contracts.get("non_kernel_graph_defs", []))
    if aliased_defs & non_kernel_defs:
        errors.append("a frozen schema def is both a kernel alias and graph-only")
    if aliased_defs | non_kernel_defs != declared_defs:
        errors.append("frozen schema defs are not fully classified")

    try:
        actual_dynamic_types = _dynamic_output_types(inventory)
    except (KeyError, OSError, json.JSONDecodeError) as exc:
        errors.append(f"cannot load Dynamic output object types: {exc}")
        actual_dynamic_types = set()
    if actual_dynamic_types != set(contracts.get("dynamic_output_object_types", [])):
        errors.append("dynamic_output_object_types drifted from the output schema")

    classifications: Counter[str] = Counter()
    statuses: Counter[str] = Counter()
    dynamic_types = set(contracts.get("dynamic_mutation_object_types", []))
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"objects[{index}] must be an object")
            continue
        name = str(entry.get("kernel_type") or f"objects[{index}]")
        classification = entry.get("classification")
        implementation_status = entry.get("implementation_status")
        classifications[str(classification)] += 1
        statuses[str(implementation_status)] += 1
        if classification not in ALLOWED_CLASSIFICATIONS:
            errors.append(f"{name}: invalid classification {classification!r}")
        if implementation_status not in ALLOWED_IMPLEMENTATION_STATUSES:
            errors.append(f"{name}: invalid implementation_status {implementation_status!r}")
        if classification == "ALREADY_COVERED" and implementation_status == "ABSENT":
            errors.append(f"{name}: covered object cannot be ABSENT")
        if classification == "RUNTIME_GAP" and not entry.get("follow_up_issue"):
            errors.append(f"{name}: runtime gap needs an explicit follow-up")
        mutation_type = entry.get("dynamic_mutation_type")
        if mutation_type is not None and mutation_type not in dynamic_types:
            errors.append(f"{name}: unknown Dynamic mutation type {mutation_type!r}")
        evidence = entry.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            errors.append(f"{name}: at least one evidence reference is required")
            continue
        for evidence_index, reference in enumerate(evidence):
            if not isinstance(reference, dict):
                errors.append(f"{name}: evidence[{evidence_index}] must be an object")
                continue
            relative = reference.get("path")
            anchor = reference.get("anchor")
            if not isinstance(relative, str) or not isinstance(anchor, str):
                errors.append(f"{name}: evidence[{evidence_index}] needs path and anchor")
                continue
            evidence_path = ROOT / relative
            if not evidence_path.is_file():
                errors.append(f"{name}: evidence path does not exist: {relative}")
                continue
            if anchor not in evidence_path.read_text(encoding="utf-8"):
                errors.append(f"{name}: evidence anchor not found in {relative}: {anchor}")

    summary = inventory.get("summary", {})
    for classification in ALLOWED_CLASSIFICATIONS:
        if summary.get(classification) != classifications[classification]:
            errors.append(f"summary count drifted for {classification}")
    for key, status in (("complete", "COMPLETE"), ("partial", "PARTIAL"), ("absent", "ABSENT")):
        if summary.get(key) != statuses[status]:
            errors.append(f"summary count drifted for {key}")
    return errors


def _print_table(inventory: dict[str, Any]) -> None:
    print(f"Kernel object coverage {inventory['kernel']['version']} ({len(inventory['objects'])} types)")
    print("TYPE\tCLASSIFICATION\tSTATUS\tCURRENT REPRESENTATION")
    for entry in inventory["objects"]:
        print(
            f"{entry['kernel_type']}\t{entry['classification']}\t"
            f"{entry['implementation_status']}\t{entry['current_representation']}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="print the versioned inventory as JSON")
    args = parser.parse_args()
    inventory = load_inventory()
    errors = audit_inventory(inventory)
    if errors:
        print("FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    if args.json:
        print(json.dumps(inventory, indent=2, ensure_ascii=False))
    else:
        _print_table(inventory)
        print("PASS: inventory matches kernel and frozen contracts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
