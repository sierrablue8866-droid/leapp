#!/usr/bin/env python3
"""Launch Command Deck Kanban micro-service.

Local, SQLite-backed Kanban system with a minimal JSON API and static UI.
No external dependencies.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import mimetypes
import re
import subprocess
import threading
import uuid
import sqlite3
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, unquote, urlparse

BASE_DIR = Path(__file__).resolve().parent
PUBLIC_DIR = BASE_DIR / "public"
WORKSPACE_DIR = BASE_DIR.parent.parent
DATA_DIR = WORKSPACE_DIR / ".amphion" / "command-deck" / "data"
DB_FILE = DATA_DIR / "amphion.db"
LEGACY_STATE_FILE = DATA_DIR / "state.json"
CONTROL_PLANE_DIR = WORKSPACE_DIR / ".amphion" / "control-plane"
LEGACY_DOCS_DIR = WORKSPACE_DIR / "referenceDocs"
RUNTIME_SERVER = "launch-command-deck"
RUNTIME_IMPLEMENTATION = "python"
RUNTIME_DATASTORE = "sqlite"
RUNTIME_FINGERPRINT = f"{RUNTIME_SERVER}:{RUNTIME_IMPLEMENTATION}:{RUNTIME_DATASTORE}"


def now_iso() -> str:
    return dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def sort_by_order(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(items, key=lambda x: (x.get("order", 0), x.get("title", "")))


MERMAID_BLOCK_RE = re.compile(r"```mermaid\s*\n(?P<body>.*?)```", re.IGNORECASE | re.DOTALL)
FLOWCHART_START_RE = re.compile(r"^\s*(flowchart|graph)\b", re.IGNORECASE)
FLOWCHART_SKIP_RE = re.compile(
    r"^\s*(%%|subgraph\b|end\b|classDef\b|class\b|style\b|linkStyle\b|click\b)",
    re.IGNORECASE,
)
MERMAID_DIAGRAM_HEADERS = (
    "flowchart",
    "graph",
    "sequenceDiagram",
    "classDiagram",
    "stateDiagram",
    "erDiagram",
    "journey",
    "gantt",
    "pie",
    "gitGraph",
    "mindmap",
    "timeline",
    "quadrantChart",
    "requirementDiagram",
    "sankey-beta",
    "xychart-beta",
)
MERMAID_FENCED_BLOCK_ONLY_RE = re.compile(
    r"^\s*```mermaid\s*\n(?P<body>[\s\S]*?)\n?```\s*$",
    re.IGNORECASE,
)
MERMAID_RAW_HEADER_RE = re.compile(
    r"^\s*(?:" + "|".join(re.escape(header) for header in MERMAID_DIAGRAM_HEADERS) + r")\b",
    re.IGNORECASE,
)
CHART_MARKDOWN_ERROR = "markdown must be Mermaid chart content"
MILESTONE_KIND_STANDARD = "standard"
MILESTONE_KIND_PREFLIGHT = "preflight"
MILESTONE_REQUIRED_ERROR = "milestoneId is required. Add/select a milestone for new work."
MILESTONE_CLOSED_ERROR = "Pre-flight milestone is write-closed. Use an active milestone or create a new one."
MILESTONE_ARCHIVED_ERROR = "Milestone is archived. Restore it from Archives before assigning new work."
MILESTONE_TEXT_MAX_LEN = 10_000
MILESTONE_CODE_MAX_LEN = 64
MILESTONE_CODE_RE = re.compile(r"^[A-Z][A-Z0-9]*-\d+$")
MILESTONE_CODE_FROM_TITLE_RE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9]*-\d+)\b")
MILESTONE_METADATA_FIELDS = ("metaContract", "goals", "nonGoals", "risks")
ARTIFACT_ALLOWED_TYPES = {"findings", "outcomes"}
BOARD_ARTIFACT_ALLOWED_TYPES = {"charter", "prd", "guardrails", "playbook"}
ARTIFACT_TITLE_MAX_LEN = 280
ARTIFACT_SUMMARY_MAX_LEN = 4_000
ARTIFACT_BODY_MAX_LEN = 40_000
ARTIFACT_SOURCE_REF_MAX_LEN = 120
MERMAID_NODE_PATTERNS = [
    (re.compile(r"(?P<id>\b[A-Za-z_][\w-]*)\{\{\s*(?P<label>(?![\"']).*?)\s*\}\}"), "{id}{{{{{label}}}}}"),
    (re.compile(r"(?P<id>\b[A-Za-z_][\w-]*)\{(?!\{)\s*(?P<label>(?![\"']).*?)\s*\}"), "{id}{{{label}}}"),
    (re.compile(r"(?P<id>\b[A-Za-z_][\w-]*)\[\[\s*(?P<label>(?![\"']).*?)\s*\]\]"), "{id}[[{label}]]"),
    (re.compile(r"(?P<id>\b[A-Za-z_][\w-]*)\[(?!\[)\s*(?P<label>(?![\"']).*?)\s*\](?!\])"), "{id}[{label}]"),
    (re.compile(r"(?P<id>\b[A-Za-z_][\w-]*)\(\(\s*(?P<label>(?![\"']).*?)\s*\)\)"), "{id}(({label}))"),
    (re.compile(r"(?P<id>\b[A-Za-z_][\w-]*)\((?!\()\s*(?P<label>(?![\"']).*?)\s*\)(?!\))"), "{id}({label})"),
]


def _quote_mermaid_label(label: str) -> str:
    clean = label.strip()
    if len(clean) >= 2 and ((clean[0] == clean[-1] == '"') or (clean[0] == clean[-1] == "'")):
        clean = clean[1:-1]
    escaped = clean.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _sanitize_flowchart_line(line: str) -> str:
    result = line
    for pattern, template in MERMAID_NODE_PATTERNS:
        def _replace(match: re.Match[str]) -> str:
            quoted = _quote_mermaid_label(match.group("label"))
            return template.format(id=match.group("id"), label=quoted)
        result = pattern.sub(_replace, result)
    return result


def sanitize_mermaid_node_labels(markdown: str) -> str:
    """Normalize flowchart node labels to Mermaid-safe quoted form."""

    def _replace_block(match: re.Match[str]) -> str:
        body = match.group("body")
        lines = body.splitlines()
        in_flowchart = False
        changed = False
        updated_lines: List[str] = []

        for line in lines:
            stripped = line.strip()
            if FLOWCHART_START_RE.match(stripped):
                in_flowchart = True
                updated_lines.append(line)
                continue

            if not in_flowchart or FLOWCHART_SKIP_RE.match(stripped):
                updated_lines.append(line)
                continue

            safe_line = _sanitize_flowchart_line(line)
            if safe_line != line:
                changed = True
            updated_lines.append(safe_line)

        if not changed:
            return match.group(0)
        return "```mermaid\n" + "\n".join(updated_lines) + "\n```"

    return MERMAID_BLOCK_RE.sub(_replace_block, markdown)


def _normalize_mermaid_body(raw: str) -> str:
    trimmed = str(raw or "").strip()
    if not trimmed:
        return ""
    return "\n".join(line.rstrip() for line in trimmed.splitlines()).strip()


def _first_significant_mermaid_line(body: str) -> str:
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("%%"):
            continue
        return stripped
    return ""


def normalize_and_validate_mermaid(markdown: str) -> str:
    raw = str(markdown or "")
    if not raw.strip():
        raise ValueError(CHART_MARKDOWN_ERROR)

    fenced_match = MERMAID_FENCED_BLOCK_ONLY_RE.match(raw)
    if fenced_match:
        body = _normalize_mermaid_body(fenced_match.group("body"))
    else:
        body = _normalize_mermaid_body(raw)

    if not body:
        raise ValueError(CHART_MARKDOWN_ERROR)

    first_line = _first_significant_mermaid_line(body)
    if not first_line or not MERMAID_RAW_HEADER_RE.match(first_line):
        raise ValueError(CHART_MARKDOWN_ERROR)

    canonical = f"```mermaid\n{body}\n```"
    return sanitize_mermaid_node_labels(canonical)


def _coerce_milestone_text(value: Any, field_name: str) -> str:
    """Normalize milestone metadata fields into bounded text payloads."""
    if value is None:
        text = ""
    elif isinstance(value, str):
        text = value
    elif isinstance(value, (list, dict)):
        text = json.dumps(value, ensure_ascii=False)
    else:
        text = str(value)

    if len(text) > MILESTONE_TEXT_MAX_LEN:
        raise ValueError(f"{field_name} exceeds max length ({MILESTONE_TEXT_MAX_LEN})")
    return text


def _extract_milestone_code_from_title(title: Any) -> str:
    source = str(title or "").strip()
    if not source:
        return ""
    match = MILESTONE_CODE_FROM_TITLE_RE.match(source)
    if not match:
        return ""
    return str(match.group(1) or "").upper()


def _strip_milestone_code_prefix(title: str, code: str) -> str:
    source = str(title or "").strip()
    normalized_code = str(code or "").strip().upper()
    if not source or not normalized_code:
        return source
    pattern = re.compile(rf"^\s*{re.escape(normalized_code)}\s*[·:\-]\s*(.+?)\s*$", re.IGNORECASE)
    match = pattern.match(source)
    if not match:
        return source
    return str(match.group(1) or "").strip()


def _coerce_milestone_code(value: Any, title: Any = "") -> str:
    if value is None:
        raw = ""
    elif isinstance(value, str):
        raw = value.strip()
    else:
        raw = str(value).strip()

    if not raw:
        raw = _extract_milestone_code_from_title(title)
    if not raw:
        return ""

    normalized = raw.upper()
    if len(normalized) > MILESTONE_CODE_MAX_LEN:
        raise ValueError(f"code exceeds max length ({MILESTONE_CODE_MAX_LEN})")
    if not MILESTONE_CODE_RE.fullmatch(normalized):
        raise ValueError("code must match pattern [A-Z][A-Z0-9]*-<digits> (example: AMV2-005)")
    return normalized


def _coerce_artifact_type(value: Any) -> str:
    artifact_type = str(value or "").strip().lower()
    if artifact_type not in ARTIFACT_ALLOWED_TYPES:
        raise ValueError("artifactType must be one of: findings, outcomes")
    return artifact_type


def _coerce_board_artifact_type(value: Any) -> str:
    artifact_type = str(value or "").strip().lower()
    if artifact_type not in BOARD_ARTIFACT_ALLOWED_TYPES:
        raise ValueError("artifactType must be one of: charter, prd, guardrails, playbook")
    return artifact_type


def _coerce_artifact_text(value: Any, field_name: str, max_len: int, *, required: bool = False) -> str:
    if value is None:
        text = ""
    elif isinstance(value, str):
        text = value
    elif isinstance(value, (list, dict)):
        text = json.dumps(value, ensure_ascii=False)
    else:
        text = str(value)

    if required and not text.strip():
        raise ValueError(f"{field_name} is required")
    if len(text) > max_len:
        raise ValueError(f"{field_name} exceeds max length ({max_len})")
    return text


def _artifact_payload(row: Dict[str, Any], *, include_body: bool = False) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "id": str(row.get("id") or ""),
        "boardId": str(row.get("boardId") or ""),
        "milestoneId": str(row.get("milestoneId") or ""),
        "artifactType": str(row.get("artifactType") or ""),
        "revision": int(row.get("revision") or 0),
        "title": str(row.get("title") or ""),
        "summary": str(row.get("summary") or ""),
        "sourceCardId": str(row.get("sourceCardId") or ""),
        "sourceEventId": str(row.get("sourceEventId") or ""),
        "createdAt": str(row.get("createdAt") or ""),
        "updatedAt": str(row.get("updatedAt") or ""),
    }
    body = str(row.get("body") or "")
    if include_body:
        payload["body"] = body
    else:
        payload["bodyLength"] = len(body)
    return payload


def _board_artifact_payload(row: Dict[str, Any], *, include_body: bool = False) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "id": str(row.get("id") or ""),
        "boardId": str(row.get("boardId") or ""),
        "artifactType": str(row.get("artifactType") or ""),
        "revision": int(row.get("revision") or 0),
        "title": str(row.get("title") or ""),
        "summary": str(row.get("summary") or ""),
        "sourceRef": str(row.get("sourceRef") or ""),
        "createdAt": str(row.get("createdAt") or ""),
        "updatedAt": str(row.get("updatedAt") or ""),
    }
    body = str(row.get("body") or "")
    if include_body:
        payload["body"] = body
    else:
        payload["bodyLength"] = len(body)
    return payload


MEMORY_ALLOWED_SOURCES = {"user", "operator", "verified-system"}
MEMORY_ALLOWED_EVENT_TYPES = {"upsert", "delete", "touch"}
MEMORY_ALLOWED_BUCKETS = {"ct", "dec", "trb", "lrn", "nx", "ref", "misc"}
MEMORY_EXPORT_DIR = WORKSPACE_DIR / ".amphion" / "memory"


@dataclass(frozen=True)
class MemoryBudgets:
    max_objects: int = 300
    max_events: int = 2000
    max_object_bytes: int = 262_144
    max_event_bytes: int = 524_288

    @staticmethod
    def from_payload(payload: Dict[str, Any]) -> "MemoryBudgets":
        return MemoryBudgets(
            max_objects=_safe_int(payload.get("maxObjects"), 300, 25, 5000),
            max_events=_safe_int(payload.get("maxEvents"), 2000, 100, 20_000),
            max_object_bytes=_safe_int(payload.get("maxObjectBytes"), 262_144, 16_384, 8_388_608),
            max_event_bytes=_safe_int(payload.get("maxEventBytes"), 524_288, 32_768, 16_777_216),
        )


def _safe_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _json_dumps_compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _json_loads_safe(raw: str, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default


def _slugify_export_value(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("summary", "title", "text", "note", "value"):
            if key in value:
                return str(value[key])[:120]
        return _json_dumps_compact(value)[:120]
    if isinstance(value, list):
        return _json_dumps_compact(value)[:120]
    if value is None:
        return "null"
    return str(value)[:120]


def _resolve_board_id(cursor, requested: str) -> str:
    candidate = (requested or "").strip()
    if not candidate:
        cursor.execute("SELECT value FROM meta WHERE key='activeBoardId'")
        row = cursor.fetchone()
        candidate = row["value"] if row and row.get("value") else ""
    if not candidate:
        return ""
    cursor.execute("SELECT id FROM boards WHERE id=?", (candidate,))
    return candidate if cursor.fetchone() else ""


def _ensure_preflight_lifecycle(cursor, now: str) -> None:
    cursor.execute(
        "UPDATE milestones SET kind=? WHERE kind IS NULL OR TRIM(kind)=''",
        (MILESTONE_KIND_STANDARD,),
    )
    cursor.execute("UPDATE milestones SET acceptsNewCards=1 WHERE acceptsNewCards IS NULL")
    cursor.execute("UPDATE milestones SET writeClosedAt='' WHERE writeClosedAt IS NULL")
    cursor.execute("UPDATE milestones SET archivedAt='' WHERE archivedAt IS NULL")

    cursor.execute("SELECT id, preflightLifecycleInitialized FROM boards")
    boards = cursor.fetchall()
    for board in boards:
        board_id = str(board.get("id") or "")
        if not board_id:
            continue
        initialized = int(board.get("preflightLifecycleInitialized") or 0)
        cursor.execute(
            """
            SELECT id
            FROM milestones
            WHERE boardId=? AND kind=?
            ORDER BY msOrder ASC, id ASC
            LIMIT 1
            """,
            (board_id, MILESTONE_KIND_PREFLIGHT),
        )
        existing_preflight = cursor.fetchone()
        if existing_preflight:
            if initialized != 1:
                cursor.execute(
                    "UPDATE boards SET preflightLifecycleInitialized=1, updatedAt=? WHERE id=?",
                    (now, board_id),
                )
            continue
        if initialized == 1:
            continue
        cursor.execute(
            """
            SELECT id
            FROM milestones
            WHERE boardId=?
            ORDER BY msOrder ASC, id ASC
            LIMIT 1
            """,
            (board_id,),
        )
        first = cursor.fetchone()
        if not first:
            continue
        cursor.execute(
            "UPDATE milestones SET kind=?, updatedAt=? WHERE id=?",
            (MILESTONE_KIND_PREFLIGHT, now, first["id"]),
        )
        cursor.execute(
            "UPDATE boards SET preflightLifecycleInitialized=1, updatedAt=? WHERE id=?",
            (now, board_id),
        )


def _get_milestone(cursor, board_id: str, milestone_id: str) -> Optional[Dict[str, Any]]:
    cursor.execute("SELECT * FROM milestones WHERE id=? AND boardId=?", (milestone_id, board_id))
    return cursor.fetchone()


def _is_archived_milestone(milestone: Optional[Dict[str, Any]]) -> bool:
    if not milestone:
        return False
    return bool(str(milestone.get("archivedAt") or "").strip())


def _is_write_closed_preflight(milestone: Optional[Dict[str, Any]]) -> bool:
    if not milestone:
        return False
    kind = str(milestone.get("kind") or MILESTONE_KIND_STANDARD)
    accepts = int(milestone.get("acceptsNewCards") or 0)
    return kind == MILESTONE_KIND_PREFLIGHT and accepts != 1


def _is_complete_list_key(list_key: str) -> bool:
    key = str(list_key or "").strip().lower()
    return key in {"qa", "done"}


def _is_complete_list_id(cursor, board_id: str, list_id: str) -> bool:
    safe_board_id = str(board_id or "").strip()
    safe_list_id = str(list_id or "").strip()
    if not safe_board_id or not safe_list_id:
        return False
    cursor.execute("SELECT key FROM lists WHERE id=? AND boardId=?", (safe_list_id, safe_board_id))
    row = cursor.fetchone()
    if not row:
        return False
    return _is_complete_list_key(str(row.get("key") or ""))


def _is_completion_transition(cursor, board_id: str, old_list_id: str, new_list_id: str) -> bool:
    return (not _is_complete_list_id(cursor, board_id, old_list_id)) and _is_complete_list_id(
        cursor, board_id, new_list_id
    )


def _is_eval_card_title(title: Any) -> bool:
    text = str(title or "").strip()
    if not text:
        return False
    upper = text.upper()
    return bool(re.search(r"(?<!NON-)\bEVAL\b", upper))


def _build_eval_findings_artifact_payload(cursor, card: Dict[str, Any]) -> Optional[Dict[str, str]]:
    board_id = str(card.get("boardId") or "").strip()
    milestone_id = str(card.get("milestoneId") or "").strip()
    card_id = str(card.get("id") or "").strip()
    if not board_id or not milestone_id or not card_id:
        return None

    cursor.execute("SELECT * FROM milestones WHERE id=? AND boardId=?", (milestone_id, board_id))
    milestone = cursor.fetchone()
    if not milestone:
        return None

    issue_number = str(card.get("issueNumber") or "").strip()
    card_title = str(card.get("title") or "").strip() or "Evaluation Findings"
    card_header = f"{issue_number} · {card_title}" if issue_number else card_title

    description = str(card.get("description") or "").strip()
    acceptance = str(card.get("acceptance") or "").strip()
    if not description:
        description = "No description provided."
    if not acceptance:
        acceptance = "No acceptance criteria provided."

    cursor.execute("SELECT title, key FROM lists WHERE id=? AND boardId=?", (str(card.get("listId") or ""), board_id))
    list_row = cursor.fetchone() or {}
    status_title = str(list_row.get("title") or "Unknown Status")
    status_key = str(list_row.get("key") or "").strip().lower()
    completion_bucket = "Complete" if _is_complete_list_key(status_key) else "Incomplete"

    artifact_title = f"Findings · {card_header}"[:ARTIFACT_TITLE_MAX_LEN]
    summary_seed = str(card.get("description") or "").strip()
    if summary_seed:
        summary_seed = summary_seed.splitlines()[0]
    if not summary_seed:
        summary_seed = str(card.get("acceptance") or "").strip().splitlines()[0] if str(card.get("acceptance") or "").strip() else ""
    if not summary_seed:
        summary_seed = f"Findings captured from {card_header}"
    artifact_summary = summary_seed[:ARTIFACT_SUMMARY_MAX_LEN]

    artifact_body = (
        f"Evaluation Card: {card_header}\n"
        f"Milestone: {str(milestone.get('title') or '').strip()}\n"
        f"Status: {status_title}\n"
        f"Bucket: {completion_bucket}\n\n"
        f"Description:\n{description}\n\n"
        f"Acceptance:\n{acceptance}"
    )[:ARTIFACT_BODY_MAX_LEN]

    return {
        "boardId": board_id,
        "milestoneId": milestone_id,
        "title": artifact_title,
        "summary": artifact_summary,
        "body": artifact_body,
    }


def _append_findings_for_eval_completion(
    cursor,
    card: Dict[str, Any],
    now: str,
    source_event_id: str = "",
) -> bool:
    if not _is_eval_card_title(card.get("title")):
        return False

    payload = _build_eval_findings_artifact_payload(cursor, card)
    if not payload:
        return False

    board_id = payload["boardId"]
    milestone_id = payload["milestoneId"]
    card_id = str(card.get("id") or "")
    safe_source_event_id = str(source_event_id or "")[:ARTIFACT_SOURCE_REF_MAX_LEN]

    cursor.execute(
        """
        SELECT title, summary, body, sourceCardId
        FROM milestone_artifacts
        WHERE boardId=? AND milestoneId=? AND artifactType='findings' AND sourceCardId=?
        ORDER BY revision DESC, createdAt DESC
        LIMIT 1
        """,
        (board_id, milestone_id, card_id[:ARTIFACT_SOURCE_REF_MAX_LEN]),
    )
    latest = cursor.fetchone()
    if latest:
        same_payload = (
            str(latest.get("title") or "") == payload["title"]
            and str(latest.get("summary") or "") == payload["summary"]
            and str(latest.get("body") or "") == payload["body"]
            and str(latest.get("sourceCardId") or "") == card_id
        )
        if same_payload:
            return False

    cursor.execute(
        """
        SELECT COALESCE(MAX(revision), 0) + 1 AS nextRevision
        FROM milestone_artifacts
        WHERE boardId=? AND milestoneId=? AND artifactType='findings'
        """,
        (board_id, milestone_id),
    )
    revision_row = cursor.fetchone() or {}
    next_revision = int(revision_row.get("nextRevision") or 1)

    cursor.execute(
        """
        INSERT INTO milestone_artifacts (
            id, boardId, milestoneId, artifactType, revision,
            title, summary, body, sourceCardId, sourceEventId, createdAt, updatedAt
        ) VALUES (?, ?, ?, 'findings', ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            new_id("mfa"),
            board_id,
            milestone_id,
            next_revision,
            payload["title"],
            payload["summary"],
            payload["body"],
            card_id[:ARTIFACT_SOURCE_REF_MAX_LEN],
            safe_source_event_id,
            now,
            now,
        ),
    )
    return True


