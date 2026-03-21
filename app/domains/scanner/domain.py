"""
Hardcoded domain data for scanner-field-response.
Contains all sites, scanners, field incidents, module escalations,
application qualifications, customer readiness, and constants.
"""
from __future__ import annotations

from typing import Any

SERVICE_NAME = "scanner-field-response"
OPS_CONTRACT = "ops-envelope-v1"
FIELD_INCIDENT_SCHEMA = "scanner-field-incident-v1"
APPLICATION_QUALIFICATION_SCHEMA = "scanner-qualification-record-v1"
SHIFT_HANDOFF_SCHEMA = "scanner-shift-handoff-v1"
HANDOFF_SIGNATURE_CONTRACT = "scanner-handoff-signature-v1"
RUNTIME_BRIEF_CONTRACT = "scanner-runtime-brief-v1"
RUNTIME_SCORECARD_CONTRACT = "scanner-runtime-scorecard-v1"
REVIEW_PACK_CONTRACT = "scanner-review-pack-v1"
FIELD_RESPONSE_BOARD_CONTRACT = "scanner-field-response-board-v1"
SUBSYSTEM_ESCALATION_CONTRACT = "scanner-subsystem-escalation-v1"
QUALIFICATION_BOARD_CONTRACT = "scanner-qualification-board-v1"
CUSTOMER_READINESS_CONTRACT = "scanner-customer-readiness-v1"
LOT_RISK_CONTRACT = "scanner-lot-risk-board-v1"
SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}

SITES = [
    {
        "site_id": "hwaseong-customer-park",
        "name": "Hwaseong Customer Park",
        "shift": "night",
        "customer": "alpha-mobile",
        "focus": "logic ramp qualification",
    }
]

SCANNERS = [
    {
        "tool_id": "scanner-euv-02",
        "site_id": "hwaseong-customer-park",
        "family": "EUV",
        "status": "degraded",
        "subsystem_focus": "wafer-stage",
        "availability_pct": 92.4,
        "throughput_wph": 144,
        "current_incident_id": "inc-3407",
    },
    {
        "tool_id": "scanner-duv-11",
        "site_id": "hwaseong-customer-park",
        "family": "DUV immersion",
        "status": "watch",
        "subsystem_focus": "dose-control",
        "availability_pct": 96.1,
        "throughput_wph": 221,
        "current_incident_id": "inc-3410",
    },
    {
        "tool_id": "metrology-04",
        "site_id": "hwaseong-customer-park",
        "family": "Overlay metrology",
        "status": "healthy",
        "subsystem_focus": "overlay-verification",
        "availability_pct": 99.2,
        "throughput_wph": 310,
        "current_incident_id": "",
    },
]

FIELD_INCIDENTS = [
    {
        "incident_id": "inc-3407",
        "severity": "critical",
        "tool_id": "scanner-euv-02",
        "lot_id": "lot-n2-118",
        "customer": "alpha-mobile",
        "product": "N2 mobile logic",
        "subsystem": "wafer-stage",
        "status": "open",
        "started_at": "2026-03-16T02:18:00Z",
        "symptom": "overlay drift breached customer qualification band during edge-placement verification",
        "local_action": "freeze the current wafer set and capture stage vibration plus reticle alignment traces",
        "field_owner": "field-hwaseong-b",
        "next_owner": "subsystem-stage-dynamics",
        "sla_minutes": 25,
        "qualification_blocker": True,
    },
    {
        "incident_id": "inc-3410",
        "severity": "high",
        "tool_id": "scanner-duv-11",
        "lot_id": "lot-auto-441",
        "customer": "auto-sensor",
        "product": "Automotive sensor shrink",
        "subsystem": "dose-control",
        "status": "watch",
        "started_at": "2026-03-16T03:11:00Z",
        "symptom": "dose drift is still inside hard stop limits but trending outside the qualification comfort band",
        "local_action": "tighten the local monitor window and prep the dose-control packet for remote review",
        "field_owner": "field-hwaseong-a",
        "next_owner": "subsystem-dose-window",
        "sla_minutes": 55,
        "qualification_blocker": False,
    },
    {
        "incident_id": "inc-3413",
        "severity": "medium",
        "tool_id": "metrology-04",
        "lot_id": "lot-n2-125",
        "customer": "alpha-mobile",
        "product": "N2 mobile logic",
        "subsystem": "overlay-verification",
        "status": "open",
        "started_at": "2026-03-16T04:02:00Z",
        "symptom": "metrology queue delay is threatening the next qualification checkpoint",
        "local_action": "protect the qualification slot and keep the route clear for the focus lot",
        "field_owner": "field-hwaseong-b",
        "next_owner": "qualification-lane",
        "sla_minutes": 70,
        "qualification_blocker": False,
    },
]

