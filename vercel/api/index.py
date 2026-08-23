"""Single Vercel Python entrypoint — routes /api/* requests."""
from __future__ import annotations
import base64, io, json, os, re, sqlite3, sys, tempfile, traceback, uuid
import urllib.request, urllib.error, urllib.parse
from http.server import BaseHTTPRequestHandler
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_TOOLS = _HERE.parent.parent / "tools"
_PROJECT_ROOT = _HERE.parent.parent

sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_TOOLS))
from _core import SYSTEM_PROMPT, CHAT_SYSTEM, call_api, parse_json, API_KEY
from _claim_graph import claims_to_graph
from _graph_store import DealGraph, build_from_extraction

BLOB_TOKEN = os.environ.get("BLOB_READ_WRITE_TOKEN", "")

_MODEL_NODES_CSV = _PROJECT_ROOT / "vault" / "runs" / "e4v6" / "model_nodes.csv"
_MODEL_DEPS_JSON  = _PROJECT_ROOT / "vault" / "runs" / "e4v6" / "deps.json"

try:
    import csv as _csv_mod
    from keystone_model import propagate_claim as _propagate_claim, run_lbo as _run_lbo, PERIODS as _MODEL_PERIODS
    _MODEL_READY = True
except Exception as _me:
    _MODEL_READY = False
    _MODEL_IMPORT_ERR = str(_me)


# ── Vercel Blob helpers ───────────────────────────────────────────────────────

def _blob_store_base() -> str:
    """Derive the private base URL from the token (vercel_blob_rw_{storeId}_{secret})."""
    prefix = "vercel_blob_rw_"
    if not BLOB_TOKEN.startswith(prefix):
        return ""
    store_id = BLOB_TOKEN[len(prefix):].split("_")[0].lower()
    return f"https://{store_id}.private.blob.vercel-storage.com"


def _blob_put(pathname: str, data: bytes, content_type: str = "application/json") -> str:
    """Upload bytes to private Vercel Blob; return the canonical URL."""
    url = f"https://blob.vercel-storage.com/{pathname}"
    req = urllib.request.Request(
        url, data=data, method="PUT",
        headers={
            "Authorization":          f"Bearer {BLOB_TOKEN}",
            "Content-Type":           content_type,
            "x-api-version":          "7",
            "x-vercel-blob-access":   "private",
            "x-add-random-suffix":    "0",
        }
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())["url"]


def _blob_get(url: str) -> bytes:
    """Fetch bytes from a private Vercel Blob URL using the token."""
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {BLOB_TOKEN}",
            "User-Agent":    "pe-os/1.0",
        }
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


# ── PDF parsing ───────────────────────────────────────────────────────────────

def _pdf_to_text(data: bytes) -> str:
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(data))
        return "\n\n".join(p.extract_text() or "" for p in reader.pages)
    except ImportError:
        raise RuntimeError("pypdf not available on this server.")


# ── Analytics ─────────────────────────────────────────────────────────────────

def _build_analytics(dg: DealGraph) -> dict:
    try:
        pr   = dg.pagerank()
        btwn = dg.betweenness()
        top_pr = sorted(
            [{"id": nid, "score": round(s, 5), **dict(dg.G.nodes[nid])} for nid, s in pr.items()],
            key=lambda x: -x["score"])[:12]
        top_btwn = sorted(
            [{"id": nid, "score": round(s, 5), **dict(dg.G.nodes[nid])} for nid, s in btwn.items()],
            key=lambda x: -x["score"])[:8]
        return {
            "ready":           True,
            "stats":           dg.stats(),
            "top_pagerank":    top_pr,
            "top_betweenness": top_btwn,
            "contradictions":  dg.contradictions(),
            "graph":           dg.to_vis_json(),
        }
    except Exception:
        return {"ready": False, "error": traceback.format_exc()[-400:]}


# ── Route handlers ────────────────────────────────────────────────────────────

def _handle_extract(payload: dict) -> dict:
    text    = (payload.get("text")    or "").strip()
    deal    = (payload.get("deal")    or "test").strip()
    req_key = (payload.get("api_key") or "").strip()
    key     = req_key or API_KEY

    if not text:
        return {"error": "empty text"}
    if not key:
        return {"error": "No API key — paste your Anthropic key in the key field"}

    deal_context = (
        f"Deal: {deal}. Extract all factual claims relevant to investment analysis. "
        "Apply epistemic typing: asserted=seller/mgmt claim; observed=directly measured; "
        "attested=third-party cert; derived=computed. Include period and perimeter on every claim."
    )
    user_msg = f"DEAL CONTEXT:\n{deal_context}\n\nARTIFACT:\n{text[:80_000]}"

    import time
    t0     = time.time()
    raw    = call_api(SYSTEM_PROMPT, user_msg, key)
    claims = parse_json(raw)
    graph  = claims_to_graph(claims)
    elapsed = round(time.time() - t0, 2)

    dg        = build_from_extraction(claims, graph, deal)
    analytics = _build_analytics(dg)

    result: dict = {"claims": claims, "graph": graph, "analytics": analytics, "elapsed": elapsed}

    if BLOB_TOKEN:
        try:
            sid = uuid.uuid4().hex[:12]
            _blob_put(f"sessions/{sid}/claims.json",
                      json.dumps(claims, ensure_ascii=False).encode())
            _blob_put(f"sessions/{sid}/graph.json",
                      json.dumps(graph,  ensure_ascii=False).encode())
            result["session_id"] = sid
        except Exception:
            result["session_warning"] = traceback.format_exc()[-200:]

    return result


