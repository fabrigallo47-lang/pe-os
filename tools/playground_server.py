#!/usr/bin/env python3
"""A bench for feeding one input in and watching every layer act on it.

Why this and not the V20 app
----------------------------
V20 shows a finished case. This shows the machinery: paste a sentence, drop a
document or a workbook, and see what each layer did to it and — as often matters
more — what it refused to do.

    L1  chunk        deterministic split; for a workbook, cells and formulas
    L2  extract      the model proposes claims (Haiku, forced schema)
    L3  identity     each claim's tuple, and whether it resolves at all
    L4  relations    what the new claim did to what was already there

Deliberately stdlib-only and single-process. The machine this runs on could not
start a second uvicorn, and a debugging tool that needs a healthy machine is
useless exactly when it is needed.

Nothing is written to the vault or to pipeline_out. State lives in memory for the
life of the process, so a session can be thrown away by restarting.

    python3 tools/playground_server.py            # http://127.0.0.1:8901
    python3 tools/playground_server.py --port N
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
from email.parser import BytesParser
from email.policy import default as email_policy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Claims admitted this session, newest last. In memory on purpose: the bench must
# never contaminate the real corpus with experiments.
SESSION: list[dict[str, Any]] = []


def _identity_report(claim: dict[str, Any]) -> dict[str, Any]:
    from tools.object_identity import claim_id, is_resolvable, metric_identity

    identity = metric_identity(claim)
    names = ("entità", "metrica", "periodo", "ambito", "base",
             "fetta", "scenario", "unità", "valuta")
    missing = [n for n, v in zip(names[:3], identity[:3]) if not v]
    return {
        "dimensions": [{"name": n, "value": v} for n, v in zip(names, identity)],
        "resolvable": is_resolvable(claim),
        "claim_id": claim_id(claim),
        "key": "|".join(identity),
        # Say which dimension is missing, not merely that it failed: "no period"
        # is actionable, "unresolvable" is not.
        "why": ("confrontabile con altri claim sulla stessa quantità"
                if is_resolvable(claim)
                else f"non confrontabile — manca: {', '.join(missing)}. "
                     f"Resta come coverage limit dichiarato, mai accoppiato a caso."),
    }


def _relation_report(claim: dict[str, Any], identity_key: str) -> dict[str, Any]:
    """What this claim did to the claims already present."""
    peers = [c for c in SESSION if c.get("_identity_key") == identity_key]
    if not peers:
        return {"event": "NEW_IDENTITY", "peers": [],
                "why": "prima affermazione su questa quantità — un nodo, ancora senza significato"}

    def value_of(c):
        try:
            return f"{float(c.get('value')):.6g}"
        except (TypeError, ValueError):
            return str(c.get("value") or "").strip().lower()

    mine = value_of(claim)
    peer_values = {value_of(p) for p in peers if value_of(p)}
    peer_ids = [str(p.get("claim_id")) for p in peers]

    if mine and mine in peer_values:
        return {"event": "CORROBORATES", "peers": peer_ids,
                "why": "un'altra fonte afferma lo stesso valore sulla stessa identità — "
                       "restano due claim, mai fusi: l'accordo è l'informazione"}
    return {"event": "CONTRADICTS", "peers": peer_ids,
            "why": f"stessa identità, valore divergente ({mine} contro {', '.join(sorted(peer_values))}) — "
                   f"è qui che il caso guadagna un conflitto"}


def run_pipeline(text: str, filename: str = "incolla.md",
                 raw: bytes | None = None) -> dict[str, Any]:
    from tools.extract_v2_physical import (CHUNK_WORDS, annotate_chunk, parse_source,
                                  validate, MODEL)
    from tools.llm_provider import configured_api_key

    stages: list[dict[str, Any]] = []
    tmp = ROOT / "pipeline_out" / "trace" / "_playground_input"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp = tmp.with_suffix(Path(filename).suffix or ".md")
    tmp.write_bytes(raw if raw is not None else text.encode("utf-8"))

    # ── L1 ────────────────────────────────────────────────────────────────────
    try:
        chunks = parse_source(tmp, max_words=CHUNK_WORDS)
    except Exception as exc:
        return {"error": f"L1 non è riuscito a leggere {filename}: {exc}"}
    stages.append({
        "layer": "L1 · chunk deterministico",
        "detail": f"{len(chunks)} frammento/i, nessun modello coinvolto",
        "items": [{"locator": c.locator, "preview": (c.body or "")[:220]} for c in chunks[:12]],
    })

    if not configured_api_key():
        stages.append({"layer": "L2 · estrazione", "detail":
                       "ANTHROPIC_API_KEY non impostata — mi fermo qui invece di inventare claim",
                       "items": []})
        return {"stages": stages, "claims": []}

    # ── L2 ────────────────────────────────────────────────────────────────────
    raw_claims = []
    errors = []
    for chunk in chunks[:6]:                      # bounded: this is a bench
        try:
            raw_claims.extend(annotate_chunk(chunk, _client(), "playground", raise_errors=True))
        except Exception as exc:
            errors.append(f"{chunk.locator}: {exc}")
    stages.append({
        "layer": f"L2 · estrazione ({MODEL})",
        "detail": f"{len(raw_claims)} claim proposti" + (f" · {len(errors)} chunk falliti" if errors else ""),
        "items": [{"locator": e, "preview": ""} for e in errors[:4]],
    })

    # ── L3 + L4 ───────────────────────────────────────────────────────────────
    out = []
    for raw_claim in raw_claims:
        canonical = validate(raw_claim)
        record = {**canonical.__dict__}
        ident = _identity_report(record)
        rel = _relation_report(record, ident["key"])
        record["_identity_key"] = ident["key"]
        SESSION.append(record)
        out.append({
            "statement": canonical.statement,
            "value": canonical.value, "unit": canonical.unit,
            "epistemic": canonical.epistemic_class,
            "locator": canonical.locator,
            "identity": ident, "relation": rel,
            "validation_errors": canonical.validation_errors,
        })
    return {"stages": stages, "claims": out, "session_size": len(SESSION)}


def _client():
    from tools.extract_v2_physical import MODEL  # noqa: F401
    from tools.llm_provider import anthropic_client_kwargs, configured_api_key
    import anthropic
    return anthropic.Anthropic(**anthropic_client_kwargs(configured_api_key()))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):                 # keep the console readable
        pass

    def _send(self, payload: Any, status: int = 200, ctype: str = "application/json"):
        body = payload if isinstance(payload, bytes) else json.dumps(payload, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            page = ROOT / "tools" / "playground.html"
            return self._send(page.read_bytes(), ctype="text/html; charset=utf-8")
        if self.path == "/session":
            return self._send({"count": len(SESSION)})
        if self.path == "/reset":
            SESSION.clear()
            return self._send({"ok": True, "count": 0})
        self._send({"error": "not found"}, 404)

    def do_POST(self):
        try:
            ctype = self.headers.get("Content-Type", "")
            if ctype.startswith("multipart/form-data"):
                # `cgi` was removed in Python 3.13 and this runs on 3.14. The
                # email parser is the stdlib path that replaces it: reconstruct
                # the body as a MIME document and read the one file part.
                length = int(self.headers.get("Content-Length") or 0)
                body = b"Content-Type: " + ctype.encode() + b"\r\n\r\n" + self.rfile.read(length)
                message = BytesParser(policy=email_policy).parsebytes(body)
                part = next((p for p in message.iter_parts() if p.get_filename()), None)
                if part is None:
                    return self._send({"error": "nessun file nella richiesta"}, 400)
                data = part.get_payload(decode=True) or b""
                name = part.get_filename() or "upload.bin"
                text = "" if name.lower().endswith((".xlsx", ".xlsm", ".pdf")) \
                    else data.decode("utf-8", "replace")
                result = run_pipeline(text, name, raw=data)
            else:
                length = int(self.headers.get("Content-Length") or 0)
                payload = json.loads(self.rfile.read(length) or b"{}")
                result = run_pipeline(payload.get("text", ""), "incolla.md")
            self._send(result)
        except Exception:
            self._send({"error": traceback.format_exc()[-1200:]}, 500)


def main() -> int:
    parser = argparse.ArgumentParser(description="Extraction bench")
    parser.add_argument("--port", type=int, default=8901)
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"banco di prova: http://127.0.0.1:{args.port}")
    print("nulla viene scritto nel vault; lo stato vive in memoria")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nchiuso")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
