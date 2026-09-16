# CONTRACT · Sierra

**Phase:** 2 (Planning & Agreement)
**Status:** Canonical Instruction Set
**Codename:** `Sie`

## When to Use
Invoke this command after Evaluate is complete and scope is locked. This phase defines the implementation "How" and secures operator approval before execution.

## Inputs
- [ ] Evaluation findings (from chat context of prior EVALUATE session)
- [ ] Active board context
- [ ] Target milestone (new milestone for net-new work)
- [ ] Affected File Paths (AFPs)

## Instructions
1. **Runtime Gate**: Confirm Command Deck API is reachable and board context resolves.
2. **Blocked Behavior**: If API/board is unavailable, halt as blocked. Do not emit a chat-only or file-only contract as authority.
3. **Canonical Findings Write (Required)**: Write findings artifact to DB via API (`artifactType: findings`) using evaluated findings from chat context. This is the canonical persistence point.
4. **Macro Contract Metadata**: Populate milestone-level contract metadata (`metaContract`, `goals`, `nonGoals`, `risks`).
5. **Micro-Contract Cards (Required)**: Create/update sequenced contract cards on board, each milestone-bound and acceptance-driven.
6. **AFP Enumeration**: Include exact files to be created/modified/deleted in card descriptions/acceptance.
7. **Risk Coverage**: Explicitly capture side effects and failure handling in contract scope.
8. **Approval Handoff**: Present milestone ID + issue-numbered contract cards for formal operator approval.
9. **Trigger-Based Execution**: `/execute` may begin only after explicit approval of the board-authored contract set.

**CRITICAL AGENT INSTRUCTION:** Findings become canonical when written to DB during this phase. Once findings are persisted and contract cards authored, they are the sole execution authority.

**CRITICAL AGENT INSTRUCTION:** After canonical findings write and contract cards are authored and presented, halt and await explicit `/execute` authorization.

## Output
- [ ] Findings artifact recorded in DB milestone artifacts (canonical persistence).
- [ ] Approved, milestone-bound contract card set on board (DB canonical).
- [ ] Milestone contract metadata recorded.
- [ ] Operator-facing summary with milestone ID + issue IDs.