MODULE_ESCALATIONS: dict[str, dict[str, Any]] = {
    "scanner-euv-02": {
        "tool_id": "scanner-euv-02",
        "linked_incident_id": "inc-3407",
        "owner": "subsystem-stage-dynamics",
        "subsystem": "wafer-stage metrology",
        "escalation_status": "open",
        "remote_partner": "D&E stage diagnostics",
        "failure_hypotheses": [
            "stage vibration compensation is stale after the last maintenance window",
            "reticle alignment drift is amplifying overlay miss on the qualification wafer",
            "local calibration closed green but the replay bundle still shows edge placement drift",
        ],
        "required_evidence": [
            "stage vibration trace bundle",
            "reticle thermal drift log",
            "overlay delta by field and slit position",
        ],
        "restore_criteria": [
            "overlay delta returns under 2.0 nm on the replay wafer",
            "stage trace stays inside the subsystem control band for two consecutive runs",
            "qualification packet can clear without manual caveat",
        ],
    },
    "scanner-duv-11": {
        "tool_id": "scanner-duv-11",
        "linked_incident_id": "inc-3410",
        "owner": "subsystem-dose-window",
        "subsystem": "dose-control loop",
        "escalation_status": "watch",
        "remote_partner": "imaging performance diagnostics",
        "failure_hypotheses": [
            "dose feedback loop is lagging after recipe changeover",
            "lamp stability window is compressing for the current lot family",
        ],
        "required_evidence": [
            "dose loop stability plot",
            "recipe delta from the last golden run",
            "focus-dose window replay",
        ],
        "restore_criteria": [
            "dose delta stays under 1.5 percent for two replay runs",
            "qualification process window reopens to the target band",
        ],
    },
}

APPLICATION_QUALIFICATIONS: dict[str, dict[str, Any]] = {
    "lot-n2-118": {
        "lot_id": "lot-n2-118",
        "tool_id": "scanner-euv-02",
        "customer": "alpha-mobile",
        "product": "N2 mobile logic",
        "qualification_owner": "qualification-edge-placement",
        "qualification_status": "hold-qualification",
        "customer_milestone": "pilot qualification week 6",
        "current_overlay_nm": 3.4,
        "target_overlay_nm": 2.0,
        "current_cd_delta_nm": 1.8,
        "target_cd_delta_nm": 1.2,
        "current_focus_margin_nm": 58,
        "target_focus_margin_nm": 70,
        "current_dose_margin_pct": 2.1,
        "target_dose_margin_pct": 2.8,
        "throughput_wph": 144,
        "target_throughput_wph": 150,
        "recommended_actions": [
            "close the subsystem wafer-stage escalation before the next qualification wafer",
            "rerun edge-placement and overlay verification on the same lot family",
            "hold the customer milestone as amber until overlay is back in band",
        ],
    },
    "lot-auto-441": {
        "lot_id": "lot-auto-441",
        "tool_id": "scanner-duv-11",
        "customer": "auto-sensor",
        "product": "Automotive sensor shrink",
        "qualification_owner": "qualification-process-window",
        "qualification_status": "watch-window",
        "customer_milestone": "customer release rehearsal",
        "current_overlay_nm": 2.3,
        "target_overlay_nm": 2.0,
        "current_cd_delta_nm": 1.3,
        "target_cd_delta_nm": 1.2,
        "current_focus_margin_nm": 71,
        "target_focus_margin_nm": 72,
        "current_dose_margin_pct": 2.5,
        "target_dose_margin_pct": 2.8,
        "throughput_wph": 221,
        "target_throughput_wph": 220,
        "recommended_actions": [
            "keep the lot in watch until the next dose replay closes clean",
            "prepare the customer-facing process window note with the current caveat",
        ],
    },
}

