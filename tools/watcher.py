"""
Inbox watcher — polls vault/inbox/ every 10 seconds.
When a new file arrives, fires sentinel + indexer so the deal pipeline activates
without any human action beyond dropping an artifact.

Usage:
  python3 tools/watcher.py              # default: http://127.0.0.1:8787
  python3 tools/watcher.py --base-url http://localhost:8787
"""

import argparse
import os
import sys
import time
import urllib.request
import urllib.error
import json
import subprocess
from pathlib import Path

ROOT   = Path(__file__).resolve().parent.parent
INBOX  = ROOT / "vault" / "inbox"
INDEXER = ROOT / "tools" / "indexer.py"
PYTHON  = sys.executable

SKIP_EXTENSIONS = {".gitkeep", ".DS_Store", ""}
SKIP_NAMES      = {".gitkeep", ".DS_Store", "README.md"}


def _post(url: str, payload: dict) -> dict | None:
    body = json.dumps(payload).encode()
    req  = urllib.request.Request(url, data=body,
                                   headers={"Content-Type": "application/json"},
                                   method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.URLError as e:
        print(f"  [watcher] POST {url} failed: {e}", flush=True)
        return None


def _reindex():
    result = subprocess.run(
        [PYTHON, str(INDEXER)],
        capture_output=True, text=True, timeout=60
    )
    if result.returncode != 0:
        print(f"  [watcher] indexer error: {result.stderr[:200]}", flush=True)


def _trigger(base_url: str, path: Path):
    print(f"  [watcher] new artifact: {path.name}", flush=True)

    # 1. Rebuild index so new file is visible in the graph
    _reindex()

    # 2. Run sentinel (scans inbox, classifies, attaches to deal)
    r = _post(f"{base_url}/api/agents/run/sentinel", {})
    if r:
        print(f"  [watcher] sentinel → {r.get('status','?')}", flush=True)

    # 3. Run extractor for the affected deal (sentinel output tells us which deal)
    # Extractor is triggered by sentinel producing a new artifact node;
    # a second sentinel pass or extractor tick will pick it up.
    # We fire a tick so all ready agents activate.
    time.sleep(2)
    r = _post(f"{base_url}/api/agents/tick", {})
    if r:
        agents = r.get("ran", [])
        print(f"  [watcher] tick ran: {agents}", flush=True)


def watch(base_url: str):
    known: set[str] = set()

    # Seed known set so we don't fire on files that were already there
    for f in INBOX.iterdir():
        if f.is_file() and f.name not in SKIP_NAMES and f.suffix not in SKIP_EXTENSIONS:
            known.add(f.name)

    print(f"[watcher] watching {INBOX}  ({len(known)} existing files seeded)", flush=True)
    print(f"[watcher] server  : {base_url}", flush=True)
    print(f"[watcher] drop a file into vault/inbox/ to activate the pipeline", flush=True)

    while True:
        time.sleep(10)
        try:
            current = {
                f.name for f in INBOX.iterdir()
                if f.is_file()
                and f.name not in SKIP_NAMES
                and f.suffix not in SKIP_EXTENSIONS
            }
        except OSError:
            continue

        new_files = current - known
        for fname in sorted(new_files):
            _trigger(base_url, INBOX / fname)

        known = current


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8787")
    args = parser.parse_args()
    try:
        watch(args.base_url)
    except KeyboardInterrupt:
        print("\n[watcher] stopped", flush=True)
