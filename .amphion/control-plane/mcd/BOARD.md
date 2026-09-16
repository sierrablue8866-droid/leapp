# BOARD · Sierra

**Status:** Deprecated Lifecycle Command
**Codename:** `Sie`

## Canonical Change
`BOARD` is no longer a first-class lifecycle phase.

Canonical lifecycle:
1. Evaluate
2. Contract
3. Execute
4. Closeout

## Replacement Behavior
Board population is mandatory work embedded in `CONTRACT`:
- Create/update sequenced task cards via API/SQLite runtime.
- Bind all cards to active milestones.
- Verify visibility in `/api/state` and board UI.

## Operator Guidance
If `/board` is invoked, route to `/contract` behavior and continue with Contract-based task population.
