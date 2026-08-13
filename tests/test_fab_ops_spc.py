"""High-signal tests for synthetic SPC, flow, disposition, and replay evidence."""

from __future__ import annotations

import json
import math
from importlib import resources
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.domains.fab_ops import spc
from app.domains.fab_ops.spc import (
    build_control_plan,
    build_disposition_evaluation,
    build_fixture_excursion_review,
    evaluate_flow_indicators,
    evaluate_spc,
    execute_replay_suite,
    load_synthetic_scenario,
    scenario_sha256,
)
from app.main import app

ROOT = Path(__file__).resolve().parents[1]


def measurement(values: list[float], *, planned: int | None = None) -> dict[str, Any]:
    count = len(values)
    return {
        "name": "standardized_test",
        "unit": "sigma",
        "centerline": 0.0,
        "sigma": 1.0,
        "lsl": -10.0,
        "usl": 10.0,
        "sampling_plan": {
            "planned_wafer_averages": planned if planned is not None else count,
            "observed_wafer_averages": count,
            "sites_per_wafer": 1,
        },
        "observations": [
            {"sequence": index, "wafer_id": f"W{index:02d}", "value": value}
            for index, value in enumerate(values, start=1)
        ],
    }


@pytest.mark.parametrize(
    ("values", "expected", "expected_side"),
    [
        ([3.0], ["WECO-1"], "upper"),
        ([-3.0], ["WECO-1"], "lower"),
        ([2.0, 0.25, 2.0], ["WECO-2"], "upper"),
        ([-2.0, 0.25, -2.0], ["WECO-2"], "lower"),
        ([1.0, 1.0, 0.25, 1.0, 1.0], ["WECO-3"], "upper"),
        ([-1.0, -1.0, 0.25, -1.0, -1.0], ["WECO-3"], "lower"),
        ([0.1] * 8, ["WECO-4"], "upper"),
        ([-0.1] * 8, ["WECO-4"], "lower"),
    ],
)
def test_western_electric_boundaries_are_inclusive_except_centerline(
    values: list[float],
    expected: list[str],
    expected_side: str,
) -> None:
    result = evaluate_spc(measurement(values))
    assert result["unique_rule_ids"] == expected
    assert {signal["side"] for signal in result["signals"]} == {expected_side}
    assert result["data_quality"]["status"] == "pass"


def test_nonzero_decimal_reference_keeps_exact_three_sigma_boundary_inclusive() -> None:
    exact_boundary = measurement([0.6])
    exact_boundary.update({"centerline": 0.3, "sigma": 0.1})
    result = evaluate_spc(exact_boundary)

    assert result["observations"][0]["z_score"] == 3.0
    assert result["unique_rule_ids"] == ["WECO-1"]
    assert result["signals"][0]["side"] == "upper"

    materially_inside = measurement([0.599])
    materially_inside.update({"centerline": 0.3, "sigma": 0.1})
    assert evaluate_spc(materially_inside)["unique_rule_ids"] == []


def test_centerline_points_do_not_trigger_either_side_of_weco_4() -> None:
    result = evaluate_spc(measurement([0.0] * 8))
    assert result["signals"] == []
    assert result["process_state"] == "no_rule_violation_detected"


def test_centerline_point_breaks_an_eight_point_same_side_run() -> None:
    result = evaluate_spc(measurement([0.1, 0.2, 0.1, 0.0, 0.1, 0.2, 0.1, 0.2]))
    assert "WECO-4" not in result["unique_rule_ids"]


def test_opposite_side_zone_points_are_not_combined() -> None:
    assert evaluate_spc(measurement([2.0, -2.0, 0.0]))["unique_rule_ids"] == []
    assert evaluate_spc(measurement([1.0, -1.0, 1.0, -1.0, 0.0]))["unique_rule_ids"] == []


