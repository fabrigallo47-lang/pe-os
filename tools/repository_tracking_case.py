"""Read-only tracking audit over the repository's existing test documents and graphs.

This is a fixture browser and source-address audit, not an extraction benchmark
or a projection of adopted Current. Gold/answer-key prose is never ingested.
"""
from __future__ import annotations
import collections
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException
from openpyxl import load_workbook
from app.source_documents import SourceDocument, locate_document, workbook_positions, workbook_dimensions
from tools.source_envelope import build_source_envelope

ROOT = Path(__file__).resolve().parents[1]
CASE_ID = 'REPOSITORY-TRACKING-TEST'
PACKAGE_NAME = 'PANTA_Keystone_Canonical_Investment_Case_v1_1'


def digest(path):
    return 'sha256:' + hashlib.sha256(path.read_bytes()).hexdigest()


def evaluation_addresses(case):
    """Use the supplied benchmark evidence addresses, without claiming extraction."""
    items = list(case.get('evidence', []))
    gold = case.get('gold', {})
    items += gold.get('fields', []) + gold.get('facts', []) + gold.get('elements', [])
    for item in items:
        ref = item.get('locator', {})
        kind = ref.get('type')
        locator = None
        if kind in {'page', 'image_region'} and ref.get('page'):
            locator = f'p{ref["page"]}'
        elif kind == 'cell':
            locator = "'" + ref['sheet'].replace("'", "''") + "'!" + ref['range']
        elif kind == 'slide':
            locator = f'slide:{ref["slide"]}'
        elif kind == 'word' and ref.get('section'):
            locator = 'section:' + ref['section']
        elif kind == 'email_part' and ref.get('part') in {'body_text', 'headers', 'subject'}:
            locator = 'message-id:' + ref['message_id'] + (':body' if ref['part'] == 'body_text' else ':headers')
        elif kind == 'image_region':
            locator = 'image:1'
        if locator and ref.get('bbox') and kind in {'page', 'image_region'}:
            locator += ':rect:' + ','.join(map(str, ref['bbox']))
        if locator:
            yield item, locator


