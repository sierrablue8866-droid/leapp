# EVALUATE · Sierra

**Phase:** 1 (Research & Scoping)
**Status:** Canonical Instruction Set
**Codename:** `Sie`

## When to Use
Invoke this command when starting a new milestone, feature, or complex bug fix. This phase is for understanding the "Why" and "What" before deciding "How".

## Inputs
- [ ] Project Charter
- [ ] High-Level PRD
- [ ] Current Architecture (Architecture Primitives)
- [ ] Governance Guardrails
- [ ] Target board + milestone context

## Instructions
1. **Research**: Analyze the codebase and existing documentation relevant to the user request.
2. **Gap Analysis**: Identify what is missing or what needs to change in the current system.
3. **Scoping**: Define boundaries. What is in-scope? What is strictly out-of-scope?
4. **Primitive Review**: Determine whether new Architecture Primitives are required.
5. **Findings Presentation**: Present detailed findings in chat (research summary, gaps, scoping boundaries, assumptions). Findings will be persisted to DB during CONTRACT phase.
6. **Phase Isolation**: Do not draft implementation details beyond scoping in this phase.

**CRITICAL AGENT INSTRUCTION:** Findings are presented in chat and remain in chat context pending CONTRACT phase. Do not write to DB during EVALUATE; findings become canonical only when written during CONTRACT card creation.

**CRITICAL AGENT INSTRUCTION:** After presenting findings in chat, halt execution and request explicit `/contract` authorization to proceed with contract creation and canonical findings write.

## Output
- [ ] Detailed findings presented in chat (research, gaps, scoping, assumptions).
- [ ] Scope summary with target milestone context ready for CONTRACT card creation.
- [ ] (Optional) New or revised Architecture Primitives.
- [ ] Chat context preserved for CONTRACT phase (findings not yet persisted to DB).
