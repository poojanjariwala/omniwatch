"""Repository secret scanner.

Scans tracked text files and git history for high-entropy secrets and known
credential patterns. Findings are reported WITHOUT printing the secret values.
Usage:  python scripts/scan_secrets.py [--history]
"""
from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# .env.example is intentionally excluded; real .env should never exist.
_SKIP_PARTS = (".venv", "node_modules", "dist", "__pycache__", ".git", "data", "assets")

PATTERNS = [
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("github_token", re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}")),
    ("slack_token", re.compile(r"xox[baprs]-[0-9A-Za-z-]{10,}")),
    ("google_api", re.compile(r"AIza[0-9A-Za-z_-]{35}")),
    ("stripe_secret", re.compile(r"sk_live_[0-9A-Za-z]{24,}")),
    ("private_key_header", re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("jwt_secret_env", re.compile(r"(?im)^[A-Z0-9_]*(?:SECRET|TOKEN|PASSWORD|PASSWD|KEY)[A-Z0-9_]*\s*=\s*['\"]?(?=.{16,}$)[^'\"\s]{16,}")),
    ("supabase_service", re.compile(r"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9\.[A-Za-z0-9_-]{40,}\.([A-Za-z0-9_-]{40,})")),
]


def _iter_text_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_PARTS and not d.startswith(".")]
        for name in filenames:
            p = Path(dirpath) / name
            # .env.example holds obvious placeholders by design; real .env is
            # already excluded by .gitignore and should never be present.
            if p.name in (".env", ".env.example") or name in ("requirements.txt", "package-lock.json"):
                continue
            if p.suffix in {".py", ".ts", ".tsx", ".js", ".json", ".md", ".yml", ".yaml",
                            ".env.example", ".txt", ".conf", ".sql", ".html", ".css"}:
                yield p


def _scan_text(text: str):
    hits = []
    for label, rx in PATTERNS:
            for m in rx.finditer(text):
                value = m.group(0)
                low = value.lower()
                # Ignore obvious placeholders/test fixtures.
                if any(x in low for x in ("test", "changeme", "change-me", "example",
                                          "placeholder", "your-")):
                    continue
                hits.append((label, hashlib.sha256(value.encode()).hexdigest()[:12], value))
    return hits


def scan_tree() -> list[str]:
    findings = []
    for p in _iter_text_files(ROOT):
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for label, digest, _value in _scan_text(text):
            findings.append(f"{p.relative_to(ROOT)} :: {label} (sha256:{digest})")
    return findings


def scan_history() -> list[str]:
    findings = []
    try:
        out = subprocess.run(
            ["git", "log", "-p", "--all"], capture_output=True, text=True, timeout=120,
            cwd=ROOT,
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        return ["git history unavailable (not a git repo)"]
    for i, line in enumerate(out.stdout.splitlines()):
        if line.startswith(("+", "diff ")) and "password" in line.lower():
            findings.append(f"history@{i} contains a line mentioning password")
        for label, digest, _ in _scan_text(line):
            findings.append(f"history@{i} :: {label} (sha256:{digest})")
    return findings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--history", action="store_true", help="also scan git history")
    args = parser.parse_args()
    print(f"Scanning repository tree at {ROOT} …")
    tree = scan_tree()
    hist = scan_history() if args.history else []
    print(f"\nTree findings ({len(tree)}):")
    for f in tree[:50]:
        print("  " + f)
    if hist:
        print(f"\nHistory findings ({len(hist)}):")
        for f in hist[:50]:
            print("  " + f)
    if tree or hist:
        print("\n[!] Potential secrets found - rotate anything real and remove the file/history.")
        return 1
    print("\nNo obvious secrets found. Values are never printed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
