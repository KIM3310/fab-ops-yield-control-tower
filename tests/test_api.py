from __future__ import annotations

import importlib.util
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


APP_MODULE = load_module("fab_ops_main", "app/main.py")


def test_health_and_service_grade_surfaces() -> None:
    client = TestClient(APP_MODULE.app)

    health = client.get("/health")
    meta = client.get("/api/meta")
    runtime_brief = client.get("/api/runtime/brief")
    runtime_scorecard = client.get("/api/runtime/scorecard")
    review_summary = client.get("/api/review-summary?severity=critical")
    review_summary_schema = client.get("/api/review-summary/schema")
    recovery_board = client.get("/api/recovery-board?mode=hold")
    release_board = client.get("/api/release-board")
    recovery_what_if = client.get("/api/recovery-what-if?lot_id=lot-8812&yield_gain=0.25&maintenance_complete=true")
    recovery_board_schema = client.get("/api/recovery-board/schema")
    review_pack = client.get("/api/review-pack")
    alarm_schema = client.get("/api/schema/alarm-report")
    handoff_schema = client.get("/api/schema/shift-handoff")
    audit_feed = client.get("/api/audit/feed")

    assert health.status_code == 200
    health_payload = health.json()
    assert health_payload["service"] == "fab-ops-yield-control-tower"
    assert health_payload["links"]["meta"] == "/api/meta"
    assert health_payload["links"]["runtime_brief"] == "/api/runtime/brief"
    assert health_payload["links"]["review_summary"] == "/api/review-summary"
    assert health_payload["links"]["recovery_board"] == "/api/recovery-board"
    assert health_payload["links"]["release_board"] == "/api/release-board"
    assert health_payload["links"]["recovery_what_if"] == "/api/recovery-what-if"
    assert health_payload["links"]["review_pack"] == "/api/review-pack"
    assert health_payload["diagnostics"]["shift_handoff_ready"] is True
    assert health_payload["diagnostics"]["audit_feed_ready"] is True
    assert health_payload["ops_contract"]["schema"] == "ops-envelope-v1"

    assert meta.status_code == 200
    meta_payload = meta.json()
    assert meta_payload["runtime_contract"] == "fab-ops-runtime-brief-v1"
    assert meta_payload["review_pack_contract"] == "fab-ops-review-pack-v1"
    assert meta_payload["review_summary_contract"] == "fab-ops-review-summary-v1"
    assert meta_payload["report_contract"]["schema"] == "fab-ops-alarm-report-v1"
    assert meta_payload["handoff_contract"]["schema"] == "fab-ops-shift-handoff-v1"
    assert meta_payload["diagnostics"]["recovery_board_ready"] is True
    assert "/api/review-summary" in meta_payload["routes"]
    assert "/api/recovery-board" in meta_payload["routes"]
    assert "/api/release-board" in meta_payload["routes"]
    assert "/api/recovery-what-if" in meta_payload["routes"]
    assert "/api/recovery-board/schema" in meta_payload["routes"]
    assert "/api/alarms" in meta_payload["routes"]
    assert "/api/shift-handoff" in meta_payload["routes"]
    assert "/api/tool-ownership" in meta_payload["routes"]
    assert "/api/release-gate" in meta_payload["routes"]
    assert "/api/shift-handoff/signature" in meta_payload["routes"]

    assert runtime_brief.status_code == 200
    brief_payload = runtime_brief.json()
    assert brief_payload["readiness_contract"] == "fab-ops-runtime-brief-v1"
    assert brief_payload["evidence_counts"]["replay_scenarios"] == 4
    assert brief_payload["evidence_counts"]["recovery_routes"] == 3
    assert brief_payload["ops_snapshot"]["critical_alarm_count"] == 1
    assert brief_payload["assignment_count"] == 3
    assert brief_payload["focus_lot"]["lot_id"] == "lot-8812"
    assert brief_payload["focus_lot"]["release_decision"] == "hold-release"
    assert brief_payload["focus_lot"]["review_path"][-1] == "/api/shift-handoff/signature"
    assert brief_payload["links"]["review_summary"] == "/api/review-summary"
    assert brief_payload["links"]["recovery_board"] == "/api/recovery-board"
    assert brief_payload["links"]["release_board"] == "/api/release-board"
    assert brief_payload["links"]["recovery_what_if"] == "/api/recovery-what-if"
    assert brief_payload["links"]["runtime_scorecard"] == "/api/runtime/scorecard"
    assert len(brief_payload["two_minute_review"]) == 6
    assert brief_payload["proof_assets"][0]["href"] == "/health"
    assert any(asset["href"] == "/api/release-board" for asset in brief_payload["proof_assets"])

    assert runtime_scorecard.status_code == 200
    scorecard_payload = runtime_scorecard.json()
    assert scorecard_payload["readiness_contract"] == "fab-ops-runtime-scorecard-v1"
    assert scorecard_payload["summary"]["critical_alarm_count"] == 1
    assert scorecard_payload["summary"]["hold_lots"] == 1
    assert scorecard_payload["summary"]["watch_lots"] == 1
    assert scorecard_payload["summary"]["ready_lots"] == 1
    assert scorecard_payload["summary"]["release_board_rows"] == 3
    assert scorecard_payload["runtime"]["persistence"]["enabled"] is True
    assert scorecard_payload["runtime"]["persistence"]["event_type_counts"]["route_hit"] >= 1
    assert scorecard_payload["links"]["recovery_board"] == "/api/recovery-board"
    assert scorecard_payload["links"]["release_board"] == "/api/release-board"
    assert scorecard_payload["links"]["recovery_what_if"] == "/api/recovery-what-if"

    assert review_summary.status_code == 200
    review_summary_payload = review_summary.json()
    assert review_summary_payload["contract_version"] == "fab-ops-review-summary-v1"
    assert review_summary_payload["summary"]["alarm_count"] == 1
    assert review_summary_payload["spotlight"]["alarm"]["alarm_id"] == "alm-2041"
    assert review_summary_payload["route_bundle"]["review_summary"] == "/api/review-summary"

    assert review_summary_schema.status_code == 200
    assert review_summary_schema.json()["schema"] == "fab-ops-review-summary-v1"

    assert recovery_board.status_code == 200
    recovery_payload = recovery_board.json()
    assert recovery_payload["contract_version"] == "fab-ops-recovery-board-v1"
    assert recovery_payload["summary"]["hold_count"] == 1
    assert recovery_payload["items"][0]["lot_id"] == "lot-8812"
    assert recovery_payload["spotlight"]["maintenance_owner"] == "maint-etch-cell-a"
    assert recovery_payload["route_bundle"]["recovery_board_schema"] == "/api/recovery-board/schema"

    assert release_board.status_code == 200
    release_board_payload = release_board.json()
    assert release_board_payload["contract_version"] == "fab-ops-release-board-v1"
    assert release_board_payload["summary"]["hold_release"] == 1
    assert release_board_payload["summary"]["reroute_review"] == 1
    assert release_board_payload["summary"]["release_with_sampling"] == 1
    assert release_board_payload["spotlight"]["lot_id"] == "lot-8812"

    assert recovery_what_if.status_code == 200
    recovery_what_if_payload = recovery_what_if.json()
    assert recovery_what_if_payload["contract_version"] == "fab-ops-recovery-what-if-v1"
    assert recovery_what_if_payload["baseline"]["decision"] == "hold-release"
    assert recovery_what_if_payload["simulated"]["decision"] in {"reroute-review", "release-with-sampling"}
    assert recovery_what_if_payload["delta"]["release_eta_minutes"] >= 0
    assert recovery_what_if_payload["route_bundle"]["recovery_what_if"] == "/api/recovery-what-if"

    assert recovery_board_schema.status_code == 200
    assert recovery_board_schema.json()["schema"] == "fab-ops-recovery-board-v1"

    assert review_pack.status_code == 200
    review_payload = review_pack.json()
    assert review_payload["readiness_contract"] == "fab-ops-review-pack-v1"
    assert "/api/runtime/scorecard" in review_payload["proof_bundle"]["review_routes"]
    assert "/api/review-summary" in review_payload["proof_bundle"]["review_routes"]
    assert "/api/recovery-board" in review_payload["proof_bundle"]["review_routes"]
    assert "/api/release-board" in review_payload["proof_bundle"]["review_routes"]
    assert "/api/recovery-what-if" in review_payload["proof_bundle"]["review_routes"]
    assert review_payload["proof_bundle"]["critical_alarm_count"] == 1
    assert review_payload["proof_bundle"]["hold_count"] == 1
    assert review_payload["proof_bundle"]["watch_count"] == 1
    assert review_payload["proof_bundle"]["ready_count"] == 1
    assert review_payload["proof_bundle"]["release_board_rows"] == 3
    assert "/api/evals/replays" in review_payload["proof_bundle"]["review_routes"]
    assert "/api/audit/feed" in review_payload["proof_bundle"]["review_routes"]
    assert review_payload["proof_bundle"]["latest_audit_events"] == 3
    assert review_payload["focus_lot"]["maintenance_owner"] == "maint-etch-cell-a"
    assert review_payload["focus_lot"]["review_path"][1] == "/api/recovery-board?mode=hold"
    assert isinstance(review_payload["operator_promises"], list)
    assert len(review_payload["two_minute_review"]) == 6
    assert review_payload["proof_assets"][0]["href"] == "/health"

    assert alarm_schema.status_code == 200
    assert alarm_schema.json()["schema"] == "fab-ops-alarm-report-v1"

    assert handoff_schema.status_code == 200
    assert handoff_schema.json()["schema"] == "fab-ops-shift-handoff-v1"

    assert audit_feed.status_code == 200
    assert audit_feed.json()["summary"]["events"] == 3


