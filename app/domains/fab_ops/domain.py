"""
Hardcoded domain data for fab-ops-yield-control-tower.
Contains all fabs, tools, alarms, lots, replay suites, tool ownership, audit events, and constants.
"""
from __future__ import annotations

from typing import Any

SERVICE_NAME = "fab-ops-yield-control-tower"
ALARM_REPORT_SCHEMA = "fab-ops-alarm-report-v1"
SHIFT_HANDOFF_SCHEMA = "fab-ops-shift-handoff-v1"
HANDOFF_SIGNATURE_CONTRACT = "fab-ops-handoff-signature-v1"
ALARM_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}
ALLOWED_RECOVERY_MODES: set[str] = {"all", "hold", "watch", "ready"}

FABS = [
    {
        "fab_id": "fab-west-1",
        "name": "Fab West 1",
        "site": "Hsinchu",
        "focus": "logic-node pilot line",
        "shift": "night",
        "owner": "ops-west-night",
    }
]

TOOLS = [
    {
        "tool_id": "etch-14",
        "fab_id": "fab-west-1",
        "line": "etch-bay-a",
        "chamber": "A2",
        "status": "alarm",
        "last_pm_hours": 147,
        "mtbf_risk": "high",
        "current_alarm_id": "alm-2041",
    },
    {
        "tool_id": "depo-03",
        "fab_id": "fab-west-1",
        "line": "deposition-bay-c",
        "chamber": "C1",
        "status": "warning",
        "last_pm_hours": 112,
        "mtbf_risk": "medium",
        "current_alarm_id": "alm-2043",
    },
    {
        "tool_id": "cmp-07",
        "fab_id": "fab-west-1",
        "line": "cmp-bay-b",
        "chamber": "B3",
        "status": "healthy",
        "last_pm_hours": 64,
        "mtbf_risk": "low",
        "current_alarm_id": "",
    },
]

ALARMS = [
    {
        "alarm_id": "alm-2041",
        "fab_id": "fab-west-1",
        "tool_id": "etch-14",
        "lot_id": "lot-8812",
        "severity": "critical",
        "category": "plasma-instability",
        "status": "triage",
        "started_at": "2026-03-08T07:12:00Z",
        "symptom": "etch uniformity drift exceeded shift threshold",
        "sop_ref": "ETCH-SOP-21",
        "recommended_actions": [
            "pause affected lot progression",
            "verify chamber pressure calibration",
            "route chamber A2 to maintenance review",
        ],
    },
    {
        "alarm_id": "alm-2043",
        "fab_id": "fab-west-1",
        "tool_id": "depo-03",
        "lot_id": "lot-8821",
        "severity": "high",
        "category": "temperature-drift",
        "status": "monitoring",
        "started_at": "2026-03-08T07:48:00Z",
        "symptom": "temperature delta trending above control band",
        "sop_ref": "DEPO-SOP-07",
        "recommended_actions": [
            "tighten drift watch window",
            "queue post-shift inspection",
            "hold next high-priority lot until trend stabilizes",
        ],
    },
]

LOTS_AT_RISK = [
    {
        "lot_id": "lot-8812",
        "tool_id": "etch-14",
        "product_family": "N3 mobile logic",
        "wafer_count": 25,
        "yield_risk_score": 0.94,
        "risk_bucket": "severe",
        "next_action": "maintenance approval + reroute review",
    },
    {
        "lot_id": "lot-8821",
        "tool_id": "depo-03",
        "product_family": "automotive sensor",
        "wafer_count": 18,
        "yield_risk_score": 0.73,
        "risk_bucket": "elevated",
        "next_action": "tight monitoring and post-shift inspection",
    },
    {
        "lot_id": "lot-8836",
        "tool_id": "cmp-07",
        "product_family": "edge compute package",
        "wafer_count": 20,
        "yield_risk_score": 0.41,
        "risk_bucket": "watch",
        "next_action": "normal flow with sampling",
    },
]

REPLAY_SUITE = [
    {"scenario": "plasma-instability", "status": "pass", "checks": 8},
    {"scenario": "temperature-drift", "status": "pass", "checks": 8},
    {"scenario": "vacuum-loss", "status": "pass", "checks": 8},
    {"scenario": "shift-handoff-gap", "status": "pass", "checks": 8},
]

TOOL_OWNERSHIP: dict[str, dict[str, Any]] = {
    "etch-14": {
        "tool_id": "etch-14",
        "primary_operator": "ops-west-night",
        "maintenance_owner": "maint-etch-cell-a",
        "escalation_lane": "plasma-stability-review",
        "due_by": "2026-03-08T09:10:00Z",
        "ack_required": True,
    },
    "depo-03": {
        "tool_id": "depo-03",
        "primary_operator": "ops-west-night",
        "maintenance_owner": "maint-depo-cell-c",
        "escalation_lane": "temperature-drift-watch",
        "due_by": "2026-03-08T10:00:00Z",
        "ack_required": True,
    },
    "cmp-07": {
        "tool_id": "cmp-07",
        "primary_operator": "ops-west-night",
        "maintenance_owner": "maint-cmp-cell-b",
        "escalation_lane": "normal-observation",
        "due_by": "2026-03-08T12:00:00Z",
        "ack_required": False,
    },
}

AUDIT_EVENTS = [
    {
        "at": "2026-03-08T08:07:00Z",
        "event": "handoff-preview-generated",
        "actor": "shift-exporter",
        "tool_id": "etch-14",
        "lot_id": "lot-8812",
    },
    {
        "at": "2026-03-08T07:56:00Z",
        "event": "maintenance-owner-assigned",
        "actor": "ops-west-night",
        "tool_id": "etch-14",
        "lot_id": "lot-8812",
    },
    {
        "at": "2026-03-08T07:51:00Z",
        "event": "drift-watch-window-tightened",
        "actor": "depo-monitor",
        "tool_id": "depo-03",
        "lot_id": "lot-8821",
    },
]

ALLOWED_SEVERITIES: set[str] = {str(item["severity"]) for item in ALARMS}
ALLOWED_RISK_BUCKETS: set[str] = {str(item["risk_bucket"]) for item in LOTS_AT_RISK}
