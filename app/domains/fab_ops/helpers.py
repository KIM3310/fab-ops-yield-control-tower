"""
Business logic helpers for the fab-ops domain.

Contains all ``build_*`` functions, utility helpers, and domain logic used
by the fab-ops API routes.  Every function that contributes to a JSON
response lives here so that route handlers stay thin.
"""

import logging
from datetime import UTC, datetime
from typing import Any, cast

from fastapi import HTTPException

from app.domains.fab_ops.domain import (
    ALARM_REPORT_SCHEMA,
    ALARM_SEVERITY_RANK,
    ALARMS,
    ALLOWED_RECOVERY_MODES,
    ALLOWED_RISK_BUCKETS,
    ALLOWED_SEVERITIES,
    AUDIT_EVENTS,
    FABS,
    HANDOFF_ARTIFACT_CHANNEL,
    HANDOFF_GENERATED_BY,
    HANDOFF_SIGNATURE_ALGORITHM,
    HANDOFF_SIGNATURE_CONTRACT,
    HANDOFF_SIGNATURE_PURPOSE,
    HANDOFF_VERIFICATION_METHOD,
    HANDOFF_VERIFICATION_ROUTE,
    HANDOFF_VERIFICATION_STEPS,
    LOTS_AT_RISK,
    SERVICE_NAME,
    SHIFT_HANDOFF_SCHEMA,
    TOOL_OWNERSHIP,
    TOOLS,
)
from app.domains.fab_ops.spc import (
    CONTROL_PLAN_CONTRACT,
    DISPOSITION_CONTRACT,
    build_control_plan,
    build_fixture_excursion_review,
    execute_replay_suite,
    scenario_sha256,
)
from app.shared.operator_access import build_operator_auth_status
from app.shared.runtime_store import record_runtime_event, summarize_runtime_events
from app.shared.signatures import sign_manifest, signing_key_id, signing_status, verify_signature

logger = logging.getLogger("fab_ops.helpers")

DOMAIN: str = "fab_ops"


def build_synthetic_evidence_boundary() -> dict[str, Any]:
    """Return the common truth-in-labeling boundary for fab demo outputs."""
    return {
        "data_classification": "synthetic_fixture",
        "measured_yield": False,
        "yield_forecast": False,
        "production_telemetry": False,
        "human_release_authority_required": True,
        "material_state_changes_supported": False,
    }


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def utc_now_iso() -> str:
    """Return the current UTC timestamp as an ISO-8601 string.

    Returns:
        ISO-formatted UTC datetime, e.g. ``"2026-03-08T07:12:00+00:00"``.
    """
    return datetime.now(UTC).isoformat()


def record_route_hit(route: str) -> None:
    """Persist a ``route_hit`` event for the fab-ops domain.

    Args:
        route: The API path that was accessed.
    """
    record_runtime_event("route_hit", domain=DOMAIN, at=utc_now_iso(), route=route)


def _yield_risk(item: dict[str, Any]) -> float:
    return float(cast(float | str, item["simulated_yield_risk_score"]))


def _lot_id(item: dict[str, Any]) -> str:
    return cast(str, item["lot_id"])


def _tool_id(item: dict[str, Any]) -> str:
    return cast(str, item["tool_id"])


def _alarm_rank(item: dict[str, Any]) -> int:
    return ALARM_SEVERITY_RANK.get(str(item["severity"]), 99)


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------


def get_tool_or_404(tool_id: str) -> dict[str, Any]:
    """Look up a tool by ID or raise HTTP 404.

    Args:
        tool_id: Unique tool identifier (e.g. ``"etch-14"``).

    Returns:
        The matching tool dictionary from :data:`TOOLS`.

    Raises:
        HTTPException: 404 when no tool matches *tool_id*.
    """
    for item in TOOLS:
        if item["tool_id"] == tool_id:
            return item
    logger.warning("[fab_ops] tool not found: %s", tool_id)
    raise HTTPException(status_code=404, detail=f"Unknown tool: {tool_id}")


def get_lot_or_404(lot_id: str) -> dict[str, Any]:
    """Look up a lot-at-risk by ID or raise HTTP 404.

    Args:
        lot_id: Unique lot identifier (e.g. ``"lot-8812"``).

    Returns:
        The matching lot dictionary from :data:`LOTS_AT_RISK`.

    Raises:
        HTTPException: 404 when no lot matches *lot_id*.
    """
    for item in LOTS_AT_RISK:
        if item["lot_id"] == lot_id:
            return item
    logger.warning("[fab_ops] lot not found: %s", lot_id)
    raise HTTPException(status_code=404, detail=f"Unknown lot: {lot_id}")


def normalize_architecture_filter(name: str, value: str | None, allowed: set[str]) -> str | None:
    """Validate and normalise an optional filter parameter.

    Returns ``None`` when *value* is empty or ``None``.  Raises HTTP 400 if
    *value* is non-empty but not in *allowed*.

    Args:
        name: Human-readable filter name used in the error message.
        value: The raw query parameter value.
        allowed: Set of acceptable values.

    Returns:
        The validated value, or ``None`` if the filter is inactive.

    Raises:
        HTTPException: 400 when the value is not in the allowed set.
    """
    if value is None or value == "":
        return None
    if value not in allowed:
        raise HTTPException(status_code=400, detail=f"Invalid {name} filter: {value}")
    return value


# ---------------------------------------------------------------------------
# Schema builders
# ---------------------------------------------------------------------------


def build_alarm_report_schema() -> dict[str, Any]:
    """Return the canonical alarm report schema definition.

    Returns:
        Dictionary describing required sections and operator rules for
        alarm reports.
    """
    return {
        "schema": ALARM_REPORT_SCHEMA,
        "required_sections": [
            "alarm_id",
            "tool_id",
            "severity",
            "category",
            "symptom",
            "lot_id",
            "recommended_actions",
            "sop_ref",
        ],
        "operator_rules": [
            "No alarm is marked resolved without a handoff note or maintenance decision.",
            "Severity drives queue ordering before any AI summary is trusted.",
            "Recommendations must remain grounded in tool, lot, and SOP context.",
        ],
    }


def build_shift_handoff_schema() -> dict[str, Any]:
    """Return the canonical shift handoff schema definition.

    Returns:
        Dictionary describing required sections and operator rules for
        shift handoff packs.
    """
    return {
        "schema": SHIFT_HANDOFF_SCHEMA,
        "required_sections": [
            "fab_id",
            "shift",
            "open_critical_alarms",
            "lots_at_risk",
            "tool_watchlist",
            "must_acknowledge",
            "spc_evidence_binding",
        ],
        "operator_rules": [
            "Critical alarms must be acknowledged in the handoff export.",
            "Synthetic fixture-risk lots stay visible until an authorized human review is recorded.",
            "The handoff pack is reviewable without live integrations.",
        ],
    }


