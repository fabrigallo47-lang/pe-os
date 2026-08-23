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


API_GET_ROUTES = {
    "/api/model/nodes":    _handle_model_nodes,
    "/api/model/snapshot": _handle_model_snapshot,
}

API_POST_ROUTES = {
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
        path = self.path.split("?")[0].rstrip("/") or "/"
        if path in API_GET_ROUTES:
            self._json_response(API_GET_ROUTES[path]())
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
