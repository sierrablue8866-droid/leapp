#!/usr/bin/env python3
"""Initialize Launch Command Deck state (SQLite) for a new project scaffold."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Dict, List, Tuple


def now_iso() -> str:
    return dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def new_id(prefix: str, seed: str = "") -> str:
    """Generate a stable ID if seed is provided, else fallback to random UUID."""
    if seed:
        h = hashlib.sha256(seed.encode()).hexdigest()
        return f"{prefix}_{h[:10]}"
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def board_status_lists(seed_base: str = "") -> List[Dict[str, Any]]:
    statuses = [
        ("backlog", "Backlog"),
        ("active", "In Progress"),
        ("blocked", "Blocked"),
        ("qa", "QA / Review"),
        ("done", "Done"),
    ]
    items = []
    for order, (key, title) in enumerate(statuses):
        items.append(
            {
                "id": new_id("list", f"{seed_base}_{key}"),
                "key": key,
                "title": title,
                "order": order,
            }
        )
    return items


def init_db(db_path: Path, project_name: str, codename: str, initial_version: str, milestone_title: str, seed_template: str, project_type: str = "standard") -> None:
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # 1. Create Tables
    c.executescript('''
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE TABLE IF NOT EXISTS boards (
            id TEXT PRIMARY KEY,
            name TEXT,
            codename TEXT,
            nextIssueNumber INTEGER,
            description TEXT,
            projectType TEXT,
            foundationPath TEXT,
            preflightLifecycleInitialized INTEGER DEFAULT 0,
            createdAt TEXT,
            updatedAt TEXT
        );

        CREATE TABLE IF NOT EXISTS lists (
            id TEXT PRIMARY KEY,
            boardId TEXT,
            key TEXT,
            title TEXT,
            listOrder INTEGER,
            createdAt TEXT,
            updatedAt TEXT
        );

        CREATE TABLE IF NOT EXISTS milestones (
            id TEXT PRIMARY KEY,
            boardId TEXT,
            code TEXT,
            title TEXT,
            msOrder INTEGER,
            kind TEXT DEFAULT 'standard',
            acceptsNewCards INTEGER DEFAULT 1,
            writeClosedAt TEXT DEFAULT '',
            archivedAt TEXT DEFAULT '',
            nextCardNumber INTEGER DEFAULT 1,
            createdAt TEXT,
            updatedAt TEXT
        );

        CREATE TABLE IF NOT EXISTS cards (
            id TEXT PRIMARY KEY,
            boardId TEXT,
            issueNumber TEXT,
            title TEXT,
            description TEXT,
            acceptance TEXT,
            milestoneId TEXT,
            listId TEXT,
            priority TEXT,
            owner TEXT,
            targetDate TEXT,
            cardOrder INTEGER,
            createdAt TEXT,
            updatedAt TEXT
        );
        
        CREATE TABLE IF NOT EXISTS charts (
            id TEXT PRIMARY KEY,
            boardId TEXT,
            title TEXT,
            description TEXT,
            markdown TEXT,
            createdAt TEXT,
            updatedAt TEXT
        );

        CREATE TABLE IF NOT EXISTS memory_events (
            id TEXT PRIMARY KEY,
            boardId TEXT,
            memoryKey TEXT,
            eventType TEXT,
            sourceType TEXT,
            attested INTEGER,
            bucket TEXT,
            value TEXT,
            tags TEXT,
            ttlSeconds INTEGER,
            sourceRef TEXT,
            createdAt TEXT
        );

        CREATE TABLE IF NOT EXISTS memory_objects (
            id TEXT PRIMARY KEY,
            boardId TEXT,
            memoryKey TEXT,
            bucket TEXT,
            value TEXT,
            tags TEXT,
            sourceType TEXT,
            isDeleted INTEGER,
            version INTEGER,
            lastEventId TEXT,
            createdAt TEXT,
            updatedAt TEXT,
            lastTouchedAt TEXT,
            expiresAt TEXT,
            UNIQUE(boardId, memoryKey)
        );

        CREATE TABLE IF NOT EXISTS milestone_artifacts (
            id TEXT PRIMARY KEY,
            boardId TEXT NOT NULL,
            milestoneId TEXT NOT NULL,
            artifactType TEXT NOT NULL CHECK (artifactType IN ('findings', 'outcomes')),
            revision INTEGER NOT NULL CHECK (revision > 0),
            title TEXT NOT NULL,
            summary TEXT NOT NULL DEFAULT '',
            body TEXT NOT NULL DEFAULT '',
            sourceCardId TEXT NOT NULL DEFAULT '',
            sourceEventId TEXT NOT NULL DEFAULT '',
            createdAt TEXT NOT NULL,
            updatedAt TEXT NOT NULL,
            UNIQUE(boardId, milestoneId, artifactType, revision)
        );

        CREATE TABLE IF NOT EXISTS board_artifacts (
            id TEXT PRIMARY KEY,
            boardId TEXT NOT NULL,
            artifactType TEXT NOT NULL CHECK (artifactType IN ('charter', 'prd', 'guardrails', 'playbook')),
            revision INTEGER NOT NULL CHECK (revision > 0),
            title TEXT NOT NULL,
            summary TEXT NOT NULL DEFAULT '',
            body TEXT NOT NULL DEFAULT '',
            sourceRef TEXT NOT NULL DEFAULT '',
            createdAt TEXT NOT NULL,
            updatedAt TEXT NOT NULL,
            UNIQUE(boardId, artifactType, revision)
        );

        CREATE INDEX IF NOT EXISTS idx_memory_events_board_created ON memory_events(boardId, createdAt);
        CREATE INDEX IF NOT EXISTS idx_memory_events_board_key ON memory_events(boardId, memoryKey);
        CREATE INDEX IF NOT EXISTS idx_memory_objects_board_updated ON memory_objects(boardId, updatedAt);
        CREATE INDEX IF NOT EXISTS idx_memory_objects_board_bucket ON memory_objects(boardId, bucket);
        CREATE INDEX IF NOT EXISTS idx_milestone_artifacts_lookup
            ON milestone_artifacts(boardId, milestoneId, artifactType, revision DESC);
        CREATE INDEX IF NOT EXISTS idx_milestone_artifacts_type_updated
            ON milestone_artifacts(artifactType, updatedAt DESC);
        CREATE INDEX IF NOT EXISTS idx_board_artifacts_lookup
            ON board_artifacts(boardId, artifactType, revision DESC);
        CREATE INDEX IF NOT EXISTS idx_board_artifacts_type_updated
            ON board_artifacts(artifactType, updatedAt DESC);
    ''')
    conn.commit()

    # 2. Setup Meta & Board
    board_seed = f"{codename}_{project_name}"
    board_id = new_id("board", board_seed)
    c.execute("INSERT INTO meta (key, value) VALUES (?, ?)", ("activeBoardId", board_id))
    c.execute("INSERT INTO meta (key, value) VALUES (?, ?)", ("version", "1"))

    now = now_iso()
    c.execute('''
        INSERT INTO boards (
            id, name, codename, nextIssueNumber, description, projectType, foundationPath, preflightLifecycleInitialized, createdAt, updatedAt
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
    ''', (
        board_id,
        f"{project_name} Launch Command Deck",
        codename.upper()[:3],
        1,
        f"Command deck for {project_name} ({codename}) using MCD protocol.",
        project_type,
        ".amphion/control-plane/foundation.json",
        now,
        now,
    ))

    # 2.5 Seed foundational board artifacts (DB-canonical docs)
    foundational_artifacts = [
        (
            "charter",
            f"Project Charter · {project_name}",
            "Initial charter placeholder. Update via board artifact API to establish canonical project charter.",
            (
                f"# Project Charter\n\n"
                f"Project: {project_name}\n"
                f"Codename: {codename.upper()[:3]}\n"
                f"Version: {initial_version}\n\n"
                "## Intent\n"
                "Define mission, constraints, and success criteria."
            ),
        ),
        (
            "prd",
            f"High-Level PRD · {project_name}",
            "Initial PRD placeholder. Update via board artifact API to establish canonical PRD.",
            (
                f"# High-Level PRD\n\n"
                f"Project: {project_name}\n\n"
                "## Scope\n"
                "Define high-level product requirements and acceptance goals."
            ),
        ),
        (
            "guardrails",
            f"Guardrails · {project_name}",
            "Canonical governance guardrails artifact (initial revision).",
            (
                "# Governance Guardrails\n\n"
                f"Codename: {codename}\n"
                f"Initial Version: {initial_version}\n\n"
                "Canonical lifecycle: Evaluate -> Contract -> Execute -> Closeout.\n\n"
                "Closeout is mandatory for release finalization and cannot be replaced by /remember."
            ),
        ),
        (
            "playbook",
            f"MCD Playbook · {project_name}",
            "Canonical playbook artifact (initial revision).",
            """# The Micro-Contract Development (MCD) Playbook: Operator's Guide

