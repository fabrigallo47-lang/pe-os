"""Audit supplied test artifacts without changing their originals."""
import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / 'backend/dynamics'):
    sys.path.insert(0, str(path))

from tools.repository_tracking_case import build_repository_case, digest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--workspace', type=Path, default=ROOT.parent)
    parser.add_argument('--output', type=Path, default=ROOT / 'docs/verification/repository-source-tracking.json')
    parser.add_argument('--simulate-locations', action='store_true')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='panta-reference-audit-') as temporary:
        case = build_repository_case(Path(temporary), args.workspace, simulate_locations=args.simulate_locations)
        report = case['report']
        report['originals_unchanged'] = all(digest(Path(path)) == expected for path, expected in report['source_hashes'].items())
        if not report['originals_unchanged']:
            raise RuntimeError('An original artifact changed during the audit.')
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps({key: report[key] for key in ('source_count', 'model_node_count', 'declared_edge_count', 'canonical_location_counts', 'evaluation_location_counts', 'model_location_counts', 'originals_unchanged')}, indent=2))
        print(f'Report: {args.output}')


if __name__ == '__main__':
    main()
