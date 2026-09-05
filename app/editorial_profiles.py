"""Fund-owned editorial preferences, separate from case facts and authority.

Fund identity is supplied by the trusted case loader, never by a command body.
Versions are append-only in the output store; artifacts freeze the chosen version.
"""
import copy
import json
import re

from fastapi import HTTPException

SECTIONS = (
    ('investment_case', 'Investment case'), ('financial_basis', 'Financial basis'),
    ('risks', 'Risks'), ('recorded_views', 'Recorded views'),
    ('recorded_decision', 'Recorded decision'), ('open_diligence', 'Open diligence'),
    ('conditions', 'Conditions'), ('still_to_establish', 'Still to establish'),
)
TEXT_FIELDS = {
    'name': ('Standard IC memo', 120),
    'audience': ('Investment committee', 1000),
    'decisionPurpose': ('Explain the decision requested and keep unrecorded decisions explicitly open.', 2000),
    'investmentContext': ('Specify the fund strategy, investment type and stage of the process.', 2000),
    'language': ('English', 80),
    'tone': ('Direct, analytical, concise; distinguish evidence from interpretation.', 1000),
    'lengthGuidance': ('Concise main memo; detailed supporting material in appendices. Do not omit material uncertainty to meet a length target.', 2000),
    'analysisGuidance': ('Explain implications for the thesis and decision using only supplied evidence.', 3000),
    'recommendationGuidance': ('Preserve attributed human views. Do not invent a recommendation or an investment decision.', 3000),
    'numbersGuidance': ('Preserve values, units, periods, scope and precision. Distinguish historical values, forecasts and assumptions.', 3000),
    'scenarioGuidance': ('Describe only supplied scenarios and sensitivities, with their assumptions. Identify missing analysis.', 3000),
    'riskGuidance': ('Explain documented risks, mitigations, open diligence and conditions before a decision.', 3000),
    'evidenceGuidance': ('Distinguish facts, source statements, system synthesis and attributed views. Expose conflicting, missing and stale evidence.', 3000),
    'citationGuidance': ('Keep every passage linked to its frozen basis and the exact cited document version.', 2000),
    'presentationGuidance': ('Use clear section headings. Describe desired tables, charts and appendices without inventing data.', 3000),
    'qualityCriteria': ('Check completeness, source fidelity, clarity, decision relevance, contradictions, repetition and unsupported assertions.', 3000),
}


def default_config():
    return {**{key: default for key, (default, _) in TEXT_FIELDS.items()},
            'sections': [{'key': key, 'title': title} for key, title in SECTIONS]}


def validate_config(value):
    if not isinstance(value, dict) or set(value) != {*TEXT_FIELDS, 'sections'}:
        raise HTTPException(422, 'Supply the complete editorial configuration with recognized fields only.')
    config = {}
    for key, (_, limit) in TEXT_FIELDS.items():
        text = value.get(key)
        if not isinstance(text, str) or not text.strip() or len(text) > limit:
            raise HTTPException(422, f'{key} must contain between 1 and {limit} characters.')
        config[key] = text.strip()
    sections = value['sections']
    if not isinstance(sections, list) or len(sections) != len(SECTIONS):
        raise HTTPException(422, 'Keep each case content section exactly once; titles and order are customizable.')
    for section in sections:
        if not isinstance(section, dict) or set(section) != {'key', 'title'} or not isinstance(section.get('key'), str) or not isinstance(section.get('title'), str) or not 1 <= len(section['title'].strip()) <= 160:
            raise HTTPException(422, 'Each section needs a recognized key and a title of at most 160 characters.')
    if sorted(s['key'] for s in sections) != sorted(key for key, _ in SECTIONS):
        raise HTTPException(422, 'Keep each case content section exactly once.')
    config['sections'] = [{'key': s['key'], 'title': s['title'].strip()} for s in sections]
    return config


def fund_ref(case):
    fund = case.get('editorialFund')
    if fund is None:
        return None
    if not isinstance(fund, dict) or not isinstance(fund.get('id'), str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,119}', fund['id']) or not isinstance(fund.get('name'), str) or not 1 <= len(fund['name'].strip()) <= 160:
        raise HTTPException(503, 'The editorial fund binding is invalid. Ask the case administrator to correct it.')
    return {'id': fund['id'], 'name': fund['name'].strip()}


