#!/usr/bin/env zsh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
HOST="${KANBAN_HOST:-127.0.0.1}"

CONFIG_FILE="$ROOT/../config.json"
CONFIGURED_PORT=""
if [[ -f "$CONFIG_FILE" ]]; then
    CONFIGURED_PORT=$(grep -Eo '"port"\s*:\s*"[0-9]+"' "$CONFIG_FILE" | grep -Eo '[0-9]+' || echo "")
fi

if [ -z "${1:-}" ] && [ -z "${KANBAN_PORT:-}" ] && [ -z "$CONFIGURED_PORT" ]; then
    echo "No port specified. Set port in .amphion/config.json or pass as argument." >&2
    exit 1
fi
PORT="${1:-${KANBAN_PORT:-$CONFIGURED_PORT}}"

python3 "$ROOT/server.py" --host "$HOST" --port "$PORT"
