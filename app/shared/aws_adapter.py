"""
AWS integration adapter for the semiconductor-ops-platform.

All AWS functionality is **gated** by the presence of ``AWS_ACCESS_KEY_ID``
in the environment.  When the key is absent every public function in this
module is a safe no-op that returns ``None`` or an empty dict, so the
platform runs identically without any AWS credentials.

Capabilities:
- **S3 export**: Upload handoff packs and audit bundles to an S3 bucket.
- **SQS publish**: Publish domain events to an SQS queue (placeholder).
"""

import json
import logging
import os
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

logger = logging.getLogger("shared.aws_adapter")

# ---------------------------------------------------------------------------
# Gate check
# ---------------------------------------------------------------------------

_AWS_KEY = os.getenv("AWS_ACCESS_KEY_ID", "").strip()
_AWS_SECRET = os.getenv("AWS_SECRET_ACCESS_KEY", "").strip()
_AWS_REGION = os.getenv("AWS_DEFAULT_REGION", "us-west-2").strip()
_S3_BUCKET = os.getenv("AWS_S3_BUCKET", "semiconductor-ops-exports").strip()
_SQS_QUEUE_URL = os.getenv("AWS_SQS_QUEUE_URL", "").strip()
_DYNAMODB_TABLE = os.getenv("AWS_DYNAMODB_TABLE", "").strip()


def aws_enabled() -> bool:
    """Return True when AWS credentials are configured."""
    return bool(_AWS_KEY and _AWS_SECRET)


def _get_s3_client():  # type: ignore[no-untyped-def]
    """Lazily create a boto3 S3 client."""
    import boto3

    return boto3.client(
        "s3",
        aws_access_key_id=_AWS_KEY,
        aws_secret_access_key=_AWS_SECRET,
        region_name=_AWS_REGION,
    )


def _get_sqs_client():  # type: ignore[no-untyped-def]
    """Lazily create a boto3 SQS client."""
    import boto3

    return boto3.client(
        "sqs",
        aws_access_key_id=_AWS_KEY,
        aws_secret_access_key=_AWS_SECRET,
        region_name=_AWS_REGION,
    )


def _get_dynamodb_resource():  # type: ignore[no-untyped-def]
    """Lazily create a boto3 DynamoDB resource."""
    import boto3

    return boto3.resource(
        "dynamodb",
        aws_access_key_id=_AWS_KEY,
        aws_secret_access_key=_AWS_SECRET,
        region_name=_AWS_REGION,
    )


