# Semiconductor Ops Platform

`semiconductor-ops-platform` is a unified manufacturing operations platform for semiconductor environments. It combines two domains into a single FastAPI application with shared infrastructure and zero code duplication.

## Domains

### Fab Ops Yield Control Tower (`/api/fab-ops/`)
Manages `alarms`, `lot-at-risk prioritization`, `tool ownership`, `release gate`, `recovery board`, and `shift handoff` in a single operator dashboard.

### Scanner Field Response (`/api/scanner/`)
A semiconductor equipment field-response workflow for `field response`, `subsystem escalation`, `qualification review`, and `signed handoff`. Keeps one scanner incident visible from local triage through qualification review and customer milestone readiness.

## Architecture

```
app/
  shared/                  # Zero-duplication shared modules
    operator_access.py     # Unified operator auth (per-domain env vars)
    runtime_store.py       # Unified event persistence (per-domain store files)
    signatures.py          # Unified HMAC-SHA256 signing and verification
  domains/
    fab_ops/               # Fab ops domain
      domain.py            # Hardcoded fab/tool/alarm/lot data
      helpers.py           # Business logic (build_* functions)
      routes.py            # FastAPI router (/api/fab-ops/...)
    scanner/               # Scanner domain
      domain.py            # Hardcoded scanner/incident/qualification data
      helpers.py           # Business logic (build_* functions)
      routes.py            # FastAPI router (/api/scanner/...)
  main.py                  # Unified entrypoint
```

## Quickstart

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev]"
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`.

## API endpoints

### Platform
- `GET /health`

### Fab Ops (`/api/fab-ops/`)
- `GET /api/fab-ops/meta`
- `GET /api/fab-ops/runtime/brief`
- `GET /api/fab-ops/runtime/scorecard`
- `GET /api/fab-ops/review-pack`
- `GET /api/fab-ops/review-summary`
- `GET /api/fab-ops/recovery-board`
- `GET /api/fab-ops/release-board`
- `GET /api/fab-ops/recovery-what-if`
- `GET /api/fab-ops/recovery-board/schema`
- `GET /api/fab-ops/schema/alarm-report`
- `GET /api/fab-ops/schema/shift-handoff`
- `GET /api/fab-ops/fabs/summary`
- `GET /api/fab-ops/tools`
- `GET /api/fab-ops/tool-ownership`
- `GET /api/fab-ops/alarms`
- `GET /api/fab-ops/lots/at-risk`
- `GET /api/fab-ops/release-gate`
- `GET /api/fab-ops/shift-handoff`
- `GET /api/fab-ops/shift-handoff/signature`
- `GET /api/fab-ops/shift-handoff/verify`
- `GET /api/fab-ops/audit/feed`
- `GET /api/fab-ops/evals/replays`

### Scanner (`/api/scanner/`)
- `GET /api/scanner/meta`
- `GET /api/scanner/runtime/brief`
- `GET /api/scanner/runtime/scorecard`
- `GET /api/scanner/review-pack`
- `GET /api/scanner/schema/field-incident`
- `GET /api/scanner/schema/application-qualification`
- `GET /api/scanner/scanners`
- `GET /api/scanner/incidents`
- `GET /api/scanner/field-response-board`
- `GET /api/scanner/subsystem-escalation`
- `GET /api/scanner/qualification-board`
- `GET /api/scanner/customer-readiness`
- `GET /api/scanner/lot-risk`
- `GET /api/scanner/shift-handoff`
- `GET /api/scanner/shift-handoff/signature`
- `GET /api/scanner/shift-handoff/verify`
- `GET /api/scanner/evals/replays`
- `GET /api/scanner/audit/feed`
- `GET /api/scanner/operator/runtime`

## Local Verification

```bash
python -m pip install -U pip
python -m pip install -e ".[dev]"
python3 -m compileall -q app tests
python -m pytest
```

## What was unified

Both domains previously had near-identical copies of:
- **operator_access.py** -- operator token auth with HMAC comparison and role checking
- **runtime_store.py** -- JSONL event persistence with summarization
- **HMAC-SHA256 signature logic** -- signing keys, stable JSON, digest computation

These are now single implementations in `app/shared/` parameterized by domain name, eliminating all duplication while preserving per-domain environment variable isolation.
