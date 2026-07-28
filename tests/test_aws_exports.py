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
