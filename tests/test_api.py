from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app


def test_platform_health() -> None:
    client = TestClient(app)
    health = client.get("/health")
    resource_pack = client.get("/api/resource-pack")
    assert health.status_code == 200
    payload = health.json()
    assert payload["service"] == "semiconductor-ops-platform"
    assert "fab_ops" in payload["domains"]
    assert "scanner" in payload["domains"]
    assert payload["reviewer_fast_path"][0] == "/health"
    assert payload["reviewer_fast_path"][1] == "/api/resource-pack"
    assert payload["proof_routes"]["resource_pack"] == "/api/resource-pack"
    assert payload["proof_routes"]["fab_ops_review_pack"] == "/api/fab-ops/review-pack"
    assert payload["proof_routes"]["scanner_review_pack"] == "/api/scanner/review-pack"
    assert payload["links"]["resource_pack"] == "/api/resource-pack"
    assert resource_pack.status_code == 200
    resource_payload = resource_pack.json()
    assert resource_payload["contract_version"] == "semiconductor-ops-resource-pack-v1"
    assert resource_payload["summary"]["fab_alarm_count"] >= 2
    assert "external_data" in resource_payload
    assert resource_payload["reviewer_fast_path"][1] == "/api/resource-pack"


# ---------------------------------------------------------------------------
# Fab Ops domain
# ---------------------------------------------------------------------------

