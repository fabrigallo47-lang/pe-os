#!/usr/bin/env python3
"""Vault ⇄ Vercel Blob sync — the storage layer for cloud mode.

Files stay files: the vault lives as private blobs under the 'vault/' prefix,
functions mirror it to /tmp, all existing code runs unchanged on the mirror.
Wire format verified empirically against the private store (API v12, pathname
as query param, x-vercel-blob-access header, Bearer download).

Seed once:  python3 tools/vaultsync.py seed
Status:     python3 tools/vaultsync.py status
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://blob.vercel-storage.com"
PREFIX = "vault/"


def _token() -> str:
    t = os.environ.get("BLOB_READ_WRITE_TOKEN")
    if not t:
        raise RuntimeError("BLOB_READ_WRITE_TOKEN not set")
    return t


def _req(url: str, method="GET", data=None, headers=None, timeout=60):
    h = {"Authorization": f"Bearer {_token()}", "x-api-version": "12", **(headers or {})}
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def list_blobs() -> dict[str, dict]:
    out, cursor = {}, None
    while True:
        q = {"prefix": PREFIX, "limit": "1000"}
        if cursor:
            q["cursor"] = cursor
        data = json.loads(_req(f"{API}/?{urllib.parse.urlencode(q)}"))
        for b in data.get("blobs", []):
            out[b["pathname"]] = b
        cursor = data.get("cursor")
        if not data.get("hasMore"):
            return out


def download(url: str) -> bytes:
    return _req(url)


def upload(pathname: str, content: bytes) -> None:
    _req(f"{API}/?pathname={urllib.parse.quote(pathname)}", method="PUT", data=content,
         headers={"x-vercel-blob-access": "private", "x-add-random-suffix": "0",
                  "x-allow-overwrite": "1"})


def delete(urls: list[str]) -> None:
    if urls:
        _req(f"{API}/delete", method="POST",
             data=json.dumps({"urls": urls}).encode(),
             headers={"Content-Type": "application/json"})


# ---------------------------------------------------------------- mirror sync

def _state_file(mirror: Path) -> Path:
    return mirror.parent / (mirror.name + ".sync.json")


def _load_state(mirror: Path) -> dict:
    f = _state_file(mirror)
    return json.loads(f.read_text()) if f.exists() else {}


def _save_state(mirror: Path, st: dict) -> None:
    _state_file(mirror).write_text(json.dumps(st))


def _md5(b: bytes) -> str:
    return hashlib.md5(b).hexdigest()


def sync_down(mirror: Path) -> int:
    """Pull remote changes into the mirror. Returns number of files updated."""
    st = _load_state(mirror)
    remote = list_blobs()
    n = 0
    for pathname, b in remote.items():
        rel = pathname[len(PREFIX):]
        entry = st.get(pathname, {})
        if entry.get("remote") == b["uploadedAt"]:
            continue
        content = download(b["url"])
        dest = mirror / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(content)
        st[pathname] = {"remote": b["uploadedAt"], "hash": _md5(content)}
        n += 1
    # remove local files deleted remotely
    for pathname in [p for p in st if p not in remote]:
        (mirror / pathname[len(PREFIX):]).unlink(missing_ok=True)
        del st[pathname]
        n += 1
    _save_state(mirror, st)
    return n


def push_dirty(mirror: Path) -> int:
    """Push local mirror changes up. Returns number of files pushed."""
    st = _load_state(mirror)
    n = 0
    for f in mirror.rglob("*"):
        if not f.is_file() or f.name.startswith("."):
            continue
        pathname = PREFIX + str(f.relative_to(mirror))
        content = f.read_bytes()
        h = _md5(content)
        if st.get(pathname, {}).get("hash") == h:
            continue
        upload(pathname, content)
        st[pathname] = {"remote": st.get(pathname, {}).get("remote", ""), "hash": h}
        n += 1
    _save_state(mirror, st)
    return n


def seed(local_vault: Path) -> int:
    n = 0
    for f in local_vault.rglob("*"):
        if f.is_file() and not f.name.startswith("."):
            upload(PREFIX + str(f.relative_to(local_vault)), f.read_bytes())
            n += 1
    return n


if __name__ == "__main__":
    ROOT = Path(__file__).resolve().parent.parent
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "seed":
        print(f"seeded {seed(ROOT / 'vault')} files → blob:{PREFIX}")
    elif cmd == "status":
        blobs = list_blobs()
        print(f"{len(blobs)} blobs under {PREFIX}")
        for p in sorted(blobs)[:10]:
            print("  ", p)
