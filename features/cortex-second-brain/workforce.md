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
- [x] Phase 2 — Design + Research (9 user stories; 9 OQs flagged from research)
- [x] Phase 3 — Critique (ALL 17 BLOCKING items RESOLVED Round 2; 6 CONCERN folded; 3 NIT acknowledged)
- [>] Phase 4 — Coding (TDD)
  - [>] Coding Phase 0 — us-1-foundation (in progress)
  - [ ] Coding Phase 1 — us-2-ai-pipeline
  - [ ] Coding Phase 2 — us-3-frontend-setup
  - [ ] Coding Phase 3 — us-4-voice-ux-offline
  - [ ] Coding Phase 4 — us-5-deployment
  - [ ] Coding Phase 5 — us-6-insights · us-7-personal-dictionary · us-9-realtime-stt (parallel)
  - [ ] Coding Phase 6 — us-8-shadow-reader
- [ ] Phase 5 — Review (with spec auditor)

## Open Questions Surfaced by Researcher (must be resolved before Phase 4)
- OQ-1 (BLOCKING): Azure OpenAI not in westus2 — needs separate `openaiLocation` Bicep param
- OQ-2 (HIGH): `python-jose==3.3.*` CVE-2024-33663/33664 — bump to ≥3.5 or switch to `pyjwt`
- OQ-4 (MEDIUM): `passlib[bcrypt]==1.7.*` breaks on bcrypt ≥4.1
- OQ-5 (HIGH): missing Postgres firewall rule in Bicep
- OQ-7 (HIGH): missing `Microsoft.App/containerApps` resource in Bicep
- OQ-9 (HIGH): pgvector extension is named `vector` not `pgvector` in `CREATE EXTENSION`
- OQ-3, OQ-6, OQ-8: low-severity version-bump recommendations

## Current State
**Active phase:** 4 — Coding (Phase 0: us-1-foundation)
**Active agents:** coder-us-1-foundation, tester-us-1-foundation (TDD pair)
**Waiting for:** `Coder done: features/cortex-second-brain/tasks/us-1-foundation.tasks.md` AND `Tester done: features/cortex-second-brain/tasks/us-1-foundation.tasks.md`

## Review Base Commit
3851ee8bb7af66aeccdc589eabea76577601660e
