---
name: bug
description: "Run MCD BUG command for Sierra"
---

# BUG

This workflow handles the creation of a new bug card on the active Command Deck board.

1. Ensure you have the context of the bug (title and description) from the user's request.
2. Obtain the ID of the active board and active milestone. **CRITICAL: The bug card MUST be connected to the current active milestone.**
3. Create a new card via `POST /api/cards` with `kind` set to `bug` and `milestoneId` set appropriately.
4. If testing or verification is needed, outline or execute the steps.
5. Provide the user with the issue number of the newly created bug card.