def test_fab_ops_health_and_service_grade_surfaces() -> None:
    client = TestClient(app)

    meta = client.get("/api/fab-ops/meta")
    runtime_brief = client.get("/api/fab-ops/runtime/brief")
    runtime_scorecard = client.get("/api/fab-ops/runtime/scorecard")
    review_summary = client.get("/api/fab-ops/review-summary?severity=critical")
    review_summary_schema = client.get("/api/fab-ops/review-summary/schema")
    recovery_board = client.get("/api/fab-ops/recovery-board?mode=hold")
    release_board = client.get("/api/fab-ops/release-board")
    recovery_what_if = client.get("/api/fab-ops/recovery-what-if?lot_id=lot-8812&yield_gain=0.25&maintenance_complete=true")
    recovery_board_schema = client.get("/api/fab-ops/recovery-board/schema")
    review_pack = client.get("/api/fab-ops/review-pack")
    alarm_schema = client.get("/api/fab-ops/schema/alarm-report")
    handoff_schema = client.get("/api/fab-ops/schema/shift-handoff")
    audit_feed = client.get("/api/fab-ops/audit/feed")

    assert meta.status_code == 200
    meta_payload = meta.json()
    assert meta_payload["runtime_contract"] == "fab-ops-runtime-brief-v1"
    assert meta_payload["review_pack_contract"] == "fab-ops-review-pack-v1"
    assert meta_payload["review_summary_contract"] == "fab-ops-review-summary-v1"
    assert meta_payload["report_contract"]["schema"] == "fab-ops-alarm-report-v1"
    assert meta_payload["handoff_contract"]["schema"] == "fab-ops-shift-handoff-v1"
    assert meta_payload["diagnostics"]["recovery_board_ready"] is True
    assert "/api/fab-ops/review-summary" in meta_payload["routes"]
    assert "/api/fab-ops/recovery-board" in meta_payload["routes"]
    assert "/api/fab-ops/release-board" in meta_payload["routes"]
    assert "/api/fab-ops/recovery-what-if" in meta_payload["routes"]
    assert "/api/fab-ops/recovery-board/schema" in meta_payload["routes"]
    assert "/api/fab-ops/alarms" in meta_payload["routes"]
    assert "/api/fab-ops/shift-handoff" in meta_payload["routes"]
    assert "/api/fab-ops/tool-ownership" in meta_payload["routes"]
    assert "/api/fab-ops/release-gate" in meta_payload["routes"]
    assert "/api/fab-ops/shift-handoff/signature" in meta_payload["routes"]

    assert runtime_brief.status_code == 200
    brief_payload = runtime_brief.json()
    assert brief_payload["readiness_contract"] == "fab-ops-runtime-brief-v1"
    assert brief_payload["evidence_counts"]["replay_scenarios"] == 4
    assert brief_payload["evidence_counts"]["recovery_routes"] == 3
    assert brief_payload["ops_snapshot"]["critical_alarm_count"] == 1
    assert brief_payload["assignment_count"] == 3
    assert brief_payload["focus_lot"]["lot_id"] == "lot-8812"
    assert brief_payload["focus_lot"]["release_decision"] == "hold-release"
    assert brief_payload["focus_lot"]["review_path"][-1] == "/api/fab-ops/shift-handoff/signature"
    assert brief_payload["links"]["review_summary"] == "/api/fab-ops/review-summary"
    assert brief_payload["links"]["recovery_board"] == "/api/fab-ops/recovery-board"
    assert brief_payload["links"]["release_board"] == "/api/fab-ops/release-board"
    assert brief_payload["links"]["recovery_what_if"] == "/api/fab-ops/recovery-what-if"
    assert brief_payload["links"]["runtime_scorecard"] == "/api/fab-ops/runtime/scorecard"
    assert len(brief_payload["two_minute_review"]) == 6
    assert brief_payload["proof_assets"][0]["href"] == "/health"
    assert any(asset["href"] == "/api/fab-ops/release-board" for asset in brief_payload["proof_assets"])

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
    assert scorecard_payload["links"]["recovery_board"] == "/api/fab-ops/recovery-board"
    assert scorecard_payload["links"]["release_board"] == "/api/fab-ops/release-board"
    assert scorecard_payload["links"]["recovery_what_if"] == "/api/fab-ops/recovery-what-if"

    assert review_summary.status_code == 200
    review_summary_payload = review_summary.json()
    assert review_summary_payload["contract_version"] == "fab-ops-review-summary-v1"
    assert review_summary_payload["summary"]["alarm_count"] == 1
    assert review_summary_payload["spotlight"]["alarm"]["alarm_id"] == "alm-2041"
    assert review_summary_payload["route_bundle"]["review_summary"] == "/api/fab-ops/review-summary"

    assert review_summary_schema.status_code == 200
    assert review_summary_schema.json()["schema"] == "fab-ops-review-summary-v1"

    assert recovery_board.status_code == 200
    recovery_payload = recovery_board.json()
    assert recovery_payload["contract_version"] == "fab-ops-recovery-board-v1"
    assert recovery_payload["summary"]["hold_count"] == 1
    assert recovery_payload["items"][0]["lot_id"] == "lot-8812"
    assert recovery_payload["spotlight"]["maintenance_owner"] == "maint-etch-cell-a"
    assert recovery_payload["route_bundle"]["recovery_board_schema"] == "/api/fab-ops/recovery-board/schema"

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
    assert recovery_what_if_payload["route_bundle"]["recovery_what_if"] == "/api/fab-ops/recovery-what-if"

    assert recovery_board_schema.status_code == 200
    assert recovery_board_schema.json()["schema"] == "fab-ops-recovery-board-v1"

    assert review_pack.status_code == 200
    review_payload = review_pack.json()
    assert review_payload["readiness_contract"] == "fab-ops-review-pack-v1"
    assert "/api/fab-ops/runtime/scorecard" in review_payload["proof_bundle"]["review_routes"]
    assert "/api/fab-ops/review-summary" in review_payload["proof_bundle"]["review_routes"]
    assert "/api/fab-ops/recovery-board" in review_payload["proof_bundle"]["review_routes"]
    assert "/api/fab-ops/release-board" in review_payload["proof_bundle"]["review_routes"]
    assert "/api/fab-ops/recovery-what-if" in review_payload["proof_bundle"]["review_routes"]
    assert review_payload["proof_bundle"]["critical_alarm_count"] == 1
    assert review_payload["proof_bundle"]["hold_count"] == 1
    assert review_payload["proof_bundle"]["watch_count"] == 1
    assert review_payload["proof_bundle"]["ready_count"] == 1
    assert review_payload["proof_bundle"]["release_board_rows"] == 3
    assert "/api/fab-ops/review-pack" in review_payload["proof_bundle"]["review_routes"]
    assert review_payload["proof_bundle"]["latest_audit_events"] == 3
    assert review_payload["focus_lot"]["maintenance_owner"] == "maint-etch-cell-a"
    assert review_payload["focus_lot"]["review_path"][1] == "/api/fab-ops/recovery-board?mode=hold"
    assert isinstance(review_payload["operator_promises"], list)
    assert len(review_payload["two_minute_review"]) == 6
    assert review_payload["proof_assets"][0]["href"] == "/health"

    assert alarm_schema.status_code == 200
    assert alarm_schema.json()["schema"] == "fab-ops-alarm-report-v1"

    assert handoff_schema.status_code == 200
    assert handoff_schema.json()["schema"] == "fab-ops-shift-handoff-v1"

    assert audit_feed.status_code == 200
    assert audit_feed.json()["summary"]["events"] == 3


