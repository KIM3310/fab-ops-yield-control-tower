"""
Business logic helpers for the scanner field-response domain.

Contains all ``build_*`` functions, lookup helpers, and domain logic used
by the scanner API routes.  Route handlers delegate to these functions so
they remain thin and testable.
"""

import hmac as _hmac
import logging
from datetime import UTC, datetime
from typing import Any, cast

from fastapi import HTTPException

from app.domains.scanner.domain import (
    APPLICATION_QUALIFICATIONS,
    AUDIT_EVENTS,
    CUSTOMER_READINESS,
    CUSTOMER_READINESS_CONTRACT,
    FIELD_INCIDENTS,
    FIELD_RESPONSE_BOARD_CONTRACT,
    HANDOFF_SIGNATURE_CONTRACT,
    MODULE_ESCALATIONS,
    QUALIFICATION_BOARD_CONTRACT,
    REPLAY_SUITE,
    REVIEW_PACK_CONTRACT,
    RUNTIME_BRIEF_CONTRACT,
    RUNTIME_SCORECARD_CONTRACT,
    SCANNERS,
    SEVERITY_RANK,
    SHIFT_HANDOFF_SCHEMA,
    SUBSYSTEM_ESCALATION_CONTRACT,
    WAFER_RISK_ITEMS,
)
from app.shared.operator_access import build_operator_auth_status
from app.shared.runtime_store import record_runtime_event, summarize_runtime_events
from app.shared.signatures import sign_manifest, signing_key_id

logger = logging.getLogger("scanner.helpers")

DOMAIN: str = "scanner"

# Route path helpers
FIELD_RESPONSE_ROUTE: str = "/api/scanner/field-response-board"
SUBSYSTEM_ESCALATION_ROUTE: str = "/api/scanner/subsystem-escalation"
QUALIFICATION_ROUTE: str = "/api/scanner/qualification-board"
LOT_RISK_ROUTE: str = "/api/scanner/lot-risk"
CUSTOMER_READINESS_ROUTE: str = "/api/scanner/customer-readiness"
SHIFT_HANDOFF_ROUTE: str = "/api/scanner/shift-handoff"
SHIFT_HANDOFF_SIGNATURE_ROUTE: str = "/api/scanner/shift-handoff/signature"


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def utc_now_iso() -> str:
    """Return the current UTC timestamp as an ISO-8601 string.

    Returns:
        ISO-formatted UTC datetime string.
    """
    return datetime.now(UTC).isoformat()


def record_route_hit(route: str) -> None:
    """Persist a ``route_hit`` event for the scanner domain.

    Args:
        route: The API path that was accessed.
    """
    record_runtime_event("route_hit", domain=DOMAIN, at=utc_now_iso(), route=route)


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------


def get_scanner_or_404(tool_id: str) -> dict[str, Any]:
    """Look up a scanner by tool ID or raise HTTP 404.

    Args:
        tool_id: Unique scanner tool identifier (e.g. ``"scanner-euv-02"``).

    Returns:
        The matching scanner dictionary from :data:`SCANNERS`.

    Raises:
        HTTPException: 404 when no scanner matches *tool_id*.
    """
    for scanner in SCANNERS:
        if scanner["tool_id"] == tool_id:
            return scanner
    logger.warning("[scanner] scanner not found: %s", tool_id)
    raise HTTPException(status_code=404, detail=f"Unknown scanner: {tool_id}")


def get_incident_or_404(incident_id: str) -> dict[str, Any]:
    """Look up a field incident by ID or raise HTTP 404.

    Args:
        incident_id: Unique incident identifier (e.g. ``"inc-3407"``).

    Returns:
        The matching incident dictionary from :data:`FIELD_INCIDENTS`.

    Raises:
        HTTPException: 404 when no incident matches *incident_id*.
    """
    for item in FIELD_INCIDENTS:
        if item["incident_id"] == incident_id:
            return item
    logger.warning("[scanner] incident not found: %s", incident_id)
    raise HTTPException(status_code=404, detail=f"Unknown incident: {incident_id}")


def get_lot_or_404(lot_id: str) -> dict[str, Any]:
    """Look up an application qualification record by lot ID or raise HTTP 404.

    Args:
        lot_id: Qualification lot identifier (e.g. ``"lot-n2-118"``).

    Returns:
        The matching qualification dictionary.

    Raises:
        HTTPException: 404 when no qualification record matches *lot_id*.
    """
    qualification = APPLICATION_QUALIFICATIONS.get(lot_id)
    if qualification:
        return qualification
    logger.warning("[scanner] qualification lot not found: %s", lot_id)
    raise HTTPException(status_code=404, detail=f"Unknown qualification lot: {lot_id}")


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def field_response_path() -> str:
    """Return the canonical path for the field response board.

    Returns:
        Route path string.
    """
    return FIELD_RESPONSE_ROUTE