Welcome directly to the **Command Deck**. This platform operates on the Micro-Contract Development (MCD) methodology. MCD is designed for solo operators working alongside advanced AI agents in modern IDEs like Windsurf and Cursor.

The core philosophy is **Deterministic Versioning**: zero hallucination, zero scope creep, and total traceability. Every line of code written must be explicitly authorized by a text-based contract, and AI agents are structurally barred from chaining operations together without operator consent.

## The "Halt and Prompt" Safety Rail
The most critical rule of the MCD protocol is **Halt and Prompt**.
An AI agent executing a phase (like Evaluate or Contract) is strictly forbidden from automatically starting the next phase. Once a phase's outputs are generated, the agent MUST explicitly halt tool execution, present the results to the human Operator, and prompt the user for the next Slash Command. This prevents runaway agent logic and guarantees the human is always the supreme arbiter of state.

---

## The 4-Phase Sequence & IDE Slash Commands
To utilize the MCD protocol, the human Operator guides the AI through these discrete phases using explicit Slash Commands in the IDE chat interface:

### 1. `@[/evaluate]`
*Understand before building.*
- **Action**: Assess the current state of the application, read related documentation, and write a formal evaluation determining what needs to be built or fixed.
- **Output**: A milestone `findings` artifact written through `/api/milestones/{milestoneId}/artifacts` (DB canonical).
- **Rule**: Absolutely no project code is modified during Evaluation.

