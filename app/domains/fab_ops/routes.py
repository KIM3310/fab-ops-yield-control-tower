"""
FastAPI router for the fab-ops domain.

All routes are prefixed with ``/api/fab-ops`` by the parent app.  Route
handlers are intentionally thin -- business logic lives in
:mod:`app.domains.fab_ops.helpers`.
"""

import logging
from typing import Any, cast

from fastapi import APIRouter, Query, Request

from app.domains.fab_ops.domain import ALARMS, LOTS_AT_RISK, SERVICE_NAME, TOOLS
from app.domains.fab_ops.helpers import (
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
from app.shared.operator_access import require_operator_token
from app.shared.runtime_store import record_runtime_event

logger = logging.getLogger("fab_ops.routes")

DOMAIN: str = "fab_ops"
router = APIRouter(prefix="/api/fab-ops", tags=["fab-ops"])


@router.get("/meta")
async def meta() -> dict[str, Any]:
    """Return fab-ops domain metadata, contracts, and diagnostic info."""
    record_route_hit("/api/fab-ops/meta")
    return build_meta()


@router.get("/runtime/brief")
async def runtime_brief() -> dict[str, Any]:
    """Return the comprehensive runtime brief for the fab control tower."""
    record_route_hit("/api/fab-ops/runtime/brief")
    return build_runtime_brief()


@router.get("/runtime/scorecard")
async def runtime_scorecard() -> dict[str, Any]:
    """Return the runtime scorecard with aggregated operational metrics."""
    record_route_hit("/api/fab-ops/runtime/scorecard")
    return build_runtime_scorecard()


@router.get("/review-summary")
async def review_summary(
    severity: str | None = Query(default=None),
    risk_bucket: str | None = Query(default=None),
) -> dict[str, Any]:
    """Return a filtered review summary of alarms and lots at risk."""
    record_route_hit("/api/fab-ops/review-summary")
    return build_review_summary(severity=severity, risk_bucket=risk_bucket)


@router.get("/review-summary/schema")
async def review_summary_schema() -> dict[str, Any]:
    """Return the review summary JSON schema definition."""
    return build_review_summary_schema()


@router.get("/recovery-board")
async def recovery_board(mode: str | None = Query(default=None)) -> dict[str, Any]:
    """Return the recovery board, optionally filtered by board status mode."""
    record_route_hit("/api/fab-ops/recovery-board")
    return build_recovery_board(mode=mode)


@router.get("/release-board")
async def release_board() -> dict[str, Any]:
    """Return the release board with all lots sorted by yield risk."""
    record_route_hit("/api/fab-ops/release-board")
    return build_release_board()


@router.get("/recovery-board/schema")
async def recovery_board_schema() -> dict[str, Any]:
    """Return the recovery board JSON schema definition."""
    return build_recovery_board_schema()


@router.get("/recovery-what-if")
async def recovery_what_if(
    lot_id: str = Query(default="lot-8812"),
    yield_gain: float = Query(default=0.2),
    maintenance_complete: bool = Query(default=False),
) -> dict[str, Any]:
    """Run a what-if recovery simulation for the specified lot."""
    record_route_hit("/api/fab-ops/recovery-what-if")
    return build_recovery_what_if(
        lot_id=lot_id,
        yield_gain=yield_gain,
        maintenance_complete=maintenance_complete,
    )


@router.get("/review-pack")
async def review_pack() -> dict[str, Any]:
    """Return the shift-ready review pack aggregating all fab-ops surfaces."""
    record_route_hit("/api/fab-ops/review-pack")
    return build_review_pack()


@router.get("/schema/alarm-report")
async def alarm_report_schema() -> dict[str, Any]:
    """Return the alarm report schema definition."""
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "generated_at": utc_now_iso(),
        **build_alarm_report_schema(),
    }


@router.get("/schema/shift-handoff")
async def shift_handoff_schema() -> dict[str, Any]:
    """Return the shift handoff schema definition."""
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "generated_at": utc_now_iso(),
        **build_shift_handoff_schema(),
    }


