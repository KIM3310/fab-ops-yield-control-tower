"""
API endpoint edge case tests.

Covers 404 lookups, invalid parameters, auth flows, and cross-domain
integration points.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client() -> TestClient:
    """Provide a shared test client for the full app."""
    return TestClient(app)


class TestFabOps404Routes:
    """Tests for fab-ops routes that should return 404."""

    def test_unknown_tool_ownership(self, client: TestClient) -> None:
        resp = client.get("/api/fab-ops/tool-ownership?tool_id=nonexistent-99")
        assert resp.status_code == 404

    def test_unknown_lot_release_gate(self, client: TestClient) -> None:
        resp = client.get("/api/fab-ops/release-gate?lot_id=lot-0000")
        assert resp.status_code == 404

    def test_recovery_what_if_unknown_lot(self, client: TestClient) -> None:
        resp = client.get("/api/fab-ops/recovery-what-if?lot_id=lot-0000")
        assert resp.status_code == 404


class TestScanner404Routes:
    """Tests for scanner routes that should return 404."""

    def test_unknown_subsystem_escalation(self, client: TestClient) -> None:
        resp = client.get("/api/scanner/subsystem-escalation?tool_id=metrology-04")
        assert resp.status_code == 404

    def test_unknown_qualification_lot(self, client: TestClient) -> None:
        resp = client.get("/api/scanner/qualification-board?lot_id=lot-unknown")
        assert resp.status_code == 404


class TestScannerBadInputs:
    """Tests for scanner routes with invalid query parameters."""

    def test_invalid_severity_filter(self, client: TestClient) -> None:
        resp = client.get("/api/scanner/incidents?severity=panic")
        assert resp.status_code == 400

    def test_invalid_customer(self, client: TestClient) -> None:
        resp = client.get("/api/scanner/customer-readiness?customer=nobody")
        assert resp.status_code == 400


class TestFabOpsBadInputs:
    """Tests for fab-ops routes with invalid query parameters."""

    def test_invalid_recovery_mode(self, client: TestClient) -> None:
        resp = client.get("/api/fab-ops/recovery-board?mode=panic")
        assert resp.status_code == 400

    def test_invalid_review_severity(self, client: TestClient) -> None:
        resp = client.get("/api/fab-ops/review-summary?severity=unknown")
        assert resp.status_code == 400

    def test_invalid_review_risk_bucket(self, client: TestClient) -> None:
        resp = client.get("/api/fab-ops/review-summary?risk_bucket=invalid")
        assert resp.status_code == 400


class TestFabOpsAuthFlow:
    """Tests for operator token auth on sensitive fab-ops routes."""

    def test_release_gate_no_token_when_disabled(self, client: TestClient) -> None:
        # When no token is set, should work without auth
        resp = client.get("/api/fab-ops/release-gate?lot_id=lot-8812")
        assert resp.status_code == 200

    def test_shift_handoff_accessible_without_token(self, client: TestClient) -> None:
        resp = client.get("/api/fab-ops/shift-handoff")
        assert resp.status_code == 200

    def test_auth_required_when_token_set(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    ) -> None:
        monkeypatch.setenv("FAB_OPS_OPERATOR_TOKEN", "test-secret")
        monkeypatch.setenv("FAB_OPS_RUNTIME_STORE_PATH", str(tmp_path / "rt.jsonl"))
        test_client = TestClient(app)

        # No token -> 401
        resp = test_client.get("/api/fab-ops/release-gate?lot_id=lot-8812")
        assert resp.status_code == 401

        # Wrong token -> 401
        resp = test_client.get(
            "/api/fab-ops/release-gate?lot_id=lot-8812",
            headers={"x-operator-token": "wrong"},
        )
        assert resp.status_code == 401

        # Correct token, no roles required -> 200
        resp = test_client.get(
            "/api/fab-ops/release-gate?lot_id=lot-8812",
            headers={"x-operator-token": "test-secret"},
        )
        assert resp.status_code == 200

    def test_bearer_auth_works(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
    ) -> None:
        monkeypatch.setenv("FAB_OPS_OPERATOR_TOKEN", "bearer-test")
        monkeypatch.setenv("FAB_OPS_RUNTIME_STORE_PATH", str(tmp_path / "rt.jsonl"))
        test_client = TestClient(app)

        resp = test_client.get(
            "/api/fab-ops/shift-handoff",
            headers={"Authorization": "Bearer bearer-test"},
        )
        assert resp.status_code == 200


class TestCrossDomainIntegration:
    """Tests verifying both domains coexist on the same app."""

    def test_health_lists_both_domains(self, client: TestClient) -> None:
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert "fab_ops" in body["domains"]
        assert "scanner" in body["domains"]

    def test_fab_ops_and_scanner_meta_both_200(self, client: TestClient) -> None:
        fab = client.get("/api/fab-ops/meta")
        scanner = client.get("/api/scanner/meta")
        assert fab.status_code == 200
        assert scanner.status_code == 200
        assert fab.json()["service"] != scanner.json()["service"]
