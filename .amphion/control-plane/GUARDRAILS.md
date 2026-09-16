# Sierra - Governance Guardrails

Codename: `Sie`
Initial Version: `0.1.0`

## Execution Model
All work follows this strict sequence:
1. Evaluate
2. Contract
3. Execute
4. Closeout

No phase skipping is permitted.

## Phase Rules
### 1) Evaluate
- Define objective, scope, constraints, and assumptions.
- Do not produce implementation code in this phase.
- Findings are canonical only when written as milestone artifacts in DB.

### 2) Contract
- Contract authority is board-native and DB-canonical.
- Contracts must be milestone-bound card sets with acceptance criteria and AFP scope.
- Chat summaries are informational only and never replace board contracts.
- If board/API runtime is unavailable, contract phase halts as blocked.

### 3) Execute
- Implement only what approved board contract cards authorize.
- Keep versioning and build naming deterministic.
- Record meaningful outcomes in DB artifacts.

### 4) Closeout
- Closeout requires completed scope verification and outcomes recorded in DB.
- `/closeout` is required to finalize a version; `/remember` cannot replace lifecycle closeout.

## Utility Commands
### `/remember` (Utility-Only)
- `/remember` writes compact operational memory through `/api/memory/*`.
- `/remember` must not auto-advance lifecycle or execute code changes.

## Agent Memory Policy
- Canonical memory authority: SQLite (`.amphion/command-deck/data/amphion.db`) via `/api/memory/*`.
- Canonical write boundary: API-mediated writes only.
- Memory model: append-only event log + deterministic LWW materialized state + bounded compaction.

## Closeout Procedure
A version is not closed until:
1. Contract cards in scope are executed/reviewed.
2. Compliance checklist passes.
3. Outcomes artifact exists in milestone artifacts.
4. Required source/runtime artifacts are staged.
5. `closeout:` commit is completed when in scope.

## Commit Message Format
```
closeout: {VERSION} {brief description}
```

## Document Naming Convention
Project documents use:
```
YYYYMMDDHHMM-[DOCUMENT_TITLE].md
```
Exception: `GUARDRAILS.md` keeps stable basename.

## Documentation Standards
- Architecture diagrams and flowcharts use `Mermaid.js`.

## Change Safety
- Core modifications require referenced active board contract cards.
- Uncontracted work is deferred until contract approval.
- Unexpected repository changes are surfaced before continuing.

## Compliance Checklist
- [ ] Current phase is explicit.
- [ ] Approved board contract cards exist for core-file changes.
- [ ] Work matches approved board contract scope.
- [ ] Naming/versioning remains deterministic.
- [ ] Conflicts with active contracts have been flagged.
- [ ] Agent memory updated and validated via `/api/memory/*`.
- [ ] Outcomes artifact exists for closed milestone/version.
- [ ] Git commit completed with all artifacts staged (when closing a version).