def test_overlapping_qualifying_windows_are_retained() -> None:
    result = evaluate_spc(measurement([2.1, 2.2, 2.3, 2.4]))
    rule_two = [signal for signal in result["signals"] if signal["rule_id"] == "WECO-2"]
    assert [signal["window_sequences"] for signal in rule_two] == [[1, 2, 3], [2, 3, 4]]


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("sigma", 0.0, "sigma must be greater than zero"),
        ("sigma", math.inf, "sigma must be finite"),
        ("lsl", 10.0, "lsl must be lower than usl"),
        ("centerline", 11.0, "centerline must fall inside"),
    ],
)
def test_invalid_reference_is_rejected(field: str, value: float, message: str) -> None:
    payload = measurement([0.0])
    payload[field] = value
    with pytest.raises(ValueError, match=message):
        evaluate_spc(payload)


def test_invalid_observation_structure_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least one"):
        evaluate_spc({**measurement([0.0]), "observations": []})

    duplicate = measurement([0.0, 0.1])
    duplicate["observations"][1]["sequence"] = 1
    with pytest.raises(ValueError, match="unique and increasing"):
        evaluate_spc(duplicate)

    nonfinite = measurement([0.0])
    nonfinite["observations"][0]["value"] = math.nan
    with pytest.raises(ValueError, match="must be finite"):
        evaluate_spc(nonfinite)

    boolean = measurement([0.0])
    boolean["observations"][0]["value"] = True
    with pytest.raises(ValueError, match="must be a number"):
        evaluate_spc(boolean)


def test_sampling_manifest_failures_are_visible_not_imputed() -> None:
    incomplete = measurement([0.1], planned=2)
    result = evaluate_spc(incomplete)
    assert result["data_quality"]["status"] == "fail"
    assert result["data_quality"]["checks"]["sampling_plan_complete"] is False
    assert result["sampling"]["completeness_pct"] == 50.0

    disposition = build_disposition_evaluation(
        lot_id="synthetic-incomplete",
        tool_id="tool-demo",
        operation="non-production check",
        measurement=incomplete,
        tool_status="healthy",
        evaluated_at="2026-03-08T08:15:00Z",
        lineage={"data_classification": "synthetic"},
    )
    assert disposition["gate"]["recommendation"] == "HOLD_FOR_CONTAINMENT"
    assert "MEASUREMENT_DATA_INCOMPLETE" in {
        blocker["code"] for blocker in disposition["gate"]["hard_blockers"]
    }


def test_duplicate_wafer_and_partial_timestamps_fail_data_quality() -> None:
    payload = measurement([0.0, 0.1])
    payload["observations"][1]["wafer_id"] = "W01"
    payload["observations"][0]["measured_at"] = "2026-03-08T08:00:00Z"
    result = evaluate_spc(payload)
    assert result["data_quality"]["status"] == "fail"
    assert result["data_quality"]["checks"]["wafer_ids_unique"] is False
    assert result["data_quality"]["checks"]["timestamps_all_or_none"] is False


def test_engineering_spec_excursion_blocks_without_being_called_yield() -> None:
    payload = measurement([0.0])
    payload["lsl"] = -0.5
    payload["usl"] = 0.5
    payload["observations"][0]["value"] = 0.75
    result = build_disposition_evaluation(
        lot_id="synthetic-oos",
        tool_id="tool-demo",
        operation="non-production check",
        measurement=payload,
        tool_status="healthy",
        evaluated_at="2026-03-08T08:15:00Z",
        lineage={"data_classification": "synthetic"},
    )
    assert result["spc"]["outside_spec_sequences"] == [1]
    assert result["evidence_boundary"]["measured_yield"] is False
    assert result["gate"]["material_state_changed"] is False


def test_fixture_flow_indicators_and_human_authority() -> None:
    result = build_fixture_excursion_review("lot-8812")
    flow = result["flow_indicators"]
    assert flow["q_time"] == {
        "status": "breached",
        "elapsed_minutes": 140.0,
        "limit_minutes": 120,
        "remaining_minutes": -20.0,
        "overrun_minutes": 20.0,
        "utilization_pct": 116.666666667,
    }
    assert flow["tat"]["status"] == "over_target"
    assert flow["routing"]["route_state"] == "hold"
    assert flow["routing"]["route_changed"] is False
    assert result["gate"]["human_release_authority_required"] is True
    assert result["gate"]["human_approval_status"] == "not_recorded"
    assert result["gate"]["material_state_changed"] is False
    assert result["evidence_boundary"]["classification_source"] == "packaged_fixture"


