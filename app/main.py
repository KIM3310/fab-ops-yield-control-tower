from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

APP_DIR = Path(__file__).resolve().parent
REPO_ROOT = APP_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.operator_access import build_operator_auth_status, require_operator_token
from app.runtime_store import record_runtime_event, summarize_runtime_events


BASE_DIR = APP_DIR
STATIC_DIR = BASE_DIR / "static"

SERVICE_NAME = "fab-ops-yield-control-tower"
ALARM_REPORT_SCHEMA = "fab-ops-alarm-report-v1"
SHIFT_HANDOFF_SCHEMA = "fab-ops-shift-handoff-v1"
HANDOFF_SIGNATURE_CONTRACT = "fab-ops-handoff-signature-v1"
ALARM_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}
ALLOWED_RECOVERY_MODES = {"all", "hold", "watch", "ready"}

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

TOOL_OWNERSHIP: Dict[str, Dict[str, Any]] = {
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
ALLOWED_SEVERITIES = {item["severity"] for item in ALARMS}
ALLOWED_RISK_BUCKETS = {item["risk_bucket"] for item in LOTS_AT_RISK}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def handoff_signing_key() -> str:
    return str(os.getenv("FAB_OPS_HANDOFF_SIGNING_KEY", "fab-ops-demo-signing-key")).strip() or "fab-ops-demo-signing-key"


def handoff_signing_key_id() -> str:
    return str(os.getenv("FAB_OPS_HANDOFF_SIGNING_KEY_ID", "fab-ops-demo-v1")).strip() or "fab-ops-demo-v1"


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def record_route_hit(route: str) -> None:
    record_runtime_event("route_hit", at=utc_now_iso(), route=route)


def get_tool_or_404(tool_id: str) -> Dict[str, Any]:
    for item in TOOLS:
        if item["tool_id"] == tool_id:
            return item
    raise HTTPException(status_code=404, detail=f"Unknown tool: {tool_id}")


def get_lot_or_404(lot_id: str) -> Dict[str, Any]:
    for item in LOTS_AT_RISK:
        if item["lot_id"] == lot_id:
            return item
    raise HTTPException(status_code=404, detail=f"Unknown lot: {lot_id}")


def build_alarm_report_schema() -> Dict[str, Any]:
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


def build_shift_handoff_schema() -> Dict[str, Any]:
    return {
        "schema": SHIFT_HANDOFF_SCHEMA,
        "required_sections": [
            "fab_id",
            "shift",
            "open_critical_alarms",
            "lots_at_risk",
            "tool_watchlist",
            "must_acknowledge",
        ],
        "operator_rules": [
            "Critical alarms must be acknowledged in the handoff export.",
            "Lots at risk stay visible until reroute, release, or scrap decision is recorded.",
            "The handoff pack is reviewable without live integrations.",
        ],
    }


def build_focus_lot() -> Dict[str, Any]:
    spotlight_lot = get_lot_or_404('lot-8812')
    spotlight_alarm = next(alarm for alarm in ALARMS if alarm['lot_id'] == spotlight_lot['lot_id'])
    spotlight_tool = get_tool_or_404(spotlight_lot['tool_id'])
    release_gate = build_release_gate(spotlight_lot['lot_id'])
    ownership = build_tool_ownership(spotlight_tool['tool_id'])
    handoff = build_shift_handoff()
    return {
        'lot_id': spotlight_lot['lot_id'],
        'alarm_id': spotlight_alarm['alarm_id'],
        'tool_id': spotlight_tool['tool_id'],
        'severity': spotlight_alarm['severity'],
        'risk_bucket': spotlight_lot['risk_bucket'],
        'release_decision': release_gate['decision'],
        'next_action': spotlight_lot['next_action'],
        'maintenance_owner': ownership['maintenance_owner'],
        'handoff_headline': handoff['headline'],
        'review_path': [
            '/api/runtime/brief',
            '/api/recovery-board?mode=hold',
            f"/api/release-gate?lot_id={spotlight_lot['lot_id']}",
            '/api/shift-handoff/signature',
        ],
    }


def build_fab_summary() -> Dict[str, Any]:
    critical_alarms = [alarm for alarm in ALARMS if alarm["severity"] == "critical"]
    severe_lots = [lot for lot in LOTS_AT_RISK if lot["yield_risk_score"] >= 0.8]
    return {
        "fab_id": "fab-west-1",
        "headline": "Night shift is stable but etch-bay-a is blocking one severe lot.",
        "tool_count": len(TOOLS),
        "alarm_count": len(ALARMS),
        "critical_alarm_count": len(critical_alarms),
        "severe_lot_count": len(severe_lots),
        "healthy_tools": len([tool for tool in TOOLS if tool["status"] == "healthy"]),
        "degraded_tools": len([tool for tool in TOOLS if tool["status"] != "healthy"]),
    }


def build_shift_handoff() -> Dict[str, Any]:
    sorted_lots = sorted(LOTS_AT_RISK, key=lambda item: item["yield_risk_score"], reverse=True)
    watchlist = [tool for tool in TOOLS if tool["status"] != "healthy"]
    return {
        "fab_id": "fab-west-1",
        "shift": "night",
        "generated_at": utc_now_iso(),
        "schema": SHIFT_HANDOFF_SCHEMA,
        "headline": "One severe lot needs maintenance approval before morning release.",
        "open_critical_alarms": [alarm["alarm_id"] for alarm in ALARMS if alarm["severity"] == "critical"],
        "lots_at_risk": sorted_lots,
        "tool_watchlist": watchlist,
        "must_acknowledge": [
            "etch-14 maintenance approval",
            "lot-8812 reroute decision",
            "depo-03 drift inspection assignment",
        ],
    }


def build_tool_ownership(tool_id: str) -> Dict[str, Any]:
    tool = get_tool_or_404(tool_id)
    ownership = TOOL_OWNERSHIP[tool_id]
    return {
        **ownership,
        "line": tool["line"],
        "status": tool["status"],
        "current_alarm_id": tool["current_alarm_id"],
        "mtbf_risk": tool["mtbf_risk"],
    }


def build_release_gate(lot_id: str) -> Dict[str, Any]:
    lot = get_lot_or_404(lot_id)
    tool = get_tool_or_404(lot["tool_id"])
    assignment = build_tool_ownership(tool["tool_id"])

    if lot["yield_risk_score"] >= 0.85 and tool["status"] == "alarm":
        decision = "hold-release"
    elif lot["yield_risk_score"] >= 0.65:
        decision = "reroute-review"
    else:
        decision = "release-with-sampling"

    failed_checks: List[str] = []
    if tool["status"] == "alarm":
        failed_checks.append("critical tool alarm still open")
    if lot["yield_risk_score"] >= 0.85:
        failed_checks.append("yield risk score exceeds severe threshold")
    if assignment["ack_required"]:
        failed_checks.append("maintenance owner acknowledgement still required")

    if decision == "release-with-sampling":
        failed_checks = []

    return {
        "lot_id": lot_id,
        "tool_id": tool["tool_id"],
        "decision": decision,
        "yield_risk_score": lot["yield_risk_score"],
        "tool_status": tool["status"],
        "next_action": lot["next_action"],
        "primary_operator": assignment["primary_operator"],
        "maintenance_owner": assignment["maintenance_owner"],
        "failed_checks": failed_checks,
    }


def build_recovery_what_if(
    lot_id: str,
    *,
    yield_gain: float = 0.2,
    maintenance_complete: bool = False,
) -> Dict[str, Any]:
    baseline = build_release_gate(lot_id)
    lot = get_lot_or_404(lot_id)
    tool = get_tool_or_404(lot["tool_id"])
    assignment = build_tool_ownership(tool["tool_id"])

    simulated_yield_risk = round(max(0.0, float(lot["yield_risk_score"]) - max(0.0, min(0.5, yield_gain))), 2)
    simulated_tool_status = "healthy" if maintenance_complete else tool["status"]
    simulated_ack_required = False if maintenance_complete else assignment["ack_required"]

    if simulated_yield_risk >= 0.85 and simulated_tool_status == "alarm":
        simulated_decision = "hold-release"
    elif simulated_yield_risk >= 0.65:
        simulated_decision = "reroute-review"
    else:
        simulated_decision = "release-with-sampling"

    simulated_failed_checks: List[str] = []
    if simulated_tool_status == "alarm":
        simulated_failed_checks.append("critical tool alarm still open")
    if simulated_yield_risk >= 0.85:
        simulated_failed_checks.append("yield risk score exceeds severe threshold")
    if simulated_ack_required:
        simulated_failed_checks.append("maintenance owner acknowledgement still required")
    if simulated_decision == "release-with-sampling":
        simulated_failed_checks = []

    baseline_eta = 240 if baseline["decision"] == "hold-release" else 90 if baseline["decision"] == "reroute-review" else 30
    simulated_eta = 240 if simulated_decision == "hold-release" else 90 if simulated_decision == "reroute-review" else 30

    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "generated_at": utc_now_iso(),
        "contract_version": "fab-ops-recovery-what-if-v1",
        "lot_id": lot_id,
        "baseline": {
            **baseline,
            "release_eta_minutes": baseline_eta,
        },
        "simulated": {
            "lot_id": lot_id,
            "tool_id": tool["tool_id"],
            "decision": simulated_decision,
            "yield_risk_score": simulated_yield_risk,
            "tool_status": simulated_tool_status,
            "next_action": "Promote recovery path to release board if simulated posture holds through the next shift." if simulated_decision != "hold-release" else lot["next_action"],
            "primary_operator": assignment["primary_operator"],
            "maintenance_owner": assignment["maintenance_owner"],
            "failed_checks": simulated_failed_checks,
            "release_eta_minutes": simulated_eta,
        },
        "delta": {
            "risk_score_reduction": round(float(baseline["yield_risk_score"]) - simulated_yield_risk, 2),
            "release_eta_minutes": max(0, baseline_eta - simulated_eta),
            "maintenance_clearance": maintenance_complete,
        },
        "review_actions": [
            "Run the what-if drill before claiming the lot is ready for release or reroute.",
            "Pair the simulated decision with tool ownership and handoff signature before shift change.",
            "Use recovery board + release gate + what-if together during maintenance approval review.",
        ],
        "route_bundle": {
            "recovery_board": "/api/recovery-board",
            "recovery_what_if": "/api/recovery-what-if",
            "release_gate": f"/api/release-gate?lot_id={lot_id}",
            "shift_handoff_signature": "/api/shift-handoff/signature",
        },
    }