def subsystem_escalation_path(tool_id: str) -> str:
    """Return the parameterised path for a subsystem escalation query.

    Args:
        tool_id: Scanner tool identifier.

    Returns:
        Route path string with ``tool_id`` query parameter.
    """
    return f"{SUBSYSTEM_ESCALATION_ROUTE}?tool_id={tool_id}"


def qualification_path(lot_id: str) -> str:
    """Return the parameterised path for a qualification board query.

    Args:
        lot_id: Lot identifier.

    Returns:
        Route path string with ``lot_id`` query parameter.
    """
    return f"{QUALIFICATION_ROUTE}?lot_id={lot_id}"


def customer_readiness_path(customer: str) -> str:
    """Return the parameterised path for a customer readiness query.

    Args:
        customer: Customer identifier string.

    Returns:
        Route path string with ``customer`` query parameter.
    """
    return f"{CUSTOMER_READINESS_ROUTE}?customer={customer}"


def _severity_rank(item: dict[str, Any]) -> int:
    return SEVERITY_RANK[str(item["severity"])]


def _incident_sla(item: dict[str, Any]) -> int:
    return int(item["sla_minutes"])


def _replay_checks(item: dict[str, Any]) -> int:
    return int(cast(int | str, item["checks"]))


# ---------------------------------------------------------------------------
# Focus selectors
# ---------------------------------------------------------------------------


def focus_incident() -> dict[str, Any]:
    """Return the highest-severity field incident.

    Returns:
        The incident dictionary with the lowest severity rank (most critical).
    """
    return sorted(FIELD_INCIDENTS, key=_severity_rank)[0]


def focus_lot() -> dict[str, Any]:
    """Return the qualification record linked to the focus incident.

    Returns:
        The application qualification dictionary for the focus incident's lot.
    """
    incident = focus_incident()
    return get_lot_or_404(cast(str, incident["lot_id"]))


# ---------------------------------------------------------------------------
# Domain logic builders
# ---------------------------------------------------------------------------


def build_field_response_board() -> dict[str, Any]:
    """Build the field response board sorted by severity and SLA.

    Returns:
        Field response board payload with summary, spotlight, and items.
    """
    incident_items = sorted(FIELD_INCIDENTS, key=lambda item: (_severity_rank(item), _incident_sla(item)))
    spotlight = incident_items[0]
    blocked = sum(1 for item in incident_items if item["qualification_blocker"])
    logger.info("[scanner] field response board: %d incidents, %d blockers", len(incident_items), blocked)
    return {
        "contract_version": FIELD_RESPONSE_BOARD_CONTRACT,
        "summary": {
            "incidents": len(incident_items),
            "critical": sum(1 for item in incident_items if item["severity"] == "critical"),
            "watch": sum(1 for item in incident_items if item["status"] == "watch"),
            "qualification_blockers": blocked,
        },
        "items": incident_items,
        "spotlight": {
            "incident_id": spotlight["incident_id"],
            "tool_id": spotlight["tool_id"],
            "lot_id": spotlight["lot_id"],
            "owner": spotlight["field_owner"],
            "next_owner": spotlight["next_owner"],
            "local_action": spotlight["local_action"],
        },
        "route_bundle": {
            "field_response": field_response_path(),
            "subsystem_escalation": subsystem_escalation_path(cast(str, spotlight["tool_id"])),
            "qualification_board": qualification_path(cast(str, spotlight["lot_id"])),
            "shift_handoff": SHIFT_HANDOFF_ROUTE,
        },
    }


def build_subsystem_escalation(tool_id: str) -> dict[str, Any]:
    """Build the subsystem escalation payload for a scanner.

    Args:
        tool_id: Scanner tool identifier.

    Returns:
        Escalation payload with linked incident and subsystem detail.

    Raises:
        HTTPException: 404 when no escalation lane exists for the scanner.
    """
    get_scanner_or_404(tool_id)
    payload = MODULE_ESCALATIONS.get(tool_id)
    if payload is None:
        raise HTTPException(status_code=404, detail=f"No module escalation lane for {tool_id}")
    linked_incident = get_incident_or_404(payload["linked_incident_id"])
    return {
        "contract_version": SUBSYSTEM_ESCALATION_CONTRACT,
        "tool_id": tool_id,
        "linked_incident": linked_incident,
        "payload": {
            **payload,
            "route_bundle": {
                "field_response": field_response_path(),
                "subsystem_escalation": subsystem_escalation_path(tool_id),
                "qualification_board": qualification_path(linked_incident["lot_id"]),
                "customer_readiness": customer_readiness_path(linked_incident["customer"]),
            },
        },
    }