# ---------------------------------------------------------------------------
# Domain logic builders
# ---------------------------------------------------------------------------


def build_tool_ownership(tool_id: str) -> dict[str, Any]:
    """Build the enriched tool ownership record for *tool_id*.

    Merges static ownership data with live tool status fields.

    Args:
        tool_id: Unique tool identifier.

    Returns:
        Combined ownership + tool status dictionary.

    Raises:
        HTTPException: 404 when tool or ownership record is missing.
    """
    tool = get_tool_or_404(tool_id)
    ownership = TOOL_OWNERSHIP.get(tool_id)
    if ownership is None:
        raise HTTPException(status_code=404, detail=f"No ownership record for tool: {tool_id}")
    return {
        **ownership,
        "line": tool["line"],
        "status": tool["status"],
        "current_alarm_id": tool["current_alarm_id"],
        "mtbf_risk": tool["mtbf_risk"],
    }


def build_release_gate(lot_id: str) -> dict[str, Any]:
    """Evaluate the release gate decision for a lot.

    The advisory result is ``"hold-release"``, ``"reroute-check"``, or
    ``"release-with-sampling"`` based on simulated fixture risk, tool state,
    and acknowledgement evidence. It never changes material state.

    Args:
        lot_id: Lot identifier to evaluate.

    Returns:
        Release gate payload including decision, failed checks, and ownership.
    """
    lot = get_lot_or_404(lot_id)
    tool = get_tool_or_404(lot["tool_id"])
    assignment = build_tool_ownership(tool["tool_id"])

    simulated_risk = float(lot["simulated_yield_risk_score"])
    if tool["status"] == "alarm" or simulated_risk >= 0.85:
        decision = "hold-release"
    elif tool["status"] == "warning" or simulated_risk >= 0.65 or assignment["ack_required"]:
        decision = "reroute-check"
    else:
        decision = "release-with-sampling"

    failed_checks: list[str] = []
    if tool["status"] == "alarm":
        failed_checks.append("critical tool alarm still open")
    elif tool["status"] == "warning":
        failed_checks.append("fixture tool warning still open")
    if simulated_risk >= 0.85:
        failed_checks.append("simulated fixture risk score exceeds severe threshold")
    if assignment["ack_required"]:
        failed_checks.append("maintenance owner acknowledgement still required")

    logger.info("[fab_ops] release gate for %s: decision=%s", lot_id, decision)
    return {
        "lot_id": lot_id,
        "tool_id": tool["tool_id"],
        "decision": decision,
        "decision_type": "advisory_fixture_recommendation",
        "simulated_yield_risk_score": lot["simulated_yield_risk_score"],
        "tool_status": tool["status"],
        "next_action": lot["next_action"],
        "primary_operator": assignment["primary_operator"],
        "maintenance_owner": assignment["maintenance_owner"],
        "failed_checks": failed_checks,
        "data_classification": "synthetic_fixture",
        "risk_basis": "hand-authored simulated workflow score; not measured yield",
        "human_release_authority_required": True,
        "human_approval_status": "not_recorded",
        "material_state_changed": False,
    }


def _build_spc_handoff_binding(lot_id: str = "lot-8812") -> dict[str, Any]:
    """Bind the signed handoff to the executed synthetic SPC evidence chain."""
    disposition = build_fixture_excursion_review(lot_id)
    control_plan = build_control_plan()
    flow = disposition["flow_indicators"]
    return {
        "binding_contract": "fab-ops-handoff-spc-evidence-binding-v1",
        "data_classification": "synthetic_fixture",
        "dataset_id": disposition["lineage"]["dataset_id"],
        "fixture_sha256": disposition["lineage"]["fixture_sha256"],
        "control_plan_contract": CONTROL_PLAN_CONTRACT,
        "control_plan_policy_id": control_plan["control_plan"]["policy_id"],
        "control_plan_revision": control_plan["control_plan"]["revision"],
        "disposition_contract": DISPOSITION_CONTRACT,
        "disposition_evaluated_at": disposition["evaluated_at"],
        "lot_id": disposition["lot"]["lot_id"],
        "recommendation": disposition["gate"]["recommendation"],
        "data_quality_status": disposition["spc"]["data_quality"]["status"],
        "unique_rule_ids": disposition["spc"]["unique_rule_ids"],
        "q_time_status": flow["q_time"]["status"],
        "tat_status": flow["tat"]["status"],
        "route_state": flow["routing"]["route_state"],
        "human_release_authority_required": True,
        "human_approval_status": "not_recorded",
        "material_state_changed": False,
        "proof_routes": {
            "control_plan": "/api/fab-ops/v1/control-plan",
            "disposition": f"/api/fab-ops/v1/lots/{lot_id}/disposition",
            "replays": "/api/fab-ops/v1/evals/replays",
        },
    }


def build_shift_handoff(*, generated_at: str | None = None) -> dict[str, Any]:
    """Build the night-shift handoff pack for fab-west-1.

    Sorts lots by simulated fixture risk (descending) and identifies tools on the
    watchlist (non-healthy status).

    Returns:
        Shift handoff payload with headline, alarms, lots, and acknowledgements.
    """
    sorted_lots = sorted(LOTS_AT_RISK, key=_yield_risk, reverse=True)
    watchlist = [tool for tool in TOOLS if tool["status"] != "healthy"]
    return {
        "fab_id": "fab-west-1",
        "shift": "night",
        "generated_at": generated_at or utc_now_iso(),
        "schema": SHIFT_HANDOFF_SCHEMA,
        "data_classification": "synthetic_fixture",
        "measured_yield": False,
        "human_release_authority_required": True,
        "human_approval_status": "not_recorded",
        "material_state_changed": False,
        "headline": "One synthetic severe-risk lot needs human review before any release decision.",
        "open_critical_alarms": [alarm["alarm_id"] for alarm in ALARMS if alarm["severity"] == "critical"],
        "lots_at_risk": sorted_lots,
        "tool_watchlist": watchlist,
        "must_acknowledge": [
            "etch-14 maintenance approval",
            "lot-8812 reroute decision",
            "depo-03 drift inspection assignment",
        ],
        "spc_evidence_binding": _build_spc_handoff_binding(),
    }