def _repair_amp007_findings_if_missing(cursor, now: str) -> bool:
    """Backfill a baseline findings artifact for AMP-007 when missing."""
    cursor.execute(
        """
        SELECT * FROM milestones
        WHERE title LIKE 'AMP-007%' AND title LIKE '%DB Canonical Lifecycle Contracts%'
        ORDER BY updatedAt DESC, createdAt DESC
        LIMIT 1
        """
    )
    milestone = cursor.fetchone()
    if not milestone:
        return False

    milestone_id = str(milestone.get("id") or "").strip()
    board_id = str(milestone.get("boardId") or "").strip()
    if not milestone_id or not board_id:
        return False

    cursor.execute(
        """
        SELECT id
        FROM milestone_artifacts
        WHERE boardId=? AND milestoneId=? AND artifactType='findings'
        LIMIT 1
        """,
        (board_id, milestone_id),
    )
    if cursor.fetchone():
        return False

    cursor.execute(
        """
        SELECT id, issueNumber, title
        FROM cards
        WHERE boardId=? AND milestoneId=?
        ORDER BY
            CASE WHEN issueNumber='AMP-044' THEN 0 ELSE 1 END,
            cardOrder ASC,
            updatedAt DESC,
            createdAt DESC
        LIMIT 1
        """,
        (board_id, milestone_id),
    )
    source_card = cursor.fetchone() or {}
    source_card_id = str(source_card.get("id") or "")[:ARTIFACT_SOURCE_REF_MAX_LEN]

    milestone_title = str(milestone.get("title") or "").strip() or "AMP-007"
    meta_contract = str(milestone.get("metaContract") or "").strip()
    goals = str(milestone.get("goals") or "").strip()
    non_goals = str(milestone.get("nonGoals") or "").strip()
    risks = str(milestone.get("risks") or "").strip()

    cursor.execute(
        """
        SELECT issueNumber, title
        FROM cards
        WHERE boardId=? AND milestoneId=?
        ORDER BY cardOrder ASC, updatedAt ASC, createdAt ASC
        """,
        (board_id, milestone_id),
    )
    card_rows = cursor.fetchall()
    card_lines = []
    for row in card_rows:
        issue = str(row.get("issueNumber") or "—").strip() or "—"
        title = str(row.get("title") or "").strip() or "Untitled Task"
        card_lines.append(f"- {issue} · {title}")
    if not card_lines:
        card_lines = ["- No milestone cards were available during repair."]

    summary_seed = meta_contract or f"{milestone_title} findings backfill baseline."
    artifact_summary = summary_seed[:ARTIFACT_SUMMARY_MAX_LEN]
    artifact_body = (
        "Recovered Findings Baseline:\n"
        f"- Milestone: {milestone_title}\n\n"
        "Meta Contract:\n"
        f"{meta_contract or 'No meta contract recorded.'}\n\n"
        "Goals:\n"
        f"{goals or 'No goals recorded.'}\n\n"
        "Non-Goals:\n"
        f"{non_goals or 'No non-goals recorded.'}\n\n"
        "Risks:\n"
        f"{risks or 'No risks recorded.'}\n\n"
        "Milestone Cards:\n"
        f"{chr(10).join(card_lines)}"
    )[:ARTIFACT_BODY_MAX_LEN]

    cursor.execute(
        """
        SELECT COALESCE(MAX(revision), 0) + 1 AS nextRevision
        FROM milestone_artifacts
        WHERE boardId=? AND milestoneId=? AND artifactType='findings'
        """,
        (board_id, milestone_id),
    )
    revision_row = cursor.fetchone() or {}
    next_revision = int(revision_row.get("nextRevision") or 1)

    cursor.execute(
        """
        INSERT INTO milestone_artifacts (
            id, boardId, milestoneId, artifactType, revision,
            title, summary, body, sourceCardId, sourceEventId, createdAt, updatedAt
        ) VALUES (?, ?, ?, 'findings', ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            new_id("mfa"),
            board_id,
            milestone_id,
            next_revision,
            "Findings · AMP-007 Backfill Baseline",
            artifact_summary,
            artifact_body,
            source_card_id,
            "amp-046-amp007-findings-repair-v1",
            now,
            now,
        ),
    )
    return True


def _format_outcomes_item_lines(items: List[str], empty_fallback: str) -> str:
    if not items:
        return f"- {empty_fallback}"
    return "\n".join(items[:20])


def _build_milestone_outcomes_payload(cursor, milestone: Dict[str, Any]) -> Optional[Dict[str, str]]:
    board_id = str(milestone.get("boardId") or "").strip()
    milestone_id = str(milestone.get("id") or "").strip()
    milestone_title = str(milestone.get("title") or "").strip() or "Untitled Milestone"
    if not board_id or not milestone_id:
        return None

    cursor.execute(
        """
        SELECT
            c.id,
            c.issueNumber,
            c.title,
            c.cardOrder,
            c.updatedAt,
            l.key AS listKey,
            l.title AS listTitle
        FROM cards c
        LEFT JOIN lists l ON l.id = c.listId
        WHERE c.boardId=? AND c.milestoneId=?
        ORDER BY c.cardOrder ASC, c.updatedAt ASC, c.id ASC
        """,
        (board_id, milestone_id),
    )
    rows = cursor.fetchall()

    completed_items: List[str] = []
    deferred_items: List[str] = []
    blocked_items: List[str] = []

    for row in rows:
        issue = str(row.get("issueNumber") or "—").strip() or "—"
        card_title = str(row.get("title") or "").strip() or "Untitled Task"
        status_key = str(row.get("listKey") or "").strip().lower()
        status_title = str(row.get("listTitle") or "").strip() or "Unknown Status"
        line = f"- {issue} · {card_title} ({status_title})"

        if _is_complete_list_key(status_key):
            completed_items.append(line)
        else:
            deferred_items.append(line)
            if status_key == "blocked":
                blocked_items.append(line)

    completed_count = len(completed_items)
    deferred_count = len(deferred_items)
    blocked_count = len(blocked_items)

    completed_section = _format_outcomes_item_lines(completed_items, "No tasks were completed at closeout.")
    deferred_section = _format_outcomes_item_lines(deferred_items, "No deferred tasks.")
    notable_section = _format_outcomes_item_lines(blocked_items, "No blocked tasks recorded at closeout.")

    if deferred_count > 0:
        deviation_line = f"- Milestone archived with {deferred_count} deferred task(s)."
        next_action_line = "- Re-route deferred tasks into an active milestone before finalizing release history."
    else:
        deviation_line = "- No closeout deviation recorded."
        next_action_line = "- Milestone can remain archived as historical record."

    body = (
        "Completed Scope:\n"
        f"{completed_section}\n\n"
        "Deferred Tasks:\n"
        f"{deferred_section}\n\n"
        "Notable Issues:\n"
        f"{notable_section}\n\n"
        "Deviations:\n"
        f"{deviation_line}\n\n"
        "Next Action:\n"
        f"{next_action_line}"
    )[:ARTIFACT_BODY_MAX_LEN]

    summary = (
        f"{completed_count} complete, {deferred_count} deferred, {blocked_count} blocked at closeout."
    )[:ARTIFACT_SUMMARY_MAX_LEN]
    title = f"Outcomes · {milestone_title} closeout"[:ARTIFACT_TITLE_MAX_LEN]

    return {
        "boardId": board_id,
        "milestoneId": milestone_id,
        "title": title,
        "summary": summary,
        "body": body,
    }


def _append_outcomes_for_milestone_closeout(
    cursor,
    milestone: Dict[str, Any],
    now: str,
    source_event_id: str = "",
) -> bool:
    payload = _build_milestone_outcomes_payload(cursor, milestone)
    if not payload:
        return False

    board_id = payload["boardId"]
    milestone_id = payload["milestoneId"]

    cursor.execute(
        """
        SELECT COALESCE(MAX(revision), 0) + 1 AS nextRevision
        FROM milestone_artifacts
        WHERE boardId=? AND milestoneId=? AND artifactType='outcomes'
        """,
        (board_id, milestone_id),
    )
    revision_row = cursor.fetchone() or {}
    next_revision = int(revision_row.get("nextRevision") or 1)

    cursor.execute(
        """
        INSERT INTO milestone_artifacts (
            id, boardId, milestoneId, artifactType, revision,
            title, summary, body, sourceCardId, sourceEventId, createdAt, updatedAt
        ) VALUES (?, ?, ?, 'outcomes', ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            new_id("mfa"),
            board_id,
            milestone_id,
            next_revision,
            payload["title"],
            payload["summary"],
            payload["body"],
            "",  # sourceCardId
            str(source_event_id or "")[:ARTIFACT_SOURCE_REF_MAX_LEN],
            now,
            now,
        ),
    )
    return True


def _done_list_ids(cursor, board_id: str) -> set[str]:
    cursor.execute("SELECT id FROM lists WHERE boardId=? AND key='done'", (board_id,))
    return {str(row.get("id") or "") for row in cursor.fetchall() if row.get("id")}