def build_qualification_board(lot_id: str) -> dict[str, Any]:
    """Build the qualification board payload for a specific lot.

    Computes deltas between current measurements and qualification targets.

    Args:
        lot_id: Qualification lot identifier.

    Returns:
        Qualification board payload with deltas and route bundle.
    """
    payload = get_lot_or_404(lot_id)
    delta_overlay = round(payload["current_overlay_nm"] - payload["target_overlay_nm"], 2)
    delta_cd = round(payload["current_cd_delta_nm"] - payload["target_cd_delta_nm"], 2)
    delta_focus = round(payload["target_focus_margin_nm"] - payload["current_focus_margin_nm"], 2)
    delta_dose = round(payload["target_dose_margin_pct"] - payload["current_dose_margin_pct"], 2)
    return {
        "contract_version": QUALIFICATION_BOARD_CONTRACT,
        "payload": {
            **payload,
            "decision": payload["qualification_status"],
            "deltas": {
                "overlay_over_target_nm": delta_overlay,
                "cd_over_target_nm": delta_cd,
                "focus_margin_gap_nm": delta_focus,
                "dose_margin_gap_pct": delta_dose,
            },
            "route_bundle": {
                "field_response": field_response_path(),
                "subsystem_escalation": subsystem_escalation_path(payload["tool_id"]),
                "qualification_board": qualification_path(lot_id),
                "customer_readiness": customer_readiness_path(payload["customer"]),
            },
        },
    }


def build_customer_readiness(customer: str) -> dict[str, Any]:
    """Build the customer readiness payload for a customer program.

    Args:
        customer: Customer identifier (e.g. ``"alpha-mobile"``).

    Returns:
        Customer readiness payload with status, blockers, and release conditions.

    Raises:
        HTTPException: 404 when the customer program is unknown.
    """
    if customer not in CUSTOMER_READINESS:
        raise HTTPException(status_code=404, detail=f"Unknown customer program: {customer}")
    readiness = CUSTOMER_READINESS[customer]
    return {
        "contract_version": CUSTOMER_READINESS_CONTRACT,
        "payload": {
            **readiness,
            "route_bundle": {
                "field_response": field_response_path(),
                "focus_subsystem_escalation": subsystem_escalation_path("scanner-euv-02"),
                "focus_qualification_board": qualification_path("lot-n2-118"),
                "shift_handoff": SHIFT_HANDOFF_SIGNATURE_ROUTE,
            },
        },
    }


def build_shift_handoff_payload() -> dict[str, Any]:
    """Build the scanner shift handoff payload.

    Returns:
        Handoff payload with focus incident, acknowledgements, and review path.
    """
    focus = focus_incident()
    lot = focus_lot()
    return {
        "schema": SHIFT_HANDOFF_SCHEMA,
        "handoff_id": "handoff-hwaseong-night",
        "site": "Hwaseong Customer Park",
        "headline": "Keep lot-n2-118 blocked until the subsystem wafer-stage lane closes and the qualification rerun clears overlay.",
        "focus_incident_id": focus["incident_id"],
        "focus_lot_id": lot["lot_id"],
        "must_acknowledge": [
            "scanner-euv-02 is still the top blocker for the customer milestone",
            "the next shift must not clear qualification without the subsystem replay packet",
            "the qualification rerun only counts if overlay returns under 2.0 nm on the same lot family",
        ],
        "next_shift_checks": [
            "confirm the stage trace packet was uploaded",
            "rerun the qualification wafer after subsystem sign-off",
            "update the customer readiness lane before reopening the milestone",
        ],
        "review_path": [
            "/api/scanner/runtime/brief",
            field_response_path(),
            subsystem_escalation_path("scanner-euv-02"),
            qualification_path("lot-n2-118"),
            customer_readiness_path("alpha-mobile"),
            SHIFT_HANDOFF_SIGNATURE_ROUTE,
        ],
    }


