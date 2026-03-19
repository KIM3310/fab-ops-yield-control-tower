# Semiconductor Ops Platform

[![CI](https://github.com/KIM3310/fab-ops-yield-control-tower/actions/workflows/ci.yml/badge.svg)](https://github.com/KIM3310/fab-ops-yield-control-tower/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688.svg)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docker](https://img.shields.io/badge/docker-ready-2496ED.svg)](https://ghcr.io/kim3310/fab-ops-yield-control-tower)

A unified manufacturing operations platform for semiconductor environments. Combines two production domains into a single FastAPI application with shared infrastructure, SQLite persistence, Prometheus metrics, and multi-cloud deployment support.

## Architecture

```
                        +---------------------------+
                        |     Load Balancer / CDN   |
                        |    (Cloudflare / ALB)     |
                        +-------------+-------------+
                                      |
                        +-------------v-------------+
                        |   FastAPI Application      |
                        |   /docs  /health  /metrics |
                        +---+-------------------+---+
                            |                   |
              +-------------v---+       +-------v-----------+
              |   Fab Ops       |       |   Scanner Field   |
              |   Yield Control |       |   Response        |
              |   Tower         |       |                   |
              | /api/fab-ops/*  |       | /api/scanner/*    |
              +--------+--------+       +--------+----------+
                       |                         |
              +--------v-------------------------v----------+
              |              Shared Infrastructure          |
              |  operator_access | signatures | runtime_store|
              |  database (SQLite/SQLAlchemy) | aws_adapter |
              +---------------------+-----------------------+
                                    |
                    +---------------+---------------+
                    |               |               |
              +-----v---+   +------v----+   +------v----+
              | SQLite   |   |   S3      |   |   SQS     |
              | (local)  |   | (export)  |   | (events)  |
              +----------+   +-----------+   +-----------+
```

## Domains

### Fab Ops Yield Control Tower (`/api/fab-ops/`)

Manages alarms, lot-at-risk prioritization, tool ownership, release gate decisions, recovery board, and shift handoff in a single operator dashboard. Designed around the workflow: **triage alarm -> assess lot risk -> check tool ownership -> decide release gate -> export signed handoff**.

### Scanner Field Response (`/api/scanner/`)

A semiconductor equipment field-response workflow for field incidents, subsystem escalation, qualification review, and signed handoff. Keeps one scanner incident visible from local triage through qualification review and customer milestone readiness.

## Quick Start

### Local Development

```bash
# Clone and install
git clone https://github.com/KIM3310/fab-ops-yield-control-tower.git
cd fab-ops-yield-control-tower
make install

# Run the server
uvicorn app.main:app --reload

# Open in browser
# App:     http://127.0.0.1:8000
# Docs:    http://127.0.0.1:8000/docs
# ReDoc:   http://127.0.0.1:8000/redoc
# Metrics: http://127.0.0.1:8000/metrics
```

### Docker

```bash
# Build and run
make docker-build
make docker-run

# Or directly:
docker build -t semiconductor-ops-platform .
docker run --rm -p 8000:8000 semiconductor-ops-platform
```

### Kubernetes

```bash
# Apply all manifests (requires kubectl context)
make deploy

# Or step by step:
kubectl apply -f infra/k8s/configmap.yaml
kubectl apply -f infra/k8s/deployment.yaml
kubectl apply -f infra/k8s/service.yaml
kubectl apply -f infra/k8s/hpa.yaml
```

## API Documentation

Interactive docs are available at `/docs` (Swagger UI) and `/redoc` (ReDoc) when the server is running.

### Platform

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Platform health and domain navigation |
| `GET /metrics` | Prometheus metrics (request counts, latencies) |
| `GET /docs` | OpenAPI Swagger UI |

### Fab Ops (`/api/fab-ops/`)

| Endpoint | Description |
|----------|-------------|
| `GET /api/fab-ops/meta` | Domain metadata and diagnostics |
| `GET /api/fab-ops/runtime/brief` | Control tower runtime brief |
| `GET /api/fab-ops/runtime/scorecard` | Aggregated operational metrics |
| `GET /api/fab-ops/review-summary` | Filtered review summary |
| `GET /api/fab-ops/recovery-board` | Recovery board (hold/watch/ready) |
| `GET /api/fab-ops/release-board` | Release board with gate decisions |
| `GET /api/fab-ops/recovery-what-if` | What-if recovery simulation |
| `GET /api/fab-ops/review-pack` | Shift-ready review pack |
| `GET /api/fab-ops/fabs/summary` | Fab operational posture |
| `GET /api/fab-ops/tools` | Tool inventory |
| `GET /api/fab-ops/tool-ownership` | Tool ownership record |
| `GET /api/fab-ops/alarms` | Active alarms |
| `GET /api/fab-ops/lots/at-risk` | Lots at risk by yield score |
| `GET /api/fab-ops/release-gate` | Release gate decision (auth) |
| `GET /api/fab-ops/shift-handoff` | Shift handoff pack (auth) |
| `GET /api/fab-ops/shift-handoff/signature` | Signed handoff envelope (auth) |
| `GET /api/fab-ops/shift-handoff/verify` | Signature verification (auth) |
| `GET /api/fab-ops/audit/feed` | Audit event feed |
| `GET /api/fab-ops/evals/replays` | Replay suite summary |

### Scanner (`/api/scanner/`)

| Endpoint | Description |
|----------|-------------|
| `GET /api/scanner/meta` | Domain metadata and diagnostics |
| `GET /api/scanner/runtime/brief` | Scanner runtime brief |
| `GET /api/scanner/runtime/scorecard` | Operational scorecard |
| `GET /api/scanner/review-pack` | Shift-ready review pack |
| `GET /api/scanner/scanners` | Scanner inventory |
| `GET /api/scanner/incidents` | Field incidents (filterable) |
| `GET /api/scanner/field-response-board` | Field response board |
| `GET /api/scanner/subsystem-escalation` | Subsystem escalation detail |
| `GET /api/scanner/qualification-board` | Qualification review board |
| `GET /api/scanner/customer-readiness` | Customer milestone readiness |
| `GET /api/scanner/lot-risk` | Lot risk board |
| `GET /api/scanner/shift-handoff` | Shift handoff payload |
| `GET /api/scanner/shift-handoff/signature` | Signed handoff envelope |
| `GET /api/scanner/shift-handoff/verify` | Signature verification |
| `GET /api/scanner/evals/replays` | Replay suite summary |
| `GET /api/scanner/audit/feed` | Audit event feed |
| `GET /api/scanner/operator/runtime` | Operator runtime info (auth) |

### curl Examples

```bash
# Health check
curl -s http://localhost:8000/health | python3 -m json.tool

# Fab ops recovery board (hold lots only)
curl -s http://localhost:8000/api/fab-ops/recovery-board?mode=hold | python3 -m json.tool

# Release gate decision (with operator token when auth is enabled)
curl -s -H "x-operator-token: YOUR_TOKEN" \
     -H "x-operator-role: shift-lead" \
     http://localhost:8000/api/fab-ops/release-gate?lot_id=lot-8812 | python3 -m json.tool

# Scanner field response board
curl -s http://localhost:8000/api/scanner/field-response-board | python3 -m json.tool

# Scanner subsystem escalation
curl -s "http://localhost:8000/api/scanner/subsystem-escalation?tool_id=scanner-euv-02" | python3 -m json.tool

# Prometheus metrics
curl -s http://localhost:8000/metrics
```

## Multi-Cloud Deployment

### AWS (ECS / EKS)

The platform includes an AWS adapter (`app/shared/aws_adapter.py`) gated by `AWS_ACCESS_KEY_ID`:

- **S3**: Automatic export of handoff packs and audit bundles
- **SQS**: Event publishing for downstream pipelines (placeholder)
- **RDS**: Set `DATABASE_URL` to a PostgreSQL/MySQL connection string for RDS persistence

```bash
# Set AWS credentials to enable S3/SQS integration
export AWS_ACCESS_KEY_ID=AKIA...
export AWS_SECRET_ACCESS_KEY=...
export AWS_S3_BUCKET=my-semiconductor-exports
```

### GCP (Cloud Run)

Terraform configuration in `infra/terraform/` deploys to Google Cloud Run:

```bash
cd infra/terraform
terraform init
terraform plan -var="project_id=my-gcp-project"
terraform apply
```

### Cloudflare Pages

Static frontend deployment is configured via `.github/workflows/pages-auto-deploy.yml`. See `docs/deployment/CLOUDFLARE_PAGES.md`.

### Kubernetes

Production-ready manifests in `infra/k8s/` with:
- **Deployment**: 2 replicas, health probes, resource limits
- **Service**: ClusterIP for internal routing
- **ConfigMap**: Environment configuration
- **HPA**: Autoscaling 2-8 pods based on CPU/memory utilization

## Persistence

The platform supports two persistence backends controlled by `PERSISTENCE_BACKEND`:

| Backend | Value | Description |
|---------|-------|-------------|
| SQLite | `sqlite` (default) | SQLAlchemy models with local SQLite. Tables auto-created on startup. |
| JSONL | `jsonl` | Legacy flat-file JSONL store. Good for development and stateless containers. |

Migration from JSONL to SQLite:

```python
from app.shared.database import migrate_jsonl_to_sqlite
migrate_jsonl_to_sqlite(".runtime/fab-ops-events.jsonl", domain="fab_ops")
migrate_jsonl_to_sqlite(".runtime/scanner-response-events.jsonl", domain="scanner")
```

## Monitoring

- **Prometheus metrics** at `/metrics`: request counts, latency histograms, active requests
- **Structured JSON logging**: Set `LOG_FORMAT=json` for production log aggregation
- **Request ID middleware**: Every request gets a unique `X-Request-ID` header for tracing

## Development

```bash
make install      # Install all dependencies
make test         # Run test suite
make coverage     # Run tests with coverage report
make lint         # Lint with ruff
make typecheck    # Type check with mypy
make docker-build # Build Docker image
make docker-run   # Run in Docker
make deploy       # Apply K8s manifests
make clean        # Remove build artifacts
```

## Project Structure

```
app/
  shared/                  # Zero-duplication shared modules
    database.py            # SQLAlchemy models and persistence layer
    aws_adapter.py         # AWS S3/SQS integration (env-var gated)
    operator_access.py     # Unified operator auth (per-domain env vars)
    runtime_store.py       # Event persistence (SQLite or JSONL backend)
    signatures.py          # HMAC-SHA256 signing and verification
  domains/
    fab_ops/               # Fab ops domain
      domain.py            # Domain data (fabs, tools, alarms, lots)
      helpers.py           # Business logic (build_* functions)
      routes.py            # FastAPI router (/api/fab-ops/...)
    scanner/               # Scanner domain
      domain.py            # Domain data (scanners, incidents, qualifications)
      helpers.py           # Business logic (build_* functions)
      routes.py            # FastAPI router (/api/scanner/...)
  main.py                  # Unified entrypoint with OpenAPI config
infra/
  k8s/                     # Kubernetes manifests
  terraform/               # GCP Cloud Run Terraform config
.github/workflows/
  ci.yml                   # CI/CD: lint, test, coverage, Docker push
  pages-auto-deploy.yml    # Cloudflare Pages static deploy
```

## What Was Unified

Both domains previously had near-identical copies of operator access, runtime storage, and HMAC signature logic. These are now single implementations in `app/shared/` parameterized by domain name, eliminating all duplication while preserving per-domain environment variable isolation.
