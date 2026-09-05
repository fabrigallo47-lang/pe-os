"""Conservative output projection of CURRENT runtime content, never extraction candidates.

This is an Artifact input projection. It does not adopt facts or create human views.
Legacy decisions without an exact frozen basis are deliberately not projected here.
"""
from app.live_outputs import COLLECTIONS, digest
from app.statement_tracking import statement_context


def project_output_case(projection):
    deal = projection['deal']
    case = {key: [] for key in (*COLLECTIONS, 'artifacts', 'artifactBlocks', 'artifactDiffs', 'relations',
                               'events', 'outcomes', 'findings', 'pendingReviews', 'simulationOptions', 'decisionPaths')}
    case.update(caseRef={'id': deal['case_id'], 'name': deal['entity']}, caseVersion=deal['as_of_state_id'], asOf=deal['as_of_date'])
    case['actors'] = [{'id': a.get('id') or a.get('participant_id'), 'type': 'PERSON', 'displayName': a.get('name') or a['id'], 'role': a.get('role')}
                      for a in projection.get('actor_directory', [])]
    # Read only the server's admitted semantic graph. Never consult candidate_graph.
    graph = deal.get('semantic_current_graph') or {}
    raw = {c.get('claim_id') or c.get('id'): c for c in deal.get('claims', [])}
    for node in graph.get('nodes', []):
        if node.get('type') != 'claim':
            continue
        identity = node.get('claim_id') or node.get('stable_id') or node.get('id')
        c = {**raw.get(identity, {}), **node}
        claim = dict(id=identity, sourceId=c.get('source_id'), sourceVersionId=c.get('source_version_id'),
                     locator=c.get('locator'), type='Source statement', label=c.get('statement') or c.get('label') or identity,
                     normalizedStatement=c.get('statement') or c.get('label'), claimKind=c.get('claim_kind'),
                     tracking=statement_context(c), institutionalState='CURRENT')
        case['claims'].append(claim)
        if claim['sourceVersionId'] and claim['sourceId']:
            case['sourceVersions'].append(dict(id=claim['sourceVersionId'], sourceId=claim['sourceId'], contentHash=claim['sourceVersionId'], knownAt=c.get('known_at'), permissionScope='case'))
            case['sources'].append(dict(id=claim['sourceId'], title=c.get('source_doc') or claim['sourceId'], type='document', currentVersionId=claim['sourceVersionId']))
    for key in ('sources', 'sourceVersions'):
        case[key] = list({item['id']: item for item in case[key]}.values())
    current = deal.get('current_graph') or {}
    for node in current.get('model_nodes', []):
        if not node.get('model_node_id'):
            continue
        case['quantities'].append(dict(id=node['model_node_id'], label=node.get('name') or node['model_node_id'],
            value=node.get('value'), unit=node.get('unit'), currency=node.get('currency'), formula=node.get('formula'),
            perimeter=dict(period=node.get('period'), scope=node.get('perimeter'), basis=node.get('basis'), scenario=node.get('scenario')),
            sourceObjectIds=node.get('input_claim_ids') or [], assumptionObjectIds=[], institutionalState='CURRENT',
            freshnessStatus=node.get('freshness_status') or 'UNKNOWN', runtimeBasis=node))
    for unknown in current.get('unknowns', []):
        if not unknown.get('unknown_id'):
            continue
        case['unknowns'].append(dict(id=unknown['unknown_id'], title=unknown.get('label') or unknown['unknown_id'],
            status='RESOLVED' if unknown.get('status') == 'CLOSED' else unknown.get('status') or 'OPEN',
            targetObjectIds=unknown.get('target_object_ids') or [], resolutionPath=unknown.get('resolution_path'),
            runtimeBasis=unknown))
    statements = current.get('stated_positions') or []
    superseded = {p.get('supersedes_stated_position_id') for p in statements}
    for position in statements:
        actor_id = position.get('stated_by')
        if position.get('stated_position_id') in superseded or not isinstance(actor_id, str) or not position.get('known_at'):
            continue
        if not any(a['id'] == actor_id for a in case['actors']):
            continue  # No fabricated attribution from source prose.
        case['humanPositions'].append(dict(id=position['stated_position_id'], authorActorId=actor_id,
            scopeObjectId=(position.get('question_ids') or [''])[0], text=position['statement'],
            recordedAt=position['known_at'], institutionalState='CURRENT', sourceBasisIds=position.get('claim_ids') or []))
    for reading in deal.get('positions', []):
        if not reading.get('system_attributed') or not reading.get('stated_position_ids'):
            continue
        # Only explicit evidence associations supplied by _semantic_rooms.
        support = [e.get('claim_id') or e.get('stated_position_id') for e in reading.get('evidence_options', [])]
        case['caseReadings'].append(dict(id=reading['id'], questionId=reading['question_id'],
            text=reading.get('reading_statement') or reading.get('proposition') or '', institutionalState='CURRENT',
            epistemicStatus=reading.get('epistemic_status', 'UNEXAMINED'), freshnessStatus=reading.get('freshness_status', 'UNKNOWN'),
            decisionLinkStatus='NO_DECISION', supportObjectIds=[i for i in support if i], independentSupportObjectIds=[],
            unknownIds=[], relatedObjectIds=[], computationVersion=reading.get('derivation_hash')))
    for question in deal.get('question_spine', []):
        identity = question.get('id') or question['question_id']
        workstream = question.get('workstream') or 'case'
        reading = next((r['id'] for r in case['caseReadings'] if r['questionId'] == identity), None)
        case['questions'].append(dict(id=identity, name=question.get('label') or question.get('title') or identity,
            workstreamId=workstream, currentCaseReadingId=reading, questionStatus=question.get('status') or 'OPEN',
            claimIds=[], workItemIds=[], openUnknownIds=[], chronologyEventIds=[]))
        if not any(w['id'] == workstream for w in case['workstreams']):
            case['workstreams'].append(dict(id=workstream, name=workstream, currentCaseReadingId=reading or '', activeWorkItemIds=[], openUnknownIds=[], questionIds=[]))
        next(w for w in case['workstreams'] if w['id'] == workstream)['questionIds'].append(identity)
    # Include the complete authoritative input digest: even an old runtime that reuses its
    # state ID cannot make an approval appear current after a content change.
    case['caseVersion'] = deal['as_of_state_id'] + '@' + digest(case)[7:]
    return case