@router.get("/fabs/summary")
async def fabs_summary() -> dict[str, Any]:
    """Return a summary of the fab's operational posture."""
    record_route_hit("/api/fab-ops/fabs/summary")
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "items": [build_fab_summary()],
    }


@router.get("/tools")
async def tools() -> dict[str, Any]:
    """Return the list of all tools in the fab."""
    record_route_hit("/api/fab-ops/tools")
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "items": TOOLS,
    }


@router.get("/tool-ownership")
async def tool_ownership(tool_id: str = Query(default="etch-14")) -> dict[str, Any]:
    """Return the ownership record for a specific tool."""
    record_route_hit("/api/fab-ops/tool-ownership")
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "payload": build_tool_ownership(tool_id),
    }


@router.get("/alarms")
async def alarms() -> dict[str, Any]:
    """Return the list of all active alarms."""
    record_route_hit("/api/fab-ops/alarms")
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "items": ALARMS,
    }


@router.get("/lots/at-risk")
async def lots_at_risk() -> dict[str, Any]:
    """Return lots at risk sorted by yield risk score (descending)."""
    record_route_hit("/api/fab-ops/lots/at-risk")
    items = sorted(LOTS_AT_RISK, key=lambda item: float(cast(float | str, item["yield_risk_score"])), reverse=True)
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "items": items,
    }


@router.get("/release-gate")
async def release_gate(request: Request, lot_id: str = Query(default="lot-8812")) -> dict[str, Any]:
    """Evaluate and return the release gate decision for a lot (auth required)."""
    require_operator_token(request, DOMAIN)
    record_route_hit("/api/fab-ops/release-gate")
    record_runtime_event("release_gate_check", domain=DOMAIN, at=utc_now_iso(), lot_id=lot_id)
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "payload": build_release_gate(lot_id),
    }


@router.get("/shift-handoff")
async def shift_handoff(request: Request) -> dict[str, Any]:
    """Export the shift handoff pack (auth required)."""
    require_operator_token(request, DOMAIN)
    record_route_hit("/api/fab-ops/shift-handoff")
    record_runtime_event("handoff_export", domain=DOMAIN, at=utc_now_iso(), shift="night", fab_id="fab-west-1")
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "payload": build_shift_handoff(),
    }


@router.get("/shift-handoff/signature")
async def shift_handoff_signature(request: Request) -> dict[str, Any]:
    """Export the signed shift handoff envelope (auth required)."""
    require_operator_token(request, DOMAIN)
    record_route_hit("/api/fab-ops/shift-handoff/signature")
    record_runtime_event(
        "handoff_signature_export",
        domain=DOMAIN,
        at=utc_now_iso(),
        shift="night",
        fab_id="fab-west-1",
    )
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "payload": build_handoff_signature(),
    }


@router.get("/shift-handoff/verify")
async def shift_handoff_verify(
    request: Request,
    algorithm: str | None = Query(default=None),
    key_id: str | None = Query(default=None),
    sha256: str | None = Query(default=None),
    signature: str | None = Query(default=None),
) -> dict[str, Any]:
    """Verify the shift handoff signature (auth required)."""
    require_operator_token(request, DOMAIN)
    record_route_hit("/api/fab-ops/shift-handoff/verify")
    payload = build_handoff_signature_verification(
        algorithm=algorithm,
        key_id=key_id,
        sha256=sha256,
        signature=signature,
    )
    record_runtime_event(
        "handoff_signature_verify",
        domain=DOMAIN,
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


@router.get("/audit/feed")
async def audit_feed() -> dict[str, Any]:
    """Return the audit event feed for the fab-ops domain."""
    record_route_hit("/api/fab-ops/audit/feed")
    return build_audit_feed()


@router.get("/evals/replays")
async def replay_evals() -> dict[str, Any]:
    """Return the replay suite summary for the fab-ops domain."""
    record_route_hit("/api/fab-ops/evals/replays")
    return build_replay_summary()