def _handle_parse_pdf(payload: dict) -> dict:
    pdf_bytes = base64.b64decode(payload.get("data", ""))
    text = _pdf_to_text(pdf_bytes)
    return {"text": text, "chars": len(text)}


def _handle_chat(payload: dict) -> dict:
    message  = (payload.get("message")  or "").strip()
    graph_in = payload.get("graph", {"nodes": [], "edges": []})
    req_key  = (payload.get("api_key") or "").strip()
    key      = req_key or API_KEY

    if not key:
        return {"error": "No API key"}
    if not message:
        return {"error": "empty message"}

    nodes_ctx = [
        {"id": n.get("id",""), "type": n.get("type",""),
         "metric": n.get("metric",""), "label": n.get("label",""),
         "value": n.get("value",""), "epistemic": n.get("epistemic",""),
         "subject": n.get("subject","")}
        for n in graph_in.get("nodes", [])
    ]
    edges_ctx = [
        {"source": e.get("source",""), "target": e.get("target",""), "rel": e.get("rel","")}
        for e in graph_in.get("edges", [])
    ]
    graph_ctx = "CURRENT GRAPH:\n" + json.dumps(
        {"nodes": nodes_ctx, "edges": edges_ctx}, separators=(",", ":"))
    user_msg = f"{graph_ctx}\n\nUSER REQUEST: {message}"

    raw = call_api(CHAT_SYSTEM, user_msg, key).strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        return json.loads(m.group()) if m else {"message": raw, "commands": []}


# ── SQLite export ─────────────────────────────────────────────────────────────

def _handle_export(payload: dict) -> bytes:
    """Build an in-memory SQLite DB from graph + claims, return raw bytes."""
    graph  = payload.get("graph",  {"nodes": [], "edges": []})
    claims = payload.get("claims", [])

    con = sqlite3.connect(":memory:")
    con.execute("""CREATE TABLE nodes (
        id TEXT PRIMARY KEY, type TEXT, label TEXT,
        metric TEXT, value TEXT, unit TEXT,
        epistemic TEXT, direction TEXT, subject TEXT,
        period TEXT, perimeter TEXT, statement TEXT, data TEXT
    )""")
    con.execute("""CREATE TABLE edges (
        src TEXT, tgt TEXT, rel TEXT, data TEXT,
        PRIMARY KEY (src, tgt, rel)
    )""")
    con.execute("""CREATE TABLE claims (
        idx INTEGER PRIMARY KEY, subject TEXT, metric TEXT,
        value TEXT, unit TEXT, as_of TEXT, period TEXT,
        perimeter TEXT, epistemic TEXT, direction TEXT,
        topic TEXT, source_doc TEXT, author TEXT,
        locator TEXT, statement TEXT, derivation TEXT, data TEXT
    )""")

    for n in graph.get("nodes", []):
        con.execute(
            "INSERT OR REPLACE INTO nodes VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (str(n.get("id","")), n.get("type",""), n.get("label",""),
             n.get("metric",""), str(n.get("value","")), n.get("unit",""),
             n.get("epistemic",""), n.get("direction",""), n.get("subject",""),
             n.get("period",""), n.get("perimeter",""), n.get("statement",""),
             json.dumps(n))
        )
    for e in graph.get("edges", []):
        con.execute(
            "INSERT OR REPLACE INTO edges VALUES (?,?,?,?)",
            (str(e.get("source","")), str(e.get("target","")),
             e.get("rel",""), json.dumps(e))
        )
    for i, c in enumerate(claims):
        con.execute(
            "INSERT OR REPLACE INTO claims VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (i, c.get("subject",""), c.get("metric",""), str(c.get("value","")),
             c.get("unit",""), c.get("as_of",""), c.get("period",""),
             c.get("perimeter",""), c.get("epistemic",""), c.get("direction",""),
             c.get("topic",""), c.get("source_doc",""), c.get("author",""),
             c.get("locator",""), c.get("statement",""), c.get("derivation",""),
             json.dumps(c))
        )
    con.commit()
    db_bytes = con.serialize()
    con.close()
    return db_bytes


