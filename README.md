# Semiconductor Ops Platform

[![CI](https://github.com/KIM3310/fab-ops-yield-control-tower/actions/workflows/ci.yml/badge.svg)](https://github.com/KIM3310/fab-ops-yield-control-tower/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688.svg)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Unified manufacturing operations platform for semiconductor environments. Two production domains in a single FastAPI application with shared infrastructure, SQLite persistence, Prometheus metrics, and multi-cloud deployment.

Technical review pack: [`docs/technical-review-pack.md`](docs/technical-review-pack.md)

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
make install
source .venv/bin/activate
uvicorn app.main:app --reload
# App:     http://127.0.0.1:8000
# Docs:    http://127.0.0.1:8000/docs
# Metrics: http://127.0.0.1:8000/metrics
```

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

**AWS** — set `AWS_ACCESS_KEY_ID` to activate: S3 handoff/audit export, DynamoDB metadata, SQS event publishing.

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

This repository includes a neutral cloud and AI engineering blueprint that maps the current proof surface to runtime boundaries, data contracts, model-risk controls, deployment posture, and validation hooks.

- [Cloud + AI architecture blueprint](docs/cloud-ai-architecture.md)
- [Machine-readable architecture manifest](docs/architecture/blueprint.json)
- Validation command: `python3 scripts/validate_architecture_blueprint.py`
