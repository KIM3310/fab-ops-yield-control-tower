from fastapi.testclient import TestClient

from app.main import app
from app.shared import aws_adapter


def test_aws_activation_requires_access_key_and_secret(monkeypatch) -> None:
    monkeypatch.setattr(aws_adapter, "_AWS_KEY", "")
    monkeypatch.setattr(aws_adapter, "_AWS_SECRET", "")
    assert aws_adapter.aws_enabled() is False

    monkeypatch.setattr(aws_adapter, "_AWS_KEY", "access-key")
    assert aws_adapter.aws_enabled() is False

    monkeypatch.setattr(aws_adapter, "_AWS_KEY", "")
    monkeypatch.setattr(aws_adapter, "_AWS_SECRET", "secret-key")
    assert aws_adapter.aws_enabled() is False

    monkeypatch.setattr(aws_adapter, "_AWS_KEY", "access-key")
    assert aws_adapter.aws_enabled() is True


def test_fab_ops_shift_handoff_exposes_aws_export_metadata(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.domains.fab_ops.routes.export_handoff_to_s3",
        lambda *args, **kwargs: {"bucket": "fab-bucket", "key": "handoffs/fab.json", "etag": "etag"},
    )
    monkeypatch.setattr(
        "app.domains.fab_ops.routes.persist_export_metadata_to_dynamodb",
        lambda *args, **kwargs: {"table": "fab-ops-runtime-store", "export_id": "handoff-fab-west-1-night"},
    )
    monkeypatch.setattr(
        "app.domains.fab_ops.routes.publish_event_to_sqs",
        lambda *args, **kwargs: {"message_id": "msg-1"},
    )

    client = TestClient(app)
    response = client.get("/api/fab-ops/shift-handoff")

    assert response.status_code == 200
    payload = response.json()
    assert payload["aws_exports"]["s3"]["bucket"] == "fab-bucket"
    assert payload["aws_exports"]["dynamodb"]["table"] == "fab-ops-runtime-store"
    assert payload["aws_exports"]["sqs"]["message_id"] == "msg-1"


def test_scanner_audit_feed_exposes_aws_export_metadata(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.domains.scanner.routes.export_audit_bundle_to_s3",
        lambda *args, **kwargs: {"bucket": "fab-bucket", "key": "audit/scanner.json", "etag": "etag"},
    )
    monkeypatch.setattr(
        "app.domains.scanner.routes.persist_export_metadata_to_dynamodb",
        lambda *args, **kwargs: {"table": "fab-ops-runtime-store", "export_id": "audit-export"},
    )
    monkeypatch.setattr(
        "app.domains.scanner.routes.publish_event_to_sqs",
        lambda *args, **kwargs: {"message_id": "msg-2"},
    )

    client = TestClient(app)
    response = client.get("/api/scanner/audit/feed")

    assert response.status_code == 200
    payload = response.json()
    assert payload["aws_exports"]["s3"]["key"] == "audit/scanner.json"
    assert payload["aws_exports"]["dynamodb"]["table"] == "fab-ops-runtime-store"
    assert payload["aws_exports"]["sqs"]["message_id"] == "msg-2"


def test_production_audit_exports_require_operator_auth_before_cloud_writes(monkeypatch) -> None:
    monkeypatch.setenv("SEMICONDUCTOR_OPS_MODE", "production")
    monkeypatch.delenv("FAB_OPS_OPERATOR_TOKEN", raising=False)
    monkeypatch.delenv("SCANNER_OPERATOR_TOKEN", raising=False)
    calls: list[str] = []

    def unexpected_writer(*args, **kwargs):
        calls.append("called")
        return {"unexpected": True}

    for module in ("app.domains.fab_ops.routes", "app.domains.scanner.routes"):
        monkeypatch.setattr(f"{module}.export_audit_bundle_to_s3", unexpected_writer)
        monkeypatch.setattr(f"{module}.persist_export_metadata_to_dynamodb", unexpected_writer)
        monkeypatch.setattr(f"{module}.publish_event_to_sqs", unexpected_writer)

    client = TestClient(app)
    assert client.get("/api/fab-ops/audit/feed").status_code == 503
    assert client.get("/api/scanner/audit/feed").status_code == 503
    assert calls == []


def test_authenticated_production_audit_export_can_reach_writers(monkeypatch) -> None:
    monkeypatch.setenv("SEMICONDUCTOR_OPS_MODE", "production")
    monkeypatch.setenv("FAB_OPS_OPERATOR_TOKEN", "fab-secret")
    monkeypatch.delenv("FAB_OPS_OPERATOR_ALLOWED_ROLES", raising=False)
    calls: list[str] = []

    def writer(*args, **kwargs):
        calls.append("called")
        return {"ok": True}

    monkeypatch.setattr("app.domains.fab_ops.routes.export_audit_bundle_to_s3", writer)
    monkeypatch.setattr("app.domains.fab_ops.routes.persist_export_metadata_to_dynamodb", writer)
    monkeypatch.setattr("app.domains.fab_ops.routes.publish_event_to_sqs", writer)

    response = TestClient(app).get(
        "/api/fab-ops/audit/feed",
        headers={"x-operator-token": "fab-secret"},
    )
    assert response.status_code == 200
    assert len(calls) == 3
