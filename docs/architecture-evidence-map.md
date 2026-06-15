# Architecture Guide - Semiconductor Ops Platform

Updated: 2026-05-30

Use this page as the short path through the repository. It keeps the architecture grounded in the code, docs, commands, and boundaries that are already present.

## Summary

| Field | Notes |
|---|---|
| Lane | B2B manufacturing operations |
| Core idea | Dual-domain operations control tower with shift handoff, release gating, and resource-pack evidence. |
| Primary reader | Fab operations leaders, process engineers, manufacturing IT, and field response teams. |
| Stack | Python, Terraform, Docker |

## Open First

1. Start with the README fast path and architecture section.
2. Open `docs/service-launch-playbook.md` only when architectureing the product or service angle.
3. Check the commands below before making claims about quality.
4. Skim the CI workflows and fixture data before deeper implementation architecture.
5. Read the boundaries section before presenting the project externally.

## Checks

| Purpose | Command |
|---|---|
| Full local gate | `make verify` |
| Test suite | `make test` |

## CI

- .github/workflows/architecture-blueprint.yml
- .github/workflows/ci.yml
- .github/workflows/dependency-architecture.yml
- .github/workflows/pages-auto-deploy.yml
- .github/workflows/repository-health.yml
- .github/workflows/repository-surface.yml
- .github/workflows/secret-scan.yml

## Evidence

- pytest/ruff-style local verification path
- infrastructure-as-code architecture surface
- containerized delivery path
- make verify passes
- Architecture-pack artifacts exist
- Staged process data is clear

## Architecture Notes

| Possible offer | Working scope assumption |
|---|---|
| Factory control-tower pilot | Scope after product intake |
| Yield architecture workshop | operator-approved implementation diagnostic |
| Operator dashboard starter kit | Scope after product intake |

## Boundaries

- MES/SCADA integration requires controls
- No production claims from staged data
- Operator authority must be mapped

## Useful Metrics

- Handoff completeness
- Alarm triage time
- Release gate accuracy
