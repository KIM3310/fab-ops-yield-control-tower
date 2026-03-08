from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles


BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

SERVICE_NAME = "fab-ops-yield-control-tower"
ALARM_REPORT_SCHEMA = "fab-ops-alarm-report-v1"
SHIFT_HANDOFF_SCHEMA = "fab-ops-shift-handoff-v1"

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


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def build_runtime_brief() -> Dict[str, Any]:
    summary = build_fab_summary()
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
        },
        "ops_snapshot": summary,
        "review_flow": [
            "Open /health to confirm the fab runtime posture and review routes.",
            "Read /api/runtime/brief for the control-tower contract and evidence counts.",
            "Inspect /api/alarms and /api/lots/at-risk before acting on a shift decision.",
            "Export /api/shift-handoff before the next operator release.",
        ],
        "watchouts": [
            "The demo uses synthetic fab telemetry and does not claim MES connectivity.",
            "Recommendations are grounded in alarm, lot, and SOP context only.",
            "The queue is intentionally small so reviewer paths stay easy to follow.",
        ],
    }


def build_review_pack() -> Dict[str, Any]:
    runtime_brief = build_runtime_brief()
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
                "/api/review-pack",
                "/api/schema/alarm-report",
                "/api/schema/shift-handoff",
                "/api/fabs/summary",
                "/api/tools",
                "/api/alarms",
                "/api/lots/at-risk",
                "/api/shift-handoff",
                "/api/evals/replays",
            ],
            "critical_alarm_count": runtime_brief["ops_snapshot"]["critical_alarm_count"],
            "severe_lot_count": runtime_brief["ops_snapshot"]["severe_lot_count"],
            "replay_pass_count": len([case for case in REPLAY_SUITE if case["status"] == "pass"]),
        },
        "operator_promises": [
            "Critical lots stay visible before a release decision is made.",
            "Tool alarms remain linked to chambers, lots, and SOP references.",
            "Shift handoff can be reviewed without external infrastructure.",
        ],
        "trust_boundary": [
            "alarm board: operator triage starts from severity and lot impact",
            "lot risk board: yield exposure is visible before reroute or release",
            "handoff pack: the next shift can review open alarms and watchlist items",
            "replay suite: the surface stays reviewable without live fab telemetry",
        ],
        "review_sequence": [
            "Health -> Runtime Brief -> Alarms -> Lots At Risk -> Shift Handoff -> Replay Summary",
        ],
    }


def build_meta() -> Dict[str, Any]:
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "generated_at": utc_now_iso(),
        "runtime_contract": "fab-ops-runtime-brief-v1",
        "review_pack_contract": "fab-ops-review-pack-v1",
        "report_contract": build_alarm_report_schema(),
        "handoff_contract": build_shift_handoff_schema(),
        "routes": [
            "/health",
            "/api/meta",
            "/api/runtime/brief",
            "/api/review-pack",
            "/api/schema/alarm-report",
            "/api/schema/shift-handoff",
            "/api/fabs/summary",
            "/api/tools",
            "/api/alarms",
            "/api/lots/at-risk",
            "/api/shift-handoff",
            "/api/evals/replays",
        ],
        "capabilities": [
            "fab-control-tower",
            "tool-health-board",
            "lot-risk-prioritization",
            "shift-handoff-surface",
            "review-pack-surface",
            "replay-suite-surface",
        ],
        "diagnostics": {
            "demo_mode": "synthetic-fab-telemetry",
            "shift_handoff_ready": True,
            "replay_suite_ready": True,
            "next_action": "Review critical alarms and severe lots before opening the shift handoff export.",
        },
        "ops_contract": {
            "schema": "ops-envelope-v1",
            "version": 1,
            "required_fields": ["service", "status", "diagnostics.next_action"],
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
            "review_pack": "/api/review-pack",
            "alarm_report_schema": "/api/schema/alarm-report",
            "shift_handoff_schema": "/api/schema/shift-handoff",
            "replay_evals": "/api/evals/replays",
        },
    }


@app.get("/api/meta")
async def meta() -> Dict[str, Any]:
    return build_meta()


@app.get("/api/runtime/brief")
async def runtime_brief() -> Dict[str, Any]:
    return build_runtime_brief()


@app.get("/api/review-pack")
async def review_pack() -> Dict[str, Any]:
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
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "items": [build_fab_summary()],
    }


@app.get("/api/tools")
async def tools() -> Dict[str, Any]:
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "items": TOOLS,
    }


@app.get("/api/alarms")
async def alarms() -> Dict[str, Any]:
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "items": ALARMS,
    }


@app.get("/api/lots/at-risk")
async def lots_at_risk() -> Dict[str, Any]:
    items = sorted(LOTS_AT_RISK, key=lambda item: item["yield_risk_score"], reverse=True)
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "items": items,
    }


@app.get("/api/shift-handoff")
async def shift_handoff() -> Dict[str, Any]:
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "payload": build_shift_handoff(),
    }


@app.get("/api/evals/replays")
async def replay_evals() -> Dict[str, Any]:
    return build_replay_summary()


app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="frontend")