def build_handoff_signature(payload: dict[str, Any]) -> dict[str, Any]:
    """Sign the handoff payload and return the signature envelope.

    Args:
        payload: The shift handoff payload dictionary to sign.

    Returns:
        Signature envelope with algorithm, key ID, digest, and HMAC.
    """
    sigs = sign_manifest(payload, DOMAIN)
    logger.info("[scanner] handoff signature generated for %s", payload.get("handoff_id", "unknown"))
    return {
        "signature_contract": HANDOFF_SIGNATURE_CONTRACT,
        "signature_id": payload["handoff_id"],
        "algorithm": "hmac-sha256",
        "key_id": signing_key_id(DOMAIN),
        "sha256": sigs["sha256"],
        "signature": sigs["signature"],
        "signed_by": "shift-lead-kim",
    }


def build_handoff_verify(payload: dict[str, Any], expected: dict[str, Any]) -> dict[str, Any]:
    """Verify a handoff signature against the expected envelope.

    Args:
        payload: The shift handoff payload to re-sign and compare.
        expected: The previously generated signature envelope.

    Returns:
        Verification result with ``overall_valid`` and individual checks.
    """
    current_signature = build_handoff_signature(payload)
    overall_valid = _hmac.compare_digest(current_signature["signature"], expected["signature"])
    if not overall_valid:
        logger.warning("[scanner] handoff signature verification failed")
    return {
        "overall_valid": overall_valid,
        "checks": {
            "signature_match": _hmac.compare_digest(current_signature["signature"], expected["signature"]),
            "digest_match": current_signature["sha256"] == expected["sha256"],
            "key_id_present": bool(current_signature["key_id"]),
        },
    }


def build_runtime_brief() -> dict[str, Any]:
    """Build the comprehensive runtime brief for the scanner domain.

    This is the primary entry-point payload showing incidents, escalations,
    qualification status, and customer readiness in one surface.

    Returns:
        Runtime brief payload.
    """
    focus = focus_incident()
    lot = focus_lot()
    readiness = build_customer_readiness("alpha-mobile")["payload"]
    return {
        "readiness_contract": RUNTIME_BRIEF_CONTRACT,
        "headline": "One scanner issue stays visible from field response through subsystem escalation to qualification review.",
        "evidence_counts": {
            "incidents": len(FIELD_INCIDENTS),
            "module_escalations": len(MODULE_ESCALATIONS),
            "qualification_lots": len(APPLICATION_QUALIFICATIONS),
            "replay_scenarios": len(REPLAY_SUITE),
        },
        "ops_snapshot": {
            "critical_incident_count": sum(1 for item in FIELD_INCIDENTS if item["severity"] == "critical"),
            "blocked_qualification_count": sum(
                1 for item in APPLICATION_QUALIFICATIONS.values() if item["qualification_status"] == "hold-qualification"
            ),
            "ready_customer_programs": sum(1 for item in CUSTOMER_READINESS.values() if item["status"] == "green"),
        },
        "focus_incident": {
            "incident_id": focus["incident_id"],
            "tool_id": focus["tool_id"],
            "lot_id": lot["lot_id"],
            "customer": lot["customer"],
            "qualification_status": lot["qualification_status"],
            "review_path": build_shift_handoff_payload()["review_path"],
        },
        "review_lanes": [
            {"lane": "Field Response", "href": field_response_path(), "why": "first-line containment, packet capture, and local ownership"},
            {
                "lane": "Subsystem Escalation",
                "href": subsystem_escalation_path("scanner-euv-02"),
                "why": "subsystem diagnosis, evidence handoff, and restore criteria",
            },
            {
                "lane": "Qualification Review",
                "href": qualification_path("lot-n2-118"),
                "why": "lot impact, process window, and milestone judgment",
            },
        ],
        "two_minute_review": [
            "Open the runtime brief and focus incident first.",
            "Read the field-response board before talking about scanner internals.",
            "Use the subsystem lane to show restore criteria instead of vague troubleshooting.",
            "Use the qualification board to tie the scanner issue to lot impact and customer milestones.",
            "Open customer readiness to show milestone judgment.",
            "Finish on the signed shift handoff so the story ends on operational continuity.",
        ],
        "proof_assets": [
            {"label": "Health", "href": "/health"},
            {"label": "Field Response Board", "href": field_response_path()},
            {"label": "Subsystem Escalation", "href": subsystem_escalation_path("scanner-euv-02")},
            {"label": "Qualification Board", "href": qualification_path("lot-n2-118")},
            {"label": "Customer Readiness", "href": customer_readiness_path("alpha-mobile")},
            {"label": "Shift Handoff Signature", "href": SHIFT_HANDOFF_SIGNATURE_ROUTE},
        ],
        "links": {
            "review_pack": "/api/scanner/review-pack",
            "runtime_scorecard": "/api/scanner/runtime/scorecard",
            "field_response_board": field_response_path(),
            "subsystem_escalation": subsystem_escalation_path("scanner-euv-02"),
            "qualification_board": qualification_path("lot-n2-118"),
            "customer_readiness": customer_readiness_path("alpha-mobile"),
            "shift_handoff": SHIFT_HANDOFF_SIGNATURE_ROUTE,
        },
        "customer_headline": readiness["headline"],
    }


