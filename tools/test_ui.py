#!/usr/bin/env python3
"""
PE OS — Extraction Test UI
Local HTTP server (stdlib only). Serves a dark-mode claim-extraction workbench.

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    .venv/bin/python3 tools/test_ui.py          # opens http://localhost:8765
    .venv/bin/python3 tools/test_ui.py --port 9000
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.extract import SYSTEM_PROMPT, parse_json
from vercel.api._claim_graph import claims_to_graph
from tools.graph_store import build_from_extraction, graph_path, DealGraph

CHAT_SYSTEM = """\
You are a knowledge graph co-pilot for a PE OS private equity deal analysis tool.

You see a graph of due-diligence claims. Each node is a fact extracted from deal documents.

Node types:
- claim: metric, value, unit, period, epistemic (asserted|attested|observed|derived),
         direction (supports|contradicts|context), topic, subject, statement
- subject: the entity described (e.g. "Alderstone")
- question: a diligence question node (e.g. "qt-ebitda-quality")

Edge types and meanings:
- HAS_CLAIM   subject -> claim   entity owns the claim
- CHALLENGES  attested -> asserted  higher-trust fact challenges seller claim (>5% delta)
- CONTRADICTS direction=supports -> direction=contradicts on the same metric
- TRACKS      same metric, different period (time series link)
- REFINES     same metric, different perimeter (scope)
- CORROBORATES both support same question, different source docs
- DERIVES_FROM computed claim -> the claims its formula references
- SUPPORTS    quantitative claim -> thesis/narrative claim it proves
- BEARS_ON    claim -> question  (claim is evidence for this question)

When asked to analyse or modify the graph, respond with ONLY valid JSON — no markdown:
{
  "message": "2-3 sentence plain-English explanation of what you found or changed",
  "commands": [
    {"action": "add_node", "type": "claim", "subject": "...", "metric": "...",
     "value": "...", "unit": "...", "epistemic": "asserted|attested|observed|derived",
     "direction": "supports|contradicts|context", "period": "...", "topic": "...",
     "statement": "..."},
    {"action": "add_edge",    "source": "<metric or label>", "target": "<metric or label>", "rel": "<EDGE_TYPE>"},
    {"action": "remove_edge", "source": "<metric or label>", "target": "<metric or label>", "rel": "<EDGE_TYPE>"},
    {"action": "update_node", "find": "<metric or label>", "updates": {"field": "value"}},
    {"action": "remove_node", "find": "<metric or label>"}
  ]
}
Return ONLY the JSON object. No text before or after. No markdown fences.
"""

def _load_dotenv() -> None:
    """Load key=value pairs from .env.local (repo root) if ANTHROPIC_API_KEY not set."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return
    env_file = ROOT / ".env.local"
    if not env_file.exists():
        return
    with open(env_file) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            v = v.strip().strip('"').strip("'")
            if k.strip() and k.strip() not in os.environ:
                os.environ[k.strip()] = v

_load_dotenv()
API_KEY   = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL     = os.environ.get("PEOS_MODEL", "claude-sonnet-5")
_last_dg: DealGraph | None = None


