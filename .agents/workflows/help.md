---
name: help
description: "Provide MCD and AmphionAgent help using .amphion/control-plane/MCD_HELP_SOURCE.md"
---

# HELP

This workflow invokes the canonical MCD HELP command.

1. Read the command instructions:
[HELP.md](file:///${projectRoot}/.amphion/control-plane/mcd/HELP.md)

2. Follow the step-by-step instructions in the file to complete the phase.

3. If launched from the Command Deck dashboard, run the deterministic memory intent hook first:
   - Write `phase.intent.help` via `POST /api/memory/events` using `sourceType: verified-system`.