def test_q_time_limit_is_not_breached_until_elapsed_time_exceeds_limit() -> None:
    scenario = load_synthetic_scenario()
    flow = scenario["lots"]["lot-8836"]["flow_context"]
    at_limit = evaluate_flow_indicators(
        {
            **flow,
            "queue_entered_at": "2026-03-08T06:35:00Z",
            "q_time_limit_minutes": 100,
        },
        evaluated_at="2026-03-08T08:15:00Z",
    )
    just_over = evaluate_flow_indicators(
        {
            **flow,
            "queue_entered_at": "2026-03-08T06:34:59.900000Z",
            "q_time_limit_minutes": 100,
        },
        evaluated_at="2026-03-08T08:15:00Z",
    )
    one_microsecond_over = evaluate_flow_indicators(
        {
            **flow,
            "queue_entered_at": "2026-03-08T06:34:59.999999Z",
            "q_time_limit_minutes": 100,
        },
        evaluated_at="2026-03-08T08:15:00Z",
    )
    assert at_limit["q_time"]["status"] == "at_risk"
    assert at_limit["q_time"]["remaining_minutes"] == 0.0
    assert at_limit["q_time"]["overrun_minutes"] == 0.0
    assert just_over["q_time"]["status"] == "breached"
    assert just_over["q_time"]["elapsed_minutes"] == 100.001666667
    assert just_over["q_time"]["remaining_minutes"] == -0.001666667
    assert just_over["q_time"]["overrun_minutes"] == 0.001666667
    assert one_microsecond_over["q_time"]["status"] == "breached"
    assert one_microsecond_over["q_time"]["elapsed_minutes"] > 100
    assert one_microsecond_over["q_time"]["remaining_minutes"] < 0
    assert one_microsecond_over["q_time"]["overrun_minutes"] > 0

    disposition = build_disposition_evaluation(
        lot_id="q-time-boundary",
        tool_id="tool-demo",
        operation="non-production q-time check",
        measurement=measurement([0.0]),
        tool_status="healthy",
        evaluated_at="2026-03-08T08:15:00Z",
        lineage={"data_classification": "synthetic"},
        flow_context={
            **flow,
            "queue_entered_at": "2026-03-08T06:34:59.900000Z",
            "q_time_limit_minutes": 100,
        },
    )
    blocker = next(item for item in disposition["gate"]["hard_blockers"] if item["code"] == "Q_TIME_LIMIT_BREACHED")
    assert blocker["evidence"] == "Synthetic q-time exceeds its limit by 0.001666667 minutes."
    assert disposition["gate"]["recommendation"] == "HOLD_FOR_CONTAINMENT"


def test_invalid_flow_time_and_route_fail_validation() -> None:
    scenario = load_synthetic_scenario()
    flow = scenario["lots"]["lot-8812"]["flow_context"]
    with pytest.raises(ValueError, match="cannot be after"):
        evaluate_flow_indicators(
            {**flow, "queue_entered_at": "2026-03-08T09:00:00Z"},
            evaluated_at="2026-03-08T08:15:00Z",
        )
    with pytest.raises(ValueError, match="route_state must be one of"):
        evaluate_flow_indicators(
            {**flow, "route_state": "auto_release"},
            evaluated_at="2026-03-08T08:15:00Z",
        )
    with pytest.raises(ValueError, match="cannot be before lot_started_at"):
        evaluate_flow_indicators(
            {**flow, "queue_entered_at": "2026-03-07T16:00:00Z"},
            evaluated_at="2026-03-08T08:15:00Z",
        )


def test_packaged_fixture_lineage_and_copy_isolation() -> None:
    first = load_synthetic_scenario()
    first["dataset_id"] = "mutated"
    second = load_synthetic_scenario()
    assert second["dataset_id"] != "mutated"

    fixture_resource = resources.files("app.domains.fab_ops").joinpath("fixtures", "synthetic_shift.json")
    fixture_bytes = fixture_resource.read_bytes()
    assert json.loads(fixture_bytes)["synthetic"] is True
    assert len(scenario_sha256()) == 64

    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"app.domains.fab_ops" = ["fixtures/*.json"]' in pyproject
    assert '"app" = ["static/*.html", "static/*.js", "static/*.css"]' in pyproject
    assert "include-package-data = true" in pyproject