def build_handoff_signature() -> Dict[str, Any]:
    handoff = build_shift_handoff()
    manifest_bytes = stable_json(handoff).encode("utf-8")
    sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    signature = hmac.new(handoff_signing_key().encode("utf-8"), manifest_bytes, hashlib.sha256).hexdigest()
    return {
        "fab_id": handoff["fab_id"],
        "signature_contract": HANDOFF_SIGNATURE_CONTRACT,
        "signature_id": f"handoff-{handoff['fab_id']}-{handoff['shift']}",
        "algorithm": "hmac-sha256",
        "key_id": handoff_signing_key_id(),
        "sha256": sha256,
        "signature": signature,
        "digest_preview": sha256[:16],
        "signed_by": "ops-west-night",
        "signed_at": handoff["generated_at"],
        "release_channel": "morning-shift-briefing-pack",
        "manifest": handoff,
        "verification_route": "/api/shift-handoff/verify",
        "verification_steps": [
            "Confirm open critical alarms are still listed in the handoff pack.",
            "Recompute SHA-256 over the handoff manifest before release or reroute.",
            "Check must-acknowledge items and verify the HMAC signature against the current key id.",
        ],
    }


def build_handoff_signature_verification(
    *,
    algorithm: str | None = None,
    key_id: str | None = None,
    sha256: str | None = None,
    signature: str | None = None,
) -> Dict[str, Any]:
    current = build_handoff_signature()
    provided_algorithm = str(algorithm or current["algorithm"]).strip()
    provided_key_id = str(key_id or current["key_id"]).strip()
    provided_sha256 = str(sha256 or current["sha256"]).strip()
    provided_signature = str(signature or current["signature"]).strip()
    checks = {
        "algorithm_match": hmac.compare_digest(provided_algorithm, current["algorithm"]),
        "key_id_match": hmac.compare_digest(provided_key_id, current["key_id"]),
        "sha256_match": hmac.compare_digest(provided_sha256, current["sha256"]),
        "signature_match": hmac.compare_digest(provided_signature, current["signature"]),
    }
    return {
        "fab_id": current["fab_id"],
        "verification_contract": "fab-ops-handoff-signature-verify-v1",
        "signature_contract": HANDOFF_SIGNATURE_CONTRACT,
        "signature_id": current["signature_id"],
        "overall_valid": all(checks.values()),
        "checks": checks,
        "verification_route": "/api/shift-handoff/verify",
    }


