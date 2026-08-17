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
from tools.claim_graph import claims_to_graph

API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL   = os.environ.get("PEOS_MODEL", "claude-sonnet-5")


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
    import json as _json
    import urllib.request
    payload = {
        "model": MODEL, "max_tokens": 16000,
        "thinking": {"type": "adaptive"}, "output_config": {"effort": "low"},
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=_json.dumps(payload).encode(), method="POST",
        headers={"Content-Type": "application/json", "x-api-key": key,
                 "anthropic-version": "2023-06-01"})
    with urllib.request.urlopen(req, timeout=300) as resp:
        blocks = _json.loads(resp.read())["content"]
        text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        if not text:
            raise ValueError(f"no text block in response: {str(blocks)[:200]}")
        return text

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

  .results-wrap { flex: 1; overflow-y: auto; padding: 12px 16px; display: flex; flex-direction: column; gap: 10px; }

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

  /* ── Claim card ── */
  .claim {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius); overflow: hidden;
    animation: slide-in .18s ease both;
  }
  @keyframes slide-in {
    from { opacity: 0; transform: translateY(5px); }
    to   { opacity: 1; transform: translateY(0); }
  }

  /* Row 1: badge + metric + value */
  .claim-head {
    display: flex; align-items: center; gap: 10px;
    padding: 11px 14px 0; cursor: pointer; user-select: none;
  }
  .claim-num { font-family: var(--mono); font-size: 11px; color: var(--muted); min-width: 26px; }

  .ep-badge {
    font-size: 10px; font-weight: 700; padding: 3px 8px; border-radius: 4px;
    text-transform: uppercase; letter-spacing: .05em; flex-shrink: 0;
  }
  .ep-asserted { color: var(--ep-asserted); background: rgba(227,179,65,.15); }
  .ep-attested { color: var(--ep-attested); background: rgba(63,185,80,.15); }
  .ep-observed { color: var(--ep-observed); background: rgba(88,166,255,.15); }
  .ep-derived  { color: var(--ep-derived);  background: rgba(210,153,34,.15); }
  .ep-unknown  { color: var(--ep-unknown);  background: rgba(110,118,129,.12); }

  .claim-metric { font-size: 14px; font-weight: 600; flex: 1; line-height: 1.3; }
  .claim-value  {
    font-family: var(--mono); font-size: 15px; font-weight: 700;
    color: var(--accent); white-space: nowrap; flex-shrink: 0;
  }
  .chevron { font-size: 11px; color: var(--muted); transition: transform .15s; flex-shrink: 0; }
  .claim.open .chevron { transform: rotate(90deg); }

  /* Row 2: context line — always visible */
  .claim-context {
    padding: 4px 14px 10px 14px; font-size: 12px; color: var(--muted);
    border-bottom: 1px solid var(--border); cursor: pointer;
    display: flex; align-items: baseline; gap: 0; flex-wrap: wrap;
  }
  .ctx-topic  { color: var(--accent); font-weight: 500; margin-right: 6px; }
  .ctx-sep    { color: var(--border); margin: 0 5px; }
  .ctx-plain  { color: var(--muted); }

  /* Expanded body */
  .claim-body { display: none; border-top: 1px solid var(--border); }
  .claim.open .claim-body { display: block; }

  .claim-grid {
    display: grid; grid-template-columns: 110px 1fr; gap: 0;
    font-size: 12.5px; padding: 10px 14px;
  }
  .cg-row { display: contents; }
  .cg-key {
    color: var(--muted); font-family: var(--mono); font-size: 11px;
    padding: 4px 10px 4px 0; align-self: start; white-space: nowrap;
  }
  .cg-val { color: var(--text); font-family: var(--mono); font-size: 12px;
    word-break: break-word; line-height: 1.5; padding: 4px 0; }
  .cg-val.dim { color: var(--muted); font-style: italic; }

  .claim-stmt {
    margin: 0 14px 12px; padding: 10px 12px;
    background: var(--surface2); border-radius: var(--radius);
    font-size: 12.5px; color: var(--text); line-height: 1.7;
    border-left: 3px solid var(--accent-d); font-style: italic;
  }
  .claim-stmt.dim { color: var(--muted); font-style: normal; }

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
    width: 10px; height: 10px; border-radius: 50%;
  }

  /* ── Scrollbar ── */
  ::-webkit-scrollbar { width: 6px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
  ::-webkit-scrollbar-thumb:hover { background: var(--muted); }

  @media (max-width: 768px) {
    .panels { grid-template-columns: 1fr; grid-template-rows: auto 1fr; }
    .left { border-right: none; border-bottom: 1px solid var(--border); max-height: 45vh; }
    .doc-area textarea { min-height: 120px; }
  }
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
          <button class="tab active" id="tab-cards" onclick="switchTab('cards')">Cards</button>
          <button class="tab" id="tab-raw"   onclick="switchTab('raw')">JSON</button>
          <button class="tab" id="tab-graph" onclick="switchTab('graph')">Graph</button>
        </div>
      </div>

      <div class="error-banner" id="error-banner"></div>

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
          </div>
          <div class="graph-legend">
            <span class="leg-item"><span class="leg-dot" style="background:#58a6ff;border:2px solid #58a6ff"></span>Subject</span>
            <span class="leg-item"><span class="leg-dot" style="background:rgba(63,185,80,.2);border:2px solid #3fb950"></span>Attested</span>
            <span class="leg-item"><span class="leg-dot" style="background:rgba(227,179,65,.2);border:2px solid #e3b341"></span>Asserted</span>
            <span class="leg-item"><span class="leg-dot" style="background:rgba(88,166,255,.2);border:2px solid #58a6ff"></span>Observed</span>
            <span class="leg-item"><span class="leg-dot" style="background:rgba(188,140,255,.2);border:2px solid #bc8cff"></span>Question</span>
          </div>
        </div>
        <div class="graph-detail" id="graph-detail">
          <div style="color:var(--muted);font-size:12px;padding-top:20px;text-align:center">Click a node<br>to see details</div>
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

// ── Graph sim state ──────────────────────────────────────────────────────────
let simNodes = [], simEdges = [];
let animId = null, selectedNode = null, draggingNode = null;
let pan = {x:0, y:0}, zoomLevel = 1;
let isPanning = false, lastMouse = null;

function switchTab(tab) {
  currentTab = tab;
  ['cards','raw','graph'].forEach(t => {
    document.getElementById('tab-' + t).classList.toggle('active', t === tab);
  });
  document.getElementById('results-wrap').style.display = tab === 'cards' ? 'flex'  : 'none';
  document.getElementById('raw-view').style.display    = tab === 'raw'   ? 'flex'  : 'none';
  document.getElementById('graph-view').style.display  = tab === 'graph' ? 'flex'  : 'none';
  // Defer one frame so the browser lays out the now-visible canvas container
  // before we read clientWidth/clientHeight (would be 0 if read immediately).
  if (tab === 'graph' && lastGraph) requestAnimationFrame(() => initGraph(lastGraph));
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

function renderCard(item, idx) {
  const ep     = item.epistemic || 'unknown';
  const metric = esc(item.metric || item.subject || '—');
  const value  = item.value
    ? esc(item.value) + (item.unit ? ' ' + esc(item.unit) : '')
    : '';
  const stmt   = esc(item.statement || '');
  const hasStmt = !!(item.statement || '').trim();
  const bears  = Array.isArray(item.bears_on)
    ? item.bears_on.join(', ') : (item.bears_on || '');

  // Context line: topic · as_of · source_doc · author (readable, 12px)
  const ctxParts = [
    item.topic     ? `<span class="ctx-topic">${esc(item.topic)}</span>` : '',
    item.as_of     ? `<span class="ctx-plain">${esc(item.as_of)}</span>` : '',
    item.source_doc? `<span class="ctx-plain">${esc(item.source_doc)}</span>` : '',
    item.author    ? `<span class="ctx-plain">${esc(item.author)}</span>` : '',
  ].filter(Boolean).join('<span class="ctx-sep">·</span>');

  const rows = [
    ['subject',    item.subject],
    ['value',      item.value ? item.value + (item.unit ? ' ' + item.unit : '') : ''],
    ['period',     item.period],
    ['as_of',      item.as_of],
    ['perimeter',  item.perimeter],
    ['source_doc', item.source_doc],
    ['locator',    item.locator],
    ['author',     item.author],
    ['direction',  item.direction],
    ['bears-on',   bears],
  ].filter(([,v]) => v);
  if (item.derivation) rows.push(['derivation', item.derivation]);

  const gridHtml = rows.map(([k,v]) =>
    `<span class="cg-key">${k}</span><span class="cg-val">${esc(v)}</span>`
  ).join('');

  return `
<div class="claim" id="claim-${idx}">
  <div class="claim-head" onclick="toggleClaim(${idx})">
    <span class="claim-num">${String(idx).padStart(2,'0')}</span>
    <span class="ep-badge ${epClass(ep)}">${ep}</span>
    <span class="claim-metric">${metric}</span>
    ${value ? `<span class="claim-value">${value}</span>` : ''}
    <span class="chevron">▶</span>
  </div>
  <div class="claim-context" onclick="toggleClaim(${idx})">${ctxParts || '<span class="ctx-plain">—</span>'}</div>
  <div class="claim-body">
    <div class="claim-grid">${gridHtml}</div>
    <div class="claim-stmt ${hasStmt ? '' : 'dim'}">${hasStmt ? stmt : 'no statement extracted'}</div>
  </div>
</div>`;
}

function toggleClaim(idx) {
  const el = document.getElementById('claim-' + idx);
  el.classList.toggle('open');
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
  document.getElementById('graph-detail').style.display = 'none';
  const cv = document.getElementById('graph-canvas');
  const ctx = cv.getContext('2d');
  ctx.clearRect(0, 0, cv.width, cv.height);
  if (animId) { cancelAnimationFrame(animId); animId = null; }
  lastClaims = []; lastGraph = null; simNodes = []; simEdges = [];
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

  // Render cards with stagger
  wrap.innerHTML = '';
  claims.forEach((item, i) => {
    setTimeout(() => {
      wrap.insertAdjacentHTML('beforeend', renderCard(item, i + 1));
    }, i * 40);
  });

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

  if (lastGraph && currentTab === 'graph') initGraph(lastGraph);

  btn.disabled = false; btn.textContent = 'Extract claims';
  dot.classList.remove('pulsing');
}

// ── Force-directed graph ─────────────────────────────────────────────────────

const EP_COLOR = {
  asserted: '#e3b341', attested: '#3fb950',
  observed: '#58a6ff', derived:  '#d29922',
};
let _graphDraw = null;  // exposed so fitView/resetView can call it

function nodeColor(n) {
  if (n.type === 'subject')  return '#58a6ff';
  if (n.type === 'question') return '#bc8cff';
  return EP_COLOR[n.epistemic] || '#6e7681';
}

function edgeColor(rel) {
  if (rel === 'CONTRADICTS') return '#f85149';
  if (rel === 'BEARS_ON')    return '#6e7681';
  return '#30363d';
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

  const cv = document.getElementById('graph-canvas');
  // Size canvas to its CSS layout box
  cv.width  = cv.parentElement.clientWidth;
  cv.height = cv.parentElement.clientHeight;
  const W = cv.width, H = cv.height;

  // Assign radii and initial positions:
  // subjects spread in a ring, claims near their subject, questions on periphery.
  const nodeById = {};
  const subjects = graph.nodes.filter(n => n.type === 'subject');
  const subjIdx  = Object.fromEntries(subjects.map((n,i) => [n.id, i]));
  const SR = Math.min(W, H) * 0.28;  // subject ring radius

  simNodes = graph.nodes.map(n => {
    let x, y;
    if (n.type === 'subject') {
      const angle = (subjIdx[n.id] / Math.max(subjects.length, 1)) * Math.PI * 2;
      x = W/2 + Math.cos(angle) * SR;
      y = H/2 + Math.sin(angle) * SR;
    } else {
      // Find parent subject via HAS_CLAIM or place randomly
      const parentEdge = graph.edges.find(e => e.rel === 'HAS_CLAIM' && e.target === n.id);
      if (parentEdge && subjIdx[parentEdge.source] !== undefined) {
        const angle = (subjIdx[parentEdge.source] / Math.max(subjects.length, 1)) * Math.PI * 2;
        const r = SR * (n.type === 'question' ? 1.6 : 0.5);
        x = W/2 + Math.cos(angle) * r + (Math.random()-.5)*40;
        y = H/2 + Math.sin(angle) * r + (Math.random()-.5)*40;
      } else {
        x = W/2 + (Math.random()-.5)*W*.4;
        y = H/2 + (Math.random()-.5)*H*.4;
      }
    }
    const sn = { ...n, x, y, vx: 0, vy: 0,
                  r: n.type === 'subject' ? 13 : n.type === 'question' ? 7 : 9 };
    nodeById[n.id] = sn;
    return sn;
  });

  simEdges = graph.edges
    .map(e => ({...e, source: nodeById[e.source], target: nodeById[e.target]}))
    .filter(e => e.source && e.target);

  let hoverNode = null;

  // Single unified mousemove: drag node OR pan OR track hover
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
  cv.onmouseup = cv.onmouseleave = () => {
    draggingNode = null; isPanning = false; lastMouse = null;
  };
  cv.onwheel = e => {
    e.preventDefault();
    const f = e.deltaY < 0 ? 1.1 : 0.91;
    const newZ = Math.max(.1, Math.min(6, zoomLevel * f));
    pan.x = e.offsetX - (e.offsetX - pan.x) * newZ / zoomLevel;
    pan.y = e.offsetY - (e.offsetY - pan.y) * newZ / zoomLevel;
    zoomLevel = newZ;
    if (!animId) draw();
  };

  let alpha = 1;

  function tick() {
    const SPRING = 0.04, REST_SC = 90, REST_CQ = 110;
    const REP    = 2200;
    const GRAV   = 0.018;
    const DAMP   = 0.82;

    simNodes.forEach(n => { n.fx = 0; n.fy = 0; });

    // Repulsion (O(n²) — fine for <300 nodes)
    for (let i = 0; i < simNodes.length; i++) {
      for (let j = i+1; j < simNodes.length; j++) {
        const a = simNodes[i], b = simNodes[j];
        let dx = b.x-a.x, dy = b.y-a.y;
        const d2 = dx*dx+dy*dy || 1;
        const d  = Math.sqrt(d2);
        const f  = REP / d2;
        a.fx -= f*dx/d; a.fy -= f*dy/d;
        b.fx += f*dx/d; b.fy += f*dy/d;
      }
    }

    // Spring per edge
    simEdges.forEach(e => {
      const dx = e.target.x-e.source.x, dy = e.target.y-e.source.y;
      const d  = Math.sqrt(dx*dx+dy*dy) || 1;
      const rest = e.rel === 'BEARS_ON' ? REST_CQ : REST_SC;
      const f  = SPRING * (d - rest);
      const fx = f*dx/d, fy = f*dy/d;
      e.source.fx += fx; e.source.fy += fy;
      e.target.fx -= fx; e.target.fy -= fy;
    });

    // Gravity toward canvas center
    simNodes.forEach(n => {
      n.fx += (W/2 - n.x) * GRAV;
      n.fy += (H/2 - n.y) * GRAV;
    });

    // Integrate
    simNodes.forEach(n => {
      if (n === draggingNode) return;
      n.vx = (n.vx + n.fx) * DAMP * alpha;
      n.vy = (n.vy + n.fy) * DAMP * alpha;
      n.x += n.vx; n.y += n.vy;
    });

    alpha = Math.max(0, alpha - 0.004);
    draw();
    if (alpha > 0.001) animId = requestAnimationFrame(tick);
    else animId = null;
  }

  function draw() {
    const ctx = cv.getContext('2d');
    const cW = cv.width, cH = cv.height;
    ctx.clearRect(0, 0, cW, cH);
    ctx.save();
    ctx.translate(pan.x, pan.y);
    ctx.scale(zoomLevel, zoomLevel);

    // Edges
    simEdges.forEach(e => {
      if (!e.source || !e.target) return;
      ctx.beginPath();
      ctx.moveTo(e.source.x, e.source.y);
      ctx.lineTo(e.target.x, e.target.y);
      ctx.strokeStyle = edgeColor(e.rel);
      ctx.lineWidth   = e.rel === 'CONTRADICTS' ? 2 : 1;
      ctx.globalAlpha = e.rel === 'CONTRADICTS' ? .85 : .38;
      ctx.stroke();
    });
    ctx.globalAlpha = 1;

    // Nodes
    simNodes.forEach(n => {
      const col = nodeColor(n);
      const sel = n === selectedNode;
      ctx.beginPath();
      ctx.arc(n.x, n.y, n.r, 0, Math.PI*2);
      ctx.fillStyle = col + (n.type === 'subject' ? '30' : '20');
      ctx.fill();
      if (sel) { ctx.shadowColor = col; ctx.shadowBlur = 18; }
      ctx.strokeStyle = col;
      ctx.lineWidth = sel ? 2.5 : n.type === 'subject' ? 2 : 1.5;
      ctx.stroke();
      ctx.shadowBlur = 0;

      // Labels
      ctx.textAlign = 'center';
      if (n.type === 'subject') {
        const words = n.label.split(' ');
        let line = '', lines = [];
        words.forEach(w => {
          const t = line ? line+' '+w : w;
          if (t.length > 18 && line) { lines.push(line); line = w; }
          else line = t;
        });
        if (line) lines.push(line);
        lines = lines.slice(0,3);
        ctx.font      = 'bold 12px -apple-system,system-ui,sans-serif';
        ctx.fillStyle = '#c9d1d9';
        lines.forEach((l,i) => ctx.fillText(l, n.x, n.y + n.r + 14 + i*14));
      } else if (sel) {
        const lbl = (n.metric || n.label || '').slice(0, 26);
        const vl  = n.value ? n.value + (n.unit ? ' '+n.unit : '') : '';
        ctx.font      = '11px -apple-system,system-ui,sans-serif';
        ctx.fillStyle = '#e6edf3';
        ctx.fillText(lbl, n.x, n.y + n.r + 14);
        if (vl) {
          ctx.font = 'bold 11px ui-monospace,monospace';
          ctx.fillStyle = col;
          ctx.fillText(vl, n.x, n.y + n.r + 27);
        }
      }
    });
    ctx.restore();

    // Hover tooltip — screen-space, outside transform
    if (hoverNode && hoverNode !== selectedNode) {
      const tx = hoverNode.x * zoomLevel + pan.x;
      const ty = hoverNode.y * zoomLevel + pan.y;
      const tip = (hoverNode.metric || hoverNode.label || '').slice(0, 36);
      const val = hoverNode.value ? hoverNode.value + (hoverNode.unit ? ' '+hoverNode.unit : '') : '';
      ctx.font = '11px -apple-system,system-ui,sans-serif';
      const tw = Math.max(ctx.measureText(tip).width, ctx.measureText(val).width) + 18;
      const th = val ? 38 : 24;
      const bx = Math.max(4, Math.min(tx - tw/2, cW - tw - 4));
      const by = ty - hoverNode.r * zoomLevel - th - 6;
      ctx.fillStyle = 'rgba(13,17,23,.93)';
      ctx.strokeStyle = '#30363d';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.rect(bx, by, tw, th);
      ctx.fill(); ctx.stroke();
      ctx.fillStyle = '#e6edf3'; ctx.textAlign = 'left';
      ctx.fillText(tip, bx + 8, by + 15);
      if (val) {
        ctx.font = 'bold 11px ui-monospace,monospace';
        ctx.fillStyle = nodeColor(hoverNode);
        ctx.fillText(val, bx + 8, by + 30);
      }
    }
  }
  _graphDraw = draw;  // expose for fitView / resetView

  function hitNode(mx, my) {
    const wx = (mx-pan.x)/zoomLevel, wy = (my-pan.y)/zoomLevel;
    for (let i = simNodes.length-1; i >= 0; i--) {
      const n = simNodes[i];
      const dx = wx-n.x, dy = wy-n.y;
      if (dx*dx+dy*dy < (n.r+6)*(n.r+6)) return n;
    }
    return null;
  }

  // Resize
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

  const typeLabel = {'subject':'Entity','claim':'Claim','question':'Question'}[n.type] || n.type;
  let html = `<div class="gd-type">${typeLabel}</div>`;
  html += `<div class="gd-label">${esc(n.label || n.id)}</div>`;

  if (n.type === 'claim') {
    const rows = [
      ['metric',     n.metric],    ['value',      n.value + (n.unit ? ' ' + n.unit : '')],
      ['topic',      n.topic],     ['as_of',      n.as_of],
      ['period',     n.period],    ['perimeter',  n.perimeter],
      ['source_doc', n.source_doc],['epistemic',  n.epistemic],
      ['direction',  n.direction], ['author',     n.author],
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
    if (n.statement) {
      html += `<div class="gd-stmt">${esc(n.statement)}</div>`;
    }
  }

  det.innerHTML = html;
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
            t0 = time.time()
            raw = _call_api(SYSTEM_PROMPT, user_msg, key)
            claims = parse_json(raw)
            graph  = claims_to_graph(claims)
            elapsed = round(time.time() - t0, 2)
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
