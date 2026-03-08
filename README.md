# Fab Ops Yield Control Tower

`fab-ops-yield-control-tower` is a service-grade manufacturing operations demo for semiconductor and industrial environments. It keeps `alarms`, `lot-at-risk prioritization`, `tool watchlist`, and `shift handoff` in one reviewable operator surface.

## What it demonstrates

- Fab control tower framing instead of a generic AI copilot
- Alarm -> lot -> tool -> SOP linkage for grounded triage
- Shift handoff export surface for operator continuity
- Replay-style review evidence for manufacturing incident scenarios
- Service-grade runtime brief, review pack, schema endpoints, and CI

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
- `GET /api/alarms`
- `GET /api/lots/at-risk`
- `GET /api/shift-handoff`
- `GET /api/evals/replays`

## Review Flow

1. `health`
2. `runtime brief`
3. `alarm queue`
4. `lots at risk`
5. `shift handoff`
6. `replay evals`

## Local Verification

```bash
python3 -m compileall -q app tests
pytest -q
```