def build_handoff_signature_verification(
    *,
    algorithm: str | None = None,
    key_id: str | None = None,
    sha256: str | None = None,
    signature: str | None = None,
) -> Dict[str, Any]:
    current = build_handoff_signature()
    provided_algorithm = str(algorithm or current["algorithm"]).strip()
    provided_key_id = str(key_id or current["key_id"]).strip()
    provided_sha256 = str(sha256 or current["sha256"]).strip()
    provided_signature = str(signature or current["signature"]).strip()
    checks = {
        "algorithm_match": hmac.compare_digest(provided_algorithm, current["algorithm"]),
        "key_id_match": hmac.compare_digest(provided_key_id, current["key_id"]),
        "sha256_match": hmac.compare_digest(provided_sha256, current["sha256"]),
        "signature_match": hmac.compare_digest(provided_signature, current["signature"]),
    }
    return {
        "fab_id": current["fab_id"],
        "verification_contract": "fab-ops-handoff-signature-verify-v1",
        "signature_contract": HANDOFF_SIGNATURE_CONTRACT,
        "signature_id": current["signature_id"],
        "overall_valid": all(checks.values()),
        "checks": checks,
        "verification_route": "/api/shift-handoff/verify",
    }


def build_audit_feed() -> Dict[str, Any]:
    return {
        "summary": {
            "events": len(AUDIT_EVENTS),
            "critical_alarm_count": len([alarm for alarm in ALARMS if alarm["severity"] == "critical"]),
            "watchlist_tools": len([tool for tool in TOOLS if tool["status"] != "healthy"]),
        },
        "items": AUDIT_EVENTS,
    }