def test_control_plan_is_versioned_and_truthfully_labeled() -> None:
    plan = build_control_plan()
    assert plan["api_version"] == "v1"
    assert plan["contract_version"] == "fab-ops-control-plan-v1"
    assert plan["dataset"]["data_classification"] == "synthetic_fixture"
    assert plan["dataset"]["measured_fab_data"] is False
    assert plan["authority_boundary"]["human_release_authority_required"] is True
    assert plan["routes"]["executed_replays"] == "/api/fab-ops/v1/evals/replays"


def test_executed_replays_assert_expected_against_actual() -> None:
    replay = execute_replay_suite()
    assert replay["status"] == "pass"
    assert replay["summary"] == {
        "scenarios": 9,
        "total_assertions": 54,
        "passed_assertions": 54,
        "failed_assertions": 0,
        "score_pct": 100.0,
    }
    assert all(run["status"] == "pass" for run in replay["runs"])
    assert all(assertion["passed"] for run in replay["runs"] for assertion in run["assertions"])
    centerline = next(run for run in replay["runs"] if run["case_id"] == "centerline-does-not-pick-a-side")
    assert centerline["actual"]["unique_rule_ids"] == []


def test_executed_replay_aggregate_turns_red_on_actual_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    original = spc.evaluate_spc

    def mismatching_evaluator(payload: dict[str, Any]) -> dict[str, Any]:
        result = original(payload)
        if payload.get("name") == "centerline-does-not-pick-a-side":
            result["unique_rule_ids"] = ["REGRESSION"]
        return result

    monkeypatch.setattr(spc, "evaluate_spc", mismatching_evaluator)
    replay = execute_replay_suite()
    assert replay["status"] == "fail"
    assert replay["summary"]["failed_assertions"] == 1
    failed_run = next(run for run in replay["runs"] if run["status"] == "fail")
    assert failed_run["assertions"][0]["passed"] is False


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def test_openapi_exposes_versioned_spc_contracts(client: TestClient) -> None:
    document = client.get("/openapi.json").json()
    assert "get" in document["paths"]["/api/fab-ops/v1/control-plan"]
    assert "get" in document["paths"]["/api/fab-ops/v1/lots/{lot_id}/disposition"]
    assert "post" in document["paths"]["/api/fab-ops/v1/disposition/evaluate"]
    assert "get" in document["paths"]["/api/fab-ops/v1/evals/replays"]
    assert "post" in document["paths"]["/api/fab-ops/shift-handoff/verify"]
    verify_schema = document["paths"]["/api/fab-ops/shift-handoff/verify"]["post"]["requestBody"]
    assert verify_schema["required"] is True
    request_schema = document["paths"]["/api/fab-ops/v1/disposition/evaluate"]["post"]["requestBody"]
    assert request_schema["required"] is True


def test_versioned_api_control_disposition_and_replays(client: TestClient) -> None:
    plan = client.get("/api/fab-ops/v1/control-plan")
    disposition = client.get("/api/fab-ops/v1/lots/lot-8812/disposition")
    replay = client.get("/api/fab-ops/v1/evals/replays")
    assert plan.status_code == disposition.status_code == replay.status_code == 200
    assert disposition.json()["gate"]["recommendation"] == "HOLD_FOR_CONTAINMENT"
    assert disposition.json()["flow_indicators"]["q_time"]["status"] == "breached"
    assert replay.json()["summary"]["failed_assertions"] == 0
    assert replay.json()["runs"][0]["assertions"][0]["actual"] == "HOLD_FOR_CONTAINMENT"


def test_unknown_fixture_lot_returns_404(client: TestClient) -> None:
    response = client.get("/api/fab-ops/v1/lots/not-a-lot/disposition")
    assert response.status_code == 404
    assert "Unknown synthetic fixture lot" in response.json()["detail"]