def build_repository_case(temporary: Path, workspace: Path | None = None):
    workspace = workspace or ROOT.parent
    package = workspace / PACKAGE_NAME
    graph_path = package / 'canonical/PANTA_Keystone_Canonical_Investment_Case_v1.1.json'
    mapping_path = workspace / 'GOLD/keystone_execution_mapping_v1 (3).json'
    semantic_path = workspace / 'GOLD/keystone_semantic_financial_graph_v1 (5).json'
    graph = json.loads(graph_path.read_text())
    mapping = json.loads(mapping_path.read_text())
    semantic = json.loads(semantic_path.read_text())
    captured_at = datetime.now(timezone.utc).isoformat()
    inbox = temporary / 'vault/inbox'
    inbox.mkdir(parents=True, exist_ok=True)
    original_paths = [graph_path, mapping_path, semantic_path]
    records, documents, sources, versions = [], {}, [], []
    def register(path, source_id, metadata=None, expected_hash=None):
        if source_id in documents:
            return documents[source_id]
        actual_hash = digest(path)
        if expected_hash and actual_hash != ('sha256:' + expected_hash.removeprefix('sha256:')):
            raise ValueError(f'Test source hash mismatch: {path.name}')
        destination = inbox / path.name
        shutil.copyfile(path, destination)
        meta = metadata or {}
        envelope = build_source_envelope(destination, CASE_ID, captured_at, declared_metadata={
            'source_id': source_id, 'issuer': meta.get('party'), 'effective_date': meta.get('date'),
            'provenance': 'explicit_test_fixture_import', 'document_type': meta.get('type')})
        records.append({'case_id': CASE_ID, 'source_envelope': envelope})
        original_paths.append(path)
        doc = SourceDocument(CASE_ID, source_id, actual_hash, path.name, path.suffix.lower(), destination.read_bytes())
        documents[source_id] = doc
        sources.append({'id': source_id, 'title': path.name, 'type': meta.get('type', path.suffix[1:]),
                        'origin': meta.get('party', 'Repository test fixture'), 'currentVersionId': actual_hash,
                        'occurredAt': meta.get('date')})
        versions.append({'id': actual_hash, 'sourceId': source_id, 'contentHash': actual_hash,
                         'knownAt': captured_at, 'permissionScope': 'CASE'})
        return doc

    for source_id, source in graph['sources'].items():
        if source.get('validation_only'):
            continue
        matches = [path for layer in ('layer_1_ingested', 'layer_2_monitoring')
                   if (path := package / 'source_materials' / layer / source['file']).is_file()]
        if len(matches) != 1:
            raise ValueError(f'Original test source is missing or ambiguous: {source_id}')
        register(matches[0], source_id, source,
                 mapping['source_workbook']['sha256'] if source_id == 'SRC-MODEL' else None)
    if semantic['workbook_hash'] != documents['SRC-MODEL'].version_id:
        raise ValueError('The semantic graph belongs to another workbook version.')

    fixture_cases = [json.loads(line) for line in (ROOT / 'evaluation/fixtures/cases/panta_smoke.ndjson').read_text().splitlines() if line.strip()]
    evidence_claims, seen = [], set()
    for case in fixture_cases:
        inputs = {row['input_id']: row for row in case['inputs']}
        for item in case['inputs']:
            register(ROOT / item['path'], 'EVAL-' + Path(item['path']).stem, expected_hash=item['sha256'])
        for item, locator in evaluation_addresses(case):
            source = inputs.get(item.get('input_id'))
            if not source:
                continue
            sid = 'EVAL-' + Path(source['path']).stem
            identity = (sid, locator, item.get('quote') or item.get('name') or item.get('fact_id') or item.get('text'))
            if identity in seen:
                continue
            seen.add(identity)
            label = item.get('name') or item.get('fact_id') or item.get('text') or case.get('query') or 'Fixture evidence'
            statement = item.get('quote') or (str(label) + ': ' + str(item['value']) if 'value' in item else str(label))
            evidence_claims.append({'claim_id': 'EVAL-' + str(len(evidence_claims) + 1), 'source_id': sid, 'locator': locator,
                                    'statement': statement, 'verbatim_or_lossless_span': item.get('quote')})

    claims = [dict(c) for c in graph['claims'] if not c.get('validation_only') and c['source_id'] in documents] + evidence_claims
    refs, entries, audit = {}, [], []
    def source_ref(source_id, locator, claim_id=None):
        ref = {'sourceId': source_id, 'sourceVersionId': documents[source_id].version_id, 'locator': locator}
        if claim_id:
            ref['claimId'] = claim_id
        return ref
    for claim in claims:
        claim['source_version_id'] = documents[claim['source_id']].version_id
        refs[claim['claim_id']] = [source_ref(claim['source_id'], claim['locator'], claim['claim_id'])]
        entries.append({'id': claim['claim_id'], 'label': claim['statement'], 'kind': 'claim'})
        try:
            position = locate_document(documents[claim['source_id']], claim['locator'])
            audit.append({'id': claim['claim_id'], 'source_id': claim['source_id'], 'locator': claim['locator'], 'status': position['status'], 'position': position})
        except HTTPException as exc:
            audit.append({'id': claim['claim_id'], 'source_id': claim['source_id'], 'locator': claim['locator'], 'status': 'INVALID', 'reason': exc.detail})

    book = load_workbook(io_bytes(documents['SRC-MODEL'].data), read_only=True, keep_links=False)
    sheets = workbook_dimensions(book)
    book.close()
    nodes = {n['model_node_id']: n for n in mapping['model_nodes']}
    formulas = {f['output_id']: f for f in mapping['formulas'] if f.get('output_id')}
    upstream, downstream, relations = collections.defaultdict(list), collections.defaultdict(list), []
    for edge in mapping['directed_model_edges']:
        source, target = edge['from_model_node_id'], edge['to_model_node_id']
        if source not in nodes or target not in nodes:
            raise ValueError(f'Broken declared edge: {edge["edge_id"]}')
        upstream[target].append(source)
        downstream[source].append(target)
        relations.append({'id': edge['edge_id'], 'caseId': CASE_ID, 'sourceObjectId': source, 'sourceObjectType': 'modelNode',
                          'targetObjectId': target, 'targetObjectType': 'modelNode', 'type': 'DRIVES',
                          'rationale': edge.get('source_locator'), 'institutionalState': 'CANDIDATE', 'contractVersion': '0.1.0'})
    quantities = []
    for identity, node in nodes.items():
        address = node.get('workbook_locator') or (
            node['workbook_sheet'] + '!' + node['workbook_cell_or_range'] if node.get('workbook_sheet') and node.get('workbook_cell_or_range') else None)
        node_refs = [source_ref('SRC-MODEL', address)] if address else []
        formula = formulas.get(identity, {})
        for ref in formula.get('source_refs', []):
            if ref in documents:
                node_refs.append(source_ref(ref, ''))
        refs[identity] = node_refs
        if address:
            try:
                position = workbook_positions(address, sheets)
                audit.append({'id': identity, 'source_id': 'SRC-MODEL', 'locator': address, 'status': position['status']})
            except HTTPException as exc:
                audit.append({'id': identity, 'source_id': 'SRC-MODEL', 'locator': address, 'status': 'INVALID', 'reason': exc.detail})
        entries.append({'id': identity, 'label': node.get('name') or identity, 'kind': 'quantity'})
        quantities.append({'id': identity, 'label': node.get('name') or identity,
                           'value': node.get('baseline_value_decimal', node.get('baseline_value')), 'unit': node.get('unit'),
                           'perimeter': {'period': node.get('period'), 'scope': node.get('perimeter'), 'scenario': node.get('scenario_id')},
                           'sourceObjectIds': list(dict.fromkeys(upstream[identity])), 'formula': formula.get('expression'),
                           'assumptionObjectIds': [], 'downstreamObjectIds': list(dict.fromkeys(downstream[identity])),
                           'editable': False, 'institutionalState': 'CANDIDATE', 'freshnessStatus': 'UNKNOWN'})

    snapshot = {key: [] for key in ('actors workstreams questions caseReadings unknowns metricDefinitions metricObservations assumptions risks modelNodes outcomes findings humanPositions workItems artifacts artifactBlocks artifactDiffs events pendingReviews simulationOptions conditions decisionPaths decisions').split()}
    snapshot.update(caseRef={'id': CASE_ID, 'name': 'Keystone · repository test graph'}, caseVersion=digest(graph_path), asOf=captured_at,
                    sources=sources, sourceVersions=versions, quantities=quantities, relations=relations,
                    claims=[{'id': c['claim_id'], 'sourceId': c['source_id'], 'sourceVersionId': c['source_version_id'],
                             'locator': c['locator'], 'label': c['statement'], 'normalizedStatement': c['statement'],
                             'verbatimOrLosslessSpan': c.get('verbatim_or_lossless_span'), 'type': 'Repository fixture statement'} for c in claims])
    for source in sources:
        refs[source['id']] = [source_ref(source['id'], '')]
    counts = collections.Counter(item['status'] for item in audit)
    indirect_paths = {}
    for identity in nodes:
        if refs[identity]:
            continue
        queue, visited = collections.deque([[identity]]), {identity}
        while queue:
            path = queue.popleft()
            if any(ref.get('locator') for ref in refs[path[-1]]):
                indirect_paths[identity] = path
                break
            for parent in upstream[path[-1]]:
                if parent not in visited:
                    visited.add(parent)
                    queue.append(path + [parent])
    report = {'schema': 'source-tracking-audit/1.0', 'captured_at': captured_at, 'case_id': CASE_ID,
              'scope': 'Existing test graphs and original test documents; no extraction score and no Current adoption',
              'canonical_graph': str(graph_path), 'execution_mapping': str(mapping_path), 'semantic_graph': str(semantic_path),
              'workbook_hash_verified': documents['SRC-MODEL'].version_id, 'source_count': len(sources),
              'canonical_claim_count': len(claims) - len(evidence_claims), 'evaluation_reference_count': len(evidence_claims),
              'model_node_count': len(nodes), 'declared_edge_count': len(relations), 'direct_reference_counts': dict(counts),
              'canonical_location_counts': dict(collections.Counter(row['status'] for row in audit if row['id'].startswith('CL-'))),
              'evaluation_location_counts': dict(collections.Counter(row['status'] for row in audit if row['id'].startswith('EVAL-'))),
              'model_location_counts': dict(collections.Counter(row['status'] for row in audit if row['id'] in nodes)),
              'nodes_without_direct_locator': [n for n in nodes if not any(ref.get('locator') for ref in refs[n])],
              'nodes_with_source_overview_only': [n for n in nodes if refs[n] and not any(ref.get('locator') for ref in refs[n])],
              'indirect_paths': indirect_paths,
              'nodes_without_source_path': [n for n in nodes if not refs[n] and n not in indirect_paths],
              'unresolved_references': [item for item in audit if item['status'] != 'LOCATED'],
              'source_hashes': {str(path): digest(path) for path in dict.fromkeys(original_paths)}}
    manifest_path = inbox / '.ingest-manifest.json'
    existing = json.loads(manifest_path.read_text()).get('items', []) if manifest_path.exists() else []
    manifest_path.write_text(json.dumps({'items': [item for item in existing if item.get('case_id') != CASE_ID] + records}))
    bundle = temporary / 'cases' / CASE_ID
    bundle.mkdir(parents=True, exist_ok=True)
    (bundle / 'claims.json').write_text(json.dumps(claims))
    valid_ids = {row['id'] for row in entries} | {row['id'] for row in sources}
    def inspect(identity):
        if identity not in valid_ids:
            return None
        return {'objectId': identity, 'supportObjectIds': list(dict.fromkeys(upstream[identity])), 'independentSupportObjectIds': [],
                'dependentObjectIds': list(dict.fromkeys(downstream[identity])), 'unknownIds': [], 'relatedObjectIds': [],
                'sourceLocators': refs[identity], 'allowedActions': ['OPEN_SOURCE'] if refs[identity] else []}
    return {'snapshot': snapshot, 'entries': entries, 'report': report, 'audit': audit, 'documents': documents,
            'records': records, 'inspect': inspect, 'refs': refs}


def io_bytes(data):
    from io import BytesIO
    return BytesIO(data)