def normalize_review_filter(name: str, value: str | None, allowed: set[str]) -> str | None:
    if value is None or value == "":
        return None
    if value not in allowed:
        raise HTTPException(status_code=400, detail=f"Invalid {name} filter: {value}")
    return value


def build_runtime_brief() -> Dict[str, Any]:
    summary = build_fab_summary()
    recovery_board = build_recovery_board()
    operator_auth = build_operator_auth_status()
    persistence = summarize_runtime_events()
    focus_lot = build_focus_lot()
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "generated_at": utc_now_iso(),
        "readiness_contract": "fab-ops-runtime-brief-v1",
        "headline": "Fab control tower that keeps alarms, lot risk, tool health, and shift handoff in one reviewable operator flow.",
        "report_contract": build_alarm_report_schema(),
        "handoff_contract": build_shift_handoff_schema(),
        "evidence_counts": {
            "fabs": len(FABS),
            "tools": len(TOOLS),
            "alarms": len(ALARMS),
            "lots_at_risk": len(LOTS_AT_RISK),
            "replay_scenarios": len(REPLAY_SUITE),
            "recovery_routes": len(recovery_board["items"]),
        },
        "assignment_count": len(TOOL_OWNERSHIP),
        "focus_lot": focus_lot,
        "operator_auth": operator_auth,
        "persistence": persistence,
        "ops_snapshot": summary,
        "review_flow": [
            "Open /health to confirm the fab runtime posture and review routes.",
            "Read /api/runtime/brief for the control-tower contract and evidence counts.",
            "Use /api/recovery-board to separate hold lots from watch and release-ready lots.",
            "Inspect /api/tool-ownership and /api/release-gate before acting on a shift decision.",
            "Export /api/shift-handoff, /api/shift-handoff/signature, and /api/shift-handoff/verify before the next operator release.",
        ],
        "two_minute_review": [
            "Open /health to confirm critical-alarm and replay surfaces are available.",
            "Read /api/runtime/brief for the control-tower contract and current ops snapshot.",
            "Inspect /api/recovery-board?mode=hold to find the lot that blocks release posture.",
            "Inspect /api/tool-ownership?tool_id=etch-14 and /api/release-gate?lot_id=lot-8812 before trusting release posture.",
            "Review /api/shift-handoff, /api/shift-handoff/signature, and /api/shift-handoff/verify before handing the queue to the next shift.",
        ],
        "watchouts": [
            "The demo uses synthetic fab telemetry and does not claim MES connectivity.",
            "Recommendations are grounded in alarm, lot, and SOP context only.",
            "The queue is intentionally small so reviewer paths stay easy to follow.",
        ],
        "proof_assets": [
            {"label": "Health Surface", "href": "/health", "kind": "route"},
            {"label": "Review Summary", "href": "/api/review-summary", "kind": "route"},
            {"label": "Recovery Board", "href": "/api/recovery-board?mode=hold", "kind": "route"},
            {"label": "Recovery What-If", "href": "/api/recovery-what-if?lot_id=lot-8812&yield_gain=0.25&maintenance_complete=true", "kind": "route"},
            {"label": "Tool Ownership", "href": "/api/tool-ownership?tool_id=etch-14", "kind": "route"},
            {"label": "Release Gate", "href": "/api/release-gate?lot_id=lot-8812", "kind": "route"},
            {"label": "Handoff Signature", "href": "/api/shift-handoff/signature", "kind": "route"},
            {"label": "Handoff Verify", "href": "/api/shift-handoff/verify", "kind": "route"},
        ],
        "links": {
            "runtime_scorecard": "/api/runtime/scorecard",
            "review_summary": "/api/review-summary",
            "review_summary_schema": "/api/review-summary/schema",
            "recovery_board": "/api/recovery-board",
            "recovery_what_if": "/api/recovery-what-if",
            "recovery_board_schema": "/api/recovery-board/schema",
            "review_pack": "/api/review-pack",
        },
    }


