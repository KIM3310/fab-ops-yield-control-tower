"""
FastAPI router for the scanner field-response domain.

All routes are prefixed with ``/api/scanner`` by the parent app.  Route
handlers are intentionally thin -- business logic lives in
:mod:`app.domains.scanner.helpers`.
"""

import logging
from typing import Any, cast

from fastapi import APIRouter, HTTPException, Query, Request

from app.domains.scanner.domain import (
    ALLOWED_CUSTOMERS,
    ALLOWED_SEVERITIES,
    APPLICATION_QUALIFICATION_SCHEMA,
    AUDIT_EVENTS,
    FIELD_INCIDENT_SCHEMA,
    FIELD_INCIDENTS,
    LOT_RISK_CONTRACT,
    REVIEW_PACK_CONTRACT,
    RUNTIME_BRIEF_CONTRACT,
    RUNTIME_SCORECARD_CONTRACT,
    SCANNERS,
    SERVICE_NAME,
    SHIFT_HANDOFF_SCHEMA,
    WAFER_RISK_ITEMS,
)
from app.domains.scanner.helpers import (
    build_customer_readiness,
    build_field_response_board,
    build_handoff_signature,
    build_handoff_verify,
    build_qualification_board,
    build_replay_summary,
    build_review_pack,
    build_runtime_brief,
    build_runtime_scorecard,
    build_shift_handoff_payload,
    build_subsystem_escalation,
    record_route_hit,
    utc_now_iso,
)
from app.shared.operator_access import build_operator_auth_status, require_operator_token
from app.shared.runtime_store import record_runtime_event

logger = logging.getLogger("scanner.routes")

DOMAIN: str = "scanner"
router = APIRouter(prefix="/api/scanner", tags=["scanner"])


@router.get("/meta")
def meta() -> dict[str, Any]:
    """Return scanner domain metadata, contracts, and diagnostic info."""
    record_route_hit("/api/scanner/meta")
    return {
        "service": SERVICE_NAME,
        "runtime_contract": RUNTIME_BRIEF_CONTRACT,
        "runtime_scorecard_contract": RUNTIME_SCORECARD_CONTRACT,
        "review_pack_contract": REVIEW_PACK_CONTRACT,
        "field_incident_contract": {"schema": FIELD_INCIDENT_SCHEMA},
        "application_qualification_contract": {"schema": APPLICATION_QUALIFICATION_SCHEMA},
        "handoff_contract": {"schema": SHIFT_HANDOFF_SCHEMA},
        "diagnostics": {
            "field_response_ready": True,
            "subsystem_escalation_ready": True,
            "qualification_ready": True,
            "customer_readiness_ready": True,
        },
        "routes": [
            "/health",
            "/api/scanner/runtime/brief",
            "/api/scanner/runtime/scorecard",
            "/api/scanner/review-pack",
            "/api/scanner/schema/field-incident",
            "/api/scanner/schema/application-qualification",
            "/api/scanner/scanners",
            "/api/scanner/incidents",
            "/api/scanner/field-response-board",
            "/api/scanner/subsystem-escalation",
            "/api/scanner/qualification-board",
            "/api/scanner/customer-readiness",
            "/api/scanner/lot-risk",
            "/api/scanner/shift-handoff",
            "/api/scanner/shift-handoff/signature",
            "/api/scanner/shift-handoff/verify",
            "/api/scanner/evals/replays",
            "/api/scanner/audit/feed",
        ],
    }


@router.get("/runtime/brief")
def runtime_brief() -> dict[str, Any]:
    """Return the comprehensive runtime brief for the scanner domain."""
    record_route_hit("/api/scanner/runtime/brief")
    return build_runtime_brief()


@router.get("/runtime/scorecard")
def runtime_scorecard() -> dict[str, Any]:
    """Return the runtime scorecard with operational metrics."""
    record_route_hit("/api/scanner/runtime/scorecard")
    return build_runtime_scorecard()


@router.get("/review-pack")
def review_pack() -> dict[str, Any]:
    """Return the shift-ready review pack for the scanner domain."""
    record_route_hit("/api/scanner/review-pack")
    return build_review_pack()


@router.get("/schema/field-incident")
def field_incident_schema() -> dict[str, Any]:
    """Return the field incident schema definition."""
    record_route_hit("/api/scanner/schema/field-incident")
    return {
        "schema": FIELD_INCIDENT_SCHEMA,
        "required": ["incident_id", "severity", "tool_id", "lot_id", "subsystem", "symptom", "local_action"],
    }


@router.get("/schema/application-qualification")
def application_qualification_schema() -> dict[str, Any]:
    """Return the application qualification schema definition."""
    record_route_hit("/api/scanner/schema/application-qualification")
    return {
        "schema": APPLICATION_QUALIFICATION_SCHEMA,
        "required": [
            "lot_id",
            "tool_id",
            "customer",
            "qualification_status",
            "current_overlay_nm",
            "target_overlay_nm",
        ],
    }


