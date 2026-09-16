---
name: remember
description: "Capture a compact memory checkpoint for Sierra without phase transition"
---

# REMEMBER

This workflow invokes the canonical MCD REMEMBER command.

1. Read the command instructions:
[REMEMBER.md](file:///${projectRoot}/.amphion/control-plane/mcd/REMEMBER.md)

2. Follow the step-by-step instructions in the file to complete the phase.

3. If launched from the Command Deck dashboard, run the deterministic memory intent hook first:
   - Write `phase.intent.remember` via `POST /api/memory/events` using `sourceType: verified-system`.
