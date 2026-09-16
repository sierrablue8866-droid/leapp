#!/usr/bin/env python3
"""Agent-assisted workspace migration into .amphion control plane."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import zipfile
import datetime as dt
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _state_json_counts(path: Path) -> Dict[str, int]:
    if not path.exists():
        return {"boards": 0, "lists": 0, "milestones": 0, "cards": 0, "charts": 0}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        boards = state.get("boards", [])
        return {
            "boards": len(boards),
            "lists": sum(len(board.get("lists", [])) for board in boards if isinstance(board, dict)),
            "milestones": sum(len(board.get("milestones", [])) for board in boards if isinstance(board, dict)),
            "cards": sum(len(board.get("cards", [])) for board in boards if isinstance(board, dict)),
            "charts": len(state.get("charts", [])),
        }
    except Exception:
        return {"boards": 0, "lists": 0, "milestones": 0, "cards": 0, "charts": 0}


def _sqlite_counts(path: Path) -> Dict[str, int]:
    if not path.exists():
        return {"boards": 0, "lists": 0, "milestones": 0, "cards": 0, "charts": 0}
    conn = sqlite3.connect(path)
    c = conn.cursor()
    try:
        return {
            "boards": int(c.execute("SELECT COUNT(*) FROM boards").fetchone()[0]),
            "lists": int(c.execute("SELECT COUNT(*) FROM lists").fetchone()[0]),
            "milestones": int(c.execute("SELECT COUNT(*) FROM milestones").fetchone()[0]),
            "cards": int(c.execute("SELECT COUNT(*) FROM cards").fetchone()[0]),
            "charts": int(c.execute("SELECT COUNT(*) FROM charts").fetchone()[0]),
        }
    finally:
        conn.close()


def _copy_deck(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        if item.name == "__pycache__":
            continue
        target = dst / item.name
        if item.is_dir():
            if item.name == "data":
                target.mkdir(parents=True, exist_ok=True)
                for data_file in item.iterdir():
                    if data_file.name in {"state.json", "__pycache__"}:
                        continue
                    if data_file.is_file() and not (target / data_file.name).exists():
                        shutil.copy2(data_file, target / data_file.name)
                continue
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            if item.name == "state.json":
                continue
            if not target.exists():
                shutil.copy2(item, target)


def _confirm(prompt: str) -> bool:
    try:
        response = input(f"{prompt} [y/N]: ").strip().lower()
    except EOFError:
        return False
    return response in {"y", "yes"}


def _timestamp_slug() -> str:
    return dt.datetime.utcnow().strftime("%Y%m%d%H%M")


def _iter_files(root: Path) -> List[Path]:
    if root.is_file():
        return [root]
    files: List[Path] = []
    for path in root.rglob("*"):
        if path.is_file():
            files.append(path)
    return sorted(files, key=lambda p: str(p))


def _should_exclude(path: Path) -> bool:
    parts = path.parts
    if "__pycache__" in parts:
        return True
    if path.suffix == ".pyc":
        return True
    return False


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _build_archive(
    workspace_root: Path,
    archive_path: Path,
    candidate_paths: List[Path],
    *,
    force: bool = False,
) -> Dict[str, Any]:
    if archive_path.exists() and not force:
        return {
            "ok": False,
            "reason": "archive-already-exists",
            "path": str(archive_path),
        }

    include_files: List[Path] = []
    include_roots: List[str] = []
    excluded: List[str] = []
    total_bytes = 0

    for root in candidate_paths:
        if not root.exists():
            continue
        include_roots.append(str(root.relative_to(workspace_root)))
        for file_path in _iter_files(root):
            rel = file_path.relative_to(workspace_root)
            if _should_exclude(file_path):
                excluded.append(str(rel))
                continue
            include_files.append(file_path)
            total_bytes += file_path.stat().st_size

    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(include_files, key=lambda p: str(p)):
            arcname = str(file_path.relative_to(workspace_root))
            zf.write(file_path, arcname=arcname)

    checksum = _sha256(archive_path)
    return {
        "ok": True,
        "path": str(archive_path),
        "sizeBytes": archive_path.stat().st_size,
        "sha256": checksum,
        "includedRoots": include_roots,
        "includedFileCount": len(include_files),
        "includedTotalBytes": total_bytes,
        "excludedCount": len(excluded),
        "excludedPaths": sorted(excluded),
    }


def _write_restore_runbook(root: Path) -> Path:
    runbook = root / ".amphion" / "migrations" / "RESTORE_FROM_ARCHIVE.md"
    runbook.parent.mkdir(parents=True, exist_ok=True)
    runbook.write_text(
        "# Restore From Legacy Scaffold Archive\n\n"
        "1. Identify the migration archive in `.amphion/archives/`.\n"
        "2. Extract it at workspace root (same level as `.amphion/`).\n"
        "3. Verify restored directories/files before restarting Command Deck.\n"
        "4. If needed, point runtime back to legacy path by editing `.amphion/config.json`.\n"
        "5. Re-run migration script in preview mode to compare counts.\n",
        encoding="utf-8",
    )
    return runbook


def _delete_path(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "deleted": False, "reason": "not-found"}
    if path.is_dir():
        shutil.rmtree(path)
        return {"path": str(path), "deleted": True, "type": "dir"}
    path.unlink()
    return {"path": str(path), "deleted": True, "type": "file"}


def _backup_and_copy_file(src: Path, dest: Path, backup_suffix: str) -> Dict[str, Any]:
    details: Dict[str, Any] = {"copied": False, "backupPath": ""}
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        backup = dest.with_suffix(dest.suffix + backup_suffix)
        shutil.copy2(dest, backup)
        details["backupPath"] = str(backup)
    shutil.copy2(src, dest)
    details["copied"] = True
    return details


def _cleanup_decision_prompt() -> str:
    print("\nPost-migration cleanup options:")
    print("1) Open Archive")
    print("2) Review Legacy Paths")
    print("3) Delete Legacy Now")
    print("4) Keep for Now")
    choice = input("Select [1-4] (default 4): ").strip() or "4"
    return {
        "1": "open-archive",
        "2": "review-paths",
        "3": "delete-legacy-now",
        "4": "keep-for-now",
    }.get(choice, "keep-for-now")


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate workspace from legacy ops layout to .amphion control plane.")
    parser.add_argument("--workspace", default=".", help="Workspace root directory")
    parser.add_argument("--apply", action="store_true", help="Apply migration changes")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt")
    parser.add_argument("--force-archive", action="store_true", help="Allow archive overwrite if same path exists.")
    parser.add_argument(
        "--cleanup-action",
        choices=["prompt", "keep", "delete"],
        default="prompt",
        help="Post-migration cleanup behavior for legacy scaffolding.",
    )
    args = parser.parse_args()

    root = Path(args.workspace).resolve()
    ops_cfg = root / "ops" / "amphion.json"
    amphion_cfg = root / ".amphion" / "config.json"
    legacy_deck = root / "ops" / "launch-command-deck"
    canonical_deck = root / ".amphion" / "command-deck"

    legacy_state = legacy_deck / "data" / "state.json"
    legacy_db = legacy_deck / "data" / "amphion.db"
    canonical_db = canonical_deck / "data" / "amphion.db"
    now_slug = _timestamp_slug()
    archive_path = root / ".amphion" / "archives" / f"{now_slug}-legacy-scaffold.zip"
    report_path = root / ".amphion" / "migrations" / f"{now_slug}-migration-report.json"

    pre = {
        "workspace": str(root),
        "paths": {
            "legacyDeck": str(legacy_deck),
            "canonicalDeck": str(canonical_deck),
            "legacyConfig": str(ops_cfg),
            "canonicalConfig": str(amphion_cfg),
        },
        "exists": {
            "legacyDeck": legacy_deck.exists(),
            "canonicalDeck": canonical_deck.exists(),
            "legacyConfig": ops_cfg.exists(),
            "canonicalConfig": amphion_cfg.exists(),
        },
        "legacyStateCounts": _state_json_counts(legacy_state),
        "legacySqliteCounts": _sqlite_counts(legacy_db),
        "canonicalSqliteCounts": _sqlite_counts(canonical_db),
    }

    plan = [
        "ensure .amphion canonical runtime directories exist",
        "copy command deck assets from ops/launch-command-deck to .amphion/command-deck (non-destructive)",
        "if legacy sqlite is ahead of canonical, back up canonical DB then sync from legacy",
        "mirror runtime config to .amphion/config.json and set commandDeckPath=.amphion/command-deck",
        "preserve ops/amphion.json as compatibility mirror",
        "skip legacy state.json import files during copy",
        "archive legacy scaffolding to .amphion/archives/*.zip with manifest/checksum",
        "present cleanup recommendation with explicit user decision",
    ]

    report: Dict[str, Any] = {
        "ok": True,
        "applied": False,
        "timestamp": now_slug,
        "plan": plan,
        "preflight": pre,
        "archive": {},
        "cleanup": {"decision": "not-run", "actions": []},
        "reportPath": str(report_path),
    }

    if not args.apply:
        print(json.dumps(report, indent=2))
        return 0

    if not args.yes and not _confirm("Apply workspace migration now?"):
        report["ok"] = False
        report["applied"] = False
        report["reason"] = "aborted-by-user"
        print(json.dumps(report, indent=2))
        return 1

    root.joinpath(".amphion", "memory").mkdir(parents=True, exist_ok=True)
    _copy_deck(legacy_deck, canonical_deck)

    sync_details: Dict[str, Any] = {"performed": False}
    legacy_counts_now = _sqlite_counts(legacy_db)
    canonical_counts_now = _sqlite_counts(canonical_db)
    if legacy_db.exists() and (
        canonical_counts_now["cards"] < legacy_counts_now["cards"]
        or canonical_counts_now["milestones"] < legacy_counts_now["milestones"]
    ):
        sync_details = _backup_and_copy_file(
            legacy_db,
            canonical_db,
            backup_suffix=f".pre-sync-{now_slug}.bak",
        )
        sync_details["performed"] = True
    report["dbSync"] = sync_details

    cfg = _read_json(amphion_cfg) or _read_json(ops_cfg)
    cfg["commandDeckPath"] = ".amphion/command-deck"
    if "port" not in cfg:
        cfg["port"] = "8888"
    if "serverLang" not in cfg:
        cfg["serverLang"] = "python"
    _write_json(amphion_cfg, cfg)
    _write_json(ops_cfg, cfg)

    post = {
        "canonicalSqliteCounts": _sqlite_counts(canonical_db),
    }
    report["applied"] = True
    report["postflight"] = post
    report["verification"] = {
        "legacyMilestones": pre["legacySqliteCounts"]["milestones"],
        "canonicalMilestones": post["canonicalSqliteCounts"]["milestones"],
        "milestoneCountOk": post["canonicalSqliteCounts"]["milestones"] >= pre["legacySqliteCounts"]["milestones"],
        "legacyCards": pre["legacySqliteCounts"]["cards"],
        "canonicalCards": post["canonicalSqliteCounts"]["cards"],
        "cardCountOk": post["canonicalSqliteCounts"]["cards"] >= pre["legacySqliteCounts"]["cards"],
    }
    if not report["verification"]["cardCountOk"] or not report["verification"]["milestoneCountOk"]:
        report["ok"] = False
        report["reason"] = "count-regression"

    # Archive legacy scaffolding after successful migration verification.
    legacy_candidates = [
        root / "ops" / "launch-command-deck",
        root / "referenceDocs" / "06_AgentMemory",
        root / ".cursor",
        root / ".windsurf",
        root / ".clinerules",
        root / ".cursorrules",
        root / "CLAUDE.md",
    ]
    if report["ok"]:
        archive_result = _build_archive(root, archive_path, legacy_candidates, force=args.force_archive)
        report["archive"] = archive_result
        if not archive_result.get("ok"):
            report["ok"] = False
            report["reason"] = "archive-failed"
            report["cleanup"]["decision"] = "blocked"
    else:
        report["archive"] = {"ok": False, "reason": "verification-failed"}
        report["cleanup"]["decision"] = "blocked"

    # Guided cleanup recommendation (never automatic).
    cleanup_candidates = [
        root / "ops" / "launch-command-deck",
        root / "referenceDocs" / "06_AgentMemory",
    ]
    if report["ok"]:
        decision = "keep-for-now"
        if args.cleanup_action == "delete":
            decision = "delete-legacy-now"
        elif args.cleanup_action == "keep":
            decision = "keep-for-now"
        else:
            if args.yes:
                decision = "keep-for-now"
            elif sys.stdin.isatty():
                decision = _cleanup_decision_prompt()
            else:
                decision = "keep-for-now"

        report["cleanup"]["decision"] = decision
        report["cleanup"]["candidates"] = [str(p) for p in cleanup_candidates if p.exists()]
        report["cleanup"]["archivePath"] = report["archive"].get("path", "")

        if decision == "open-archive":
            archive_file = Path(str(report["archive"].get("path", "")))
            if archive_file.exists():
                if sys.platform == "darwin":
                    subprocess.run(["open", str(archive_file)], check=False)
                elif os.name == "nt":
                    os.startfile(str(archive_file))  # type: ignore[attr-defined]
            # Do not delete on open.
        elif decision == "review-paths":
            # No destructive action; list remains in report.
            pass
        elif decision == "delete-legacy-now":
            actions: List[Dict[str, Any]] = []
            for candidate in cleanup_candidates:
                actions.append(_delete_path(candidate))
            report["cleanup"]["actions"] = actions

    runbook_path = _write_restore_runbook(root)
    report["restoreRunbook"] = str(runbook_path)

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
