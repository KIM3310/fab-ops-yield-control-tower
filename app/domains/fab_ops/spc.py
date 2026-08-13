"""Deterministic SPC and advisory lot disposition for the synthetic fab demo.

The module evaluates caller-supplied or packaged non-production series against a
configured qualified reference. It never estimates control limits from the short
fixture, predicts yield, changes a route, or authorizes material release.
"""

from __future__ import annotations

import hashlib
import json
import math
from copy import deepcopy
from datetime import UTC, datetime
from functools import lru_cache
from importlib import resources
from typing import Any

SERVICE_NAME = "fab-ops-yield-control-tower"
DISPOSITION_CONTRACT = "fab-ops-spc-disposition-v1"
CONTROL_PLAN_CONTRACT = "fab-ops-control-plan-v1"
REPLAY_CONTRACT = "fab-ops-executed-replays-v1"
CONTROL_PLAN_ROUTE = "/api/fab-ops/v1/control-plan"
METHODOLOGY_PATH = "docs/fab-yield-methodology.md"
_FIXTURE_PARTS = ("fixtures", "synthetic_shift.json")
_ALLOWED_TOOL_STATES = {"healthy", "warning", "alarm"}
_ALLOWED_ALARM_SEVERITIES = {"none", "low", "medium", "high", "critical"}
_ALLOWED_ROUTE_STATES = {
    "in_queue",
    "hold",
    "awaiting_engineering_review",
    "ready_for_reviewed_dispatch",
    "in_process",
    "complete",
}


def _fixture_bytes() -> bytes:
    resource = resources.files("app.domains.fab_ops")
    for part in _FIXTURE_PARTS:
        resource = resource.joinpath(part)
    return resource.read_bytes()


