#!/usr/bin/env python3
"""Agent-assisted legacy state.json -> SQLite migration runner."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request


def request_json(url: str, method: str = "GET", body: dict | None = None) -> dict:
    if not url.startswith(("http://", "https://")):
        raise ValueError("Invalid URL scheme")
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as resp:  # nosec B310
        raw = resp.read().decode("utf-8")
    return json.loads(raw)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run legacy state.json -> SQLite migration via Command Deck API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", required=True, help="Port from .amphion/config.json")
    parser.add_argument("--force", action="store_true", help="Force migration even if SQLite already has boards.")
    parser.add_argument(
        "--expect-min-cards",
        type=int,
        default=0,
        help="Fail if resulting board snapshot has fewer than this many cards.",
    )
    args = parser.parse_args()

    base_url = f"http://{args.host}:{args.port}"
    try:
        result = request_json(f"{base_url}/api/migration/legacy-state-json/run", "POST", {"force": args.force})
        status = request_json(f"{base_url}/api/migration/legacy-state-json/status")
        snapshot = request_json(f"{base_url}/api/state")
    except urllib.error.URLError as exc:
        print(f"Migration failed: unable to reach Command Deck API ({exc}).", file=sys.stderr)
        return 2
    except Exception as exc:  # pragma: no cover - operational guard
        print(f"Migration failed: {exc}", file=sys.stderr)
        return 2

    boards = snapshot.get("state", {}).get("boards", [])
    counts = {
        "boards": len(boards),
        "lists": sum(len(board.get("lists", [])) for board in boards),
        "milestones": sum(len(board.get("milestones", [])) for board in boards),
        "cards": sum(len(board.get("cards", [])) for board in boards),
        "charts": len(snapshot.get("state", {}).get("charts", [])),
    }
    output = {
        "run": result,
        "status": status,
        "verification": {
            "ok": counts["cards"] >= args.expect_min_cards,
            "expectedMinCards": args.expect_min_cards,
            "counts": counts,
        },
    }
    print(json.dumps(output, indent=2))
    if not result.get("ok") or counts["cards"] < args.expect_min_cards:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
