"""Output HTTP boundary: server-owned case, authenticated actor, exact revisions."""
import copy
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from app.output_export import render_export


def output_router(load_case, authenticate, get_store, writer=None, *, writer_label=None):
    router = APIRouter(prefix='/api/v20/cases/{case_id}/outputs')

    def context(case_id, request):
        actor = authenticate(case_id, request.headers.get('x-panta-actor', ''), request.headers.get('x-panta-session'))
        if 'READ_CASE' not in actor.get('entitlements', []):
            raise HTTPException(403, 'Case access is required.')
        case = load_case(case_id)
        if case['caseRef']['id'] != case_id:
            raise HTTPException(409, 'The case projection does not match the requested case.')
        return case, actor, get_store(case_id)

    def projection(case, store):
        return {**copy.deepcopy(case), **store.project(case), 'outputCapabilities': {
            'versioned': True, 'aiRedraftAvailable': writer is not None,
            'writerLabel': writer_label or getattr(writer, 'model', None)}}

    @router.get('')
    def read(case_id: str, request: Request):
        case, actor, store = context(case_id, request)
        return {'snapshot': projection(case, store), 'actor': actor}

    @router.post('/commands')
    def command(case_id: str, request: Request, payload: dict):
        case, actor, store = context(case_id, request)
        # Snapshot, authority and timestamps in caller data are never authoritative.
        saved = store.mutate(case, actor, payload, writer=writer)
        # A slow draft may finish after case changes: project against the latest case.
        current = load_case(case_id)
        return {'snapshot': projection(current, store), 'revisionId': saved['revisionId']}

    @router.get('/{artifact_id}/export')
    def export(case_id: str, artifact_id: str, revision: str, request: Request, format: str = 'html'):
        case, actor, store = context(case_id, request)
        saved = store.approved(case, artifact_id, revision)
        filename, media_type, content = render_export(saved, format, str(request.base_url))
        return Response(content, media_type=media_type, headers={
            'Content-Disposition': f'attachment; filename="{filename}"', 'Cache-Control': 'no-store',
            'X-Content-Type-Options': 'nosniff', 'Content-Security-Policy': "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'"})

    return router
