#!/usr/bin/env python3
"""Validate Amphion workspace migration report artifacts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List


REQUIRED_TOP_LEVEL = [
    "ok",
    "applied",
    "timestamp",
    "preflight",
    "postflight",
    "verification",
    "archive",
    "cleanup",
    "reportPath",
    "restoreRunbook",
]


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _find_latest_report(root: Path) -> Path:
    migrations_dir = root / ".amphion" / "migrations"
    if not migrations_dir.exists():
        raise FileNotFoundError(f"migrations directory not found: {migrations_dir}")
    reports = sorted(migrations_dir.glob("*-migration-report.json"))
    if not reports:
        raise FileNotFoundError("no migration report files found")
    return reports[-1]


def _validate(report: Dict[str, Any]) -> List[str]:
    errors: List[str] = []

    for key in REQUIRED_TOP_LEVEL:
        if key not in report:
            errors.append(f"missing field: {key}")

    verification = report.get("verification", {})
    if not verification.get("cardCountOk", False):
        errors.append("verification.cardCountOk is false")
    if not verification.get("milestoneCountOk", False):
        errors.append("verification.milestoneCountOk is false")

    archive = report.get("archive", {})
    if not archive.get("ok", False):
        errors.append("archive.ok is false")
    else:
        archive_path = Path(str(archive.get("path", "")))
        if not archive_path.exists():
            errors.append(f"archive path missing on disk: {archive_path}")

    restore_path = Path(str(report.get("restoreRunbook", "")))
    if not restore_path.exists():
        errors.append(f"restore runbook missing: {restore_path}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate .amphion migration report integrity.")
    parser.add_argument("--workspace", default=".", help="Workspace root")
    parser.add_argument("--report", default="", help="Explicit report path (optional)")
    args = parser.parse_args()

    root = Path(args.workspace).resolve()
    report_path = Path(args.report).resolve() if args.report else _find_latest_report(root)
    report = _load_json(report_path)
    errors = _validate(report)

    payload = {
        "ok": len(errors) == 0,
        "reportPath": str(report_path),
        "errors": errors,
    }
    print(json.dumps(payload, indent=2))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
