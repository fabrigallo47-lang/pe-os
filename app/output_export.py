"""Portable approved output plus frozen, addressable evidence; no external publishing."""
import csv
import io
import json
from html import escape
from urllib.parse import urlencode, quote

from fastapi import HTTPException


def render_export(saved, fmt, origin):
    title = saved['artifact']['title']
    name = saved['artifact']['type'].lower() + '-' + saved['revisionId'][7:19]
    if fmt == 'json':
        return name + '.json', 'application/json', json.dumps(saved, ensure_ascii=False, indent=2)
    if fmt == 'csv':
        if saved['artifact']['type'] not in {'MODEL', 'TRACKER'}:
            raise HTTPException(422, 'CSV is available for the model and tracker.')
        stream = io.StringIO()
        writer = csv.writer(stream)
        writer.writerow(['Section', 'Text', 'Basis IDs', 'Revision', 'Approved by'])
        safe = lambda value: "'" + value if value.lstrip().startswith(('=', '+', '-', '@')) else value
        for block in saved['blocks']:
            writer.writerow([safe(str(value)) for value in (block['title'], block['text'], ';'.join(block['boundObjectIds']), saved['revisionId'], saved['approval']['actorId'])])
        return name + '.csv', 'text/csv', stream.getvalue()
    if fmt != 'html':
        raise HTTPException(422, 'Choose HTML, JSON, or CSV for model and tracker.')
    sections = []
    for number, block in enumerate(saved['blocks'], 1):
        refs = []
        for identity, obj in block['_basis'].items():
            if not obj:
                continue
            link = ''
            if obj.get('sourceId') and obj.get('sourceVersionId'):
                url = origin.rstrip('/') + '/api/v20/cases/' + quote(saved['caseId'], safe='') + '/source-document/view?' + urlencode({
                    'source_id': obj['sourceId'], 'source_version_id': obj['sourceVersionId'], 'locator': obj.get('locator') or '', 'claim_id': identity})
                link = f' <a href="{escape(url, quote=True)}">Open cited original</a>'
            refs.append(f'<li><strong>{escape(identity)}</strong>{link}<pre>{escape(json.dumps(obj, ensure_ascii=False, indent=2))}</pre></li>')
        sections.append(f'<section id="passage-{number}"><h2>{escape(block["title"])}</h2><p>{escape(block["text"])}</p><details><summary>Frozen basis for passage {number}</summary><ul>{"".join(refs)}</ul></details></section>')
    mode = saved['artifact']['type'].lower()
    content = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(title)}</title>
<style>body{{font:17px/1.6 Georgia,serif;color:#18231f;background:#f6f5f0;margin:auto;max-width:960px;padding:48px}}h1,h2,summary,small{{font-family:system-ui,sans-serif}}h1{{font-size:32px}}h2{{font-size:21px}}section{{border-top:1px solid #c6cec8;padding:24px 0}}p{{white-space:pre-wrap}}small,summary{{color:#4b6157}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.5 monospace}}a{{color:#236346}}.deck section{{min-height:55vh;padding:60px 0}}@media print{{body{{background:white;padding:0;font-size:12pt}}details{{display:block}}.deck section{{break-after:page}}section{{break-inside:avoid}}}}</style>
<body class="{mode}"><small>Approved work product · {escape(saved['approval']['recordedAt'])}</small><h1>{escape(title)}</h1><p>Approved by {escape(saved['approval']['actorId'])}. Approval applies to this work product; it does not record an investment decision.</p><small>Output revision: {escape(saved['revisionId'])}<br>Case version: {escape(saved['approval']['caseVersion'])}</small>{''.join(sections)}<footer>Original document links require access to the PANTA server. The basis above remains frozen in this export.</footer></body></html>'''
    return name + '.html', 'text/html', content