def build_review_pack() -> Dict[str, Any]:
    runtime_brief = build_runtime_brief()
    audit_feed = build_audit_feed()
    recovery_board = build_recovery_board()
    focus_lot = build_focus_lot()
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "generated_at": utc_now_iso(),
        "readiness_contract": "fab-ops-review-pack-v1",
        "headline": "Shift-ready control tower review pack tying alarms, yield risk, tool watchlist, and handoff export into one operator surface.",
        "proof_bundle": {
            "review_routes": [
                "/health",
                "/api/meta",
                "/api/runtime/brief",
                "/api/runtime/scorecard",
                "/api/review-summary",
                "/api/recovery-board",
                "/api/recovery-what-if",
                "/api/recovery-board/schema",
                "/api/review-pack",
                "/api/schema/alarm-report",
                "/api/schema/shift-handoff",
                "/api/fabs/summary",
                "/api/tools",
                "/api/tool-ownership",
                "/api/alarms",
                "/api/lots/at-risk",
                "/api/release-gate",
                "/api/shift-handoff",
                "/api/shift-handoff/signature",
                "/api/shift-handoff/verify",
                "/api/audit/feed",
                "/api/evals/replays",
            ],
            "critical_alarm_count": runtime_brief["ops_snapshot"]["critical_alarm_count"],
            "severe_lot_count": runtime_brief["ops_snapshot"]["severe_lot_count"],
            "replay_pass_count": len([case for case in REPLAY_SUITE if case["status"] == "pass"]),
            "latest_audit_events": audit_feed["summary"]["events"],
            "hold_count": recovery_board["summary"]["hold_count"],
            "watch_count": recovery_board["summary"]["watch_count"],
            "ready_count": recovery_board["summary"]["ready_count"],
            "operator_auth": runtime_brief["operator_auth"],
            "persistence": runtime_brief["persistence"],
        },
        "focus_lot": focus_lot,
        "operator_promises": [
            "Critical lots stay visible before a release decision is made.",
            "Tool alarms remain linked to chambers, lots, and SOP references.",
            "Shift handoff can be reviewed and signed without external infrastructure.",
        ],
        "trust_boundary": [
            "alarm board: operator triage starts from severity and lot impact",
            "lot risk board: yield exposure is visible before reroute or release",
            "handoff pack: the next shift can review open alarms, watchlist items, and signature proof",
            "replay suite: the surface stays reviewable without live fab telemetry",
        ],
        "review_sequence": [
            "Health -> Runtime Brief -> Recovery Board -> Tool Ownership -> Release Gate -> Shift Handoff -> Audit Feed -> Replay Summary",
        ],
        "two_minute_review": runtime_brief["two_minute_review"],
        "proof_assets": runtime_brief["proof_assets"],
        "links": {
            "runtime_scorecard": "/api/runtime/scorecard",
            "review_summary": "/api/review-summary",
            "recovery_board": "/api/recovery-board",
            "recovery_what_if": "/api/recovery-what-if",
            "runtime_brief": "/api/runtime/brief",
        },
    }