def _require_finite_number(value: Any, field: str) -> float:
    """Return *value* as a finite float or raise a domain validation error."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{field} must be finite")
    return number


def _at_or_beyond(value: float, boundary: float) -> bool:
    """Compare an inclusive sigma boundary without binary-float false negatives.

    Decimal references such as centerline ``0.3`` and sigma ``0.1`` can produce
    a normalized value of ``2.9999999999999996`` for an exact +3-sigma point.
    The tight tolerance only absorbs representation noise; it does not turn a
    materially sub-boundary observation into a signal.
    """
    return value > boundary or math.isclose(value, boundary, rel_tol=1e-12, abs_tol=1e-12)


def _at_or_beyond_lower(value: float, boundary: float) -> bool:
    """Lower-side counterpart to :func:`_at_or_beyond`."""
    return value < boundary or math.isclose(value, boundary, rel_tol=1e-12, abs_tol=1e-12)


def _format_minutes(value: float) -> str:
    """Render microsecond-resolution minutes without trailing zeros."""
    rendered = f"{value:.9f}".rstrip("0").rstrip(".")
    return rendered or "0"


def _require_positive_int(value: Any, field: str, *, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{field} must be a positive integer")
    if value > maximum:
        raise ValueError(f"{field} cannot exceed {maximum}")
    return int(value)


def _parse_timestamp(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be an ISO-8601 timestamp")
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must include a timezone")
    return parsed.astimezone(UTC)


@lru_cache(maxsize=1)
def _cached_scenario() -> dict[str, Any]:
    payload = json.loads(_fixture_bytes().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("synthetic scenario root must be an object")
    return payload


def load_synthetic_scenario() -> dict[str, Any]:
    """Load an isolated copy of the packaged deterministic demo fixture."""
    return deepcopy(_cached_scenario())


def scenario_sha256() -> str:
    """Return the SHA-256 of the exact packaged fixture bytes."""
    return hashlib.sha256(_fixture_bytes()).hexdigest()


def _same_side_signal(
    z_scores: list[float],
    sequences: list[int],
    *,
    window_size: int,
    required_count: int,
    threshold: float,
    rule_id: str,
    name: str,
    severity: str,
) -> list[dict[str, Any]]:
    """Detect same-side rolling-window rules and retain qualifying overlaps.

    Zone boundaries for WECO-2 and WECO-3 are inclusive. A zero threshold is
    special: WECO-4 requires points to be strictly on one side, so a point
    exactly on the centerline belongs to neither side.
    """
    signals: list[dict[str, Any]] = []
    if len(z_scores) < window_size:
        return signals

    for end in range(window_size, len(z_scores) + 1):
        start = end - window_size
        window = z_scores[start:end]
        window_sequences = sequences[start:end]
        if threshold == 0.0:
            side_positions = {
                "upper": [index for index, value in enumerate(window) if value > 0.0],
                "lower": [index for index, value in enumerate(window) if value < 0.0],
            }
        else:
            side_positions = {
                "upper": [index for index, value in enumerate(window) if _at_or_beyond(value, threshold)],
                "lower": [index for index, value in enumerate(window) if _at_or_beyond_lower(value, -threshold)],
            }

        for side, trigger_positions in side_positions.items():
            if len(trigger_positions) < required_count:
                continue
            boundary_word = "strictly" if threshold == 0.0 else "at or beyond"
            signals.append(
                {
                    "rule_id": rule_id,
                    "name": name,
                    "severity": severity,
                    "side": side,
                    "window_sequences": window_sequences,
                    "trigger_sequences": [window_sequences[index] for index in trigger_positions],
                    "evidence": (
                        f"{len(trigger_positions)} of {window_size} points {boundary_word} "
                        f"{threshold:g} sigma on the {side} side"
                    ),
                }
            )
    return signals


def evaluate_spc(measurement: dict[str, Any]) -> dict[str, Any]:
    """Evaluate a sequential series with the four Western Electric zone rules.

    ``sigma`` is a previously qualified reference constant. It is never
    estimated from the short series under evaluation.
    """
    if not isinstance(measurement, dict):
        raise ValueError("measurement must be an object")
    centerline = _require_finite_number(measurement.get("centerline"), "centerline")
    sigma = _require_finite_number(measurement.get("sigma"), "sigma")
    lsl = _require_finite_number(measurement.get("lsl"), "lsl")
    usl = _require_finite_number(measurement.get("usl"), "usl")
    if sigma <= 0:
        raise ValueError("sigma must be greater than zero")
    if lsl >= usl:
        raise ValueError("lsl must be lower than usl")
    if not lsl <= centerline <= usl:
        raise ValueError("centerline must fall inside the engineering specification limits")

    raw_observations = measurement.get("observations")
    if not isinstance(raw_observations, list) or not raw_observations:
        raise ValueError("observations must contain at least one item")
    if len(raw_observations) > 200:
        raise ValueError("observations cannot exceed 200 items")

    observations: list[dict[str, Any]] = []
    sequences: list[int] = []
    values: list[float] = []
    wafer_ids: list[str] = []
    measured_times: list[datetime] = []
    timestamp_count = 0
    for index, item in enumerate(raw_observations):
        if not isinstance(item, dict):
            raise ValueError(f"observations[{index}] must be an object")
        sequence = item.get("sequence")
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
            raise ValueError(f"observations[{index}].sequence must be a positive integer")
        value = _require_finite_number(item.get("value"), f"observations[{index}].value")
        raw_wafer_id = item.get("wafer_id", f"W{sequence:02d}")
        if not isinstance(raw_wafer_id, str) or not raw_wafer_id.strip():
            raise ValueError(f"observations[{index}].wafer_id must be a non-empty string")
        wafer_id = raw_wafer_id.strip()
        measured_at = item.get("measured_at")
        if measured_at is not None:
            measured_times.append(_parse_timestamp(measured_at, f"observations[{index}].measured_at"))
            timestamp_count += 1

        sequences.append(sequence)
        values.append(value)
        wafer_ids.append(wafer_id)
        observations.append(
            {
                "sequence": sequence,
                "wafer_id": wafer_id,
                "measured_at": measured_at,
                "value": value,
                "z_score": round((value - centerline) / sigma, 3),
                "inside_engineering_spec": lsl <= value <= usl,
            }
        )

    if sequences != sorted(sequences) or len(sequences) != len(set(sequences)):
        raise ValueError("observation sequences must be unique and increasing")

    sampling_plan = measurement.get("sampling_plan")
    if not isinstance(sampling_plan, dict):
        raise ValueError("sampling_plan must be an object")
    planned = _require_positive_int(
        sampling_plan.get("planned_wafer_averages"),
        "planned_wafer_averages",
        maximum=200,
    )
    observed_manifest = sampling_plan.get("observed_wafer_averages")
    if isinstance(observed_manifest, bool) or not isinstance(observed_manifest, int) or observed_manifest < 0:
        raise ValueError("observed_wafer_averages must be a non-negative integer")
    if observed_manifest > 200:
        raise ValueError("observed_wafer_averages cannot exceed 200")
    sites_per_wafer = _require_positive_int(
        sampling_plan.get("sites_per_wafer"),
        "sites_per_wafer",
        maximum=1000,
    )

    actual_count = len(observations)
    completeness = min(actual_count / planned, 1.0)
    z_scores = [(value - centerline) / sigma for value in values]
    signals: list[dict[str, Any]] = []

    for index, z_score in enumerate(z_scores):
        if _at_or_beyond(abs(z_score), 3.0):
            side = "upper" if z_score > 0 else "lower"
            signals.append(
                {
                    "rule_id": "WECO-1",
                    "name": "one point at or beyond three sigma",
                    "severity": "critical",
                    "side": side,
                    "window_sequences": [sequences[index]],
                    "trigger_sequences": [sequences[index]],
                    "evidence": f"point {sequences[index]} is {abs(z_score):.3f} sigma from centerline",
                }
            )

    signals.extend(
        _same_side_signal(
            z_scores,
            sequences,
            window_size=3,
            required_count=2,
            threshold=2.0,
            rule_id="WECO-2",
            name="two of three at or beyond two sigma",
            severity="major",
        )
    )
    signals.extend(
        _same_side_signal(
            z_scores,
            sequences,
            window_size=5,
            required_count=4,
            threshold=1.0,
            rule_id="WECO-3",
            name="four of five at or beyond one sigma",
            severity="major",
        )
    )
    signals.extend(
        _same_side_signal(
            z_scores,
            sequences,
            window_size=8,
            required_count=8,
            threshold=0.0,
            rule_id="WECO-4",
            name="eight consecutive points strictly on one side",
            severity="major",
        )
    )

    timestamps_consistent = timestamp_count in {0, actual_count}
    timestamps_increasing = timestamps_consistent and measured_times == sorted(measured_times)
    integrity_checks = {
        "observation_count_matches_manifest": observed_manifest == actual_count,
        "observation_count_within_plan": actual_count <= planned,
        "sampling_plan_complete": actual_count >= planned,
        "sequence_unique_and_increasing": True,
        "wafer_ids_unique": len(wafer_ids) == len(set(wafer_ids)),
        "timestamps_all_or_none": timestamps_consistent,
        "timestamps_non_decreasing": timestamps_increasing,
        "finite_numeric_values": True,
        "reference_sigma_positive": True,
        "specification_order_valid": True,
        "centerline_inside_specification": True,
    }
    outside_spec_sequences = [item["sequence"] for item in observations if not item["inside_engineering_spec"]]
    cp = (usl - lsl) / (6.0 * sigma)
    cpk = min((usl - centerline) / (3.0 * sigma), (centerline - lsl) / (3.0 * sigma))

    return {
        "measurement_name": str(measurement.get("name", "unnamed_measurement")),
        "unit": str(measurement.get("unit", "unknown")),
        "reference": {
            "centerline": centerline,
            "sigma": sigma,
            "lcl_3sigma": round(centerline - 3.0 * sigma, 6),
            "ucl_3sigma": round(centerline + 3.0 * sigma, 6),
            "lsl": lsl,
            "usl": usl,
        },
        "sampling": {
            "planned_wafer_averages": planned,
            "declared_observed_wafer_averages": observed_manifest,
            "actual_observation_count": actual_count,
            "sites_per_wafer": sites_per_wafer,
            "completeness_pct": round(completeness * 100.0, 1),
        },
        "data_quality": {
            "status": "pass" if all(integrity_checks.values()) else "fail",
            "checks": integrity_checks,
        },
        "process_state": "special_cause_detected" if signals else "no_rule_violation_detected",
        "observations": observations,
        "signals": signals,
        "unique_rule_ids": sorted({str(signal["rule_id"]) for signal in signals}),
        "outside_spec_sequences": outside_spec_sequences,
        "reference_capability": {
            "cp": round(cp, 3),
            "cpk": round(cpk, 3),
            "basis": "configured synthetic qualified-reference constants",
            "caveat": "Informational only; not estimated from this short run and not a measured or predicted lot yield.",
        },
        "calculation_boundary": {
            "deterministic": True,
            "model_inference_used": False,
            "control_limits_estimated_from_series": False,
            "measured_yield": False,
        },
    }


def evaluate_flow_indicators(flow_context: dict[str, Any] | None, *, evaluated_at: str) -> dict[str, Any]:
    """Calculate deterministic q-time, TAT, and routing indicators when supplied."""
    if flow_context is None:
        return {
            "supported": False,
            "status": "unavailable",
            "reason": "No synthetic flow context was supplied; route, q-time, and TAT evidence are unknown.",
            "data_classification": "non-production",
            "authoritative_source_verified": False,
            "required_for_release_recommendation": True,
        }
    if not isinstance(flow_context, dict):
        raise ValueError("flow_context must be an object")

    as_of = _parse_timestamp(evaluated_at, "evaluated_at")
    queue_entered = _parse_timestamp(flow_context.get("queue_entered_at"), "flow_context.queue_entered_at")
    lot_started = _parse_timestamp(flow_context.get("lot_started_at"), "flow_context.lot_started_at")
    if queue_entered > as_of:
        raise ValueError("flow_context.queue_entered_at cannot be after evaluated_at")
    if lot_started > as_of:
        raise ValueError("flow_context.lot_started_at cannot be after evaluated_at")
    if queue_entered < lot_started:
        raise ValueError("flow_context.queue_entered_at cannot be before lot_started_at")

    q_limit = _require_positive_int(
        flow_context.get("q_time_limit_minutes"),
        "flow_context.q_time_limit_minutes",
        maximum=100_000,
    )
    tat_target = _require_positive_int(
        flow_context.get("tat_target_minutes"),
        "flow_context.tat_target_minutes",
        maximum=1_000_000,
    )
    current_step = _require_positive_int(flow_context.get("current_step"), "flow_context.current_step", maximum=1_000_000)
    next_step = _require_positive_int(flow_context.get("next_step"), "flow_context.next_step", maximum=1_000_000)
    if next_step <= current_step:
        raise ValueError("flow_context.next_step must be greater than current_step")

    route_state = flow_context.get("route_state")
    if route_state not in _ALLOWED_ROUTE_STATES:
        allowed = ", ".join(sorted(_ALLOWED_ROUTE_STATES))
        raise ValueError(f"flow_context.route_state must be one of: {allowed}")
    for field in ("route_id", "current_operation", "next_operation"):
        value = flow_context.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"flow_context.{field} must be a non-empty string")

    q_elapsed_raw = (as_of - queue_entered).total_seconds() / 60.0
    tat_elapsed_raw = (as_of - lot_started).total_seconds() / 60.0
    if q_elapsed_raw > q_limit:
        q_status = "breached"
    elif q_elapsed_raw >= q_limit * 0.8:
        q_status = "at_risk"
    else:
        q_status = "within_window"
    tat_status = "over_target" if tat_elapsed_raw > tat_target else "within_target"

    # Nine decimal minutes preserve Python datetime's microsecond resolution.
    # Classification, remaining time, and overrun all derive from the same raw
    # duration, so any representable just-over-boundary breach remains visibly
    # positive instead of displaying 100.0 / 100 with -0.0 evidence.
    duration_precision = 9
    q_elapsed = round(q_elapsed_raw, duration_precision)
    q_remaining = round(q_limit - q_elapsed_raw, duration_precision)
    q_overrun = round(max(q_elapsed_raw - q_limit, 0.0), duration_precision)
    tat_elapsed = round(tat_elapsed_raw, duration_precision)
    tat_remaining = round(tat_target - tat_elapsed_raw, duration_precision)
    tat_overrun = round(max(tat_elapsed_raw - tat_target, 0.0), duration_precision)

    return {
        "supported": True,
        "status": "available",
        "data_classification": "synthetic_fixture_or_non_production_test",
        "authoritative_source_verified": False,
        "as_of": evaluated_at,
        "q_time": {
            "status": q_status,
            "elapsed_minutes": q_elapsed,
            "limit_minutes": q_limit,
            "remaining_minutes": q_remaining,
            "overrun_minutes": q_overrun,
            "utilization_pct": round((q_elapsed_raw / q_limit) * 100.0, duration_precision),
        },
        "tat": {
            "status": tat_status,
            "elapsed_minutes": tat_elapsed,
            "target_minutes": tat_target,
            "remaining_minutes": tat_remaining,
            "overrun_minutes": tat_overrun,
            "utilization_pct": round((tat_elapsed_raw / tat_target) * 100.0, duration_precision),
        },
        "routing": {
            "route_id": str(flow_context["route_id"]),
            "current_step": current_step,
            "current_operation": str(flow_context["current_operation"]),
            "next_step": next_step,
            "next_operation": str(flow_context["next_operation"]),
            "route_state": route_state,
            "route_changed": False,
        },
    }


def build_disposition_evaluation(
    *,
    lot_id: str,
    tool_id: str,
    operation: str,
    measurement: dict[str, Any],
    tool_status: str,
    active_alarm_severity: str = "none",
    maintenance_ack_required: bool = False,
    evaluated_at: str,
    lineage: dict[str, Any],
    flow_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an explainable advisory disposition recommendation."""
    if tool_status not in _ALLOWED_TOOL_STATES:
        raise ValueError("tool_status must be healthy, warning, or alarm")
    if active_alarm_severity not in _ALLOWED_ALARM_SEVERITIES:
        raise ValueError("active_alarm_severity is unsupported")

    spc = evaluate_spc(measurement)
    flow = evaluate_flow_indicators(flow_context, evaluated_at=evaluated_at)
    hard_blockers: list[dict[str, str]] = []
    review_flags: list[dict[str, str]] = []

    if spc["signals"]:
        rules = ", ".join(spc["unique_rule_ids"])
        hard_blockers.append({"code": "SPC_SPECIAL_CAUSE", "evidence": f"Western Electric rule violation(s): {rules}"})
    if spc["outside_spec_sequences"]:
        hard_blockers.append(
            {
                "code": "OUTSIDE_ENGINEERING_SPEC",
                "evidence": f"Out-of-spec sequence(s): {spc['outside_spec_sequences']}",
            }
        )
    if spc["data_quality"]["status"] != "pass":
        hard_blockers.append(
            {
                "code": "MEASUREMENT_DATA_INCOMPLETE",
                "evidence": "Sampling completeness or manifest-integrity evidence failed.",
            }
        )
    if tool_status == "alarm":
        hard_blockers.append({"code": "TOOL_ALARM_ACTIVE", "evidence": f"Tool {tool_id} remains in alarm state."})
    if active_alarm_severity == "critical":
        hard_blockers.append({"code": "CRITICAL_ALARM_ACTIVE", "evidence": "A linked critical alarm remains open."})
    if flow.get("supported"):
        if flow["q_time"]["status"] == "breached":
            hard_blockers.append(
                {
                    "code": "Q_TIME_LIMIT_BREACHED",
                    "evidence": (
                        "Synthetic q-time exceeds its limit by "
                        f"{_format_minutes(float(flow['q_time']['overrun_minutes']))} minutes."
                    ),
                }
            )
        if flow["routing"]["route_state"] == "hold":
            hard_blockers.append({"code": "ROUTING_HOLD_ACTIVE", "evidence": "Synthetic route state remains on hold."})
    else:
        review_flags.append(
            {
                "code": "FLOW_CONTEXT_MISSING",
                "evidence": (
                    "No synthetic route/q-time/TAT context was supplied. The demo cannot verify an authoritative "
                    "MES hold state, so it cannot recommend release."
                ),
            }
        )

    if tool_status == "warning":
        review_flags.append({"code": "TOOL_ON_WATCH", "evidence": f"Tool {tool_id} is in warning state."})
    if active_alarm_severity in {"high", "medium", "low"}:
        review_flags.append(
            {"code": "LINKED_ALARM_OPEN", "evidence": f"A linked {active_alarm_severity} alarm remains open."}
        )
    if maintenance_ack_required:
        review_flags.append(
            {
                "code": "OWNER_ACK_REQUIRED",
                "evidence": "Maintenance ownership acknowledgement is not recorded in the scenario.",
            }
        )
    if flow.get("supported"):
        if flow["q_time"]["status"] == "at_risk":
            review_flags.append({"code": "Q_TIME_AT_RISK", "evidence": "Synthetic q-time has consumed at least 80% of its window."})
        if flow["tat"]["status"] == "over_target":
            review_flags.append({"code": "TAT_TARGET_EXCEEDED", "evidence": "Synthetic lot TAT is over its workflow target."})
        if flow["routing"]["route_state"] == "awaiting_engineering_review":
            review_flags.append({"code": "ROUTING_REVIEW_PENDING", "evidence": "Synthetic route awaits engineering review."})

    if hard_blockers:
        recommendation = "HOLD_FOR_CONTAINMENT"
        rationale = "At least one fail-closed containment condition is present."
    elif review_flags:
        recommendation = "ENGINEERING_REVIEW"
        rationale = "No containment condition fired, but open equipment, alarm, flow, or acknowledgement evidence needs human review."
    else:
        recommendation = "RELEASE_WITH_SAMPLING"
        rationale = "No displayed rule or equipment blocker fired; authorized human approval and downstream evidence remain required."

    actions: list[str] = []
    blocker_codes = {item["code"] for item in hard_blockers}
    if "SPC_SPECIAL_CAUSE" in blocker_codes:
        actions.extend(
            [
                "Contain the affected synthetic scenario lot and apply the site OCAP in any real implementation.",
                "Verify metrology health, then stratify by wafer sequence, chamber, recipe, and adjacent-lot genealogy.",
                "Require documented root-cause evidence and a qualified monitor run before reconsidering disposition.",
            ]
        )
    if "OUTSIDE_ENGINEERING_SPEC" in blocker_codes:
        actions.append("Escalate out-of-spec material to human material review; this API does not infer scrap.")
    if "MEASUREMENT_DATA_INCOMPLETE" in blocker_codes:
        actions.append("Complete the sampling plan and reconcile observation counts before disposition review.")
    if "Q_TIME_LIMIT_BREACHED" in blocker_codes:
        actions.append("Escalate the q-time exception under the approved route-specific procedure; the API cannot reroute material.")
    if any(item["code"] == "FLOW_CONTEXT_MISSING" for item in review_flags):
        actions.append("Supply reviewed non-production flow context or reconcile the authoritative MES hold before release review.")
    if recommendation == "ENGINEERING_REVIEW":
        actions.append("Process engineering must review the linked evidence before any lot movement.")
    if recommendation == "RELEASE_WITH_SAMPLING":
        actions.append("Obtain release-supervisor approval; this recommendation does not move or release material.")
    actions.append("Record the human reviewer, source-system evidence, decision, and expiry before changing material state.")

    data_classification = str(lineage.get("data_classification", "non-production-test"))
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "api_version": "v1",
        "contract_version": DISPOSITION_CONTRACT,
        "evaluated_at": evaluated_at,
        "lot": {"lot_id": lot_id, "tool_id": tool_id, "operation": operation},
        "spc": spc,
        "flow_indicators": flow,
        "gate": {
            "recommendation": recommendation,
            "rationale": rationale,
            "hard_blockers": hard_blockers,
            "review_flags": review_flags,
            "required_actions": actions,
            "human_release_authority_required": True,
            "human_approval_status": "not_recorded",
            "authority": "authorized_process_engineer_and_release_supervisor",
            "automation_boundary": "advisory_only_no_material_movement",
            "material_state_changed": False,
        },
        "lineage": lineage,
        "evidence_boundary": {
            "data_classification": data_classification,
            "classification_source": "packaged_fixture" if lineage.get("fixture_sha256") else "caller_asserted",
            "classification_verified_against_source_system": False,
            "non_production": data_classification in {"synthetic", "non-production-test"},
            "measured_yield": False,
            "yield_forecast": False,
            "risk_or_yield_model_used": False,
            "not_production_release_authority": True,
            "missing_evidence": [
                "MES lot genealogy and authoritative hold state",
                "FDC trace and chamber matching history",
                "metrology gauge R&R and equipment health record",
                "wafer-map and defect-pareto context",
                "downstream inline and final electrical test",
            ],
        },
        "references": {"control_plan": CONTROL_PLAN_ROUTE, "methodology": METHODOLOGY_PATH},
    }


