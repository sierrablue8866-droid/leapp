# REMEMBER · Sierra

**Type:** Utility Command (Non-Phase)
**Status:** Canonical Instruction Set
**Codename:** `Sie`

## When to Use
Use this command to capture a compact memory checkpoint without changing lifecycle phase.

## Inputs
- [ ] Current contract context (if any)
- [ ] Durable decisions/troubleshooting outcomes worth preserving
- [ ] Current milestone/slice identifier

## Instructions
1. **Resolve Board Context**: Use active board context (or explicit `boardId`) as memory scope authority.
2. **Write Memory Events**: Record checkpoint facts via `POST /api/memory/events` with attested `sourceType` (`user`, `operator`, `verified-system`) and deterministic `memoryKey`.
3. **Materialized State Check**: Validate checkpoint presence via `GET /api/memory/state` or `GET /api/memory/query`.
4. **Compaction Control**: If needed, run `POST /api/memory/compact` to enforce bounded memory budgets.
5. **No Phase Transition**: Confirm checkpoint completion and remain in current lifecycle phase.

## Guardrails
- `/remember` is utility-only and cannot replace Evaluate/Contract/Execute/Closeout.
- Canonical write boundary is `/api/memory/*` routes; avoid direct SQL mutation as standard workflow.
- Do not include long prose; use short slug-like entries.
- Do not write speculative or unverified facts into memory.

## Output
- [ ] Memory event(s) recorded in SQLite authority via `/api/memory/events`.
- [ ] Memory state verification evidence (`/api/memory/state` or `/api/memory/query`).
- [ ] Brief user-facing confirmation that memory checkpoint was recorded.
