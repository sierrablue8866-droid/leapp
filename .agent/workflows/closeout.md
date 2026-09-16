---
name: closeout
description: "Run MCD CLOSEOUT command for Sierra"
---

# CLOSEOUT

This workflow invokes the canonical MCD CLOSEOUT command.

1. Read the command instructions:
[CLOSEOUT.md](file:///${projectRoot}/.amphion/control-plane/mcd/CLOSEOUT.md)

2. Follow the step-by-step instructions in the file to complete the phase.

3. If launched from the Command Deck dashboard, run the deterministic memory intent hook first:
   - Write `phase.intent.closeout` via `POST /api/memory/events` using `sourceType: verified-system`.