def build_fixture_excursion_review(lot_id: str) -> dict[str, Any]:
    """Execute disposition logic for one lot in the packaged fixture."""
    scenario = load_synthetic_scenario()
    lots = scenario.get("lots")
    if not isinstance(lots, dict) or lot_id not in lots:
        raise KeyError(lot_id)
    lot = lots[lot_id]
    if not isinstance(lot, dict):
        raise ValueError(f"fixture lot {lot_id} must be an object")
    equipment = lot.get("equipment_context")
    if not isinstance(equipment, dict):
        raise ValueError(f"fixture lot {lot_id} equipment_context must be an object")
    measurement = lot.get("measurement")
    if not isinstance(measurement, dict):
        raise ValueError(f"fixture lot {lot_id} measurement must be an object")

    result = build_disposition_evaluation(
        lot_id=lot_id,
        tool_id=str(lot["tool_id"]),
        operation=str(lot["operation"]),
        measurement=measurement,
        tool_status=str(equipment.get("tool_status")),
        active_alarm_severity=str(equipment.get("active_alarm_severity", "none")),
        maintenance_ack_required=bool(equipment.get("maintenance_ack_required", False)),
        evaluated_at=str(scenario["as_of"]),
        lineage={
            "dataset_id": scenario["dataset_id"],
            "schema_version": scenario["schema_version"],
            "fixture_sha256": scenario_sha256(),
            "data_classification": "synthetic",
            "origin": scenario["origin"],
            "as_of": scenario["as_of"],
        },
        flow_context=lot.get("flow_context"),
    )
    result["scenario"] = {
        "purpose": scenario["purpose"],
        "limitations": scenario["limitations"],
        "expected_recommendation": lot.get("expected_recommendation"),
        "expected_rule_ids": lot.get("expected_rule_ids", []),
        "expected_flow": lot.get("expected_flow", {}),
    }
    return result


