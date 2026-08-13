"""
FastAPI router for the fab-ops domain.

All routes are prefixed with ``/api/fab-ops`` by the parent app.  Route
handlers are intentionally thin -- business logic lives in
:mod:`app.domains.fab_ops.helpers`.
"""

import hashlib
import json
import logging
from typing import Any, cast

from fastapi import APIRouter, HTTPException, Query, Request

from app.domains.fab_ops.domain import ALARMS, LOTS_AT_RISK, SERVICE_NAME, TOOLS
from app.domains.fab_ops.helpers import (
    build_alarm_report_schema,
    build_architecture_pack,
    build_architecture_summary,
    build_architecture_summary_schema,
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
    build_runtime_brief,
    build_runtime_scorecard,
    build_shift_handoff,
    build_shift_handoff_schema,
    build_synthetic_evidence_boundary,
    build_tool_ownership,
    record_route_hit,
    utc_now_iso,
)
from app.domains.fab_ops.models import (
    DispositionEvaluationRequest,
    HandoffVerificationEnvelope,
    HandoffVerificationRequest,
)
from app.domains.fab_ops.spc import (
    build_control_plan,
    build_disposition_evaluation,
    build_fixture_excursion_review,
)
from app.shared.aws_adapter import (
    aws_status,
    export_audit_bundle_to_s3,
    export_handoff_to_s3,
    persist_export_metadata_to_dynamodb,
    publish_event_to_sqs,
)
from app.shared.operator_access import require_operator_token
from app.shared.runtime_store import record_runtime_event, summarize_runtime_events

logger = logging.getLogger("fab_ops.routes")

DOMAIN: str = "fab_ops"
router = APIRouter(prefix="/api/fab-ops", tags=["fab-ops"])


def _handoff_id_from_payload(payload: dict[str, Any]) -> str:
    return str(payload.get("handoff_id") or f"handoff-{payload.get('fab_id', 'unknown')}-{payload.get('shift', 'unknown')}")


def _build_export_ledger(*, runtime_brief_path: str, architecture_pack_path: str) -> dict[str, Any]:
    runtime = summarize_runtime_events(DOMAIN)
    export_events = [
        event
        for event in runtime.get("recent_events", [])
        if str(event.get("event_type", "")) in {"handoff_export", "handoff_signature_export", "audit_bundle_export"}
    ]
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "evidence_boundary": build_synthetic_evidence_boundary(),
        "schema": "fab-ops-export-ledger-v1",
        "aws": aws_status(),
        "summary": {
            "export_event_count": len(export_events),
            "last_event_at": runtime.get("last_event_at"),
        },
        "recent_exports": export_events[-6:],
        "architecture_fast_path": [runtime_brief_path, "/api/fab-ops/runtime/export-ledger", architecture_pack_path],
    }


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


@router.get("/runtime/export-ledger")
async def runtime_export_ledger() -> dict[str, Any]:
    """Return the export ledger for reviewer-facing handoff proof."""
    record_route_hit("/api/fab-ops/runtime/export-ledger")
    return _build_export_ledger(
        runtime_brief_path="/api/fab-ops/runtime/brief",
        architecture_pack_path="/api/fab-ops/architecture-pack",
    )


@router.get("/v1/control-plan")
async def synthetic_control_plan_v1() -> dict[str, Any]:
    """Return the versioned synthetic SPC control plan and authority boundary."""
    record_route_hit("/api/fab-ops/v1/control-plan")
    return build_control_plan()


