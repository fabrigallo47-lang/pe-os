"""State-transition dynamics embedded in the PE OS backend.

The public backend boundary is intentionally small: callers either execute a
Candidate transition from an already compiled runtime bundle or explicitly
settle that Candidate into a new Current runtime state.
"""

from .service import (
    DynamicsBundleError,
    load_event_batch,
    run_bundle_transition,
    settle_candidate_state,
)

__all__ = [
    "DynamicsBundleError",
    "load_event_batch",
    "run_bundle_transition",
    "settle_candidate_state",
]
