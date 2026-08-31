#!/usr/bin/env python3
"""Enforce the project invariants that a generic CI would never think to check.

CLAUDE.md invariant 7 says nothing leaves this machine. The repository is public.
Those two facts are only compatible because certain paths are gitignored — a
convention that holds until someone runs ``git add -A`` at the wrong moment, and
that fails silently and irreversibly: once a deal file is pushed it is in
GitHub's history whether or not the next commit removes it.

This turns the convention into a gate. It checks what is *tracked*, not what is
on disk, because .gitignore only protects files nobody has staged yet.

    python3 tools/check_guards.py

Exit 0 clean, 1 with findings.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Paths whose contents are confidential deal material or private modules. A file
# tracked under any of these is a leak, not a style problem.
FORBIDDEN_PREFIXES: dict[str, str] = {
    "vault/deals/": "deal claims, questions and decisions — confidential client work",
    "vault/inbox/": "raw uploaded artifacts awaiting ingestion",
    "vault/audit/": "runtime audit state, may name people and actions",
    "vault/entities/people/": "named individuals",
    "sources/": "source corpora, including client documents",
}

FORBIDDEN_FILES: dict[str, str] = {
    ".env": "credentials",
    ".env.local": "credentials",
    ".env.vercel": "credentials",
    "tools/cell_engine.py": "private module, deliberately excluded from the public repo",
}

# Secret shapes worth failing on. Deliberately narrow: a pattern that fires on
# ordinary code teaches people to ignore the gate, which is worse than not having
# one. Each must match a real credential format, anchored enough to avoid prose.
SECRET_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"sk-ant-[A-Za-z0-9_\-]{20,}", "Anthropic API key"),
    (r"lin_api_[A-Za-z0-9]{30,}", "Linear API key"),
    (r"sk-[A-Za-z0-9]{32,}", "OpenAI-style API key"),
    (r"ghp_[A-Za-z0-9]{30,}", "GitHub personal access token"),
    (r"AKIA[0-9A-Z]{16}", "AWS access key id"),
    (r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----", "private key"),
)

# Files that legitimately contain a secret-shaped string: the guard's own
# patterns, and documentation showing what a key looks like.
SECRET_SCAN_EXEMPT = {"tools/check_guards.py"}

MAX_TRACKED_MB = 25


def tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    )
    return [line for line in out.stdout.splitlines() if line.strip()]


def check_confidential(files: list[str]) -> list[str]:
    findings = []
    for path in files:
        for prefix, why in FORBIDDEN_PREFIXES.items():
            if path.startswith(prefix):
                findings.append(f"{path} is tracked — {prefix} holds {why}")
        if path in FORBIDDEN_FILES:
            findings.append(f"{path} is tracked — {FORBIDDEN_FILES[path]}")
    return findings


def check_secrets(files: list[str]) -> list[str]:
    findings = []
    for path in files:
        if path in SECRET_SCAN_EXEMPT:
            continue
        full = ROOT / path
        try:
            if full.stat().st_size > 2_000_000:
                continue                       # a 2MB+ file is data, not source
            content = full.read_text(encoding="utf-8", errors="ignore")
        except (OSError, ValueError):
            continue
        for pattern, label in SECRET_PATTERNS:
            match = re.search(pattern, content)
            if match:
                # Report the location, never the value.
                line = content[: match.start()].count("\n") + 1
                findings.append(f"{path}:{line} looks like a {label}")
    return findings


def check_size(files: list[str]) -> list[str]:
    findings = []
    for path in files:
        try:
            size_mb = (ROOT / path).stat().st_size / 1_000_000
        except OSError:
            continue
        if size_mb > MAX_TRACKED_MB:
            findings.append(f"{path} is {size_mb:.1f}MB — over the {MAX_TRACKED_MB}MB limit")
    return findings


def check_gitignore() -> list[str]:
    """The prefixes above must actually be ignored, not merely unstaged so far."""
    try:
        text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    except OSError:
        return [".gitignore is missing — nothing is protecting the confidential paths"]
    findings = []
    for prefix in list(FORBIDDEN_PREFIXES) + [".env"]:
        needle = prefix.rstrip("/")
        if not any(line.strip().rstrip("/") == needle for line in text.splitlines()):
            findings.append(
                f"{prefix} is not in .gitignore — it is unprotected the moment "
                f"someone runs `git add -A`"
            )
    return findings


def main() -> int:
    files = tracked_files()
    sections = (
        ("confidential paths", check_confidential(files)),
        ("secrets in tracked content", check_secrets(files)),
        (".gitignore coverage", check_gitignore()),
        ("tracked file size", check_size(files)),
    )
    total = sum(len(findings) for _, findings in sections)

    print(f"guards: {len(files)} tracked files\n")
    for name, findings in sections:
        if findings:
            print(f"  FAIL  {name}")
            for finding in findings:
                print(f"          {finding}")
        else:
            print(f"  ok    {name}")

    if total:
        print(f"\n{total} finding(s). Nothing confidential may reach a public remote.")
        print("If a file is already pushed, removing it in a later commit is not enough —")
        print("it stays in history. Rotate anything exposed and rewrite the history.")
        return 1
    print("\nclean")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