def ad_hoc_payload() -> dict[str, Any]:
    return {
        "lot_id": "synthetic-caller-lot",
        "tool_id": "tool-demo-1",
        "operation": "non-production inline check",
        "measurement_name": "cd_bias",
        "unit": "nm",
        "centerline": 0.0,
        "sigma": 1.0,
        "lsl": -10.0,
        "usl": 10.0,
        "values": [-0.1, 0.1],
        "planned_wafer_averages": 2,
        "sites_per_wafer": 3,
        "tool_status": "healthy",
        "data_classification": "synthetic",
    }


def test_post_non_production_evaluation_executes_and_hashes_request(client: TestClient) -> None:
    response = client.post("/api/fab-ops/v1/disposition/evaluate", json=ad_hoc_payload())
    assert response.status_code == 200
    body = response.json()
    assert body["gate"]["recommendation"] == "ENGINEERING_REVIEW"
    assert {item["code"] for item in body["gate"]["review_flags"]} == {"FLOW_CONTEXT_MISSING"}
    assert body["flow_indicators"]["status"] == "unavailable"
    assert body["gate"]["human_approval_status"] == "not_recorded"
    assert body["gate"]["material_state_changed"] is False
    assert len(body["lineage"]["request_sha256"]) == 64
    assert body["evidence_boundary"]["measured_yield"] is False
    assert body["evidence_boundary"]["classification_source"] == "caller_asserted"
    assert body["evidence_boundary"]["classification_verified_against_source_system"] is False


def test_post_evaluation_accepts_valid_synthetic_flow_context(client: TestClient) -> None:
    payload = ad_hoc_payload()
    scenario = load_synthetic_scenario()
    payload["evaluated_at"] = scenario["as_of"]
    payload["flow_context"] = scenario["lots"]["lot-8836"]["flow_context"]
    response = client.post("/api/fab-ops/v1/disposition/evaluate", json=payload)
    assert response.status_code == 200
    body = response.json()
    flow = body["flow_indicators"]
    assert body["gate"]["recommendation"] == "RELEASE_WITH_SAMPLING"
    assert flow["q_time"]["status"] == "within_window"
    assert flow["tat"]["status"] == "within_target"
    assert flow["routing"]["route_state"] == "ready_for_reviewed_dispatch"
    assert flow["routing"]["route_changed"] is False


def test_post_evaluation_rejects_invalid_flow_context(client: TestClient) -> None:
    payload = ad_hoc_payload()
    scenario = load_synthetic_scenario()
    flow = scenario["lots"]["lot-8836"]["flow_context"]
    payload["evaluated_at"] = scenario["as_of"]
    payload["flow_context"] = {**flow, "next_step": flow["current_step"]}
    response = client.post("/api/fab-ops/v1/disposition/evaluate", json=payload)
    assert response.status_code == 422
    assert "next_step must be greater than current_step" in response.text