def _pdf_to_text(pdf_bytes: bytes) -> str:
    """Extract text from PDF bytes using pdftotext (poppler) or pypdf fallback."""
    # Try pdftotext (best quality, preserves layout)
    pdftotext = (shutil.which("pdftotext") or
                 next((p for p in ["/opt/homebrew/bin/pdftotext",
                                   "/usr/local/bin/pdftotext",
                                   "/usr/bin/pdftotext"]
                       if os.path.isfile(p)), None))
    if pdftotext:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(pdf_bytes)
            tmp = f.name
        try:
            result = subprocess.run(
                [pdftotext, "-layout", tmp, "-"],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout
        finally:
            os.unlink(tmp)

    # Try pypdf (pure Python fallback)
    try:
        import pypdf, io
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n\n".join(pages)
    except ImportError:
        pass

    raise RuntimeError(
        "Could not extract text from this PDF. "
        "If poppler is missing: brew install poppler. "
        "If already installed, try: .venv/bin/pip install pypdf as fallback."
    )


def _call_api(system: str, user: str, key: str) -> str:
    """Direct API call with an explicit key (avoids module-level constant)."""
    import json as _json, urllib.request, urllib.error
    payload = {
        "model":      MODEL,
        "max_tokens": 16000,
        "system":     system,
        "messages":   [{"role": "user", "content": user}],
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=_json.dumps(payload).encode(), method="POST",
        headers={
            "Content-Type":    "application/json",
            "x-api-key":       key,
            "anthropic-version": "2023-06-01",
        })
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            blocks = _json.loads(resp.read())["content"]
            text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
            if not text:
                raise ValueError(f"no text block in response: {str(blocks)[:200]}")
            return text
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")[:400]
        raise RuntimeError(f"Anthropic API {e.code}: {e.reason}. {body}") from None

# ── HTML (self-contained) ────────────────────────────────────────────────────

HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>PE OS — Extraction Test</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg:       #0d1117;
    --surface:  #161b22;
    --surface2: #21262d;
    --border:   #30363d;
    --text:     #e6edf3;
    --muted:    #8b949e;
    --accent:   #58a6ff;
    --accent-d: #1f6feb;

    --ep-asserted:  #e3b341;
    --ep-attested:  #3fb950;
    --ep-observed:  #58a6ff;
    --ep-derived:   #d29922;
    --ep-unknown:   #6e7681;

    --mono: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', 'SF Mono',
            'Consolas', ui-monospace, monospace;
    --ui:   -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
    --radius: 6px;
  }

  html, body { height: 100%; background: var(--bg); color: var(--text); font-family: var(--ui); }

  /* ── Layout ── */
  .app { display: grid; grid-template-rows: 48px 1fr; height: 100vh; overflow: hidden; }

  .topbar {
    display: flex; align-items: center; gap: 12px;
    padding: 0 20px; border-bottom: 1px solid var(--border);
    background: var(--surface); flex-shrink: 0;
  }
  .topbar-logo { font-family: var(--mono); font-size: 13px; color: var(--accent); letter-spacing: 0.04em; }
  .topbar-sep  { color: var(--border); }
  .topbar-title { font-size: 13px; color: var(--muted); }
  .topbar-pill {
    margin-left: auto; display: flex; align-items: center; gap: 6px;
    font-family: var(--mono); font-size: 11px; color: var(--muted);
  }
  .dot { width: 7px; height: 7px; border-radius: 50%; background: var(--ep-attested); }
  .dot.pulsing { animation: pulse 1.2s ease-in-out infinite; }
  @keyframes pulse { 0%,100% { opacity:1; transform:scale(1); } 50% { opacity:.4; transform:scale(.85); } }

  .panels { display: grid; grid-template-columns: 420px 1fr; overflow: hidden; }

  /* ── Left panel ── */
  .left { display: flex; flex-direction: column; border-right: 1px solid var(--border); overflow: hidden; }

  .left-head {
    padding: 14px 16px 10px; border-bottom: 1px solid var(--border);
    font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: .08em;
  }

  .field { padding: 10px 16px 0; }
  .field label { display: block; font-size: 11px; color: var(--muted); margin-bottom: 4px; letter-spacing: .04em; }

  .field input, .field textarea, .field select {
    width: 100%; background: var(--surface2); border: 1px solid var(--border);
    border-radius: var(--radius); color: var(--text); font-family: var(--ui);
    font-size: 13px; padding: 7px 10px; outline: none; resize: none;
    transition: border-color .15s;
  }
  .field input:focus, .field textarea:focus { border-color: var(--accent-d); }

  .doc-area { flex: 1; padding: 10px 16px; display: flex; flex-direction: column; min-height: 0; }
  .doc-area label { font-size: 11px; color: var(--muted); margin-bottom: 4px; letter-spacing: .04em; display: block; }
  .doc-area textarea {
    flex: 1; background: var(--surface2); border: 1px solid var(--border);
    border-radius: var(--radius); color: var(--text); font-family: var(--mono);
    font-size: 12px; padding: 10px; outline: none; resize: none;
    line-height: 1.5; transition: border-color .15s;
  }
  .doc-area textarea:focus { border-color: var(--accent-d); }
  .doc-area textarea::placeholder { color: var(--muted); opacity: .5; }
  .doc-area.drag-over textarea { border-color: var(--accent-d); }

  .upload-row {
    display: flex; align-items: center; gap: 8px; margin-bottom: 6px;
  }
  .btn-upload {
    background: var(--surface2); border: 1px solid var(--border);
    border-radius: var(--radius); color: var(--muted); font-size: 11px;
    padding: 4px 10px; cursor: pointer; white-space: nowrap;
    transition: border-color .15s, color .15s;
  }
  .btn-upload:hover { border-color: var(--accent-d); color: var(--text); }
  .file-name {
    font-family: var(--mono); font-size: 11px; color: var(--muted);
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }
  .drop-hint {
    font-size: 11px; color: var(--muted); opacity: .5; margin-left: auto; white-space: nowrap;
  }

  .left-foot {
    padding: 12px 16px; border-top: 1px solid var(--border);
    display: flex; align-items: center; gap: 10px;
  }
  .btn-extract {
    flex: 1; background: var(--accent-d); color: #fff; border: none;
    border-radius: var(--radius); font-family: var(--ui); font-size: 13px;
    font-weight: 500; padding: 8px 16px; cursor: pointer; letter-spacing: .01em;
    transition: background .15s, opacity .15s;
  }
  .btn-extract:hover:not(:disabled) { background: var(--accent); }
  .btn-extract:disabled { opacity: .45; cursor: not-allowed; }
  .btn-clear {
    background: transparent; border: 1px solid var(--border); color: var(--muted);
    border-radius: var(--radius); font-size: 13px; padding: 8px 12px; cursor: pointer;
    transition: border-color .15s, color .15s;
  }
  .btn-clear:hover { border-color: var(--muted); color: var(--text); }

  /* ── Right panel ── */
  .right { display: flex; flex-direction: column; overflow: hidden; }

  .right-head {
    display: flex; align-items: center; gap: 12px;
    padding: 10px 16px; border-bottom: 1px solid var(--border); flex-shrink: 0;
  }
  .right-head-label { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: .08em; }
  .count-badge {
    background: var(--surface2); border: 1px solid var(--border);
    border-radius: 20px; font-family: var(--mono); font-size: 11px;
    color: var(--muted); padding: 1px 8px;
  }
  .tab-row { margin-left: auto; display: flex; gap: 2px; }
  .tab {
    background: transparent; border: 1px solid transparent;
    border-radius: var(--radius); font-size: 11px; color: var(--muted);
    padding: 3px 10px; cursor: pointer; transition: all .12s;
  }
  .tab.active { background: var(--surface2); border-color: var(--border); color: var(--text); }
  .tab:hover:not(.active) { color: var(--text); }

  .results-wrap { flex: 1; overflow-y: auto; padding: 0; display: flex; flex-direction: column; }

  .empty-state {
    flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center;
    gap: 8px; color: var(--muted); padding: 40px;
  }
  .empty-icon { font-size: 32px; opacity: .4; }
  .empty-text { font-size: 13px; text-align: center; line-height: 1.6; }

  .error-banner {
    background: #3d1a1a; border: 1px solid #6e2020; border-radius: var(--radius);
    padding: 12px 14px; font-size: 12px; font-family: var(--mono);
    color: #ff7b7b; white-space: pre-wrap; word-break: break-all; display: none;
  }

  /* ── Epistemic badge ── */
  .ep-badge {
    display: inline-block;
    font-size: 10px; font-weight: 700; padding: 2px 7px; border-radius: 4px;
    text-transform: uppercase; letter-spacing: .04em;
  }
  .ep-asserted { color: var(--ep-asserted); background: rgba(227,179,65,.15); }
  .ep-attested { color: var(--ep-attested); background: rgba(63,185,80,.15); }
  .ep-observed { color: var(--ep-observed); background: rgba(88,166,255,.15); }
  .ep-derived  { color: var(--ep-derived);  background: rgba(210,153,34,.15); }
  .ep-unknown  { color: var(--ep-unknown);  background: rgba(110,118,129,.12); }

  /* ── Claims table ── */
  .claims-table {
    width: 100%; border-collapse: collapse; table-layout: fixed; font-size: 12.5px;
  }
  .claims-table thead th {
    position: sticky; top: 0; z-index: 1; background: var(--bg);
    font-size: 10px; text-transform: uppercase; letter-spacing: .07em;
    color: var(--muted); text-align: left; padding: 8px 10px;
    border-bottom: 2px solid var(--border); white-space: nowrap; font-weight: 600;
  }
  .ct-row { cursor: pointer; user-select: none; }
  .ct-row:hover td { background: var(--surface2); }
  .ct-row.open td  { background: var(--surface); }
  .claims-table td {
    padding: 10px 10px; border-bottom: 1px solid var(--border);
    vertical-align: middle; overflow: hidden; text-overflow: ellipsis;
    white-space: nowrap; max-width: 0;
  }
  /* Column widths */
  .col-num   { width: 52px; color: var(--muted); font-family: var(--mono); font-size: 11px; }
  .col-ep    { width: 76px; }
  .col-metric{ /* flex */ font-weight: 500; color: var(--text); }
  .col-value { width: 115px; font-family: var(--mono); color: var(--accent); font-weight: 700; font-size: 13px; }
  .col-asof  { width: 90px; color: var(--muted); font-family: var(--mono); font-size: 11px; }
  .col-topic { width: 140px; font-size: 11.5px; color: var(--muted); }
  .col-src   { width: 110px; font-size: 11px; color: var(--muted); opacity: .7; }

  /* Chevron in number cell */
  .ct-chevron {
    font-size: 8px; color: var(--muted); margin-right: 5px;
    display: inline-block; transition: transform .15s; opacity: .6;
  }
  .ct-row.open .ct-chevron { transform: rotate(90deg); }

  /* Detail (expanded) row */
  .ct-detail { display: none; }
  .ct-detail.open { display: table-row; }
  .ct-detail-cell {
    padding: 14px 18px 18px !important; background: var(--surface) !important;
    white-space: normal !important; max-width: none !important;
    overflow: visible !important; border-bottom: 2px solid var(--border);
  }
  .ct-detail-inner {
    display: grid; grid-template-columns: 100px 1fr; gap: 3px 14px;
    font-size: 11.5px; max-width: 860px;
  }
  .ct-key { color: var(--muted); font-family: var(--mono); font-size: 10.5px; padding-top: 2px; white-space: nowrap; }
  .ct-val { font-family: var(--mono); font-size: 11px; word-break: break-word; line-height: 1.5; }
  .ct-stmt {
    grid-column: 1 / -1; margin-top: 12px;
    padding: 10px 13px; background: var(--surface2); border-radius: 4px;
    border-left: 3px solid var(--accent-d);
    font-size: 12.5px; line-height: 1.75; color: var(--text); font-style: italic;
  }
  .ct-stmt.dim { color: var(--muted); font-style: normal; }

  /* ── Raw JSON view ── */
  .raw-view {
    flex: 1; overflow-y: auto; padding: 12px 16px; display: none;
  }
  .raw-view pre {
    background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius);
    padding: 14px; font-family: var(--mono); font-size: 11px; color: var(--text);
    white-space: pre-wrap; word-break: break-all; line-height: 1.6;
  }

  /* ── Status bar ── */
  .statusbar {
    padding: 5px 16px; border-top: 1px solid var(--border); background: var(--surface);
    display: flex; align-items: center; gap: 12px; font-family: var(--mono);
    font-size: 11px; color: var(--muted); flex-shrink: 0;
  }
  .status-item { display: flex; align-items: center; gap: 5px; }
  .status-sep { color: var(--border); }
  .status-val { color: var(--text); }

  /* ── Graph view ── */
  .graph-view {
    flex: 1; display: none; overflow: hidden;
    flex-direction: row; min-height: 0;
  }
  .graph-canvas-wrap {
    flex: 1; position: relative; overflow: hidden;
  }
  #graph-canvas {
    width: 100%; height: 100%; display: block; cursor: grab;
  }
  #graph-canvas:active { cursor: grabbing; }
  .graph-detail {
    width: 260px; flex-shrink: 0; border-left: 1px solid var(--border);
    overflow-y: auto; padding: 14px; font-size: 12px;
    display: none;
  }
  .gd-type {
    font-size: 10px; text-transform: uppercase; letter-spacing: .08em;
    color: var(--muted); margin-bottom: 6px;
  }
  .gd-label {
    font-size: 13px; font-weight: 500; margin-bottom: 10px;
    line-height: 1.4; word-break: break-word;
  }
  .gd-grid {
    display: grid; grid-template-columns: 80px 1fr; gap: 3px 8px;
    font-family: var(--mono); font-size: 11px; margin-bottom: 10px;
  }
  .gd-key { color: var(--muted); padding-top: 1px; }
  .gd-val { word-break: break-word; line-height: 1.5; }
  .gd-stmt {
    padding: 8px; background: var(--surface2); border-radius: 4px;
    font-size: 11px; line-height: 1.6; color: var(--muted);
    border-left: 2px solid var(--border);
  }
  .graph-overlay {
    position: absolute; top: 10px; left: 12px;
    display: flex; gap: 6px;
  }
  .graph-btn {
    background: var(--surface2); border: 1px solid var(--border);
    border-radius: var(--radius); color: var(--muted); font-size: 11px;
    padding: 4px 10px; cursor: pointer;
    transition: border-color .12s, color .12s;
  }
  .graph-btn:hover { border-color: var(--accent-d); color: var(--text); }
  .graph-legend {
    position: absolute; bottom: 12px; left: 12px;
    display: flex; gap: 14px; flex-wrap: wrap;
    background: rgba(13,17,23,.7); padding: 6px 10px; border-radius: var(--radius);
  }
  .leg-item {
    display: flex; align-items: center; gap: 5px;
    font-size: 11px; color: var(--muted);
  }
  .leg-dot {
    width: 10px; height: 10px; flex-shrink: 0;
  }
  .leg-line {
    width: 18px; height: 2px; flex-shrink: 0; border-radius: 1px;
  }
  .leg-section { display: flex; align-items: center; gap: 8px; }
  .leg-sep { width: 1px; height: 16px; background: var(--border); }
  .leg-head {
    font-size: 9px; text-transform: uppercase; letter-spacing: .08em;
    color: var(--muted); font-weight: 700; margin-right: 2px;
  }

  /* ── Scrollbar ── */
  ::-webkit-scrollbar { width: 6px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
  ::-webkit-scrollbar-thumb:hover { background: var(--muted); }

  /* ── Deal health panel ── */
  .deal-health {
    padding: 8px 16px; border-bottom: 1px solid var(--border);
    display: none; flex-wrap: wrap; gap: 10px; align-items: center;
    background: var(--surface); flex-shrink: 0; min-height: 38px;
  }
  .dh-alert {
    display: flex; align-items: center; gap: 5px; padding: 3px 9px;
    border-radius: 4px; font-size: 11px; font-weight: 600; border: 1px solid;
    white-space: nowrap;
  }
  .dh-alert-red    { background: rgba(248,81,73,.1);  border-color: rgba(248,81,73,.3);  color: #f85149; }
  .dh-alert-orange { background: rgba(210,153,34,.1); border-color: rgba(210,153,34,.3); color: #d29922; }
  .dh-alert-yellow { background: rgba(227,179,65,.1); border-color: rgba(227,179,65,.3); color: #e3b341; }
  .dh-alert-green  { background: rgba(63,185,80,.1);  border-color: rgba(63,185,80,.3);  color: #3fb950; }
  .dh-sep { width: 1px; height: 18px; background: var(--border); flex-shrink: 0; }
  .dh-ep-bar { display: flex; height: 5px; border-radius: 3px; overflow: hidden; width: 90px; flex-shrink: 0; }
  .dh-ep-seg { height: 100%; }
  .dh-areas { display: flex; flex-wrap: wrap; gap: 3px; }
  .dh-area-chip {
    font-size: 9px; padding: 2px 5px; border-radius: 3px; border: 1px solid;
    font-weight: 700; letter-spacing: .02em; opacity: .28; transition: opacity .2s;
  }
  .dh-area-chip.lit { opacity: 1; }

  /* Contradiction / challenge flag on claim rows */
  .ct-flag {
    display: inline-flex; align-items: center; gap: 2px;
    font-size: 9px; padding: 1px 5px; border-radius: 3px; margin-left: 5px;
    font-weight: 700; vertical-align: middle;
  }
  .ct-flag-red    { background: rgba(248,81,73,.15); color: #f85149; }
  .ct-flag-orange { background: rgba(210,153,34,.12); color: #d29922; }
  .ct-flag-yellow { background: rgba(227,179,65,.15); color: #e3b341; }
  .ct-flag-purple { background: rgba(188,140,255,.12); color: #bc8cff; }

  @media (max-width: 768px) {
    .panels { grid-template-columns: 1fr; grid-template-rows: auto 1fr; }
    .left { border-right: none; border-bottom: 1px solid var(--border); max-height: 45vh; }
    .doc-area textarea { min-height: 120px; }
  }

  /* ── Analytics view ── */
  .analytics-view {
    flex: 1; overflow-y: auto; padding: 16px 20px; display: none;
    flex-direction: column; gap: 16px;
  }
  .an-section { display: flex; flex-direction: column; gap: 8px; }
  .an-label {
    font-size: 10px; text-transform: uppercase; letter-spacing: .08em;
    color: var(--muted); font-weight: 600;
  }
  .an-stats-row { display: flex; gap: 10px; flex-wrap: wrap; }
  .an-stat {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 8px 14px; text-align: center;
    min-width: 80px;
  }
  .an-stat-num { font-family: var(--mono); font-size: 20px; font-weight: 700; color: var(--accent); }
  .an-stat-lbl { font-size: 10px; color: var(--muted); margin-top: 2px; text-transform: uppercase; letter-spacing: .04em; }
  .an-list { display: flex; flex-direction: column; gap: 3px; }
  .an-row {
    display: flex; align-items: center; gap: 8px;
    padding: 5px 8px; border-radius: 4px;
    background: var(--surface); border: 1px solid var(--border);
    font-size: 11.5px;
  }
  .an-row:hover { border-color: var(--accent-d); }
  .an-type-pill {
    font-size: 9px; padding: 2px 6px; border-radius: 3px;
    font-weight: 700; text-transform: uppercase; letter-spacing: .04em;
    flex-shrink: 0; min-width: 52px; text-align: center;
  }
  .an-score { font-family: var(--mono); font-size: 11px; color: var(--muted); margin-left: auto; flex-shrink: 0; }
  .an-lbl { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text); }
  .an-stmt { font-size: 10.5px; color: var(--muted); margin-top: 1px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .an-contradiction {
    background: rgba(248,81,73,.06); border: 1px solid rgba(248,81,73,.2);
    border-radius: 4px; padding: 8px 10px; display: flex; flex-direction: column; gap: 3px;
  }
  .an-contra-line { font-size: 11px; display: flex; align-items: center; gap: 6px; }
  .an-contra-arrow { color: #f85149; font-size: 13px; }
  .an-contra-val { font-family: var(--mono); font-size: 12px; font-weight: 700; }
  .an-decomp-btn {
    align-self: flex-start; background: var(--surface2); border: 1px solid var(--border);
    border-radius: var(--radius); color: var(--muted); font-size: 11px;
    padding: 5px 12px; cursor: pointer; transition: all .12s;
  }
  .an-decomp-btn:hover { border-color: var(--accent-d); color: var(--text); }
  .an-decomp-btn.active { border-color: var(--accent); color: var(--accent); background: rgba(88,166,255,.08); }
  .an-empty { color: var(--muted); font-size: 12px; padding: 12px 0; text-align: center; }
  .an-type-claim     { background: rgba(88,166,255,.12); color: #58a6ff; }
  .an-type-entity    { background: rgba(88,166,255,.12); color: #58a6ff; }
  .an-type-metric    { background: rgba(227,179,65,.12); color: #e3b341; }
  .an-type-period    { background: rgba(188,140,255,.12); color: #bc8cff; }
  .an-type-source    { background: rgba(110,118,129,.12); color: #8b949e; }
  .an-type-area      { background: rgba(63,185,80,.12); color: #3fb950; }
  .an-type-question  { background: rgba(188,140,255,.12); color: #bc8cff; }
  .an-type-perimeter { background: rgba(121,192,255,.12); color: #79c0ff; }
  .an-type-author    { background: rgba(110,118,129,.10); color: #6e7681; }

  /* ── Schema view ── */
  .schema-view {
    flex: 1; overflow-y: auto; padding: 16px 20px; display: none;
    flex-direction: column; gap: 18px;
  }
  .sv-label {
    font-size: 10px; text-transform: uppercase; letter-spacing: .08em;
    color: var(--muted); font-weight: 600; margin-bottom: 8px;
  }
  .sv-section { display: flex; flex-direction: column; }
  .sv-two-col { flex-direction: row !important; gap: 24px; }
  .sv-two-col > div { flex: 1; }

  /* Node type examples */
  .sv-nodes-row { display: flex; flex-wrap: wrap; gap: 12px; }
  .sv-node-ex { width: 160px; display: flex; flex-direction: column; gap: 6px; }
  .sv-circle {
    width: 72px; height: 72px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 10px; text-align: center; padding: 6px; font-family: var(--mono);
    word-break: break-all; line-height: 1.3;
  }
  .sv-subj-c { background: rgba(88,166,255,.12); border: 2px solid #58a6ff; color: #58a6ff; }
  .sv-q-c    { background: rgba(188,140,255,.1);  border: 2px solid #bc8cff; color: #bc8cff; }
  .sv-ex-cap { font-size: 11px; font-weight: 600; color: var(--text); }
  .sv-ex-desc { font-size: 11px; color: var(--muted); line-height: 1.5; }

  .sv-card-demo {
    width: 130px; height: 46px; border-radius: 5px; border: 1px solid #30363d;
    background: var(--surface); display: flex; overflow: hidden;
  }
  .sv-card-bar { width: 3px; flex-shrink: 0; }
  .sv-att-bar  { background: #3fb950; }
  .sv-ass-bar  { background: #e3b341; }
  .sv-obs-bar  { background: #58a6ff; }
  .sv-der-bar  { background: #d29922; }
  .sv-card-inner { padding: 5px 7px; display: flex; flex-direction: column; gap: 1px; width: 100%; }
  .sv-card-metric { font-size: 9px; color: var(--muted); font-family: var(--mono); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .sv-card-value  { font-size: 12px; font-weight: 700; font-family: var(--mono); }
  .sv-card-period { font-size: 8px; color: #4d5561; font-family: var(--mono); }
  .sv-att-v { color: #3fb950; } .sv-ass-v { color: #e3b341; }
  .sv-obs-v { color: #58a6ff; } .sv-der-v { color: #d29922; }
  .sv-area-demo {
    width: 90px; padding: 8px 14px; border-radius: 6px;
    font-size: 11px; font-weight: 700; letter-spacing: .04em;
    background: #0d2218; border: 1px solid #1e5c30; color: #3fb950;
    text-align: center;
  }

  /* Epistemic row */
  .sv-ep-row { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
  .sv-ep-badge {
    font-size: 10px; font-weight: 700; padding: 3px 9px; border-radius: 4px;
    text-transform: uppercase; letter-spacing: .04em;
  }
  .sv-att-badge { background: rgba(63,185,80,.15); color: #3fb950; }
  .sv-obs-badge { background: rgba(88,166,255,.15); color: #58a6ff; }
  .sv-der-badge { background: rgba(210,153,34,.15); color: #d29922; }
  .sv-ass-badge { background: rgba(227,179,65,.15); color: #e3b341; }
  .sv-ep-desc-sm { font-size: 10px; color: var(--muted); }
  .sv-ep-gt { color: var(--muted); font-size: 14px; }

  /* Field grid */
  .sv-field-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .sv-fg-group { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 8px 10px; }
  .sv-fg-head { font-size: 10px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); margin-bottom: 6px; font-weight: 600; }
  .sv-fr { display: flex; gap: 8px; margin-bottom: 4px; }
  .sv-fr code { font-family: var(--mono); font-size: 10.5px; color: #79c0ff; white-space: nowrap; min-width: 80px; }
  .sv-fr span  { font-size: 11px; color: var(--muted); line-height: 1.4; }

  /* Macro area chips */
  .sv-area-chips { display: flex; flex-wrap: wrap; gap: 7px; }
  .sv-ac {
    padding: 5px 12px; border-radius: 4px; border: 1px solid; font-size: 11px;
    font-weight: 600; letter-spacing: .03em;
  }

  /* Edge list */
  .sv-edge-list { display: flex; flex-direction: column; gap: 3px; }
  .sv-edge-row { display: flex; align-items: center; gap: 8px; padding: 4px 6px; border-radius: 4px; }
  .sv-edge-row:hover { background: var(--surface2); }
  .sv-edge-sem { padding-left: 12px; }
  .sv-eline { width: 20px; height: 2px; border-radius: 1px; flex-shrink: 0; }
  .sv-ename { font-family: var(--mono); font-size: 10.5px; color: var(--text); min-width: 100px; }
  .sv-edesc { font-size: 11px; color: var(--muted); }

  /* ── Build / Playground view ── */
  .build-view { flex: 1; display: none; flex-direction: row; overflow: hidden; min-height: 0; }

  .build-left {
    width: 290px; flex-shrink: 0; overflow-y: auto; display: flex;
    flex-direction: column; border-right: 1px solid var(--border);
  }
  .build-panel {
    padding: 10px 12px; border-bottom: 1px solid var(--border);
    display: flex; flex-direction: column; gap: 6px;
  }
  .build-panel-flex { flex: 1; overflow: hidden; display: flex; flex-direction: column; }
  .build-panel-title {
    font-size: 10px; text-transform: uppercase; letter-spacing: .07em;
    color: var(--muted); font-weight: 600; margin-bottom: 2px;
  }
  .build-or { text-align: center; font-size: 10px; color: var(--muted); padding: 6px 0; }
  .build-ta {
    width: 100%; height: 70px; background: var(--surface2); border: 1px solid var(--border);
    border-radius: var(--radius); color: var(--text); font-family: var(--mono);
    font-size: 11px; padding: 7px 8px; resize: none; outline: none; line-height: 1.5;
    transition: border-color .15s;
  }
  .build-ta:focus { border-color: var(--accent-d); }
  .build-row { display: flex; gap: 6px; align-items: flex-end; }
  .build-field { display: flex; flex-direction: column; gap: 3px; flex: 1; }
  .build-field-sm { flex: 0 0 90px; }
  .build-field-xs { flex: 0 0 60px; }
  .build-field-full { flex: 1; }
  .build-field label { font-size: 10px; color: var(--muted); letter-spacing: .03em; }
  .build-field input, .build-field select {
    background: var(--surface2); border: 1px solid var(--border);
    border-radius: var(--radius); color: var(--text); font-family: var(--ui);
    font-size: 12px; padding: 5px 7px; outline: none; width: 100%;
    transition: border-color .15s;
  }
  .build-field input:focus, .build-field select:focus { border-color: var(--accent-d); }
  .build-btn {
    background: var(--surface2); border: 1px solid var(--border);
    border-radius: var(--radius); color: var(--text); font-size: 12px;
    padding: 6px 12px; cursor: pointer; width: 100%; transition: border-color .15s, background .15s;
  }
  .build-btn:hover { border-color: var(--accent-d); background: var(--surface); }
  .build-btn-primary { background: var(--accent-d); border-color: var(--accent-d); color: #fff; }
  .build-btn-primary:hover { background: var(--accent); border-color: var(--accent); }
  .build-btn:disabled { opacity: .4; cursor: not-allowed; }
  .build-edge-form { display: flex; gap: 4px; align-items: center; flex-wrap: wrap; }
  .build-sel { flex: 1; min-width: 0; background: var(--surface2); border: 1px solid var(--border);
    border-radius: var(--radius); color: var(--text); font-size: 11px; padding: 4px 5px; }
  .build-rel-sel { flex: 0 0 100px; font-size: 10.5px; }
  .build-tip { font-size: 10px; color: var(--muted); line-height: 1.4; }
  .build-node-list { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 3px; padding: 4px 0; }
  .build-node-item {
    display: flex; align-items: center; gap: 7px; padding: 5px 8px;
    border-radius: var(--radius); cursor: pointer; transition: background .1s;
  }
  .build-node-item:hover { background: var(--surface2); }
  .build-node-item.selected { background: var(--surface); border: 1px solid var(--border); }
  .bni-bar { width: 3px; height: 24px; border-radius: 2px; flex-shrink: 0; }
  .bni-info { flex: 1; min-width: 0; }
  .bni-metric { font-size: 11px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .bni-sub    { font-size: 10px; color: var(--muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .bni-del    { font-size: 13px; color: var(--muted); cursor: pointer; padding: 2px 4px; border-radius: 3px; flex-shrink: 0; }
  .bni-del:hover { background: var(--surface2); color: #f85149; }

  .build-right { flex: 1; position: relative; overflow: hidden; }
  #build-canvas { width: 100%; height: 100%; display: block; cursor: grab; }
  #build-canvas:active { cursor: grabbing; }
  .build-overlay { position: absolute; top: 10px; left: 12px; display: flex; gap: 6px; }
  .build-status {
    position: absolute; bottom: 12px; left: 12px;
    font-size: 11px; color: var(--muted); background: rgba(13,17,23,.8);
    padding: 4px 10px; border-radius: 4px; pointer-events: none;
    transition: opacity .3s; opacity: 0;
  }
  .build-status.show { opacity: 1; }

  /* ── Chat panel ── */
  .build-chat { flex: 0 0 auto; border-top: 1px solid var(--border); display: flex; flex-direction: column; }
  .build-chat-head {
    display: flex; align-items: center; justify-content: space-between;
    padding: 7px 12px; cursor: pointer; user-select: none;
  }
  .build-chat-head:hover { background: var(--surface2); }
  .build-chat-title {
    font-size: 10px; text-transform: uppercase; letter-spacing: .07em;
    color: var(--muted); font-weight: 600;
  }
  .build-chat-toggle { font-size: 10px; color: var(--muted); transition: transform .15s; }
  .build-chat.open .build-chat-toggle { transform: rotate(180deg); }
  .build-chat-body { display: none; flex-direction: column; }
  .build-chat.open .build-chat-body { display: flex; }
  .chat-history {
    max-height: 200px; overflow-y: auto; display: flex; flex-direction: column;
    gap: 5px; padding: 8px 10px;
  }
  .chat-msg { border-radius: 5px; padding: 6px 9px; font-size: 11.5px; line-height: 1.55; max-width: 92%; }
  .chat-msg-user  { background: var(--surface2); align-self: flex-end; color: var(--text); }
  .chat-msg-claude {
    align-self: flex-start;
    background: rgba(30,77,122,.12); border: 1px solid rgba(88,166,255,.2);
    color: var(--text);
  }
  .chat-msg-badge { font-size: 9px; color: #3fb950; margin-top: 3px; }
  .chat-msg-thinking { color: var(--muted); font-style: italic; font-size: 11px; }
  .chat-input-row { display: flex; gap: 5px; align-items: flex-end; padding: 6px 10px 8px; }
  .chat-ta {
    flex: 1; height: 42px; resize: none; background: var(--surface2);
    border: 1px solid var(--border); border-radius: var(--radius);
    color: var(--text); font-family: var(--ui); font-size: 11.5px;
    padding: 6px 8px; outline: none; line-height: 1.4;
    transition: border-color .15s;
  }
  .chat-ta:focus { border-color: var(--accent-d); }
  .chat-send-btn {
    flex-shrink: 0; width: 42px; height: 42px; background: var(--accent-d);
    border: none; border-radius: var(--radius); color: #fff;
    font-size: 16px; cursor: pointer; display: flex; align-items: center;
    justify-content: center; transition: background .15s;
  }
  .chat-send-btn:hover { background: var(--accent); }
  .chat-send-btn:disabled { opacity: .4; cursor: not-allowed; }

</style>
</head>
<body>
<div class="app">

  <!-- Topbar -->
  <header class="topbar">
    <span class="topbar-logo">PE OS</span>
    <span class="topbar-sep">›</span>
    <span class="topbar-title">Extraction Workbench</span>
    <div class="topbar-pill">
      <span class="dot" id="dot"></span>
      <span id="model-label">MODEL_PLACEHOLDER</span>
    </div>
  </header>

  <div class="panels">

    <!-- Left: input -->
    <div class="left">
      <div class="left-head">Input</div>

      <div class="field" style="padding-top:12px">
        <label>ANTHROPIC API KEY</label>
        <input type="password" id="api-key" autocomplete="off"
          placeholder="KEY_PLACEHOLDER"
          style="font-family:var(--mono);letter-spacing:.05em">
      </div>

      <div class="field">
        <label>DEAL CONTEXT</label>
        <input type="text" id="deal-ctx" value="test"
          placeholder="e.g. Project Keystone — PE acquisition of Alderstone">
      </div>

      <div class="doc-area" id="doc-area">
        <div class="upload-row">
          <label class="btn-upload" for="file-input">↑ Upload file</label>
          <input type="file" id="file-input" accept=".md,.txt,.html,.csv,.json,.pdf"
            style="display:none" onchange="handleFileInput(this)">
          <span class="file-name" id="file-name">no file loaded</span>
          <span class="drop-hint">or drop here</span>
        </div>
        <textarea id="doc-text"
          placeholder="Paste text here, or upload / drop a file above (.md .txt .html .csv .json)…

The extractor will:
  · Identify every factual claim
  · Assign epistemic type (asserted / attested / observed / derived)
  · Tag period + perimeter
  · Provide a source locator"></textarea>
      </div>

      <div class="left-foot">
        <button class="btn-extract" id="btn" onclick="runExtract()">Extract claims</button>
        <button class="btn-clear" onclick="clearAll()">Clear</button>
      </div>
    </div>

    <!-- Right: results -->
    <div class="right">
      <div class="right-head">
        <span class="right-head-label">Claims</span>
        <span class="count-badge" id="count-badge">0</span>
        <div class="tab-row">
          <button class="tab active" id="tab-cards"     onclick="switchTab('cards')">Cards</button>
          <button class="tab" id="tab-raw"         onclick="switchTab('raw')">JSON</button>
          <button class="tab" id="tab-graph"       onclick="switchTab('graph')">Graph</button>
          <button class="tab" id="tab-analytics"   onclick="switchTab('analytics')">Analytics</button>
          <button class="tab" id="tab-schema"      onclick="switchTab('schema')">Schema</button>
          <button class="tab" id="tab-build"       onclick="switchTab('build')">Build</button>
        </div>
      </div>

      <div class="error-banner" id="error-banner"></div>

      <div class="deal-health" id="deal-health"></div>

      <div class="results-wrap" id="results-wrap">
        <div class="empty-state" id="empty-state">
          <div class="empty-icon">⬡</div>
          <div class="empty-text">Paste a document on the left<br>and click <strong>Extract claims</strong></div>
        </div>
      </div>

      <div class="raw-view" id="raw-view">
        <pre id="raw-pre">—</pre>
      </div>

      <div class="graph-view" id="graph-view">
        <div class="graph-canvas-wrap">
          <canvas id="graph-canvas"></canvas>
          <div class="graph-overlay">
            <button class="graph-btn" onclick="fitView()" title="Fit all nodes in view">⊡ Fit</button>
            <button class="graph-btn" onclick="resetView()" title="Reset pan/zoom">↺ Reset</button>
            <button class="graph-btn" id="btn-decomposed" onclick="toggleDecomposed()" title="Show decomposed property graph (metric/period/source as nodes)">⬡ Decomposed</button>
          </div>
          <div class="graph-legend">
            <div class="leg-section">
              <span class="leg-head">Nodes</span>
              <span class="leg-item"><span class="leg-dot" style="background:rgba(88,166,255,.25);border:2px solid #58a6ff;border-radius:50%"></span>Subject</span>
              <span class="leg-item"><span class="leg-dot" style="background:rgba(63,185,80,.2);border:2px solid #3fb950;border-radius:3px"></span>Att</span>
              <span class="leg-item"><span class="leg-dot" style="background:rgba(227,179,65,.2);border:2px solid #e3b341;border-radius:3px"></span>Ass</span>
              <span class="leg-item"><span class="leg-dot" style="background:rgba(88,166,255,.2);border:2px solid #58a6ff;border-radius:3px"></span>Obs</span>
              <span class="leg-item"><span class="leg-dot" style="background:rgba(210,153,34,.2);border:2px solid #d29922;border-radius:3px"></span>Der</span>
              <span class="leg-item"><span class="leg-dot" style="background:rgba(188,140,255,.2);border:2px solid #bc8cff;border-radius:50%"></span>Q</span>
            </div>
            <div class="leg-sep"></div>
            <div class="leg-section">
              <span class="leg-head">Edges</span>
              <span class="leg-item"><span class="leg-line" style="background:#f85149"></span>Contradicts</span>
              <span class="leg-item"><span class="leg-line" style="background:#e3b341"></span>Challenges</span>
              <span class="leg-item"><span class="leg-line" style="background:#bc8cff;opacity:.7"></span>Tracks</span>
              <span class="leg-item"><span class="leg-line" style="background:#3fb950"></span>Corroborates</span>
              <span class="leg-item"><span class="leg-line" style="background:#79c0ff;opacity:.7"></span>Refines</span>
              <span class="leg-item"><span class="leg-line" style="background:#d29922"></span>Derives</span>
              <span class="leg-item"><span class="leg-line" style="background:#ff7b72;opacity:.9"></span>Supersedes</span>
            </div>
          </div>
        </div>
        <div class="graph-detail" id="graph-detail">
          <div style="color:var(--muted);font-size:12px;padding-top:20px;text-align:center">Click a node<br>to see details</div>
        </div>
      </div>

      <!-- Schema reference view -->
      <div class="schema-view" id="schema-view">
        <div class="sv-section">
          <div class="sv-label">Node types</div>
          <div class="sv-nodes-row">
            <div class="sv-node-ex">
              <div class="sv-circle sv-subj-c">Entity</div>
              <div class="sv-ex-cap">Subject</div>
              <div class="sv-ex-desc">The entity being described. One node per unique subject string (e.g. "Alderstone").</div>
            </div>
            <div class="sv-node-ex">
              <div class="sv-card-demo">
                <div class="sv-card-bar sv-att-bar"></div>
                <div class="sv-card-inner">
                  <div class="sv-card-metric">EBITDA</div>
                  <div class="sv-card-value sv-att-v">$11.9m</div>
                  <div class="sv-card-period">FY2025A</div>
                </div>
              </div>
              <div class="sv-ex-cap">Claim (attested)</div>
              <div class="sv-ex-desc">A single extracted fact. Green bar = attested (QoE / IC). Highest trust.</div>
            </div>
            <div class="sv-node-ex">
              <div class="sv-card-demo">
                <div class="sv-card-bar sv-ass-bar"></div>
                <div class="sv-card-inner">
                  <div class="sv-card-metric">Largest customer</div>
                  <div class="sv-card-value sv-ass-v">7.6%</div>
                  <div class="sv-card-period">FY2025E</div>
                </div>
              </div>
              <div class="sv-ex-cap">Claim (asserted)</div>
              <div class="sv-ex-desc">Yellow bar = seller / management claim. Lowest trust. Challenged by attested.</div>
            </div>
            <div class="sv-node-ex">
              <div class="sv-card-demo">
                <div class="sv-card-bar sv-der-bar"></div>
                <div class="sv-card-inner">
                  <div class="sv-card-metric">Ultimate-parent conc.</div>
                  <div class="sv-card-value sv-der-v">18.2%</div>
                  <div class="sv-card-period">FY2025E</div>
                </div>
              </div>
              <div class="sv-ex-cap">Claim (derived)</div>
              <div class="sv-ex-desc">Orange bar = computed from other claims. Requires derivation field.</div>
            </div>
            <div class="sv-node-ex">
              <div class="sv-circle sv-q-c">qt-ebitda-quality</div>
              <div class="sv-ex-cap">Question</div>
              <div class="sv-ex-desc">Diligence question from the library. Claims attach evidence to it via BEARS_ON.</div>
            </div>
            <div class="sv-node-ex">
              <div class="sv-area-demo">Earnings</div>
              <div class="sv-ex-cap">Macro area</div>
              <div class="sv-ex-desc">Background cluster grouping claims by topic. 8 universal areas.</div>
            </div>
          </div>
        </div>

        <div class="sv-section">
          <div class="sv-label">Epistemic trust  (highest → lowest)</div>
          <div class="sv-ep-row">
            <span class="sv-ep-badge sv-att-badge">attested</span>
            <span class="sv-ep-desc-sm">QoE firm / IC decision / Firm underwriting</span>
            <span class="sv-ep-gt">›</span>
            <span class="sv-ep-badge sv-obs-badge">observed</span>
            <span class="sv-ep-desc-sm">Direct measurement / data room workpaper</span>
            <span class="sv-ep-gt">›</span>
            <span class="sv-ep-badge sv-der-badge">derived</span>
            <span class="sv-ep-desc-sm">Computed from other stated values</span>
            <span class="sv-ep-gt">›</span>
            <span class="sv-ep-badge sv-ass-badge">asserted</span>
            <span class="sv-ep-desc-sm">Seller / management claim, no external verification</span>
          </div>
        </div>

        <div class="sv-section sv-two-col">
          <div>
            <div class="sv-label">Claim fields</div>
            <div class="sv-field-grid">
              <div class="sv-fg-group">
                <div class="sv-fg-head">Identity</div>
                <div class="sv-fr"><code>subject</code><span>entity being described ("Alderstone")</span></div>
                <div class="sv-fr"><code>metric</code><span>what is measured ("EBITDA")</span></div>
                <div class="sv-fr"><code>value + unit</code><span>the numeric fact ("11.9", "m")</span></div>
              </div>
              <div class="sv-fg-group">
                <div class="sv-fg-head">Scope</div>
                <div class="sv-fr"><code>period</code><span>time reference ("FY2025A")</span></div>
                <div class="sv-fr"><code>perimeter</code><span>economic boundary ("consolidated")</span></div>
                <div class="sv-fr"><code>as_of</code><span>point-in-time snapshot date</span></div>
              </div>
              <div class="sv-fg-group">
                <div class="sv-fg-head">Provenance</div>
                <div class="sv-fr"><code>epistemic</code><span>attested | observed | derived | asserted</span></div>
                <div class="sv-fr"><code>author</code><span>who produced it ("Big4 Advisory")</span></div>
                <div class="sv-fr"><code>source_doc</code><span>which artifact ("QoE Report")</span></div>
                <div class="sv-fr"><code>locator</code><span>where in artifact ("Sheet1!D42")</span></div>
              </div>
              <div class="sv-fg-group">
                <div class="sv-fg-head">Graph links</div>
                <div class="sv-fr"><code>bears_on</code><span>question IDs → BEARS_ON edges</span></div>
                <div class="sv-fr"><code>direction</code><span>supports | contradicts | context</span></div>
                <div class="sv-fr"><code>topic</code><span>macro area for clustering</span></div>
                <div class="sv-fr"><code>derivation</code><span>formula (for derived claims)</span></div>
                <div class="sv-fr"><code>statement</code><span>full sentence extracted verbatim</span></div>
              </div>
            </div>
          </div>
          <div>
            <div class="sv-label">Macro areas (auto-detected from topic)</div>
            <div class="sv-area-chips">
              <div class="sv-ac" style="background:#0d2236;border-color:#1e4d7a;color:#58a6ff">Revenue</div>
              <div class="sv-ac" style="background:#0d2218;border-color:#1e5c30;color:#3fb950">Earnings</div>
              <div class="sv-ac" style="background:#2a1010;border-color:#5c2020;color:#f85149">Customer</div>
              <div class="sv-ac" style="background:#1a0d2a;border-color:#3d1a6e;color:#bc8cff">Market</div>
              <div class="sv-ac" style="background:#2a1d0d;border-color:#6e4a1a;color:#e3b341">Operations</div>
              <div class="sv-ac" style="background:#0d1a2a;border-color:#1a4a6e;color:#79c0ff">Structure</div>
              <div class="sv-ac" style="background:#1a2a0d;border-color:#4a6e1a;color:#7ee787">Governance</div>
              <div class="sv-ac" style="background:#2a180d;border-color:#6e3a1a;color:#d29922">Returns</div>
            </div>
            <div class="sv-label" style="margin-top:14px">Edge types</div>
            <div class="sv-edge-list">
              <div class="sv-edge-row"><span class="sv-eline" style="background:#1e2d3a"></span><span class="sv-ename">HAS_CLAIM</span><span class="sv-edesc">subject → claim (entity owns it)</span></div>
              <div class="sv-edge-row"><span class="sv-eline" style="background:#6e7681;opacity:.6"></span><span class="sv-ename">BEARS_ON</span><span class="sv-edesc">claim → question (evidence for this question)</span></div>
              <div class="sv-edge-row sv-edge-sem"><span class="sv-eline" style="background:#f85149"></span><span class="sv-ename">CONTRADICTS</span><span class="sv-edesc">supports vs contradicts, same subject</span></div>
              <div class="sv-edge-row sv-edge-sem"><span class="sv-eline" style="background:#e3b341"></span><span class="sv-ename">CHALLENGES</span><span class="sv-edesc">higher-trust vs lower-trust, values differ &gt;5%</span></div>
              <div class="sv-edge-row sv-edge-sem"><span class="sv-eline" style="background:#bc8cff;opacity:.7"></span><span class="sv-ename">TRACKS</span><span class="sv-edesc">same metric + subject, different period</span></div>
              <div class="sv-edge-row sv-edge-sem"><span class="sv-eline" style="background:#3fb950"></span><span class="sv-ename">CORROBORATES</span><span class="sv-edesc">both support same question, different sources</span></div>
              <div class="sv-edge-row sv-edge-sem"><span class="sv-eline" style="background:#79c0ff;opacity:.7"></span><span class="sv-ename">REFINES</span><span class="sv-edesc">same metric, different perimeter (narrower scope)</span></div>
              <div class="sv-edge-row sv-edge-sem"><span class="sv-eline" style="background:#d29922"></span><span class="sv-ename">DERIVES_FROM</span><span class="sv-edesc">derived claim names another's metric in derivation</span></div>
              <div class="sv-edge-row sv-edge-sem"><span class="sv-eline" style="background:#9ecbff;opacity:.7"></span><span class="sv-ename">SUPPORTS</span><span class="sv-edesc">quantitative claim → thesis/narrative claim it proves</span></div>
              <div class="sv-edge-row sv-edge-sem"><span class="sv-eline" style="background:#ff7b72"></span><span class="sv-ename">SUPERSEDES</span><span class="sv-edesc">higher-trust contradicts claim → displaced lower-trust supports claim</span></div>
            </div>
          </div>
        </div>
      </div>

      <!-- Build / Playground view -->
      <div class="build-view" id="build-view">
        <div class="build-left">

          <div class="build-panel">
            <div class="build-panel-title">1 · Extract from text</div>
            <textarea id="b-text" class="build-ta" placeholder="e.g. QoE confirmed FY2025 EBITDA of $11.9m vs seller's $12.7m claim. Riverton accounts for 18.2% of revenue at ultimate-parent level."></textarea>
            <button class="build-btn build-btn-primary" onclick="buildExtract()">Extract &#x2192;</button>
          </div>

          <div class="build-or">&#x2014; or &#x2014;</div>

          <div class="build-panel">
            <div class="build-panel-title">Manual node</div>
            <div class="build-row">
              <div class="build-field"><label>Subject</label><input id="bm-subj" placeholder="Alderstone"></div>
              <div class="build-field build-field-sm">
                <label>Epistemic</label>
                <select id="bm-ep">
                  <option value="asserted">asserted</option>
                  <option value="attested">attested</option>
                  <option value="observed">observed</option>
                  <option value="derived">derived</option>
                </select>
              </div>
            </div>
            <div class="build-row">
              <div class="build-field"><label>Metric</label><input id="bm-metric" placeholder="EBITDA"></div>
              <div class="build-field build-field-xs"><label>Value</label><input id="bm-value" placeholder="11.9"></div>
              <div class="build-field build-field-xs"><label>Unit</label><input id="bm-unit" placeholder="$m"></div>
            </div>
            <div class="build-row">
              <div class="build-field"><label>Period / As of</label><input id="bm-period" placeholder="FY2025A"></div>
              <div class="build-field">
                <label>Topic / Macro area</label>
                <select id="bm-topic">
                  <option value="">— none —</option>
                  <option>Revenue</option><option>Earnings</option><option>Customer</option>
                  <option>Market</option><option>Operations</option><option>Structure</option>
                  <option>Governance</option><option>Returns</option>
                </select>
              </div>
            </div>
            <div class="build-row">
              <div class="build-field"><label>Source doc</label><input id="bm-src" placeholder="QoE Report"></div>
            </div>
            <div class="build-row">
              <div class="build-field build-field-full"><label>Statement (optional)</label><input id="bm-stmt" placeholder="QoE confirmed normalized EBITDA of $11.9m"></div>
            </div>
            <button class="build-btn" onclick="buildAddManual()">Add node</button>
          </div>

          <div class="build-panel">
            <div class="build-panel-title">2 · Connect nodes</div>
            <div class="build-edge-form">
              <select id="be-from" class="build-sel"></select>
              <select id="be-rel" class="build-sel build-rel-sel">
                <option value="CHALLENGES">CHALLENGES</option>
                <option value="TRACKS">TRACKS</option>
                <option value="CONTRADICTS">CONTRADICTS</option>
                <option value="CORROBORATES">CORROBORATES</option>
                <option value="REFINES">REFINES</option>
                <option value="DERIVES_FROM">DERIVES_FROM</option>
                <option value="SUPPORTS">SUPPORTS</option>
                <option value="BEARS_ON">BEARS_ON</option>
                <option value="HAS_CLAIM">HAS_CLAIM</option>
              </select>
              <select id="be-to" class="build-sel"></select>
            </div>
            <button class="build-btn" onclick="buildAddEdge()">Add edge</button>
            <div class="build-tip">Semantic edges are also auto-detected when you extract.</div>
          </div>

          <div class="build-panel build-panel-flex">
            <div class="build-panel-title">Nodes <span id="build-n-count" style="color:var(--muted);font-weight:400">0</span></div>
            <div id="build-node-list" class="build-node-list"></div>
          </div>
          </div>

          <!-- Chat with Claude -->
          <div class="build-chat open" id="build-chat">
            <div class="build-chat-head" onclick="chatToggle()">
              <span class="build-chat-title">&#x2B27; Chat with Claude</span>
              <span class="build-chat-toggle">&#x25BC;</span>
            </div>
            <div class="build-chat-body">
              <div class="chat-history" id="chat-history"></div>
              <div class="chat-input-row">
                <textarea id="chat-ta" class="chat-ta"
                  placeholder="e.g. add a CHALLENGES edge between the two concentration nodes, or: what edges are missing?"
                  onkeydown="if((event.metaKey||event.ctrlKey)&&event.key==='Enter'){chatSend();event.preventDefault();}"></textarea>
                <button class="chat-send-btn" id="chat-send-btn" onclick="chatSend()" title="Send (Cmd/Ctrl+Enter)">&#x2191;</button>
              </div>
            </div>
          </div>

        </div>

        <div class="build-right">
          <canvas id="build-canvas"></canvas>
          <div class="build-overlay">
            <button class="graph-btn" onclick="buildFit()">&#x229F; Fit</button>
            <button class="graph-btn" onclick="buildRunGraph()">&#x21BB; Re-layout</button>
            <button class="graph-btn" onclick="buildExport()">&#x2193; Save JSON</button>
            <button class="graph-btn" onclick="buildClear()">&#x2715; Clear</button>
          </div>
          <div class="build-status" id="build-status"></div>
        </div>
      </div>

      <!-- Analytics view -->
      <div class="analytics-view" id="analytics-view">
        <div class="an-section" id="an-stats-section">
          <div class="an-label">Graph stats</div>
          <div class="an-stats-row" id="an-stats-row">
            <div class="an-empty">Extract a document to see graph analytics.</div>
          </div>
        </div>
        <div class="an-section">
          <div class="an-label">PageRank — most central nodes</div>
          <div class="an-list" id="an-pr-list"><div class="an-empty">—</div></div>
        </div>
        <div class="an-section">
          <div class="an-label">Betweenness — bridge nodes</div>
          <div class="an-list" id="an-btwn-list"><div class="an-empty">—</div></div>
        </div>
        <div class="an-section">
          <div class="an-label">Contradictions</div>
          <div id="an-contra-list"><div class="an-empty">—</div></div>
        </div>
        <div class="an-section">
          <div class="an-label">Decomposed graph view</div>
          <button class="an-decomp-btn" id="an-decomp-btn" onclick="switchTab('graph'); requestAnimationFrame(toggleDecomposed)">
            Open in Graph tab &rarr;
          </button>
        </div>
      </div>

      <div class="statusbar">
        <div class="status-item">claims <span class="status-val" id="st-count">0</span></div>
        <span class="status-sep">·</span>
        <div class="status-item">time <span class="status-val" id="st-time">—</span></div>
        <span class="status-sep">·</span>
        <div class="status-item">ep <span class="status-val" id="st-ep">—</span></div>
      </div>
    </div>

  </div>
</div>

<script>
let lastClaims = [];
let lastGraph  = null;
let currentTab = 'cards';
let decomposedMode = false;
let lastDecomposedGraph = null;

// ── Graph sim state ──────────────────────────────────────────────────────────
let simNodes = [], simEdges = [];
let animId = null, selectedNode = null, draggingNode = null;
let pan = {x:0, y:0}, zoomLevel = 1;
let isPanning = false, lastMouse = null;

function switchTab(tab) {
  currentTab = tab;
  ['cards','raw','graph','analytics','schema','build'].forEach(t => {
    document.getElementById('tab-' + t).classList.toggle('active', t === tab);
  });
  document.getElementById('results-wrap').style.display    = tab === 'cards'     ? 'flex' : 'none';
  document.getElementById('raw-view').style.display        = tab === 'raw'       ? 'flex' : 'none';
  document.getElementById('graph-view').style.display      = tab === 'graph'     ? 'flex' : 'none';
  document.getElementById('analytics-view').style.display  = tab === 'analytics' ? 'flex' : 'none';
  document.getElementById('schema-view').style.display     = tab === 'schema'    ? 'flex' : 'none';
  document.getElementById('build-view').style.display      = tab === 'build'     ? 'flex' : 'none';
  if (tab === 'graph' && lastGraph) requestAnimationFrame(() => {
    if (decomposedMode && lastDecomposedGraph) initGraph(lastDecomposedGraph);
    else initGraph(lastGraph);
  });
  if (tab === 'analytics') requestAnimationFrame(() => loadAnalytics());
  if (tab === 'build') requestAnimationFrame(() => buildInit());
}

function epClass(ep) {
  const m = { asserted:'ep-asserted', attested:'ep-attested', observed:'ep-observed', derived:'ep-derived' };
  return m[ep] || 'ep-unknown';
}

function esc(s) {
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function val(s) {
  if (!s) return '<span class="cg-val dim">—</span>';
  return '<span class="cg-val">' + esc(s) + '</span>';
}

function renderRow(item, idx, flagSet) {
  const ep      = item.epistemic || 'unknown';
  const metric  = esc(item.metric || item.subject || '—');
  const rawVal  = item.value ? item.value + (item.unit ? ' ' + item.unit : '') : '';
  const value   = esc(rawVal);
  const asof    = esc(item.as_of || item.period || '');
  const topic   = esc(item.topic || '');
  const src     = esc(item.source_doc || '');
  const bears   = Array.isArray(item.bears_on) ? item.bears_on.join(', ') : (item.bears_on || '');
  const stmt    = esc(item.statement || '');
  const hasStmt = !!(item.statement || '').trim();
  const numStr  = String(idx).padStart(2, '0');

  // Claim node id is 0-indexed, padded: claim:000, claim:001 ...
  const nodeId = 'claim:' + String(idx-1).padStart(3,'0');
  let flags = '';
  if (flagSet) {
    if (flagSet.SUPERSEDES && flagSet.SUPERSEDES.has(nodeId))
      flags += '<span class="ct-flag ct-flag-orange">↩ superseded</span>';
    if (flagSet.CONTRADICTS && flagSet.CONTRADICTS.has(nodeId))
      flags += '<span class="ct-flag ct-flag-red">⚡ contradicts</span>';
    if (flagSet.CHALLENGES && flagSet.CHALLENGES.has(nodeId))
      flags += '<span class="ct-flag ct-flag-yellow">⚠ challenged</span>';
  }

  const rows = [
    ['subject',   item.subject],
    ['period',    item.period],
    ['perimeter', item.perimeter],
    ['author',    item.author],
    ['locator',   item.locator],
    ['direction', item.direction],
    ['bears-on',  bears],
  ].filter(([,v]) => v);
  if (item.derivation) rows.push(['derivation', item.derivation]);

  const gridHtml = rows.map(([k,v]) =>
    `<span class="ct-key">${k}</span><span class="ct-val">${esc(String(v))}</span>`
  ).join('');

  return `
<tr class="ct-row" onclick="toggleRow(${idx})">
  <td class="col-num"><span class="ct-chevron">▶</span>${numStr}</td>
  <td class="col-ep"><span class="ep-badge ${epClass(ep)}">${ep.slice(0,3)}</span></td>
  <td class="col-metric" title="${metric}">${metric}${flags}</td>
  <td class="col-value">${value || '<span style="color:var(--muted)">—</span>'}</td>
  <td class="col-asof">${asof}</td>
  <td class="col-topic" title="${topic}">${topic}</td>
  <td class="col-src" title="${src}">${src}</td>
</tr>
<tr class="ct-detail" id="detail-${idx}">
  <td colspan="7" class="ct-detail-cell">
    <div class="ct-detail-inner">
      ${gridHtml}
      <div class="ct-stmt${hasStmt ? '' : ' dim'}">${hasStmt ? stmt : 'no statement extracted'}</div>
    </div>
  </td>
</tr>`;
}

function toggleRow(idx) {
  const det = document.getElementById('detail-' + idx);
  const row = document.querySelector('[onclick="toggleRow(' + idx + ')"]');
  const open = det.classList.toggle('open');
  if (row) row.classList.toggle('open', open);
}
function clearAll() {
  document.getElementById('doc-text').value = '';
  document.getElementById('results-wrap').innerHTML =
    '<div class="empty-state" id="empty-state"><div class="empty-icon">⬡</div>' +
    '<div class="empty-text">Paste a document on the left<br>and click <strong>Extract claims</strong></div></div>';
  document.getElementById('raw-pre').textContent = '—';
  document.getElementById('count-badge').textContent = '0';
  document.getElementById('st-count').textContent = '0';
  document.getElementById('st-time').textContent = '—';
  document.getElementById('st-ep').textContent = '—';
  document.getElementById('error-banner').style.display = 'none';
  document.getElementById('deal-health').style.display = 'none';
  document.getElementById('graph-detail').style.display = 'none';
  const cv = document.getElementById('graph-canvas');
  const ctx = cv.getContext('2d');
  ctx.clearRect(0, 0, cv.width, cv.height);
  if (animId) { cancelAnimationFrame(animId); animId = null; }
  lastClaims = []; lastGraph = null; lastDecomposedGraph = null;
  decomposedMode = false;
  const dbtn = document.getElementById('btn-decomposed');
  if (dbtn) { dbtn.classList.remove('active'); dbtn.textContent = '⬡ Decomposed'; }
  simNodes = []; simEdges = [];
}

async function runExtract() {
  const text = document.getElementById('doc-text').value.trim();
  if (!text) return;

  const btn  = document.getElementById('btn');
  const dot  = document.getElementById('dot');
  const wrap = document.getElementById('results-wrap');
  const err  = document.getElementById('error-banner');

  btn.disabled = true; btn.textContent = 'Extracting…';
  dot.classList.add('pulsing');
  err.style.display = 'none';
  wrap.innerHTML = '<div class="empty-state"><div class="empty-icon" style="animation:pulse 1.2s infinite">⟳</div><div class="empty-text">Running extractor…</div></div>';
  document.getElementById('count-badge').textContent = '…';

  const t0 = Date.now();
  let claims = [];

  try {
    const key = document.getElementById('api-key').value.trim();
    const res = await fetch('/extract', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text,
        deal: document.getElementById('deal-ctx').value.trim() || 'test',
        api_key: key,
      })
    });
    const data = await res.json();
    if (data.error) throw new Error(data.error);
    claims = data.claims || [];
    lastGraph = data.graph || null;
  } catch (e) {
    err.textContent = e.message;
    err.style.display = 'block';
    wrap.innerHTML = '<div class="empty-state"><div class="empty-icon">✕</div><div class="empty-text">Extraction failed — see error above</div></div>';
    btn.disabled = false; btn.textContent = 'Extract claims';
    dot.classList.remove('pulsing');
    return;
  }

  const elapsed = ((Date.now() - t0) / 1000).toFixed(1) + 's';
  lastClaims = claims;

  // Build flag sets: which claim node IDs are involved in alert edges
  const flagSet = { CONTRADICTS: new Set(), CHALLENGES: new Set(), SUPERSEDES: new Set() };
  if (lastGraph) {
    (lastGraph.edges || []).forEach(e => {
      if (flagSet[e.rel]) { flagSet[e.rel].add(e.source); flagSet[e.rel].add(e.target); }
    });
  }

  // Render all claims as a table
  wrap.innerHTML = '';
  const tbody = claims.map((item, i) => renderRow(item, i + 1, flagSet)).join('');
  wrap.innerHTML =
    '<table class="claims-table">'
    + '<thead><tr>'
    + '<th class="col-num">#</th>'
    + '<th class="col-ep">Type</th>'
    + '<th class="col-metric">Metric / Claim</th>'
    + '<th class="col-value">Value</th>'
    + '<th class="col-asof">As Of</th>'
    + '<th class="col-topic">Topic</th>'
    + '<th class="col-src">Source</th>'
    + '</tr></thead>'
    + '<tbody>' + tbody + '</tbody>'
    + '</table>';

  // Raw JSON
  document.getElementById('raw-pre').textContent = JSON.stringify(claims, null, 2);

  // Stats
  const epCounts = {};
  claims.forEach(c => { const e = c.epistemic || 'unknown'; epCounts[e] = (epCounts[e] || 0) + 1; });
  const epStr = Object.entries(epCounts).map(([k,v]) => `${k.slice(0,3)} ${v}`).join(' · ');

  document.getElementById('count-badge').textContent = claims.length;
  document.getElementById('st-count').textContent = claims.length;
  document.getElementById('st-time').textContent = elapsed;
  document.getElementById('st-ep').textContent = epStr || '—';

  // Deal health panel
  renderDealHealth(claims, lastGraph);

  if (lastGraph && currentTab === 'graph') initGraph(lastGraph);

  btn.disabled = false; btn.textContent = 'Extract claims';
  dot.classList.remove('pulsing');
}

// ── Force-directed graph ───────────────────────────────────────────

const EP_COLOR = {
  asserted: '#e3b341', attested: '#3fb950',
  observed: '#58a6ff', derived:  '#d29922',
};

// Semantic edge colors
const EDGE_META = {
  // Structural (claim → dimension, faint)
  HAS_CLAIM:   { color: '#1e2d3a', width: 1,   alpha: .25, dash: []       },
  ABOUT:       { color: '#30363d', width: 1,   alpha: .2,  dash: []       },
  MEASURES:    { color: '#e3b341', width: 1,   alpha: .28, dash: [3,2]    },
  IN_PERIOD:   { color: '#bc8cff', width: 1,   alpha: .22, dash: [3,2]    },
  SCOPED_TO:   { color: '#79c0ff', width: 1,   alpha: .18, dash: [2,3]    },
  FROM_SOURCE: { color: '#6e7681', width: 1,   alpha: .22, dash: [3,2]    },
  BY_AUTHOR:   { color: '#4d5561', width: 1,   alpha: .16, dash: [2,3]    },
  IN_AREA:     { color: null,      width: 0,   alpha: 0,   dash: []       }, // rendered as bg cluster
  BEARS_ON:    { color: '#6e7681', width: 1,   alpha: .35, dash: [4,3]    },
  // Semantic (claim → claim, vivid)
  CONTRADICTS: { color: '#f85149', width: 2,   alpha: .85, dash: []       },
  CHALLENGES:  { color: '#e3b341', width: 1.5, alpha: .8,  dash: []       },
  TRACKS:      { color: '#bc8cff', width: 1.5, alpha: .65, dash: [6,3]    },
  CORROBORATES:{ color: '#3fb950', width: 1.5, alpha: .7,  dash: []       },
  REFINES:     { color: '#79c0ff', width: 1,   alpha: .6,  dash: [3,2]    },
  DERIVES_FROM:{ color: '#d29922', width: 1,   alpha: .65, dash: [2,3]    },
  SUPPORTS:    { color: '#9ecbff', width: 1,   alpha: .55, dash: [5,3]    },
  SUPERSEDES:  { color: '#ff7b72', width: 2,   alpha: .9,  dash: [8,4]    },
};

let _graphDraw = null;  // exposed for fitView/resetView

function nodeColor(n) {
  if (n.type === 'subject'  || n.type === 'entity')    return '#58a6ff';
  if (n.type === 'question')                           return '#bc8cff';
  if (n.type === 'topic')                              return '#6e7681';
  if (n.type === 'metric')                             return '#e3b341';
  if (n.type === 'period')                             return '#bc8cff';
  if (n.type === 'source')                             return '#8b949e';
  if (n.type === 'author')                             return '#6e7681';
  if (n.type === 'area')                               return '#3fb950';
  if (n.type === 'perimeter')                          return '#79c0ff';
  return EP_COLOR[n.epistemic] || '#6e7681';
}
async function toggleDecomposed() {
  const btn = document.getElementById('btn-decomposed');
  if (!lastGraph) return;
  if (decomposedMode) {
    decomposedMode = false;
    lastDecomposedGraph = null;
    btn.classList.remove('active');
    btn.textContent = '⬡ Decomposed';
    if (currentTab === 'graph') requestAnimationFrame(() => initGraph(lastGraph));
    return;
  }
  btn.textContent = '⬡ Loading…';
  try {
    const res = await fetch('/analytics');
    const data = await res.json();
    if (!data.ready || !data.graph || !data.graph.nodes.length) {
      btn.textContent = '⬡ Decomposed';
      return;
    }
    lastDecomposedGraph = data.graph;
    decomposedMode = true;
    btn.classList.add('active');
    btn.textContent = '⬡ Claim view';
    if (currentTab === 'graph') requestAnimationFrame(() => initGraph(lastDecomposedGraph));
  } catch(e) {
    btn.textContent = '⬡ Decomposed';
    console.error('decomposed fetch error', e);
  }
}

function _anTypePill(type, text) {
  return `<span class="an-type-pill an-type-${type}">${text || type}</span>`;
}

async function loadAnalytics() {
  const prEl    = document.getElementById('an-pr-list');
  const btwnEl  = document.getElementById('an-btwn-list');
  const contraEl= document.getElementById('an-contra-list');
  const statsEl = document.getElementById('an-stats-row');
  try {
    const res  = await fetch('/analytics');
    const data = await res.json();
    if (!data.ready) {
      prEl.innerHTML    = '<div class="an-empty">Extract a document first.</div>';
      btwnEl.innerHTML  = '<div class="an-empty">—</div>';
      contraEl.innerHTML= '<div class="an-empty">—</div>';
      statsEl.innerHTML = '<div class="an-empty">No graph yet. Run an extraction to build the property graph.</div>';
      return;
    }
    // Stats chips
    const s = data.stats;
    const nt = s.node_types || {};
    const et = s.edge_types || {};
    const nodeTotal = s.nodes || 0;
    const edgeTotal = s.edges || 0;
    statsEl.innerHTML = `
      <div class="an-stat"><div class="an-stat-num">${nodeTotal}</div><div class="an-stat-lbl">Nodes</div></div>
      <div class="an-stat"><div class="an-stat-num">${edgeTotal}</div><div class="an-stat-lbl">Edges</div></div>
      ${Object.entries(nt).map(([t,c])=>`<div class="an-stat"><div class="an-stat-num" style="font-size:16px">${c}</div><div class="an-stat-lbl">${t}</div></div>`).join('')}
    `;
    // PageRank list
    function prRow(n) {
      const lbl = n.label || n.statement || n.id;
      const stmt = n.statement ? `<div class="an-stmt">${esc(n.statement.slice(0,80))}…</div>` : '';
      return `<div class="an-row">
        ${_anTypePill(n.type)}
        <div style="flex:1;overflow:hidden">
          <div class="an-lbl">${esc(lbl.slice(0,60))}</div>
          ${stmt}
        </div>
        <span class="an-score">${n.score.toFixed(4)}</span>
      </div>`;
    }
    prEl.innerHTML = data.top_pagerank.length
      ? data.top_pagerank.map(prRow).join('')
      : '<div class="an-empty">—</div>';
    btwnEl.innerHTML = data.top_betweenness.length
      ? data.top_betweenness.filter(n=>n.score>0).map(prRow).join('') || '<div class="an-empty">All scores 0 (star graph)</div>'
      : '<div class="an-empty">—</div>';
    // Contradictions
    if (data.contradictions.length) {
      contraEl.innerHTML = data.contradictions.map(c => {
        const sv = c.source.value ? `${c.source.value}${c.source.unit?' '+c.source.unit:''}` : '';
        const tv = c.target.value ? `${c.target.value}${c.target.unit?' '+c.target.unit:''}` : '';
        const sm = c.source.statement || c.source.id;
        const tm = c.target.statement || c.target.id;
        return `<div class="an-contradiction">
          <div class="an-contra-line">
            <span class="ep-badge ep-${c.source.epistemic||'unknown'}">${c.source.epistemic||'?'}</span>
            <span class="an-lbl">${esc(sm.slice(0,60))}</span>
            ${sv ? `<span class="an-contra-val">${esc(sv)}</span>` : ''}
          </div>
          <div class="an-contra-line">
            <span class="an-contra-arrow">⚡</span>
            <span class="ep-badge ep-${c.target.epistemic||'unknown'}">${c.target.epistemic||'?'}</span>
            <span class="an-lbl">${esc(tm.slice(0,60))}</span>
            ${tv ? `<span class="an-contra-val">${esc(tv)}</span>` : ''}
          </div>
        </div>`;
      }).join('');
    } else {
      contraEl.innerHTML = '<div class="an-empty">No contradictions detected.</div>';
    }
  } catch(e) {
    prEl.innerHTML = `<div class="an-empty" style="color:#f85149">Error: ${esc(String(e))}</div>`;
  }
}

function fitView() {
  if (!simNodes.length || !_graphDraw) return;
  const cv = document.getElementById('graph-canvas');
  const W = cv.width, H = cv.height, PAD = 48;
  let x0=Infinity,y0=Infinity,x1=-Infinity,y1=-Infinity;
  simNodes.forEach(n => {
    x0=Math.min(x0,n.x-n.r); y0=Math.min(y0,n.y-n.r);
    x1=Math.max(x1,n.x+n.r); y1=Math.max(y1,n.y+n.r);
  });
  const z = Math.min((W-PAD*2)/(x1-x0||1), (H-PAD*2)/(y1-y0||1), 2.5);
  zoomLevel = z;
  pan.x = W/2 - ((x0+x1)/2)*z;
  pan.y = H/2 - ((y0+y1)/2)*z;
  _graphDraw();
}

function resetView() {
  pan = {x:0, y:0}; zoomLevel = 1;
  if (_graphDraw) _graphDraw();
}

function initGraph(graph) {
  if (!graph || !graph.nodes.length) return;
  if (animId) { cancelAnimationFrame(animId); animId = null; }
  pan = {x:0, y:0}; zoomLevel = 1; selectedNode = null; draggingNode = null;

  const areaColors  = graph.area_colors        || {};
  const areaBorders = graph.area_border_colors  || {};

  const cv = document.getElementById('graph-canvas');
  cv.width  = cv.parentElement.clientWidth;
  cv.height = cv.parentElement.clientHeight;

  // Card sizing for claim nodes
  const CLAIM_W = 90, CLAIM_H = 40;
  const CLAIM_R = Math.ceil(Math.sqrt((CLAIM_W/2)**2 + (CLAIM_H/2)**2));

  const subjects = graph.nodes.filter(n => n.type === 'subject' || n.type === 'entity');
  const subjIdx  = Object.fromEntries(subjects.map((n,i) => [n.id, i]));
  const SR = Math.min(cv.width, cv.height) * 0.3;

  const nodeById = {};
  simNodes = graph.nodes.map(n => {
    if (n.type === 'topic') {
      const sn = { ...n, x: cv.width/2, y: cv.height/2, vx: 0, vy: 0, r: 0, hidden: true };
      nodeById[n.id] = sn; return sn;
    }
    let x, y, r;
    if (n.type === 'subject' || n.type === 'entity') {
      r = 18;
      const angle = (subjIdx[n.id] / Math.max(subjects.length, 1)) * Math.PI * 2;
      x = cv.width/2  + Math.cos(angle) * SR;
      y = cv.height/2 + Math.sin(angle) * SR;
    } else if (n.type === 'question') {
      r = 8;
      x = cv.width/2  + (Math.random()-.5)*cv.width*.5;
      y = cv.height/2 + (Math.random()-.5)*cv.height*.5;
    } else if (n.type === 'metric') {
      r = 14;
      x = cv.width/2  + (Math.random()-.5)*cv.width*.5;
      y = cv.height/2 + (Math.random()-.5)*cv.height*.5;
    } else if (n.type === 'period' || n.type === 'perimeter') {
      r = 8;
      x = cv.width/2  + (Math.random()-.5)*cv.width*.6;
      y = cv.height/2 + (Math.random()-.5)*cv.height*.6;
    } else if (n.type === 'source' || n.type === 'author') {
      r = 10;
      x = cv.width/2  + (Math.random()-.5)*cv.width*.65;
      y = cv.height/2 + (Math.random()-.5)*cv.height*.65;
    } else if (n.type === 'area') {
      r = 16;
      x = cv.width/2  + (Math.random()-.5)*cv.width*.4;
      y = cv.height/2 + (Math.random()-.5)*cv.height*.4;
    } else {
      r = CLAIM_R;
      const parentEdge = graph.edges.find(e =>
        (e.rel === 'HAS_CLAIM' || e.rel === 'ABOUT') && e.target === n.id);
      if (parentEdge && subjIdx[parentEdge.source] !== undefined) {
        const angle = (subjIdx[parentEdge.source] / Math.max(subjects.length, 1)) * Math.PI * 2;
        const dist  = SR * 1.1 + Math.random()*SR*0.6;
        x = cv.width/2  + Math.cos(angle)*dist + (Math.random()-.5)*60;
        y = cv.height/2 + Math.sin(angle)*dist + (Math.random()-.5)*60;
      } else {
        x = cv.width/2  + (Math.random()-.5)*cv.width*.4;
        y = cv.height/2 + (Math.random()-.5)*cv.height*.4;
      }
    }
    const sn = { ...n, x, y, vx: 0, vy: 0, r };
    nodeById[n.id] = sn; return sn;
  });

  // Exclude IN_AREA from simulation edges (topic cluster drawn as background)
  simEdges = graph.edges
    .filter(e => e.rel !== 'IN_AREA' && e.rel !== 'IN_AREA_E')
    .map(e => ({...e, source: nodeById[e.source], target: nodeById[e.target]}))
    .filter(e => e.source && e.target && !e.source.hidden && !e.target.hidden);

  let hoverNode = null;

  cv.onmousedown = e => {
    const n = hitNode(e.offsetX, e.offsetY);
    if (n) { draggingNode = n; selectedNode = n; showDetail(n); if (!animId) draw(); }
    else   { isPanning = true; lastMouse = {x:e.offsetX, y:e.offsetY}; }
  };
  cv.onmousemove = e => {
    if (draggingNode) {
      draggingNode.x = (e.offsetX - pan.x) / zoomLevel;
      draggingNode.y = (e.offsetY - pan.y) / zoomLevel;
      draggingNode.vx = draggingNode.vy = 0;
      if (!animId) { alpha = 0.2; animId = requestAnimationFrame(tick); }
    } else if (isPanning && lastMouse) {
      pan.x += e.offsetX - lastMouse.x;
      pan.y += e.offsetY - lastMouse.y;
      lastMouse = {x:e.offsetX, y:e.offsetY};
      if (!animId) draw();
    }
    const h = hitNode(e.offsetX, e.offsetY);
    if (h !== hoverNode) { hoverNode = h; if (!animId) draw(); }
    cv.style.cursor = h ? 'pointer' : isPanning ? 'grabbing' : 'grab';
  };
  cv.onmouseup = cv.onmouseleave = () => { draggingNode = null; isPanning = false; lastMouse = null; };
  cv.onwheel = e => {
    e.preventDefault();
    const f = e.deltaY < 0 ? 1.1 : 0.91;
    const newZ = Math.max(.1, Math.min(6, zoomLevel * f));
    pan.x = e.offsetX - (e.offsetX - pan.x) * newZ / zoomLevel;
    pan.y = e.offsetY - (e.offsetY - pan.y) * newZ / zoomLevel;
    zoomLevel = newZ; if (!animId) draw();
  };

  let alpha = 1;

  function tick() {
    const SPRING = 0.025, REST = 170, REST_BEARS = 240;
    const REP = 7000, GRAV = 0.006, DAMP = 0.76;

    simNodes.forEach(n => { if (!n.hidden) { n.fx = 0; n.fy = 0; } });

    for (let i = 0; i < simNodes.length; i++) {
      const a = simNodes[i]; if (a.hidden) continue;
      for (let j = i+1; j < simNodes.length; j++) {
        const b = simNodes[j]; if (b.hidden) continue;
        let dx = b.x-a.x, dy = b.y-a.y;
        const d2 = dx*dx+dy*dy || 1, d = Math.sqrt(d2);
        const f = REP / d2;
        a.fx -= f*dx/d; a.fy -= f*dy/d;
        b.fx += f*dx/d; b.fy += f*dy/d;
      }
    }

    simEdges.forEach(e => {
      if (!e.source || !e.target) return;
      const dx = e.target.x-e.source.x, dy = e.target.y-e.source.y;
      const d  = Math.sqrt(dx*dx+dy*dy) || 1;
      const rest = e.rel === 'BEARS_ON' ? REST_BEARS : REST;
      const f  = SPRING * (d - rest);
      const fx = f*dx/d, fy = f*dy/d;
      e.source.fx += fx; e.source.fy += fy;
      e.target.fx -= fx; e.target.fy -= fy;
    });

    // Area cohesion: claims in the same macro area attract each other gently,
    // creating visible clusters without fighting the per-edge springs.
    const AREA_SPRING = 0.005, AREA_REST = 120;
    for (let i = 0; i < simNodes.length; i++) {
      const a = simNodes[i];
      if (a.hidden || a.type !== 'claim' || !a.area || a.area === 'Other') continue;
      for (let j = i+1; j < simNodes.length; j++) {
        const b = simNodes[j];
        if (b.hidden || b.type !== 'claim' || b.area !== a.area) continue;
        const dx = b.x-a.x, dy = b.y-a.y;
        const d = Math.sqrt(dx*dx+dy*dy)||1;
        const f = AREA_SPRING * (d - AREA_REST);
        const fx = f*dx/d, fy = f*dy/d;
        a.fx += fx; a.fy += fy;
        b.fx -= fx; b.fy -= fy;
      }
    }

    simNodes.forEach(n => {
      if (n.hidden) return;
      n.fx += (cv.width/2  - n.x) * GRAV;
      n.fy += (cv.height/2 - n.y) * GRAV;
    });

    simNodes.forEach(n => {
      if (n.hidden || n === draggingNode) return;
      n.vx = (n.vx + n.fx) * DAMP * alpha;
      n.vy = (n.vy + n.fy) * DAMP * alpha;
      n.x += n.vx; n.y += n.vy;
    });

    alpha = Math.max(0, alpha - 0.004);
    draw();
    if (alpha > 0.001) animId = requestAnimationFrame(tick);
    else animId = null;
  }

  function drawTopicClusters(ctx) {
    const groups = {};
    simNodes.forEach(n => {
      if (n.hidden || n.type !== 'claim' || !n.area) return;
      (groups[n.area] = groups[n.area] || []).push(n);
    });
    Object.entries(groups).forEach(([area, ns]) => {
      if (ns.length < 2) return;
      let x0=Infinity,y0=Infinity,x1=-Infinity,y1=-Infinity;
      ns.forEach(n => {
        x0=Math.min(x0,n.x-CLAIM_W/2); y0=Math.min(y0,n.y-CLAIM_H/2);
        x1=Math.max(x1,n.x+CLAIM_W/2); y1=Math.max(y1,n.y+CLAIM_H/2);
      });
      const pad = 20, r = 14;
      ctx.beginPath();
      ctx.roundRect(x0-pad, y0-pad, x1-x0+pad*2, y1-y0+pad*2, r);
      ctx.fillStyle = areaColors[area] || '#161b22';
      ctx.globalAlpha = 0.55; ctx.fill(); ctx.globalAlpha = 1;
      ctx.strokeStyle = areaBorders[area] || '#30363d';
      ctx.lineWidth = 1; ctx.stroke();
      ctx.font = 'bold 10px -apple-system,system-ui,sans-serif';
      ctx.fillStyle = areaBorders[area] || '#6e7681';
      ctx.textAlign = 'left';
      ctx.globalAlpha = 0.7;
      ctx.fillText(area.toUpperCase(), x0-pad+8, y0-pad+13);
      ctx.globalAlpha = 1;
    });
  }

  function drawClaimCard(ctx, n, col, sel) {
    const isNarrative = !n.value;  // thesis/narrative node has no numeric value
    const W = isNarrative ? CLAIM_W + 20 : CLAIM_W;
    const H = isNarrative ? CLAIM_H + 10 : CLAIM_H;
    const hw = W/2, hh = H/2;
    // Card background
    ctx.beginPath();
    ctx.roundRect(n.x-hw, n.y-hh, W, H, 5);
    ctx.fillStyle = sel ? '#1c2a36' : (isNarrative ? '#0d1117' : '#161b22');
    ctx.fill();
    // Border: dashed for narrative nodes
    if (sel) { ctx.shadowColor = col; ctx.shadowBlur = 10; }
    ctx.strokeStyle = sel ? col : (isNarrative ? col + '80' : '#30363d');
    ctx.lineWidth = sel ? 2 : (isNarrative ? 1 : 1);
    if (isNarrative) ctx.setLineDash([4, 3]);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.shadowBlur = 0;
    // Left accent bar
    ctx.fillStyle = isNarrative ? col + '60' : col;
    ctx.fillRect(n.x-hw, n.y-hh+4, 3, H-8);
    // Metric / thesis label
    const metric = (n.metric || n.label || '').slice(0, isNarrative ? 20 : 15);
    ctx.font = isNarrative ? 'italic 9px ui-monospace,monospace' : '9px ui-monospace,monospace';
    ctx.fillStyle = isNarrative ? col + 'cc' : '#8b949e';
    ctx.textAlign = 'left';
    ctx.fillText(metric, n.x-hw+9, n.y - (isNarrative ? 7 : 4));
    if (isNarrative) {
      // Second line: show topic/area
      const area = (n.area || n.topic || 'thesis').slice(0, 18);
      ctx.font = '8px ui-monospace,monospace';
      ctx.fillStyle = '#4d5561';
      ctx.fillText(area, n.x-hw+9, n.y+4);
      // Third line: "thesis" badge
      ctx.font = '8px ui-monospace,monospace';
      ctx.fillStyle = col + '70';
      ctx.fillText('◇ thesis', n.x-hw+9, n.y+14);
    } else {
      // Value line
      const valStr = (n.value + (n.unit ? ' '+n.unit : '')).slice(0, 14);
      ctx.font = 'bold 11px ui-monospace,monospace';
      ctx.fillStyle = col;
      ctx.fillText(valStr, n.x-hw+9, n.y+11);
      // Period (top-right)
      const per = (n.as_of || n.period || '').slice(0, 8);
      if (per) {
        ctx.font = '8px ui-monospace,monospace';
        ctx.fillStyle = '#4d5561';
        ctx.textAlign = 'right';
        ctx.fillText(per, n.x+hw-4, n.y-4);
      }
    }
    ctx.textAlign = 'center';
  }

  function drawDiamondNode(ctx, n, col, sel) {
    const r = n.r;
    ctx.beginPath();
    ctx.moveTo(n.x,     n.y - r);
    ctx.lineTo(n.x + r, n.y);
    ctx.lineTo(n.x,     n.y + r);
    ctx.lineTo(n.x - r, n.y);
    ctx.closePath();
    ctx.fillStyle = col + '22';
    ctx.fill();
    if (sel) { ctx.shadowColor = col; ctx.shadowBlur = 12; }
    ctx.strokeStyle = sel ? col : col + 'cc';
    ctx.lineWidth = sel ? 2 : 1.5;
    ctx.stroke();
    ctx.shadowBlur = 0;
    ctx.font = '8px ui-monospace,monospace';
    ctx.fillStyle = col;
    ctx.textAlign = 'center';
    ctx.fillText((n.label || '').slice(0, 14), n.x, n.y + r + 11);
  }

  function drawPillNode(ctx, n, col, sel) {
    const lbl = (n.label || '').slice(0, 16);
    ctx.font = '8px ui-monospace,monospace';
    const tw = ctx.measureText(lbl).width;
    const pw = Math.max(32, tw + 14), ph = 15, hr = ph/2;
    ctx.beginPath();
    ctx.roundRect(n.x - pw/2, n.y - hr, pw, ph, hr);
    ctx.fillStyle = col + '1a';
    ctx.fill();
    if (sel) { ctx.shadowColor = col; ctx.shadowBlur = 10; }
    ctx.strokeStyle = sel ? col : col + 'aa';
    ctx.lineWidth = sel ? 1.5 : 1;
    ctx.stroke();
    ctx.shadowBlur = 0;
    ctx.fillStyle = col;
    ctx.textAlign = 'center';
    ctx.fillText(lbl, n.x, n.y + 4);
    // update hitbox radius for pills
    n.r = Math.max(pw/2, hr);
  }

  function drawSquareNode(ctx, n, col, sel) {
    const s = n.r * 1.7;
    ctx.beginPath();
    ctx.roundRect(n.x - s/2, n.y - s/2, s, s, 3);
    ctx.fillStyle = col + '18';
    ctx.fill();
    if (sel) { ctx.shadowColor = col; ctx.shadowBlur = 10; }
    ctx.strokeStyle = sel ? col : col + 'aa';
    ctx.lineWidth = sel ? 1.5 : 1;
    ctx.stroke();
    ctx.shadowBlur = 0;
    ctx.font = '8px ui-monospace,monospace';
    ctx.fillStyle = col;
    ctx.textAlign = 'center';
    ctx.fillText((n.label || '').slice(0, 14), n.x, n.y + n.r + 11);
  }

  function draw() {
    const ctx = cv.getContext('2d');
    ctx.clearRect(0, 0, cv.width, cv.height);
    ctx.save();
    ctx.translate(pan.x, pan.y);
    ctx.scale(zoomLevel, zoomLevel);

    // 1. Topic cluster backgrounds
    drawTopicClusters(ctx);

    // 2. Edges
    simEdges.forEach(e => {
      if (!e.source || !e.target) return;
      const meta = EDGE_META[e.rel] || EDGE_META.HAS_CLAIM;
      if (!meta.color) return;
      ctx.beginPath();
      ctx.moveTo(e.source.x, e.source.y);
      ctx.lineTo(e.target.x, e.target.y);
      ctx.strokeStyle  = meta.color;
      ctx.lineWidth    = meta.width;
      ctx.globalAlpha  = meta.alpha;
      ctx.setLineDash(meta.dash);
      ctx.stroke();
      ctx.setLineDash([]);
    });
    ctx.globalAlpha = 1;

    // 3. Nodes
    simNodes.forEach(n => {
      if (n.hidden) return;
      const col = nodeColor(n);
      const sel = n === selectedNode;
      if (n.type === 'claim') {
        drawClaimCard(ctx, n, col, sel);
      } else if (n.type === 'metric') {
        drawDiamondNode(ctx, n, col, sel);
      } else if (n.type === 'period' || n.type === 'perimeter') {
        drawPillNode(ctx, n, col, sel);
      } else if (n.type === 'source' || n.type === 'author') {
        drawSquareNode(ctx, n, col, sel);
      } else {
        ctx.beginPath();
        ctx.arc(n.x, n.y, n.r, 0, Math.PI*2);
        ctx.fillStyle = col + (n.type === 'subject' || n.type === 'entity' ? '30' : '20');
        ctx.fill();
        if (sel) { ctx.shadowColor = col; ctx.shadowBlur = 18; }
        ctx.strokeStyle = col;
        ctx.lineWidth = sel ? 2.5 : (n.type === 'subject' || n.type === 'entity') ? 2 : 1.5;
        ctx.stroke();
        ctx.shadowBlur = 0;
        if (n.type === 'subject' || n.type === 'entity') {
          const words = (n.label || n.id.split(':')[1] || '').split(' ');
          let line = '', lines = [];
          words.forEach(w => {
            const t = line ? line+' '+w : w;
            if (t.length > 16 && line) { lines.push(line); line = w; } else line = t;
          });
          if (line) lines.push(line);
          lines = lines.slice(0, 3);
          ctx.textAlign = 'center';
          ctx.font = 'bold 11px -apple-system,system-ui,sans-serif';
          ctx.fillStyle = '#c9d1d9';
          lines.forEach((l,i) => ctx.fillText(l, n.x, n.y+n.r+13+i*13));
        } else if (n.type === 'area') {
          ctx.textAlign = 'center';
          ctx.font = 'bold 9px -apple-system,system-ui,sans-serif';
          ctx.fillStyle = col + 'cc';
          ctx.fillText((n.label || '').slice(0, 12), n.x, n.y + 3);
        }
      }
    });
    ctx.restore();

    // 4. Hover tooltip (screen-space)
    if (hoverNode && hoverNode !== selectedNode && !hoverNode.hidden) {
      const tx = hoverNode.x * zoomLevel + pan.x;
      const ty = hoverNode.y * zoomLevel + pan.y;
      const tip = (hoverNode.metric || hoverNode.label || '').slice(0, 40);
      const val = hoverNode.value ? hoverNode.value + (hoverNode.unit ? ' '+hoverNode.unit : '') : '';
      const ep  = hoverNode.epistemic ? '  ·  ' + hoverNode.epistemic : '';
      ctx.font = '11px -apple-system,system-ui,sans-serif';
      const tw = Math.max(ctx.measureText(tip+ep).width, ctx.measureText(val).width) + 20;
      const th = val ? 44 : 28;
      const half_h = hoverNode.type === 'claim' ? CLAIM_H/2 : (hoverNode.r || 8);
      const bx = Math.max(4, Math.min(tx - tw/2, cv.width - tw - 4));
      const by = ty - half_h * zoomLevel - th - 8;
      ctx.fillStyle = 'rgba(13,17,23,.96)';
      ctx.strokeStyle = '#30363d'; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.roundRect(bx, by, tw, th, 4); ctx.fill(); ctx.stroke();
      ctx.fillStyle = '#e6edf3'; ctx.textAlign = 'left';
      ctx.fillText(tip + ep, bx+9, by+17);
      if (val) {
        ctx.font = 'bold 11px ui-monospace,monospace';
        ctx.fillStyle = nodeColor(hoverNode);
        ctx.fillText(val, bx+9, by+34);
      }
    }
  }
  _graphDraw = draw;

  function hitNode(mx, my) {
    const wx = (mx-pan.x)/zoomLevel, wy = (my-pan.y)/zoomLevel;
    for (let i = simNodes.length-1; i >= 0; i--) {
      const n = simNodes[i];
      if (n.hidden) continue;
      if (n.type === 'claim') {
        const W = n.value ? CLAIM_W : CLAIM_W+20;
        const H = n.value ? CLAIM_H : CLAIM_H+10;
        if (wx >= n.x-W/2 && wx <= n.x+W/2 &&
            wy >= n.y-H/2 && wy <= n.y+H/2) return n;
      } else if (n.type === 'source' || n.type === 'author') {
        const s = n.r * 1.7 / 2;
        if (wx >= n.x-s && wx <= n.x+s && wy >= n.y-s && wy <= n.y+s) return n;
      } else {
        if ((wx-n.x)**2 + (wy-n.y)**2 < (n.r+4)**2) return n;
      }
    }
    return null;
  }

  const ro = new ResizeObserver(() => {
    cv.width  = cv.parentElement.clientWidth;
    cv.height = cv.parentElement.clientHeight;
    if (!animId) draw();
  });
  ro.observe(cv.parentElement);

  animId = requestAnimationFrame(tick);
}

function showDetail(n) {
  const det = document.getElementById('graph-detail');
  det.style.display = 'block';
  const typeLabel = {'subject':'Entity','claim':'Claim','question':'Question','topic':'Area'}[n.type] || n.type;
  let html = `<div class="gd-type">${typeLabel}</div>`;
  html += `<div class="gd-label">${esc(n.label || n.id)}</div>`;
  if (n.type === 'claim') {
    const rows = [
      ['area',       n.area],
      ['metric',     n.metric],
      ['value',      n.value ? n.value + (n.unit ? ' '+n.unit : '') : ''],
      ['as_of',      n.as_of],
      ['period',     n.period],
      ['perimeter',  n.perimeter],
      ['epistemic',  n.epistemic],
      ['direction',  n.direction],
      ['topic',      n.topic],
      ['source',     n.source_doc],
      ['author',     n.author],
      ['locator',    n.locator],
    ].filter(([,v]) => v);
    html += '<div class="gd-grid">';
    rows.forEach(([k,v]) => {
      html += `<span class="gd-key">${k}</span><span class="gd-val">${esc(v)}</span>`;
    });
    html += '</div>';
    if (n.derivation) {
      html += `<div class="gd-grid"><span class="gd-key">derivation</span><span class="gd-val">${esc(n.derivation)}</span></div>`;
    }
    if (n.statement) html += `<div class="gd-stmt">${esc(n.statement)}</div>`;
  }
  det.innerHTML = html;
}
// ── Deal health panel ────────────────────────────────────────────────────────

const _DH_AREAS = ['Revenue','Earnings','Customer','Market','Operations','Structure','Governance','Returns'];
const _DH_AREA_KW = {
  Revenue:    ['revenue','recurring','backlog','billing'],
  Earnings:   ['ebitda','earnings','margin','adjustment','normaliz','qoe'],
  Customer:   ['customer','concentration','churn','retention','contract','account'],
  Market:     ['market','position','regulatory','competitive','technology'],
  Operations: ['operations','operational','integration','systems','working capital','wip','utilization','headcount'],
  Structure:  ['debt','leverage','covenant','capital structure','loan','revolver','lien'],
  Governance: ['governance','management','board','incentive'],
  Returns:    ['exit','returns','moic','irr','xirr','multiple','acquisition'],
};
const _DH_AREA_COL = {
  Revenue:'#58a6ff', Earnings:'#3fb950', Customer:'#f85149', Market:'#bc8cff',
  Operations:'#e3b341', Structure:'#79c0ff', Governance:'#7ee787', Returns:'#d29922',
};

function _topicToArea(t) {
  const tl = (t || '').toLowerCase();
  for (const [area, kws] of Object.entries(_DH_AREA_KW)) {
    if (kws.some(kw => tl.includes(kw))) return area;
  }
  return 'Other';
}

function renderDealHealth(claims, graph) {
  const el = document.getElementById('deal-health');
  if (!claims || !claims.length) { el.style.display = 'none'; return; }

  // Edge type counts
  const edgeTypes = {};
  (graph && graph.edges || []).forEach(e => {
    edgeTypes[e.rel] = (edgeTypes[e.rel] || 0) + 1;
  });
  const contradicts  = edgeTypes['CONTRADICTS']  || 0;
  const challenges   = edgeTypes['CHALLENGES']   || 0;
  const supersedes   = edgeTypes['SUPERSEDES']   || 0;
  const corroborates = edgeTypes['CORROBORATES'] || 0;

  // Epistemic distribution
  const epCounts = { attested:0, observed:0, derived:0, asserted:0 };
  claims.forEach(c => { const ep = c.epistemic||'asserted'; if(ep in epCounts) epCounts[ep]++; });
  const total = claims.length;

  // Area coverage
  const covered = new Set();
  claims.forEach(c => { const a = _topicToArea(c.topic); if(a !== 'Other') covered.add(a); });

  // Question count
  const qCount = (graph && graph.nodes || []).filter(n => n.type === 'question').length;

  let html = '';

  // ── Alert strip ──
  if (contradicts > 0)
    html += `<div class="dh-alert dh-alert-red">⚡ ${contradicts} contradiction${contradicts>1?'s':''}</div>`;
  if (supersedes > 0)
    html += `<div class="dh-alert dh-alert-orange">↩ ${supersedes} superseded</div>`;
  if (challenges > 0)
    html += `<div class="dh-alert dh-alert-yellow">⚠ ${challenges} challenge${challenges>1?'s':''}</div>`;
  if (corroborates > 0)
    html += `<div class="dh-alert dh-alert-green">✓ ${corroborates} corroborated</div>`;
  if (contradicts === 0 && challenges === 0 && supersedes === 0)
    html += `<div class="dh-alert dh-alert-green">✓ No conflicts</div>`;

  html += '<div class="dh-sep"></div>';

  // ── Epistemic bar ──
  const epOrder = ['attested','observed','derived','asserted'];
  const epCols  = { attested:'#3fb950', observed:'#58a6ff', derived:'#d29922', asserted:'#e3b341' };
  const segs = epOrder.map(ep => {
    const pct = total > 0 ? epCounts[ep] / total * 100 : 0;
    return pct > 0 ? `<div class="dh-ep-seg" style="width:${pct.toFixed(1)}%;background:${epCols[ep]}" title="${ep}: ${epCounts[ep]}"></div>` : '';
  }).join('');
  html += `<div style="display:flex;align-items:center;gap:6px;flex-shrink:0">
    <div class="dh-ep-bar" title="Epistemic mix">${segs}</div>
    <span style="font-size:10px;color:var(--muted);white-space:nowrap">${total} claims</span>
  </div>`;

  html += '<div class="dh-sep"></div>';

  // ── Area chips ──
  html += '<div class="dh-areas">';
  _DH_AREAS.forEach(area => {
    const col = _DH_AREA_COL[area];
    const lit = covered.has(area);
    html += `<div class="dh-area-chip${lit?' lit':''}" style="border-color:${col}50;color:${col};background:${col}18">${area}</div>`;
  });
  html += '</div>';

  if (qCount > 0) {
    html += '<div class="dh-sep"></div>';
    html += `<span style="font-size:10px;color:var(--muted);white-space:nowrap">${qCount} Q linked</span>`;
  }

  el.style.display = 'flex';
  el.innerHTML = html;
}

// ── File upload & drag-drop ──────────────────────────────────────────────────

function loadText(text, name) {
  document.getElementById('doc-text').value = text;
  document.getElementById('file-name').textContent = name;
}

function handleFileInput(input) {
  const file = input.files[0];
  if (!file) return;
  readFile(file);
  input.value = '';  // allow re-selecting same file
}

function readFile(file) {
  const name = file.name;
  const isPdf = file.type === 'application/pdf' || name.toLowerCase().endsWith('.pdf');

  if (isPdf) {
    document.getElementById('file-name').textContent = 'parsing PDF…';
    const reader = new FileReader();
    reader.onload = async e => {
      const base64 = e.target.result.split(',')[1];
      try {
        const res = await fetch('/parse-pdf', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ data: base64, name }),
        });
        const data = await res.json();
        if (data.error) throw new Error(data.error);
        loadText(data.text, `${name}  (${(data.chars/1000).toFixed(1)}k chars)`);
      } catch(err) {
        document.getElementById('file-name').textContent = 'PDF error: ' + err.message;
      }
    };
    reader.readAsDataURL(file);
  } else {
    const reader = new FileReader();
    reader.onload = e => loadText(e.target.result, name);
    reader.onerror = () => {
      document.getElementById('file-name').textContent = 'read error';
    };
    reader.readAsText(file);
  }
}

// Drag-and-drop onto the doc-area
const docArea = document.getElementById('doc-area');
docArea.addEventListener('dragover', e => {
  e.preventDefault();
  docArea.classList.add('drag-over');
});
docArea.addEventListener('dragleave', () => docArea.classList.remove('drag-over'));
docArea.addEventListener('drop', e => {
  e.preventDefault();
  docArea.classList.remove('drag-over');
  const file = e.dataTransfer.files[0];
  if (file) readFile(file);
});

// Ctrl+Enter to extract
document.addEventListener('keydown', e => {
  if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') runExtract();
});
// ── Build Playground ─────────────────────────────────────────────────────────

let buildG = { nodes: [], edges: [] };        // playground graph data
let buildSimN = [], buildSimE = [];           // sim state
let buildAnim = null, buildPan = {x:0,y:0}, buildZoom = 1;
let buildDragN = null, buildSelN = null, buildHoverN = null;
let buildIsPan = false, buildLastMouse = null;
let buildConnFrom = null;  // click-to-connect source node
let buildStatusTimer = null;

const BUILD_CLAIM_W = 86, BUILD_CLAIM_H = 38;
const BUILD_EP_COLOR = { asserted:'#e3b341', attested:'#3fb950', observed:'#58a6ff', derived:'#d29922' };

function buildStatus(msg) {
  const el = document.getElementById('build-status');
  el.textContent = msg; el.classList.add('show');
  clearTimeout(buildStatusTimer);
  buildStatusTimer = setTimeout(() => el.classList.remove('show'), 2500);
}

function buildInit() {
  const cv = document.getElementById('build-canvas');
  cv.width  = cv.parentElement.clientWidth;
  cv.height = cv.parentElement.clientHeight;
  buildSetupEvents(cv);
  buildRunLayout();
}

function buildSetupEvents(cv) {
  if (cv._buildEventsAttached) return;
  cv._buildEventsAttached = true;
  cv.onmousedown = e => {
    const n = buildHit(e.offsetX, e.offsetY);
    if (n) {
      if (buildConnFrom) {
        // Complete the edge connection
        if (n !== buildConnFrom) {
          const rel = document.getElementById('be-rel').value || 'CHALLENGES';
          buildG.edges.push({ source: buildConnFrom.id, target: n.id, rel });
          buildStatus('Edge added: ' + buildConnFrom.id.slice(0,14) + ' → ' + rel + ' → ' + n.id.slice(0,14));
          buildConnFrom = null;
          buildRefreshSim();
        } else {
          buildConnFrom = null;
        }
      } else {
        buildDragN = n; buildSelN = n;
        buildUpdateSelects();
        buildDraw();
      }
    } else {
      buildConnFrom = null;
      buildIsPan = true; buildLastMouse = {x:e.offsetX, y:e.offsetY};
    }
  };
  cv.onmousemove = e => {
    if (buildDragN) {
      buildDragN.x = (e.offsetX - buildPan.x) / buildZoom;
      buildDragN.y = (e.offsetY - buildPan.y) / buildZoom;
      buildDragN.vx = buildDragN.vy = 0;
      if (!buildAnim) buildDraw();
    } else if (buildIsPan && buildLastMouse) {
      buildPan.x += e.offsetX - buildLastMouse.x;
      buildPan.y += e.offsetY - buildLastMouse.y;
      buildLastMouse = {x:e.offsetX, y:e.offsetY};
      if (!buildAnim) buildDraw();
    }
    const h = buildHit(e.offsetX, e.offsetY);
    if (h !== buildHoverN) { buildHoverN = h; if (!buildAnim) buildDraw(); }
    cv.style.cursor = buildConnFrom ? 'crosshair' : (h ? 'pointer' : (buildIsPan ? 'grabbing' : 'grab'));
  };
  cv.onmouseup = cv.onmouseleave = () => { buildDragN = null; buildIsPan = false; buildLastMouse = null; };
  cv.onwheel = e => {
    e.preventDefault();
    const f = e.deltaY < 0 ? 1.1 : 0.91;
    const nz = Math.max(.1, Math.min(6, buildZoom * f));
    buildPan.x = e.offsetX - (e.offsetX - buildPan.x) * nz / buildZoom;
    buildPan.y = e.offsetY - (e.offsetY - buildPan.y) * nz / buildZoom;
    buildZoom = nz; if (!buildAnim) buildDraw();
  };
  const ro = new ResizeObserver(() => {
    cv.width  = cv.parentElement.clientWidth;
    cv.height = cv.parentElement.clientHeight;
    if (!buildAnim) buildDraw();
  });
  ro.observe(cv.parentElement);
}

function buildRunLayout() {
  if (buildAnim) { cancelAnimationFrame(buildAnim); buildAnim = null; }
  const cv = document.getElementById('build-canvas');
  const W = cv.width, H = cv.height;

  // Rebuild sim nodes from buildG.nodes
  const nodeById = {};
  const existPos = {};
  buildSimN.forEach(n => { existPos[n.id] = {x:n.x, y:n.y}; });

  buildSimN = buildG.nodes.map(n => {
    const prev = existPos[n.id];
    const x = prev ? prev.x : W/2 + (Math.random()-.5)*W*.4;
    const y = prev ? prev.y : H/2 + (Math.random()-.5)*H*.4;
    const sn = { ...n, x, y, vx: 0, vy: 0,
      r: n.type === 'subject' ? 16 : n.type === 'question' ? 8 : 46 };
    nodeById[n.id] = sn; return sn;
  });
  buildSimE = buildG.edges
    .map(e => ({...e, source: nodeById[e.source], target: nodeById[e.target]}))
    .filter(e => e.source && e.target);

  let alpha = 1;
  function tick() {
    const REP = 6000, SPRING = 0.022, REST = 160, GRAV = 0.006, DAMP = 0.76;
    buildSimN.forEach(n => { n.fx = 0; n.fy = 0; });
    for (let i = 0; i < buildSimN.length; i++) {
      const a = buildSimN[i];
      for (let j = i+1; j < buildSimN.length; j++) {
        const b = buildSimN[j];
        let dx = b.x-a.x, dy = b.y-a.y;
        const d2 = dx*dx+dy*dy||1, d = Math.sqrt(d2);
        const f = REP/d2;
        a.fx -= f*dx/d; a.fy -= f*dy/d;
        b.fx += f*dx/d; b.fy += f*dy/d;
      }
    }
    buildSimE.forEach(e => {
      if (!e.source||!e.target) return;
      const dx = e.target.x-e.source.x, dy = e.target.y-e.source.y;
      const d = Math.sqrt(dx*dx+dy*dy)||1;
      const f = SPRING*(d-REST);
      e.source.fx += f*dx/d; e.source.fy += f*dy/d;
      e.target.fx -= f*dx/d; e.target.fy -= f*dy/d;
    });
    buildSimN.forEach(n => {
      n.fx += (W/2 - n.x)*GRAV; n.fy += (H/2 - n.y)*GRAV;
    });
    buildSimN.forEach(n => {
      if (n === buildDragN) return;
      n.vx = (n.vx + n.fx)*DAMP*alpha; n.vy = (n.vy + n.fy)*DAMP*alpha;
      n.x += n.vx; n.y += n.vy;
    });
    alpha = Math.max(0, alpha - 0.006);
    buildDraw();
    if (alpha > 0.001) buildAnim = requestAnimationFrame(tick);
    else buildAnim = null;
  }
  if (buildSimN.length > 0) buildAnim = requestAnimationFrame(tick);
  else buildDraw();
}

function buildRefreshSim() {
  buildRunLayout();
  buildUpdateNodeList();
  buildUpdateSelects();
}

function buildDraw() {
  const cv = document.getElementById('build-canvas');
  const ctx = cv.getContext('2d');
  ctx.clearRect(0, 0, cv.width, cv.height);
  if (buildSimN.length === 0) {
    ctx.font = '13px -apple-system,system-ui,sans-serif';
    ctx.fillStyle = '#4d5561';
    ctx.textAlign = 'center';
    ctx.fillText('Extract a claim or add a node manually to start', cv.width/2, cv.height/2);
    return;
  }
  ctx.save();
  ctx.translate(buildPan.x, buildPan.y);
  ctx.scale(buildZoom, buildZoom);

  // Edges
  buildSimE.forEach(e => {
    if (!e.source||!e.target) return;
    const meta = EDGE_META[e.rel] || EDGE_META.HAS_CLAIM;
    if (!meta.color) return;
    ctx.beginPath();
    ctx.moveTo(e.source.x, e.source.y);
    ctx.lineTo(e.target.x, e.target.y);
    ctx.strokeStyle = meta.color; ctx.lineWidth = meta.width;
    ctx.globalAlpha = meta.alpha; ctx.setLineDash(meta.dash);
    ctx.stroke(); ctx.setLineDash([]);
  });
  ctx.globalAlpha = 1;

  // Edge label (edge type) at midpoint
  buildSimE.forEach(e => {
    if (!e.source||!e.target) return;
    const mx = (e.source.x+e.target.x)/2, my = (e.source.y+e.target.y)/2;
    const meta = EDGE_META[e.rel] || EDGE_META.HAS_CLAIM;
    ctx.font = '8px ui-monospace,monospace';
    ctx.fillStyle = meta.color || '#6e7681';
    ctx.globalAlpha = 0.7;
    ctx.textAlign = 'center';
    ctx.fillText(e.rel, mx, my - 4);
    ctx.globalAlpha = 1;
  });

  // Nodes
  buildSimN.forEach(n => {
    const col = BUILD_EP_COLOR[n.epistemic] || (n.type === 'subject' ? '#58a6ff' : n.type === 'question' ? '#bc8cff' : '#6e7681');
    const sel = n === buildSelN || n === buildConnFrom;
    if (n.type === 'claim') {
      const isNarr = !n.value;
      const BW = isNarr ? BUILD_CLAIM_W+20 : BUILD_CLAIM_W;
      const BH = isNarr ? BUILD_CLAIM_H+10 : BUILD_CLAIM_H;
      const hw = BW/2, hh = BH/2;
      ctx.beginPath(); ctx.roundRect(n.x-hw, n.y-hh, BW, BH, 5);
      ctx.fillStyle = sel ? '#1c2a36' : (isNarr ? '#0d1117' : '#161b22'); ctx.fill();
      if (sel) { ctx.shadowColor = col; ctx.shadowBlur = 10; }
      ctx.strokeStyle = sel ? col : (n === buildConnFrom ? '#f85149' : (isNarr ? col+'80' : '#30363d'));
      ctx.lineWidth = sel ? 2 : 1;
      if (isNarr) ctx.setLineDash([4,3]);
      ctx.stroke(); ctx.setLineDash([]); ctx.shadowBlur = 0;
      // Accent bar
      ctx.fillStyle = isNarr ? col+'60' : col;
      ctx.fillRect(n.x-hw, n.y-hh+4, 3, BH-8);
      // Metric / label
      ctx.font = isNarr ? 'italic 9px ui-monospace,monospace' : '9px ui-monospace,monospace';
      ctx.fillStyle = isNarr ? col+'cc' : '#8b949e'; ctx.textAlign = 'left';
      ctx.fillText((n.metric||n.label||'').slice(0, isNarr?20:16), n.x-hw+8, n.y-(isNarr?7:4));
      if (isNarr) {
        ctx.font = '8px ui-monospace,monospace'; ctx.fillStyle = '#4d5561';
        ctx.fillText((n.area||n.topic||'thesis').slice(0,18), n.x-hw+8, n.y+4);
        ctx.fillStyle = col+'70';
        ctx.fillText('◇ thesis', n.x-hw+8, n.y+14);
      } else {
        ctx.font = 'bold 11px ui-monospace,monospace'; ctx.fillStyle = col;
        ctx.fillText((n.value+(n.unit?' '+n.unit:'')).slice(0,14), n.x-hw+8, n.y+11);
      }
      // Period
      if (!isNarr && (n.period||n.as_of)) {
        ctx.font = '8px ui-monospace,monospace'; ctx.fillStyle = '#4d5561'; ctx.textAlign = 'right';
        ctx.fillText((n.period||n.as_of||'').slice(0,8), n.x+hw-4, n.y-4);
      }
    } else {
      ctx.beginPath(); ctx.arc(n.x, n.y, n.r, 0, Math.PI*2);
      ctx.fillStyle = col + (n.type==='subject'?'30':'20'); ctx.fill();
      if (sel) { ctx.shadowColor = col; ctx.shadowBlur = 14; }
      ctx.strokeStyle = col; ctx.lineWidth = sel ? 2.5 : 1.5; ctx.stroke(); ctx.shadowBlur = 0;
      ctx.textAlign = 'center'; ctx.font = 'bold 10px -apple-system,system-ui,sans-serif';
      ctx.fillStyle = '#c9d1d9';
      ctx.fillText((n.label||n.id||'').slice(0,18), n.x, n.y + n.r + 12);
    }
  });
  ctx.restore();

  // Hover tooltip
  if (buildHoverN && buildHoverN !== buildSelN) {
    const tx = buildHoverN.x*buildZoom+buildPan.x, ty = buildHoverN.y*buildZoom+buildPan.y;
    const tip = (buildHoverN.metric||buildHoverN.label||'').slice(0,40);
    const val = buildHoverN.value ? buildHoverN.value+(buildHoverN.unit?' '+buildHoverN.unit:'') : '';
    ctx.font = '11px -apple-system,system-ui,sans-serif';
    const tw = Math.max(ctx.measureText(tip).width, ctx.measureText(val).width)+20;
    const th = val?40:26;
    const half = buildHoverN.type==='claim' ? BUILD_CLAIM_H/2 : (buildHoverN.r||8);
    const bx = Math.max(4,Math.min(tx-tw/2,cv.width-tw-4)), by = ty-half*buildZoom-th-8;
    ctx.fillStyle='rgba(13,17,23,.95)'; ctx.strokeStyle='#30363d'; ctx.lineWidth=1;
    ctx.beginPath(); ctx.roundRect(bx,by,tw,th,4); ctx.fill(); ctx.stroke();
    ctx.fillStyle='#e6edf3'; ctx.textAlign='left';
    ctx.fillText(tip,bx+9,by+16);
    if (val) {
      ctx.font='bold 11px ui-monospace,monospace';
      ctx.fillStyle=BUILD_EP_COLOR[buildHoverN.epistemic]||'#58a6ff';
      ctx.fillText(val,bx+9,by+32);
    }
  }

  // Connect-mode overlay
  if (buildConnFrom) {
    ctx.font = '12px -apple-system,system-ui,sans-serif';
    ctx.fillStyle = 'rgba(248,81,73,.12)'; ctx.fillRect(0,0,cv.width,cv.height);
    ctx.fillStyle = '#f85149'; ctx.textAlign = 'center';
    ctx.fillText('Click target node — or click empty space to cancel', cv.width/2, 24);
  }
}

function buildHit(mx, my) {
  const wx = (mx-buildPan.x)/buildZoom, wy = (my-buildPan.y)/buildZoom;
  for (let i = buildSimN.length-1; i >= 0; i--) {
    const n = buildSimN[i];
    if (n.type === 'claim') {
      const BHW=(n.value?BUILD_CLAIM_W:BUILD_CLAIM_W+20)/2, BHH=(n.value?BUILD_CLAIM_H:BUILD_CLAIM_H+10)/2;
      if (wx>=n.x-BHW&&wx<=n.x+BHW&&wy>=n.y-BHH&&wy<=n.y+BHH) return n;
    } else {
      if ((wx-n.x)**2+(wy-n.y)**2<(n.r+4)**2) return n;
    }
  }
  return null;
}

function buildFit() {
  if (!buildSimN.length) return;
  const cv = document.getElementById('build-canvas');
  const W = cv.width, H = cv.height, PAD = 50;
  let x0=Infinity,y0=Infinity,x1=-Infinity,y1=-Infinity;
  buildSimN.forEach(n => {
    const hw = n.type==='claim'?BUILD_CLAIM_W/2:n.r;
    const hh = n.type==='claim'?BUILD_CLAIM_H/2:n.r;
    x0=Math.min(x0,n.x-hw); y0=Math.min(y0,n.y-hh);
    x1=Math.max(x1,n.x+hw); y1=Math.max(y1,n.y+hh);
  });
  const z = Math.min((W-PAD*2)/(x1-x0||1),(H-PAD*2)/(y1-y0||1),2.5);
  buildZoom = z;
  buildPan.x = W/2 - ((x0+x1)/2)*z;
  buildPan.y = H/2 - ((y0+y1)/2)*z;
  buildDraw();
}

function buildRunGraph() { buildRunLayout(); }

function buildExport() {
  const out = {
    nodes: buildG.nodes.map(n => {
      const { id, type, label, metric, value, unit, period, as_of, perimeter,
              epistemic, direction, topic, source_doc, author, statement, derivation } = n;
      return { id, type, label, metric, value, unit, period, as_of, perimeter,
               epistemic, direction, topic, source_doc, author, statement, derivation };
    }),
    edges: buildG.edges,
  };
  const blob = new Blob([JSON.stringify(out, null, 2)], {type:'application/json'});
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a'); a.href = url; a.download = 'claim-graph.json';
  a.click(); URL.revokeObjectURL(url);
}

function buildClear() {
  buildG = { nodes: [], edges: [] };
  buildSimN = []; buildSimE = []; buildSelN = null; buildConnFrom = null;
  if (buildAnim) { cancelAnimationFrame(buildAnim); buildAnim = null; }
  buildUpdateNodeList(); buildUpdateSelects(); buildDraw();
}

async function buildExtract() {
  const text = document.getElementById('b-text').value.trim();
  if (!text) return;
  const key = document.getElementById('api-key').value.trim();
  const btn = document.querySelector('[onclick="buildExtract()"]');
  btn.disabled = true; btn.textContent = 'Extracting…';
  buildStatus('Running extractor…');
  try {
    const res = await fetch('/extract', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ text, deal: 'playground', api_key: key })
    });
    const data = await res.json();
    if (data.error) throw new Error(data.error);
    const claims = data.claims || [];
    claims.forEach((c, i) => buildAddClaim(c, 'c:x' + Date.now() + '_' + i));
    buildRefreshSim();
    buildStatus(claims.length + ' claim(s) extracted');
  } catch(e) {
    buildStatus('Error: ' + e.message.slice(0, 60));
  }
  btn.disabled = false; btn.textContent = 'Extract →';
}

function buildAddClaim(c, idOverride) {
  const id = idOverride || ('c:' + Date.now());
  const area_rules = [
    ['ebitda','Earnings'],['earnings','Earnings'],['margin','Earnings'],['adjustment','Earnings'],
    ['revenue','Revenue'],['recurring','Revenue'],['growth','Revenue'],
    ['customer','Customer'],['concentration','Customer'],['churn','Customer'],['retention','Customer'],
    ['market','Market'],['position','Market'],['regulatory','Market'],
    ['operations','Operations'],['integration','Operations'],['wip','Operations'],['utilization','Operations'],
    ['debt','Structure'],['leverage','Structure'],['covenant','Structure'],
    ['governance','Governance'],['management','Governance'],['board','Governance'],
    ['exit','Returns'],['moic','Returns'],['irr','Returns'],['multiple','Returns'],
  ];
  function topicToArea(t) {
    const tl = (t||'').toLowerCase();
    for (const [kw,a] of area_rules) { if (tl.includes(kw)) return a; }
    return 'Other';
  }
  const node = {
    id, type: 'claim',
    label: c.metric || c.subject || 'claim',
    metric: c.metric || '',
    value: c.value || '', unit: c.unit || '',
    period: c.period || '', as_of: c.as_of || '',
    perimeter: c.perimeter || '',
    epistemic: c.epistemic || 'asserted',
    direction: c.direction || 'context',
    topic: c.topic || '',
    area: topicToArea(c.topic),
    source_doc: c.source_doc || '',
    author: c.author || '',
    statement: c.statement || '',
    derivation: c.derivation || null,
    subject: c.subject || '',
  };
  buildG.nodes.push(node);
  // Auto-create subject node and HAS_CLAIM edge
  const subj = (c.subject || '').trim();
  if (subj) {
    let sNode = buildG.nodes.find(n => n.type === 'subject' && n.label === subj);
    if (!sNode) {
      sNode = { id: 'subj:' + subj, type: 'subject', label: subj };
      buildG.nodes.push(sNode);
    }
    buildG.edges.push({ source: sNode.id, target: id, rel: 'HAS_CLAIM' });
  }
  return node;
}

function buildAddManual() {
  const subj   = document.getElementById('bm-subj').value.trim();
  const metric = document.getElementById('bm-metric').value.trim();
  const value  = document.getElementById('bm-value').value.trim();
  const unit   = document.getElementById('bm-unit').value.trim();
  const period = document.getElementById('bm-period').value.trim();
  const ep     = document.getElementById('bm-ep').value;
  const topic  = document.getElementById('bm-topic').value;
  const src    = document.getElementById('bm-src').value.trim();
  const stmt   = document.getElementById('bm-stmt').value.trim();
  if (!subj || !metric) { buildStatus('Subject and Metric are required'); return; }
  buildAddClaim({ subject:subj, metric, value, unit, period, epistemic:ep, topic, source_doc:src, statement:stmt });
  buildRefreshSim();
  buildStatus('Node added: ' + metric);
}

function buildAddEdge() {
  const from = document.getElementById('be-from').value;
  const to   = document.getElementById('be-to').value;
  const rel  = document.getElementById('be-rel').value;
  if (!from || !to || from === to) { buildStatus('Select two different nodes'); return; }
  buildG.edges.push({ source: from, target: to, rel });
  buildRefreshSim();
  buildStatus('Edge added: ' + rel);
}

function buildDeleteNode(id) {
  buildG.nodes = buildG.nodes.filter(n => n.id !== id);
  buildG.edges = buildG.edges.filter(e => e.source !== id && e.target !== id);
  if (buildSelN && buildSelN.id === id) buildSelN = null;
  buildRefreshSim();
}

function buildUpdateNodeList() {
  const list = document.getElementById('build-node-list');
  const count = document.getElementById('build-n-count');
  const claims = buildG.nodes.filter(n => n.type === 'claim' || n.type === 'subject');
  count.textContent = claims.length;
  list.innerHTML = claims.map(n => {
    const col = BUILD_EP_COLOR[n.epistemic] || (n.type==='subject'?'#58a6ff':'#6e7681');
    const label = n.type === 'subject'
      ? `<div class="bni-metric">${esc(n.label)}</div><div class="bni-sub">subject</div>`
      : `<div class="bni-metric">${esc(n.metric||n.label)}</div>
         <div class="bni-sub">${esc(n.value?n.value+(n.unit?' '+n.unit:''):'')}&nbsp;${esc(n.period||n.as_of||'')} ${esc(n.epistemic||'')}</div>`;
    return `<div class="build-node-item" onclick="buildSelectNode('${n.id}')">
      <div class="bni-bar" style="background:${col}"></div>
      <div class="bni-info">${label}</div>
      <div class="bni-del" onclick="event.stopPropagation();buildDeleteNode('${n.id}')">✕</div>
    </div>`;
  }).join('');
}

function buildSelectNode(id) {
  buildSelN = buildSimN.find(n => n.id === id) || null;
  buildDraw();
}

function buildUpdateSelects() {
  ['be-from','be-to'].forEach(sid => {
    const sel = document.getElementById(sid);
    const cur = sel.value;
    sel.innerHTML = buildG.nodes.map(n =>
      `<option value="${n.id}">${esc((n.metric||n.label||n.id).slice(0,22))} [${n.type.slice(0,3)}]</option>`
    ).join('');
    if (buildG.nodes.find(n => n.id === cur)) sel.value = cur;
  });
}

// ── Chat with Claude ─────────────────────────────────────────────────────────

let chatHistory = [];  // [{role:'user'|'claude', text:'', applied:0}]

function chatToggle() {
  document.getElementById('build-chat').classList.toggle('open');
}

function chatRender() {
  const el = document.getElementById('chat-history');
  el.innerHTML = chatHistory.map(m => {
    if (m.role === 'user') {
      return `<div class="chat-msg chat-msg-user">${esc(m.text)}</div>`;
    }
    if (m.role === 'thinking') {
      return `<div class="chat-msg chat-msg-claude chat-msg-thinking">${esc(m.text)}</div>`;
    }
    const badge = m.applied > 0
      ? `<div class="chat-msg-badge">&#x2713; ${m.applied} change${m.applied>1?'s':''} applied to graph</div>`
      : '';
    return `<div class="chat-msg chat-msg-claude">${esc(m.text)}${badge}</div>`;
  }).join('');
  el.scrollTop = el.scrollHeight;
}

async function chatSend() {
  const ta  = document.getElementById('chat-ta');
  const btn = document.getElementById('chat-send-btn');
  const msg = ta.value.trim();
  if (!msg) return;

  ta.value = '';
  chatHistory.push({role: 'user', text: msg});
  chatHistory.push({role: 'thinking', text: 'Thinking…'});
  chatRender();

  // Open the chat panel if collapsed
  document.getElementById('build-chat').classList.add('open');

  const key = document.getElementById('api-key').value.trim();
  btn.disabled = true;

  // Compact graph for context
  const graphCtx = {
    nodes: buildG.nodes.map(n => ({
      id: n.id, type: n.type,
      metric: n.metric||n.label||'',
      value: n.value||'',
      epistemic: n.epistemic||'',
      subject: n.subject||'',
      direction: n.direction||''
    })),
    edges: buildG.edges.map(e => ({source: e.source, target: e.target, rel: e.rel}))
  };

  try {
    const res = await fetch('/chat', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({message: msg, graph: graphCtx, api_key: key})
    });
    const data = await res.json();
    const applied = buildApplyCommands(data.commands || []);
    // Remove the thinking placeholder
    chatHistory = chatHistory.filter(m => m.role !== 'thinking');
    chatHistory.push({
      role: 'claude',
      text: data.message || data.reply || '(no response)',
      applied
    });
  } catch(e) {
    chatHistory = chatHistory.filter(m => m.role !== 'thinking');
    chatHistory.push({role: 'claude', text: 'Network error: ' + e.message, applied: 0});
  }

  btn.disabled = false;
  chatRender();
}

function buildApplyCommands(commands) {
  if (!commands || !commands.length) return 0;
  let count = 0;

  function findNode(ref) {
    if (!ref) return null;
    const r = ref.toLowerCase();
    return buildG.nodes.find(n =>
      n.id === ref ||
      (n.metric && n.metric.toLowerCase() === r) ||
      (n.label  && n.label.toLowerCase()  === r)
    );
  }

  for (const cmd of commands) {
    try {
      if (cmd.action === 'add_node') {
        buildAddClaim({
          subject:    cmd.subject    || '',
          metric:     cmd.metric     || cmd.label || '',
          value:      cmd.value      || '',
          unit:       cmd.unit       || '',
          epistemic:  cmd.epistemic  || 'asserted',
          direction:  cmd.direction  || 'context',
          period:     cmd.period     || '',
          topic:      cmd.topic      || '',
          statement:  cmd.statement  || '',
          source_doc: cmd.source_doc || 'Chat',
        }, 'c:chat:' + Date.now() + '_' + count);
        count++;
      } else if (cmd.action === 'add_edge') {
        const src = findNode(cmd.source);
        const tgt = findNode(cmd.target);
        if (src && tgt && src.id !== tgt.id) {
          buildG.edges.push({source: src.id, target: tgt.id, rel: cmd.rel || 'SUPPORTS'});
          count++;
        }
      } else if (cmd.action === 'remove_edge') {
        const src = findNode(cmd.source);
        const tgt = findNode(cmd.target);
        if (src && tgt) {
          const before = buildG.edges.length;
          buildG.edges = buildG.edges.filter(e =>
            !(e.source === src.id && e.target === tgt.id && e.rel === cmd.rel)
          );
          count += before - buildG.edges.length;
        }
      } else if (cmd.action === 'update_node') {
        const n = findNode(cmd.find);
        if (n && cmd.updates) {
          // Update both buildG.nodes entry and simNode
          Object.assign(n, cmd.updates);
          const sn = buildSimN.find(s => s.id === n.id);
          if (sn) Object.assign(sn, cmd.updates);
          count++;
        }
      } else if (cmd.action === 'remove_node') {
        const n = findNode(cmd.find);
        if (n) {
          buildG.nodes = buildG.nodes.filter(x => x.id !== n.id);
          buildG.edges = buildG.edges.filter(e => e.source !== n.id && e.target !== n.id);
          count++;
        }
      }
    } catch(e) { console.warn('Command error:', e, cmd); }
  }

  if (count > 0) buildRefreshSim();
  return count;
}

</script>
</body>
</html>
"""


# ── HTTP handler ─────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # suppress default access log
        pass

    def _send(self, code: int, ctype: str, body: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            key_placeholder = "set via env  ✓" if API_KEY else "sk-ant-…  paste your key here"
            page = (HTML
                    .replace("MODEL_PLACEHOLDER", MODEL)
                    .replace("KEY_PLACEHOLDER", key_placeholder))
            self._send(200, "text/html; charset=utf-8", page.encode())
        elif self.path == "/analytics":
            if _last_dg is None:
                resp = json.dumps({"ready": False, "stats": {},
                                   "top_pagerank": [], "top_betweenness": [],
                                   "contradictions": [], "graph": {"nodes": [], "edges": []}})
            else:
                try:
                    pr   = _last_dg.pagerank()
                    btwn = _last_dg.betweenness()
                    top_pr = sorted(
                        [{"id": nid, "score": round(s, 5), **dict(_last_dg.G.nodes[nid])}
                         for nid, s in pr.items()],
                        key=lambda x: -x["score"])[:12]
                    top_btwn = sorted(
                        [{"id": nid, "score": round(s, 5), **dict(_last_dg.G.nodes[nid])}
                         for nid, s in btwn.items()],
                        key=lambda x: -x["score"])[:8]
                    resp = json.dumps({
                        "ready": True,
                        "stats": _last_dg.stats(),
                        "top_pagerank":    top_pr,
                        "top_betweenness": top_btwn,
                        "contradictions":  _last_dg.contradictions(),
                        "graph":           _last_dg.to_vis_json(),
                    })
                except Exception:
                    resp = json.dumps({"ready": False, "error": traceback.format_exc()[-400:]})
            self._send(200, "application/json; charset=utf-8", resp.encode())
        else:
            self._send(404, "text/plain", b"not found")

    def do_POST(self):
        if self.path == "/parse-pdf":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            try:
                payload = json.loads(body)
                pdf_bytes = base64.b64decode(payload.get("data", ""))
                text = _pdf_to_text(pdf_bytes)
                resp = json.dumps({"text": text, "chars": len(text)})
            except Exception as e:
                resp = json.dumps({"error": str(e)})
            self._send(200, "application/json; charset=utf-8", resp.encode())
            return

        if self.path == "/chat":
            length = int(self.headers.get("Content-Length", 0))
            body   = self.rfile.read(length)
            try:
                payload = json.loads(body)
            except Exception:
                self._send(400, "application/json", json.dumps({"error": "bad JSON"}).encode())
                return
            message  = (payload.get("message") or "").strip()
            graph_in = payload.get("graph", {"nodes": [], "edges": []})
            req_key  = (payload.get("api_key") or "").strip()
            key      = req_key or API_KEY
            if not key:
                self._send(400, "application/json",
                           json.dumps({"error": "No API key"}).encode()); return
            if not message:
                self._send(400, "application/json",
                           json.dumps({"error": "empty message"}).encode()); return
            nodes_ctx = [
                {"id": n.get("id",""), "type": n.get("type",""),
                 "metric": n.get("metric",""), "label": n.get("label",""),
                 "value": n.get("value",""), "epistemic": n.get("epistemic",""),
                 "subject": n.get("subject","")}
                for n in graph_in.get("nodes", [])
            ]
            edges_ctx = [
                {"source": e.get("source",""), "target": e.get("target",""),
                 "rel": e.get("rel","")}
                for e in graph_in.get("edges", [])
            ]
            graph_ctx = (
                "CURRENT GRAPH:\n"
                + json.dumps({"nodes": nodes_ctx, "edges": edges_ctx}, separators=(",",":"))
            )
            user_msg = f"{graph_ctx}\n\nUSER REQUEST: {message}"
            try:
                raw = _call_api(CHAT_SYSTEM, user_msg, key)
                raw = raw.strip()
                if raw.startswith("```"):
                    raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0]
                result = json.loads(raw)
            except json.JSONDecodeError:
                import re as _re
                m = _re.search(r'\{.*\}', raw, _re.DOTALL)
                result = json.loads(m.group()) if m else {"message": raw, "commands": []}
            except Exception:
                err = traceback.format_exc()
                print(err, file=sys.stderr)
                result = {"message": f"Error: {err[-200:]}", "commands": []}
            self._send(200, "application/json; charset=utf-8",
                       json.dumps(result).encode())
            return

        if self.path != "/extract":
            self._send(404, "text/plain", b"not found")
            return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            payload = json.loads(body)
        except Exception:
            self._send(400, "application/json",
                       json.dumps({"error": "bad JSON"}).encode())
            return

        text    = (payload.get("text")    or "").strip()
        deal    = (payload.get("deal")    or "test").strip()
        req_key = (payload.get("api_key") or "").strip()
        key     = req_key or API_KEY

        if not text:
            self._send(400, "application/json",
                       json.dumps({"error": "empty text"}).encode())
            return

        if not key:
            self._send(400, "application/json",
                       json.dumps({"error": "No API key — paste your Anthropic key in the key field"}).encode())
            return

        deal_context = (
            f"Deal: {deal}. Extract all factual claims relevant to investment analysis. "
            "Apply epistemic typing carefully:\n"
            "  asserted  = seller or management claim, no external verification\n"
            "  observed  = directly measured / recorded by a third party\n"
            "  attested  = qualified third party formally certifies (QoE firm, IC, Firm underwriting)\n"
            "  derived   = you computed it from other stated values (include derivation)\n"
            "Include period and perimeter on every claim."
        )
        user_msg = f"DEAL CONTEXT:\n{deal_context}\n\nARTIFACT:\n{text[:80_000]}"

        try:
            global _last_dg
            t0 = time.time()
            raw = _call_api(SYSTEM_PROMPT, user_msg, key)
            claims = parse_json(raw)
            graph  = claims_to_graph(claims)
            elapsed = round(time.time() - t0, 2)
            # Build and persist decomposed property graph
            try:
                _last_dg = build_from_extraction(claims, graph, deal)
                _last_dg.save(graph_path(deal))
                gs = _last_dg.stats()
                print(f"  → {len(claims)} claims  {graph['stats']}  graph={gs['nodes']}n/{gs['edges']}e  ({elapsed}s)  deal={deal}")
            except Exception as gs_err:
                _last_dg = None
                print(f"  [graph_store] {gs_err}", file=sys.stderr)
                print(f"  → {len(claims)} claims  {graph['stats']}  ({elapsed}s)  deal={deal}")
            resp = json.dumps({"claims": claims, "graph": graph, "elapsed": elapsed})
        except Exception:
            err = traceback.format_exc()
            print(err, file=sys.stderr)
            resp = json.dumps({"error": err[-300:]})

        self._send(200, "application/json; charset=utf-8", resp.encode())


# ── Entry point ──────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(description="PE OS extraction test UI")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    url = f"http://localhost:{args.port}"
    server = HTTPServer(("localhost", args.port), Handler)
    print(f"PE OS Extraction Workbench")
    print(f"  {url}")
    print(f"  model : {MODEL}")
    print(f"  Ctrl+C to stop\n")

    if not args.no_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
