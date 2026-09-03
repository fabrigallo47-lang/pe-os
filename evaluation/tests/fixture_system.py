#!/usr/bin/env python3
"""Test-only command target proving that the runner never exposes gold."""

from __future__ import annotations

import json
import sys


case = json.load(sys.stdin)
if any(key in case for key in ("gold", "evidence", "metrics", "acceptance")):
    raise SystemExit("gold leaked to system command")
print(json.dumps({
    "schema_version": "panta-eval.prediction/1.0",
    "test_id": case["test_id"],
    "status": "success",
    "answer": "approved",
}))
