# EXECUTE · Sierra

**Phase:** 3 (Implementation & Verification)
**Status:** Canonical Instruction Set
**Codename:** `Sie`

## When to Use
Invoke this command ONLY when approved contract cards exist on the board for the active milestone.

## Inputs
- [ ] Approved Contract Cards
- [ ] Current Repository State
- [ ] Test Harness / Environment

## Instructions
1. **Implementation**: Execute the changes exactly as authorized by the contract. Do not deviate from the Approved AFPs.
2. **Verification**: Run all automated tests and perform manual validation as defined in the contract's Verification Plan.
3. **Iteration**: Fix bugs discovered during verification. If a fundamental design change is needed, stop and return to the Contract phase.
4. **Documentation**: Record outcomes and build details in milestone/card DB artifacts, and write local files only when explicitly required by tooling.

## Output
- [ ] Verified implementation matching all acceptance criteria.
- [ ] Card status + milestone context updated to reflect execution outcome.
