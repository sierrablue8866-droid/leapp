---
name: execute
description: "Run MCD EXECUTE command for Sierra"
---

# EXECUTE

This workflow invokes the canonical MCD EXECUTE command.

1. Read the command instructions:
[EXECUTE.md](file:///${projectRoot}/.amphion/control-plane/mcd/EXECUTE.md)

2. Follow the step-by-step instructions in the file to complete the phase.

3. If launched from the Command Deck dashboard, run the deterministic memory intent hook first:
   - Write `phase.intent.execute` via `POST /api/memory/events` using `sourceType: verified-system`.
