"""Validated API contracts for non-production fab disposition drills."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, model_validator


class HandoffVerificationEnvelope(BaseModel):
    """Exact caller-presented export envelope; unknown fields are rejected.

    Every field emitted by ``build_handoff_signature`` is required here and is
    either cryptographically checked or validated as a deterministic derivative
    by the verifier. Callers can POST the exported ``payload`` unchanged.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    fab_id: str = Field(min_length=1, max_length=64)
    signature_contract: str = Field(min_length=1, max_length=80)
    signature_id: str = Field(min_length=1, max_length=160)
    algorithm: str = Field(min_length=1, max_length=32)
    key_id: str = Field(min_length=1, max_length=160)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    signature: str = Field(pattern=r"^[0-9a-f]{64}$")
    digest_preview: str = Field(pattern=r"^[0-9a-f]{16}$")
    generated_by: str = Field(min_length=1, max_length=160)
    signed_at: str = Field(min_length=1, max_length=64)
    artifact_channel: str = Field(min_length=1, max_length=160)
    signature_purpose: str = Field(min_length=1, max_length=240)
    human_approval_status: str = Field(min_length=1, max_length=64)
    human_release_authority_required: StrictBool
    manifest: dict[str, object]
    verification_method: str = Field(min_length=1, max_length=16)
    verification_route: str = Field(min_length=1, max_length=160)
    verification_steps: list[str] = Field(min_length=3, max_length=3)


class HandoffVerificationRequest(BaseModel):
    """Optional API-response wrapper around a caller-presented envelope."""

    model_config = ConfigDict(extra="forbid")

    payload: HandoffVerificationEnvelope


class SyntheticFlowContext(BaseModel):
    """Optional non-production q-time, TAT, and route context."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    route_id: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9._-]+$")
    current_step: StrictInt = Field(ge=1, le=1_000_000)
    current_operation: str = Field(min_length=1, max_length=160)
    next_step: StrictInt = Field(ge=1, le=1_000_000)
    next_operation: str = Field(min_length=1, max_length=160)
    route_state: Literal[
        "in_queue",
        "hold",
        "awaiting_engineering_review",
        "ready_for_reviewed_dispatch",
        "in_process",
        "complete",
    ]
    queue_entered_at: datetime
    q_time_limit_minutes: StrictInt = Field(ge=1, le=100_000)
    lot_started_at: datetime
    tat_target_minutes: StrictInt = Field(ge=1, le=1_000_000)

    @model_validator(mode="after")
    def validate_route_and_timestamps(self) -> SyntheticFlowContext:
        if self.next_step <= self.current_step:
            raise ValueError("next_step must be greater than current_step")
        for name, timestamp in (
            ("queue_entered_at", self.queue_entered_at),
            ("lot_started_at", self.lot_started_at),
        ):
            if timestamp.tzinfo is None or timestamp.utcoffset() is None:
                raise ValueError(f"{name} must include a timezone")
        return self


class DispositionEvaluationRequest(BaseModel):
    """Caller-supplied synthetic series for the advisory SPC evaluator.

    Production/customer classifications are intentionally unsupported: this
    repository is a demonstration, not an approved fab-data ingestion path.
    """

    model_config = ConfigDict(
        extra="forbid",
        allow_inf_nan=False,
        str_strip_whitespace=True,
    )

    lot_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    tool_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    operation: str = Field(min_length=1, max_length=160)
    measurement_name: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9._-]+$")
    unit: str = Field(min_length=1, max_length=32, pattern=r"^[A-Za-z0-9_./%-]+$")
    centerline: StrictFloat
    sigma: StrictFloat = Field(gt=0)
    lsl: StrictFloat
    usl: StrictFloat
    values: list[StrictFloat] = Field(min_length=1, max_length=200)
    planned_wafer_averages: StrictInt = Field(ge=1, le=200)
    sites_per_wafer: StrictInt = Field(ge=1, le=1000)
    tool_status: Literal["healthy", "warning", "alarm"]
    active_alarm_severity: Literal["none", "low", "medium", "high", "critical"] = "none"
    maintenance_ack_required: StrictBool = False
    data_classification: Literal["synthetic", "non-production-test"] = "synthetic"
    evaluated_at: datetime | None = None
    flow_context: SyntheticFlowContext | None = None

    @model_validator(mode="after")
    def validate_reference_and_sampling(self) -> DispositionEvaluationRequest:
        if self.lsl >= self.usl:
            raise ValueError("lsl must be lower than usl")
        if not self.lsl <= self.centerline <= self.usl:
            raise ValueError("centerline must fall inside the engineering specification limits")
        if len(self.values) > self.planned_wafer_averages:
            raise ValueError("values cannot exceed planned_wafer_averages")
        if self.flow_context is not None and self.flow_context.queue_entered_at < self.flow_context.lot_started_at:
            raise ValueError("flow_context.queue_entered_at cannot be before lot_started_at")
        if self.evaluated_at is not None:
            if self.evaluated_at.tzinfo is None or self.evaluated_at.utcoffset() is None:
                raise ValueError("evaluated_at must include a timezone")
            if self.flow_context is not None:
                if self.flow_context.queue_entered_at > self.evaluated_at:
                    raise ValueError("flow_context.queue_entered_at cannot be after evaluated_at")
                if self.flow_context.lot_started_at > self.evaluated_at:
                    raise ValueError("flow_context.lot_started_at cannot be after evaluated_at")
        return self