WAFER_RISK_ITEMS = [
    {
        "lot_id": "lot-n2-118",
        "tool_id": "scanner-euv-02",
        "customer": "alpha-mobile",
        "product": "N2 mobile logic",
        "risk_bucket": "blocked",
        "qualification_status": "hold-qualification",
        "risk_score": 0.96,
        "next_action": "close wafer-stage escalation and rerun qualification wafer",
    },
    {
        "lot_id": "lot-auto-441",
        "tool_id": "scanner-duv-11",
        "customer": "auto-sensor",
        "product": "Automotive sensor shrink",
        "risk_bucket": "watch",
        "qualification_status": "watch-window",
        "risk_score": 0.68,
        "next_action": "finish the next dose replay before clearing the customer note",
    },
    {
        "lot_id": "lot-n2-125",
        "tool_id": "metrology-04",
        "customer": "alpha-mobile",
        "product": "N2 mobile logic",
        "risk_bucket": "ready",
        "qualification_status": "ready-for-qualification",
        "risk_score": 0.31,
        "next_action": "protect metrology turnaround and keep the slot open",
    },
]

CUSTOMER_READINESS = {
    "alpha-mobile": {
        "customer": "alpha-mobile",
        "program": "N2 mobile logic ramp",
        "status": "amber",
        "milestone": "pilot qualification week 6",
        "headline": "One blocked EUV qualification lot is the only thing standing between the customer and the next ramp checkpoint.",
        "blocked_by": [
            "overlay is still above the target band on lot-n2-118",
            "the subsystem wafer-stage lane is not closed yet",
        ],
        "release_conditions": [
            "subsystem replay closes with overlay under 2.0 nm",
            "qualification rerun clears process window without manual caveat",
            "shift handoff stays signed for the next qualification window",
        ],
    },
    "auto-sensor": {
        "customer": "auto-sensor",
        "program": "Automotive sensor shrink",
        "status": "watch",
        "milestone": "customer release rehearsal",
        "headline": "The program is not blocked, but dose stability still needs one clean replay before the release note loses its caveat.",
        "blocked_by": [
            "dose drift trend is still outside the comfort band",
        ],
        "release_conditions": [
            "dose replay closes under 1.5 percent drift",
            "qualification process window returns to the target margin",
        ],
    },
}

REPLAY_SUITE = [
    {"scenario": "wafer-stage-overlay-regression", "status": "pass", "checks": 9},
    {"scenario": "dose-window-watch-lane", "status": "pass", "checks": 8},
    {"scenario": "customer-milestone-handoff", "status": "pass", "checks": 8},
    {"scenario": "qualification-packet-continuity", "status": "pass", "checks": 8},
]

AUDIT_EVENTS = [
    {
        "at": "2026-03-16T05:12:00Z",
        "event": "qualification-hold-issued",
        "actor": "qualification-edge-placement",
        "tool_id": "scanner-euv-02",
        "lot_id": "lot-n2-118",
    },
    {
        "at": "2026-03-16T05:03:00Z",
        "event": "subsystem-stage-escalation-opened",
        "actor": "subsystem-stage-dynamics",
        "tool_id": "scanner-euv-02",
        "lot_id": "lot-n2-118",
    },
    {
        "at": "2026-03-16T04:48:00Z",
        "event": "field-packet-captured",
        "actor": "field-hwaseong-b",
        "tool_id": "scanner-euv-02",
        "lot_id": "lot-n2-118",
    },
    {
        "at": "2026-03-16T04:26:00Z",
        "event": "dose-watch-window-tightened",
        "actor": "field-hwaseong-a",
        "tool_id": "scanner-duv-11",
        "lot_id": "lot-auto-441",
    },
]

ALLOWED_SEVERITIES = {item["severity"] for item in FIELD_INCIDENTS}
ALLOWED_CUSTOMERS = set(CUSTOMER_READINESS)