def build_meta() -> Dict[str, Any]:
    operator_auth = build_operator_auth_status()
    persistence = summarize_runtime_events()
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "generated_at": utc_now_iso(),
        "runtime_contract": "fab-ops-runtime-brief-v1",
        "review_pack_contract": "fab-ops-review-pack-v1",
        "review_summary_contract": "fab-ops-review-summary-v1",
        "report_contract": build_alarm_report_schema(),
        "handoff_contract": build_shift_handoff_schema(),
        "routes": [
            "/health",
            "/api/meta",
            "/api/runtime/brief",
            "/api/runtime/scorecard",
            "/api/review-summary",
            "/api/review-summary/schema",
            "/api/recovery-board",
            "/api/recovery-what-if",
            "/api/recovery-board/schema",
            "/api/review-pack",
            "/api/schema/alarm-report",
            "/api/schema/shift-handoff",
            "/api/fabs/summary",
            "/api/tools",
            "/api/tool-ownership",
            "/api/alarms",
            "/api/lots/at-risk",
            "/api/release-gate",
            "/api/shift-handoff",
            "/api/shift-handoff/signature",
            "/api/shift-handoff/verify",
            "/api/audit/feed",
            "/api/evals/replays",
        ],
        "capabilities": [
            "fab-control-tower",
            "tool-health-board",
            "tool-ownership-surface",
            "release-gate-surface",
            "recovery-board-surface",
            "lot-risk-prioritization",
            "shift-handoff-surface",
            "audit-feed-surface",
            "review-pack-surface",
            "replay-suite-surface",
        ],
        "diagnostics": {
            "demo_mode": "synthetic-fab-telemetry",
            "shift_handoff_ready": True,
            "recovery_board_ready": True,
            "audit_feed_ready": True,
            "replay_suite_ready": True,
            "operator_auth_enabled": operator_auth["enabled"],
            "runtime_store_path": persistence["path"],
            "next_action": "Review critical alarms and severe lots before opening the shift handoff export.",
        },
        "ops_contract": {
            "schema": "ops-envelope-v1",
            "version": 1,
            "required_fields": ["service", "status", "diagnostics.next_action"],
        },
    }


