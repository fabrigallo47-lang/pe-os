"""State-transition dynamics embedded in the PE OS backend.

The public backend boundary is intentionally small: callers either execute a
Candidate transition from an already compiled runtime bundle or explicitly
settle that Candidate into a new Current runtime state.
"""

import sys as _sys
from pathlib import Path as _Path

# panta_transition_engine imports its siblings as a top-level `runtime` package
# (`from runtime.consequence_reasoning import ...`) so the same source can be
# packaged standalone for serverless. That only resolves with this directory on
# the path, which the test suite gets for free by running with
# cwd=backend/dynamics -- and which every caller launched from the repo root
# does NOT. Three separate tools hit the same ModuleNotFoundError before this
# was fixed here: tools/test_pan36.py, tools/verify_all.py's bundle stage, and
# tools/bundle_assemble.py. Fixing it once at the package boundary beats
# patching each caller, and leaves the flat imports intact for packaging.
_HERE = str(_Path(__file__).resolve().parent)
if _HERE not in _sys.path:
    _sys.path.append(_HERE)

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
