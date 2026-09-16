#!/usr/bin/env python3
"""Validate minimal clean-room Amphion scaffold."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List


REQUIRED_PATHS = [
    ".amphion",
    ".amphion/config.json",
    ".amphion/environment.json",
    ".amphion/command-deck",
    ".amphion/control-plane",
    ".amphion/control-plane/mcd",
]

OPTIONAL_LEGACY_PATHS = [
    "referenceDocs",
    "mcd-starter-kit-dev",
    "ops",
    ".amphion/memory",
]

DISALLOWED_DEFAULT_PATHS = [
    "referenceDocs",
    "mcd-starter-kit-dev",
    "ops",
]


def _exists(root: Path, rel: str) -> bool:
    return (root / rel).exists()


def _scan(root: Path) -> Dict[str, List[str]]:
    missing_required = [rel for rel in REQUIRED_PATHS if not _exists(root, rel)]
    present_legacy = [rel for rel in OPTIONAL_LEGACY_PATHS if _exists(root, rel)]
    present_disallowed = [rel for rel in DISALLOWED_DEFAULT_PATHS if _exists(root, rel)]
    return {
        "missingRequired": missing_required,
        "presentLegacyOptional": present_legacy,
        "presentDisallowedDefaults": present_disallowed,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate clean-room minimal scaffold output.")
    parser.add_argument("--workspace", default=".", help="Workspace root to validate")
    parser.add_argument(
        "--strict-no-legacy",
        action="store_true",
        help="Fail if optional legacy adapter/paths are present",
    )
    args = parser.parse_args()

    root = Path(args.workspace).resolve()
    findings = _scan(root)
    ok = len(findings["missingRequired"]) == 0 and len(findings["presentDisallowedDefaults"]) == 0
    if args.strict_no_legacy and len(findings["presentLegacyOptional"]) > 0:
        ok = False

    report = {
        "ok": ok,
        "workspace": str(root),
        "requiredPaths": REQUIRED_PATHS,
        "disallowedDefaultPaths": DISALLOWED_DEFAULT_PATHS,
        "strictNoLegacy": args.strict_no_legacy,
        "findings": findings,
    }
    print(json.dumps(report, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
