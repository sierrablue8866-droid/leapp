# The Micro-Contract Development (MCD) Playbook: Operator's Guide

Welcome directly to the **Command Deck**. This platform operates on the Micro-Contract Development (MCD) methodology. MCD is designed for solo operators working alongside advanced AI agents in modern IDEs like Windsurf and Cursor.

The core philosophy is **Deterministic Versioning**: zero hallucination, zero scope creep, and total traceability. Every code change must be explicitly authorized by board-authored contract records.

## The "Halt and Prompt" Safety Rail
An AI agent completing a phase must halt, present results, and request explicit authorization for the next phase.

---

## The 4-Phase Sequence & IDE Slash Commands

### 1. `@[/evaluate]`
*Understand before building.*
- **Action**: Assess current state and scope required changes.
- **Output**: Milestone `findings` artifact written through Command Deck API (DB canonical).
- **Rule**: No implementation changes during Evaluate.

### 2. `@[/contract]`
*Authorize the work.*
- **Action**: Write milestone contract metadata and sequenced micro-contract cards on the board.
- **Output**: Milestone-bound contract card set (issue-numbered, acceptance-bound).
- **Rule**: If board/API runtime is unavailable, halt as blocked; chat text cannot substitute for canonical contracts.

### 3. `@[/execute]`
*Build to specification.*
- **Action**: Implement only authorized AFP scope from approved board contract cards.
- **Rule**: If scope must change, halt and return to Contract.

### 4. `@[/closeout]`
*Formalize the release.*
- **Action**: Verify acceptance, archive milestone, append outcomes, and commit when applicable.
- **Output**:
  1. Outcomes artifact appended in DB.
  2. Milestone archived/closed in board runtime.
  3. DB memory state updated through `/api/memory/*`.
  4. Strict `closeout: {description}` Git Commit.

---

## Utility Command: `@[/remember]`
`/remember` is a utility checkpoint, not a lifecycle phase.

- **Purpose**: Capture compact operational context through `/api/memory/*`.
- **Rule**: `/remember` does not transition lifecycle phase and does not authorize code changes by itself.

---

## Core Operational Rules (`GUARDRAILS.md`)
1. **Local Only**: MCD runs locally.
2. **Mermaid.js Required**: Architecture docs use Mermaid.
3. **Immutability**: Remediation of closed/archived scope requires a fresh Evaluate -> Contract pipeline.
