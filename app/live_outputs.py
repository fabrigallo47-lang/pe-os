"""Versioned, case-backed work products. The case loader and actor are server-owned.

This store records Artifact revisions, not investment decisions or case adoption.
No input from an HTTP caller can replace the authoritative case projection.
"""
from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
import re
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException
from app import editorial_profiles as editorial

KINDS = {'IC_MEMO': 'IC Memo', 'MODEL': 'Case Model', 'DECISION_PACK': 'Decision Pack', 'DECK': 'Investment Deck', 'TRACKER': 'Diligence Tracker'}
COLLECTIONS = ('questions', 'workstreams', 'caseReadings', 'claims', 'sources', 'sourceVersions', 'quantities',
               'metricObservations', 'metricDefinitions', 'modelNodes', 'humanPositions', 'actors', 'unknowns',
               'conditions', 'risks', 'assumptions', 'decisions', 'workItems')


def digest(value):
    return 'sha256:' + hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


def object_index(case):
    return {item['id']: item for key in COLLECTIONS for item in case.get(key, []) if item.get('id')}


def basis(case, ids):
    """Freeze explicitly declared inputs, including cited source versions. Cycles terminate."""
    index, frozen, pending = object_index(case), {}, list(ids)
    while pending:
        identity = pending.pop()
        if identity in frozen:
            continue
        item = index.get(identity)
        frozen[identity] = copy.deepcopy(item)
        if not item:
            continue
        for field in ('supportObjectIds', 'sourceObjectIds', 'assumptionObjectIds', 'evidenceBasisIds', 'sourceBasisIds', 'basisObjectIds', 'conditionIds'):
            pending.extend(item.get(field) or [])
        for field in ('sourceVersionId', 'metricDefinitionId', 'authorActorId', 'actorOrBodyId'):
            if item.get(field):
                pending.append(item[field])
    return frozen


def readable(value):
    return str(value or 'Not supplied').replace('_', ' ').lower()


def compile_blocks(case, kind, artifact_id):
    """Mechanical rendering of admitted projection objects; never invent a recommendation."""
    if not isinstance(kind, str) or kind not in KINDS:
        raise HTTPException(422, 'Unsupported output type.')
    result, seen = [], set()

    def add(section, item, text, *, locked=False):
        if not text or (section, item['id']) in seen:
            return
        seen.add((section, item['id']))
        identity = 'BLOCK-' + digest([artifact_id, section, item['id']])[7:27]
        frozen = basis(case, [item['id']])
        result.append(dict(id=identity, artifactId=artifact_id, title=section, text=str(text),
                           authorship='CASE_BACKED', boundObjectIds=[item['id']],
                           editorialLocked=locked, _basis=frozen, _compiledText=str(text)))

    if kind in {'IC_MEMO', 'DECK', 'DECISION_PACK'}:
        readings = {r['id']: r for r in case.get('caseReadings', [])}
        for question in case.get('questions', []):
            reading = readings.get(question.get('currentCaseReadingId'))
            if reading and reading.get('institutionalState') in {'CURRENT', 'APPROVED'}:
                add(question.get('name') or 'Investment case', reading,
                    f"{reading['text']} Evidence: {readable(reading.get('epistemicStatus'))}. Freshness: {readable(reading.get('freshnessStatus'))}.")
            else:
                add('Still to establish', question, f"{question.get('name', 'Open question')} — no current case reading supplied.")
        for position in case.get('humanPositions', []):
            if position.get('institutionalState') not in {'CURRENT', 'APPROVED'}:
                continue
            actor = next((a for a in case.get('actors', []) if a['id'] == position.get('authorActorId')), None)
            if actor and position.get('recordedAt'):
                add('Recorded views', position, f"{actor['displayName']} ({position['recordedAt']}): {position['text']}", locked=True)
        for decision in case.get('decisions', []):
            if decision.get('caseVersion') == case['caseVersion']:
                add('Recorded decision', decision, decision.get('rationale'), locked=True)
        for risk in case.get('risks', []):
            if risk.get('institutionalState') in {'CURRENT', 'APPROVED'}:
                add('Risks', risk, risk.get('mechanism'))
    if kind in {'IC_MEMO', 'MODEL', 'DECK'}:
        for item in [*case.get('quantities', []), *case.get('metricObservations', [])]:
            if item.get('institutionalState') not in {'CURRENT', 'APPROVED'}:
                continue
            dims = item.get('perimeter', item)
            value = item.get('display') or (str(item['value']) if item.get('value') is not None else 'Not established')
            context = '; '.join(f'{key}: {dims[key]}' for key in ('period', 'scope', 'basis', 'measurement', 'scenario') if dims.get(key))
            text = f"{item.get('label') or item.get('displayLabel') or item['id']}: {value} {' '.join(str(item[k]) for k in ('currency', 'unit') if item.get(k))}. {context}"
            if item.get('formula'):
                text += f". Calculation: {item['formula']}"
            add('Financial basis', item, text)
    if kind in {'IC_MEMO', 'DECK', 'DECISION_PACK', 'TRACKER'}:
        for item in case.get('unknowns', []):
            if item.get('status') not in {'RESOLVED', 'RETIRED'}:
                add('Open diligence', item, f"{item['title']} — {readable(item.get('status'))}. {item.get('resolutionPath') or 'Resolution path not supplied.'}")
        for item in case.get('conditions', []):
            add('Conditions', item, f"{item['label']} — {readable(item.get('status'))}.")
        if kind == 'TRACKER':
            for item in case.get('workItems', []):
                add('Diligence work', item, f"{item['name']} — {readable(item.get('status'))}. {item.get('whatToObtain') or ''}")
    if not result:
        raise HTTPException(422, 'No admitted case content is available for this output.')
    return result


