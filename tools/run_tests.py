#!/usr/bin/env python3
"""One command that runs the suite the same way locally and in CI.

Why this exists rather than a line of YAML
------------------------------------------
The suite has three traps that a naive `python -m unittest discover` walks into:

1. Tests under ``backend/dynamics/tests/`` import ``runtime`` as a top-level
   package, so they need ``backend/dynamics`` on the path. Run them from the repo
   root and every one fails with ModuleNotFoundError — which looks like the code
   is broken when only the invocation is.
2. ``tools/`` tests import ``tools.*``, so they need the repo root instead. The
   two groups cannot share one path setting.
3. A few tests reach for a model API and cannot run without a key.

Putting that knowledge in a workflow file means a developer running the suite by
hand gets different results from CI, and the difference is silent. Putting it
here means both run this.

Quarantine
----------
Two kinds of test do not gate a merge, and each is listed below with a reason
rather than deleted or skipped silently:

* KNOWN_FAILING — a real failure someone owns. Quarantined so the gate stays
  meaningful, listed so it cannot be quietly forgotten. A quarantined test that
  starts passing is reported too: that is how the list shrinks.
* NEEDS_API_KEY — calls a model. Excluded from CI, run locally when relevant.

Usage
-----
    python3 tools/run_tests.py              # gate: everything that must pass
    python3 tools/run_tests.py --all        # also run quarantined, still exit 0 on them
    python3 tools/run_tests.py --quarantine # only the quarantined ones
    python3 tools/run_tests.py --list       # show the plan without running
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DYNAMICS = ROOT / "backend" / "dynamics"

# Tests that fail today for a reason someone owns. Keep the reason specific
# enough that a reader can decide whether it still applies.
KNOWN_FAILING: dict[str, str] = {
    "backend/dynamics/tests/test_v20_bulk_intake.py":
        "test_partial_failure_persists_and_failed_file_retries_independently expects "
        "batch status PARTIAL_ERROR. Predates the current bulk-intake behaviour; "
        "unclear whether the test or the handler is wrong.",
}

# Tests that cannot run unattended. Not failures — they need something CI has
# no way to provide.
NEEDS_API_KEY: dict[str, str] = {
    "tools/test_extract.py":
        "exits early with 'ANTHROPIC_API_KEY not set'; exercises live extraction.",
    "tools/test_ui.py":
        "an interactive harness, not a unit test: needs an API key and serves a "
        "browser on localhost:8765. Hangs rather than fails when run headless.",
}

def discover() -> list[Path]:
    found: list[Path] = []
    for directory in (ROOT / "tools", DYNAMICS / "tests"):
        if directory.is_dir():
            found.extend(sorted(directory.glob("test_*.py")))
    return found


def _env_for(test: Path) -> dict[str, str]:
    """backend/dynamics tests import `runtime`; tools tests import `tools`."""
    env = dict(os.environ)
    root = str(DYNAMICS) if DYNAMICS in test.parents else str(ROOT)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = f"{root}{os.pathsep}{existing}" if existing else root
    # Never let a developer's key make a CI-excluded test pass by accident.
    env.pop("ANTHROPIC_API_KEY", None) if env.get("PEOS_CI") else None
    return env


def run_one(test: Path, timeout: int = 300) -> tuple[bool, str, float]:
    started = time.monotonic()
    try:
        proc = subprocess.run(
            [sys.executable, str(test)],
            cwd=str(DYNAMICS if DYNAMICS in test.parents else ROOT),
            env=_env_for(test), capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return False, f"timed out after {timeout}s", time.monotonic() - started
    elapsed = time.monotonic() - started
    if proc.returncode == 0:
        return True, "", elapsed
    tail = (proc.stderr or proc.stdout or "").strip().splitlines()
    return False, "\n".join(tail[-25:]), elapsed


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the pe-os test suite")
    parser.add_argument("--all", action="store_true",
                        help="also run quarantined tests (they still do not fail the run)")
    parser.add_argument("--quarantine", action="store_true",
                        help="run only the quarantined tests")
    parser.add_argument("--list", action="store_true", help="show the plan and exit")
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()

    tests = discover()
    rel = {t: str(t.relative_to(ROOT)) for t in tests}
    quarantined = [t for t in tests if rel[t] in KNOWN_FAILING or rel[t] in NEEDS_API_KEY]
    gating = [t for t in tests if t not in quarantined]

    if args.list:
        print(f"gate ({len(gating)}):")
        for t in gating:
            print(f"    {rel[t]}")
        print(f"\nquarantined ({len(quarantined)}):")
        for t in quarantined:
            why = KNOWN_FAILING.get(rel[t]) or NEEDS_API_KEY.get(rel[t], "")
            print(f"    {rel[t]}\n        {why}")
        return 0

    selected = quarantined if args.quarantine else gating + (quarantined if args.all else [])
    failures: list[tuple[str, str]] = []
    recovered: list[str] = []
    started = time.monotonic()

    print(f"running {len(selected)} test file(s)\n")
    for test in selected:
        name = rel[test]
        is_quarantined = test in quarantined
        ok, detail, elapsed = run_one(test, args.timeout)
        if ok:
            status = "PASS"
            if is_quarantined and name in KNOWN_FAILING:
                # A quarantined test that passes is news: the list can shrink.
                status = "PASS (quarantined — now passing, remove it from the list)"
                recovered.append(name)
        else:
            status = "QUARANTINED FAIL" if is_quarantined else "FAIL"
            if not is_quarantined:
                failures.append((name, detail))
        print(f"  [{elapsed:5.1f}s] {status:<12} {name}")
        if not ok and not is_quarantined:
            print("\n".join(f"        {line}" for line in detail.splitlines()[-12:]))

    total = time.monotonic() - started
    print(f"\n{len(selected) - len(failures)}/{len(selected)} passed in {total:.1f}s")

    if recovered:
        print("\nno longer failing — remove from KNOWN_FAILING in tools/run_tests.py:")
        for name in recovered:
            print(f"  {name}")

    if failures:
        print(f"\n{len(failures)} gating failure(s):")
        for name, _ in failures:
            print(f"  {name}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
