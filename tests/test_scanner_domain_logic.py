"""
Unit tests for scanner domain logic helpers.

Tests cover field response board, subsystem escalation, qualification board,
customer readiness, handoff signing/verification, and edge cases.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.domains.scanner.helpers import (
    build_customer_readiness,
    build_field_response_board,
    build_handoff_signature,
    build_handoff_verify,
    build_qualification_board,
    build_replay_summary,
    build_runtime_brief,
    build_runtime_scorecard,
    build_shift_handoff_payload,
    build_subsystem_escalation,
    customer_readiness_path,
    field_response_path,
    focus_incident,
    focus_lot,
    get_incident_or_404,
    get_lot_or_404,
    get_scanner_or_404,
    qualification_path,
    subsystem_escalation_path,
)


class TestScannerLookups:
    """Tests for scanner lookup helpers."""

    def test_get_scanner_valid(self) -> None:
        scanner = get_scanner_or_404("scanner-euv-02")
        assert scanner["family"] == "EUV"
        assert scanner["status"] == "degraded"

    def test_get_scanner_invalid_raises_404(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            get_scanner_or_404("scanner-fake-99")
        assert exc_info.value.status_code == 404

    def test_get_incident_valid(self) -> None:
        incident = get_incident_or_404("inc-3407")
        assert incident["severity"] == "critical"

    def test_get_incident_invalid_raises_404(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            get_incident_or_404("inc-0000")
        assert exc_info.value.status_code == 404

    def test_get_lot_valid(self) -> None:
        lot = get_lot_or_404("lot-n2-118")
        assert lot["customer"] == "alpha-mobile"

    def test_get_lot_invalid_raises_404(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            get_lot_or_404("lot-nonexistent")
        assert exc_info.value.status_code == 404


class TestScannerPathHelpers:
    """Tests for path builder functions."""

    def test_field_response_path(self) -> None:
        assert field_response_path() == "/api/scanner/field-response-board"

    def test_subsystem_escalation_path(self) -> None:
        result = subsystem_escalation_path("scanner-euv-02")
        assert "tool_id=scanner-euv-02" in result

    def test_qualification_path(self) -> None:
        result = qualification_path("lot-n2-118")
        assert "lot_id=lot-n2-118" in result

    def test_customer_readiness_path(self) -> None:
        result = customer_readiness_path("alpha-mobile")
        assert "customer=alpha-mobile" in result


class TestFocusSelectors:
    """Tests for focus_incident and focus_lot."""

    def test_focus_incident_is_most_critical(self) -> None:
        incident = focus_incident()
        assert incident["severity"] == "critical"
        assert incident["incident_id"] == "inc-3407"

    def test_focus_lot_matches_focus_incident(self) -> None:
        lot = focus_lot()
        incident = focus_incident()
        assert lot["lot_id"] == incident["lot_id"]


class TestBuildFieldResponseBoard:
    """Tests for build_field_response_board()."""

    def test_board_structure(self) -> None:
        board = build_field_response_board()
        assert board["summary"]["incidents"] == 3
        assert board["summary"]["critical"] == 1
        assert board["summary"]["qualification_blockers"] == 1
        assert board["spotlight"]["incident_id"] == "inc-3407"

    def test_items_sorted_by_severity(self) -> None:
        board = build_field_response_board()
        items = board["items"]
        assert items[0]["severity"] == "critical"


class TestBuildSubsystemEscalation:
    """Tests for build_subsystem_escalation()."""

    def test_valid_escalation(self) -> None:
        result = build_subsystem_escalation("scanner-euv-02")
        assert result["tool_id"] == "scanner-euv-02"
        assert result["linked_incident"]["incident_id"] == "inc-3407"
        assert "failure_hypotheses" in result["payload"]

    def test_no_escalation_lane_raises_404(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            build_subsystem_escalation("metrology-04")
        assert exc_info.value.status_code == 404
        assert "No module escalation lane" in str(exc_info.value.detail)


class TestBuildQualificationBoard:
    """Tests for build_qualification_board()."""

    def test_blocked_lot_deltas(self) -> None:
        board = build_qualification_board("lot-n2-118")
        payload = board["payload"]
        assert payload["decision"] == "hold-qualification"
        assert payload["deltas"]["overlay_over_target_nm"] == 1.4
        assert payload["deltas"]["cd_over_target_nm"] == 0.6

    def test_watch_lot(self) -> None:
        board = build_qualification_board("lot-auto-441")
        payload = board["payload"]
        assert payload["decision"] == "watch-window"


class TestBuildCustomerReadiness:
    """Tests for build_customer_readiness()."""

    def test_amber_customer(self) -> None:
        result = build_customer_readiness("alpha-mobile")
        assert result["payload"]["status"] == "amber"
        assert len(result["payload"]["blocked_by"]) > 0

    def test_watch_customer(self) -> None:
        result = build_customer_readiness("auto-sensor")
        assert result["payload"]["status"] == "watch"

    def test_unknown_customer_raises_404(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            build_customer_readiness("unknown-corp")
        assert exc_info.value.status_code == 404


class TestScannerHandoffSignature:
    """Tests for scanner handoff signing and verification."""

    def test_signature_format(self) -> None:
        payload = build_shift_handoff_payload()
        sig = build_handoff_signature(payload)
        assert sig["algorithm"] == "hmac-sha256"
        assert len(sig["sha256"]) == 64
        assert len(sig["signature"]) == 64

    def test_self_verification_passes(self) -> None:
        payload = build_shift_handoff_payload()
        sig = build_handoff_signature(payload)
        verification = build_handoff_verify(payload, sig)
        assert verification["overall_valid"] is True
        assert verification["checks"]["signature_match"] is True
        assert verification["checks"]["digest_match"] is True

    def test_tampered_signature_fails(self) -> None:
        payload = build_shift_handoff_payload()
        sig = build_handoff_signature(payload)
        sig["signature"] = "0" * 64
        verification = build_handoff_verify(payload, sig)
        assert verification["overall_valid"] is False


class TestScannerReplaySummary:
    """Tests for build_replay_summary()."""

    def test_perfect_score(self) -> None:
        summary = build_replay_summary()
        assert summary["summary"]["scenarios"] == 4
        assert summary["summary"]["score_pct"] == 100.0


class TestScannerRuntimeBrief:
    """Tests for build_runtime_brief()."""

    def test_brief_structure(self) -> None:
        brief = build_runtime_brief()
        assert brief["readiness_contract"] == "scanner-runtime-brief-v1"
        assert brief["evidence_counts"]["incidents"] == 3
        assert brief["focus_incident"]["incident_id"] == "inc-3407"
        assert len(brief["review_lanes"]) == 3


class TestScannerRuntimeScorecard:
    """Tests for build_runtime_scorecard()."""

    def test_scorecard_counts(self) -> None:
        scorecard = build_runtime_scorecard()
        assert scorecard["summary"]["scanners"] == 3
        assert scorecard["summary"]["blocked_lots"] == 1
        assert scorecard["summary"]["watch_lots"] == 1
        assert scorecard["summary"]["ready_lots"] == 1
