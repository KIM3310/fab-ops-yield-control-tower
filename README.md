# Fab Ops Yield Control Tower

[![CI](https://github.com/KIM3310/fab-ops-yield-control-tower/actions/workflows/ci.yml/badge.svg)](https://github.com/KIM3310/fab-ops-yield-control-tower/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.141.1-009688.svg)](https://fastapi.tiangolo.com)

## Live Demo

- [Open the public Cloudflare Pages demo](https://fab-ops-yield-control-tower.pages.dev/)
- Scope: credential-free, synthetic semiconductor-operations review surface; not connected to live fab systems.

A reviewable semiconductor-operations demo: deterministic Western Electric SPC, explainable lot-disposition gates, synthetic q-time/TAT/routing context, executed replay assertions, and tamper-evident shift artifacts in FastAPI.

> **Evidence boundary:** every fab value is hand-authored synthetic fixture data. The service has no MES/FDC connection, reports no measured yield, makes no yield forecast, never moves material, and never replaces authorized process-engineer or release-supervisor judgment.

## 60-second technical review

| Inspect | Concrete evidence |
|---|---|
| [`app/domains/fab_ops/spc.py`](app/domains/fab_ops/spc.py) | Four Western Electric rules, numerically robust inclusive zone boundaries (including decimal center/sigma references), strict same-side handling for centerline points, data-quality gates, and deterministic flow calculations. |
| [`app/domains/fab_ops/fixtures/synthetic_shift.json`](app/domains/fab_ops/fixtures/synthetic_shift.json) | Packaged, hashed scenario with three lot dispositions plus six SPC boundary cases. |
| `GET /api/fab-ops/v1/lots/lot-8812/disposition` | Actual `HOLD_FOR_CONTAINMENT`, WECO-1/2/3 evidence, breached synthetic q-time, route hold, and `material_state_changed: false`. |
| `GET /api/fab-ops/v1/evals/replays` | Executes nine cases and 54 assertions; it does not return a prewritten pass list. |
| [`tests/test_fab_ops_spc.py`](tests/test_fab_ops_spc.py) | Decimal-boundary and centerline regressions, malformed series, incomplete samples, coherent q-time boundaries, lineage tamper rejection, installed-wheel/static smoke, and authority assertions. |

Start with the [reviewer evidence guide](docs/reviewer-evidence.md), then read the [SPC and disposition methodology](docs/fab-yield-methodology.md).

## Run locally

```bash
make run
# UI       http://127.0.0.1:8000/
# OpenAPI  http://127.0.0.1:8000/docs
# Metrics  http://127.0.0.1:8000/metrics
```

`make run` explicitly selects the `demo` profile, so the synthetic review needs no credential. An unset mode is locked, not implicitly demo. Python 3.11+ is required; if `python3` is older, use `make PYTHON_BIN=/path/to/python3.11 run`.

Containerized demo: `make docker-build && make docker-run` (the built image itself defaults to locked mode; the Make target opts into demo).

Quick proof:

```bash
curl -fsS http://127.0.0.1:8000/api/fab-ops/v1/control-plan
curl -fsS http://127.0.0.1:8000/api/fab-ops/v1/lots/lot-8812/disposition
curl -fsS http://127.0.0.1:8000/api/fab-ops/v1/evals/replays
```

## What is implemented

- **SPC:** WECO-1 through WECO-4 against configured reference centerline/sigma; overlapping windows remain visible.
- **Fail-closed disposition:** incomplete evidence, special cause, out-of-spec values, critical equipment state, q-time breach, or route hold produces containment advice; missing flow context routes to human engineering review rather than release advice.
- **Flow context:** deterministic q-time, TAT, current/next route step, and route state when the fixture supplies them. Displayed elapsed/remaining/overrun values use one calculation basis at boundaries.
- **Executed evaluation:** expected and actual values are compared at request time, with assertion-level results and fixture SHA-256 lineage.
- **Human authority:** API recommendations are advisory; approval is always `not_recorded` and material state is never changed.
- **Security posture:** credential-free access and demo HMAC credentials exist only in exact `demo` mode. Other modes close sensitive and cloud-writing audit routes when credentials are absent; `/ready` reports critical configuration.
- **Two domains:** the same application also retains the scanner field-response workflow under `/api/scanner/`.

## Fab Ops API

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/fab-ops/v1/control-plan` | Versioned rule, fixture, and authority contract |
| `GET` | `/api/fab-ops/v1/lots/{lot_id}/disposition` | Execute packaged synthetic lot disposition |
| `POST` | `/api/fab-ops/v1/disposition/evaluate` | Evaluate explicitly synthetic/non-production values |
| `GET` | `/api/fab-ops/v1/evals/replays` | Execute fixture and SPC boundary assertions |
| `GET` | `/api/fab-ops/recovery-board` | Legacy simulated-risk workflow board |
| `GET` | `/api/fab-ops/shift-handoff/signature` | HMAC integrity envelope binding fixture/SPC/disposition/flow evidence; **not** human approval |
| `POST` | `/api/fab-ops/shift-handoff/verify` | Verify the exact caller-presented manifest/envelope; missing or tampered proof fails |
| `GET` | `/api/fab-ops/audit/feed` | Operator-guarded audit export (may write configured AWS targets) |
| `GET` | `/api/fab-ops/meta` | Contracts, route discovery, auth/signing posture |
| `GET` | `/ready` | Configuration-aware readiness; HTTP 503 when production auth/signing is incomplete |

The POST contract forbids extra fields and production classifications, rejects NaN/infinity, validates engineering limits and sampling, and accepts at most 200 sequential values. See OpenAPI for the complete schema.

## Runtime security modes

```bash
# Local packaged demo (selected explicitly by make run, make docker-run, or .env.example)
SEMICONDUCTOR_OPS_MODE=demo

# Non-demo example: sensitive routes fail closed unless these are configured
SEMICONDUCTOR_OPS_MODE=production
FAB_OPS_OPERATOR_TOKEN='replace-me'
FAB_OPS_OPERATOR_ALLOWED_ROLES='shift-lead,release-supervisor'
FAB_OPS_HANDOFF_SIGNING_KEY='replace-with-secret-manager-value'
FAB_OPS_HANDOFF_SIGNING_KEY_ID='fab-ops-prod-v1'
```

`x-operator-token` or `Authorization: Bearer` carries the token; configured role headers are also enforced. HMAC proves payload integrity/authenticity under a shared key. The signed manifest binds the fixture SHA-256, control-plan/disposition contracts, recommendation, WECO result, and synthetic q-time/TAT/routing state. Verification hashes the caller-presented manifest rather than rebuilding a local trusted copy, rejects unknown outer fields, and validates every exported outer field (including digest preview, provenance/purpose, human-authority labels, route/method, and ordered verification steps) against deterministic values or the signed manifest. HMAC is not an electronic signature, identity attestation, or release authorization. Deployment secrets belong in a secret manager, never the ConfigMap or repository.

For `PERSISTENCE_BACKEND=jsonl`, readiness opens both `FAB_OPS_RUNTIME_STORE_PATH` and `SCANNER_RUNTIME_STORE_PATH` for append; either unusable path makes `/ready` return 503 and closes authenticated non-demo sensitive routes. Unsupported backend names are rejected rather than treated as JSONL.

**AWS** — set both `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` to activate optional exports. SQS additionally needs `AWS_SQS_QUEUE_URL`; DynamoDB additionally needs `AWS_DYNAMODB_TABLE`. These integrations are off in the credential-free demo. Fab and scanner audit feeds authenticate before invoking any S3, DynamoDB, or SQS writer outside demo mode.

**Kubernetes** — [`infra/k8s/deployment.yaml`](infra/k8s/deployment.yaml) references the externally managed `semiconductor-ops-secrets` Secret for both domains' tokens and signing keys, while [`infra/k8s/configmap.yaml`](infra/k8s/configmap.yaml) contains only non-secret production policy. The readiness probe uses `/ready`; liveness remains `/health`. The SQLite topology is intentionally one replica with `Recreate` updates and a `ReadWriteOnce` PVC; no HPA is shipped or applied. Migrate to a reviewed shared database before horizontal scaling. Create/rotate the Secret and review durability limitations in [`infra/k8s/README.md`](infra/k8s/README.md). No Secret values are checked in.

## Architecture

```text
Browser / API client
        │
FastAPI + request metrics
        ├── /api/fab-ops/v1/*  → validated request → deterministic SPC
        │                                      ├── fixture SHA lineage
        │                                      ├── q-time/TAT/route indicators
        │                                      └── advisory human gate
        ├── /api/fab-ops/*     → legacy synthetic workflow boards
        └── /api/scanner/*     → field-response domain
                     │
        shared auth · HMAC · SQLite/JSONL event evidence · optional AWS export
```

The packaged fixture and `app/static` UI are declared in `pyproject.toml`. `make package-check` installs the built wheel into a clean target, proves `app.main` imports from that target, serves the packaged UI, and smokes health/control-plan APIs; no current working directory is assumed.

## Validation

```bash
make verify-strict
# or individually
make lint
make typecheck
make coverage
make package-check
make smoke
make validate
```

CI performs bytecode compilation, Ruff, mypy, pytest with coverage, installed-wheel/static/API packaging smoke, runtime smoke, and repository/Kubernetes configuration validators. The deterministic runtime exerciser is available as:

```bash
SEMICONDUCTOR_OPS_MODE=demo PERSISTENCE_BACKEND=jsonl .venv/bin/python scripts/exercise_runtime.py
```

## Evidence and design notes

- [SPC and disposition methodology](docs/fab-yield-methodology.md)
- [Reviewer evidence guide](docs/reviewer-evidence.md)
- [Architecture evidence map](docs/architecture-evidence-map.md)
- [Quality gate](docs/quality-gate.md)
- [Cloud + AI architecture](docs/cloud-ai-architecture.md)
- [Machine-readable architecture blueprint](docs/architecture/blueprint.json)
- Blueprint validator: `scripts/validate_architecture_blueprint.py`

## License

MIT