def build_control_plan() -> dict[str, Any]:
    """Expose the versioned rule policy and packaged-fixture boundary."""
    scenario = load_synthetic_scenario()
    lots = scenario.get("lots", {})
    replay_cases = scenario.get("spc_replay_cases", [])
    return {
        "status": "ok",
        "service": SERVICE_NAME,
        "api_version": "v1",
        "contract_version": CONTROL_PLAN_CONTRACT,
        "dataset": {
            "dataset_id": scenario["dataset_id"],
            "schema_version": scenario["schema_version"],
            "fixture_sha256": scenario_sha256(),
            "as_of": scenario["as_of"],
            "data_classification": "synthetic_fixture",
            "synthetic": scenario["synthetic"],
            "measured_fab_data": False,
            "origin": scenario["origin"],
            "purpose": scenario["purpose"],
            "limitations": scenario["limitations"],
        },
        "control_plan": scenario["control_plan"],
        "covered_lots": sorted(lots) if isinstance(lots, dict) else [],
        "fixture_disposition_case_count": len(lots) if isinstance(lots, dict) else 0,
        "spc_boundary_replay_case_count": len(replay_cases) if isinstance(replay_cases, list) else 0,
        "total_replay_case_count": (
            (len(lots) if isinstance(lots, dict) else 0)
            + (len(replay_cases) if isinstance(replay_cases, list) else 0)
        ),
        "decision_precedence": [
            "Fail closed on data-integrity, SPC special-cause, out-of-spec, tool-alarm, critical-alarm, q-time breach, or route-hold evidence.",
            "Route missing flow context, warning/high-alarm, acknowledgement, TAT, or pending-routing evidence to engineering review.",
            "Recommend release with sampling only when synthetic flow context is present and no displayed blocker or review flag fires; only authorized humans can change material state.",
        ],
        "authority_boundary": {
            "advisory_only": True,
            "human_release_authority_required": True,
            "material_state_changes_supported": False,
        },
        "routes": {
            "fixture_disposition": "/api/fab-ops/v1/lots/lot-8812/disposition",
            "non_production_evaluation": "/api/fab-ops/v1/disposition/evaluate",
            "executed_replays": "/api/fab-ops/v1/evals/replays",
        },
    }