def test_post_evaluation_executes_western_electric_signal(client: TestClient) -> None:
    payload = ad_hoc_payload()
    payload["values"] = [-0.2, 0.2, 3.0]
    payload["planned_wafer_averages"] = 3
    response = client.post("/api/fab-ops/v1/disposition/evaluate", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["spc"]["unique_rule_ids"] == ["WECO-1"]
    assert body["gate"]["recommendation"] == "HOLD_FOR_CONTAINMENT"
    assert "SPC_SPECIAL_CAUSE" in {
        blocker["code"] for blocker in body["gate"]["hard_blockers"]
    }


def test_post_incomplete_plan_fails_closed(client: TestClient) -> None:
    payload = ad_hoc_payload()
    payload["values"] = [0.1]
    response = client.post("/api/fab-ops/v1/disposition/evaluate", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["gate"]["recommendation"] == "HOLD_FOR_CONTAINMENT"
    assert body["spc"]["data_quality"]["status"] == "fail"


@pytest.mark.parametrize(
    ("mutation", "expected_fragment"),
    [
        ({"data_classification": "production"}, "Input should be"),
        ({"sigma": 0}, "greater than 0"),
        ({"unexpected": True}, "Extra inputs are not permitted"),
        ({"centerline": True}, "Input should be a valid number"),
        ({"values": [True]}, "Input should be a valid number"),
        ({"planned_wafer_averages": True}, "Input should be a valid integer"),
        ({"lsl": 5.0, "usl": -5.0}, "lsl must be lower than usl"),
    ],
)
def test_post_contract_rejects_unsafe_or_malformed_input(
    client: TestClient,
    mutation: dict[str, Any],
    expected_fragment: str,
) -> None:
    payload = {**ad_hoc_payload(), **mutation}
    response = client.post("/api/fab-ops/v1/disposition/evaluate", json=payload)
    assert response.status_code == 422
    assert expected_fragment in response.text


def test_sensitive_spc_routes_fail_closed_outside_demo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEMICONDUCTOR_OPS_MODE", "production")
    monkeypatch.delenv("FAB_OPS_OPERATOR_TOKEN", raising=False)
    client = TestClient(app)
    assert client.get("/api/fab-ops/v1/control-plan").status_code == 200
    assert client.get("/api/fab-ops/v1/lots/lot-8812/disposition").status_code == 503
    assert client.post("/api/fab-ops/v1/disposition/evaluate", json=ad_hoc_payload()).status_code == 503
    assert client.get("/api/fab-ops/shift-handoff/signature").status_code == 503
    assert client.get("/api/fab-ops/audit/feed").status_code == 503


def test_signing_key_is_required_in_non_demo_even_with_operator_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SEMICONDUCTOR_OPS_MODE", "production")
    monkeypatch.setenv("FAB_OPS_OPERATOR_TOKEN", "operator-secret")
    monkeypatch.delenv("FAB_OPS_OPERATOR_ALLOWED_ROLES", raising=False)
    monkeypatch.delenv("FAB_OPS_HANDOFF_SIGNING_KEY", raising=False)
    monkeypatch.setenv("FAB_OPS_HANDOFF_SIGNING_KEY_ID", "prod-v1")
    client = TestClient(app)
    response = client.get(
        "/api/fab-ops/shift-handoff/signature",
        headers={"x-operator-token": "operator-secret"},
    )
    assert response.status_code == 503
    assert response.json()["detail"]["fail_closed"] is True


def test_unset_runtime_mode_is_locked_not_implicit_demo(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SEMICONDUCTOR_OPS_MODE", raising=False)
    monkeypatch.delenv("FAB_OPS_OPERATOR_TOKEN", raising=False)
    client = TestClient(app)
    response = client.get("/api/fab-ops/v1/lots/lot-8812/disposition")
    assert response.status_code == 503
    assert response.json()["detail"]["runtime_mode"] == "locked"


def test_signature_verification_requires_complete_caller_manifest_and_envelope() -> None:
    client = TestClient(app)
    assert client.get("/api/fab-ops/shift-handoff/verify").status_code == 405
    envelope = client.get("/api/fab-ops/shift-handoff/signature").json()["payload"]

    invalid_signature = {**envelope, "signature": "0" * 64}
    response = client.post("/api/fab-ops/shift-handoff/verify", json=invalid_signature)
    assert response.status_code == 200
    body = response.json()["payload"]
    assert body["overall_valid"] is False
    assert body["checks"]["signature_match"] is False
    assert body["human_approval_verified"] is False

    tampered_manifest = json.loads(json.dumps(envelope))
    tampered_manifest["manifest"]["headline"] = "tampered after signing"
    tampered = client.post("/api/fab-ops/shift-handoff/verify", json=tampered_manifest)
    assert tampered.status_code == 200
    assert tampered.json()["payload"]["overall_valid"] is False
    assert tampered.json()["payload"]["checks"]["sha256_match"] is False

    tampered_lineage = json.loads(json.dumps(envelope))
    tampered_lineage["manifest"]["spc_evidence_binding"]["fixture_sha256"] = "0" * 64
    lineage = client.post("/api/fab-ops/shift-handoff/verify", json={"payload": tampered_lineage})
    assert lineage.status_code == 200
    assert lineage.json()["payload"]["overall_valid"] is False
    assert lineage.json()["payload"]["checks"]["signature_match"] is False

    valid = client.post("/api/fab-ops/shift-handoff/verify", json=envelope)
    assert valid.status_code == 200
    assert valid.json()["payload"]["overall_valid"] is True


@pytest.mark.parametrize(
    ("field", "tampered_value", "failed_check"),
    [
        ("digest_preview", "0" * 16, "digest_preview_matches_sha256"),
        ("generated_by", "tampered-generator", "generated_by_match"),
        ("artifact_channel", "tampered-channel", "artifact_channel_match"),
        ("signature_purpose", "tampered purpose", "signature_purpose_match"),
        ("human_approval_status", "approved", "outer_human_approval_status_match"),
        ("human_release_authority_required", False, "outer_human_release_authority_match"),
        ("verification_method", "GET", "verification_method_match"),
        ("verification_route", "/tampered", "verification_route_match"),
        ("verification_steps", ["tampered", "steps", "only"], "verification_steps_match"),
    ],
)
def test_post_verifier_rejects_every_tampered_outer_envelope_field(
    field: str,
    tampered_value: Any,
    failed_check: str,
) -> None:
    client = TestClient(app)
    envelope = client.get("/api/fab-ops/shift-handoff/signature").json()["payload"]
    envelope[field] = tampered_value

    response = client.post("/api/fab-ops/shift-handoff/verify", json=envelope)
    assert response.status_code == 200
    verification = response.json()["payload"]
    assert verification["overall_valid"] is False
    assert verification["checks"][failed_check] is False


def test_post_verifier_rejects_unknown_outer_envelope_fields() -> None:
    client = TestClient(app)
    envelope = client.get("/api/fab-ops/shift-handoff/signature").json()["payload"]
    envelope["authority"] = "fabricated"

    response = client.post("/api/fab-ops/shift-handoff/verify", json=envelope)
    assert response.status_code == 422
    assert "Extra inputs are not permitted" in response.text


def test_fully_configured_non_demo_auth_and_signing_work(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("SEMICONDUCTOR_OPS_MODE", "production")
    monkeypatch.setenv("FAB_OPS_OPERATOR_TOKEN", "operator-secret")
    monkeypatch.setenv("FAB_OPS_OPERATOR_ALLOWED_ROLES", "release-supervisor")
    monkeypatch.setenv("FAB_OPS_HANDOFF_SIGNING_KEY", "configured-production-test-key")
    monkeypatch.setenv("FAB_OPS_HANDOFF_SIGNING_KEY_ID", "prod-test-v1")
    monkeypatch.setenv("FAB_OPS_RUNTIME_STORE_PATH", str(tmp_path / "events.jsonl"))
    headers = {
        "x-operator-token": "operator-secret",
        "x-operator-role": "release-supervisor",
    }
    client = TestClient(app)
    disposition = client.get(
        "/api/fab-ops/v1/lots/lot-8812/disposition",
        headers=headers,
    )
    signature_response = client.get("/api/fab-ops/shift-handoff/signature", headers=headers)
    assert disposition.status_code == signature_response.status_code == 200
    envelope = signature_response.json()["payload"]
    assert envelope["key_id"] == "prod-test-v1"
    verify = client.post(
        "/api/fab-ops/shift-handoff/verify",
        headers=headers,
        json=envelope,
    )
    assert verify.status_code == 200
    assert verify.json()["payload"]["overall_valid"] is True


def test_legacy_risk_and_trend_surfaces_are_explicitly_synthetic() -> None:
    client = TestClient(app)
    lots = client.get("/api/fab-ops/lots/at-risk").json()
    trend = client.get("/api/fab-ops/yield-trend").json()
    assert lots["evidence_boundary"]["measured_yield"] is False
    assert "yield_risk_score" not in lots["items"][0]
    assert lots["items"][0]["risk_basis"].endswith("not measured yield")
    assert trend["data_classification"] == "synthetic_fixture"
    assert trend["measured_yield"] is False
    assert "simulated_yield_fraction" in trend["items"][0]["shifts"][0]


def test_unknown_alarm_acknowledgement_is_a_real_404() -> None:
    response = TestClient(app).post("/api/fab-ops/alarms/not-an-alarm/acknowledge")
    assert response.status_code == 404
    assert "Unknown synthetic fixture alarm" in response.json()["detail"]