def _refresh_preflight_write_state(cursor, board_id: str, now: str) -> None:
    _ensure_preflight_lifecycle(cursor, now)
    done_list_ids = _done_list_ids(cursor, board_id)
    if not done_list_ids:
        return

    cursor.execute(
        "SELECT id, acceptsNewCards, archivedAt FROM milestones WHERE boardId=? AND kind=?",
        (board_id, MILESTONE_KIND_PREFLIGHT),
    )
    preflight_rows = cursor.fetchall()
    for milestone in preflight_rows:
        if _is_archived_milestone(milestone):
            continue
        if int(milestone.get("acceptsNewCards") or 0) != 1:
            continue
        milestone_id = str(milestone.get("id") or "")
        if not milestone_id:
            continue
        cursor.execute(
            "SELECT listId FROM cards WHERE boardId=? AND milestoneId=?",
            (board_id, milestone_id),
        )
        rows = cursor.fetchall()
        total_cards = len(rows)
        if total_cards == 0:
            continue
        if all(str(row.get("listId") or "") in done_list_ids for row in rows):
            cursor.execute(
                """
                UPDATE milestones
                SET acceptsNewCards=0,
                    writeClosedAt=COALESCE(NULLIF(writeClosedAt, ''), ?),
                    updatedAt=?
                WHERE id=?
                """,
                (now, now, milestone_id),
            )


def _memory_event_payload_bytes(row: Dict[str, Any]) -> int:
    return len(str(row.get("memoryKey") or "")) + len(str(row.get("value") or "")) + len(
        str(row.get("tags") or "")
    ) + len(str(row.get("sourceRef") or ""))


def _memory_object_payload_bytes(row: Dict[str, Any]) -> int:
    return len(str(row.get("memoryKey") or "")) + len(str(row.get("value") or "")) + len(
        str(row.get("tags") or "")
    )


def _memory_stats(cursor, board_id: str) -> Dict[str, int]:
    cursor.execute(
        """
        SELECT
            COUNT(*) AS eventCount,
            COALESCE(SUM(LENGTH(memoryKey) + LENGTH(COALESCE(value,'')) + LENGTH(COALESCE(tags,'')) + LENGTH(COALESCE(sourceRef,''))), 0) AS eventBytes
        FROM memory_events
        WHERE boardId=?
        """,
        (board_id,),
    )
    events = cursor.fetchone() or {}

    cursor.execute(
        """
        SELECT
            COUNT(*) AS objectCount,
            COALESCE(SUM(LENGTH(memoryKey) + LENGTH(COALESCE(value,'')) + LENGTH(COALESCE(tags,''))), 0) AS objectBytes
        FROM memory_objects
        WHERE boardId=? AND isDeleted=0
        """,
        (board_id,),
    )
    objects = cursor.fetchone() or {}

    return {
        "eventCount": int(events.get("eventCount") or 0),
        "eventBytes": int(events.get("eventBytes") or 0),
        "objectCount": int(objects.get("objectCount") or 0),
        "objectBytes": int(objects.get("objectBytes") or 0),
    }


