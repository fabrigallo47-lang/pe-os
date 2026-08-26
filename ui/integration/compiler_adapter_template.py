"""Fabri-side adapter template: compiler output -> PANTA V17 frontend input.

This module deliberately does not implement extraction or inference. It checks
and normalizes an already-produced compiler bundle. Replace the TODO calls with
the repository's frozen schema validators.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


class AdapterContractError(ValueError):
    pass


@dataclass(frozen=True)
class CompilerBundle:
    current_graph: Mapping[str, Any]
    execution_mapping: Mapping[str, Any]
    admission_manifest: Mapping[str, Any]
    pending_events: tuple[Mapping[str, Any], ...]


def compile_frontend_input(bundle: CompilerBundle) -> dict[str, Any]:
    """Return the compiler-owned inputs consumed by Anto and the frontend.

    Invariants:
    - never mutates the raw extraction;
    - never creates Candidate/Current/Approved transitions;
    - never computes policy, materiality, human stops, or settlement;
    - every unresolved mapping becomes a coverage limit.
    """
    case_id = bundle.current_graph.get("case_id")
    if not case_id:
        raise AdapterContractError("current_graph.case_id is required")
    if bundle.admission_manifest.get("case_id") not in (None, case_id):
        raise AdapterContractError("manifest and current_graph case_id differ")
    return {
        "case_id": case_id,
        "current_graph": dict(bundle.current_graph),
        "execution_mapping": dict(bundle.execution_mapping),
        "admission_manifest": dict(bundle.admission_manifest),
        "pending_events": [dict(event) for event in bundle.pending_events],
    }