def test_fab_ops_core_domain_endpoints() -> None:
    client = TestClient(app)

    fabs = client.get("/api/fab-ops/fabs/summary")
    tools = client.get("/api/fab-ops/tools")
    ownership = client.get("/api/fab-ops/tool-ownership?tool_id=etch-14")
    alarms = client.get("/api/fab-ops/alarms")
    lots = client.get("/api/fab-ops/lots/at-risk")
    release_gate = client.get("/api/fab-ops/release-gate?lot_id=lot-8812")
    handoff = client.get("/api/fab-ops/shift-handoff")
    handoff_signature = client.get("/api/fab-ops/shift-handoff/signature")
    handoff_verify = client.get("/api/fab-ops/shift-handoff/verify")
    replay = client.get("/api/fab-ops/evals/replays")

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


def test_fab_ops_release_gate_relaxation_and_audit_feed() -> None:
    client = TestClient(app)

    watch_gate = client.get("/api/fab-ops/release-gate?lot_id=lot-8836")
    audit_feed = client.get("/api/fab-ops/audit/feed")

    assert watch_gate.status_code == 200
    watch_payload = watch_gate.json()["payload"]
    assert watch_payload["decision"] == "release-with-sampling"
    assert watch_payload["failed_checks"] == []

    assert audit_feed.status_code == 200
    audit_payload = audit_feed.json()["items"]
    assert audit_payload[0]["event"] == "handoff-preview-generated"
    assert audit_payload[0]["tool_id"] == "etch-14"


def test_fab_ops_review_summary_rejects_invalid_filters() -> None:
    client = TestClient(app)
    response = client.get("/api/fab-ops/review-summary?severity=urgent")
    assert response.status_code == 400
    assert "Invalid severity filter" in response.json()["detail"]


def test_fab_ops_recovery_board_rejects_invalid_filters() -> None:
    client = TestClient(app)
    response = client.get("/api/fab-ops/recovery-board?mode=escalate")
    assert response.status_code == 400
    assert "Invalid mode filter" in response.json()["detail"]