def _memory_rows_to_payload(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    payload: List[Dict[str, Any]] = []
    for row in rows:
        tags = _json_loads_safe(str(row.get("tags") or "[]"), [])
        if not isinstance(tags, list):
            tags = []
        payload.append(
            {
                "id": row.get("id", ""),
                "boardId": row.get("boardId", ""),
                "memoryKey": row.get("memoryKey", ""),
                "bucket": row.get("bucket", "misc"),
                "value": _json_loads_safe(str(row.get("value") or "null"), None),
                "tags": [str(tag) for tag in tags if isinstance(tag, str)],
                "sourceType": row.get("sourceType", ""),
                "isDeleted": bool(row.get("isDeleted", 0)),
                "version": int(row.get("version") or 0),
                "createdAt": row.get("createdAt", ""),
                "updatedAt": row.get("updatedAt", ""),
                "lastTouchedAt": row.get("lastTouchedAt", ""),
                "expiresAt": row.get("expiresAt", ""),
                "lastEventId": row.get("lastEventId", ""),
            }
        )
    return payload


def _lww_wins(now: str, event_id: str, existing: Dict[str, Any]) -> bool:
    updated_at = str(existing.get("updatedAt") or "")
    prev_event = str(existing.get("lastEventId") or "")
    return now > updated_at or (now == updated_at and event_id > prev_event)


def _apply_memory_event(
    cursor,
    board_id: str,
    event_id: str,
    now: str,
    memory_key: str,
    event_type: str,
    source_type: str,
    bucket: str,
    value_json: str,
    tags_json: str,
    expires_at: Optional[str],
) -> bool:
    cursor.execute("SELECT * FROM memory_objects WHERE boardId=? AND memoryKey=?", (board_id, memory_key))
    existing = cursor.fetchone()

    if event_type == "touch" and (not existing or int(existing.get("isDeleted") or 0) == 1):
        return False

    if not existing:
        is_deleted = 1 if event_type == "delete" else 0
        cursor.execute(
            """
            INSERT INTO memory_objects (
                id, boardId, memoryKey, bucket, value, tags, sourceType, isDeleted,
                version, lastEventId, createdAt, updatedAt, lastTouchedAt, expiresAt
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_id("memobj"),
                board_id,
                memory_key,
                bucket,
                "null" if is_deleted else value_json,
                "[]" if is_deleted else tags_json,
                source_type,
                is_deleted,
                1,
                event_id,
                now,
                now,
                now,
                expires_at or "",
            ),
        )
        return True

    if not _lww_wins(now, event_id, existing):
        return False

    next_version = int(existing.get("version") or 0) + 1

    if event_type == "touch":
        cursor.execute(
            """
            UPDATE memory_objects
            SET sourceType=?, version=?, lastEventId=?, updatedAt=?, lastTouchedAt=?
            WHERE boardId=? AND memoryKey=?
            """,
            (source_type, next_version, event_id, now, now, board_id, memory_key),
        )
        return True

    is_deleted = 1 if event_type == "delete" else 0
    cursor.execute(
        """
        UPDATE memory_objects
        SET bucket=?, value=?, tags=?, sourceType=?, isDeleted=?, version=?, lastEventId=?, updatedAt=?, lastTouchedAt=?, expiresAt=?
        WHERE boardId=? AND memoryKey=?
        """,
        (
            bucket,
            "null" if is_deleted else value_json,
            "[]" if is_deleted else tags_json,
            source_type,
            is_deleted,
            next_version,
            event_id,
            now,
            now,
            expires_at or "",
            board_id,
            memory_key,
        ),
    )
    return True


def _compact_memory(cursor, board_id: str, now: str, budgets: MemoryBudgets) -> Dict[str, Any]:
    stats_before = _memory_stats(cursor, board_id)
    removed = {
        "expiredObjects": 0,
        "overflowObjects": 0,
        "objectBytesPruned": 0,
        "overflowEvents": 0,
        "eventBytesPruned": 0,
    }

    cursor.execute(
        "DELETE FROM memory_objects WHERE boardId=? AND expiresAt IS NOT NULL AND expiresAt != '' AND expiresAt <= ?",
        (board_id, now),
    )
    removed["expiredObjects"] += cursor.rowcount

    cursor.execute(
        "SELECT id FROM memory_objects WHERE boardId=? AND isDeleted=0 ORDER BY updatedAt DESC, memoryKey ASC, id DESC",
        (board_id,),
    )
    object_ids = [row["id"] for row in cursor.fetchall()]
    if len(object_ids) > budgets.max_objects:
        drop_ids = object_ids[budgets.max_objects :]
        cursor.executemany("DELETE FROM memory_objects WHERE id=?", [(obj_id,) for obj_id in drop_ids])
        removed["overflowObjects"] += len(drop_ids)

    stats_mid = _memory_stats(cursor, board_id)
    object_bytes = stats_mid["objectBytes"]
    while object_bytes > budgets.max_object_bytes:
        cursor.execute(
            """
            SELECT id, memoryKey, value, tags
            FROM memory_objects
            WHERE boardId=? AND isDeleted=0
            ORDER BY updatedAt ASC, memoryKey ASC, id ASC
            LIMIT 1
            """,
            (board_id,),
        )
        oldest = cursor.fetchone()
        if not oldest:
            break
        object_bytes -= _memory_object_payload_bytes(oldest)
        cursor.execute("DELETE FROM memory_objects WHERE id=?", (oldest["id"],))
        removed["objectBytesPruned"] += 1

    cursor.execute(
        "SELECT id FROM memory_events WHERE boardId=? ORDER BY createdAt DESC, id DESC",
        (board_id,),
    )
    event_ids = [row["id"] for row in cursor.fetchall()]
    if len(event_ids) > budgets.max_events:
        drop_ids = event_ids[budgets.max_events :]
        cursor.executemany("DELETE FROM memory_events WHERE id=?", [(event_id,) for event_id in drop_ids])
        removed["overflowEvents"] += len(drop_ids)

    stats_mid = _memory_stats(cursor, board_id)
    event_bytes = stats_mid["eventBytes"]
    while event_bytes > budgets.max_event_bytes:
        cursor.execute(
            """
            SELECT id, memoryKey, value, tags, sourceRef
            FROM memory_events
            WHERE boardId=?
            ORDER BY createdAt ASC, id ASC
            LIMIT 1
            """,
            (board_id,),
        )
        oldest = cursor.fetchone()
        if not oldest:
            break
        event_bytes -= _memory_event_payload_bytes(oldest)
        cursor.execute("DELETE FROM memory_events WHERE id=?", (oldest["id"],))
        removed["eventBytesPruned"] += 1

    stats_after = _memory_stats(cursor, board_id)
    return {
        "boardId": board_id,
        "budgets": {
            "maxObjects": budgets.max_objects,
            "maxEvents": budgets.max_events,
            "maxObjectBytes": budgets.max_object_bytes,
            "maxEventBytes": budgets.max_event_bytes,
        },
        "removed": removed,
        "before": stats_before,
        "after": stats_after,
    }


def _build_memory_projection(rows: List[Dict[str, Any]], board_id: str, now: str) -> Dict[str, Any]:
    buckets = {"ct": [], "dec": [], "trb": [], "lrn": [], "nx": [], "ref": []}
    for row in rows:
        bucket = str(row.get("bucket") or "dec")
        value = _json_loads_safe(str(row.get("value") or "null"), None)
        slug = f"{row.get('memoryKey', '')}:{_slugify_export_value(value)}".strip(":")
        if bucket not in buckets:
            bucket = "dec"
        if slug and slug not in buckets[bucket]:
            buckets[bucket].append(slug)

    for key in buckets:
        buckets[key] = buckets[key][:20]

    return {
        "v": 1,
        "upd": now,
        "cur": {
            "st": "memory-db",
            "ms": f"board:{board_id}",
            "ct": buckets["ct"],
            "dec": buckets["dec"],
            "trb": buckets["trb"],
            "lrn": buckets["lrn"],
            "nx": buckets["nx"],
            "ref": buckets["ref"],
        },
        "hist": [],
    }


def _export_memory_snapshot(cursor, board_id: str, export_path: Path, now: str) -> Dict[str, Any]:
    export_dir = MEMORY_EXPORT_DIR.resolve()
    export_target = export_path.resolve()
    if not str(export_target).startswith(str(export_dir)):
        raise ValueError(f"Export path must remain inside {export_dir}")

    cursor.execute(
        """
        SELECT * FROM memory_objects
        WHERE boardId=? AND isDeleted=0
        ORDER BY updatedAt DESC, memoryKey ASC
        LIMIT 500
        """,
        (board_id,),
    )
    rows = cursor.fetchall()
    payload = _build_memory_projection(rows, board_id, now)

    previous_cur = None
    if export_target.exists():
        try:
            previous = json.loads(export_target.read_text(encoding="utf-8"))
            previous_cur = previous.get("cur")
            previous_hist = previous.get("hist", [])
            if isinstance(previous_hist, list):
                payload["hist"] = [entry for entry in previous_hist if isinstance(entry, dict)][:3]
        except Exception:
            previous_cur = None

    if isinstance(previous_cur, dict):
        payload["hist"] = [previous_cur] + payload["hist"]
        payload["hist"] = payload["hist"][:3]

    export_target.parent.mkdir(parents=True, exist_ok=True)
    export_target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"path": str(export_target), "count": len(rows)}


def ensure_sqlite_schema(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = dict_factory
    try:
        now = now_iso()
        c = conn.cursor()
        c.executescript(
            """
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
                metaContract TEXT DEFAULT '',
                goals TEXT DEFAULT '',
                nonGoals TEXT DEFAULT '',
                risks TEXT DEFAULT '',
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
                kind TEXT DEFAULT 'task',
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

            CREATE INDEX IF NOT EXISTS idx_lists_board_order ON lists(boardId, listOrder);
            CREATE INDEX IF NOT EXISTS idx_cards_board_order ON cards(boardId, cardOrder);
            CREATE INDEX IF NOT EXISTS idx_cards_list_order ON cards(listId, cardOrder);
            CREATE INDEX IF NOT EXISTS idx_milestones_board_order ON milestones(boardId, msOrder);
            CREATE INDEX IF NOT EXISTS idx_charts_board_updated ON charts(boardId, updatedAt);
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
            """
        )
        c.execute("PRAGMA table_info(boards)")
        board_columns = {str(row.get("name") or "") for row in c.fetchall()}
        if "preflightLifecycleInitialized" not in board_columns:
            c.execute("ALTER TABLE boards ADD COLUMN preflightLifecycleInitialized INTEGER DEFAULT 0")

        c.execute("PRAGMA table_info(milestones)")
        milestone_columns = {str(row.get("name") or "") for row in c.fetchall()}
        if "kind" not in milestone_columns:
            c.execute("ALTER TABLE milestones ADD COLUMN kind TEXT DEFAULT 'standard'")
        if "acceptsNewCards" not in milestone_columns:
            c.execute("ALTER TABLE milestones ADD COLUMN acceptsNewCards INTEGER DEFAULT 1")
        if "writeClosedAt" not in milestone_columns:
            c.execute("ALTER TABLE milestones ADD COLUMN writeClosedAt TEXT DEFAULT ''")
        if "archivedAt" not in milestone_columns:
            c.execute("ALTER TABLE milestones ADD COLUMN archivedAt TEXT DEFAULT ''")
        if "metaContract" not in milestone_columns:
            c.execute("ALTER TABLE milestones ADD COLUMN metaContract TEXT DEFAULT ''")
        if "goals" not in milestone_columns:
            c.execute("ALTER TABLE milestones ADD COLUMN goals TEXT DEFAULT ''")
        if "nonGoals" not in milestone_columns:
            c.execute("ALTER TABLE milestones ADD COLUMN nonGoals TEXT DEFAULT ''")
        if "risks" not in milestone_columns:
            c.execute("ALTER TABLE milestones ADD COLUMN risks TEXT DEFAULT ''")
        if "nextCardNumber" not in milestone_columns:
            c.execute("ALTER TABLE milestones ADD COLUMN nextCardNumber INTEGER DEFAULT 1")
            c.execute(
                """
                UPDATE milestones SET nextCardNumber = 1 + COALESCE(
                    (SELECT MAX(CAST(SUBSTR(c.issueNumber, LENGTH(milestones.code) + 2) AS INTEGER))
                     FROM cards c
                     WHERE c.milestoneId = milestones.id
                       AND c.issueNumber GLOB milestones.code || '-[0-9][0-9][0-9]'),
                    0
                )
                """
            )
        c.execute("PRAGMA table_info(cards)")
        card_columns = {str(row.get("name") or "") for row in c.fetchall()}
        if "kind" not in card_columns:
            c.execute("ALTER TABLE cards ADD COLUMN kind TEXT DEFAULT 'task'")

        _ensure_preflight_lifecycle(c, now)
        _repair_amp007_findings_if_missing(c, now)

        c.execute("INSERT OR IGNORE INTO meta (key, value) VALUES ('version', '1')")
        c.execute("INSERT OR IGNORE INTO meta (key, value) VALUES ('activeBoardId', '')")
        c.execute(
            "INSERT OR IGNORE INTO meta (key, value) VALUES ('taskIssueNumberSchemeCutoff', ?)",
            (now,),
        )
        conn.commit()
    finally:
        conn.close()


def canonicalize_legacy_chart_rows(db_path: Path) -> int:
    conn = sqlite3.connect(db_path)
    try:
        c = conn.cursor()
        c.execute("SELECT id, markdown FROM charts")
        rows = c.fetchall()

        now = now_iso()
        updates = []
        for chart_id, markdown in rows:
            raw = str(markdown or "")
            try:
                canonical = normalize_and_validate_mermaid(raw)
            except ValueError:
                continue
            if canonical != raw:
                updates.append((canonical, now, chart_id))

        if updates:
            c.executemany("UPDATE charts SET markdown=?, updatedAt=? WHERE id=?", updates)
            conn.commit()
        return len(updates)
    finally:
        conn.close()


def canonical_playbook_markdown() -> str:
    return """# The Micro-Contract Development (MCD) Playbook: Operator's Guide

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
"""


FOUNDATIONAL_DOC_TYPES = ("charter", "prd", "guardrails")
FOUNDATIONAL_DOC_HEADERS = {
    "charter": "# Project Charter",
    "prd": "# High-Level PRD",
    "guardrails": "# Governance Guardrails",
}


def _needs_foundational_doc_newline_repair(artifact_type: str, body: str) -> bool:
    key = str(artifact_type or "").strip().lower()
    header = FOUNDATIONAL_DOC_HEADERS.get(key)
    if not header:
        return False
    text = str(body or "")
    if not text:
        return False
    if "\\n" not in text:
        return False
    # Only repair records that appear fully escaped to avoid mutating intentional snippets.
    if "\n" in text:
        return False
    return header in text


def _normalize_escaped_newlines(text: str) -> str:
    return str(text or "").replace("\\r\\n", "\n").replace("\\n", "\n")


def _ensure_guardrails_closeout_rule(body: str) -> str:
    text = str(body or "")
    if not text:
        return text
    if "### 4) Closeout" in text:
        return text

    closeout_block = (
        "### 4) Closeout\n"
        "- Closeout requires completed scope verification and outcomes recorded in DB.\n"
        "- `/closeout` is required to finalize a version; `/remember` cannot replace lifecycle closeout.\n\n"
    )
    if "## Utility Commands" in text:
        return text.replace("## Utility Commands", f"{closeout_block}## Utility Commands", 1)

    fallback_line = "Closeout is mandatory for release finalization and cannot be replaced by /remember."
    if fallback_line in text:
        return text
    return f"{text.rstrip()}\n\n{fallback_line}\n"


def repair_foundational_doc_artifacts_if_needed(db_path: Path) -> int:
    conn = sqlite3.connect(db_path)
    conn.row_factory = dict_factory
    try:
        c = conn.cursor()
        c.execute("SELECT id FROM boards")
        boards = c.fetchall()
        now = now_iso()
        repaired = 0

        for board in boards:
            board_id = str(board.get("id") or "").strip()
            if not board_id:
                continue
            for artifact_type in FOUNDATIONAL_DOC_TYPES:
                c.execute(
                    """
                    SELECT * FROM board_artifacts
                    WHERE boardId=? AND artifactType=?
                    ORDER BY revision DESC, createdAt DESC
                    LIMIT 1
                    """,
                    (board_id, artifact_type),
                )
                row = c.fetchone()
                if not row:
                    continue
                body = str(row.get("body") or "")
                repaired_body = body
                repair_notes: List[str] = []

                if _needs_foundational_doc_newline_repair(artifact_type, repaired_body):
                    normalized_body = _normalize_escaped_newlines(repaired_body)
                    if normalized_body != repaired_body:
                        repaired_body = normalized_body
                        repair_notes.append("newline normalization")

                if artifact_type == "guardrails":
                    guardrails_repaired = _ensure_guardrails_closeout_rule(repaired_body)
                    if guardrails_repaired != repaired_body:
                        repaired_body = guardrails_repaired
                        repair_notes.append("closeout phase rule")

                if repaired_body == body:
                    continue

                next_revision = int(row.get("revision") or 0) + 1
                title = str(row.get("title") or "")
                summary_seed = str(row.get("summary") or "").strip()
                repair_label = ", ".join(repair_notes) if repair_notes else "artifact"
                summary = (
                    f"{summary_seed} ({repair_label} repair)."
                    if summary_seed
                    else f"Canonical {repair_label} repair (auto-migration)."
                )
                c.execute(
                    """
                    INSERT INTO board_artifacts (
                        id, boardId, artifactType, revision, title, summary, body, sourceRef, createdAt, updatedAt
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'server-startup-repair', ?, ?)
                    """,
                    (new_id("bfa"), board_id, artifact_type, next_revision, title, summary, repaired_body, now, now),
                )
                repaired += 1

        if repaired:
            conn.commit()
        return repaired
    finally:
        conn.close()


def _is_stub_playbook_body(body: str) -> bool:
    text = str(body or "").strip()
    if not text:
        return True
    if "\\n" in text and "Use DB-backed milestone/card artifacts as canonical workflow authority." in text:
        return True
    if text == "# MCD Playbook\n\nUse DB-backed milestone/card artifacts as canonical workflow authority.":
        return True
    if "The Micro-Contract Development (MCD) Playbook: Operator's Guide" in text:
        return False
    return len(text) < 220 and "MCD Playbook" in text


def repair_playbook_artifacts_if_needed(db_path: Path) -> int:
    conn = sqlite3.connect(db_path)
    conn.row_factory = dict_factory
    try:
        c = conn.cursor()
        c.execute("SELECT id, name FROM boards")
        boards = c.fetchall()
        now = now_iso()
        canonical_body = canonical_playbook_markdown()
        repaired = 0

        for board in boards:
            board_id = str(board.get("id") or "")
            if not board_id:
                continue
            board_name = str(board.get("name") or "Project").strip()
            title = f"MCD Playbook · {board_name.replace(' Launch Command Deck', '').strip()}"
            c.execute(
                """
                SELECT * FROM board_artifacts
                WHERE boardId=? AND artifactType='playbook'
                ORDER BY revision DESC, createdAt DESC
                LIMIT 1
                """,
                (board_id,),
            )
            row = c.fetchone()
            if row:
                if not _is_stub_playbook_body(str(row.get("body") or "")):
                    continue
                next_revision = int(row.get("revision") or 0) + 1
                title = str(row.get("title") or title)
                summary = "Canonical playbook artifact repair (auto-migration)."
            else:
                next_revision = 1
                summary = "Canonical playbook artifact (auto-seeded repair)."

            c.execute(
                """
                INSERT INTO board_artifacts (
                    id, boardId, artifactType, revision, title, summary, body, sourceRef, createdAt, updatedAt
                ) VALUES (?, ?, 'playbook', ?, ?, ?, ?, 'server-startup-repair', ?, ?)
                """,
                (new_id("bfa"), board_id, next_revision, title, summary, canonical_body, now, now),
            )
            repaired += 1

        if repaired:
            conn.commit()
        return repaired
    finally:
        conn.close()


def backfill_milestone_codes_if_needed(db_path: Path) -> int:
    conn = sqlite3.connect(db_path)
    conn.row_factory = dict_factory
    try:
        c = conn.cursor()
        c.execute("SELECT id, code, title FROM milestones")
        rows = c.fetchall()
        now = now_iso()
        updates: List[tuple[str, str, str]] = []

        for row in rows:
            milestone_id = str(row.get("id") or "").strip()
            if not milestone_id:
                continue
            existing_code = str(row.get("code") or "").strip()
            if existing_code:
                continue
            extracted_code = _extract_milestone_code_from_title(row.get("title"))
            if not extracted_code:
                continue
            updates.append((extracted_code, now, milestone_id))

        if updates:
            c.executemany("UPDATE milestones SET code=?, updatedAt=? WHERE id=?", updates)
            conn.commit()
        return len(updates)
    finally:
        conn.close()


def migrate_legacy_state_json_to_sqlite(
    db_path: Path,
    state_path: Path,
    *,
    force: bool = False,
) -> Dict[str, Any]:
    report: Dict[str, Any] = {
        "ok": True,
        "stateFile": str(state_path),
        "force": bool(force),
        "applied": False,
        "reason": "",
        "counts": {
            "boards": 0,
            "lists": 0,
            "milestones": 0,
            "cards": 0,
            "charts": 0,
        },
    }
    if not state_path.exists():
        report["reason"] = "legacy state.json not found"
        return report

    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception as exc:
        report["ok"] = False
        report["reason"] = f"unable to parse state.json: {exc}"
        return report

    if not isinstance(payload, dict):
        report["reason"] = "legacy state payload is not an object"
        return report

    boards = payload.get("boards") or []
    if not isinstance(boards, list) or not boards:
        report["reason"] = "legacy state contains no boards"
        return report

    conn = sqlite3.connect(db_path)
    try:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM boards")
        existing_boards = int((c.fetchone() or [0])[0] or 0)
        if existing_boards > 0 and not force:
            report["reason"] = "sqlite already populated; migration skipped (use force to merge)"
            return report

        now = now_iso()
        for board in boards:
            if not isinstance(board, dict):
                continue
            board_id = str(board.get("id") or "").strip() or new_id("board")
            name = str(board.get("name") or "Migrated Board")
            codename = str(board.get("codename") or "AMP").strip().upper()[:6] or "AMP"
            next_issue = int(board.get("nextIssueNumber") or 1)
            description = str(board.get("description") or "")
            project_type = str(board.get("projectType") or "standard")
            created_at = str(board.get("createdAt") or now)
            updated_at = str(board.get("updatedAt") or now)
            foundation_path = str(board.get("foundationPath") or ".amphion/control-plane/foundation.json")
            preflight_init = int(board.get("preflightLifecycleInitialized") or 0)

            c.execute(
                """
                INSERT OR IGNORE INTO boards (
                    id, name, codename, nextIssueNumber, description, projectType,
                    foundationPath, preflightLifecycleInitialized, createdAt, updatedAt
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    board_id,
                    name,
                    codename,
                    next_issue,
                    description,
                    project_type,
                    foundation_path,
                    preflight_init,
                    created_at,
                    updated_at,
                ),
            )
            if c.rowcount:
                report["counts"]["boards"] += 1

            lists = board.get("lists") or []
            if isinstance(lists, list):
                for list_row in lists:
                    if not isinstance(list_row, dict):
                        continue
                    list_id = str(list_row.get("id") or "").strip() or new_id("list")
                    c.execute(
                        """
                        INSERT OR IGNORE INTO lists (
                            id, boardId, key, title, listOrder, createdAt, updatedAt
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            list_id,
                            board_id,
                            str(list_row.get("key") or "backlog"),
                            str(list_row.get("title") or "Backlog"),
                            int(list_row.get("order") if list_row.get("order") is not None else list_row.get("listOrder") or 0),
                            str(list_row.get("createdAt") or now),
                            str(list_row.get("updatedAt") or now),
                        ),
                    )
                    if c.rowcount:
                        report["counts"]["lists"] += 1

            milestones = board.get("milestones") or []
            if isinstance(milestones, list):
                for ms_row in milestones:
                    if not isinstance(ms_row, dict):
                        continue
                    ms_id = str(ms_row.get("id") or "").strip() or new_id("ms")
                    c.execute(
                        """
                        INSERT OR IGNORE INTO milestones (
                            id, boardId, code, title, msOrder, kind, acceptsNewCards, writeClosedAt,
                            archivedAt, metaContract, goals, nonGoals, risks, createdAt, updatedAt
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            ms_id,
                            board_id,
                            str(ms_row.get("code") or ""),
                            str(ms_row.get("title") or "Migrated Milestone"),
                            int(ms_row.get("order") if ms_row.get("order") is not None else ms_row.get("msOrder") or 0),
                            str(ms_row.get("kind") or MILESTONE_KIND_STANDARD),
                            int(ms_row.get("acceptsNewCards") if ms_row.get("acceptsNewCards") is not None else 1),
                            str(ms_row.get("writeClosedAt") or ""),
                            str(ms_row.get("archivedAt") or ""),
                            str(ms_row.get("metaContract") or ""),
                            str(ms_row.get("goals") or ""),
                            str(ms_row.get("nonGoals") or ""),
                            str(ms_row.get("risks") or ""),
                            str(ms_row.get("createdAt") or now),
                            str(ms_row.get("updatedAt") or now),
                        ),
                    )
                    if c.rowcount:
                        report["counts"]["milestones"] += 1

            cards = board.get("cards") or []
            if isinstance(cards, list):
                for card_row in cards:
                    if not isinstance(card_row, dict):
                        continue
                    card_id = str(card_row.get("id") or "").strip() or new_id("card")
                    c.execute(
                        """
                        INSERT OR IGNORE INTO cards (
                            id, boardId, issueNumber, title, description, acceptance, milestoneId, listId,
                            priority, owner, targetDate, cardOrder, createdAt, updatedAt
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            card_id,
                            board_id,
                            str(card_row.get("issueNumber") or ""),
                            str(card_row.get("title") or "Migrated Card"),
                            str(card_row.get("description") or ""),
                            str(card_row.get("acceptance") or ""),
                            str(card_row.get("milestoneId") or ""),
                            str(card_row.get("listId") or ""),
                            str(card_row.get("priority") or "P2"),
                            str(card_row.get("owner") or ""),
                            str(card_row.get("targetDate") or ""),
                            int(card_row.get("order") if card_row.get("order") is not None else card_row.get("cardOrder") or 0),
                            str(card_row.get("createdAt") or now),
                            str(card_row.get("updatedAt") or now),
                        ),
                    )
                    if c.rowcount:
                        report["counts"]["cards"] += 1

            charts = payload.get("charts") or []
            if isinstance(charts, list):
                for chart_row in charts:
                    if not isinstance(chart_row, dict):
                        continue
                    chart_id = str(chart_row.get("id") or "").strip() or new_id("chart")
                    c.execute(
                        """
                        INSERT OR IGNORE INTO charts (
                            id, boardId, title, description, markdown, createdAt, updatedAt
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            chart_id,
                            board_id,
                            str(chart_row.get("title") or "Migrated Chart"),
                            str(chart_row.get("description") or ""),
                            str(chart_row.get("markdown") or ""),
                            str(chart_row.get("createdAt") or now),
                            str(chart_row.get("updatedAt") or now),
                        ),
                    )
                    if c.rowcount:
                        report["counts"]["charts"] += 1

        active_board = str(payload.get("activeBoardId") or "").strip()
        if active_board:
            c.execute("UPDATE meta SET value=? WHERE key='activeBoardId'", (active_board,))
        conn.commit()
        report["applied"] = True
        report["reason"] = "legacy state migrated into sqlite"
        return report
    finally:
        conn.close()


def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d

class SQLiteStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._lock = threading.RLock()

    def get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = dict_factory
        return conn

    @staticmethod
    def _normalized_order(value: Any) -> int:
        if value is None:
            return 10_000_000
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return 10_000_000
            try:
                return int(stripped)
            except ValueError:
                return 10_000_000
        return 10_000_000

    @classmethod
    def _order_sort_key(cls, row: Dict[str, Any]) -> Tuple[int, str]:
        return (
            cls._normalized_order(row.get("order")),
            str(row.get("id") or ""),
        )

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            with self.get_conn() as conn:
                c = conn.cursor()
                
                c.execute("SELECT key, value FROM meta")
                meta = {r["key"]: r["value"] for r in c.fetchall()}
                
                c.execute("SELECT * FROM boards")
                boards = c.fetchall()
                
                c.execute("SELECT * FROM lists")
                lists = c.fetchall()
                
                c.execute("SELECT * FROM milestones")
                milestones = c.fetchall()
                
                c.execute("SELECT * FROM cards")
                cards = c.fetchall()
                
                c.execute("SELECT * FROM charts")
                charts = c.fetchall()

                c.execute("SELECT * FROM board_artifacts")
                board_artifacts = c.fetchall()

            lists_by_board = {}
            for l in lists:
                l["order"] = l.pop("listOrder", 0)
                lists_by_board.setdefault(l["boardId"], []).append(l)

            ms_by_board = {}
            for m in milestones:
                m["order"] = m.pop("msOrder", 0)
                ms_by_board.setdefault(m["boardId"], []).append(m)

            cards_by_board = {}
            for cd in cards:
                cd["order"] = cd.pop("cardOrder", 0)
                cards_by_board.setdefault(cd["boardId"], []).append(cd)

            artifacts_by_board = {}
            for art in board_artifacts:
                artifacts_by_board.setdefault(art["boardId"], []).append(art)

            for b in boards:
                b["lists"] = sorted(lists_by_board.get(b["id"], []), key=self._order_sort_key)
                b["milestones"] = sorted(ms_by_board.get(b["id"], []), key=self._order_sort_key)
                b["cards"] = sorted(cards_by_board.get(b["id"], []), key=self._order_sort_key)
                b["artifacts"] = sorted(
                    artifacts_by_board.get(b["id"], []),
                    key=lambda x: (x.get("artifactType", ""), -(x.get("revision") or 0)),
                )

            return {
                "version": meta.get("version", 1),
                "updatedAt": now_iso(),
                "activeBoardId": meta.get("activeBoardId", ""),
                "charts": charts,
                "boards": boards
            }


ensure_sqlite_schema(DB_FILE)
LEGACY_MIGRATION_REPORT = migrate_legacy_state_json_to_sqlite(DB_FILE, LEGACY_STATE_FILE, force=False)
CANONICALIZED_CHART_ROWS = canonicalize_legacy_chart_rows(DB_FILE)
FOUNDATIONAL_DOC_REPAIR_ROWS = repair_foundational_doc_artifacts_if_needed(DB_FILE)
PLAYBOOK_REPAIR_ROWS = repair_playbook_artifacts_if_needed(DB_FILE)
MILESTONE_CODE_REPAIR_ROWS = backfill_milestone_codes_if_needed(DB_FILE)
if CANONICALIZED_CHART_ROWS:
    print(f"[CommandDeck] Canonicalized {CANONICALIZED_CHART_ROWS} legacy chart row(s).")
if LEGACY_MIGRATION_REPORT.get("applied"):
    print("[CommandDeck] Legacy state.json migration applied.")
if FOUNDATIONAL_DOC_REPAIR_ROWS:
    print(f"[CommandDeck] Repaired {FOUNDATIONAL_DOC_REPAIR_ROWS} foundational board artifact(s).")
if PLAYBOOK_REPAIR_ROWS:
    print(f"[CommandDeck] Repaired playbook artifact for {PLAYBOOK_REPAIR_ROWS} board(s).")
if MILESTONE_CODE_REPAIR_ROWS:
    print(f"[CommandDeck] Backfilled milestone code for {MILESTONE_CODE_REPAIR_ROWS} milestone(s).")
STORE = SQLiteStore(DB_FILE)


class KanbanHandler(BaseHTTPRequestHandler):
    server_version = "LaunchCommandDeck/0.2"

    def log_message(self, format, *args):
        # Silence state polling to reduce terminal noise
        if len(args) > 0 and isinstance(args[0], str) and "/api/state/version" in args[0]:
            return
        super().log_message(format, *args)

    def _send_json(self, payload: Dict[str, Any], status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, message: str, status: int = HTTPStatus.BAD_REQUEST) -> None:
        self._send_json({"ok": False, "error": message}, status=status)

    def _read_json(self) -> Dict[str, Any]:
        try:
            raw_length = self.headers.get("Content-Length", "0")
            content_length = int(raw_length)
        except ValueError:
            raise ValueError("Invalid content length")
        if content_length == 0:
            return {}
        raw_body = self.rfile.read(content_length)
        try:
            body = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Malformed JSON: {exc}")
        if not isinstance(body, dict):
            raise ValueError("JSON body must be an object")
        return body

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Allow", "GET,POST,PATCH,DELETE,OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        route = parsed.path
        params = parse_qs(parsed.query)

        if route == "/api/health":
            self._send_json(
                {
                    "ok": True,
                    "time": now_iso(),
                    "runtime": {
                        "server": RUNTIME_SERVER,
                        "implementation": RUNTIME_IMPLEMENTATION,
                        "datastore": RUNTIME_DATASTORE,
                        "fingerprint": RUNTIME_FINGERPRINT,
                        "dbFile": DB_FILE.name,
                    },
                }
            )
            return

        if route == "/api/conventions":
            intent = (params.get("intent") or [""])[0].strip().lower()
            _MERMAID_VALID_TYPES = [
                "flowchart", "graph", "sequenceDiagram", "classDiagram",
                "stateDiagram", "erDiagram", "journey", "gantt", "pie",
                "gitGraph", "mindmap", "timeline", "quadrantChart",
                "requirementDiagram", "sankey-beta", "xychart-beta",
            ]
            _SCHEMAS = {
                "chart": {
                    "required": ["boardId", "title"],
                    "optional": ["markdown", "description"],
                    "mermaid": {
                        "validTypes": _MERMAID_VALID_TYPES,
                        "hint": "First non-comment line must begin with a valid diagram type. Fenced ```mermaid blocks accepted. Server normalizes to fenced form.",
                        "invalidResponse": "HTTP 422 — markdown must be Mermaid chart content",
                    },
                },
                "milestone": {
                    "required": ["boardId", "title"],
                    "optional": ["code", "metaContract", "goals", "nonGoals", "risks"],
                    "codePattern": "^[A-Z][A-Z0-9]*-\\d+$",
                    "codeMaxLength": MILESTONE_CODE_MAX_LEN,
                    "textFieldMaxLength": MILESTONE_TEXT_MAX_LEN,
                    "hint": "Supply code explicitly (e.g. AMV2-010). Server auto-extracts from title prefix if omitted.",
                },
                "card": {
                    "required": ["boardId", "milestoneId", "listId", "title"],
                    "optional": ["description", "acceptance", "priority", "owner", "targetDate", "kind"],
                    "issueNumber": "server-assigned — never supply",
                    "priorityValues": ["P0", "P1", "P2", "P3"],
                    "kindValues": ["task", "bug"],
                    "listKeys": ["backlog", "active", "blocked", "qa", "done"],
                    "hint": "Resolve listId from GET /api/find (preferred) or GET /api/state. issueNumber is always server-assigned. kind defaults to 'task'.",
                },
                "findings": {
                    "required": ["boardId", "artifactType", "title"],
                    "optional": ["summary", "body", "sourceCardId", "sourceEventId"],
                    "artifactType": "findings",
                    "limits": {"title": ARTIFACT_TITLE_MAX_LEN, "summary": ARTIFACT_SUMMARY_MAX_LEN, "body": ARTIFACT_BODY_MAX_LEN, "sourceRef": ARTIFACT_SOURCE_REF_MAX_LEN},
                    "immutable": True,
                    "hint": "POST only — no PATCH or DELETE. Each POST creates a new revision. Never supply id or revision.",
                },
                "outcomes": {
                    "required": ["boardId", "artifactType", "title"],
                    "optional": ["summary", "body", "sourceCardId", "sourceEventId"],
                    "artifactType": "outcomes",
                    "limits": {"title": ARTIFACT_TITLE_MAX_LEN, "summary": ARTIFACT_SUMMARY_MAX_LEN, "body": ARTIFACT_BODY_MAX_LEN, "sourceRef": ARTIFACT_SOURCE_REF_MAX_LEN},
                    "immutable": True,
                    "hint": "POST only — no PATCH or DELETE. Each POST creates a new revision. Never supply id or revision.",
                },
                "memory": {
                    "required": ["memoryKey", "value", "sourceType"],
                    "optional": ["boardId", "eventType", "bucket", "tags", "ttlSeconds", "sourceRef"],
                    "sourceType": list(MEMORY_ALLOWED_SOURCES),
                    "eventType": list(MEMORY_ALLOWED_EVENT_TYPES),
                    "bucket": list(MEMORY_ALLOWED_BUCKETS),
                    "bucketSemantics": {"ct": "context", "dec": "decisions", "trb": "troubleshooting", "lrn": "learnings", "nx": "next actions", "ref": "reference", "misc": "miscellaneous"},
                    "ttlSecondsMax": 31_536_000,
                    "hint": "Use sourceType: verified-system for deterministic agent writes. Default eventType is upsert.",
                },
                "board-artifact": {
                    "required": ["artifactType", "title"],
                    "optional": ["summary", "body", "sourceRef"],
                    "artifactType": list(BOARD_ARTIFACT_ALLOWED_TYPES),
                    "limits": {"title": ARTIFACT_TITLE_MAX_LEN, "summary": ARTIFACT_SUMMARY_MAX_LEN, "body": ARTIFACT_BODY_MAX_LEN},
                    "hint": "PATCH /api/boards/{id}/artifacts. Append-only revision model.",
                },
            }
            _OPERATIONS = [
                {"action": "Read state",       "method": "GET",    "route": "/api/state"},
                {"action": "Find (board map)",  "method": "GET",    "route": "/api/find",         "note": "Lean index — 87% smaller than /api/state. Add ?q=, ?milestoneId=, ?list= to filter"},
                {"action": "Conventions",      "method": "GET",    "route": "/api/conventions",  "note": "Add ?intent={type} for scoped schema"},
                {"action": "Create chart",     "method": "POST",   "route": "/api/charts",       "required": ["boardId", "title"], "optional": ["markdown", "description"]},
                {"action": "Update chart",     "method": "PATCH",  "route": "/api/charts/{id}",  "required": ["one of: title, description, markdown"]},
                {"action": "Delete chart",     "method": "DELETE", "route": "/api/charts/{id}"},
                {"action": "Create milestone", "method": "POST",   "route": "/api/milestones",   "required": ["boardId", "title", "code"]},
                {"action": "Create card",      "method": "POST",   "route": "/api/cards",        "required": ["boardId", "milestoneId", "listId", "title"]},
                {"action": "Move card",        "method": "POST",   "route": "/api/cards/{id}/move", "required": ["listId"]},
                {"action": "Write findings",   "method": "POST",   "route": "/api/milestones/{id}/artifacts", "required": ["boardId", "artifactType:findings", "title", "summary", "body"]},
                {"action": "Write outcomes",   "method": "POST",   "route": "/api/milestones/{id}/artifacts", "required": ["boardId", "artifactType:outcomes", "title", "summary", "body"]},
                {"action": "Write memory",     "method": "POST",   "route": "/api/memory/events", "required": ["memoryKey", "value", "sourceType"]},
                {"action": "Health check",     "method": "GET",    "route": "/api/health"},
            ]
            if intent and intent in _SCHEMAS:
                self._send_json({"ok": True, "intent": intent, "schema": _SCHEMAS[intent]})
            else:
                self._send_json({
                    "ok": True,
                    "conventions": {
                        "version": "1.0",
                        "enforcement": "All board CRUD operations must use this API. Direct SQLite writes, Python scripts, and filesystem substitutes are non-canonical per GUARDRAILS.",
                        "portResolution": "Read .amphion/config.json -> port. No fallback — config.json is the single source of truth.",
                        "rulesFiles": ["AGENTS.md", "CLAUDE.md", ".clinerules", ".cursorrules"],
                        "intents": list(_SCHEMAS.keys()),
                        "operations": _OPERATIONS,
                        "schemas": _SCHEMAS,
                    },
                })
            return

        if route == "/api/find":
            board_request = (params.get("boardId", [""])[0] or "").strip()
            q = (params.get("q", [""])[0] or "").strip().lower()
            milestone_filter = (params.get("milestoneId", [""])[0] or "").strip()
            list_filter = (params.get("list", [""])[0] or "").strip().lower()

            with STORE._lock:
                conn = STORE.get_conn()
                c = conn.cursor()
                try:
                    board_id = _resolve_board_id(c, board_request)
                    if not board_id:
                        self._send_error("Board not found", status=HTTPStatus.NOT_FOUND)
                        return

                    c.execute("SELECT key, value FROM meta")
                    meta = {r["key"]: r["value"] for r in c.fetchall()}
                    active_board_id = meta.get("activeBoardId", board_id)

                    c.execute("SELECT id, name, codename FROM boards WHERE id=?", (board_id,))
                    board_row = c.fetchone()

                    c.execute("SELECT id, key, title, listOrder FROM lists WHERE boardId=? ORDER BY listOrder ASC", (board_id,))
                    lists = c.fetchall()
                    list_id_to_key = {l["id"]: l["key"] for l in lists}

                    c.execute("SELECT id, code, title, archivedAt, msOrder FROM milestones WHERE boardId=? ORDER BY msOrder ASC", (board_id,))
                    milestones = c.fetchall()

                    c.execute("SELECT id, issueNumber, title, milestoneId, listId, priority, kind FROM cards WHERE boardId=? ORDER BY cardOrder ASC", (board_id,))
                    cards = c.fetchall()

                    c.execute("SELECT id, title FROM charts WHERE boardId=? ORDER BY createdAt DESC", (board_id,))
                    charts = c.fetchall()
                finally:
                    conn.close()

            card_counts: dict = {}
            for card in cards:
                mid = str(card["milestoneId"] or "")
                card_counts[mid] = card_counts.get(mid, 0) + 1

            lean_milestones = []
            for m in milestones:
                archived = bool(str(m["archivedAt"] or "").strip())
                code = str(m["code"] or "")
                title = str(m["title"] or "")
                if q and q not in code.lower() and q not in title.lower():
                    continue
                lean_milestones.append({
                    "id": m["id"],
                    "code": code,
                    "title": title,
                    "archived": archived,
                    "cardCount": card_counts.get(str(m["id"]), 0),
                })

            lean_cards = []
            for card in cards:
                issue = str(card["issueNumber"] or "")
                title = str(card["title"] or "")
                ms_id = str(card["milestoneId"] or "")
                list_id = str(card["listId"] or "")
                list_key = list_id_to_key.get(list_id, "")
                if q and q not in issue.lower() and q not in title.lower():
                    continue
                if milestone_filter and ms_id != milestone_filter:
                    continue
                if list_filter and list_key != list_filter:
                    continue
                lean_cards.append({
                    "id": card["id"],
                    "issueNumber": issue,
                    "title": title,
                    "milestoneId": ms_id,
                    "listKey": list_key,
                    "priority": str(card["priority"] or "P2"),
                    "kind": str(card["kind"] or "task"),
                })

            lean_board = {
                "id": board_row["id"] if board_row else board_id,
                "name": board_row["name"] if board_row else "",
                "codename": board_row["codename"] if board_row else "",
                "lists": [{"id": l["id"], "key": l["key"], "title": l["title"]} for l in lists],
                "milestones": lean_milestones,
                "cards": lean_cards,
                "charts": [{"id": ch["id"], "title": ch["title"]} for ch in charts],
            }

            self._send_json({
                "ok": True,
                "activeBoardId": active_board_id,
                "query": {"q": q, "milestoneId": milestone_filter, "list": list_filter, "boardId": board_id},
                "boards": [lean_board],
            })
            return

        if route == "/api/state":
            self._send_json({"ok": True, "state": STORE.snapshot()})
            return

        if route == "/api/state/version":
            with STORE._lock:
                version = DB_FILE.stat().st_mtime if DB_FILE.exists() else 0
            self._send_json({"ok": True, "version": version})
            return

        if route == "/api/migration/legacy-state-json/status":
            self._send_json({"ok": True, "migration": LEGACY_MIGRATION_REPORT})
            return

        if route.startswith("/api/boards/") and "/artifacts" in route:
            parts = route.split("/")
            if len(parts) >= 5 and parts[4] == "artifacts":
                board_id = (parts[3] or "").strip()
                if not board_id:
                    self._send_error("boardId is required")
                    return

                with STORE._lock:
                    conn = STORE.get_conn()
                    c = conn.cursor()
                    try:
                        c.execute("SELECT id FROM boards WHERE id=?", (board_id,))
                        if not c.fetchone():
                            self._send_error("Board not found", status=HTTPStatus.NOT_FOUND)
                            return

                        if len(parts) == 5:
                            artifact_type_raw = (params.get("artifactType", [""])[0] or "").strip()
                            artifact_type = ""
                            if artifact_type_raw:
                                try:
                                    artifact_type = _coerce_board_artifact_type(artifact_type_raw)
                                except ValueError as exc:
                                    self._send_error(str(exc), status=HTTPStatus.UNPROCESSABLE_ENTITY)
                                    return

                            if artifact_type:
                                c.execute(
                                    """
                                    SELECT * FROM board_artifacts
                                    WHERE boardId=? AND artifactType=?
                                    ORDER BY revision DESC, createdAt DESC
                                    """,
                                    (board_id, artifact_type),
                                )
                            else:
                                c.execute(
                                    """
                                    SELECT * FROM board_artifacts
                                    WHERE boardId=?
                                    ORDER BY artifactType ASC, revision DESC, createdAt DESC
                                    """,
                                    (board_id,),
                                )
                            rows = c.fetchall()
                            self._send_json(
                                {
                                    "ok": True,
                                    "boardId": board_id,
                                    "artifactType": artifact_type,
                                    "count": len(rows),
                                    "artifacts": [_board_artifact_payload(row, include_body=False) for row in rows],
                                }
                            )
                            return

                        if len(parts) == 6 and parts[5] == "latest":
                            artifact_type_raw = (params.get("artifactType", [""])[0] or "").strip()
                            if not artifact_type_raw:
                                self._send_error("artifactType query parameter is required")
                                return
                            try:
                                artifact_type = _coerce_board_artifact_type(artifact_type_raw)
                            except ValueError as exc:
                                self._send_error(str(exc), status=HTTPStatus.UNPROCESSABLE_ENTITY)
                                return

                            c.execute(
                                """
                                SELECT * FROM board_artifacts
                                WHERE boardId=? AND artifactType=?
                                ORDER BY revision DESC, createdAt DESC
                                LIMIT 1
                                """,
                                (board_id, artifact_type),
                            )
                            row = c.fetchone()
                            if not row:
                                self._send_error("Artifact not found", status=HTTPStatus.NOT_FOUND)
                                return
                            self._send_json({"ok": True, "artifact": _board_artifact_payload(row, include_body=True)})
                            return
                    finally:
                        conn.close()

        if route.startswith("/api/milestones/") and "/artifacts" in route:
            parts = route.split("/")
            if len(parts) >= 5 and parts[4] == "artifacts":
                milestone_id = (parts[3] or "").strip()
                if not milestone_id:
                    self._send_error("milestoneId is required")
                    return

                with STORE._lock:
                    conn = STORE.get_conn()
                    c = conn.cursor()
                    try:
                        c.execute("SELECT id FROM milestones WHERE id=?", (milestone_id,))
                        if not c.fetchone():
                            self._send_error("Milestone not found", status=HTTPStatus.NOT_FOUND)
                            return

                        if len(parts) == 5:
                            artifact_type_raw = (params.get("artifactType", [""])[0] or "").strip()
                            artifact_type = ""
                            if artifact_type_raw:
                                try:
                                    artifact_type = _coerce_artifact_type(artifact_type_raw)
                                except ValueError as exc:
                                    self._send_error(str(exc), status=HTTPStatus.UNPROCESSABLE_ENTITY)
                                    return

                            if artifact_type:
                                c.execute(
                                    """
                                    SELECT * FROM milestone_artifacts
                                    WHERE milestoneId=? AND artifactType=?
                                    ORDER BY revision DESC, createdAt DESC
                                    """,
                                    (milestone_id, artifact_type),
                                )
                            else:
                                c.execute(
                                    """
                                    SELECT * FROM milestone_artifacts
                                    WHERE milestoneId=?
                                    ORDER BY artifactType ASC, revision DESC, createdAt DESC
                                    """,
                                    (milestone_id,),
                                )
                            rows = c.fetchall()
                            self._send_json(
                                {
                                    "ok": True,
                                    "milestoneId": milestone_id,
                                    "artifactType": artifact_type,
                                    "count": len(rows),
                                    "artifacts": [_artifact_payload(row, include_body=False) for row in rows],
                                }
                            )
                            return

                        if len(parts) == 6 and parts[5] == "latest":
                            artifact_type_raw = (params.get("artifactType", [""])[0] or "").strip()
                            if not artifact_type_raw:
                                self._send_error("artifactType query parameter is required")
                                return
                            try:
                                artifact_type = _coerce_artifact_type(artifact_type_raw)
                            except ValueError as exc:
                                self._send_error(str(exc), status=HTTPStatus.UNPROCESSABLE_ENTITY)
                                return

                            c.execute(
                                """
                                SELECT * FROM milestone_artifacts
                                WHERE milestoneId=? AND artifactType=?
                                ORDER BY revision DESC, createdAt DESC
                                LIMIT 1
                                """,
                                (milestone_id, artifact_type),
                            )
                            row = c.fetchone()
                            if not row:
                                self._send_error("Artifact not found", status=HTTPStatus.NOT_FOUND)
                                return
                            self._send_json({"ok": True, "artifact": _artifact_payload(row, include_body=True)})
                            return

                        if len(parts) == 6:
                            artifact_id = (parts[5] or "").strip()
                            if not artifact_id:
                                self._send_error("artifactId is required")
                                return
                            c.execute(
                                "SELECT * FROM milestone_artifacts WHERE id=? AND milestoneId=?",
                                (artifact_id, milestone_id),
                            )
                            row = c.fetchone()
                            if not row:
                                self._send_error("Artifact not found", status=HTTPStatus.NOT_FOUND)
                                return
                            self._send_json({"ok": True, "artifact": _artifact_payload(row, include_body=True)})
                            return
                    finally:
                        conn.close()

        if route == "/api/memory/state":
            board_request = (params.get("boardId", [""])[0] or "").strip()
            include_deleted = (params.get("includeDeleted", ["0"])[0] or "").strip().lower() in {"1", "true", "yes"}
            limit = _safe_int(params.get("limit", ["200"])[0], 200, 1, 1000)

            with STORE._lock:
                conn = STORE.get_conn()
                c = conn.cursor()
                try:
                    board_id = _resolve_board_id(c, board_request)
                    if not board_id:
                        self._send_error("Board not found", status=HTTPStatus.NOT_FOUND)
                        return

                    c.execute(
                        f"SELECT * FROM memory_objects WHERE boardId=? {'AND isDeleted=0' if not include_deleted else ''} ORDER BY updatedAt DESC, memoryKey ASC LIMIT ?",  # nosec B608
                        (*query_args, limit),
                    )
                    rows = c.fetchall()
                    stats = _memory_stats(c, board_id)
                finally:
                    conn.close()

            self._send_json(
                {
                    "ok": True,
                    "memory": {
                        "boardId": board_id,
                        "objects": _memory_rows_to_payload(rows),
                        "stats": stats,
                        "limit": limit,
                        "includeDeleted": include_deleted,
                    },
                }
            )
            return

        if route == "/api/memory/query":
            board_request = (params.get("boardId", [""])[0] or "").strip()
            search = (params.get("q", [""])[0] or "").strip()
            source_type = (params.get("sourceType", [""])[0] or "").strip().lower()
            bucket = (params.get("bucket", [""])[0] or "").strip().lower()
            tag = (params.get("tag", [""])[0] or "").strip()
            limit = _safe_int(params.get("limit", ["50"])[0], 50, 1, 500)

            with STORE._lock:
                conn = STORE.get_conn()
                c = conn.cursor()
                try:
                    board_id = _resolve_board_id(c, board_request)
                    if not board_id:
                        self._send_error("Board not found", status=HTTPStatus.NOT_FOUND)
                        return

                    sql = "SELECT * FROM memory_objects WHERE boardId=? AND isDeleted=0"
                    query_args: List[Any] = [board_id]

                    if source_type:
                        sql += " AND sourceType=?"
                        query_args.append(source_type)

                    if bucket:
                        sql += " AND bucket=?"
                        query_args.append(bucket)

                    if search:
                        like = f"%{search}%"
                        sql += " AND (memoryKey LIKE ? OR value LIKE ? OR tags LIKE ?)"
                        query_args.extend([like, like, like])

                    sql += " ORDER BY updatedAt DESC, memoryKey ASC LIMIT ?"
                    query_args.append(max(limit, 200))
                    c.execute(sql, tuple(query_args))
                    rows = c.fetchall()
                finally:
                    conn.close()

            candidates = _memory_rows_to_payload(rows)
            if tag:
                candidates = [row for row in candidates if tag in row.get("tags", [])]
            matches = candidates[:limit]

            self._send_json(
                {
                    "ok": True,
                    "memory": {
                        "boardId": board_id,
                        "query": {
                            "q": search,
                            "sourceType": source_type,
                            "bucket": bucket,
                            "tag": tag,
                            "limit": limit,
                        },
                        "matches": matches,
                        "count": len(matches),
                    },
                }
            )
            return

        if route.startswith("/api/docs/"):
            doc_id = route.split("/")[-1]
            try:
                content = ""
                if doc_id in BOARD_ARTIFACT_ALLOWED_TYPES:
                    with STORE._lock:
                        conn = STORE.get_conn()
                        c = conn.cursor()
                        try:
                            board_id = _resolve_board_id(c, "")
                            if board_id:
                                c.execute(
                                    """
                                    SELECT body FROM board_artifacts
                                    WHERE boardId=? AND artifactType=?
                                    ORDER BY revision DESC, createdAt DESC
                                    LIMIT 1
                                    """,
                                    (board_id, doc_id),
                                )
                                row = c.fetchone()
                                if row:
                                    content = str(row.get("body") or "")
                        finally:
                            conn.close()
                    if content:
                        self._send_json({"ok": True, "content": content})
                        return

                if doc_id == "contract":
                    with STORE._lock:
                        conn = STORE.get_conn()
                        c = conn.cursor()
                        try:
                            board_id = _resolve_board_id(c, "")
                            if not board_id:
                                self._send_json({"ok": True, "content": "*No active board context found.*"})
                                return

                            c.execute(
                                """
                                SELECT * FROM milestones
                                WHERE boardId=? AND archivedAt=''
                                ORDER BY updatedAt DESC, createdAt DESC
                                LIMIT 1
                                """,
                                (board_id,),
                            )
                            milestone = c.fetchone()
                            if not milestone:
                                self._send_json(
                                    {
                                        "ok": True,
                                        "content": (
                                            "# Contract (DB Canonical)\n\n"
                                            "No active milestone contracts are currently recorded on the board."
                                        ),
                                    }
                                )
                                return

                            milestone_id = str(milestone.get("id") or "")
                            milestone_title = str(milestone.get("title") or "Untitled Milestone")
                            meta_contract = str(milestone.get("metaContract") or "").strip() or "_Not set._"
                            goals = str(milestone.get("goals") or "").strip() or "_Not set._"
                            non_goals = str(milestone.get("nonGoals") or "").strip() or "_Not set._"
                            risks = str(milestone.get("risks") or "").strip() or "_Not set._"

                            c.execute(
                                """
                                SELECT issueNumber, title, acceptance, priority
                                FROM cards
                                WHERE boardId=? AND milestoneId=?
                                ORDER BY cardOrder ASC, updatedAt ASC, createdAt ASC
                                """,
                                (board_id, milestone_id),
                            )
                            cards = c.fetchall()

                            card_lines = []
                            for row in cards:
                                issue = str(row.get("issueNumber") or "").strip() or "(unissued)"
                                title = str(row.get("title") or "").strip() or "Untitled card"
                                priority = str(row.get("priority") or "").strip() or "P2"
                                card_lines.append(f"- `{issue}` [{priority}] {title}")
                            if not card_lines:
                                card_lines = ["- No milestone-bound contract cards recorded."]

                            content = (
                                "# Contract (DB Canonical)\n\n"
                                f"- Milestone: `{milestone_id}` · {milestone_title}\n"
                                "- Authority: Board milestone metadata + milestone-bound cards (SQLite/API)\n\n"
                                "## Macro Contract\n"
                                f"{meta_contract}\n\n"
                                "## Goals\n"
                                f"{goals}\n\n"
                                "## Non-Goals\n"
                                f"{non_goals}\n\n"
                                "## Risks\n"
                                f"{risks}\n\n"
                                "## Micro-Contract Cards\n"
                                f"{chr(10).join(card_lines)}\n"
                            )
                            self._send_json({"ok": True, "content": content})
                            return
                        finally:
                            conn.close()

                path = None
                if doc_id == "charter":
                    files = sorted(CONTROL_PLANE_DIR.glob("*PROJECT_CHARTER.md"), reverse=True)
                    path = files[0] if files else CONTROL_PLANE_DIR / "PROJECT_CHARTER.md"
                elif doc_id == "prd":
                    files = sorted(CONTROL_PLANE_DIR.glob("*HIGH_LEVEL_PRD.md"), reverse=True)
                    path = files[0] if files else CONTROL_PLANE_DIR / "HIGH_LEVEL_PRD.md"
                elif doc_id == "guardrails":
                    path = CONTROL_PLANE_DIR / "GUARDRAILS.md"
                elif doc_id == "playbook":
                    path = CONTROL_PLANE_DIR / "MCD_PLAYBOOK.md"
                else:
                    self._send_error("Unknown doc")
                    return

                if not path.exists():
                    content = "*Not generated or not found in DB/control-plane.*"
                else:
                    content = path.read_text(encoding="utf-8")
                self._send_json({"ok": True, "content": content})
            except Exception as e:
                self._send_json({"ok": True, "content": f"*Error loading doc: {e}*"})
            return

        if route == "/api/git/log":
            try:
                result = subprocess.run(
                    ["git", "log", "-n", "8", "--oneline"],
                    cwd=BASE_DIR.parent.parent,
                    capture_output=True,
                    text=True,
                    check=False
                )
                self._send_json({"ok": True, "log": result.stdout.strip() if result.returncode == 0 else "Git log not available"})
            except Exception:
                self._send_json({"ok": True, "log": "Git not initialized or available"})
            return

        if route.startswith("/api/"):
            self._send_json({"ok": False, "error": "Route not found", "hint": "See GET /api/conventions for the canonical API operation catalog and payload schemas."}, status=HTTPStatus.NOT_FOUND)
            return

        self._serve_static(route)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        route = parsed.path
        try:
            body = self._read_json()
        except ValueError as exc:
            self._send_error(str(exc))
            return

        with STORE._lock:
            conn = STORE.get_conn()
            c = conn.cursor()
            now = now_iso()

            try:
                if route == "/api/memory/events":
                    board_request = str(body.get("boardId") or "").strip()
                    board_id = _resolve_board_id(c, board_request)
                    if not board_id:
                        self._send_error("Board not found", status=HTTPStatus.NOT_FOUND)
                        return

                    memory_key = str(body.get("memoryKey") or "").strip()
                    if not memory_key:
                        self._send_error("memoryKey is required")
                        return

                    source_type = str(body.get("sourceType") or "").strip().lower()
                    if source_type not in MEMORY_ALLOWED_SOURCES:
                        self._send_error(
                            "sourceType must be one of: user, operator, verified-system",
                            status=HTTPStatus.FORBIDDEN,
                        )
                        return

                    event_type = str(body.get("eventType") or "upsert").strip().lower()
                    if event_type not in MEMORY_ALLOWED_EVENT_TYPES:
                        self._send_error("eventType must be one of: upsert, delete, touch")
                        return

                    if event_type == "upsert" and "value" not in body:
                        self._send_error("value is required for upsert events")
                        return

                    bucket = str(body.get("bucket") or "misc").strip().lower()
                    if bucket not in MEMORY_ALLOWED_BUCKETS:
                        bucket = "misc"

                    raw_tags = body.get("tags", [])
                    if raw_tags is None:
                        raw_tags = []
                    if not isinstance(raw_tags, list):
                        self._send_error("tags must be an array")
                        return
                    tags = [str(tag).strip() for tag in raw_tags if str(tag).strip()][:32]
                    tags_json = _json_dumps_compact(tags)

                    ttl_seconds = _safe_int(body.get("ttlSeconds"), 0, 0, 31_536_000)
                    expires_at = ""
                    if ttl_seconds > 0:
                        expires_at = (
                            dt.datetime.utcnow().replace(microsecond=0) + dt.timedelta(seconds=ttl_seconds)
                        ).isoformat() + "Z"

                    source_ref = str(body.get("sourceRef") or "")
                    value_json = _json_dumps_compact(body.get("value"))
                    if event_type != "upsert":
                        value_json = "null"

                    event_id = new_id("mev")
                    if event_type == "touch":
                        c.execute(
                            "SELECT id FROM memory_objects WHERE boardId=? AND memoryKey=? AND isDeleted=0",
                            (board_id, memory_key),
                        )
                        if not c.fetchone():
                            self._send_error("Cannot touch missing memoryKey", status=HTTPStatus.NOT_FOUND)
                            return

                    c.execute(
                        """
                        INSERT INTO memory_events (
                            id, boardId, memoryKey, eventType, sourceType, attested, bucket,
                            value, tags, ttlSeconds, sourceRef, createdAt
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            event_id,
                            board_id,
                            memory_key,
                            event_type,
                            source_type,
                            1,
                            bucket,
                            value_json,
                            tags_json,
                            ttl_seconds,
                            source_ref,
                            now,
                        ),
                    )

                    applied = _apply_memory_event(
                        c,
                        board_id=board_id,
                        event_id=event_id,
                        now=now,
                        memory_key=memory_key,
                        event_type=event_type,
                        source_type=source_type,
                        bucket=bucket,
                        value_json=value_json,
                        tags_json=tags_json,
                        expires_at=expires_at or None,
                    )
                    conn.commit()
                    self._send_json(
                        {
                            "ok": True,
                            "memory": {
                                "boardId": board_id,
                                "eventId": event_id,
                                "memoryKey": memory_key,
                                "applied": applied,
                                "eventType": event_type,
                            },
                        }
                    )
                    return

                if route == "/api/memory/compact":
                    board_request = str(body.get("boardId") or "").strip()
                    board_id = _resolve_board_id(c, board_request)
                    if not board_id:
                        self._send_error("Board not found", status=HTTPStatus.NOT_FOUND)
                        return

                    result = _compact_memory(c, board_id, now, MemoryBudgets.from_payload(body))
                    conn.commit()
                    self._send_json({"ok": True, "memory": {"compact": result}})
                    return

                if route == "/api/memory/export":
                    self._send_error(
                        "memory export is disabled in v2 DB-only mode; use /api/memory/state or /api/memory/query",
                        status=HTTPStatus.GONE,
                    )
                    return

                if route == "/api/migration/legacy-state-json/run":
                    force = bool(body.get("force", False))
                    report = migrate_legacy_state_json_to_sqlite(DB_FILE, LEGACY_STATE_FILE, force=force)
                    global LEGACY_MIGRATION_REPORT
                    LEGACY_MIGRATION_REPORT = report
                    self._send_json({"ok": report.get("ok", False), "migration": report})
                    return

                if route.startswith("/api/boards/") and route.endswith("/artifacts"):
                    parts = route.split("/")
                    if len(parts) != 5:
                        self._send_error("Route not found", status=HTTPStatus.NOT_FOUND)
                        return
                    board_id = (parts[3] or "").strip()
                    if not board_id:
                        self._send_error("boardId is required")
                        return

                    c.execute("SELECT id FROM boards WHERE id=?", (board_id,))
                    if not c.fetchone():
                        self._send_error("Board not found", status=HTTPStatus.NOT_FOUND)
                        return

                    if "id" in body or "revision" in body:
                        self._send_error("id and revision are server-assigned; omit both fields")
                        return

                    try:
                        artifact_type = _coerce_board_artifact_type(body.get("artifactType"))
                        title = _coerce_artifact_text(
                            body.get("title"), "title", ARTIFACT_TITLE_MAX_LEN, required=True
                        )
                        summary = _coerce_artifact_text(body.get("summary"), "summary", ARTIFACT_SUMMARY_MAX_LEN)
                        artifact_body = _coerce_artifact_text(body.get("body"), "body", ARTIFACT_BODY_MAX_LEN)
                        source_ref = _coerce_artifact_text(
                            body.get("sourceRef"), "sourceRef", ARTIFACT_SOURCE_REF_MAX_LEN
                        )
                    except ValueError as exc:
                        self._send_error(str(exc), status=HTTPStatus.UNPROCESSABLE_ENTITY)
                        return

                    c.execute(
                        """
                        SELECT COALESCE(MAX(revision), 0) + 1 AS nextRevision
                        FROM board_artifacts
                        WHERE boardId=? AND artifactType=?
                        """,
                        (board_id, artifact_type),
                    )
                    row = c.fetchone() or {}
                    next_revision = int(row.get("nextRevision") or 1)
                    artifact_id = new_id("bfa")
                    c.execute(
                        """
                        INSERT INTO board_artifacts (
                            id, boardId, artifactType, revision,
                            title, summary, body, sourceRef, createdAt, updatedAt
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            artifact_id,
                            board_id,
                            artifact_type,
                            next_revision,
                            title,
                            summary,
                            artifact_body,
                            source_ref,
                            now,
                            now,
                        ),
                    )
                    conn.commit()
                    c.execute("SELECT * FROM board_artifacts WHERE id=?", (artifact_id,))
                    created = c.fetchone()
                    self._send_json({"ok": True, "artifact": _board_artifact_payload(created, include_body=True)})
                    return

                if route.startswith("/api/milestones/"):
                    parts = route.split("/")
                    if len(parts) == 5 and parts[4] == "artifacts":
                        milestone_id = (parts[3] or "").strip()
                        if not milestone_id:
                            self._send_error("milestoneId is required")
                            return

                        if "id" in body or "revision" in body:
                            self._send_error("id and revision are server-assigned; omit both fields")
                            return

                        c.execute("SELECT * FROM milestones WHERE id=?", (milestone_id,))
                        milestone = c.fetchone()
                        if not milestone:
                            self._send_error("Milestone not found", status=HTTPStatus.NOT_FOUND)
                            return
                        if _is_archived_milestone(milestone):
                            self._send_error(MILESTONE_ARCHIVED_ERROR, status=HTTPStatus.CONFLICT)
                            return

                        try:
                            artifact_type = _coerce_artifact_type(body.get("artifactType"))
                            title = _coerce_artifact_text(
                                body.get("title"), "title", ARTIFACT_TITLE_MAX_LEN, required=True
                            )
                            summary = _coerce_artifact_text(body.get("summary"), "summary", ARTIFACT_SUMMARY_MAX_LEN)
                            artifact_body = _coerce_artifact_text(body.get("body"), "body", ARTIFACT_BODY_MAX_LEN)
                            source_card_id = _coerce_artifact_text(
                                body.get("sourceCardId"), "sourceCardId", ARTIFACT_SOURCE_REF_MAX_LEN
                            )
                            source_event_id = _coerce_artifact_text(
                                body.get("sourceEventId"), "sourceEventId", ARTIFACT_SOURCE_REF_MAX_LEN
                            )
                        except ValueError as exc:
                            self._send_error(str(exc), status=HTTPStatus.UNPROCESSABLE_ENTITY)
                            return

                        board_id = str(milestone.get("boardId") or "")
                        c.execute(
                            """
                            SELECT COALESCE(MAX(revision), 0) + 1 AS nextRevision
                            FROM milestone_artifacts
                            WHERE boardId=? AND milestoneId=? AND artifactType=?
                            """,
                            (board_id, milestone_id, artifact_type),
                        )
                        row = c.fetchone() or {}
                        next_revision = int(row.get("nextRevision") or 1)

                        artifact_id = new_id("mfa")
                        c.execute(
                            """
                            INSERT INTO milestone_artifacts (
                                id, boardId, milestoneId, artifactType, revision,
                                title, summary, body, sourceCardId, sourceEventId, createdAt, updatedAt
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                artifact_id,
                                board_id,
                                milestone_id,
                                artifact_type,
                                next_revision,
                                title,
                                summary,
                                artifact_body,
                                source_card_id,
                                source_event_id,
                                now,
                                now,
                            ),
                        )
                        conn.commit()
                        c.execute("SELECT * FROM milestone_artifacts WHERE id=?", (artifact_id,))
                        created = c.fetchone()
                        self._send_json({"ok": True, "artifact": _artifact_payload(created, include_body=True)})
                        return

                if route == "/api/boards":
                    name = str(body.get("name") or "").strip()
                    if not name:
                        self._send_error("Board name is required")
                        return
                    description = str(body.get("description") or "")
                    codename = str(body.get("codename") or "PRJ").strip().upper()[:3]
                    
                    board_id = new_id("board")
                    c.execute(
                        """
                        INSERT INTO boards (
                            id, name, codename, nextIssueNumber, description, projectType, preflightLifecycleInitialized, createdAt, updatedAt
                        ) VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)
                        """,
                        (board_id, name, codename, 1, description, "standard", now, now),
                    )
                    
                    # add default lists
                    statuses = [("backlog", "Backlog"), ("active", "In Progress"), ("blocked", "Blocked"), ("qa", "QA / Review"), ("done", "Done")]
                    for i, (k, v) in enumerate(statuses):
                        c.execute("INSERT INTO lists (id, boardId, key, title, listOrder, createdAt, updatedAt) VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (new_id("list"), board_id, k, v, i, now, now))

                    c.execute("UPDATE meta SET value = ? WHERE key = 'activeBoardId'", (board_id,))
                    conn.commit()
                    self._send_json({"ok": True, "state": STORE.snapshot()})
                    return

                if route.endswith("/activate") and route.startswith("/api/boards/"):
                    board_id = route.split("/")[3]
                    c.execute("UPDATE meta SET value = ? WHERE key = 'activeBoardId'", (board_id,))
                    conn.commit()
                    self._send_json({"ok": True, "state": STORE.snapshot()})
                    return

                if route == "/api/lists":
                    board_id = str(body.get("boardId") or "")
                    title = str(body.get("title") or "").strip()
                    if not board_id or not title:
                        self._send_error("boardId and title are required")
                        return
                    c.execute("SELECT MAX(listOrder) as m FROM lists WHERE boardId=?", (board_id,))
                    res = c.fetchone()
                    max_ord = (res["m"] + 1) if res and res["m"] is not None else 0
                    c.execute("INSERT INTO lists (id, boardId, key, title, listOrder, createdAt, updatedAt) VALUES (?, ?, '', ?, ?, ?, ?)",
                        (new_id("list"), board_id, title, max_ord, now, now))
                    conn.commit()
                    self._send_json({"ok": True, "state": STORE.snapshot()})
                    return

                if route == "/api/milestones":
                    board_id = str(body.get("boardId") or "")
                    title = str(body.get("title") or "").strip()
                    if not board_id or not title:
                        self._send_error("boardId and title are required")
                        return
                    try:
                        milestone_code = _coerce_milestone_code(body.get("code", ""), title)
                        normalized_title = _strip_milestone_code_prefix(title, milestone_code) or title
                        meta_contract = _coerce_milestone_text(body.get("metaContract", ""), "metaContract")
                        goals = _coerce_milestone_text(body.get("goals", ""), "goals")
                        non_goals = _coerce_milestone_text(body.get("nonGoals", ""), "nonGoals")
                        risks = _coerce_milestone_text(body.get("risks", ""), "risks")
                    except ValueError as exc:
                        self._send_error(str(exc))
                        return
                    c.execute("SELECT MAX(msOrder) as m FROM milestones WHERE boardId=?", (board_id,))
                    res = c.fetchone()
                    max_ord = (res["m"] + 1) if res and res["m"] is not None else 0
                    c.execute(
                        """
                        INSERT INTO milestones (
                            id, boardId, code, title, msOrder, kind, acceptsNewCards, writeClosedAt, archivedAt, metaContract, goals, nonGoals, risks, createdAt, updatedAt
                        ) VALUES (?, ?, ?, ?, ?, ?, 1, '', '', ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            new_id("ms"),
                            board_id,
                            milestone_code,
                            normalized_title,
                            max_ord,
                            MILESTONE_KIND_STANDARD,
                            meta_contract,
                            goals,
                            non_goals,
                            risks,
                            now,
                            now,
                        ),
                    )
                    conn.commit()
                    self._send_json({"ok": True, "state": STORE.snapshot()})
                    return

                if route.endswith("/restore") and route.startswith("/api/milestones/"):
                    parts = route.split("/")
                    if len(parts) < 5:
                        self._send_error("Milestone id is required")
                        return
                    milestone_id = parts[3]
                    c.execute("SELECT boardId FROM milestones WHERE id=?", (milestone_id,))
                    row = c.fetchone()
                    if not row:
                        self._send_error("Milestone not found", status=HTTPStatus.NOT_FOUND)
                        return
                    board_id = str(row.get("boardId") or "")
                    c.execute(
                        "UPDATE milestones SET archivedAt='', updatedAt=? WHERE id=?",
                        (now, milestone_id),
                    )
                    if board_id:
                        _refresh_preflight_write_state(c, board_id, now)
                    conn.commit()
                    self._send_json({"ok": True, "state": STORE.snapshot()})
                    return

                if route == "/api/cards":
                    required = ["boardId", "listId", "title", "milestoneId"]
                    if any(not str(body.get(key) or "").strip() for key in required):
                        self._send_error("boardId, listId, title, and milestoneId are required")
                        return
                    board_id = str(body["boardId"]).strip()
                    list_id = str(body["listId"]).strip()
                    milestone_id = str(body.get("milestoneId") or "").strip()
                    if not milestone_id:
                        self._send_error(MILESTONE_REQUIRED_ERROR)
                        return
                    
                    c.execute("SELECT codename, nextIssueNumber FROM boards WHERE id=?", (board_id,))
                    b_row = c.fetchone()
                    if not b_row:
                        self._send_error("Board not found", status=HTTPStatus.NOT_FOUND)
                        return

                    _refresh_preflight_write_state(c, board_id, now)
                    milestone = _get_milestone(c, board_id, milestone_id)
                    if not milestone:
                        self._send_error("Milestone not found", status=HTTPStatus.NOT_FOUND)
                        return
                    if _is_archived_milestone(milestone):
                        self._send_error(MILESTONE_ARCHIVED_ERROR, status=HTTPStatus.CONFLICT)
                        return
                    if _is_write_closed_preflight(milestone):
                        self._send_error(MILESTONE_CLOSED_ERROR, status=HTTPStatus.CONFLICT)
                        return
                    
                    cutoff_row = c.execute(
                        "SELECT value FROM meta WHERE key='taskIssueNumberSchemeCutoff'"
                    ).fetchone()
                    cutoff = str(cutoff_row.get("value") or "").strip() if cutoff_row else ""
                    use_descendant_scheme = cutoff and now >= cutoff
                    milestone_code = str(milestone.get("code") or "").strip()
                    
                    if use_descendant_scheme and milestone_code:
                        next_card = int(milestone.get("nextCardNumber") or 1)
                        issue_number = f"{milestone_code}-{next_card:03d}"
                        c.execute(
                            "UPDATE milestones SET nextCardNumber = nextCardNumber + 1, updatedAt = ? WHERE id = ?",
                            (now, milestone_id),
                        )
                    else:
                        issue_number = f"{b_row['codename']}-{b_row['nextIssueNumber']:03d}"
                        c.execute("UPDATE boards SET nextIssueNumber = nextIssueNumber + 1 WHERE id=?", (board_id,))
                    
                    card_kind = str(body.get("kind") or "task").lower()
                    if card_kind not in ("task", "bug"):
                        self._send_error("kind must be 'task' or 'bug'", status=HTTPStatus.UNPROCESSABLE_ENTITY)
                        return

                    c.execute("SELECT MAX(cardOrder) as m FROM cards WHERE listId=?", (list_id,))
                    res = c.fetchone()
                    max_ord = (res["m"] + 1) if res and res["m"] is not None else 0

                    c.execute("INSERT INTO cards (id, boardId, issueNumber, title, description, acceptance, milestoneId, listId, priority, owner, targetDate, kind, cardOrder, createdAt, updatedAt) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (new_id("card"), board_id, issue_number, body["title"], body.get("description", ""), body.get("acceptance", ""), milestone_id, list_id, body.get("priority", "P2"), body.get("owner", ""), body.get("targetDate", ""), card_kind, max_ord, now, now))
                    
                    conn.commit()
                    self._send_json({"ok": True, "state": STORE.snapshot()})
                    return

                if route == "/api/charts":
                    required = ["boardId", "title"]
                    if any(not str(body.get(key) or "").strip() for key in required):
                        self._send_error("boardId and title are required")
                        return

                    board_id = str(body.get("boardId") or "").strip()
                    title = str(body.get("title") or "").strip()
                    description = str(body.get("description") or "")
                    try:
                        markdown = normalize_and_validate_mermaid(str(body.get("markdown") or ""))
                    except ValueError as exc:
                        self._send_error(str(exc), status=HTTPStatus.UNPROCESSABLE_ENTITY)
                        return

                    c.execute("SELECT id FROM boards WHERE id=?", (board_id,))
                    if not c.fetchone():
                        self._send_error("Board not found", status=HTTPStatus.NOT_FOUND)
                        return

                    c.execute(
                        "INSERT INTO charts (id, boardId, title, description, markdown, createdAt, updatedAt) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (new_id("chart"), board_id, title, description, markdown, now, now),
                    )

                    conn.commit()
                    self._send_json({"ok": True, "state": STORE.snapshot()})
                    return

                if route.endswith("/move") and route.startswith("/api/cards/"):
                    card_id = route.split("/")[3]
                    list_id = str(body.get("listId") or "")
                    if not list_id:
                        self._send_error("listId is required")
                        return
                    c.execute("SELECT * FROM cards WHERE id=?", (card_id,))
                    card_row = c.fetchone()
                    if not card_row:
                        self._send_error("Card not found", status=HTTPStatus.NOT_FOUND)
                        return
                    board_id = str(card_row.get("boardId") or "")
                    old_list_id = str(card_row.get("listId") or "")
                    c.execute("SELECT MAX(cardOrder) as m FROM cards WHERE listId=?", (list_id,))
                    res = c.fetchone()
                    max_ord = (res["m"] + 1) if res and res["m"] is not None else 0
                    c.execute("UPDATE cards SET listId=?, cardOrder=?, updatedAt=? WHERE id=?", (list_id, max_ord, now, card_id))
                    c.execute("SELECT * FROM cards WHERE id=?", (card_id,))
                    updated_card = c.fetchone()

                    if updated_card and _is_completion_transition(c, board_id, old_list_id, str(updated_card.get("listId") or "")):
                        _append_findings_for_eval_completion(
                            c,
                            updated_card,
                            now,
                            source_event_id=f"card-move:{card_id}:{now}",
                        )

                    _refresh_preflight_write_state(c, board_id, now)
                    conn.commit()
                    self._send_json({"ok": True, "state": STORE.snapshot()})
                    return

                if route == "/api/boards/import" or route.endswith("/clone"):
                    self._send_error("Import/Clone not fully migrated to DB, skipped for simplicity", status=HTTPStatus.NOT_IMPLEMENTED)
                    return

                if route == "/api/reload":
                    self._send_json({"ok": True, "state": STORE.snapshot()})
                    return

                self._send_error("Route not found", status=HTTPStatus.NOT_FOUND)
            finally:
                conn.close()

    def do_PATCH(self) -> None:
        parsed = urlparse(self.path)
        route = parsed.path
        try:
            body = self._read_json()
        except ValueError as exc:
            self._send_error(str(exc))
            return

        with STORE._lock:
            conn = STORE.get_conn()
            c = conn.cursor()
            now = now_iso()
            try:
                if route.startswith("/api/milestones/") and "/artifacts" in route:
                    parts = route.split("/")
                    if len(parts) >= 5 and parts[4] == "artifacts":
                        self._send_error(
                            "Milestone artifacts are immutable. Create a new revision with POST /api/milestones/{milestoneId}/artifacts.",
                            status=HTTPStatus.METHOD_NOT_ALLOWED,
                        )
                        return

                if route.startswith("/api/boards/"):
                    board_id = route.split("/")[3]
                    if "name" in body:
                        c.execute("UPDATE boards SET name=?, updatedAt=? WHERE id=?", (body["name"], now, board_id))
                    if "description" in body:
                        c.execute("UPDATE boards SET description=?, updatedAt=? WHERE id=?", (body["description"], now, board_id))
                    conn.commit()
                    self._send_json({"ok": True, "state": STORE.snapshot()})
                    return

                if route.startswith("/api/lists/"):
                    list_id = route.split("/")[3]
                    if "title" in body:
                        c.execute("UPDATE lists SET title=?, updatedAt=? WHERE id=?", (body["title"], now, list_id))
                    if "order" in body:
                        c.execute("UPDATE lists SET listOrder=?, updatedAt=? WHERE id=?", (body["order"], now, list_id))
                    conn.commit()
                    self._send_json({"ok": True, "state": STORE.snapshot()})
                    return

                if route.startswith("/api/milestones/"):
                    parts = route.split("/")
                    if len(parts) != 4:
                        self._send_error("Route not found", status=HTTPStatus.NOT_FOUND)
                        return
                    milestone_id = parts[3]
                    if "title" in body:
                        c.execute("UPDATE milestones SET title=?, updatedAt=? WHERE id=?", (str(body["title"]).strip(), now, milestone_id))
                    if "code" in body:
                        try:
                            code_value = _coerce_milestone_code(body.get("code", ""), body.get("title", ""))
                        except ValueError as exc:
                            self._send_error(str(exc))
                            return
                        c.execute("UPDATE milestones SET code=?, updatedAt=? WHERE id=?", (code_value, now, milestone_id))
                    if "order" in body:
                        c.execute("UPDATE milestones SET msOrder=?, updatedAt=? WHERE id=?", (body["order"], now, milestone_id))
                    # B608 Fix: strict allowlist mapping
                    for field in MILESTONE_METADATA_FIELDS:
                        if field in body:
                            try:
                                value = _coerce_milestone_text(body.get(field), field)
                            except ValueError as exc:
                                self._send_error(str(exc))
                                return
                            # The field is already strictly checked against MILESTONE_METADATA_FIELDS
                            c.execute(f"UPDATE milestones SET {field}=?, updatedAt=? WHERE id=?", (value, now, milestone_id))  # nosec B608
                    conn.commit()
                    self._send_json({"ok": True, "state": STORE.snapshot()})
                    return

                if route.startswith("/api/cards/"):
                    card_id = route.split("/")[3]
                    c.execute("SELECT * FROM cards WHERE id=?", (card_id,))
                    current_card = c.fetchone()
                    if not current_card:
                        self._send_error("Card not found", status=HTTPStatus.NOT_FOUND)
                        return
                    board_id = str(current_card.get("boardId") or "")
                    old_list_id = str(current_card.get("listId") or "")
                    _refresh_preflight_write_state(c, board_id, now)

                    if "milestoneId" in body:
                        new_milestone_id = str(body.get("milestoneId") or "").strip()
                        if not new_milestone_id:
                            self._send_error(MILESTONE_REQUIRED_ERROR)
                            return
                        old_milestone_id = str(current_card.get("milestoneId") or "")
                        if new_milestone_id != old_milestone_id:
                            milestone = _get_milestone(c, board_id, new_milestone_id)
                            if not milestone:
                                self._send_error("Milestone not found", status=HTTPStatus.NOT_FOUND)
                                return
                            if _is_archived_milestone(milestone):
                                self._send_error(MILESTONE_ARCHIVED_ERROR, status=HTTPStatus.CONFLICT)
                                return
                            if _is_write_closed_preflight(milestone):
                                self._send_error(MILESTONE_CLOSED_ERROR, status=HTTPStatus.CONFLICT)
                                return
                        body["milestoneId"] = new_milestone_id

                    if "kind" in body:
                        patch_kind = str(body.get("kind") or "task").lower()
                        if patch_kind not in ("task", "bug"):
                            self._send_error("kind must be 'task' or 'bug'", status=HTTPStatus.UNPROCESSABLE_ENTITY)
                            return
                        c.execute("UPDATE cards SET kind=?, updatedAt=? WHERE id=?", (patch_kind, now, card_id))

                    fields = ["title", "description", "acceptance", "owner", "targetDate", "priority", "milestoneId", "listId"]
                    for f in fields:
                        if f in body:
                            db_field = "cardOrder" if f == "order" else f
                            # Safe because f is from static list 'fields', and db_field is statically mapped
                            c.execute(f"UPDATE cards SET {db_field}=?, updatedAt=? WHERE id=?", (body[f], now, card_id))  # nosec B608
                    if "listId" in body:
                        list_id = body["listId"]
                        c.execute("SELECT MAX(cardOrder) as m FROM cards WHERE listId=?", (list_id,))
                        res = c.fetchone()
                        max_ord = (res["m"] + 1) if res and res["m"] is not None else 0
                        c.execute("UPDATE cards SET cardOrder=? WHERE id=?", (max_ord, card_id))

                    c.execute("SELECT * FROM cards WHERE id=?", (card_id,))
                    updated_card = c.fetchone()
                    if updated_card and "listId" in body and _is_completion_transition(
                        c,
                        board_id,
                        old_list_id,
                        str(updated_card.get("listId") or ""),
                    ):
                        _append_findings_for_eval_completion(
                            c,
                            updated_card,
                            now,
                            source_event_id=f"card-patch:{card_id}:{now}",
                        )

                    _refresh_preflight_write_state(c, board_id, now)
                    conn.commit()
                    self._send_json({"ok": True, "state": STORE.snapshot()})
                    return

                if route.startswith("/api/charts/"):
                    chart_id = route.split("/")[3]
                    c.execute("SELECT id FROM charts WHERE id=?", (chart_id,))
                    if not c.fetchone():
                        self._send_error("Chart not found", status=HTTPStatus.NOT_FOUND)
                        return

                    if "title" in body and not str(body.get("title") or "").strip():
                        self._send_error("title cannot be empty")
                        return

                    updated = False
                    for field in ["title", "description", "markdown"]:
                        if field in body:
                            value = str(body.get(field) or "")
                            if field == "markdown":
                                try:
                                    value = normalize_and_validate_mermaid(value)
                                except ValueError as exc:
                                    self._send_error(str(exc), status=HTTPStatus.UNPROCESSABLE_ENTITY)
                                    return
                            # Safe because field is from static literal list
                            c.execute(f"UPDATE charts SET {field}=?, updatedAt=? WHERE id=?", (value, now, chart_id))  # nosec B608
                            updated = True

                    if not updated:
                        self._send_error("No updatable chart fields provided")
                        return

                    conn.commit()
                    self._send_json({"ok": True, "state": STORE.snapshot()})
                    return
                self._send_error("Route not found", status=HTTPStatus.NOT_FOUND)
            finally:
                conn.close()

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        route = parsed.path
        with STORE._lock:
            conn = STORE.get_conn()
            c = conn.cursor()
            try:
                if route.startswith("/api/boards/"):
                    board_id = route.split("/")[3]
                    c.execute("DELETE FROM boards WHERE id=?", (board_id,))
                    c.execute("DELETE FROM cards WHERE boardId=?", (board_id,))
                    c.execute("DELETE FROM lists WHERE boardId=?", (board_id,))
                    c.execute("DELETE FROM milestones WHERE boardId=?", (board_id,))
                    c.execute("DELETE FROM charts WHERE boardId=?", (board_id,))
                    c.execute("DELETE FROM milestone_artifacts WHERE boardId=?", (board_id,))
                    c.execute("DELETE FROM board_artifacts WHERE boardId=?", (board_id,))
                    c.execute("DELETE FROM memory_events WHERE boardId=?", (board_id,))
                    c.execute("DELETE FROM memory_objects WHERE boardId=?", (board_id,))
                    # fallback active board
                    c.execute("SELECT id FROM boards LIMIT 1")
                    res = c.fetchone()
                    if res:
                        c.execute("UPDATE meta SET value=? WHERE key='activeBoardId'", (res["id"],))
                    conn.commit()
                    self._send_json({"ok": True, "state": STORE.snapshot()})
                    return

                if route.startswith("/api/lists/"):
                    list_id = route.split("/")[3]
                    c.execute("SELECT boardId FROM lists WHERE id=?", (list_id,))
                    res = c.fetchone()
                    if res:
                        board_id = res["boardId"]
                        c.execute("SELECT id FROM lists WHERE boardId=? AND id!=? LIMIT 1", (board_id, list_id))
                        fallback = c.fetchone()
                        if fallback:
                            c.execute("UPDATE cards SET listId=? WHERE listId=?", (fallback["id"], list_id))
                        c.execute("DELETE FROM lists WHERE id=?", (list_id,))
                        conn.commit()
                    self._send_json({"ok": True, "state": STORE.snapshot()})
                    return

                if route.startswith("/api/milestones/"):
                    parts = route.split("/")
                    if len(parts) >= 5 and parts[4] == "artifacts":
                        self._send_error(
                            "Milestone artifacts are immutable and cannot be deleted.",
                            status=HTTPStatus.METHOD_NOT_ALLOWED,
                        )
                        return
                    if len(parts) != 4:
                        self._send_error("Route not found", status=HTTPStatus.NOT_FOUND)
                        return
                    milestone_id = parts[3]
                    c.execute("SELECT * FROM milestones WHERE id=?", (milestone_id,))
                    row = c.fetchone()
                    if not row:
                        self._send_error("Milestone not found", status=HTTPStatus.NOT_FOUND)
                        return
                    was_archived = bool(str(row.get("archivedAt") or "").strip())
                    now = now_iso()
                    if not was_archived:
                        _append_outcomes_for_milestone_closeout(
                            c,
                            row,
                            now,
                            source_event_id=f"milestone-closeout:{milestone_id}:{now}",
                        )
                    c.execute(
                        """
                        UPDATE milestones
                        SET archivedAt=COALESCE(NULLIF(archivedAt, ''), ?),
                            updatedAt=?
                        WHERE id=?
                        """,
                        (now, now, milestone_id),
                    )
                    conn.commit()
                    self._send_json({"ok": True, "state": STORE.snapshot()})
                    return

                if route.startswith("/api/cards/"):
                    card_id = route.split("/")[3]
                    c.execute("DELETE FROM cards WHERE id=?", (card_id,))
                    conn.commit()
                    self._send_json({"ok": True, "state": STORE.snapshot()})
                    return

                if route.startswith("/api/charts/"):
                    chart_id = route.split("/")[3]
                    c.execute("DELETE FROM charts WHERE id=?", (chart_id,))
                    conn.commit()
                    self._send_json({"ok": True, "state": STORE.snapshot()})
                    return

                self._send_error("Route not found", status=HTTPStatus.NOT_FOUND)
            finally:
                conn.close()

    def _serve_static(self, route: str) -> None:
        sanitized = route.lstrip("/")
        if not sanitized:
            sanitized = "index.html"
        fs_path = (PUBLIC_DIR / unquote(sanitized)).resolve()
        in_scope = str(fs_path).startswith(str(PUBLIC_DIR.resolve()))

        if not in_scope or not fs_path.exists() or fs_path.is_dir():
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        content_type, _ = mimetypes.guess_type(fs_path.name)
        content_type = content_type or "application/octet-stream"
        payload = fs_path.read_bytes()

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the local Kanban micro-service")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    parser.add_argument("--port", type=int, required=True, help="Bind port (read from .amphion/config.json)")
    return parser.parse_args()

def main() -> None:
    args = parse_args()
    server = ThreadingHTTPServer((args.host, args.port), KanbanHandler)
    print(f"Kanban (SQLite) running at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

if __name__ == "__main__":
    main()
