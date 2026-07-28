# Semiconductor Ops Platform

[![CI](https://github.com/KIM3310/fab-ops-yield-control-tower/actions/workflows/ci.yml/badge.svg)](https://github.com/KIM3310/fab-ops-yield-control-tower/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.133.0-009688.svg)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Unified manufacturing operations platform for semiconductor environments. Two production domains in a single FastAPI application with shared infrastructure, SQLite persistence, Prometheus metrics, and multi-cloud deployment.

Technical review pack: [`docs/architecture-pack.md`](docs/architecture-pack.md)

## System Overview

A semiconductor operations control tower that connects fab monitoring, qualification, and shift evidence into one reviewable system.

| Area | Details |
|---|---|
| Users | Manufacturing IT teams, fab operations leaders, process engineers, and industrial analytics groups. |
| Technical path | Validate the demo, README, architecture notes, and quality gate before deeper workflow review. |
| System scope | Fab monitoring, scanner qualification, dual-domain analytics, release gating, and review material. |
| Operating boundary | Uses staged data and operator workflows; production connection requires MES/SCADA access control and change governance. |
| Evaluation path | Run the documented runtime commands and inspect review artifacts and staged process data. |

## Evaluation Path

- **Start here:** Open `/api/resource-pack`, then compare Fab Ops and Scanner Field routes.
- **Local demo:** Run `make run`, then open `http://127.0.0.1:8000/docs`.
- **Checks:** Run `make verify` for the standard gate or `make verify-strict` before presenting it as production-quality evidence.

## Service Launch Playbook

- [Service launch playbook](docs/service-launch-playbook.md) maps the repository to its product scope, operating gates, operating boundaries, and risk controls.

## Architecture Notes

- [Review guide](docs/architecture-evidence-map.md) summarizes the system scope, first files to inspect, verification commands, and known boundaries.
- [Quality notes](docs/quality-gate.md) lists the local checks, CI surface, and release expectations for this repository.
- [Enterprise readiness notes](docs/enterprise-readiness.md) outlines security, data, operations, integration, and handoff expectations.

## Domains

**Fab Ops Yield Control Tower** (`/api/fab-ops/`) — alarm triage, lot-at-risk prioritization, tool ownership tracking, release gate decisions, recovery board, and signed shift handoff.

**Scanner Field Response** (`/api/scanner/`) — field incident workflow, subsystem escalation, qualification review, and signed handoff from local triage through customer milestone readiness.

Both domains share operator access, HMAC signature logic, and runtime storage from `app/shared/` — zero duplication, per-domain environment variable isolation.

## Architecture

```
Load Balancer / CDN
     ↓
FastAPI Application  (/docs  /health  /metrics)
     ↓                        ↓
Fab Ops Yield            Scanner Field
Control Tower            Response
/api/fab-ops/*           /api/scanner/*
     ↓                        ↓
Shared Infrastructure (auth, signatures, runtime_store, database)
     ↓              ↓              ↓
  SQLite          S3 (export)   SQS (events)
```

## Quick Start

```bash
git clone https://github.com/KIM3310/fab-ops-yield-control-tower.git && cd fab-ops-yield-control-tower
make run
# App:     http://127.0.0.1:8000
# Docs:    http://127.0.0.1:8000/docs
# Metrics: http://127.0.0.1:8000/metrics
```

Requires Python 3.11+. If your default `python3` is older, run `make PYTHON_BIN=/path/to/python3.11 verify`.

Docker:
```bash
make docker-build && make docker-run
```

Kubernetes:
```bash
make deploy  # applies infra/k8s/ manifests
```

## Core API

**Platform**

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Platform health and domain navigation |
| `GET /metrics` | Prometheus metrics |
| `GET /api/resource-pack` | Built-in manufacturing review cases |

**Fab Ops** (`/api/fab-ops/`)

| Endpoint | Description |
|----------|-------------|
| `GET /api/fab-ops/alarms` | Active alarms |
| `GET /api/fab-ops/lots/at-risk` | Lots at risk by yield score |
| `GET /api/fab-ops/release-gate` | Release gate decision (auth) |
| `GET /api/fab-ops/recovery-board` | Recovery board (hold/watch/ready) |
| `GET /api/fab-ops/shift-handoff/signature` | Signed shift handoff envelope (auth) |
| `GET /api/fab-ops/audit/feed` | Audit event feed |

**Scanner** (`/api/scanner/`)

| Endpoint | Description |
|----------|-------------|
| `GET /api/scanner/incidents` | Field incidents (filterable) |
| `GET /api/scanner/field-response-board` | Field response board |
| `GET /api/scanner/subsystem-escalation` | Subsystem escalation detail |
| `GET /api/scanner/qualification-board` | Qualification review board |
| `GET /api/scanner/customer-readiness` | Customer milestone readiness |
| `GET /api/scanner/shift-handoff/signature` | Signed handoff envelope (auth) |

## Deployment

**AWS** — set both `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` to enable AWS exports. S3 uses `AWS_S3_BUCKET` when supplied and otherwise uses the documented default. SQS additionally requires `AWS_SQS_QUEUE_URL`; DynamoDB additionally requires `AWS_DYNAMODB_TABLE`. `AWS_DEFAULT_REGION` is optional and defaults to `us-west-2`.

**GCP Cloud Run** — Terraform config in `infra/terraform/`:
```bash
cd infra/terraform
terraform init && terraform plan -var="project_id=my-gcp-project" && terraform apply
```

**Kubernetes** — manifests in `infra/k8s/`: 2-replica deployment, HPA (2–8 pods), ClusterIP service.

## Tech Stack

Python · FastAPI · SQLAlchemy · SQLite · Prometheus · AWS (S3, DynamoDB, SQS) · GCP Cloud Run · Kubernetes · Terraform · Docker

## License

MIT

## Cloud + AI Architecture

- [Cloud + AI architecture blueprint](docs/cloud-ai-architecture.md)
- [Machine-readable architecture manifest](docs/architecture/blueprint.json)
- Validation command: `python3 scripts/validate_architecture_blueprint.py`

## Enterprise Productization

- [Product operating model](docs/product-operating-model.md) defines the product scope, trust boundary, operating checks, and service path for this repository.

## System Architecture

- [System architecture](docs/system-architecture.md) maps the runtime boundary, data/control flow, cloud or local deployment surface, and operating assumptions for this repository.

## Service Architecture

- [Service architecture](docs/service-architecture.md) defines the cloud resources, account information, cost controls, and production guardrails needed to turn this repo into a scoped service without publishing public financial assumptions.

<!-- search-growth-readme:start -->

## Search And Service Surface

- Public entry: public synthetic fab demo and operating model
- Paid boundary: paid factory pilot workspace with private connectors and shift report export
- Canonical URL: https://fab-ops-yield-control-tower.pages.dev/
- Lead capture: https://kim3310-doeon-kim-portfolio.pages.dev/?offer=fab-ops-yield-control-tower&inquiry=industrial-validation-discovery#private-inquiry
- Commercial route: https://kim3310-doeon-kim-portfolio.pages.dev/?offer=fab-ops-yield-control-tower#service-offers
- Machine-readable offer: [docs/service-offer.json](docs/service-offer.json)
- Search growth implementation: [docs/search-growth-implementation.md](docs/search-growth-implementation.md)
- Revenue architecture: [docs/revenue-architecture.md](docs/revenue-architecture.md)

<!-- search-growth-readme:end -->