def test_fab_ops_sensitive_routes_require_operator_token_when_enabled(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("FAB_OPS_OPERATOR_TOKEN", "fab-secret")
    monkeypatch.setenv("FAB_OPS_OPERATOR_ALLOWED_ROLES", "shift-lead,release-supervisor")
    monkeypatch.setenv("FAB_OPS_RUNTIME_STORE_PATH", str(tmp_path / "fab-runtime.jsonl"))
    client = TestClient(app)

    unauthorized = client.get("/api/fab-ops/release-gate?lot_id=lot-8812")
    assert unauthorized.status_code == 401

    denied_role = client.get(
        "/api/fab-ops/release-gate?lot_id=lot-8812",
        headers={"x-operator-token": "fab-secret"},
    )
    assert denied_role.status_code == 403

    authorized = client.get(
        "/api/fab-ops/release-gate?lot_id=lot-8812",
        headers={
            "x-operator-token": "fab-secret",
            "x-operator-role": "shift-lead",
        },
    )
    assert authorized.status_code == 200

    handoff = client.get(
        "/api/fab-ops/shift-handoff",
        headers={"x-operator-token": "fab-secret", "x-operator-role": "shift-lead"},
    )
    assert handoff.status_code == 200

    signature = client.get(
        "/api/fab-ops/shift-handoff/signature",
        headers={
            "x-operator-token": "fab-secret",
            "x-operator-role": "shift-lead",
        },
    )
    assert signature.status_code == 200

    scorecard = client.get("/api/fab-ops/runtime/scorecard")
    assert scorecard.status_code == 200
    body = scorecard.json()
    assert body["runtime"]["operator_auth"]["enabled"] is True
    assert body["runtime"]["operator_auth"]["required_roles"] == [
        "shift-lead",
        "release-supervisor",
    ]
    assert body["runtime"]["persistence"]["event_count"] >= 3


# ---------------------------------------------------------------------------
# Scanner domain
# ---------------------------------------------------------------------------

def test_scanner_health_runtime_and_review_surfaces() -> None:
    client = TestClient(app)

    meta = client.get("/api/scanner/meta")
    brief = client.get("/api/scanner/runtime/brief")
    scorecard = client.get("/api/scanner/runtime/scorecard")
    review_pack = client.get("/api/scanner/review-pack")
    field_schema = client.get("/api/scanner/schema/field-incident")
    app_schema = client.get("/api/scanner/schema/application-qualification")

    assert meta.status_code == 200
    meta_payload = meta.json()
    assert meta_payload["runtime_contract"] == "scanner-runtime-brief-v1"
    assert meta_payload["review_pack_contract"] == "scanner-review-pack-v1"
    assert meta_payload["field_incident_contract"]["schema"] == "scanner-field-incident-v1"
    assert meta_payload["application_qualification_contract"]["schema"] == "scanner-qualification-record-v1"
    assert "/api/scanner/field-response-board" in meta_payload["routes"]
    assert "/api/scanner/subsystem-escalation" in meta_payload["routes"]
    assert "/api/scanner/qualification-board" in meta_payload["routes"]
    assert "/api/scanner/customer-readiness" in meta_payload["routes"]

    assert brief.status_code == 200
    brief_payload = brief.json()
    assert brief_payload["readiness_contract"] == "scanner-runtime-brief-v1"
    assert brief_payload["evidence_counts"]["incidents"] == 3
    assert brief_payload["evidence_counts"]["module_escalations"] == 2
    assert brief_payload["ops_snapshot"]["critical_incident_count"] == 1
    assert brief_payload["focus_incident"]["incident_id"] == "inc-3407"
    assert brief_payload["focus_incident"]["lot_id"] == "lot-n2-118"
    assert brief_payload["review_lanes"][0]["lane"] == "Field Response"
    assert brief_payload["review_lanes"][1]["lane"] == "Subsystem Escalation"
    assert brief_payload["review_lanes"][2]["lane"] == "Qualification Review"
    assert brief_payload["proof_assets"][-1]["href"] == "/api/scanner/shift-handoff/signature"

    assert scorecard.status_code == 200
    scorecard_payload = scorecard.json()
    assert scorecard_payload["readiness_contract"] == "scanner-runtime-scorecard-v1"
    assert scorecard_payload["summary"]["blocked_lots"] == 1
    assert scorecard_payload["summary"]["watch_lots"] == 1
    assert scorecard_payload["summary"]["ready_lots"] == 1
    assert scorecard_payload["runtime"]["persistence"]["enabled"] is True

    assert review_pack.status_code == 200
    review_payload = review_pack.json()
    assert review_payload["readiness_contract"] == "scanner-review-pack-v1"
    assert review_payload["focus_story"]["incident_id"] == "inc-3407"
    assert review_payload["focus_story"]["lot_id"] == "lot-n2-118"
    assert "/api/scanner/field-response-board" in review_payload["proof_bundle"]["review_routes"]
    assert "/api/scanner/subsystem-escalation?tool_id=scanner-euv-02" in review_payload["proof_bundle"]["review_routes"]
    assert "/api/scanner/qualification-board?lot_id=lot-n2-118" in review_payload["proof_bundle"]["review_routes"]
    assert "/api/scanner/customer-readiness?customer=alpha-mobile" in review_payload["proof_bundle"]["review_routes"]
    assert "/api/scanner/shift-handoff/signature" in review_payload["proof_bundle"]["review_routes"]

    assert field_schema.status_code == 200
    assert field_schema.json()["schema"] == "scanner-field-incident-v1"

    assert app_schema.status_code == 200
    assert app_schema.json()["schema"] == "scanner-qualification-record-v1"


def test_scanner_field_subsystem_qualification_and_customer_routes() -> None:
    client = TestClient(app)

    scanners = client.get("/api/scanner/scanners")
    incidents = client.get("/api/scanner/incidents?severity=critical")
    field_board = client.get("/api/scanner/field-response-board")
    subsystem_board = client.get("/api/scanner/subsystem-escalation?tool_id=scanner-euv-02")
    qualification_board = client.get("/api/scanner/qualification-board?lot_id=lot-n2-118")
    customer = client.get("/api/scanner/customer-readiness?customer=alpha-mobile")
    lot_risk = client.get("/api/scanner/lot-risk")

    assert scanners.status_code == 200
    assert len(scanners.json()["items"]) == 3
    assert any(item["status"] == "degraded" for item in scanners.json()["items"])

    assert incidents.status_code == 200
    incident_items = incidents.json()["items"]
    assert len(incident_items) == 1
    assert incident_items[0]["incident_id"] == "inc-3407"

    assert field_board.status_code == 200
    field_payload = field_board.json()
    assert field_payload["contract_version"] == "scanner-field-response-board-v1"
    assert field_payload["summary"]["incidents"] == 3
    assert field_payload["summary"]["qualification_blockers"] == 1
    assert field_payload["spotlight"]["owner"] == "field-hwaseong-b"
    assert field_payload["route_bundle"]["subsystem_escalation"] == "/api/scanner/subsystem-escalation?tool_id=scanner-euv-02"

    assert subsystem_board.status_code == 200
    subsystem_payload = subsystem_board.json()
    assert subsystem_payload["contract_version"] == "scanner-subsystem-escalation-v1"
    assert subsystem_payload["linked_incident"]["incident_id"] == "inc-3407"
    assert subsystem_payload["payload"]["owner"] == "subsystem-stage-dynamics"
    assert "stage vibration trace bundle" in subsystem_payload["payload"]["required_evidence"]
    assert "overlay delta returns under 2.0 nm on the replay wafer" in subsystem_payload["payload"]["restore_criteria"]

    assert qualification_board.status_code == 200
    qualification_payload = qualification_board.json()["payload"]
    assert qualification_payload["decision"] == "hold-qualification"
    assert qualification_payload["customer"] == "alpha-mobile"
    assert qualification_payload["deltas"]["overlay_over_target_nm"] == 1.4
    assert qualification_payload["route_bundle"]["customer_readiness"] == "/api/scanner/customer-readiness?customer=alpha-mobile"

    assert customer.status_code == 200
    customer_payload = customer.json()["payload"]
    assert customer_payload["status"] == "amber"
    assert customer_payload["program"] == "N2 mobile logic ramp"
    assert "overlay is still above the target band on lot-n2-118" in customer_payload["blocked_by"]

    assert lot_risk.status_code == 200
    risk_payload = lot_risk.json()
    assert risk_payload["contract_version"] == "scanner-lot-risk-board-v1"
    assert risk_payload["summary"]["blocked"] == 1
    assert risk_payload["items"][0]["lot_id"] == "lot-n2-118"
    assert risk_payload["items"][0]["risk_score"] > risk_payload["items"][-1]["risk_score"]


def test_scanner_shift_handoff_replay_and_validation_routes() -> None:
    client = TestClient(app)

    handoff = client.get("/api/scanner/shift-handoff")
    signature = client.get("/api/scanner/shift-handoff/signature")
    verify = client.get("/api/scanner/shift-handoff/verify")
    replay = client.get("/api/scanner/evals/replays")
    audit = client.get("/api/scanner/audit/feed")
    operator = client.get("/api/scanner/operator/runtime")

    assert handoff.status_code == 200
    handoff_payload = handoff.json()["payload"]
    assert handoff_payload["schema"] == "scanner-shift-handoff-v1"
    assert handoff_payload["handoff_id"] == "handoff-hwaseong-night"
    assert handoff_payload["focus_incident_id"] == "inc-3407"
    assert handoff_payload["review_path"][-1] == "/api/scanner/shift-handoff/signature"

    assert signature.status_code == 200
    signature_payload = signature.json()["payload"]
    assert signature_payload["signature_contract"] == "scanner-handoff-signature-v1"
    assert signature_payload["signature_id"] == "handoff-hwaseong-night"
    assert signature_payload["algorithm"] == "hmac-sha256"
    assert len(signature_payload["sha256"]) == 64
    assert len(signature_payload["signature"]) == 64

    assert verify.status_code == 200
    verify_payload = verify.json()["payload"]
    assert verify_payload["overall_valid"] is True
    assert verify_payload["checks"]["signature_match"] is True
    assert verify_payload["checks"]["digest_match"] is True

    assert replay.status_code == 200
    replay_payload = replay.json()
    assert replay_payload["summary"]["scenarios"] == 4
    assert replay_payload["summary"]["score_pct"] == 100.0

    assert audit.status_code == 200
    audit_payload = audit.json()
    assert audit_payload["summary"]["events"] == 4
    assert audit_payload["items"][0]["event"] == "qualification-hold-issued"

    assert operator.status_code == 200
    operator_payload = operator.json()
    assert operator_payload["service"] == "scanner-field-response"
    assert len(operator_payload["next_actions"]) == 3


def test_scanner_invalid_route_inputs_are_rejected() -> None:
    client = TestClient(app)

    bad_severity = client.get("/api/scanner/incidents?severity=urgent")
    bad_customer = client.get("/api/scanner/customer-readiness?customer=unknown")

    assert bad_severity.status_code == 400
    assert "Unsupported severity" in bad_severity.json()["detail"]

    assert bad_customer.status_code == 400
    assert "Unsupported customer" in bad_customer.json()["detail"]
