# Workforce Session: cortex-second-brain

**CRITICAL — Session Recovery**: If resuming a session or resuming after context compaction, this file **MUST** be read before acting.

**CRITICAL — Spawn Protocol**: All agents **MUST** be spawned with the `Agent` tool, `team_name: "cortex-second-brain"`, and **NO** `subagent_type`.

## Project Root

**All work happens under**: `C:\Users\karths\dev\Projects\cortex\`

- Specs: `SECOND_BRAIN_BUILD_SPEC.md`, `SECOND_BRAIN_BUILD_SPEC_ADDENDUM.md`
- Workforce artifacts: `features/cortex-second-brain/`
- Source: `frontend/`, `backend/`, `infra/`, `docs/`, `.github/`
- Tests: `backend/tests/`, `frontend/tests/`, `frontend/src/__tests__/`

## Resolved Agents

| Role | Agent | Path |
|------|-------|------|
| requirements | pm | bic-engineering-agents/bic-common-workforce/1.1.0/agents/pm.md |
| design | architect | bic-engineering-agents/bic-common-workforce/1.1.0/agents/architect.md |
| research | researcher | bic-engineering-agents/bic-common-workforce/1.1.0/agents/researcher.md |
| critique | critic | bic-engineering-agents/bic-common-workforce/1.1.0/agents/critic.md |
| coding | coder | bic-engineering-agents/bic-common-workforce/1.1.0/agents/coder.md |
| testing | tester | bic-engineering-agents/bic-common-workforce/1.1.0/agents/tester.md |
| review | reviewer-security | bic-engineering-agents/bic-common-workforce/1.1.0/agents/reviewer-security.md |
| review | reviewer-performance | bic-engineering-agents/bic-common-workforce/1.1.0/agents/reviewer-performance.md |
| review | reviewer-quality | bic-engineering-agents/bic-common-workforce/1.1.0/agents/reviewer-quality.md |
| review | reviewer-spec-auditor | ./.claude/agents/reviewer-spec-auditor.md |

## Resolved Code Paths
- Coder: `frontend/`, `backend/`, `infra/`, `docs/`, `.github/`
- Tester: `backend/tests/`, `frontend/tests/`, `frontend/src/__tests__/`

## Review Config
| Reviewer | Section Heading | Autofix Threshold |
|----------|----------------|-------------------|
| reviewer-security | Security Findings | BLOCKING, HIGH, MEDIUM |
| reviewer-performance | Performance Findings | BLOCKING, HIGH, MEDIUM |
| reviewer-quality | Quality Findings | BLOCKING, HIGH, MEDIUM |
| reviewer-spec-auditor | Spec Auditor Findings | BLOCKING, HIGH, MEDIUM |

## Phase Status
- [x] Phase 1 — Requirements (COMPLEX: 23 stories)
- [>] Phase 2 — Design + Research
- [ ] Phase 3 — Critique
- [ ] Phase 4 — Coding (Phase 1 MVP items 1-21, then Phase 2 items 22-34)
- [ ] Phase 5 — Review (with spec auditor)

## Current State
**Active phase:** 2 — Design + Research
**Active agents:** architect, researcher (teammates)
**Waiting for:** `Architect complete: /features/cortex-second-brain/designs/design.md and /features/cortex-second-brain/tasks/` AND `researcher complete: features/cortex-second-brain/designs/research.md`

## Review Base Commit
<!-- Written when Phase 5 begins -->
TBD
