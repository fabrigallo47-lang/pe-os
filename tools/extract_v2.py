#!/usr/bin/env python3
"""Backward-compatible entry point for the physical extraction pipeline."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.extract_v2_physical import *  # noqa: F401,F403


if __name__ == "__main__":
    from tools.extract_v2_physical import main

    raise SystemExit(main())
