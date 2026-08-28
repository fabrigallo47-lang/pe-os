"""PANTA State Transition Engine runtime package."""

from .panta_transition_engine import (
    EventInputError,
    StateInputError,
    apply_state_transition,
    build_runtime_state,
    compare_incremental_global,
    compute_affected_set,
    normalize_event_batch,
)
from .extraction_adapter import (
    ADAPTER_VERSION,
    AdmissionInputError,
    ExtractionInputError,
    analyze_extraction_graph,
    apply_extraction_transition,
    compile_extraction_to_runtime_inputs,
    validate_extraction_graph,
)
from .gold_mapping_adapter import (
    GOLD_ADAPTER_VERSION,
    GoldMappingInputError,
    apply_gold_transition,
    compile_gold_to_runtime_inputs,
)

__all__ = [
    "EventInputError",
    "StateInputError",
    "apply_state_transition",
    "build_runtime_state",
    "compare_incremental_global",
    "compute_affected_set",
    "normalize_event_batch",
    "ADAPTER_VERSION",
    "AdmissionInputError",
    "ExtractionInputError",
    "analyze_extraction_graph",
    "apply_extraction_transition",
    "compile_extraction_to_runtime_inputs",
    "validate_extraction_graph",
    "GOLD_ADAPTER_VERSION",
    "GoldMappingInputError",
    "apply_gold_transition",
    "compile_gold_to_runtime_inputs",
]