def initialize(db):
    db.execute('CREATE TABLE IF NOT EXISTS editorial_profiles (sequence INTEGER PRIMARY KEY, fund_id TEXT NOT NULL, version_id TEXT NOT NULL, request_id TEXT NOT NULL, request_hash TEXT NOT NULL, payload TEXT NOT NULL, UNIQUE(fund_id, request_id))')
    db.execute('CREATE INDEX IF NOT EXISTS editorial_fund ON editorial_profiles(fund_id, sequence)')


def current_profile(case, db):
    fund = fund_ref(case)
    if fund:
        row = db.execute('SELECT payload FROM editorial_profiles WHERE fund_id=? ORDER BY sequence DESC LIMIT 1', (fund['id'],)).fetchone()
        if row:
            return json.loads(row[0])
    from app.live_outputs import digest
    config = default_config()
    return dict(fund=fund, versionId=digest(['editorial-default-v1', fund, config]), version=0, config=config)


def context(case, db):
    profile = current_profile(case, db)
    fund = fund_ref(case)
    history = []
    if fund:
        rows = db.execute('SELECT payload FROM editorial_profiles WHERE fund_id=? ORDER BY sequence DESC', (fund['id'],)).fetchall()
        history = [{k: v for k, v in json.loads(row[0]).items() if k != 'config'} for row in rows]
    return dict(profile=profile, history=history, configurable=bool(fund),
                unavailableReason=None if fund else 'An administrator must associate this case with a fund before saving a shared editorial profile.')


def save_profile(case, actor, command, db):
    from app.live_outputs import digest, now
    if actor.get('actorId') != command.get('actorId') or 'EDIT_EDITORIAL_PROFILE' not in actor.get('entitlements', []):
        raise HTTPException(403, 'Your authenticated role cannot edit the fund editorial profile.')
    fund = fund_ref(case)
    if not fund:
        raise HTTPException(409, 'This case has no configured editorial fund.')
    action = command['action']
    if set(action) != {'type', 'config', 'expectedProfileVersion'}:
        raise HTTPException(422, 'The fund is determined by the authenticated case, not by caller data.')
    request_hash = digest([case['caseRef']['id'], command])
    prior = db.execute('SELECT request_hash,payload FROM editorial_profiles WHERE fund_id=? AND request_id=?', (fund['id'], command['requestId'])).fetchone()
    if prior:
        if prior[0] != request_hash:
            raise HTTPException(409, 'This request ID was already used for different profile content.')
        return json.loads(prior[1])
    if command.get('caseVersion') != case['caseVersion']:
        raise HTTPException(409, 'The case changed. Reload before saving the profile.')
    previous = current_profile(case, db)
    if action.get('expectedProfileVersion') != previous['versionId']:
        raise HTTPException(409, 'The fund profile changed. Reload and review the latest version before saving.')
    config = validate_config(action.get('config'))
    saved = dict(fund=fund, config=config, version=previous['version'] + 1,
                 priorVersionId=previous['versionId'], actorId=actor['actorId'], recordedAt=now())
    saved['versionId'] = digest(saved)
    db.execute('INSERT INTO editorial_profiles(fund_id,version_id,request_id,request_hash,payload) VALUES (?,?,?,?,?)',
               (fund['id'], saved['versionId'], command['requestId'], request_hash, json.dumps(saved, allow_nan=False)))
    return saved


def arrange_blocks(blocks, profile):
    """Change presentation, never object identity, text, citations or human attribution."""
    if not profile:
        return blocks
    sections = profile['config']['sections']
    defaults = {title: key for key, title in SECTIONS}
    order = {s['key']: i for i, s in enumerate(sections)}
    titles = {s['key']: s['title'] for s in sections}
    result = copy.deepcopy(blocks)
    for block in result:
        key = block.get('editorialSection') or defaults.get(block['title'], 'investment_case')
        original = block.setdefault('caseTitle', block['title'])
        block['editorialSection'] = key
        block['title'] = titles[key] + (' · ' + original if key == 'investment_case' and original != 'Investment case' else '')
    return sorted(result, key=lambda b: order[b['editorialSection']])