def build_focus_lot() -> dict[str, Any]:
    """Build the spotlight focus-lot summary centred on lot-8812.

    Composes alarm, tool, release gate, ownership, and handoff data into
    a single navigable entry point.

    Returns:
        Focus lot payload with review path links.
    """
    spotlight_lot = get_lot_or_404("lot-8812")
    spotlight_alarm = next(
        (alarm for alarm in ALARMS if alarm["lot_id"] == spotlight_lot["lot_id"]),
        None,
    )
    if spotlight_alarm is None:
        raise HTTPException(status_code=404, detail="No alarm linked to focus lot lot-8812")
    spotlight_tool = get_tool_or_404(spotlight_lot["tool_id"])
    release_gate = build_release_gate(spotlight_lot["lot_id"])
    ownership = build_tool_ownership(spotlight_tool["tool_id"])
    handoff = build_shift_handoff()
    return {
        "lot_id": spotlight_lot["lot_id"],
        "alarm_id": spotlight_alarm["alarm_id"],
        "tool_id": spotlight_tool["tool_id"],
        "severity": spotlight_alarm["severity"],
        "risk_bucket": spotlight_lot["risk_bucket"],
        "release_decision": release_gate["decision"],
        "decision_type": "advisory_fixture_recommendation",
        "evidence_boundary": build_synthetic_evidence_boundary(),
        "next_action": spotlight_lot["next_action"],
        "maintenance_owner": ownership["maintenance_owner"],
        "handoff_headline": handoff["headline"],
        "architecture_path": [
            "/api/fab-ops/runtime/brief",
            "/api/fab-ops/recovery-board?mode=hold",
            f"/api/fab-ops/release-gate?lot_id={spotlight_lot['lot_id']}",
            f"/api/fab-ops/v1/lots/{spotlight_lot['lot_id']}/disposition",
            "/api/fab-ops/shift-handoff/signature",
        ],
    }


def build_fab_summary() -> dict[str, Any]:
    """Build a high-level summary of the fab's operational posture.

    Returns:
        Dictionary with tool counts, alarm counts, and health breakdown.
    """
    critical_alarms = [alarm for alarm in ALARMS if alarm["severity"] == "critical"]
    severe_lots = [lot for lot in LOTS_AT_RISK if _yield_risk(lot) >= 0.8]
    return {
        "fab_id": "fab-west-1",
        "evidence_boundary": build_synthetic_evidence_boundary(),
        "headline": "Synthetic night-shift fixture: etch-bay-a blocks one severe-risk scenario lot.",
        "tool_count": len(TOOLS),
        "alarm_count": len(ALARMS),
        "critical_alarm_count": len(critical_alarms),
        "severe_lot_count": len(severe_lots),
        "healthy_tools": len([tool for tool in TOOLS if tool["status"] == "healthy"]),
        "degraded_tools": len([tool for tool in TOOLS if tool["status"] != "healthy"]),
    }


def build_recovery_what_if(
    lot_id: str,
    *,
    yield_gain: float = 0.2,
    maintenance_complete: bool = False,
) -> dict[str, Any]:
    """Run a what-if simulation for a recovery scenario.

    Simulates the effect of a simulated risk reduction and/or maintenance completion
    on the lot's advisory gate recommendation.

    Args:
        lot_id: Lot identifier to simulate.
        yield_gain: Simulated fixture risk-score reduction (clamped to 0.0--0.5).
        maintenance_complete: Whether to simulate the tool becoming healthy.

    Returns:
        Comparison payload with baseline, simulated, and delta sections.
    """
    baseline = build_release_gate(lot_id)
    lot = get_lot_or_404(lot_id)
    tool = get_tool_or_404(lot["tool_id"])
    assignment = build_tool_ownership(tool["tool_id"])

    simulated_yield_risk = round(max(0.0, float(lot["simulated_yield_risk_score"]) - max(0.0, min(0.5, yield_gain))), 2)
    simulated_tool_status = "healthy" if maintenance_complete else tool["status"]
    simulated_ack_required = False if maintenance_complete else assignment["ack_required"]

    if simulated_tool_status == "alarm" or simulated_yield_risk >= 0.85:
        simulated_decision = "hold-release"
    elif simulated_tool_status == "warning" or simulated_yield_risk >= 0.65 or simulated_ack_required:
        simulated_decision = "reroute-check"
    else:
        simulated_decision = "release-with-sampling"

    simulated_failed_checks: list[str] = []
    if simulated_tool_status == "alarm":
        simulated_failed_checks.append("critical tool alarm still open")
    elif simulated_tool_status == "warning":
        simulated_failed_checks.append("fixture tool warning still open")
    if simulated_yield_risk >= 0.85:
        simulated_failed_checks.append("simulated fixture risk score exceeds severe threshold")
    if simulated_ack_required:
        simulated_failed_checks.append("maintenance owner acknowledgement still required")

    baseline_eta = 240 if baseline["decision"] == "hold-release" else 90 if baseline["decision"] == "reroute-check" else 30
    simulated_eta = 240 if simulated_decision == "hold-release" else 90 if simulated_decision == "reroute-check" else 30

    logger.info(
        "[fab_ops] what-if for %s: baseline=%s simulated=%s",
        lot_id,
        baseline["decision"],
        simulated_decision,
    )
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "evidence_boundary": build_synthetic_evidence_boundary(),
        "generated_at": utc_now_iso(),
        "contract_version": "fab-ops-recovery-what-if-v1",
        "lot_id": lot_id,
        "baseline": {**baseline, "release_eta_minutes": baseline_eta},
        "simulated": {
            "lot_id": lot_id,
            "tool_id": tool["tool_id"],
            "decision": simulated_decision,
            "simulated_yield_risk_score": simulated_yield_risk,
            "tool_status": simulated_tool_status,
            "next_action": "Promote recovery path to release board if simulated posture holds through the next shift."
            if simulated_decision != "hold-release"
            else lot["next_action"],
            "primary_operator": assignment["primary_operator"],
            "maintenance_owner": assignment["maintenance_owner"],
            "failed_checks": simulated_failed_checks,
            "release_eta_minutes": simulated_eta,
            "risk_basis": "hand-authored simulated workflow score; not measured yield",
            "human_release_authority_required": True,
            "human_approval_status": "not_recorded",
            "material_state_changed": False,
        },
        "delta": {
            "risk_score_reduction": round(float(baseline["simulated_yield_risk_score"]) - simulated_yield_risk, 2),
            "release_eta_minutes": max(0, baseline_eta - simulated_eta),
            "maintenance_clearance": maintenance_complete,
        },
        "operator_actions": [
            "Run the what-if drill before claiming the lot is ready for release or reroute.",
            "Pair the simulated decision with tool ownership and handoff signature before shift change.",
            "Use recovery board + release gate + what-if together during maintenance approval review.",
        ],
        "route_bundle": {
            "recovery_board": "/api/fab-ops/recovery-board",
            "recovery_what_if": "/api/fab-ops/recovery-what-if",
            "release_gate": f"/api/fab-ops/release-gate?lot_id={lot_id}",
            "shift_handoff_signature": "/api/fab-ops/shift-handoff/signature",
        },
    }