def build_runtime_scorecard() -> Dict[str, Any]:
    summary = build_fab_summary()
    persistence = summarize_runtime_events()
    operator_auth = build_operator_auth_status()
    audit_feed = build_audit_feed()
    replay_summary = build_replay_summary()
    recovery_board = build_recovery_board()
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "generated_at": utc_now_iso(),
        "readiness_contract": "fab-ops-runtime-scorecard-v1",
        "headline": "Runtime scorecard for fab handoff posture, release pressure, and persisted operator evidence.",
        "runtime": {
            "operator_auth": operator_auth,
            "persistence": persistence,
            "review_routes": [
                "/health",
                "/api/runtime/brief",
                "/api/runtime/scorecard",
                "/api/review-summary",
                "/api/recovery-board",
                "/api/review-pack",
                "/api/shift-handoff/signature",
                "/api/shift-handoff/verify",
            ],
        },
        "summary": {
            "critical_alarm_count": summary["critical_alarm_count"],
            "severe_lot_count": summary["severe_lot_count"],
            "watchlist_tools": audit_feed["summary"]["watchlist_tools"],
            "hold_lots": recovery_board["summary"]["hold_count"],
            "watch_lots": recovery_board["summary"]["watch_count"],
            "ready_lots": recovery_board["summary"]["ready_count"],
            "replay_score_pct": replay_summary["summary"]["score_pct"],
            "persisted_events": persistence["event_count"],
        },
        "recommendations": [
            "Triage the recovery board before trusting any release-ready lot.",
            "Verify tool ownership and release gate before exporting a shift handoff.",
            "Treat the signed handoff surface plus verification as the final operator artifact for next-shift review.",
            "Keep replay score and persisted runtime events paired during reviewer walkthroughs.",
        ],
        "links": {
            "health": "/health",
            "runtime_brief": "/api/runtime/brief",
            "review_summary": "/api/review-summary",
            "recovery_board": "/api/recovery-board",
            "recovery_what_if": "/api/recovery-what-if",
            "review_pack": "/api/review-pack",
            "handoff_signature": "/api/shift-handoff/signature",
            "handoff_verify": "/api/shift-handoff/verify",
        },
    }


def build_review_summary(
    severity: str | None = None,
    risk_bucket: str | None = None,
) -> Dict[str, Any]:
    severity_filter = normalize_review_filter("severity", severity, ALLOWED_SEVERITIES)
    risk_bucket_filter = normalize_review_filter("risk_bucket", risk_bucket, ALLOWED_RISK_BUCKETS)
    filtered_alarms = [
        item for item in ALARMS if severity_filter is None or item["severity"] == severity_filter
    ]
    filtered_lots = [
        item for item in LOTS_AT_RISK if risk_bucket_filter is None or item["risk_bucket"] == risk_bucket_filter
    ]
    spotlight_alarm = sorted(
        filtered_alarms,
        key=lambda item: (ALARM_SEVERITY_RANK.get(item["severity"], 99), item["started_at"]),
    )[0] if filtered_alarms else None
    spotlight_lot = sorted(
        filtered_lots,
        key=lambda item: item["yield_risk_score"],
        reverse=True,
    )[0] if filtered_lots else None
    replay_summary = build_replay_summary()
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "generated_at": utc_now_iso(),
        "contract_version": "fab-ops-review-summary-v1",
        "filters": {
            "severity": severity_filter,
            "risk_bucket": risk_bucket_filter,
        },
        "summary": {
            "alarm_count": len(filtered_alarms),
            "lot_count": len(filtered_lots),
            "critical_alarm_count": len([item for item in filtered_alarms if item["severity"] == "critical"]),
            "severe_lot_count": len([item for item in filtered_lots if item["risk_bucket"] == "severe"]),
            "replay_score_pct": replay_summary["summary"]["score_pct"],
        },
        "spotlight": {
            "alarm": spotlight_alarm,
            "lot": spotlight_lot,
        },
        "fastest_review_path": [
            "/health",
            "/api/review-summary",
            "/api/tool-ownership",
            "/api/release-gate",
            "/api/shift-handoff",
        ],
        "route_bundle": {
            "review_summary": "/api/review-summary",
            "review_pack": "/api/review-pack",
            "tool_ownership": "/api/tool-ownership?tool_id=etch-14",
            "release_gate": "/api/release-gate?lot_id=lot-8812",
            "shift_handoff": "/api/shift-handoff",
        },
    }


