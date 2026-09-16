#!/usr/bin/env python3
"""Scan repo for legacy drift against DB-canonical lifecycle."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SCAN_PATHS = [
    ROOT / "referenceDocs",
    ROOT / ".agents",
    ROOT / ".cursor",
    ROOT / ".windsurf",
    ROOT / "AGENTS.md",
    ROOT / "CLAUDE.md",
    ROOT / "mcd-starter-kit-dev" / "extension" / "src",
]

RULES = [
    ("legacy-state-json", re.compile(r"state\.json", re.IGNORECASE)),
    ("legacy-board-phase", re.compile(r"\bBoard\s*\(Optional\)|\b/board\b|Phase:\s*1\.5", re.IGNORECASE)),
    ("legacy-contract-files", re.compile(r"03_Contracts/active|03_Contracts/archive", re.IGNORECASE)),
]


def scan_file(path: Path) -> list[dict]:
    findings = []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return findings
    for rule_id, pattern in RULES:
        for match in pattern.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            findings.append(
                {
                    "rule": rule_id,
                    "path": str(path.relative_to(ROOT)),
                    "line": line,
                    "snippet": text.splitlines()[line - 1][:220],
                }
            )
    return findings


def main() -> int:
    findings: list[dict] = []
    for scan_root in SCAN_PATHS:
        if not scan_root.exists():
            continue
        if scan_root.is_file():
            findings.extend(scan_file(scan_root))
            continue
        for path in scan_root.rglob("*"):
            if not path.is_file():
                continue
            if ".git/" in str(path):
                continue
            findings.extend(scan_file(path))

    print(json.dumps({"ok": True, "count": len(findings), "findings": findings}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