def block_status(case, block):
    current = basis(case, block['boundObjectIds'])
    claim_ids = {c['id'] for c in case.get('claims', [])}
    missing = any(value is None or identity in claim_ids and (not value.get('sourceId') or not re.fullmatch(r'sha256:[0-9a-f]{64}', value.get('sourceVersionId') or '')) for identity, value in current.items())
    invalid = any(value and value.get('institutionalState') in {'CANDIDATE', 'REJECTED', 'RETIRED'} for value in current.values())
    changed = digest(current) != digest(block['_basis']) or any(value and value.get('freshnessStatus') in {'STALE', 'MISSING_BASIS'} for value in current.values())
    return 'MISSING_BASIS' if missing or invalid else 'STALE' if changed else 'CURRENT'


class OutputStore:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS revisions (sequence INTEGER PRIMARY KEY, case_id TEXT NOT NULL, artifact_id TEXT NOT NULL, revision_id TEXT NOT NULL, request_id TEXT NOT NULL, request_hash TEXT NOT NULL, payload TEXT NOT NULL, UNIQUE(case_id, request_id))')
            db.execute('CREATE INDEX IF NOT EXISTS output_case ON revisions(case_id, artifact_id, sequence)')
            editorial.initialize(db)

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=5)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def latest(self, case_id, artifact_id=None, db=None):
        if db is None:
            with self.connect() as connection:
                return self.latest(case_id, artifact_id, connection)
        rows = db.execute('SELECT artifact_id, payload FROM revisions WHERE case_id=? ORDER BY sequence', (case_id,)).fetchall()
        records = {key: json.loads(payload) for key, payload in rows}
        return records.get(artifact_id) if artifact_id else list(records.values())

    def project(self, case):
        with self.connect() as db:
            profile_context = editorial.context(case, db)
        outputs = {'artifacts': [], 'artifactBlocks': [], 'artifactDiffs': [], 'editorialContext': profile_context}
        for saved in self.latest(case['caseRef']['id']):
            artifact, blocks = copy.deepcopy(saved['artifact']), copy.deepcopy(saved['blocks'])
            try:
                expected = compile_blocks(case, artifact['type'], artifact['id'])
            except HTTPException as exc:
                if exc.status_code != 422:
                    raise
                expected = []
            changed = {b['id'] for b in blocks if block_status(case, b) != 'CURRENT'}
            changed |= {b['id'] for b in expected} ^ {b['id'] for b in blocks}
            pending = any(b.get('suggestion') for b in blocks)
            for block in blocks:
                block['freshnessStatus'] = block_status(case, block)
                if block['id'] not in {b['id'] for b in expected}:
                    block['freshnessStatus'] = 'STALE'
                block['basisObjectCount'] = len(block['_basis'])
                block['frozenBasis'] = [dict(objectId=identity,
                    text=(obj.get('normalizedStatement') or obj.get('text') or obj.get('label') or obj.get('title') or obj.get('displayName') or identity) if obj else 'Missing basis',
                    sourceLocator=dict(sourceId=obj['sourceId'], sourceVersionId=obj['sourceVersionId'], locator=obj.get('locator'), claimId=identity)
                    if obj and obj.get('sourceId') and obj.get('sourceVersionId') else None)
                    for identity, obj in block['_basis'].items()]
                outputs['artifactBlocks'].append({k: v for k, v in block.items() if not k.startswith('_')})
            artifact.update(pendingCaseChangeCount=len(changed), freshnessStatus='STALE' if changed else 'CURRENT',
                            syncStatus='STALE' if changed else 'CURRENT', blockIds=[b['id'] for b in blocks],
                            approvalStatus='APPROVED' if saved.get('approval') and not changed and saved['approval']['caseVersion'] == case['caseVersion'] else 'DRAFT',
                            canApprove=bool(blocks) and not changed and not pending,
                            revisionId=saved['revisionId'], approval=saved.get('approval'))
            if artifact['type'] == 'IC_MEMO':
                artifact['editorialProfile'] = saved.get('editorialProfile')
                artifact['editorialUpdateAvailable'] = (saved.get('editorialProfile') or {}).get('versionId') != profile_context['profile']['versionId']
            outputs['artifacts'].append(artifact)
        return outputs

    def mutate(self, case, actor, command, *, writer=None):
        action = command.get('action') or {}
        if not isinstance(action, dict):
            raise HTTPException(422, 'An output action object is required.')
        operation = action.get('type')
        if not isinstance(operation, str) or operation not in {'SAVE_EDITORIAL_PROFILE', 'APPLY_EDITORIAL_PROFILE', 'CREATE_ARTIFACT', 'SYNC_ARTIFACT', 'REDRAFT_ARTIFACT', 'UPDATE_ARTIFACT_BLOCK', 'ACCEPT_ARTIFACT_SUGGESTION', 'DISMISS_ARTIFACT_SUGGESTION', 'APPROVE_ARTIFACT'}:
            raise HTTPException(422, 'Unsupported output command.')
        needed = 'EDIT_EDITORIAL_PROFILE' if operation == 'SAVE_EDITORIAL_PROFILE' else 'APPROVE_ARTIFACT' if operation == 'APPROVE_ARTIFACT' else 'SYNC_ARTIFACT' if operation in {'SYNC_ARTIFACT', 'REDRAFT_ARTIFACT'} else 'EDIT_ARTIFACT'
        if needed not in actor.get('entitlements', []) or actor.get('actorId') != command.get('actorId'):
            raise HTTPException(403, 'Your authenticated role cannot perform this output action.')
        request_id = command.get('requestId')
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 180:
            raise HTTPException(422, 'A command request ID is required.')
        if operation == 'SAVE_EDITORIAL_PROFILE':
            with self.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                saved_profile = editorial.save_profile(case, actor, command, db)
            return {'revisionId': saved_profile['versionId']}
        case_id, version = case['caseRef']['id'], case['caseVersion']
        request_hash = digest(command)
        suggestions = None
        if operation == 'REDRAFT_ARTIFACT':
            # A remote writing call must never hold the database's write lock.
            with self.connect() as db:
                repeat = db.execute('SELECT request_hash,payload FROM revisions WHERE case_id=? AND request_id=?', (case_id, request_id)).fetchone()
            if repeat:
                if repeat[0] != request_hash:
                    raise HTTPException(409, 'This request ID was already used for different content.')
                return json.loads(repeat[1])
            if writer is None:
                raise HTTPException(503, 'The memo writing model is not configured.')
            identity = action.get('artifactId')
            if not isinstance(identity, str) or not identity:
                raise HTTPException(422, 'An output ID is required.')
            preview = self.latest(case_id, identity)
            if not preview or command.get('expectedRevision') != preview['revisionId'] or command.get('caseVersion') != version:
                raise HTTPException(409, 'Refresh the output before requesting a draft.')
            if any(block_status(case, b) != 'CURRENT' or b.get('suggestion') for b in preview['blocks']):
                raise HTTPException(409, 'Review the case updates before requesting an editorial draft.')
            from app.memo_writer import validate_redraft
            eligible = [b for b in preview['blocks'] if not b.get('editorialLocked')]
            profile = preview.get('editorialProfile')
            if profile and not callable(getattr(writer, 'redraft_with_profile', None)):
                raise HTTPException(503, 'The writing assistant must support fund editorial profiles before redrafting this memo.')
            result = writer.redraft_with_profile(eligible, profile) if profile else writer(eligible)
            suggestions = validate_redraft(eligible, result)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            previous_request = db.execute('SELECT request_hash,payload FROM revisions WHERE case_id=? AND request_id=?', (case_id, request_id)).fetchone()
            if previous_request:
                if previous_request[0] != request_hash:
                    raise HTTPException(409, 'This request ID was already used for different content.')
                return json.loads(previous_request[1])
            if command.get('caseVersion') != version:
                raise HTTPException(409, 'The case changed. Refresh before editing this output.')
            kind = action.get('artifactType')
            artifact_id = 'OUTPUT-' + digest([case_id, kind])[7:27] if operation == 'CREATE_ARTIFACT' else action.get('artifactId')
            if not isinstance(artifact_id, str) or not artifact_id:
                raise HTTPException(422, 'An output ID is required.')
            previous = self.latest(case_id, artifact_id, db)
            if operation == 'CREATE_ARTIFACT':
                if previous:
                    raise HTTPException(409, 'This output already exists. Open its current version.')
                blocks = compile_blocks(case, kind, artifact_id)
                saved = dict(artifact=dict(id=artifact_id, type=kind, title=f"{case['caseRef']['name']} — {KINDS[kind]}", quantityIds=[q['id'] for q in case.get('quantities', []) if q.get('institutionalState') in {'CURRENT', 'APPROVED'}], institutionalState='CANDIDATE'), blocks=blocks)
                if kind == 'IC_MEMO':
                    saved['editorialProfile'] = editorial.current_profile(case, db)
                    blocks = saved['blocks'] = editorial.arrange_blocks(blocks, saved['editorialProfile'])
            else:
                if not previous:
                    raise HTTPException(404, 'Output not found in this case.')
                if command.get('expectedRevision') != previous['revisionId']:
                    raise HTTPException(409, 'The output changed. Refresh before saving.')
                saved = copy.deepcopy(previous)
                blocks = saved['blocks']
            saved.pop('approval', None)
            at = now()
            if operation == 'APPLY_EDITORIAL_PROFILE':
                if saved['artifact']['type'] != 'IC_MEMO':
                    raise HTTPException(422, 'Editorial fund profiles apply to IC memos.')
                if any(b.get('suggestion') for b in blocks):
                    raise HTTPException(409, 'Review the pending passage proposals before applying a profile.')
                profile = editorial.current_profile(case, db)
                if action.get('expectedProfileVersion') != profile['versionId']:
                    raise HTTPException(409, 'The fund profile changed. Reload before applying it.')
                if (saved.get('editorialProfile') or {}).get('versionId') == profile['versionId']:
                    raise HTTPException(409, 'This memo already uses the current fund profile.')
                saved['editorialProfile'] = profile
                blocks = saved['blocks'] = editorial.arrange_blocks(blocks, profile)
            elif operation == 'SYNC_ARTIFACT':
                try:
                    compiled = compile_blocks(case, saved['artifact']['type'], artifact_id)
                    proposals = {b['id']: b for b in editorial.arrange_blocks(compiled, saved.get('editorialProfile'))}
                except HTTPException as exc:
                    if exc.status_code != 422:
                        raise
                    proposals = {}
                for block in blocks:
                    proposed = proposals.pop(block['id'], None)
                    if not proposed or block_status(case, block) != 'CURRENT':
                        block['_proposed'] = proposed
                        block['suggestion'] = dict(signal='Removed from the current case' if proposed is None else 'Case basis changed',
                            suggestedText=proposed['text'] if proposed else 'Remove this passage from the output.',
                            reasonObjectIds=block['boundObjectIds'], remove=proposed is None)
                        block['_proposalCase'] = version
                for block in proposals.values():
                    blocks.append({**copy.deepcopy(block), 'text': 'New passage awaiting review.', '_proposed': block,
                                   '_proposalCase': version, 'suggestion': dict(signal='New in the case', suggestedText=block['text'], reasonObjectIds=block['boundObjectIds'])})
            elif operation == 'REDRAFT_ARTIFACT':
                eligible = [b for b in blocks if not b.get('editorialLocked')]
                for block in eligible:
                    if block['id'] in suggestions:
                        proposed = {**copy.deepcopy(block), 'text': suggestions[block['id']], 'authorship': 'PANTA_SUGGESTION',
                                    'writerModel': getattr(writer, 'model', 'Configured writing assistant'), 'draftedAt': at}
                        block.update(_proposed=proposed, _proposalCase=version, suggestion=dict(signal='AI editorial draft — review against the basis',
                            suggestedText=proposed['text'], reasonObjectIds=block['boundObjectIds']))
            elif operation in {'UPDATE_ARTIFACT_BLOCK', 'ACCEPT_ARTIFACT_SUGGESTION', 'DISMISS_ARTIFACT_SUGGESTION'}:
                block = next((b for b in blocks if b['id'] == action.get('blockId')), None)
                if not block:
                    raise HTTPException(404, 'Passage not found in this output.')
                if operation == 'UPDATE_ARTIFACT_BLOCK':
                    if block.get('editorialLocked'):
                        raise HTTPException(409, 'An attributed view or decision must be changed in the case, then reviewed here.')
                    text = action.get('text')
                    if not isinstance(text, str) or not text.strip() or len(text) > 20000:
                        raise HTTPException(422, 'Enter a non-empty passage of at most 20,000 characters.')
                    block.update(text=text, authorship='HUMAN_AUTHORED', authorActorId=actor['actorId'], recordedAt=at,
                                 _basis=basis(case, block['boundObjectIds']))
                elif operation == 'ACCEPT_ARTIFACT_SUGGESTION':
                    if not block.get('suggestion'):
                        raise HTTPException(409, 'There is no pending proposal for this passage.')
                    proposed = block.get('_proposed')
                    if block.get('_proposalCase') != version or proposed and digest(proposed['_basis']) != digest(basis(case, proposed['boundObjectIds'])):
                        raise HTTPException(409, 'The proposal basis changed. Prepare a new update.')
                    if proposed is None:
                        blocks.remove(block)
                    else:
                        block.clear()
                        block.update(copy.deepcopy(proposed), reviewedBy=actor['actorId'], reviewedAt=at)
                        if block['authorship'] == 'HUMAN_AUTHORED':
                            block.update(authorActorId=actor['actorId'], recordedAt=at)
                for key in ('suggestion', '_proposed', '_proposalCase'):
                    block.pop(key, None)
            elif operation == 'APPROVE_ARTIFACT':
                projected = self.project(case)
                current = next(a for a in projected['artifacts'] if a['id'] == artifact_id)
                if not current['canApprove']:
                    raise HTTPException(409, 'Resolve missing basis and review every pending change before approving.')
                saved['approval'] = dict(actorId=actor['actorId'], recordedAt=at, caseVersion=version,
                                         contentHash=digest(blocks))
            elif operation != 'CREATE_ARTIFACT':
                raise HTTPException(422, 'Unsupported output command.')
            if saved.get('editorialProfile'):
                blocks = saved['blocks'] = editorial.arrange_blocks(blocks, saved['editorialProfile'])
            saved['artifact'].update(lastSyncedCaseVersion=version, lastSyncedAt=at)
            saved.update(caseId=case_id, recordedAt=at, actorId=actor['actorId'], action=operation,
                         priorRevisionId=previous['revisionId'] if previous else None)
            saved['revisionId'] = digest({k: v for k, v in saved.items() if k != 'revisionId'})
            db.execute('INSERT INTO revisions(case_id,artifact_id,revision_id,request_id,request_hash,payload) VALUES (?,?,?,?,?,?)',
                       (case_id, artifact_id, saved['revisionId'], request_id, request_hash, json.dumps(saved, allow_nan=False)))
            return saved

    def approved(self, case, artifact_id, revision_id):
        saved = self.latest(case['caseRef']['id'], artifact_id)
        if not saved or saved['revisionId'] != revision_id:
            raise HTTPException(409, 'Export must reference the current approved output revision.')
        current = next(a for a in self.project(case)['artifacts'] if a['id'] == artifact_id)
        if current['approvalStatus'] != 'APPROVED' or saved['approval']['contentHash'] != digest(saved['blocks']):
            raise HTTPException(409, 'Approve this exact output on the current case before exporting.')
        return saved
