"""Explicit, hash-locked test migration; never a production locator heuristic."""
import hashlib
import json
from pathlib import Path

FIXTURE = Path(__file__).resolve().parents[1] / 'tests/fixtures/tracking-location-simulation.json'


def apply_location_simulation(claims, documents, graph_hash):
    fixture = json.loads(FIXTURE.read_text())
    if fixture['canonical_graph_hash'] != graph_hash:
        raise ValueError('The simulated reference mappings belong to another graph version.')
    by_id = {claim['claim_id']: claim for claim in claims}
    for entry in fixture['entries']:
        claim = by_id[entry['claim_id']]
        document = documents[entry['source_id']]
        if (claim['source_id'] != entry['source_id'] or claim['locator'] != entry['original_locator']
                or document.version_id != entry['source_version_id']):
            raise ValueError('A simulated reference no longer matches its original provenance.')
        lines = document.data.decode('utf-8').splitlines()
        spans = entry['line_spans']
        if entry['locator'] != 'lines:' + ','.join(f'{a}-{b}' for a, b in spans):
            raise ValueError('The simulated locator differs from its audited ranges.')
        hashes = ['sha256:' + hashlib.sha256('\n'.join(lines[a-1:b]).encode()).hexdigest() for a, b in spans]
        if hashes != entry['span_hashes'] or any(not 1 <= a <= b <= len(lines) for a, b in spans):
            raise ValueError('The selected original passage changed.')
        claim['original_locator'] = claim['locator']
        claim['locator'] = entry['locator']
        claim['locator_provenance'] = 'explicit_hash_locked_test_simulation'
        if entry.get('limitation'):
            claim['limitation'] = entry['limitation']
    return fixture['entries']
