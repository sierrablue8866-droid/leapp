---
name: docs
description: "Generate Project Strategy (Charter & PRD) from source documents for Sierra"
---

# DOCS

This command automates the derivation of your Project Strategy (Charter and High-Level PRD).

1.  **Read Source Documents**: Read every file in `.amphion/context/`.
2.  **Derive Charter**: Fill every section marked `*[Derive from source documents]*` in the latest Project Charter in `.amphion/control-plane/`. Do not modify the "Operating Constraints" section.
3.  **Read Charter**: Read the completed Project Charter to ensure alignment for the next step.
4.  **Derive PRD**: Fill every section marked `*[Derive from source documents]*` in the latest High-Level PRD in `.amphion/control-plane/`.
5.  **Cleanup**: Remove any remaining stub markers or introductory agent instructions from both the Charter and the PRD.
6.  **Completion**: Once finished, tell the user: "The Project PRD and Strategy documents are complete! Please return to the Onboarding WebUI and click **Complete & Launch Command Deck**."