def build_release_board() -> dict[str, Any]:
    """Build the advisory board sorted by simulated fixture risk.

    Each lot is enriched with its release gate decision and ownership info.

    Returns:
        Release board payload with summary, spotlight, and item list.
    """
    items: list[dict[str, Any]] = []
    for lot in sorted(LOTS_AT_RISK, key=_yield_risk, reverse=True):
        gate = build_release_gate(_lot_id(lot))
        ownership = build_tool_ownership(_tool_id(lot))
        items.append(
            {
                "lot_id": lot["lot_id"],
                "tool_id": lot["tool_id"],
                "decision": gate["decision"],
                "simulated_yield_risk_score": lot["simulated_yield_risk_score"],
                "risk_bucket": lot["risk_bucket"],
                "failed_checks": gate["failed_checks"],
                "maintenance_owner": ownership["maintenance_owner"],
                "ack_required": ownership["ack_required"],
                "next_action": gate["next_action"],
                "risk_basis": "hand-authored synthetic fixture; not measured yield",
                "human_release_authority_required": True,
                "human_approval_status": "not_recorded",
                "material_state_changed": False,
            }
        )
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "evidence_boundary": build_synthetic_evidence_boundary(),
        "generated_at": utc_now_iso(),
        "contract_version": "fab-ops-release-board-v1",
        "summary": {
            "visible_lots": len(items),
            "hold_release": len([item for item in items if item["decision"] == "hold-release"]),
            "reroute_check": len([item for item in items if item["decision"] == "reroute-check"]),
            "release_with_sampling": len([item for item in items if item["decision"] == "release-with-sampling"]),
        },
        "spotlight": items[0] if items else None,
        "items": items,
        "operator_actions": [
            "Review the release board before discussing any lot as a candidate for human release review.",
            "Keep failed checks and maintenance ownership paired so every advisory recommendation names the next reviewer.",
            "Use the board and HMAC integrity envelope as review evidence; only authorized humans make the go/no-go decision.",
        ],
        "route_bundle": {
            "release_board": "/api/fab-ops/release-board",
            "recovery_board": "/api/fab-ops/recovery-board",
            "release_gate": "/api/fab-ops/release-gate?lot_id=lot-8812",
            "shift_handoff": "/api/fab-ops/shift-handoff",
        },
    }


def build_handoff_signature(*, generated_at: str | None = None) -> dict[str, Any]:
    """Build and sign the shift handoff manifest.

    Produces an HMAC-SHA256 signature over the canonical JSON of the handoff
    payload, along with metadata for downstream verification.

    Returns:
        Signature envelope with digest, HMAC, key ID, and the manifest.
    """
    handoff = build_shift_handoff(generated_at=generated_at)
    sigs = sign_manifest(handoff, DOMAIN)
    logger.info("[fab_ops] handoff signature generated for %s/%s", handoff["fab_id"], handoff["shift"])
    return {
        "fab_id": handoff["fab_id"],
        "signature_contract": HANDOFF_SIGNATURE_CONTRACT,
        "signature_id": f"handoff-{handoff['fab_id']}-{handoff['shift']}",
        "algorithm": HANDOFF_SIGNATURE_ALGORITHM,
        "key_id": signing_key_id(DOMAIN),
        "sha256": sigs["sha256"],
        "signature": sigs["signature"],
        "digest_preview": sigs["sha256"][:16],
        "generated_by": HANDOFF_GENERATED_BY,
        "signed_at": handoff["generated_at"],
        "artifact_channel": HANDOFF_ARTIFACT_CHANNEL,
        "signature_purpose": HANDOFF_SIGNATURE_PURPOSE,
        "human_approval_status": "not_recorded",
        "human_release_authority_required": True,
        "manifest": handoff,
        "verification_method": HANDOFF_VERIFICATION_METHOD,
        "verification_route": HANDOFF_VERIFICATION_ROUTE,
        "verification_steps": list(HANDOFF_VERIFICATION_STEPS),
    }