### 2. `@[/contract]`
*Authorize the work.*
- **Action**: Drafts binding contract scope and sequenced micro-contract cards in the Command Deck API-backed board runtime.
- **Output**: Milestone/card contract records with deterministic issue sequencing and acceptance criteria.
- **Rule**: The operator must grant approval before the agent proceeds to Execution.

### 3. `@[/execute]`
*Build to specification.*
- **Action**: The AI modifies the Approved File Paths (AFPs) exactly as defined in the active contract.
- **Rule**: If a roadblock occurs that requires changing the *scope* of the contract, the execute phase halts immediately. A new contract must be evaluated and authorized.

### 4. `@[/closeout]`
*Formalize the release.*
- **Action**: Verifies acceptance criteria, closes/archives the milestone, appends outcomes artifact, and commits code when applicable.
- **Output**:
  1. Outcomes artifact appended to milestone records in DB.
  2. Milestone archived/closed in board runtime.
  3. Updated DB-backed memory state via `/api/memory/*`.
  4. Strict `closeout: {description}` Git Commit.

---

## Utility Command: `@[/remember]`
`/remember` is a utility checkpoint, not a lifecycle phase.

- **Purpose**: Manually capture compact operational context into DB-backed memory authority (`amphion.db`) through `/api/memory/*`.
- **When to Use**:
  1. Long sessions where context continuity is at risk.
  2. Material scope shifts under approved contracts.
  3. Durable troubleshooting/architecture decisions worth preserving.
- **Mandatory Use**: At closeout completion for each completed version/slice.
- **Rule**: `/remember` does not auto-transition phases and does not authorize code changes by itself.

---

