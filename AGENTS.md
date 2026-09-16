# Agent Instructions · Sierra (`Sie`)

This project uses the MCD protocol for deterministic AI alignment and safety.

## Protocol Entrance
Before performing any task, the agent must identify the current phase and load the appropriate command from `.amphion/control-plane/mcd/`.

## Core References
- [Governance Guardrails](.amphion/control-plane/GUARDRAILS.md)
- [MCD Playbook](.amphion/control-plane/MCD_PLAYBOOK.md)

## Workflow
1. **Research** via the Evaluate command.
2. **Plan** via the Contract command.
3. **Build** via the Execute command.
4. **Finalize** via the Closeout command.

## Utility Commands
- **Help** via the Help command (`/help`): [HELP.md](.amphion/control-plane/mcd/HELP.md) (authority: `.amphion/control-plane/MCD_HELP_SOURCE.md`).
- **Remember** via the Remember command (`/remember`) for non-phase memory checkpoints.

**Important**: Never chain MCD phases. If you complete an EVALUATE phase, you MUST halt tool execution, present your findings and ask the user to authorize `/contract`, which must be authored as milestone-bound board cards via DB/API. Once you complete a CONTRACT phase, you MUST halt tool execution and explicitly wait for the user to authorize the next phase.

## Workflow Routing

To invoke a slash command, read the corresponding workflow file:

- **evaluate** → [.agents/workflows/evaluate.md](.agents/workflows/evaluate.md)
- **contract** → [.agents/workflows/contract.md](.agents/workflows/contract.md)
- **execute** → [.agents/workflows/execute.md](.agents/workflows/execute.md)
- **closeout** → [.agents/workflows/closeout.md](.agents/workflows/closeout.md)
- **help** → [.agents/workflows/help.md](.agents/workflows/help.md)
- **remember** → [.agents/workflows/remember.md](.agents/workflows/remember.md)
- **docs** → [.agents/workflows/docs.md](.agents/workflows/docs.md)
- **bug** → [.agents/workflows/bug.md](.agents/workflows/bug.md)

## Product Manager Experience
1. **Proactive Guidance**: If the user starts a session without a specific request, proactively ask them if they want to improve their Project Charter / PRD, or if they have an idea to start the first MCD cycle.
2. **Observability**: Always keep the Command Deck updated by creating/updating contract cards in the active milestone.

## Command Deck API

**ALL board writes MUST use the Command Deck API. Direct SQLite writes, Python scripts, and filesystem substitutes are non-canonical and violate GUARDRAILS write-boundary policy.**

Resolve API location:
1. Read `port` from `.amphion/config.json`.
2. If `port` is missing or config.json does not exist, run `/amphion` to configure the workspace.
3. Base URL is `http://127.0.0.1:{resolvedPort}`.

All write operations use MCP bridge tools when available. Tool schemas carry full payload definitions (enum, required fields, constraints) — no need to call conventions before writes.

If MCP tools are unavailable, fall back to the REST API:

| Action | Method | Route | Required Fields |
|---|---|---|---|
| Read state | GET | `/api/state` | — |
| Find (board map) | GET | `/api/find` | — (optional: `?q=`, `?milestoneId=`, `?list=`) |
| Create chart | POST | `/api/charts` | `boardId`, `title`; opt: `markdown`, `description` |
| Create milestone | POST | `/api/milestones` | `boardId`, `title`, `code` |
| Create card | POST | `/api/cards` | `boardId`, `milestoneId`, `listId`, `title`; opt: `priority` (P0-P3), `kind` (task|bug) |
| Update card | PATCH | `/api/cards/{id}` | `boardId`; opt: `listId`, `title`, `priority`, `kind` |
| Move card | POST | `/api/cards/{id}/move` | `listId` |
| Delete card | DELETE | `/api/cards/{id}` | — |
| Write findings | POST | `/api/milestones/{id}/artifacts` | `boardId`, `artifactType:findings`, `title`, `summary`, `body` |
| Write outcomes | POST | `/api/milestones/{id}/artifacts` | `boardId`, `artifactType:outcomes`, `title`, `summary`, `body` |
| Write memory | POST | `/api/memory/events` | `memoryKey`, `value`, `sourceType`, `eventType:upsert` |
| Query memory | GET | `/api/memory/query` | `?q=` (key prefix) |

## Discrete Context Windows

Each MCD contract card is a discrete context window. Treat each card as an isolated task.

**Task start (fresh session):**
1. `GET /api/find` (or `GET /api/state`) to resolve active board + milestone.
2. `GET /api/memory/query?key=task.{issueNumber}.handoff` to load prior handoff state if it exists.

**Task completion (before ending session):**
```
POST /api/memory/events
{
  "memoryKey": "task.{issueNumber}.handoff",
  "eventType": "upsert",
  "sourceType": "verified-system",
  "bucket": "ref",
  "ttlSeconds": 604800,
  "value": {
    "issueNumber": "...",
    "cardTitle": "...",
    "completedAt": "...",
    "outcomeArtifactId": "... or null",
    "summary": "1-2 sentence completion summary",
    "residualNotes": "anything the next session should know"
  }
}
```

