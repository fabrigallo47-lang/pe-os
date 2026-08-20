#!/usr/bin/env python3
"""
PANTA STE conformance test runner.

Usage:
  python3 tools/run_conformance.py                       # runs all available cases
  python3 tools/run_conformance.py --ids TCE-002,TCE-003 # specific cases
  python3 tools/run_conformance.py --ids TCE-001 --state path/to/cic.json
"""
import json
import sys
from pathlib import Path

ROOT    = Path(__file__).resolve().parent.parent
HANDOFF = Path.home() / "Downloads" / "PANTA_STATE_TRANSITION_ENGINE_HANDOFF_V1" / \
          "PANTA_STATE_TRANSITION_ENGINE_HANDOFF_V1"

sys.path.insert(0, str(ROOT))

from tools.transition_engine import (
    PolicyBundle, InstitutionalState, ConformanceRunner,
)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="PANTA STE conformance runner")
    parser.add_argument("--suite",  default=str(HANDOFF / "benchmark" / "transition_engine_conformance_cases_v1.json"))
    parser.add_argument("--ids",    default="", help="Comma-separated TCE IDs (empty = all)")
    parser.add_argument("--state",  default="", help="Path to canonical IC JSON (needed for TCE-001)")
    parser.add_argument("--json",   action="store_true", help="Emit JSON results to stdout")
    args = parser.parse_args()

    suite_path = Path(args.suite)
    if not suite_path.exists():
        print(f"Suite not found: {suite_path}", file=sys.stderr)
        sys.exit(1)

    suite = json.loads(suite_path.read_text())
    print(f"Suite: {suite.get('suite_version', '?')} — {len(suite.get('cases', []))} cases")

    mat_path  = HANDOFF / "benchmark" / "keystone_materiality_policy_v0.json"
    auth_path = HANDOFF / "benchmark" / "keystone_authority_matrix_v0.json"
    exec_path = HANDOFF / "benchmark" / "keystone_execution_mapping_v0.json"

    if not mat_path.exists():
        print(f"Policy files not found at {HANDOFF}/benchmark/", file=sys.stderr)
        sys.exit(1)

    policies = PolicyBundle.from_files(mat_path, auth_path, exec_path)

    # Load canonical state for TCE-001 if provided
    canonical_state = None
    if args.state:
        sp = Path(args.state)
        if sp.exists():
            cic = json.loads(sp.read_text())
            canonical_state = InstitutionalState.from_canonical_json(cic)
            print(f"Loaded canonical state: {canonical_state.case_id} v{canonical_state.version}")

    runner   = ConformanceRunner(policies)
    # Support short prefix matching: "TCE-002" matches "TCE-002-ALTERNATIVE-ROUTE-SURVIVES"
    raw_ids = [t.strip() for t in args.ids.split(",") if t.strip()]
    if raw_ids:
        all_ids = [c["test_id"] for c in suite.get("cases", [])]
        test_ids = []
        for rid in raw_ids:
            matched = [tid for tid in all_ids if tid == rid or tid.startswith(rid + "-")]
            if matched:
                test_ids.extend(matched)
            else:
                test_ids.append(rid)  # pass through; runner will skip gracefully
    else:
        test_ids = None

    print()
    summary = runner.run_suite(suite, canonical_state=canonical_state, test_ids=test_ids)

    if args.json:
        import json as _j
        print(_j.dumps(summary, indent=2, default=str))

    sys.exit(0 if summary["passed"] == summary["total"] else 1)


if __name__ == "__main__":
    main()