def _to_dynamodb_compatible(value: Any) -> Any:
    """Recursively normalize Python payloads for DynamoDB serialization."""
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, list):
        return [_to_dynamodb_compatible(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _to_dynamodb_compatible(item) for key, item in value.items()}
    return value


# ---------------------------------------------------------------------------
# S3 export
# ---------------------------------------------------------------------------


def export_handoff_to_s3(
    domain: str,
    handoff_id: str,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    """Upload a shift handoff pack to S3.

    Args:
        domain: Domain identifier (``"fab_ops"`` or ``"scanner"``).
        handoff_id: Unique handoff identifier used as the S3 object key stem.
        payload: The full handoff payload to serialise as JSON.

    Returns:
        Dictionary with ``bucket``, ``key``, and ``etag`` on success,
        or ``None`` when AWS is not configured.
    """
    if not aws_enabled():
        logger.debug("AWS not configured -- skipping S3 handoff export")
        return None

    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    key = f"handoffs/{domain}/{handoff_id}/{ts}.json"
    body = json.dumps(payload, indent=2, ensure_ascii=False)

    try:
        client = _get_s3_client()
        response = client.put_object(
            Bucket=_S3_BUCKET,
            Key=key,
            Body=body.encode("utf-8"),
            ContentType="application/json",
        )
        etag = response.get("ETag", "")
        logger.info("[%s] Handoff exported to s3://%s/%s (ETag: %s)", domain, _S3_BUCKET, key, etag)
        return {"bucket": _S3_BUCKET, "key": key, "etag": etag}
    except Exception:
        logger.exception("[%s] Failed to export handoff to S3", domain)
        return None


def export_audit_bundle_to_s3(
    domain: str,
    audit_events: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Upload an audit event bundle to S3.

    Args:
        domain: Domain identifier.
        audit_events: List of audit event dictionaries.

    Returns:
        Dictionary with ``bucket``, ``key``, and ``etag`` on success,
        or ``None`` when AWS is not configured.
    """
    if not aws_enabled():
        logger.debug("AWS not configured -- skipping S3 audit export")
        return None

    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    key = f"audit/{domain}/{ts}-bundle.json"
    body = json.dumps(
        {"domain": domain, "exported_at": ts, "event_count": len(audit_events), "events": audit_events},
        indent=2,
        ensure_ascii=False,
    )

    try:
        client = _get_s3_client()
        response = client.put_object(
            Bucket=_S3_BUCKET,
            Key=key,
            Body=body.encode("utf-8"),
            ContentType="application/json",
        )
        etag = response.get("ETag", "")
        logger.info("[%s] Audit bundle exported to s3://%s/%s (%d events)", domain, _S3_BUCKET, key, len(audit_events))
        return {"bucket": _S3_BUCKET, "key": key, "etag": etag}
    except Exception:
        logger.exception("[%s] Failed to export audit bundle to S3", domain)
        return None


# ---------------------------------------------------------------------------
# SQS event publishing (placeholder)
# ---------------------------------------------------------------------------


def publish_event_to_sqs(
    domain: str,
    event_type: str,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    """Publish a domain event to SQS.

    This is a placeholder for future async event processing (e.g. triggering
    downstream alerting, analytics pipelines, or cross-domain notifications).

    Args:
        domain: Domain identifier.
        event_type: Categorical event label.
        payload: Event payload to publish.

    Returns:
        Dictionary with ``message_id`` on success, or ``None`` when AWS/SQS
        is not configured.
    """
    if not aws_enabled() or not _SQS_QUEUE_URL:
        logger.debug("AWS SQS not configured -- skipping event publish")
        return None

    message_body = json.dumps(
        {
            "domain": domain,
            "event_type": event_type,
            "published_at": datetime.now(UTC).isoformat(),
            "payload": payload,
        },
        ensure_ascii=False,
    )

    try:
        client = _get_sqs_client()
        message_kwargs = {
            "QueueUrl": _SQS_QUEUE_URL,
            "MessageBody": message_body,
        }
        if ".fifo" in _SQS_QUEUE_URL:
            message_kwargs["MessageGroupId"] = domain
        response = client.send_message(**message_kwargs)
        message_id = response.get("MessageId", "")
        logger.info("[%s] Event published to SQS: %s (MessageId: %s)", domain, event_type, message_id)
        return {"message_id": message_id}
    except Exception:
        logger.exception("[%s] Failed to publish event to SQS", domain)
        return None


def persist_export_metadata_to_dynamodb(
    *,
    domain: str,
    export_id: str,
    export_type: str,
    payload: dict[str, Any],
    summary: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Persist an export metadata envelope to DynamoDB when configured."""
    if not aws_enabled() or not _DYNAMODB_TABLE:
        logger.debug("AWS DynamoDB not configured -- skipping metadata persistence")
        return None

    try:
        table = _get_dynamodb_resource().Table(_DYNAMODB_TABLE)
        timestamp = datetime.now(UTC).isoformat()
        item = {
            "pk": f"{domain}#{export_type}#{export_id}",
            "sk": timestamp,
            "domain": domain,
            "export_type": export_type,
            "export_id": export_id,
            "payload": _to_dynamodb_compatible(payload),
            "summary": _to_dynamodb_compatible(summary or {}),
            "timestamp": timestamp,
        }
        table.put_item(Item=item)
        logger.info("[%s] Export metadata persisted to DynamoDB: %s", domain, export_id)
        return {
            "export_id": export_id,
            "table": _DYNAMODB_TABLE,
            "timestamp": timestamp,
        }
    except Exception:
        logger.exception("[%s] Failed to persist export metadata to DynamoDB", domain)
        return None


# ---------------------------------------------------------------------------
# Status helper
# ---------------------------------------------------------------------------


def aws_status() -> dict[str, Any]:
    """Return a summary of the AWS integration configuration.

    Useful for diagnostic and meta endpoints.

    Returns:
        Dictionary describing which AWS services are configured.
    """
    return {
        "enabled": aws_enabled(),
        "region": _AWS_REGION if aws_enabled() else None,
        "s3_bucket": _S3_BUCKET if aws_enabled() else None,
        "sqs_configured": bool(_SQS_QUEUE_URL) if aws_enabled() else False,
        "dynamodb_table": _DYNAMODB_TABLE if aws_enabled() else None,
    }
