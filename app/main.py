"""
Fab Ops Yield Control Tower - Thin FastAPI application entrypoint.

Business logic is delegated to:
  - domain.py: hardcoded fab/tool/alarm/lot domain data and constants
  - helpers.py: all build_* business logic functions
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

APP_DIR = Path(__file__).resolve().parent
REPO_ROOT = APP_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.operator_access import build_operator_auth_status, require_operator_token
from app.runtime_store import record_runtime_event, summarize_runtime_events
from app.domain import (
    ALARMS,
    LOTS_AT_RISK,
    SERVICE_NAME,
    TOOLS,
)
from app.helpers import (
    build_alarm_report_schema,
    build_audit_feed,
    build_fab_summary,
    build_handoff_signature,
    build_handoff_signature_verification,
    build_meta,
    build_recovery_board,
    build_recovery_board_schema,
    build_recovery_what_if,
    build_release_board,
    build_release_gate,
    build_replay_summary,
    build_review_pack,
    build_review_summary,
    build_review_summary_schema,
    build_runtime_brief,
    build_runtime_scorecard,
    build_shift_handoff,
    build_shift_handoff_schema,
    build_tool_ownership,
    record_route_hit,
    utc_now_iso,
)

BASE_DIR = APP_DIR
STATIC_DIR = BASE_DIR / "static"

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="Fab Ops Yield Control Tower")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------

@app.get("/health")
async def health() -> Dict[str, Any]:
    record_route_hit("/health")
    meta = build_meta()
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "diagnostics": meta["diagnostics"],
        "ops_contract": meta["ops_contract"],
        "capabilities": meta["capabilities"],
        "links": {
            "meta": "/api/meta",
            "runtime_brief": "/api/runtime/brief",
            "runtime_scorecard": "/api/runtime/scorecard",
            "review_summary": "/api/review-summary",
            "recovery_board": "/api/recovery-board",
            "release_board": "/api/release-board",
            "recovery_what_if": "/api/recovery-what-if",
            "review_pack": "/api/review-pack",
            "alarm_report_schema": "/api/schema/alarm-report",
            "shift_handoff_schema": "/api/schema/shift-handoff",
            "replay_evals": "/api/evals/replays",
        },
    }


@app.get("/api/meta")
async def meta() -> Dict[str, Any]:
    record_route_hit("/api/meta")
    return build_meta()


@app.get("/api/runtime/brief")
async def runtime_brief() -> Dict[str, Any]:
    record_route_hit("/api/runtime/brief")
    return build_runtime_brief()


@app.get("/api/runtime/scorecard")
async def runtime_scorecard() -> Dict[str, Any]:
    record_route_hit("/api/runtime/scorecard")
    return build_runtime_scorecard()


@app.get("/api/review-summary")
async def review_summary(
    severity: str | None = Query(default=None),
    risk_bucket: str | None = Query(default=None),
) -> Dict[str, Any]:
    record_route_hit("/api/review-summary")
    return build_review_summary(severity=severity, risk_bucket=risk_bucket)


@app.get("/api/review-summary/schema")
async def review_summary_schema() -> Dict[str, Any]:
    return build_review_summary_schema()


@app.get("/api/recovery-board")
async def recovery_board(mode: str | None = Query(default=None)) -> Dict[str, Any]:
    record_route_hit("/api/recovery-board")
    return build_recovery_board(mode=mode)


@app.get("/api/release-board")
async def release_board() -> Dict[str, Any]:
    record_route_hit("/api/release-board")
    return build_release_board()


@app.get("/api/recovery-board/schema")
async def recovery_board_schema() -> Dict[str, Any]:
    return build_recovery_board_schema()


@app.get("/api/recovery-what-if")
async def recovery_what_if(
    lot_id: str = Query(default="lot-8812"),
    yield_gain: float = Query(default=0.2),
    maintenance_complete: bool = Query(default=False),
) -> Dict[str, Any]:
    record_route_hit("/api/recovery-what-if")
    return build_recovery_what_if(
        lot_id=lot_id,
        yield_gain=yield_gain,
        maintenance_complete=maintenance_complete,
    )


@app.get("/api/review-pack")
async def review_pack() -> Dict[str, Any]:
    record_route_hit("/api/review-pack")
    return build_review_pack()


@app.get("/api/schema/alarm-report")
async def alarm_report_schema() -> Dict[str, Any]:
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "generated_at": utc_now_iso(),
        **build_alarm_report_schema(),
    }


@app.get("/api/schema/shift-handoff")
async def shift_handoff_schema() -> Dict[str, Any]:
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "generated_at": utc_now_iso(),
        **build_shift_handoff_schema(),
    }


@app.get("/api/fabs/summary")
async def fabs_summary() -> Dict[str, Any]:
    record_route_hit("/api/fabs/summary")
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "items": [build_fab_summary()],
    }


@app.get("/api/tools")
async def tools() -> Dict[str, Any]:
    record_route_hit("/api/tools")
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "items": TOOLS,
    }


@app.get("/api/tool-ownership")
async def tool_ownership(tool_id: str = Query(default="etch-14")) -> Dict[str, Any]:
    record_route_hit("/api/tool-ownership")
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "payload": build_tool_ownership(tool_id),
    }


@app.get("/api/alarms")
async def alarms() -> Dict[str, Any]:
    record_route_hit("/api/alarms")
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "items": ALARMS,
    }


@app.get("/api/lots/at-risk")
async def lots_at_risk() -> Dict[str, Any]:
    record_route_hit("/api/lots/at-risk")
    items = sorted(LOTS_AT_RISK, key=lambda item: item["yield_risk_score"], reverse=True)
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "items": items,
    }


@app.get("/api/release-gate")
async def release_gate(request: Request, lot_id: str = Query(default="lot-8812")) -> Dict[str, Any]:
    require_operator_token(request)
    record_route_hit("/api/release-gate")
    record_runtime_event("release_gate_check", at=utc_now_iso(), lot_id=lot_id)
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "payload": build_release_gate(lot_id),
    }


@app.get("/api/shift-handoff")
async def shift_handoff(request: Request) -> Dict[str, Any]:
    require_operator_token(request)
    record_route_hit("/api/shift-handoff")
    record_runtime_event("handoff_export", at=utc_now_iso(), shift="night", fab_id="fab-west-1")
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "payload": build_shift_handoff(),
    }


@app.get("/api/shift-handoff/signature")
async def shift_handoff_signature(request: Request) -> Dict[str, Any]:
    require_operator_token(request)
    record_route_hit("/api/shift-handoff/signature")
    record_runtime_event(
        "handoff_signature_export",
        at=utc_now_iso(),
        shift="night",
        fab_id="fab-west-1",
    )
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "payload": build_handoff_signature(),
    }


@app.get("/api/shift-handoff/verify")
async def shift_handoff_verify(
    request: Request,
    algorithm: str | None = Query(default=None),
    key_id: str | None = Query(default=None),
    sha256: str | None = Query(default=None),
    signature: str | None = Query(default=None),
) -> Dict[str, Any]:
    require_operator_token(request)
    record_route_hit("/api/shift-handoff/verify")
    payload = build_handoff_signature_verification(
        algorithm=algorithm,
        key_id=key_id,
        sha256=sha256,
        signature=signature,
    )
    record_runtime_event(
        "handoff_signature_verify",
        at=utc_now_iso(),
        fab_id=payload["fab_id"],
        signature_id=payload["signature_id"],
        overall_valid=payload["overall_valid"],
    )
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "payload": payload,
    }


@app.get("/api/audit/feed")
async def audit_feed() -> Dict[str, Any]:
    record_route_hit("/api/audit/feed")
    return build_audit_feed()


@app.get("/api/evals/replays")
async def replay_evals() -> Dict[str, Any]:
    record_route_hit("/api/evals/replays")
    return build_replay_summary()


app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="frontend")
