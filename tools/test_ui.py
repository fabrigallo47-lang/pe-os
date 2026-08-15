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
        "model": MODEL, "max_tokens": 10000,
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
    animation: slide-in .22s ease both;
  }
  @keyframes slide-in {
    from { opacity: 0; transform: translateY(6px); }
    to   { opacity: 1; transform: translateY(0); }
  }

  .claim-head {
    display: flex; align-items: center; gap: 8px;
    padding: 9px 12px; border-bottom: 1px solid var(--border);
    cursor: pointer; user-select: none;
  }
  .claim-num { font-family: var(--mono); font-size: 10px; color: var(--muted); width: 22px; }
  .ep-badge {
    font-size: 10px; font-weight: 600; padding: 2px 7px; border-radius: 20px;
    text-transform: uppercase; letter-spacing: .06em; border: 1px solid;
  }
  .ep-asserted { color: var(--ep-asserted); border-color: var(--ep-asserted); background: rgba(227,179,65,.1); }
  .ep-attested { color: var(--ep-attested); border-color: var(--ep-attested); background: rgba(63,185,80,.1); }
  .ep-observed { color: var(--ep-observed); border-color: var(--ep-observed); background: rgba(88,166,255,.1); }
  .ep-derived  { color: var(--ep-derived);  border-color: var(--ep-derived);  background: rgba(210,153,34,.1); }
  .ep-unknown  { color: var(--ep-unknown);  border-color: var(--ep-unknown);  background: rgba(110,118,129,.1); }

  .claim-subject { font-size: 13px; font-weight: 500; flex: 1; }
  .claim-value {
    font-family: var(--mono); font-size: 12px; color: var(--accent);
    background: rgba(88,166,255,.08); padding: 2px 7px; border-radius: 4px;
    max-width: 140px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  }
  .chevron { font-size: 10px; color: var(--muted); transition: transform .15s; }
  .claim.open .chevron { transform: rotate(90deg); }

  .claim-body { padding: 10px 12px; display: none; border-top: 1px solid var(--border); }
  .claim.open .claim-body { display: block; }

  .claim-grid { display: grid; grid-template-columns: 90px 1fr; gap: 3px 8px; font-size: 12px; }
  .cg-key { color: var(--muted); font-family: var(--mono); padding-top: 1px; }
  .cg-val { color: var(--text); font-family: var(--mono); word-break: break-word; line-height: 1.5; }
  .cg-val.dim { color: var(--muted); font-style: italic; }

  .claim-stmt {
    margin-top: 10px; padding: 8px 10px;
    background: var(--surface2); border-radius: 4px;
    font-size: 12px; color: var(--muted); line-height: 1.6;
    border-left: 2px solid var(--border);
  }
  .claim-stmt.has-text { color: var(--text); }

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
          <button class="tab" id="tab-raw" onclick="switchTab('raw')">JSON</button>
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
let currentTab = 'cards';

function switchTab(tab) {
  currentTab = tab;
  document.getElementById('tab-cards').classList.toggle('active', tab === 'cards');
  document.getElementById('tab-raw').classList.toggle('active', tab === 'raw');
  document.getElementById('results-wrap').style.display = tab === 'cards' ? 'flex' : 'none';
  document.getElementById('raw-view').style.display    = tab === 'raw'   ? 'flex' : 'none';
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
  const ep = item.epistemic || 'unknown';
  const subject = esc(item.subject || '—');
  const value   = esc(item.value   || '');
  const stmt    = esc(item.statement || '');
  const hasStmt = !!(item.statement || '').trim();
  const bears   = Array.isArray(item.bears_on) ? item.bears_on.join(', ') : (item.bears_on || '');

  return `
<div class="claim" id="claim-${idx}">
  <div class="claim-head" onclick="toggleClaim(${idx})">
    <span class="claim-num">${String(idx).padStart(2,'0')}</span>
    <span class="ep-badge ${epClass(ep)}">${ep}</span>
    <span class="claim-subject">${subject}</span>
    ${value ? `<span class="claim-value">${value}</span>` : ''}
    <span class="chevron">▶</span>
  </div>
  <div class="claim-body">
    <div class="claim-grid">
      <span class="cg-key">value</span>     ${val(item.value)}
      <span class="cg-key">period</span>    ${val(item.period)}
      <span class="cg-key">perimeter</span> ${val(item.perimeter)}
      <span class="cg-key">locator</span>   ${val(item.locator)}
      <span class="cg-key">direction</span> ${val(item.direction)}
      <span class="cg-key">author</span>    ${val(item.author)}
      <span class="cg-key">bears-on</span>  ${val(bears)}
      ${item.derivation ? `<span class="cg-key">derivation</span> ${val(item.derivation)}` : ''}
    </div>
    <div class="claim-stmt ${hasStmt ? 'has-text' : ''}">${hasStmt ? stmt : 'no statement'}</div>
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
  lastClaims = [];
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

  btn.disabled = false; btn.textContent = 'Extract claims';
  dot.classList.remove('pulsing');
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
            elapsed = round(time.time() - t0, 2)
            print(f"  → {len(claims)} claims  ({elapsed}s)  deal={deal}")
            resp = json.dumps({"claims": claims, "elapsed": elapsed})
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