def production_output_router():
    import os
    from pathlib import Path
    from fastapi import HTTPException
    import app.v20_router as runtime
    from app.live_outputs import OutputStore
    from app.memo_writer import configured_writer
    from app.output_routes import output_router

    def load(case_id):
        if not (runtime._case_vault_dir(case_id) / 'deal.md').exists():
            raise HTTPException(404, 'Case not found.')
        case = project_output_case(runtime._build_projection(case_id))
        # Explicit tenant binding, independent of the strategy/archetype Fund Lens.
        # Never infer fund identity from a shared default lens or a caller's payload.
        binding = runtime._case_vault_dir(case_id) / 'editorial_fund.json'
        if binding.exists():
            import json
            from app.editorial_profiles import fund_ref
            try:
                case['editorialFund'] = json.loads(binding.read_text(encoding='utf-8'))
                case['editorialFund'] = fund_ref(case)
            except (ValueError, OSError) as exc:
                raise HTTPException(503, 'The editorial fund binding cannot be read.') from exc
        return case

    def authenticate(case_id, actor_id, token):
        runtime._authenticated_principal(case_id, actor_id, query_session_id=None, header_session_id=token)
        assignment = runtime._authority_actor(case_id, actor_id) or {}
        roles = {assignment.get('role'), *(assignment.get('authority_roles') or [])}
        entitlements = ['READ_CASE']
        if roles & {'WORKSTREAM_REVIEWER', 'DEAL_PARTNER', 'PARTNER'}:
            entitlements += ['EDIT_ARTIFACT', 'SYNC_ARTIFACT']
        if roles & {'DEAL_PARTNER', 'PARTNER'}:
            entitlements += ['APPROVE_ARTIFACT', 'EDIT_EDITORIAL_PROFILE']
        return dict(actorId=actor_id, entitlements=entitlements)

    def store(case_id):
        configured = os.environ.get('PANTA_OUTPUT_DB')
        if os.environ.get('VERCEL') == '1' and not configured:
            raise HTTPException(503, 'A durable output store is required in this deployment.')
        return OutputStore(Path(configured) if configured else runtime.VAULT / 'output-revisions.sqlite3')

    return output_router(load, authenticate, store, configured_writer())
