# HELP · Sierra

**Type:** Utility Command (Non-Phase)
**Status:** Canonical Instruction Set
**Codename:** `Sie`

## When to Use
Invoke this command when the operator asks for guidance on AmphionAgent usage or the MCD methodology.

## Inputs
- [ ] User help request
- [ ] Canonical help source: `.amphion/control-plane/MCD_HELP_SOURCE.md`
- [ ] Governance context: `.amphion/control-plane/GUARDRAILS.md`

## Instructions
1. **Load Canonical Source**: Read `.amphion/control-plane/MCD_HELP_SOURCE.md` before answering.
2. **Answer Grounded in Source**: Use the canonical help source as the primary authority for MCD and AmphionAgent guidance.
3. **Fallback Sources**: If required details are missing, use `.amphion/control-plane/MCD_PLAYBOOK.md` and `.amphion/control-plane/GUARDRAILS.md`.
4. **Response Quality**: Provide direct, actionable help. Clearly label assumptions.
5. **No Side Effects**: Do not modify board state, files, or lifecycle phase while serving `/help`.

## Output
- [ ] Operator receives a concise answer grounded in canonical local help sources.