@router.get("/scanners")
def scanners() -> dict[str, Any]:
    """Return the list of all scanners at the site."""
    record_route_hit("/api/scanner/scanners")
    return {"items": SCANNERS}


@router.get("/incidents")
def incidents(severity: str | None = Query(default=None)) -> dict[str, Any]:
    """Return field incidents, optionally filtered by severity."""
    record_route_hit("/api/scanner/incidents")
    if severity and severity not in ALLOWED_SEVERITIES:
        raise HTTPException(status_code=400, detail=f"Unsupported severity: {severity}")
    items = FIELD_INCIDENTS
    if severity:
        items = [item for item in items if item["severity"] == severity]
    return {"schema": FIELD_INCIDENT_SCHEMA, "items": items}


@router.get("/field-response-board")
def field_response_board() -> dict[str, Any]:
    """Return the field response board sorted by severity and SLA."""
    record_route_hit("/api/scanner/field-response-board")
    return build_field_response_board()


@router.get("/subsystem-escalation")
def subsystem_escalation(tool_id: str = Query(...)) -> dict[str, Any]:
    """Return the subsystem escalation detail for a scanner."""
    record_route_hit("/api/scanner/subsystem-escalation")
    record_runtime_event("module_escalation_check", domain=DOMAIN, at=utc_now_iso(), tool_id=tool_id)
    return build_subsystem_escalation(tool_id)


@router.get("/qualification-board")
def qualification_board(lot_id: str = Query(...)) -> dict[str, Any]:
    """Return the qualification board for a specific lot."""
    record_route_hit("/api/scanner/qualification-board")
    record_runtime_event("application_qualification_check", domain=DOMAIN, at=utc_now_iso(), lot_id=lot_id)
    return build_qualification_board(lot_id)


@router.get("/customer-readiness")
def customer_readiness(customer: str = Query(...)) -> dict[str, Any]:
    """Return customer readiness status for a customer program."""
    record_route_hit("/api/scanner/customer-readiness")
    if customer not in ALLOWED_CUSTOMERS:
        raise HTTPException(status_code=400, detail=f"Unsupported customer: {customer}")
    return build_customer_readiness(customer)


@router.get("/lot-risk")
def lot_risk() -> dict[str, Any]:
    """Return the lot risk board sorted by risk score (descending)."""
    record_route_hit("/api/scanner/lot-risk")
    items = sorted(WAFER_RISK_ITEMS, key=lambda item: float(cast(float | str, item["risk_score"])), reverse=True)
    return {
        "contract_version": LOT_RISK_CONTRACT,
        "summary": {
            "blocked": sum(1 for item in items if item["risk_bucket"] == "blocked"),
            "watch": sum(1 for item in items if item["risk_bucket"] == "watch"),
            "ready": sum(1 for item in items if item["risk_bucket"] == "ready"),
        },
        "items": items,
    }


@router.get("/shift-handoff")
def shift_handoff() -> dict[str, Any]:
    """Export the scanner shift handoff payload."""
    record_route_hit("/api/scanner/shift-handoff")
    payload = build_shift_handoff_payload()
    record_runtime_event("handoff_export", domain=DOMAIN, at=utc_now_iso(), handoff_id=payload["handoff_id"])
    return {"payload": payload}


@router.get("/shift-handoff/signature")
def shift_handoff_signature() -> dict[str, Any]:
    """Export the signed scanner shift handoff envelope."""
    record_route_hit("/api/scanner/shift-handoff/signature")
    payload = build_shift_handoff_payload()
    signature = build_handoff_signature(payload)
    record_runtime_event("handoff_signature_export", domain=DOMAIN, at=utc_now_iso(), signature_id=signature["signature_id"])
    return {"payload": signature}


@router.get("/shift-handoff/verify")
def shift_handoff_verify() -> dict[str, Any]:
    """Verify the scanner shift handoff signature."""
    record_route_hit("/api/scanner/shift-handoff/verify")
    payload = build_shift_handoff_payload()
    expected = build_handoff_signature(payload)
    return {"payload": build_handoff_verify(payload, expected)}


@router.get("/evals/replays")
def replay_evals() -> dict[str, Any]:
    """Return the replay suite summary for the scanner domain."""
    record_route_hit("/api/scanner/evals/replays")
    return build_replay_summary()


@router.get("/audit/feed")
def audit_feed() -> dict[str, Any]:
    """Return the audit event feed for the scanner domain."""
    record_route_hit("/api/scanner/audit/feed")
    return {"summary": {"events": len(AUDIT_EVENTS)}, "items": AUDIT_EVENTS}


@router.get("/operator/runtime")
def operator_runtime(request: Request) -> dict[str, Any]:
    """Return operator runtime info (auth required when token is configured)."""
    record_route_hit("/api/scanner/operator/runtime")
    require_operator_token(request, DOMAIN)
    return {
        "service": SERVICE_NAME,
        "operator_auth": build_operator_auth_status(DOMAIN),
        "next_actions": [
            "Upload the local scanner packet",
            "Confirm the subsystem replay result",
            "Update customer readiness before the next shift handoff",
        ],
    }