@router.get("/v1/lots/{lot_id}/disposition")
async def fixture_lot_disposition_v1(request: Request, lot_id: str) -> dict[str, Any]:
    """Execute the advisory disposition gate for a packaged synthetic lot."""
    require_operator_token(request, DOMAIN)
    record_route_hit("/api/fab-ops/v1/lots/{lot_id}/disposition")
    try:
        payload = build_fixture_excursion_review(lot_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown synthetic fixture lot: {lot_id}") from exc
    record_runtime_event(
        "synthetic_disposition_evaluated",
        domain=DOMAIN,
        at=utc_now_iso(),
        lot_id=lot_id,
        recommendation=payload["gate"]["recommendation"],
        material_state_changed=False,
    )
    return payload


@router.post("/v1/disposition/evaluate")
async def non_production_disposition_evaluation_v1(
    request: Request,
    evaluation: DispositionEvaluationRequest,
) -> dict[str, Any]:
    """Evaluate a caller-supplied synthetic/non-production sequence."""
    require_operator_token(request, DOMAIN)
    record_route_hit("/api/fab-ops/v1/disposition/evaluate")
    evaluated_at = evaluation.evaluated_at.isoformat() if evaluation.evaluated_at else utc_now_iso()
    request_payload = evaluation.model_dump(mode="json")
    request_sha256 = hashlib.sha256(
        json.dumps(request_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    measurement = {
        "name": evaluation.measurement_name,
        "unit": evaluation.unit,
        "centerline": evaluation.centerline,
        "sigma": evaluation.sigma,
        "lsl": evaluation.lsl,
        "usl": evaluation.usl,
        "sampling_plan": {
            "planned_wafer_averages": evaluation.planned_wafer_averages,
            "observed_wafer_averages": len(evaluation.values),
            "sites_per_wafer": evaluation.sites_per_wafer,
        },
        "observations": [
            {"sequence": index, "wafer_id": f"CALLER-{index:03d}", "value": value}
            for index, value in enumerate(evaluation.values, start=1)
        ],
    }
    try:
        payload = build_disposition_evaluation(
            lot_id=evaluation.lot_id,
            tool_id=evaluation.tool_id,
            operation=evaluation.operation,
            measurement=measurement,
            tool_status=evaluation.tool_status,
            active_alarm_severity=evaluation.active_alarm_severity,
            maintenance_ack_required=evaluation.maintenance_ack_required,
            evaluated_at=evaluated_at,
            lineage={
                "dataset_id": f"caller-supplied-{evaluation.lot_id}",
                "schema_version": "fab-ops-non-production-evaluation-request-v1",
                "request_sha256": request_sha256,
                "data_classification": evaluation.data_classification,
                "origin": "caller-supplied API payload; rejected unless explicitly non-production",
                "as_of": evaluated_at,
            },
            flow_context=request_payload.get("flow_context"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    record_runtime_event(
        "non_production_disposition_evaluated",
        domain=DOMAIN,
        at=utc_now_iso(),
        lot_id=evaluation.lot_id,
        recommendation=payload["gate"]["recommendation"],
        data_classification=evaluation.data_classification,
        material_state_changed=False,
    )
    return payload


@router.get("/v1/evals/replays")
async def executed_replays_v1() -> dict[str, Any]:
    """Execute deterministic fixture and Western Electric boundary assertions."""
    record_route_hit("/api/fab-ops/v1/evals/replays")
    return build_replay_summary()


@router.get("/architecture-summary")
async def architecture_summary(
    severity: str | None = Query(default=None),
    risk_bucket: str | None = Query(default=None),
) -> dict[str, Any]:
    """Return a filtered synthetic-fixture architecture summary."""
    record_route_hit("/api/fab-ops/architecture-summary")
    return build_architecture_summary(severity=severity, risk_bucket=risk_bucket)


@router.get("/architecture-summary/schema")
async def architecture_summary_schema() -> dict[str, Any]:
    """Return the architecture summary JSON schema definition."""
    return build_architecture_summary_schema()


@router.get("/architecture-pack")
async def architecture_pack() -> dict[str, Any]:
    """Return the reviewer-facing fab review pack."""
    record_route_hit("/api/fab-ops/architecture-pack")
    return build_architecture_pack()


@router.get("/recovery-board")
async def recovery_board(mode: str | None = Query(default=None)) -> dict[str, Any]:
    """Return the recovery board, optionally filtered by board status mode."""
    record_route_hit("/api/fab-ops/recovery-board")
    return build_recovery_board(mode=mode)


@router.get("/release-board")
async def release_board() -> dict[str, Any]:
    """Return the advisory board sorted by simulated fixture risk."""
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


@router.get("/schema/alarm-report")
async def alarm_report_schema() -> dict[str, Any]:
    """Return the alarm report schema definition."""
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "evidence_boundary": build_synthetic_evidence_boundary(),
        "generated_at": utc_now_iso(),
        **build_alarm_report_schema(),
    }


@router.get("/schema/shift-handoff")
async def shift_handoff_schema() -> dict[str, Any]:
    """Return the shift handoff schema definition."""
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "evidence_boundary": build_synthetic_evidence_boundary(),
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
        "evidence_boundary": build_synthetic_evidence_boundary(),
        "items": [build_fab_summary()],
    }


@router.get("/tools")
async def tools() -> dict[str, Any]:
    """Return the list of all tools in the fab."""
    record_route_hit("/api/fab-ops/tools")
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "evidence_boundary": build_synthetic_evidence_boundary(),
        "items": TOOLS,
    }


@router.get("/tool-ownership")
async def tool_ownership(tool_id: str = Query(default="etch-14")) -> dict[str, Any]:
    """Return the ownership record for a specific tool."""
    record_route_hit("/api/fab-ops/tool-ownership")
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "evidence_boundary": build_synthetic_evidence_boundary(),
        "payload": build_tool_ownership(tool_id),
    }


@router.get("/alarms")
async def alarms() -> dict[str, Any]:
    """Return the list of all active alarms."""
    record_route_hit("/api/fab-ops/alarms")
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "evidence_boundary": build_synthetic_evidence_boundary(),
        "items": ALARMS,
    }