## Core Operational Rules (`GUARDRAILS.md`)
1. **Local Only**: MCD runs locally. No cloud dependencies or unprompted package manager usage.
2. **Mermaid.js Required**: All systemic architecture documents utilize Mermaid.js syntax for version-controllable diagrams.
3. **Immutability**: Once a contract is archived or a closeout record is spun down, it cannot be edited. Remediating errors requires an entirely fresh Evaluation -> Contract pipeline.
""",
        ),
    ]
    for artifact_type, title, summary, body in foundational_artifacts:
        c.execute(
            """
            INSERT OR IGNORE INTO board_artifacts (
                id, boardId, artifactType, revision, title, summary, body, sourceRef, createdAt, updatedAt
            ) VALUES (?, ?, ?, 1, ?, ?, ?, 'init_command_deck.py', ?, ?)
            """,
            (new_id("bfa", f"{board_seed}_{artifact_type}"), board_id, artifact_type, title, summary, body, now, now),
        )

    # 3. Setup Lists
    lists = board_status_lists(board_seed)
    list_id_by_key = {}
    for lst in lists:
        list_id_by_key[lst["key"]] = lst["id"]
        c.execute('''
            INSERT INTO lists (id, boardId, key, title, listOrder, createdAt, updatedAt)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (lst["id"], board_id, lst["key"], lst["title"], lst["order"], now, now))

    # 4. Setup Milestone
    milestone_id = new_id("ms", f"{board_seed}_{initial_version}")
    c.execute('''
        INSERT INTO milestones (
            id, boardId, code, title, msOrder, kind, acceptsNewCards, writeClosedAt, archivedAt, createdAt, updatedAt
        )
        VALUES (?, ?, ?, ?, ?, ?, 1, '', '', ?, ?)
    ''', (
        milestone_id,
        board_id,
        initial_version.lower().replace(".", "").replace("-", ""),
        milestone_title,
        0,
        "preflight",
        now,
        now,
    ))

    # 5. Setup Charts (Sample IA)
    chart_id = new_id("chart", f"{board_seed}_sample_ia")
    c.execute('''
        INSERT INTO charts (id, boardId, title, description, markdown, createdAt, updatedAt)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (chart_id, board_id, "Sample IA · Marketing Site", "Simple website structure example", "```mermaid\nflowchart TD\n  Home --> About\n  Home --> Blog\n  Home --> Contact\n```", now, now))

    # 6. Seed Cards
    next_issue_num = 1
    if seed_template == "scaffold":
        seed_cards = [
            (
                "active",
                f"{initial_version} - Scaffold Baseline",
                "P0",
                "Validate guardrails, canonical milestone, and startup flow for the new project.",
                "- MCD directories exist.\\n- GUARDRAILS.md is created.\\n- Launch Command Deck is reachable.",
            ),
            (
                "backlog",
                f"{initial_version} - Spec Lock: Charter & Non-Goals",
                "P0",
                "Ensure project strategy and Non-Goals are explicitly defined in the foundation.",
                "- Foundation JSON exists.\\n- Project Charter is locked.\\n- Non-goals are clearly delineated.",
            ),
            (
                "backlog",
                f"{initial_version} - Artifacts exist and are canonical",
                "P1",
                "Verify that High-Level PRD and derived artifacts are correctly populated and canonical.",
                "- High-Level PRD exists.\\n- Architecture examples are integrated.",
            ),
            (
                "backlog",
                f"{initial_version} - First Contract + Execute Slice",
                "P1",
                "Write first build contract and execute one deterministic slice end-to-end.",
                "- Contract is approved.\\n- Implementation validates against acceptance criteria.",
            ),
        ]
        
        for order, (list_key, title, priority, description, acceptance) in enumerate(seed_cards):
            card_id = new_id("card", f"{board_seed}_{title}")
            issue_num_str = f"{codename.upper()[:3]}-{next_issue_num:03d}"
            c.execute('''
                INSERT INTO cards (id, boardId, issueNumber, title, description, acceptance, milestoneId, listId, priority, owner, targetDate, cardOrder, createdAt, updatedAt)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (card_id, board_id, issue_num_str, title, description, acceptance, milestone_id, list_id_by_key[list_key], priority, "", "", order if list_key == "backlog" else 0, now, now))
            next_issue_num += 1
            
        c.execute("UPDATE boards SET nextIssueNumber = ? WHERE id = ?", (next_issue_num, board_id))

    conn.commit()
    conn.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Initialize Launch Command Deck (SQLite) for a project")
    parser.add_argument("--project-name", required=True, help="Project name")
    parser.add_argument("--codename", default="Genesis", help="Project codename")
    parser.add_argument("--initial-version", default="v0.01a", help="Initial project version")
    parser.add_argument("--milestone-title", default="Version 0a Pre-Release", help="Initial milestone title")
    parser.add_argument(
        "--seed-template",
        choices=["empty", "scaffold"],
        default="scaffold",
        help="Seed with starter cards or keep empty board",
    )
    parser.add_argument(
        "--type",
        default="standard",
        help="Project type (e.g., standard, content_pipeline, software_dev)",
    )
    parser.add_argument(
        "--db-file",
        default="",
        help="Override database path (defaults to deck_root/data/amphion.db)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    script_dir = Path(__file__).resolve().parent
    deck_root = script_dir.parent
    db_path = Path(args.db_file).expanduser().resolve() if args.db_file else (deck_root / "data" / "amphion.db")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Remove existing db if re-initializing
    if db_path.exists():
        db_path.unlink()

    init_db(
        db_path=db_path,
        project_name=args.project_name.strip(),
        codename=args.codename.strip(),
        initial_version=args.initial_version.strip(),
        milestone_title=args.milestone_title.strip(),
        seed_template=args.seed_template,
        project_type=args.type.strip(),
    )
    print(f"Initialized SQLite Launch Command Deck at {db_path}")


if __name__ == "__main__":
    main()
