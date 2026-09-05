"""Fictional admitted case for connected output acceptance; all originals are temporary."""
import copy
from app.live_outputs import COLLECTIONS
from typed_statement_fixture import build_typed_fixture

ACTOR = {'actorId': 'TEST-PARTNER', 'entitlements': ['READ_CASE', 'EDIT_ARTIFACT', 'SYNC_ARTIFACT', 'APPROVE_ARTIFACT', 'EDIT_EDITORIAL_PROFILE']}


def build_memo_cases(root, case_id='MEMO-TEST', fund=None):
    cases = []
    for amount in (5, 6):
        typed = build_typed_fixture(root, case_id, euro_amount=amount)
        claims = typed['projected']
        euro = next(c for c in claims if 'EUR ' in c['normalizedStatement'])
        verification = next(c for c in claims if 'verification remains' in c['normalizedStatement'])
        version = euro['sourceVersionId']
        case = {key: [] for key in (*COLLECTIONS, 'artifacts', 'artifactBlocks', 'artifactDiffs', 'relations', 'events',
                                   'findings', 'outcomes', 'pendingReviews', 'simulationOptions', 'decisionPaths')}
        case.update(caseRef={'id': case_id, 'name': 'Synthetic investment case'}, caseVersion=f'TEST-STATE-{amount}', asOf='2026-01-10T09:00:00Z',
                    editorialFund=fund or {'id': 'TEST-FUND-ALPHA', 'name': 'Synthetic Alpha Fund'})
        case['actors'] = [dict(id=ACTOR['actorId'], type='PERSON', displayName='Test partner', role='Partner')]
        case['sources'] = [dict(id='SRC-TYPED', type='document', title=typed['path'].name, currentVersionId=version)]
        case['sourceVersions'] = [dict(id=version, sourceId='SRC-TYPED', contentHash=version, knownAt=case['asOf'], permissionScope='case')]
        case['claims'] = [{**c, 'institutionalState': 'CURRENT'} for c in claims]
        case['questions'] = [dict(id='Q-ROUND', name='What primary capital is proposed?', workstreamId='WS-ROUND', currentCaseReadingId='READING-ROUND', questionStatus='PARTIALLY_RESOLVED', claimIds=[euro['id']], workItemIds=[], openUnknownIds=[], chronologyEventIds=[]),
            dict(id='Q-VERIFY', name='Is performance independently verified?', workstreamId='WS-VERIFY', currentCaseReadingId='READING-VERIFY', questionStatus='OPEN', claimIds=[verification['id']], workItemIds=['WORK-VERIFY'], openUnknownIds=['UNKNOWN-VERIFY'], chronologyEventIds=[])]
        case['caseReadings'] = [dict(id='READING-ROUND', questionId='Q-ROUND', text=f'The proposed primary round totals EUR {amount} million before fees. These are proposed proceeds, not funds received.', institutionalState='CURRENT', epistemicStatus='SUPPORTED', freshnessStatus='CURRENT', decisionLinkStatus='NO_DECISION', supportObjectIds=[euro['id']], independentSupportObjectIds=[], unknownIds=[], relatedObjectIds=[]),
            dict(id='READING-VERIFY', questionId='Q-VERIFY', text='Independent performance verification remains outstanding.', institutionalState='CURRENT', epistemicStatus='INSUFFICIENT', freshnessStatus='CURRENT', decisionLinkStatus='NO_DECISION', supportObjectIds=[verification['id']], independentSupportObjectIds=[], unknownIds=['UNKNOWN-VERIFY'], relatedObjectIds=[])]
        case['workstreams'] = [dict(id=q['workstreamId'], name=q['name'], currentCaseReadingId=q['currentCaseReadingId'], activeWorkItemIds=q['workItemIds'], openUnknownIds=q['openUnknownIds'], questionIds=[q['id']]) for q in case['questions']]
        case['quantities'] = [dict(id='QTY-PRIMARY', label='Primary capital proposed', value=amount, currency='EUR', unit='million', sourceObjectIds=[euro['id']], assumptionObjectIds=[], institutionalState='CURRENT', freshnessStatus='CURRENT', perimeter=dict(period='FY2026', scope='Primary round', basis='Before fees', measurement='Total cash proceeds', scenario='Base'))]
        case['humanPositions'] = [dict(id='VIEW-VERIFY', authorActorId=ACTOR['actorId'], scopeObjectId='Q-VERIFY', text='Independent verification must precede approval.', institutionalState='CURRENT', recordedAt=case['asOf'], sourceBasisIds=[verification['id']])]
        case['unknowns'] = [dict(id='UNKNOWN-VERIFY', title='Independent performance verification', status='OPEN', targetObjectIds=['Q-VERIFY'], resolutionPath='Obtain independent evidence.', workItemIds=['WORK-VERIFY'])]
        case['conditions'] = [dict(id='COND-VERIFY', label='Independent verification received', status='OPEN', sourceObjectIds=[verification['id']])]
        case['workItems'] = [dict(id='WORK-VERIFY', name='Obtain independent verification', status='ACTIVE', whatToObtain='An independently verified performance record', targetQuestionId='Q-VERIFY', sourceObjectIds=[verification['id']], ownerActorId=ACTOR['actorId'])]
        cases.append(copy.deepcopy(case))
    return cases


def simulated_writer(blocks):
    # Explicit model stub; genuine numbers/citations/versioning/HTTP remain production code.
    return {b['id']: 'For committee review: ' + b['text'] for b in blocks}


def simulated_profile_writer(blocks, profile):
    # This stub proves profile delivery, not the quality of generated Italian prose.
    prefix = 'Per il comitato: ' if profile['config']['language'].lower().startswith('ital') else 'For committee review: '
    return {b['id']: prefix + b['text'] for b in blocks}


simulated_writer.redraft_with_profile = simulated_profile_writer