@router.get("/lots/at-risk")
async def lots_at_risk() -> dict[str, Any]:
    """Return fixture lots sorted by simulated risk score (descending)."""
    record_route_hit("/api/fab-ops/lots/at-risk")
    items = sorted(LOTS_AT_RISK, key=lambda item: float(cast(float | str, item["simulated_yield_risk_score"])), reverse=True)
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "evidence_boundary": build_synthetic_evidence_boundary(),
        "items": items,
    }


@router.get("/release-gate")
async def release_gate(request: Request, lot_id: str = Query(default="lot-8812")) -> dict[str, Any]:
    """Return the legacy synthetic advisory gate recommendation (auth required)."""
    require_operator_token(request, DOMAIN)
    record_route_hit("/api/fab-ops/release-gate")
    record_runtime_event("release_gate_check", domain=DOMAIN, at=utc_now_iso(), lot_id=lot_id)
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "evidence_boundary": build_synthetic_evidence_boundary(),
        "payload": build_release_gate(lot_id),
    }


@router.get("/shift-handoff")
async def shift_handoff(request: Request) -> dict[str, Any]:
    """Export the shift handoff pack (auth required)."""
    require_operator_token(request, DOMAIN)
    record_route_hit("/api/fab-ops/shift-handoff")
    record_runtime_event("handoff_export", domain=DOMAIN, at=utc_now_iso(), shift="night", fab_id="fab-west-1")
    payload = build_shift_handoff()
    handoff_id = _handoff_id_from_payload(payload)
    aws_s3 = export_handoff_to_s3(DOMAIN, handoff_id, payload)
    aws_ddb = persist_export_metadata_to_dynamodb(
        domain=DOMAIN,
        export_id=handoff_id,
        export_type="handoff_payload",
        payload=payload,
        summary={"headline": payload.get("headline"), "fab_id": payload.get("fab_id"), "shift": payload.get("shift")},
    )
    aws_sqs = publish_event_to_sqs(DOMAIN, "handoff_export", {"handoff_id": handoff_id, "s3_key": (aws_s3 or {}).get("key")})
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "evidence_boundary": build_synthetic_evidence_boundary(),
        "payload": payload,
        "aws_exports": {"s3": aws_s3, "dynamodb": aws_ddb, "sqs": aws_sqs},
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
    payload = build_handoff_signature()
    signature_id = str(payload.get("signature_id", "handoff-signature"))
    aws_s3 = export_handoff_to_s3(DOMAIN, signature_id, payload)
    aws_ddb = persist_export_metadata_to_dynamodb(
        domain=DOMAIN,
        export_id=signature_id,
        export_type="handoff_signature",
        payload=payload,
        summary={"algorithm": payload.get("algorithm"), "key_id": payload.get("key_id")},
    )
    aws_sqs = publish_event_to_sqs(DOMAIN, "handoff_signature_export", {"signature_id": signature_id, "s3_key": (aws_s3 or {}).get("key")})
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "evidence_boundary": build_synthetic_evidence_boundary(),
        "payload": payload,
        "aws_exports": {"s3": aws_s3, "dynamodb": aws_ddb, "sqs": aws_sqs},
    }


def _verify_presented_handoff(envelope: HandoffVerificationEnvelope) -> dict[str, Any]:
    """Verify and audit one validated, caller-presented envelope."""
    presented = envelope.model_dump(mode="json")
    payload = build_handoff_signature_verification(
        manifest=cast(dict[str, Any], presented["manifest"]),
        fab_id=str(presented["fab_id"]),
        signature_contract=str(presented["signature_contract"]),
        signature_id=str(presented["signature_id"]),
        signed_at=str(presented["signed_at"]),
        algorithm=str(presented["algorithm"]),
        key_id=str(presented["key_id"]),
        sha256=str(presented["sha256"]),
        signature=str(presented["signature"]),
        digest_preview=str(presented["digest_preview"]),
        generated_by=str(presented["generated_by"]),
        artifact_channel=str(presented["artifact_channel"]),
        signature_purpose=str(presented["signature_purpose"]),
        human_approval_status=str(presented["human_approval_status"]),
        human_release_authority_required=bool(presented["human_release_authority_required"]),
        verification_method=str(presented["verification_method"]),
        verification_route=str(presented["verification_route"]),
        verification_steps=[str(item) for item in presented["verification_steps"]],
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
        "evidence_boundary": build_synthetic_evidence_boundary(),
        "payload": payload,
    }