# ── Session load ──────────────────────────────────────────────────────────────

def _handle_session_get(session_id: str) -> dict:
    if not BLOB_TOKEN:
        return {"error": "Blob storage not configured on this deployment"}
    base = _blob_store_base()
    if not base:
        return {"error": "Could not derive blob base URL from token"}
    try:
        claims = json.loads(_blob_get(f"{base}/sessions/{session_id}/claims.json"))
        graph  = json.loads(_blob_get(f"{base}/sessions/{session_id}/graph.json"))
        return {"claims": claims, "graph": graph, "session_id": session_id}
    except Exception:
        return {"error": f"Session not found or expired: {traceback.format_exc()[-200:]}"}


# ── Vercel handler ────────────────────────────────────────────────────────────

def _handle_model_nodes(_payload: dict | None = None) -> dict:
    if not _MODEL_NODES_CSV.exists():
        return {"error": f"model_nodes.csv not found at {_MODEL_NODES_CSV}", "nodes": []}
    import csv as _csv
    nodes = []
    with open(_MODEL_NODES_CSV, encoding="utf-8-sig") as f:
        for row in _csv.DictReader(f):
            nodes.append(dict(row))
    deps: dict = {}
    if _MODEL_DEPS_JSON.exists():
        deps = json.loads(_MODEL_DEPS_JSON.read_text())
    periods = [str(p) for p in _MODEL_PERIODS] if _MODEL_READY else []
    return {"nodes": nodes, "deps": deps, "periods": periods, "ready": _MODEL_READY}


def _handle_model_propagate(payload: dict) -> dict:
    if not _MODEL_READY:
        return {"error": f"Model not loaded: {globals().get('_MODEL_IMPORT_ERR', 'unknown')}"}
    claim    = payload.get("claim", {})
    scenario = payload.get("scenario", "standalone_base")
    if not claim or not claim.get("metric") or claim.get("value") is None:
        return {"error": "claim requires {metric, value, period}"}
    try:
        return _propagate_claim(claim, scenario=scenario)
    except Exception:
        return {"error": traceback.format_exc()[-600:]}


def _handle_model_snapshot(_payload: dict | None = None) -> dict:
    if not _MODEL_READY:
        return {"error": f"Model not loaded: {globals().get('_MODEL_IMPORT_ERR', 'unknown')}"}
    try:
        result = _run_lbo()
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
    except Exception:
        return {"error": traceback.format_exc()[-600:]}


ROUTES = {
    "/api/extract":          _handle_extract,
    "/api/parse-pdf":        _handle_parse_pdf,
    "/api/chat":             _handle_chat,
    "/api/model/nodes":      _handle_model_nodes,
    "/api/model/propagate":  _handle_model_propagate,
    "/api/model/snapshot":   _handle_model_snapshot,
    "/api/debug":     lambda _: {
        "blob_token_set": bool(BLOB_TOKEN),
        "blob_token_len": len(BLOB_TOKEN),
        "blob_base": _blob_store_base(),
        "api_key_set": bool(API_KEY),
        "model_ready": _MODEL_READY,
    },
}


class handler(BaseHTTPRequestHandler):
    def _json(self, code: int, body: dict) -> None:
        data = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type",   "application/json; charset=utf-8")
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
        path = self.path.split("?")[0].rstrip("/")
        qs   = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(self.path).query))
        if path == "/api/session":
            sid = qs.get("id", "").strip()
            if not sid:
                self._json(400, {"error": "missing id parameter"})
            else:
                self._json(200, _handle_session_get(sid))
        elif path in ("/api/model/nodes", "/api/model/snapshot"):
            fn = _handle_model_nodes if path == "/api/model/nodes" else _handle_model_snapshot
            self._json(200, fn())
        else:
            self._json(404, {"error": f"unknown GET route: {path}"})

    def _binary(self, data: bytes, content_type: str, filename: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type",        content_type)
        self.send_header("Content-Length",      str(len(data)))
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        path = self.path.split("?")[0].rstrip("/")

        # Binary export route (SQLite)
        if path == "/api/export":
            try:
                length  = int(self.headers.get("Content-Length", 0))
                payload = json.loads(self.rfile.read(length))
                db_bytes = _handle_export(payload)
                self._binary(db_bytes, "application/x-sqlite3", "graph.db")
            except Exception:
                self._json(500, {"error": traceback.format_exc()[-400:]})
            return

        fn = ROUTES.get(path)
        if fn is None:
            self._json(404, {"error": f"unknown route: {path}"}); return

        try:
            length  = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length))
            result  = fn(payload)
            self._json(200, result)
        except Exception:
            self._json(200, {"error": traceback.format_exc()[-400:]})

    def log_message(self, *_):
        pass