def test_core_domain_endpoints() -> None:
    client = TestClient(APP_MODULE.app)

    fabs = client.get("/api/fabs/summary")
    tools = client.get("/api/tools")
    ownership = client.get("/api/tool-ownership?tool_id=etch-14")
    alarms = client.get("/api/alarms")
    lots = client.get("/api/lots/at-risk")
    release_gate = client.get("/api/release-gate?lot_id=lot-8812")
    handoff = client.get("/api/shift-handoff")
    handoff_signature = client.get("/api/shift-handoff/signature")
    handoff_verify = client.get("/api/shift-handoff/verify")
    replay = client.get("/api/evals/replays")

    assert fabs.status_code == 200
    assert fabs.json()["items"][0]["critical_alarm_count"] == 1

    assert tools.status_code == 200
    assert len(tools.json()["items"]) == 3
    assert any(item["status"] == "alarm" for item in tools.json()["items"])

    assert ownership.status_code == 200
    ownership_payload = ownership.json()["payload"]
    assert ownership_payload["maintenance_owner"] == "maint-etch-cell-a"
    assert ownership_payload["ack_required"] is True

    assert alarms.status_code == 200
    assert alarms.json()["items"][0]["alarm_id"] == "alm-2041"

    assert lots.status_code == 200
    lots_payload = lots.json()["items"]
    assert lots_payload[0]["lot_id"] == "lot-8812"
    assert lots_payload[0]["yield_risk_score"] > lots_payload[-1]["yield_risk_score"]

    assert release_gate.status_code == 200
    gate_payload = release_gate.json()["payload"]
    assert gate_payload["decision"] == "hold-release"
    assert "critical tool alarm still open" in gate_payload["failed_checks"]

    assert handoff.status_code == 200
    handoff_payload = handoff.json()["payload"]
    assert handoff_payload["schema"] == "fab-ops-shift-handoff-v1"
    assert "etch-14 maintenance approval" in handoff_payload["must_acknowledge"]

    assert handoff_signature.status_code == 200
    signature_payload = handoff_signature.json()["payload"]
    assert signature_payload["signature_contract"] == "fab-ops-handoff-signature-v1"
    assert signature_payload["signature_id"] == "handoff-fab-west-1-night"
    assert signature_payload["algorithm"] == "hmac-sha256"
    assert len(signature_payload["sha256"]) == 64
    assert len(signature_payload["signature"]) == 64

    assert handoff_verify.status_code == 200
    verify_payload = handoff_verify.json()["payload"]
    assert verify_payload["overall_valid"] is True
    assert verify_payload["checks"]["signature_match"] is True

    assert replay.status_code == 200
    replay_payload = replay.json()
    assert replay_payload["summary"]["scenarios"] == 4
    assert replay_payload["summary"]["score_pct"] == 100.0