@router.post("/shift-handoff/verify")
async def shift_handoff_verify(
    request: Request,
    presented: HandoffVerificationEnvelope | HandoffVerificationRequest,
) -> dict[str, Any]:
    """Verify an exported caller-presented manifest/envelope (auth required)."""
    require_operator_token(request, DOMAIN)
    record_route_hit("/api/fab-ops/shift-handoff/verify")
    envelope = presented.payload if isinstance(presented, HandoffVerificationRequest) else presented
    return _verify_presented_handoff(envelope)


@router.get("/shift-handoff/verify", deprecated=True)
async def shift_handoff_verify_query(request: Request) -> dict[str, Any]:
    """Reject legacy query verification; exact envelopes require a POST body."""
    require_operator_token(request, DOMAIN)
    raise HTTPException(
        status_code=405,
        detail=(
            "POST the complete exported handoff payload as JSON; query verification cannot present the exact envelope"
        ),
    )


@router.get("/audit/feed")
async def audit_feed(request: Request) -> dict[str, Any]:
    """Export the audit event feed (auth required outside explicit demo mode)."""
    require_operator_token(request, DOMAIN)
    record_route_hit("/api/fab-ops/audit/feed")
    payload = build_audit_feed()
    aws_s3 = export_audit_bundle_to_s3(DOMAIN, payload["items"])
    aws_ddb = persist_export_metadata_to_dynamodb(
        domain=DOMAIN,
        export_id=f"audit-{utc_now_iso()}",
        export_type="audit_bundle",
        payload={"items": payload["items"]},
        summary={"events": payload["summary"]["events"]},
    )
    aws_sqs = publish_event_to_sqs(DOMAIN, "audit_bundle_export", {"events": payload["summary"]["events"], "s3_key": (aws_s3 or {}).get("key")})
    payload["aws_exports"] = {"s3": aws_s3, "dynamodb": aws_ddb, "sqs": aws_sqs}
    return payload


@router.get("/yield-trend", deprecated=True)
async def yield_trend() -> dict[str, Any]:
    """Return a clearly labeled synthetic UI trend; no yield is measured."""
    record_route_hit("/api/fab-ops/yield-trend")
    shifts = ["fixture-shift-1", "fixture-shift-2", "fixture-shift-3"]
    trend_data: list[dict[str, Any]] = []
    for tool in TOOLS:
        base = 0.92 if tool["status"] == "healthy" else 0.78 if tool["status"] == "warning" else 0.64
        trend_data.append(
            {
                "tool_id": tool["tool_id"],
                "fab_id": tool["fab_id"],
                "fixture_tool_status": tool["status"],
                "shifts": [
                    {"shift": shift, "simulated_yield_fraction": round(base + (index * 0.02) - 0.01, 4)}
                    for index, shift in enumerate(shifts)
                ],
            }
        )
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "evidence_boundary": build_synthetic_evidence_boundary(),
        "generated_at": utc_now_iso(),
        "data_classification": "synthetic_fixture",
        "measured_yield": False,
        "method": "deterministic display heuristic; not process capability or a yield forecast",
        "deprecated_reason": "Use the SPC disposition evidence endpoints; this compatibility trend is illustrative only.",
        "items": trend_data,
    }


@router.post("/alarms/{alarm_id}/acknowledge")
async def alarm_acknowledge(
    request: Request,
    alarm_id: str,
    operator_id: str = Query(default="ops-lead-1"),
) -> dict[str, Any]:
    """Acknowledge an active alarm (auth required)."""
    require_operator_token(request, DOMAIN)
    record_route_hit("/api/fab-ops/alarms/acknowledge")
    alarm = next((a for a in ALARMS if a["alarm_id"] == alarm_id), None)
    if alarm is None:
        raise HTTPException(status_code=404, detail=f"Unknown synthetic fixture alarm: {alarm_id}")
    ack_at = utc_now_iso()
    record_runtime_event(
        "alarm_acknowledged",
        domain=DOMAIN,
        at=ack_at,
        alarm_id=alarm_id,
        operator_id=operator_id,
        severity=alarm["severity"],
    )
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "evidence_boundary": build_synthetic_evidence_boundary(),
        "payload": {
            "alarm_id": alarm_id,
            "acknowledged_by": operator_id,
            "acknowledged_at": ack_at,
            "severity": alarm["severity"],
            "category": alarm["category"],
            "symptom": alarm["symptom"],
        },
    }


@router.get("/evals/replays")
async def replay_evals() -> dict[str, Any]:
    """Return the replay suite summary for the fab-ops domain."""
    record_route_hit("/api/fab-ops/evals/replays")
    return build_replay_summary()
