"""Connected acceptance for typed, contextual, versioned statement transport."""
import copy
import json
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))

import app.v20_router as router
from app.statement_tracking import statement_context
from app.source_documents import locate_document, resolve_document
from tools.extract_v2_physical import assemble, validate
from tools.object_identity import claim_id, metric_identity
from typed_statement_fixture import build_typed_fixture


class StatementTrackingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.fixture = build_typed_fixture(self.root)

    def test_real_parser_and_simulated_annotations_reach_cards_without_changing_contract(self):
        fixture = self.fixture
        self.assertEqual(fixture['graph'].admitted_count, 7)
        self.assertEqual(fixture['graph'].rejected_count, 0)
        kinds = {c['claimKind'] for c in fixture['projected']}
        self.assertTrue({'QUANTITATIVE', 'QUALITATIVE', 'NEGATIVE', 'ATTRIBUTION'} <= kinds)
        for c in fixture['e3']['claims']:
            self.assertNotIn('tracking', c, 'Frozen CAP-003 payload stays unchanged')
            self.assertNotIn('claim_kind', c)
        for c in fixture['claims']:
            self.assertEqual(c['claim_id'], claim_id(c))
        projected = {c['locator'].split('## ')[-1]: c for c in fixture['projected']}
        self.assertEqual(projected['Ownership']['tracking']['value'], 8.5)
        self.assertEqual(projected['Ownership']['tracking']['rawValue'], '8.5%')
        self.assertEqual(projected['Ownership']['tracking']['bound'], 'APPROXIMATE')
        self.assertEqual(projected['Timing']['tracking']['value'], '30-60')
        self.assertEqual(projected['Timing']['tracking']['valueType'], 'TEXT')
        self.assertEqual(projected['Verification']['tracking']['valueType'], 'MISSING')

    def test_context_and_derivation_survive_note_and_api_projection(self):
        claim = copy.deepcopy(self.fixture['claims'][0])
        claim.update(derivation='5 * 2 = 10', value='10', value_raw='10', rests_on=['declared-input'])
        before = copy.deepcopy(claim)
        with patch.object(router, 'VAULT', self.root / 'vault'):
            self.assertEqual(router._persist_claims_to_vault('CASE-1', [claim], 'typed-tracking.md'), 1)
        note = router._read_frontmatter(next((self.root / 'vault/deals/CASE-1/claims').glob('*.md')))
        self.assertEqual(note['derivation'], '5 * 2 = 10')
        self.assertEqual(note['rests-on'], ['declared-input'])
        for key in ('unit', 'definition_id', 'scope', 'basis', 'claim_kind', 'bound', 'value_raw'):
            self.assertEqual(note[key], claim[key])
        self.assertEqual(note['statement-context'], router._enrich_claims([claim], {})[0]['tracking'])
        self.assertEqual(claim, before)

    def test_all_seven_claims_resolve_original_sections(self):
        source = self.fixture['source']
        original_bytes = self.fixture['path'].read_bytes()
        for claim in self.fixture['claims']:
            records = json.loads((self.root / 'vault/inbox/.ingest-manifest.json').read_text())['items']
            document = resolve_document(self.root / 'vault', records, 'CASE-1', source['source_id'], claim['source_version_id'])
            position = locate_document(document, claim['locator'])
            self.assertEqual(position['status'], 'LOCATED', position)
        self.assertEqual(self.fixture['path'].read_bytes(), original_bytes)

    def test_different_contexts_never_become_equal_numbers(self):
        claim = self.fixture['claims'][0]
        for patch_values in ({'unit': '$m'}, {'period': 'FY2027'}, {'basis': 'after fees'}, {'scope': 'secondary round'}, {'scenario': 'Downside'}):
            changed = {**claim, **patch_values}
            self.assertNotEqual(metric_identity(claim), metric_identity(changed), patch_values)
            self.assertNotEqual(statement_context(claim), statement_context(changed))
        missing = statement_context({'value': 0})
        self.assertEqual(missing['value'], 0)
        self.assertEqual(set(missing['missingFields']), {'definition', 'period', 'scope', 'basis', 'unit'})
        self.assertEqual(statement_context({'value': False})['valueType'], 'BOOLEAN')

    def test_invalid_numeric_and_unknown_types_are_rejected(self):
        raw = self.fixture['raw'][0]
        for change in ({'value': 'NaN'}, {'value': 'Infinity'}, {'value': '1e999'}, {'claim_kind': 'INVENTED'}, {'bound': 'INVENTED'}):
            self.assertEqual(assemble([validate(replace(raw, **change))]).admitted_count, 0, change)
        json.dumps(statement_context({'value': float('nan')}), allow_nan=False)

    def test_extractor_metrics_keep_distinct_meaning_after_normalization(self):
        contexts = [statement_context({'metric': name, 'value': 5}) for name in
                    ('Customer Churn', 'Total Net Leverage Ratio', 'Minimum Liquidity')]
        self.assertTrue(all(item['metric'] for item in contexts))
        self.assertEqual(len({item['metric'] for item in contexts}), 3)


if __name__ == '__main__':
    unittest.main()
