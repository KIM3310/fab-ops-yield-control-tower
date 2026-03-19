"""
Unit tests for shared infrastructure modules: signatures, runtime store,
and operator access control.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.shared.operator_access import (
    build_operator_auth_status,
    operator_token_enabled,
)
from app.shared.runtime_store import (
    record_runtime_event,
    summarize_runtime_events,
)
from app.shared.signatures import (
    compute_hmac_sha256,
    compute_sha256,
    sign_manifest,
    signing_key,
    signing_key_id,
    stable_json,
    verify_signature,
)


class TestStableJson:
    """Tests for stable_json()."""

    def test_sorted_keys(self) -> None:
        result = stable_json({"b": 2, "a": 1})
        assert result == '{"a":1,"b":2}'

    def test_deterministic(self) -> None:
        data = {"x": [1, 2], "y": {"nested": True}}
        assert stable_json(data) == stable_json(data)


class TestComputeSha256:
    """Tests for compute_sha256()."""

    def test_known_digest(self) -> None:
        digest = compute_sha256(b"hello")
        assert len(digest) == 64
        assert digest == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"

    def test_empty_input(self) -> None:
        digest = compute_sha256(b"")
        assert len(digest) == 64


class TestComputeHmacSha256:
    """Tests for compute_hmac_sha256()."""

    def test_returns_hex_string(self) -> None:
        result = compute_hmac_sha256("key", b"data")
        assert len(result) == 64

    def test_different_keys_different_output(self) -> None:
        a = compute_hmac_sha256("key-a", b"data")
        b = compute_hmac_sha256("key-b", b"data")
        assert a != b


class TestSignManifest:
    """Tests for sign_manifest()."""

    def test_sign_returns_sha256_and_signature(self) -> None:
        result = sign_manifest({"test": True}, domain="fab_ops")
        assert "sha256" in result
        assert "signature" in result
        assert len(result["sha256"]) == 64
        assert len(result["signature"]) == 64

    def test_same_manifest_same_signature(self) -> None:
        manifest = {"a": 1, "b": 2}
        sig1 = sign_manifest(manifest, domain="fab_ops")
        sig2 = sign_manifest(manifest, domain="fab_ops")
        assert sig1["sha256"] == sig2["sha256"]
        assert sig1["signature"] == sig2["signature"]

    def test_different_domains_different_signatures(self) -> None:
        manifest = {"a": 1}
        fab = sign_manifest(manifest, domain="fab_ops")
        scanner = sign_manifest(manifest, domain="scanner")
        assert fab["signature"] != scanner["signature"]


class TestVerifySignature:
    """Tests for verify_signature()."""

    def test_self_verify_passes(self) -> None:
        manifest = {"test": "data"}
        result = verify_signature(manifest, domain="fab_ops")
        assert result["overall_valid"] is True
        assert all(result["checks"].values())

    def test_wrong_signature_fails(self) -> None:
        manifest = {"test": "data"}
        result = verify_signature(
            manifest, provided_signature="0" * 64, domain="fab_ops",
        )
        assert result["overall_valid"] is False
        assert result["checks"]["signature_match"] is False

    def test_wrong_algorithm_fails(self) -> None:
        manifest = {"test": "data"}
        result = verify_signature(
            manifest, provided_algorithm="rsa-256", domain="fab_ops",
        )
        assert result["overall_valid"] is False
        assert result["checks"]["algorithm_match"] is False


class TestSigningKeyDefaults:
    """Tests for signing_key() and signing_key_id() defaults."""

    def test_fab_ops_default_key(self) -> None:
        key = signing_key("fab_ops")
        assert key == "fab-ops-demo-signing-key"

    def test_scanner_default_key(self) -> None:
        key = signing_key("scanner")
        assert key == "scanner-demo-signing-key"

    def test_fab_ops_default_key_id(self) -> None:
        kid = signing_key_id("fab_ops")
        assert kid == "fab-ops-demo-v1"

    def test_scanner_default_key_id(self) -> None:
        kid = signing_key_id("scanner")
        assert kid == "scanner-demo-v1"


class TestRuntimeStore:
    """Tests for runtime store persistence."""

    def test_record_and_summarize(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        store_file = tmp_path / "test-events.jsonl"
        monkeypatch.setenv("FAB_OPS_RUNTIME_STORE_PATH", str(store_file))
        monkeypatch.setenv("PERSISTENCE_BACKEND", "jsonl")
        monkeypatch.setattr("app.shared.database.PERSISTENCE_BACKEND", "jsonl")

        record_runtime_event("test_event", domain="fab_ops", at="2026-01-01T00:00:00Z", detail="hello")

        summary = summarize_runtime_events("fab_ops")
        assert summary["event_count"] == 1
        assert summary["event_type_counts"]["test_event"] == 1
        assert summary["last_event_at"] == "2026-01-01T00:00:00Z"

    def test_summarize_empty_store(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        store_file = tmp_path / "empty.jsonl"
        monkeypatch.setenv("FAB_OPS_RUNTIME_STORE_PATH", str(store_file))
        monkeypatch.setenv("PERSISTENCE_BACKEND", "jsonl")
        monkeypatch.setattr("app.shared.database.PERSISTENCE_BACKEND", "jsonl")
        summary = summarize_runtime_events("fab_ops")
        assert summary["event_count"] == 0
        assert summary["enabled"] is True

    def test_malformed_lines_skipped(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        store_file = tmp_path / "bad.jsonl"
        store_file.write_text("not-json\n{\"event_type\":\"ok\",\"at\":\"2026-01-01T00:00:00Z\"}\n")
        monkeypatch.setenv("FAB_OPS_RUNTIME_STORE_PATH", str(store_file))
        monkeypatch.setenv("PERSISTENCE_BACKEND", "jsonl")
        monkeypatch.setattr("app.shared.database.PERSISTENCE_BACKEND", "jsonl")
        summary = summarize_runtime_events("fab_ops")
        assert summary["event_count"] == 1


class TestOperatorAccess:
    """Tests for operator access control helpers."""

    def test_token_disabled_by_default(self) -> None:
        assert operator_token_enabled("fab_ops") is False

    def test_auth_status_structure(self) -> None:
        status = build_operator_auth_status("fab_ops")
        assert "enabled" in status
        assert "header" in status
        assert status["bearer_supported"] is True

    def test_token_enabled_when_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FAB_OPS_OPERATOR_TOKEN", "secret")
        assert operator_token_enabled("fab_ops") is True