def build_runtime_scorecard() -> dict[str, Any]:
    """Build the runtime scorecard for the scanner domain.

    Returns:
        Scorecard payload with incident/lot/customer counts and runtime info.
    """
    runtime = summarize_runtime_events(DOMAIN)
    return {
        "readiness_contract": RUNTIME_SCORECARD_CONTRACT,
        "summary": {
            "scanners": len(SCANNERS),
            "open_incidents": sum(1 for item in FIELD_INCIDENTS if item["status"] == "open"),
            "watch_incidents": sum(1 for item in FIELD_INCIDENTS if item["status"] == "watch"),
            "blocked_lots": sum(1 for item in WAFER_RISK_ITEMS if item["risk_bucket"] == "blocked"),
            "watch_lots": sum(1 for item in WAFER_RISK_ITEMS if item["risk_bucket"] == "watch"),
            "ready_lots": sum(1 for item in WAFER_RISK_ITEMS if item["risk_bucket"] == "ready"),
            "customer_programs": len(CUSTOMER_READINESS),
        },
        "runtime": {
            "persistence": runtime,
            "operator_auth": build_operator_auth_status(DOMAIN),
        },
        "links": {
            "field_response_board": field_response_path(),
            "subsystem_escalation": subsystem_escalation_path("scanner-euv-02"),
            "qualification_board": qualification_path("lot-n2-118"),
            "shift_handoff": SHIFT_HANDOFF_SIGNATURE_ROUTE,
        },
    }


def build_review_pack() -> dict[str, Any]:
    """Build the shift-ready review pack for the scanner domain.

    Returns:
        Review pack payload with focus story and operator promises.
    """
    focus = focus_incident()
    lot = focus_lot()
    return {
        "readiness_contract": REVIEW_PACK_CONTRACT,
        "headline": "Field response proof: local triage, subsystem escalation, and qualification review stay tied to the same incident.",
        "operator_promises": [
            "The repo never treats scanner support like a generic chatbot problem.",
            "Local field ownership, subsystem escalation, and wafer/customer impact stay on one route.",
            "The walkthrough ends on a signed handoff instead of a screenshot.",
        ],
        "trust_boundary": [
            "Synthetic scanner and wafer data are used so the workflow is public and reviewable.",
            "The strongest signal is the operational contract between field response, subsystem escalation, and qualification review, not proprietary scanner internals.",
        ],
        "focus_story": {
            "incident_id": focus["incident_id"],
            "tool_id": focus["tool_id"],
            "lot_id": lot["lot_id"],
            "customer": lot["customer"],
            "review_path": build_shift_handoff_payload()["review_path"],
        },
        "proof_bundle": {
            "review_routes": [
                "/health",
                "/api/scanner/runtime/brief",
                field_response_path(),
                subsystem_escalation_path("scanner-euv-02"),
                qualification_path("lot-n2-118"),
                customer_readiness_path("alpha-mobile"),
                SHIFT_HANDOFF_SIGNATURE_ROUTE,
                "/api/scanner/evals/replays",
                "/api/scanner/audit/feed",
            ],
            "incident_count": len(FIELD_INCIDENTS),
            "blocked_qualification_count": sum(
                1 for item in APPLICATION_QUALIFICATIONS.values() if item["qualification_status"] == "hold-qualification"
            ),
            "customer_program_count": len(CUSTOMER_READINESS),
            "latest_audit_events": len(AUDIT_EVENTS),
        },
        "two_minute_review": build_runtime_brief()["two_minute_review"],
        "proof_assets": build_runtime_brief()["proof_assets"],
    }


def build_replay_summary() -> dict[str, Any]:
    """Build the replay suite summary for the scanner domain.

    Returns:
        Replay summary with scenario count and pass percentage.
    """
    score = round(
        100
        * sum(_replay_checks(item) for item in REPLAY_SUITE if item["status"] == "pass")
        / max(1, sum(_replay_checks(item) for item in REPLAY_SUITE)),
        2,
    )
    return {
        "summary": {"scenarios": len(REPLAY_SUITE), "score_pct": score},
        "runs": REPLAY_SUITE,
    }