def test_release_gate_relaxation_and_audit_feed() -> None:
    client = TestClient(APP_MODULE.app)

    watch_gate = client.get("/api/release-gate?lot_id=lot-8836")
    audit_feed = client.get("/api/audit/feed")

    assert watch_gate.status_code == 200
    watch_payload = watch_gate.json()["payload"]
    assert watch_payload["decision"] == "release-with-sampling"
    assert watch_payload["failed_checks"] == []

    assert audit_feed.status_code == 200
    audit_payload = audit_feed.json()["items"]
    assert audit_payload[0]["event"] == "handoff-preview-generated"
    assert audit_payload[0]["tool_id"] == "etch-14"


def test_review_summary_rejects_invalid_filters() -> None:
    client = TestClient(APP_MODULE.app)

    response = client.get("/api/review-summary?severity=urgent")

    assert response.status_code == 400
    assert "Invalid severity filter" in response.json()["detail"]


def test_recovery_board_rejects_invalid_filters() -> None:
    client = TestClient(APP_MODULE.app)

    response = client.get("/api/recovery-board?mode=escalate")

    assert response.status_code == 400
    assert "Invalid mode filter" in response.json()["detail"]


def test_sensitive_routes_require_operator_token_when_enabled(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("FAB_OPS_OPERATOR_TOKEN", "fab-secret")
    monkeypatch.setenv("FAB_OPS_OPERATOR_ALLOWED_ROLES", "shift-lead,release-supervisor")
    monkeypatch.setenv("FAB_OPS_RUNTIME_STORE_PATH", str(tmp_path / "fab-runtime.jsonl"))
    client = TestClient(APP_MODULE.app)

    unauthorized = client.get("/api/release-gate?lot_id=lot-8812")
    assert unauthorized.status_code == 401

    denied_role = client.get(
        "/api/release-gate?lot_id=lot-8812",
        headers={"x-operator-token": "fab-secret"},
    )
    assert denied_role.status_code == 403

    authorized = client.get(
        "/api/release-gate?lot_id=lot-8812",
        headers={
            "x-operator-token": "fab-secret",
            "x-operator-role": "shift-lead",
        },
    )
    assert authorized.status_code == 200

    handoff = client.get(
        "/api/shift-handoff",
        headers={"x-operator-token": "fab-secret", "x-operator-role": "shift-lead"},
    )
    assert handoff.status_code == 200

    signature = client.get(
        "/api/shift-handoff/signature",
        headers={
            "x-operator-token": "fab-secret",
            "x-operator-role": "shift-lead",
        },
    )
    assert signature.status_code == 200

    scorecard = client.get("/api/runtime/scorecard")
    assert scorecard.status_code == 200
    body = scorecard.json()
    assert body["runtime"]["operator_auth"]["enabled"] is True
    assert body["runtime"]["operator_auth"]["required_roles"] == [
        "shift-lead",
        "release-supervisor",
    ]
    assert body["runtime"]["persistence"]["event_count"] >= 3