def build_handoff_signature_verification(
    *,
    manifest: dict[str, Any] | None = None,
    fab_id: str | None = None,
    signature_contract: str | None = None,
    signature_id: str | None = None,
    signed_at: str | None = None,
    algorithm: str | None = None,
    key_id: str | None = None,
    sha256: str | None = None,
    signature: str | None = None,
    digest_preview: str | None = None,
    generated_by: str | None = None,
    artifact_channel: str | None = None,
    signature_purpose: str | None = None,
    human_approval_status: str | None = None,
    human_release_authority_required: bool | None = None,
    verification_method: str | None = None,
    verification_route: str | None = None,
    verification_steps: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Verify the exact caller-presented manifest and integrity envelope.

    Nothing is rebuilt from ``signed_at``. This distinction is security
    critical: changing a manifest field while reusing its original digest/HMAC
    must fail, including changes to the embedded SPC lineage binding.
    """
    presented_manifest = manifest if isinstance(manifest, dict) else {}
    input_complete = bool(
        isinstance(manifest, dict)
        and manifest
        and all(
            value is not None and str(value).strip()
            for value in (
                fab_id,
                signature_contract,
                signature_id,
                signed_at,
                algorithm,
                key_id,
                sha256,
                signature,
                digest_preview,
                generated_by,
                artifact_channel,
                signature_purpose,
                human_approval_status,
                human_release_authority_required,
                verification_method,
                verification_route,
                verification_steps,
            )
        )
    )
    cryptographic = verify_signature(
        presented_manifest,
        provided_algorithm=algorithm,
        provided_key_id=key_id,
        provided_sha256=sha256,
        provided_signature=signature,
        domain=DOMAIN,
    )

    manifest_fab_id = str(presented_manifest.get("fab_id", ""))
    manifest_shift = str(presented_manifest.get("shift", ""))
    expected_signature_id = f"handoff-{manifest_fab_id}-{manifest_shift}"
    binding = presented_manifest.get("spc_evidence_binding")
    binding_payload = binding if isinstance(binding, dict) else {}
    envelope_checks = {
        "manifest_present": bool(presented_manifest),
        "manifest_schema_match": presented_manifest.get("schema") == SHIFT_HANDOFF_SCHEMA,
        "fab_id_matches_manifest": bool(fab_id) and str(fab_id) == manifest_fab_id,
        "signature_contract_match": signature_contract == HANDOFF_SIGNATURE_CONTRACT,
        "signature_id_matches_manifest": bool(signature_id) and str(signature_id) == expected_signature_id,
        "signed_at_matches_manifest": bool(signed_at) and str(signed_at) == str(presented_manifest.get("generated_at", "")),
        "digest_preview_matches_sha256": bool(sha256) and digest_preview == str(sha256)[:16],
        "generated_by_match": generated_by == HANDOFF_GENERATED_BY,
        "artifact_channel_match": artifact_channel == HANDOFF_ARTIFACT_CHANNEL,
        "signature_purpose_match": signature_purpose == HANDOFF_SIGNATURE_PURPOSE,
        "outer_human_approval_status_match": (
            human_approval_status == "not_recorded"
            and human_approval_status == presented_manifest.get("human_approval_status")
        ),
        "outer_human_release_authority_match": (
            human_release_authority_required is True
            and human_release_authority_required
            == presented_manifest.get("human_release_authority_required")
        ),
        "verification_method_match": verification_method == HANDOFF_VERIFICATION_METHOD,
        "verification_route_match": verification_route == HANDOFF_VERIFICATION_ROUTE,
        "verification_steps_match": (
            isinstance(verification_steps, (list, tuple))
            and tuple(verification_steps) == HANDOFF_VERIFICATION_STEPS
        ),
        "spc_evidence_binding_present": bool(binding_payload),
        "spc_binding_contract_match": (
            binding_payload.get("binding_contract") == "fab-ops-handoff-spc-evidence-binding-v1"
        ),
        "spc_control_plan_contract_match": binding_payload.get("control_plan_contract") == CONTROL_PLAN_CONTRACT,
        "spc_disposition_contract_match": binding_payload.get("disposition_contract") == DISPOSITION_CONTRACT,
        "spc_fixture_sha256_present": (
            isinstance(binding_payload.get("fixture_sha256"), str)
            and len(str(binding_payload.get("fixture_sha256"))) == 64
            and all(character in "0123456789abcdef" for character in str(binding_payload.get("fixture_sha256")))
        ),
        "spc_fixture_sha256_matches_packaged_fixture": binding_payload.get("fixture_sha256") == scenario_sha256(),
        "spc_policy_identity_present": bool(
            str(binding_payload.get("control_plan_policy_id", "")).strip()
            and str(binding_payload.get("control_plan_revision", "")).strip()
        ),
        "spc_disposition_evidence_complete": (
            bool(str(binding_payload.get("dataset_id", "")).strip())
            and bool(str(binding_payload.get("lot_id", "")).strip())
            and binding_payload.get("recommendation")
            in {"HOLD_FOR_CONTAINMENT", "ENGINEERING_REVIEW", "RELEASE_WITH_SAMPLING"}
            and binding_payload.get("data_quality_status") in {"pass", "fail"}
            and isinstance(binding_payload.get("unique_rule_ids"), list)
            and binding_payload.get("q_time_status") in {"within_window", "at_risk", "breached"}
            and binding_payload.get("tat_status") in {"within_target", "over_target"}
            and binding_payload.get("route_state")
            in {
                "in_queue",
                "hold",
                "awaiting_engineering_review",
                "ready_for_reviewed_dispatch",
                "in_process",
                "complete",
            }
        ),
        "spc_human_authority_preserved": (
            binding_payload.get("human_release_authority_required") is True
            and binding_payload.get("human_approval_status") == "not_recorded"
            and binding_payload.get("material_state_changed") is False
        ),
    }
    checks = {**cryptographic["checks"], **envelope_checks}
    overall_valid = bool(input_complete and all(checks.values()))
    return {
        "fab_id": manifest_fab_id or (str(fab_id) if fab_id else None),
        "verification_contract": "fab-ops-handoff-signature-verify-v1",
        "signature_contract": signature_contract,
        "signature_id": signature_id,
        "verification_mode": "caller_supplied_manifest_and_envelope",
        "input_complete": input_complete,
        "overall_valid": overall_valid,
        "external_proof_verified": overall_valid,
        "checks": checks,
        "verified_manifest_sha256": sha256 if overall_valid else None,
        "human_approval_verified": False,
        "verification_method": HANDOFF_VERIFICATION_METHOD,
        "verification_route": HANDOFF_VERIFICATION_ROUTE,
    }


def build_audit_feed() -> dict[str, Any]:
    """Build the audit event feed for the fab-ops domain.

    Returns:
        Dictionary with summary counts and the raw audit event list.
    """
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "evidence_boundary": build_synthetic_evidence_boundary(),
        "summary": {
            "events": len(AUDIT_EVENTS),
            "critical_alarm_count": len([alarm for alarm in ALARMS if alarm["severity"] == "critical"]),
            "watchlist_tools": len([tool for tool in TOOLS if tool["status"] != "healthy"]),
        },
        "items": AUDIT_EVENTS,
    }


def build_replay_summary() -> dict[str, Any]:
    """Execute the packaged disposition and SPC replay assertions."""
    result = execute_replay_suite()
    return {**result, "service": SERVICE_NAME, "evidence_boundary": build_synthetic_evidence_boundary()}


def build_architecture_summary(severity: str | None = None, risk_bucket: str | None = None) -> dict[str, Any]:
    """Build a filtered architecture summary of alarms and lots.

    Args:
        severity: Optional alarm severity filter (e.g. ``"critical"``).
        risk_bucket: Optional lot risk bucket filter (e.g. ``"severe"``).

    Returns:
        Architecture summary payload with filtered counts and spotlight items.
    """
    severity_filter = normalize_architecture_filter("severity", severity, ALLOWED_SEVERITIES)
    risk_bucket_filter = normalize_architecture_filter("risk_bucket", risk_bucket, ALLOWED_RISK_BUCKETS)
    filtered_alarms = [item for item in ALARMS if severity_filter is None or item["severity"] == severity_filter]
    filtered_lots = [item for item in LOTS_AT_RISK if risk_bucket_filter is None or item["risk_bucket"] == risk_bucket_filter]
    spotlight_alarm = sorted(filtered_alarms, key=lambda item: (_alarm_rank(item), str(item["started_at"])))[0] if filtered_alarms else None
    spotlight_lot = sorted(filtered_lots, key=_yield_risk, reverse=True)[0] if filtered_lots else None
    replay_summary = build_replay_summary()
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "evidence_boundary": build_synthetic_evidence_boundary(),
        "generated_at": utc_now_iso(),
        "contract_version": "fab-ops-architecture-summary-v1",
        "filters": {"severity": severity_filter, "risk_bucket": risk_bucket_filter},
        "summary": {
            "alarm_count": len(filtered_alarms),
            "lot_count": len(filtered_lots),
            "critical_alarm_count": len([item for item in filtered_alarms if item["severity"] == "critical"]),
            "severe_lot_count": len([item for item in filtered_lots if item["risk_bucket"] == "severe"]),
            "replay_score_pct": replay_summary["summary"]["score_pct"],
        },
        "spotlight": {"alarm": spotlight_alarm, "lot": spotlight_lot},
        "fastest_architecture_path": [
            "/health",
            "/api/fab-ops/architecture-summary",
            "/api/fab-ops/tool-ownership",
            "/api/fab-ops/release-gate",
            "/api/fab-ops/shift-handoff",
        ],
        "route_bundle": {
            "architecture_summary": "/api/fab-ops/architecture-summary",
            "architecture_pack": "/api/fab-ops/architecture-pack",
            "tool_ownership": "/api/fab-ops/tool-ownership?tool_id=etch-14",
            "release_gate": "/api/fab-ops/release-gate?lot_id=lot-8812",
            "shift_handoff": "/api/fab-ops/shift-handoff",
        },
    }


def build_recovery_board(mode: str | None = None) -> dict[str, Any]:
    """Build the recovery board filtered by board status mode.

    Args:
        mode: Optional filter -- ``"hold"``, ``"watch"``, ``"ready"``, or ``"all"``.

    Returns:
        Recovery board payload with summary, items, and operator actions.
    """
    normalized_mode = normalize_architecture_filter("mode", mode, ALLOWED_RECOVERY_MODES) or "all"
    items: list[dict[str, Any]] = []
    for lot in sorted(LOTS_AT_RISK, key=_yield_risk, reverse=True):
        gate = build_release_gate(_lot_id(lot))
        tool = get_tool_or_404(_tool_id(lot))
        ownership = build_tool_ownership(tool["tool_id"])
        if gate["decision"] == "hold-release":
            board_status = "hold"
        elif gate["decision"] == "reroute-check":
            board_status = "watch"
        else:
            board_status = "ready"
        if normalized_mode != "all" and board_status != normalized_mode:
            continue
        items.append(
            {
                "lot_id": lot["lot_id"],
                "tool_id": lot["tool_id"],
                "product_family": lot["product_family"],
                "simulated_yield_risk_score": lot["simulated_yield_risk_score"],
                "risk_bucket": lot["risk_bucket"],
                "board_status": board_status,
                "release_decision": gate["decision"],
                "tool_status": tool["status"],
                "maintenance_owner": ownership["maintenance_owner"],
                "ack_required": ownership["ack_required"],
                "escalation_lane": ownership["escalation_lane"],
                "failed_checks": gate["failed_checks"],
                "next_action": gate["next_action"],
                "risk_basis": "hand-authored synthetic fixture; not measured yield",
                "human_release_authority_required": True,
                "human_approval_status": "not_recorded",
                "material_state_changed": False,
            }
        )
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "evidence_boundary": build_synthetic_evidence_boundary(),
        "generated_at": utc_now_iso(),
        "contract_version": "fab-ops-recovery-board-v1",
        "filters": {"mode": normalized_mode},
        "summary": {
            "visible_lots": len(items),
            "hold_count": len([item for item in items if item["board_status"] == "hold"]),
            "watch_count": len([item for item in items if item["board_status"] == "watch"]),
            "ready_count": len([item for item in items if item["board_status"] == "ready"]),
        },
        "spotlight": items[0] if items else None,
        "items": items,
        "operator_actions": [
            "Start with hold lots before reviewing watch or ready lots.",
            "Keep tool ownership, release gate, and handoff pack together during shift handoff.",
            "Treat the HMAC envelope as integrity evidence, not human release approval.",
        ],
        "route_bundle": {
            "recovery_board": "/api/fab-ops/recovery-board",
            "recovery_board_schema": "/api/fab-ops/recovery-board/schema",
            "architecture_summary": "/api/fab-ops/architecture-summary",
            "tool_ownership": "/api/fab-ops/tool-ownership?tool_id=etch-14",
            "release_gate": "/api/fab-ops/release-gate?lot_id=lot-8812",
            "shift_handoff": "/api/fab-ops/shift-handoff",
        },
    }


def build_recovery_board_schema() -> dict[str, Any]:
    """Return the recovery board JSON schema definition.

    Returns:
        Schema dictionary with required fields and navigation links.
    """
    return {
        "schema": "fab-ops-recovery-board-v1",
        "required_fields": ["contract_version", "summary.visible_lots", "summary.hold_count", "items", "route_bundle.recovery_board"],
        "links": {
            "recovery_board": "/api/fab-ops/recovery-board",
            "recovery_what_if": "/api/fab-ops/recovery-what-if",
            "recovery_board_schema": "/api/fab-ops/recovery-board/schema",
            "architecture_summary": "/api/fab-ops/architecture-summary",
            "architecture_pack": "/api/fab-ops/architecture-pack",
            "runtime_scorecard": "/api/fab-ops/runtime/scorecard",
        },
    }


def build_architecture_summary_schema() -> dict[str, Any]:
    """Return the architecture summary JSON schema definition.

    Returns:
        Schema dictionary with required fields and navigation links.
    """
    return {
        "schema": "fab-ops-architecture-summary-v1",
        "required_fields": [
            "service",
            "contract_version",
            "summary.alarm_count",
            "summary.replay_score_pct",
            "fastest_architecture_path",
            "route_bundle.architecture_summary",
        ],
        "links": {
            "architecture_summary": "/api/fab-ops/architecture-summary",
            "recovery_board": "/api/fab-ops/recovery-board",
            "architecture_pack": "/api/fab-ops/architecture-pack",
            "runtime_brief": "/api/fab-ops/runtime/brief",
        },
    }


def build_runtime_brief() -> dict[str, Any]:
    """Build the comprehensive runtime brief for the fab-ops control tower.

    This is the primary entry-point payload that ties together alarm counts,
    simulated fixture risk, recovery board, release board, operator auth, and persistence
    into one surface.

    Returns:
        Runtime brief payload.
    """
    summary = build_fab_summary()
    recovery_board = build_recovery_board()
    release_board = build_release_board()
    operator_auth = build_operator_auth_status(DOMAIN)
    persistence = summarize_runtime_events(DOMAIN)
    focus_lot = build_focus_lot()
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "evidence_boundary": build_synthetic_evidence_boundary(),
        "generated_at": utc_now_iso(),
        "readiness_contract": "fab-ops-runtime-brief-v1",
        "headline": "Fab demo that keeps alarms, synthetic fixture risk, tool health, and shift evidence in one reviewable operator flow.",
        "report_contract": build_alarm_report_schema(),
        "handoff_contract": build_shift_handoff_schema(),
        "evidence_counts": {
            "fabs": len(FABS),
            "tools": len(TOOLS),
            "alarms": len(ALARMS),
            "lots_at_risk": len(LOTS_AT_RISK),
            "replay_scenarios": build_replay_summary()["summary"]["scenarios"],
            "recovery_routes": len(recovery_board["items"]),
            "release_board_rows": release_board["summary"]["visible_lots"],
        },
        "assignment_count": len(TOOL_OWNERSHIP),
        "focus_lot": focus_lot,
        "operator_auth": operator_auth,
        "persistence": persistence,
        "ops_snapshot": summary,
        "architecture_flow": [
            "Open /health to confirm the fab runtime posture and review routes.",
            "Read /api/fab-ops/runtime/brief for the control-tower contract and evidence counts.",
            "Use /api/fab-ops/recovery-board to separate hold lots from watch and human-review candidates.",
            "Use /api/fab-ops/release-board to confirm the whole queue before discussing any single lot release.",
            "Inspect /api/fab-ops/tool-ownership and /api/fab-ops/release-gate before acting on a shift decision.",
            "Export the handoff and HMAC envelope as integrity evidence; a separate authorized human decision is required for release.",
        ],
        "two_minute_architecture": [
            "Open /health to confirm critical-alarm and replay surfaces are available.",
            "Read /api/fab-ops/runtime/brief for the control-tower contract and current ops snapshot.",
            "Inspect /api/fab-ops/recovery-board?mode=hold to find the lot that blocks release posture.",
            "Inspect /api/fab-ops/release-board before treating any downstream lot as eligible for human release review.",
            "Inspect /api/fab-ops/tool-ownership?tool_id=etch-14 and /api/fab-ops/release-gate?lot_id=lot-8812 before trusting release posture.",
            "Review /api/fab-ops/shift-handoff, /api/fab-ops/shift-handoff/signature, and /api/fab-ops/shift-handoff/verify before handing the queue to the next shift.",
        ],
        "watchouts": [
            "The demo uses synthetic fab telemetry and does not claim MES connectivity.",
            "Recommendations are grounded in alarm, lot, and SOP context only.",
            "The queue is intentionally small so reviewer paths stay easy to follow.",
        ],
        "proof_assets": [
            {"label": "Health Surface", "href": "/health", "kind": "route"},
            {"label": "SPC Control Plan", "href": "/api/fab-ops/v1/control-plan", "kind": "route"},
            {"label": "Executed Disposition", "href": "/api/fab-ops/v1/lots/lot-8812/disposition", "kind": "route"},
            {"label": "Executed Replays", "href": "/api/fab-ops/v1/evals/replays", "kind": "route"},
            {"label": "Recovery Board", "href": "/api/fab-ops/recovery-board?mode=hold", "kind": "route"},
            {"label": "Release Board", "href": "/api/fab-ops/release-board", "kind": "route"},
        ],
        "links": {
            "runtime_scorecard": "/api/fab-ops/runtime/scorecard",
            "architecture_summary": "/api/fab-ops/architecture-summary",
            "recovery_board": "/api/fab-ops/recovery-board",
            "release_board": "/api/fab-ops/release-board",
            "recovery_what_if": "/api/fab-ops/recovery-what-if",
            "architecture_pack": "/api/fab-ops/architecture-pack",
            "spc_control_plan": "/api/fab-ops/v1/control-plan",
            "fixture_disposition": "/api/fab-ops/v1/lots/lot-8812/disposition",
            "executed_replays": "/api/fab-ops/v1/evals/replays",
        },
    }


def build_architecture_pack() -> dict[str, Any]:
    """Build the shift-ready review pack for the fab-ops domain.

    Aggregates the runtime brief, audit feed, recovery board, release board,
    and focus lot into one comprehensive review artifact.

    Returns:
        Review pack payload.
    """
    runtime_brief = build_runtime_brief()
    audit_feed = build_audit_feed()
    recovery_board = build_recovery_board()
    release_board = build_release_board()
    focus_lot = build_focus_lot()
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "evidence_boundary": build_synthetic_evidence_boundary(),
        "generated_at": utc_now_iso(),
        "readiness_contract": "fab-ops-architecture-pack-v1",
        "headline": "Control tower summary tying alarms, simulated fixture risk, tool watchlist, and handoff export into one view.",
        "proof_bundle": {
            "architecture_routes": [
                "/health",
                "/api/fab-ops/meta",
                "/api/fab-ops/runtime/brief",
                "/api/fab-ops/runtime/scorecard",
                "/api/fab-ops/architecture-summary",
                "/api/fab-ops/recovery-board",
                "/api/fab-ops/release-board",
                "/api/fab-ops/recovery-what-if",
                "/api/fab-ops/v1/control-plan",
                "/api/fab-ops/v1/lots/lot-8812/disposition",
                "/api/fab-ops/v1/evals/replays",
                "/api/fab-ops/recovery-board/schema",
                "/api/fab-ops/architecture-pack",
            ],
            "critical_alarm_count": runtime_brief["ops_snapshot"]["critical_alarm_count"],
            "severe_lot_count": runtime_brief["ops_snapshot"]["severe_lot_count"],
            "replay_pass_count": len([case for case in build_replay_summary()["runs"] if case["status"] == "pass"]),
            "latest_audit_events": audit_feed["summary"]["events"],
            "hold_count": recovery_board["summary"]["hold_count"],
            "watch_count": recovery_board["summary"]["watch_count"],
            "ready_count": recovery_board["summary"]["ready_count"],
            "release_board_rows": release_board["summary"]["visible_lots"],
            "operator_auth": runtime_brief["operator_auth"],
            "persistence": runtime_brief["persistence"],
        },
        "focus_lot": focus_lot,
        "operator_promises": [
            "Synthetic critical-risk lots stay visible before an authorized human decision is made.",
            "Tool alarms remain linked to chambers, lots, and SOP references.",
            "Shift handoff can be reviewed and signed without external infrastructure.",
        ],
        "trust_boundary": [
            "alarm board: operator triage starts from severity and lot impact",
            "lot risk board: synthetic risk posture is visible before reroute or release",
            "handoff pack: the next shift can review open alarms, watchlist items, and signature proof",
            "replay suite: the surface stays reviewable without live fab telemetry",
        ],
        "architecture_sequence": [
            "Health -> SPC Control Plan -> Executed Lot Disposition -> Replay Assertions -> Legacy Workflow Boards -> HMAC Handoff Integrity"
        ],
        "two_minute_architecture": runtime_brief["two_minute_architecture"],
        "proof_assets": runtime_brief["proof_assets"],
        "links": {
            "runtime_scorecard": "/api/fab-ops/runtime/scorecard",
            "architecture_summary": "/api/fab-ops/architecture-summary",
            "recovery_board": "/api/fab-ops/recovery-board",
            "release_board": "/api/fab-ops/release-board",
            "recovery_what_if": "/api/fab-ops/recovery-what-if",
            "runtime_brief": "/api/fab-ops/runtime/brief",
        },
    }


def build_meta() -> dict[str, Any]:
    """Build the fab-ops domain metadata and diagnostics payload.

    Returns:
        Meta payload with contracts, route listing, capabilities, and diagnostics.
    """
    operator_auth = build_operator_auth_status(DOMAIN)
    persistence = summarize_runtime_events(DOMAIN)
    signature_security = signing_status(DOMAIN)
    operator_routes_ready = bool(operator_auth["token_configured"] or operator_auth["demo_mode"])
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "evidence_boundary": build_synthetic_evidence_boundary(),
        "generated_at": utc_now_iso(),
        "runtime_contract": "fab-ops-runtime-brief-v1",
        "architecture_pack_contract": "fab-ops-architecture-pack-v1",
        "architecture_summary_contract": "fab-ops-architecture-summary-v1",
        "report_contract": build_alarm_report_schema(),
        "handoff_contract": build_shift_handoff_schema(),
        "routes": [
            "/health",
            "/api/fab-ops/meta",
            "/api/fab-ops/runtime/brief",
            "/api/fab-ops/runtime/scorecard",
            "/api/fab-ops/architecture-summary",
            "/api/fab-ops/architecture-summary/schema",
            "/api/fab-ops/recovery-board",
            "/api/fab-ops/release-board",
            "/api/fab-ops/recovery-what-if",
            "/api/fab-ops/recovery-board/schema",
            "/api/fab-ops/architecture-pack",
            "/api/fab-ops/v1/control-plan",
            "/api/fab-ops/v1/lots/{lot_id}/disposition",
            "/api/fab-ops/v1/disposition/evaluate",
            "/api/fab-ops/v1/evals/replays",
            "/api/fab-ops/schema/alarm-report",
            "/api/fab-ops/schema/shift-handoff",
            "/api/fab-ops/fabs/summary",
            "/api/fab-ops/tools",
            "/api/fab-ops/tool-ownership",
            "/api/fab-ops/alarms",
            "/api/fab-ops/lots/at-risk",
            "/api/fab-ops/release-gate",
            "/api/fab-ops/shift-handoff",
            "/api/fab-ops/shift-handoff/signature",
            "/api/fab-ops/shift-handoff/verify",
            "/api/fab-ops/audit/feed",
            "/api/fab-ops/evals/replays",
        ],
        "capabilities": [
            "fab-control-tower",
            "tool-health-board",
            "tool-ownership-surface",
            "release-gate-surface",
            "release-board-surface",
            "recovery-board-surface",
            "synthetic-lot-risk-prioritization",
            "shift-handoff-surface",
            "audit-feed-surface",
            "architecture-pack-surface",
            "replay-suite-surface",
            "western-electric-spc-evaluator",
            "synthetic-lot-disposition-gate",
            "q-time-tat-routing-indicators",
            "executed-replay-assertions",
        ],
        "diagnostics": {
            "runtime_mode": operator_auth["runtime_mode"],
            "synthetic_fixture_mode": True,
            "shift_handoff_ready": operator_routes_ready and bool(signature_security["available"]),
            "recovery_board_ready": True,
            "audit_feed_ready": operator_routes_ready,
            "replay_suite_ready": True,
            "spc_control_plan_ready": True,
            "data_classification": "synthetic_fixture",
            "measured_yield": False,
            "operator_auth_enabled": operator_auth["enabled"],
            "operator_auth": operator_auth,
            "signature_security": signature_security,
            "runtime_store_path": persistence["path"],
            "next_action": "Review synthetic critical-alarm and severe-risk scenarios before opening the shift evidence export.",
        },
        "ops_contract": {"schema": "ops-envelope-v1", "version": 1, "required_fields": ["service", "status", "diagnostics.next_action"]},
    }


def build_runtime_scorecard() -> dict[str, Any]:
    """Build the runtime scorecard aggregating all operational metrics.

    Returns:
        Scorecard payload with alarm/lot/replay/persistence summaries.
    """
    summary = build_fab_summary()
    persistence = summarize_runtime_events(DOMAIN)
    operator_auth = build_operator_auth_status(DOMAIN)
    audit_feed = build_audit_feed()
    replay_summary = build_replay_summary()
    recovery_board = build_recovery_board()
    release_board = build_release_board()
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "evidence_boundary": build_synthetic_evidence_boundary(),
        "generated_at": utc_now_iso(),
        "readiness_contract": "fab-ops-runtime-scorecard-v1",
        "headline": "Runtime scorecard for fab handoff posture, release pressure, and persisted operator evidence.",
        "runtime": {
            "operator_auth": operator_auth,
            "persistence": persistence,
            "architecture_routes": [
                "/health",
                "/api/fab-ops/runtime/brief",
                "/api/fab-ops/runtime/scorecard",
                "/api/fab-ops/architecture-summary",
                "/api/fab-ops/recovery-board",
                "/api/fab-ops/release-board",
                "/api/fab-ops/architecture-pack",
                "/api/fab-ops/shift-handoff/signature",
                "/api/fab-ops/shift-handoff/verify",
            ],
        },
        "summary": {
            "critical_alarm_count": summary["critical_alarm_count"],
            "severe_lot_count": summary["severe_lot_count"],
            "watchlist_tools": audit_feed["summary"]["watchlist_tools"],
            "hold_lots": recovery_board["summary"]["hold_count"],
            "watch_lots": recovery_board["summary"]["watch_count"],
            "ready_lots": recovery_board["summary"]["ready_count"],
            "release_board_rows": release_board["summary"]["visible_lots"],
            "replay_score_pct": replay_summary["summary"]["score_pct"],
            "persisted_events": persistence["event_count"],
        },
        "recommendations": [
            "Triage the recovery board before reviewing any apparent release candidate.",
            "Verify tool ownership and release gate before exporting a shift handoff.",
            "Treat the HMAC envelope as payload-integrity evidence only; human approval remains a separate governed record.",
            "Keep replay score and persisted runtime events paired during reviewer walkthroughs.",
        ],
        "links": {
            "health": "/health",
            "runtime_brief": "/api/fab-ops/runtime/brief",
            "architecture_summary": "/api/fab-ops/architecture-summary",
            "recovery_board": "/api/fab-ops/recovery-board",
            "release_board": "/api/fab-ops/release-board",
            "recovery_what_if": "/api/fab-ops/recovery-what-if",
            "architecture_pack": "/api/fab-ops/architecture-pack",
            "handoff_signature": "/api/fab-ops/shift-handoff/signature",
            "handoff_verify": "/api/fab-ops/shift-handoff/verify",
        },
    }
