# Fab Ops Yield Control Tower

`fab-ops-yield-control-tower` is a service-grade manufacturing operations demo for semiconductor and industrial environments. It keeps `alarms`, `lot-at-risk prioritization`, `tool ownership`, `release gate`, and `shift handoff` in one reviewable operator surface.

![Review pack diagram](docs/review-pack.svg)

## What it demonstrates

- Fab control tower framing instead of a generic AI copilot
- Alarm -> lot -> tool -> SOP linkage for grounded triage
- Shift handoff export surface for operator continuity
- Tool ownership, release gate, audit feed, and signed handoff proof
- Replay-style review evidence for manufacturing incident scenarios
- Service-grade runtime brief, review pack, schema endpoints, and CI

## Review Pack At A Glance

- Tool ownership and maintenance escalation lanes stay visible before any release decision.
- Release gate makes the top lot decision explicit instead of implied by the alarm queue.
- Shift handoff now includes a digest-style signature proof for next-shift review.
- Audit feed shows the latest handoff and escalation events without live fab systems.

## Quickstart

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt -r requirements-dev.txt
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000`.

## Service-Grade Surfaces

- `GET /health`
- `GET /api/meta`
- `GET /api/runtime/brief`
- `GET /api/review-pack`
- `GET /api/schema/alarm-report`
- `GET /api/schema/shift-handoff`
- `GET /api/fabs/summary`
- `GET /api/tools`
- `GET /api/tool-ownership`
- `GET /api/alarms`
- `GET /api/lots/at-risk`
- `GET /api/release-gate`
- `GET /api/shift-handoff`
- `GET /api/shift-handoff/signature`
- `GET /api/audit/feed`
- `GET /api/evals/replays`

## Review Flow

1. `health`
2. `runtime brief`
3. `tool ownership`
4. `release gate`
5. `alarm queue + lots at risk`
6. `shift handoff + signature`
7. `audit feed + replay evals`

## Local Verification

```bash
python3 -m compileall -q app tests
pytest -q
node --check app/static/app.js
```
