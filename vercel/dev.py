#!/usr/bin/env python3
"""Local dev server for the Vercel extraction workbench + model API.

Serves vercel/public/ as static files and wires /api/* routes.
Does NOT require the Vercel CLI.

Usage:
    cd pe-os/vercel
    python3.12 dev.py
    open http://localhost:3000
"""
from __future__ import annotations

import csv, json, os, sys, traceback
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE    = Path(__file__).resolve().parent
ROOT    = HERE.parent
PUBLIC  = HERE / "public"
TOOLS   = ROOT / "tools"

sys.path.insert(0, str(HERE / "api"))
sys.path.insert(0, str(TOOLS))

try:
    from _core import SYSTEM_PROMPT, CHAT_SYSTEM, call_api, parse_json, API_KEY
    from _claim_graph import claims_to_graph
    from _graph_store import DealGraph, build_from_extraction
    _EXTRACT_READY = True
except Exception as e:
    _EXTRACT_READY = False
    _EXTRACT_ERR   = str(e)

try:
    from keystone_model import propagate_claim, run_lbo, PERIODS
    _MODEL_READY = True
except Exception as e:
    _MODEL_READY = False
    _MODEL_ERR   = str(e)

_MODEL_NODES_CSV = ROOT / "vault" / "runs" / "e4v6" / "model_nodes.csv"
_MODEL_DEPS_JSON  = ROOT / "vault" / "runs" / "e4v6" / "deps.json"


def _handle_model_nodes():
    if not _MODEL_NODES_CSV.exists():
        return {"error": f"not found: {_MODEL_NODES_CSV}", "nodes": []}
    nodes = list(csv.DictReader(open(_MODEL_NODES_CSV, encoding="utf-8-sig")))
    deps  = json.loads(_MODEL_DEPS_JSON.read_text()) if _MODEL_DEPS_JSON.exists() else {}
    periods = [str(p) for p in PERIODS] if _MODEL_READY else []
    return {"nodes": nodes, "deps": deps, "periods": periods, "ready": _MODEL_READY}


def _handle_model_snapshot():
    if not _MODEL_READY:
        return {"error": _MODEL_ERR}
    result = run_lbo()
    q = result.quarters
    return {
        "scenario":       "standalone_base",
        "exit_revenue":   round(result.exit_ltm_revenue, 3),
        "exit_ebitda":    round(result.exit_ltm_ebitda,  3),
        "exit_ev":        round(result.exit_ev,           3),
        "exit_net_debt":  round(result.exit_net_debt,     3),
        "exit_equity":    round(result.exit_equity,       3),
        "gross_moic":     round(result.gross_moic,        4),
        "gross_irr_pct":  round(result.gross_xirr * 100, 2),
        "periods":        [str(r.period)                  for r in q],
        "revenue":        [round(r.revenue,     3)        for r in q],
        "ebitda":         [round(r.firm_ebitda, 3)        for r in q],
        "net_leverage":   [round(r.net_leverage_covenant, 3) for r in q],
        "end_cash":       [round(r.end_cash,    3)        for r in q],
        "term_loan":      [round(r.term_loan,   3)        for r in q],
    }


def _handle_model_propagate(body: dict):
    if not _MODEL_READY:
        return {"error": _MODEL_ERR}
    claim    = body.get("claim", {})
    scenario = body.get("scenario", "standalone_base")
    if not claim or not claim.get("metric") or claim.get("value") is None:
        return {"error": "claim requires {metric, value, period}"}
    try:
        return propagate_claim(claim, scenario=scenario)
    except Exception:
        return {"error": traceback.format_exc()[-600:]}


def _handle_extract(body: dict) -> dict:
    if not _EXTRACT_READY:
        return {"error": f"Extraction module not loaded: {_EXTRACT_ERR}"}
    text    = (body.get("text") or "").strip()
    deal    = (body.get("deal") or "test").strip()
    req_key = (body.get("api_key") or "").strip()
    key     = req_key or API_KEY
    if not text:
        return {"error": "empty text"}
    if not key:
        return {"error": "No API key — paste your Anthropic key in the key field"}
    deal_ctx = (f"Deal: {deal}. Extract all factual claims relevant to investment analysis. "
                "Apply epistemic typing: asserted=seller/mgmt; observed=directly measured; "
                "attested=third-party cert; derived=computed. Include period and perimeter.")
    import time
    t0     = time.time()
    raw    = call_api(SYSTEM_PROMPT, f"DEAL CONTEXT:\n{deal_ctx}\n\nARTIFACT:\n{text[:80_000]}", key)
    claims = parse_json(raw)
    graph  = claims_to_graph(claims)
    elapsed = round(time.time() - t0, 2)
    dg      = build_from_extraction(claims, graph, deal)
    an_stats = {"nodes": len(graph["nodes"]), "edges": len(graph["edges"])}
    return {"claims": claims, "graph": graph, "analytics": an_stats, "elapsed": elapsed}


def _handle_chat(body: dict) -> dict:
    if not _EXTRACT_READY:
        return {"error": f"Chat module not loaded: {_EXTRACT_ERR}"}
    msg     = (body.get("message") or "").strip()
    graph   = body.get("graph", {"nodes": [], "edges": []})
    req_key = (body.get("api_key") or "").strip()
    key     = req_key or API_KEY
    if not key:
        return {"error": "No API key"}
    if not msg:
        return {"error": "empty message"}
    ctx = f"Current graph: {json.dumps(graph)[:12000]}"
    raw = call_api(CHAT_SYSTEM, f"{ctx}\n\nUser: {msg}", key)
    try:
        return json.loads(raw)
    except Exception:
        return {"message": raw[:500], "commands": []}


def _handle_session_get(sid: str) -> dict:
    return {"error": "session storage not available in dev mode", "session_id": sid}


API_GET_ROUTES = {
    "/api/model/nodes":    _handle_model_nodes,
    "/api/model/snapshot": _handle_model_snapshot,
}

API_POST_ROUTES = {
    "/api/extract":         _handle_extract,
    "/api/chat":            _handle_chat,
    "/api/model/propagate": _handle_model_propagate,
}


class DevHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PUBLIC), **kwargs)

    def _json_response(self, body: dict):
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin",  "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(self.path)
        path   = parsed.path.rstrip("/") or "/"
        qs     = parse_qs(parsed.query)
        if path in API_GET_ROUTES:
            self._json_response(API_GET_ROUTES[path]())
        elif path == "/api/session":
            sid = qs.get("id", [""])[0]
            self._json_response(_handle_session_get(sid))
        elif path == "/api/debug":
            self._json_response({"model_ready": _MODEL_READY, "extract_ready": _EXTRACT_READY,
                                  "model": "claude-sonnet-5"})
        else:
            super().do_GET()

    def do_POST(self):
        path = self.path.split("?")[0].rstrip("/")
        fn = API_POST_ROUTES.get(path)
        if fn is None:
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length", 0))
        body   = json.loads(self.rfile.read(length)) if length else {}
        self._json_response(fn(body))

    def log_message(self, fmt, *args):
        # only log API routes
        if "/api/" in (args[0] if args else ""):
            print(f"  {args[0]}  →  {args[1]}")


if __name__ == "__main__":
    PORT = int(os.environ.get("PORT", 3000))
    print(f"PE OS dev server — http://localhost:{PORT}")
    print(f"  serving:  {PUBLIC}")
    print(f"  model ready: {_MODEL_READY}")
    print()
    HTTPServer(("", PORT), DevHandler).serve_forever()
