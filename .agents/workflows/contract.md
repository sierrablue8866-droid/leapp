---
name: contract
description: "Run MCD CONTRACT command for Sierra"
---

# CONTRACT

This workflow invokes the canonical MCD CONTRACT command.

1. Read the command instructions:
[CONTRACT.md](file:///${projectRoot}/.amphion/control-plane/mcd/CONTRACT.md)

2. Follow the step-by-step instructions in the file to complete the phase.

3. If launched from the Command Deck dashboard, run the deterministic memory intent hook first:
   - Write `phase.intent.contract` via `POST /api/memory/events` using `sourceType: verified-system`.