def build_recovery_board(mode: str | None = None) -> Dict[str, Any]:
    normalized_mode = normalize_review_filter("mode", mode, ALLOWED_RECOVERY_MODES) or "all"
    items: List[Dict[str, Any]] = []
    for lot in sorted(LOTS_AT_RISK, key=lambda item: item["yield_risk_score"], reverse=True):
        gate = build_release_gate(lot["lot_id"])
        tool = get_tool_or_404(lot["tool_id"])
        ownership = build_tool_ownership(tool["tool_id"])
        if gate["decision"] == "hold-release":
            board_status = "hold"
        elif gate["decision"] == "reroute-review":
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
                "yield_risk_score": lot["yield_risk_score"],
                "risk_bucket": lot["risk_bucket"],
                "board_status": board_status,
                "release_decision": gate["decision"],
                "tool_status": tool["status"],
                "maintenance_owner": ownership["maintenance_owner"],
                "ack_required": ownership["ack_required"],
                "escalation_lane": ownership["escalation_lane"],
                "failed_checks": gate["failed_checks"],
                "next_action": gate["next_action"],
            }
        )

    return {
        "status": "ok",
        "service": SERVICE_NAME,
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
        "review_actions": [
            "Start with hold lots before reviewing watch or ready lots.",
            "Keep tool ownership, release gate, and handoff pack together during shift review.",
            "Treat the signed handoff as the final next-shift artifact after recovery decisions are made.",
        ],
        "route_bundle": {
            "recovery_board": "/api/recovery-board",
            "recovery_board_schema": "/api/recovery-board/schema",
            "review_summary": "/api/review-summary",
            "tool_ownership": "/api/tool-ownership?tool_id=etch-14",
            "release_gate": "/api/release-gate?lot_id=lot-8812",
            "shift_handoff": "/api/shift-handoff",
        },
    }


def build_recovery_board_schema() -> Dict[str, Any]:
    return {
        "schema": "fab-ops-recovery-board-v1",
        "required_fields": [
            "contract_version",
            "summary.visible_lots",
            "summary.hold_count",
            "items",
            "route_bundle.recovery_board",
        ],
        "links": {
            "recovery_board": "/api/recovery-board",
            "recovery_what_if": "/api/recovery-what-if",
            "recovery_board_schema": "/api/recovery-board/schema",
            "review_summary": "/api/review-summary",
            "review_pack": "/api/review-pack",
            "runtime_scorecard": "/api/runtime/scorecard",
        },
    }


def build_review_summary_schema() -> Dict[str, Any]:
    return {
        "schema": "fab-ops-review-summary-v1",
        "required_fields": [
            "service",
            "contract_version",
            "summary.alarm_count",
            "summary.replay_score_pct",
            "fastest_review_path",
            "route_bundle.review_summary",
        ],
        "links": {
            "review_summary": "/api/review-summary",
            "recovery_board": "/api/recovery-board",
            "review_pack": "/api/review-pack",
            "runtime_brief": "/api/runtime/brief",
        },
    }


def build_replay_summary() -> Dict[str, Any]:
    total_checks = sum(case["checks"] for case in REPLAY_SUITE)
    passed_checks = sum(case["checks"] for case in REPLAY_SUITE if case["status"] == "pass")
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "generated_at": utc_now_iso(),
        "summary": {
            "scenarios": len(REPLAY_SUITE),
            "total_checks": total_checks,
            "passed_checks": passed_checks,
            "score_pct": round((passed_checks / total_checks) * 100, 1) if total_checks else 0.0,
        },
        "runs": REPLAY_SUITE,
    }


app = FastAPI(title="Fab Ops Yield Control Tower")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
