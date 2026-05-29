# Reviewer Evidence Map - Semiconductor Ops Platform

Updated: 2026-05-29

This document is the short path for a technical reviewer, engineering leader, product evaluator, or buyer who wants to understand what this repository proves without wandering through every file.

## One-Line Proof

**B2B manufacturing operations.** Dual-domain operations control tower with shift handoff, release gating, and resource-pack evidence.

## Audience and Commercial Angle

| Lens | Answer |
|---|---|
| Primary reviewer | Fab operations leaders, process engineers, manufacturing IT, and field response teams. |
| Technical signal | Can the project be explained, verified, bounded, and extended like a real product surface? |
| Buyer signal | Is there a narrow operational pain, a runnable proof path, and a risk-aware pilot shape? |
| Stack signal | Python, Terraform, Docker |

## Seven-Minute Review Route

1. Read the README `Product and Review Surface` and `Reviewer Fast Path` sections.
2. Open `docs/monetization-playbook.md` to understand the buyer, offer ladder, and GTM hypothesis.
3. Run or inspect the strongest local quality gate below.
4. Inspect CI workflow definitions and test fixtures before deeper implementation review.
5. Check the risk boundaries so claims stay credible and not overextended.

## Verification Commands

| Purpose | Command |
|---|---|
| Full local gate | `make verify` |
| Test suite | `make test` |

## CI and Automation Surface

- .github/workflows/architecture-blueprint.yml
- .github/workflows/ci.yml
- .github/workflows/dependency-review.yml
- .github/workflows/pages-auto-deploy.yml
- .github/workflows/repository-health.yml
- .github/workflows/repository-surface.yml
- .github/workflows/secret-scan.yml

## Evidence Inventory

- pytest/ruff-style local verification path
- infrastructure-as-code review surface
- containerized delivery path
- make verify passes
- Review-pack artifacts exist
- Staged process data is clear

## Commercialization Snapshot

| Offer | Pricing hypothesis |
|---|---|
| Factory control-tower pilot | $8k-$25k workshop |
| Yield review workshop | $30k-$100k pilot |
| Operator dashboard starter kit | $5k-$20k/month ops analytics support |

## Risk Boundaries

- MES/SCADA integration requires controls
- No production claims from staged data
- Operator authority must be mapped

## Metrics That Matter

- Handoff completeness
- Alarm triage time
- Release gate accuracy

## Review Verdict

This repository should be evaluated as part of the broader KIM3310 portfolio: it is strongest when the reviewer sees the link between a concrete implementation, a documented verification path, and an externally credible operating story.