def _assertion(name: str, expected: Any, actual: Any) -> dict[str, Any]:
    return {"name": name, "expected": expected, "actual": actual, "passed": actual == expected}


def _replay_measurement(case: dict[str, Any]) -> dict[str, Any]:
    z_scores = case.get("z_scores")
    if not isinstance(z_scores, list) or not z_scores:
        raise ValueError("SPC replay z_scores must be a non-empty list")
    observations = [
        {"sequence": index, "wafer_id": f"R{index:02d}", "value": value}
        for index, value in enumerate(z_scores, start=1)
    ]
    return {
        "name": str(case.get("case_id", "spc_replay")),
        "unit": "standard_deviation",
        "centerline": 0.0,
        "sigma": 1.0,
        "lsl": -10.0,
        "usl": 10.0,
        "sampling_plan": {
            "planned_wafer_averages": len(observations),
            "observed_wafer_averages": len(observations),
            "sites_per_wafer": 1,
        },
        "observations": observations,
    }


def execute_replay_suite() -> dict[str, Any]:
    """Execute fixture disposition and SPC boundary cases with real assertions."""
    scenario = load_synthetic_scenario()
    runs: list[dict[str, Any]] = []
    lots = scenario.get("lots")
    if not isinstance(lots, dict):
        raise ValueError("fixture lots must be an object")

    for lot_id, raw_lot in lots.items():
        if not isinstance(raw_lot, dict):
            raise ValueError(f"fixture lot {lot_id} must be an object")
        result = build_fixture_excursion_review(str(lot_id))
        expected_flow = raw_lot.get("expected_flow", {})
        if not isinstance(expected_flow, dict):
            raise ValueError(f"fixture lot {lot_id} expected_flow must be an object")
        flow = result["flow_indicators"]
        assertions = [
            _assertion("recommendation", raw_lot.get("expected_recommendation"), result["gate"]["recommendation"]),
            _assertion("unique_rule_ids", raw_lot.get("expected_rule_ids", []), result["spc"]["unique_rule_ids"]),
            _assertion("data_quality", "pass", result["spc"]["data_quality"]["status"]),
            _assertion("q_time_status", expected_flow.get("q_time_status"), flow.get("q_time", {}).get("status")),
            _assertion("tat_status", expected_flow.get("tat_status"), flow.get("tat", {}).get("status")),
            _assertion("route_state", expected_flow.get("route_state"), flow.get("routing", {}).get("route_state")),
            _assertion("human_release_authority_required", True, result["gate"]["human_release_authority_required"]),
            _assertion("material_state_changed", False, result["gate"]["material_state_changed"]),
        ]
        runs.append(
            {
                "case_id": f"disposition-{lot_id}",
                "kind": "fixture_disposition",
                "status": "pass" if all(item["passed"] for item in assertions) else "fail",
                "assertions": assertions,
                "actual": {
                    "recommendation": result["gate"]["recommendation"],
                    "unique_rule_ids": result["spc"]["unique_rule_ids"],
                    "q_time_status": flow.get("q_time", {}).get("status"),
                },
            }
        )

    replay_cases = scenario.get("spc_replay_cases")
    if not isinstance(replay_cases, list):
        raise ValueError("fixture spc_replay_cases must be a list")
    for raw_case in replay_cases:
        if not isinstance(raw_case, dict):
            raise ValueError("each SPC replay case must be an object")
        result = evaluate_spc(_replay_measurement(raw_case))
        actual_signal_sides = [
            f"{signal['rule_id']}:{signal['side']}" for signal in result["signals"]
        ]
        assertions = [
            _assertion("unique_rule_ids", raw_case.get("expected_rule_ids", []), result["unique_rule_ids"]),
            _assertion("signal_sides", raw_case.get("expected_signal_sides", []), actual_signal_sides),
            _assertion("signal_count", raw_case.get("expected_signal_count", 0), len(result["signals"])),
            _assertion("data_quality", "pass", result["data_quality"]["status"]),
            _assertion("measured_yield", False, result["calculation_boundary"]["measured_yield"]),
        ]
        runs.append(
            {
                "case_id": str(raw_case.get("case_id")),
                "kind": "spc_boundary",
                "description": str(raw_case.get("description", "")),
                "status": "pass" if all(item["passed"] for item in assertions) else "fail",
                "assertions": assertions,
                "actual": {"unique_rule_ids": result["unique_rule_ids"], "signal_count": len(result["signals"])},
            }
        )

    total_assertions = sum(len(run["assertions"]) for run in runs)
    passed_assertions = sum(
        1 for run in runs for assertion in run["assertions"] if assertion["passed"]
    )
    failed_assertions = total_assertions - passed_assertions
    return {
        "status": "pass" if failed_assertions == 0 else "fail",
        "service": SERVICE_NAME,
        "api_version": "v1",
        "contract_version": REPLAY_CONTRACT,
        "executed_at": datetime.now(UTC).isoformat(),
        "scenario_as_of": str(scenario["as_of"]),
        "execution_mode": "deterministic_in_process",
        "dataset": {
            "dataset_id": scenario["dataset_id"],
            "fixture_sha256": scenario_sha256(),
            "data_classification": "synthetic_fixture",
            "measured_fab_data": False,
        },
        "summary": {
            "scenarios": len(runs),
            "total_assertions": total_assertions,
            "passed_assertions": passed_assertions,
            "failed_assertions": failed_assertions,
            "score_pct": round((passed_assertions / total_assertions) * 100.0, 1) if total_assertions else 0.0,
        },
        "runs": runs,
        "authority_boundary": {
            "evaluation_only": True,
            "production_release_authority": False,
            "material_state_changes": False,
        },
    }
