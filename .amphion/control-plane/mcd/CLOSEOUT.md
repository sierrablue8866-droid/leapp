# CLOSEOUT · Sierra

**Phase:** 4 (Archiving & Release)
**Status:** Canonical Instruction Set
**Codename:** `Sie`

## When to Use
Invoke this command when all contracted work for a version is verified and complete.

## Inputs
- [ ] All executed contracts for the version
- [ ] Verification evidence
- [ ] Final repository state
- [ ] DB-backed memory baseline (`/api/memory/state`)

## Instructions
1. **Milestone Closeout**: Close/archive the milestone through API; outcomes artifact is appended in DB.
2. **Memory Update**: Write closeout memory events through `/api/memory/events` and verify via `/api/memory/state` or `/api/memory/query`.
3. **Validation**: Run final governance and hygiene checks.
4. **Record Keeping**: Ensure outcomes artifact provenance is complete.
5. **Persistence**: Commit required source/runtime changes when applicable.
6. **Versioning**: Tag/finalize version metadata only when explicitly in scope.

## Output
- [ ] Outcomes artifact recorded for milestone closeout in DB.
- [ ] DB-backed memory checkpoint validated (`/api/memory/*`).
- [ ] Final Git commit using the `closeout:` prefix.
