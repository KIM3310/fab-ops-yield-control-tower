"""
Unit tests for fab-ops domain logic helpers.

Tests cover release gate decisions, recovery board filtering, what-if
simulations, shift handoff signing/verification, and edge cases.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.domains.fab_ops.helpers import (
    build_audit_feed,
    build_fab_summary,
    build_focus_lot,
    build_handoff_signature,
    build_handoff_signature_verification,
    build_recovery_board,
    build_recovery_what_if,
    build_release_board,
    build_release_gate,
    build_replay_summary,
    build_review_summary,
    build_shift_handoff,
    build_tool_ownership,
    get_lot_or_404,
    get_tool_or_404,
    normalize_review_filter,
    utc_now_iso,
)


class TestUtcNowIso:
    """Tests for utc_now_iso()."""

    def test_returns_iso_string(self) -> None:
        result = utc_now_iso()
        assert isinstance(result, str)
        assert "T" in result
        assert "+" in result or "Z" in result


class TestGetToolOr404:
    """Tests for get_tool_or_404()."""

    def test_valid_tool_returns_dict(self) -> None:
        tool = get_tool_or_404("etch-14")
        assert tool["tool_id"] == "etch-14"
        assert tool["status"] == "alarm"

    def test_unknown_tool_raises_404(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            get_tool_or_404("nonexistent-99")
        assert exc_info.value.status_code == 404
        assert "Unknown tool" in str(exc_info.value.detail)


class TestGetLotOr404:
    """Tests for get_lot_or_404()."""

    def test_valid_lot_returns_dict(self) -> None:
        lot = get_lot_or_404("lot-8812")
        assert lot["lot_id"] == "lot-8812"
        assert lot["yield_risk_score"] == 0.94

    def test_unknown_lot_raises_404(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            get_lot_or_404("lot-0000")
        assert exc_info.value.status_code == 404


class TestNormalizeReviewFilter:
    """Tests for normalize_review_filter()."""

    def test_none_returns_none(self) -> None:
        assert normalize_review_filter("sev", None, {"critical"}) is None

    def test_empty_string_returns_none(self) -> None:
        assert normalize_review_filter("sev", "", {"critical"}) is None

    def test_valid_value_passes_through(self) -> None:
        assert normalize_review_filter("sev", "critical", {"critical", "high"}) == "critical"

    def test_invalid_value_raises_400(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            normalize_review_filter("severity", "urgent", {"critical", "high"})
        assert exc_info.value.status_code == 400
        assert "Invalid severity filter" in str(exc_info.value.detail)


class TestBuildReleaseGate:
    """Tests for build_release_gate()."""

    def test_severe_lot_held(self) -> None:
        gate = build_release_gate("lot-8812")
        assert gate["decision"] == "hold-release"
        assert len(gate["failed_checks"]) > 0
        assert "critical tool alarm still open" in gate["failed_checks"]

    def test_elevated_lot_reroute(self) -> None:
        gate = build_release_gate("lot-8821")
        assert gate["decision"] == "reroute-review"

    def test_watch_lot_release_with_sampling(self) -> None:
        gate = build_release_gate("lot-8836")
        assert gate["decision"] == "release-with-sampling"
        assert gate["failed_checks"] == []

    def test_unknown_lot_raises_404(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            build_release_gate("lot-9999")
        assert exc_info.value.status_code == 404


class TestBuildToolOwnership:
    """Tests for build_tool_ownership()."""

    def test_returns_merged_record(self) -> None:
        ownership = build_tool_ownership("etch-14")
        assert ownership["tool_id"] == "etch-14"
        assert ownership["maintenance_owner"] == "maint-etch-cell-a"
        assert ownership["status"] == "alarm"
        assert ownership["line"] == "etch-bay-a"

    def test_healthy_tool_no_ack_required(self) -> None:
        ownership = build_tool_ownership("cmp-07")
        assert ownership["ack_required"] is False


class TestBuildRecoveryBoard:
    """Tests for build_recovery_board()."""

    def test_all_mode_returns_all_lots(self) -> None:
        board = build_recovery_board(mode=None)
        assert board["summary"]["visible_lots"] == 3
        assert board["summary"]["hold_count"] == 1
        assert board["summary"]["watch_count"] == 1
        assert board["summary"]["ready_count"] == 1

    def test_hold_mode_filters_to_hold_only(self) -> None:
        board = build_recovery_board(mode="hold")
        assert board["summary"]["visible_lots"] == 1
        assert board["items"][0]["board_status"] == "hold"
        assert board["items"][0]["lot_id"] == "lot-8812"

    def test_ready_mode_filters_to_ready_only(self) -> None:
        board = build_recovery_board(mode="ready")
        assert board["summary"]["visible_lots"] == 1
        assert board["items"][0]["board_status"] == "ready"

    def test_invalid_mode_raises_400(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            build_recovery_board(mode="escalate")
        assert exc_info.value.status_code == 400


class TestBuildRecoveryWhatIf:
    """Tests for build_recovery_what_if()."""

    def test_maintenance_complete_changes_decision(self) -> None:
        result = build_recovery_what_if(
            "lot-8812",
            yield_gain=0.25,
            maintenance_complete=True,
        )
        assert result["baseline"]["decision"] == "hold-release"
        assert result["simulated"]["decision"] in {"reroute-review", "release-with-sampling"}
        assert result["delta"]["maintenance_clearance"] is True
        assert result["delta"]["risk_score_reduction"] > 0

    def test_zero_yield_gain_preserves_risk(self) -> None:
        result = build_recovery_what_if("lot-8812", yield_gain=0.0)
        assert result["simulated"]["yield_risk_score"] == 0.94

    def test_yield_gain_clamped_to_half(self) -> None:
        result = build_recovery_what_if("lot-8812", yield_gain=1.0)
        # yield_gain clamped to 0.5, so 0.94 - 0.50 = 0.44
        assert result["simulated"]["yield_risk_score"] == 0.44


class TestBuildShiftHandoff:
    """Tests for build_shift_handoff()."""

    def test_handoff_structure(self) -> None:
        handoff = build_shift_handoff()
        assert handoff["fab_id"] == "fab-west-1"
        assert handoff["shift"] == "night"
        assert handoff["schema"] == "fab-ops-shift-handoff-v1"
        assert len(handoff["must_acknowledge"]) == 3
        assert handoff["lots_at_risk"][0]["yield_risk_score"] >= handoff["lots_at_risk"][-1]["yield_risk_score"]


class TestBuildHandoffSignature:
    """Tests for build_handoff_signature() and verification."""

    def test_signature_structure(self) -> None:
        sig = build_handoff_signature()
        assert sig["algorithm"] == "hmac-sha256"
        assert len(sig["sha256"]) == 64
        assert len(sig["signature"]) == 64
        assert sig["signature_contract"] == "fab-ops-handoff-signature-v1"

    def test_self_verification_passes(self) -> None:
        verification = build_handoff_signature_verification()
        assert verification["overall_valid"] is True
        assert all(verification["checks"].values())

    def test_wrong_sha_fails_verification(self) -> None:
        verification = build_handoff_signature_verification(sha256="0" * 64)
        assert verification["overall_valid"] is False
        assert verification["checks"]["sha256_match"] is False


class TestBuildFabSummary:
    """Tests for build_fab_summary()."""

    def test_summary_counts(self) -> None:
        summary = build_fab_summary()
        assert summary["tool_count"] == 3
        assert summary["alarm_count"] == 2
        assert summary["critical_alarm_count"] == 1
        assert summary["healthy_tools"] + summary["degraded_tools"] == summary["tool_count"]


class TestBuildReleaseBoard:
    """Tests for build_release_board()."""

    def test_release_board_counts(self) -> None:
        board = build_release_board()
        assert board["summary"]["visible_lots"] == 3
        assert board["summary"]["hold_release"] == 1
        assert board["summary"]["reroute_review"] == 1
        assert board["summary"]["release_with_sampling"] == 1
        assert board["spotlight"]["lot_id"] == "lot-8812"


class TestBuildReviewSummary:
    """Tests for build_review_summary()."""

    def test_unfiltered_returns_all(self) -> None:
        summary = build_review_summary()
        assert summary["summary"]["alarm_count"] == 2
        assert summary["summary"]["lot_count"] == 3

    def test_critical_filter(self) -> None:
        summary = build_review_summary(severity="critical")
        assert summary["summary"]["alarm_count"] == 1
        assert summary["spotlight"]["alarm"]["severity"] == "critical"

    def test_invalid_severity_raises_400(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            build_review_summary(severity="urgent")
        assert exc_info.value.status_code == 400


class TestBuildFocusLot:
    """Tests for build_focus_lot()."""

    def test_focus_lot_is_lot_8812(self) -> None:
        focus = build_focus_lot()
        assert focus["lot_id"] == "lot-8812"
        assert focus["severity"] == "critical"
        assert focus["release_decision"] == "hold-release"
        assert len(focus["review_path"]) == 4


class TestBuildAuditFeed:
    """Tests for build_audit_feed()."""

    def test_audit_feed_structure(self) -> None:
        feed = build_audit_feed()
        assert feed["summary"]["events"] == 3
        assert feed["summary"]["critical_alarm_count"] == 1
        assert len(feed["items"]) == 3


class TestBuildReplaySummary:
    """Tests for build_replay_summary()."""

    def test_perfect_score(self) -> None:
        summary = build_replay_summary()
        assert summary["summary"]["scenarios"] == 4
        assert summary["summary"]["score_pct"] == 100.0
        assert summary["summary"]["passed_checks"] == summary["summary"]["total_checks"]
