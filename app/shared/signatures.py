"""
Unified HMAC-SHA256 signature logic for the semiconductor-ops-platform.

Both fab-ops handoff signatures and scanner handoff signatures use the same
algorithm. Domain-specific signing keys and key IDs are resolved from
environment variables with domain-aware prefixes.
"""
from __future__ import annotations

import hashlib
import hmac as _hmac
import json
import logging
import os
from typing import Any

logger = logging.getLogger("shared.signatures")

_SIGNING_KEY_DEFAULTS: dict[str, str] = {
    "fab_ops": "fab-ops-demo-signing-key",
    "scanner": "scanner-demo-signing-key",
}

_SIGNING_KEY_ID_DEFAULTS: dict[str, str] = {
    "fab_ops": "fab-ops-demo-v1",
    "scanner": "scanner-demo-v1",
}

_SIGNING_KEY_ENVS: dict[str, str] = {
    "fab_ops": "FAB_OPS_HANDOFF_SIGNING_KEY",
    "scanner": "SCANNER_RESPONSE_SIGNING_KEY",
}

_SIGNING_KEY_ID_ENVS: dict[str, str] = {
    "fab_ops": "FAB_OPS_HANDOFF_SIGNING_KEY_ID",
    "scanner": "SCANNER_RESPONSE_SIGNING_KEY_ID",
}


def signing_key(domain: str = "fab_ops") -> str:
    """Return the HMAC signing key for the given domain.

    Reads from the environment variable ``{PREFIX}_HANDOFF_SIGNING_KEY``
    and falls back to a built-in demo key when the variable is unset.

    Args:
        domain: Domain identifier (``"fab_ops"`` or ``"scanner"``).

    Returns:
        The signing key string.
    """
    env_name = _SIGNING_KEY_ENVS.get(domain, "FAB_OPS_HANDOFF_SIGNING_KEY")
    default = _SIGNING_KEY_DEFAULTS.get(domain, "demo-signing-key")
    return str(os.getenv(env_name, default)).strip() or default


def signing_key_id(domain: str = "fab_ops") -> str:
    """Return the key identifier tag for the given domain's signing key.

    Args:
        domain: Domain identifier.

    Returns:
        Key identifier string used in signature envelopes.
    """
    env_name = _SIGNING_KEY_ID_ENVS.get(domain, "FAB_OPS_HANDOFF_SIGNING_KEY_ID")
    default = _SIGNING_KEY_ID_DEFAULTS.get(domain, "demo-v1")
    return str(os.getenv(env_name, default)).strip() or default


def stable_json(value: Any) -> str:
    """Serialise *value* to a deterministic, compact JSON string.

    Keys are sorted and separators are minimal so that the same logical
    payload always produces the same byte representation for hashing.

    Args:
        value: Any JSON-serialisable object.

    Returns:
        Canonical JSON string.
    """
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def compute_sha256(data: bytes) -> str:
    """Return the hex-encoded SHA-256 digest of *data*.

    Args:
        data: Raw bytes to hash.

    Returns:
        64-character lowercase hex string.
    """
    return hashlib.sha256(data).hexdigest()


def compute_hmac_sha256(key: str, data: bytes) -> str:
    """Return the hex-encoded HMAC-SHA256 of *data* using *key*.

    Args:
        key: Secret key string (will be UTF-8 encoded).
        data: Raw bytes to authenticate.

    Returns:
        64-character lowercase hex string.
    """
    return _hmac.new(key.encode("utf-8"), data, hashlib.sha256).hexdigest()


def sign_manifest(manifest: Any, domain: str = "fab_ops") -> dict[str, str]:
    """Sign a manifest dict and return sha256 + hmac signature.

    The manifest is first serialised to canonical JSON (sorted keys, compact
    separators) so signatures are reproducible.

    Args:
        manifest: The payload dictionary to sign.
        domain: Domain identifier for key selection.

    Returns:
        Dictionary with ``"sha256"`` (content digest) and ``"signature"``
        (HMAC-SHA256) hex strings.
    """
    body = stable_json(manifest).encode("utf-8")
    logger.debug("[%s] signing manifest (%d bytes)", domain, len(body))
    return {
        "sha256": compute_sha256(body),
        "signature": compute_hmac_sha256(signing_key(domain), body),
    }


def verify_signature(
    manifest: Any,
    *,
    provided_algorithm: str | None = None,
    provided_key_id: str | None = None,
    provided_sha256: str | None = None,
    provided_signature: str | None = None,
    domain: str = "fab_ops",
) -> dict[str, Any]:
    """Verify a manifest signature and return check results.

    Each of the four *provided_** parameters is compared against the
    freshly-computed value.  When a parameter is ``None`` the current
    (correct) value is substituted so the check passes by default.

    Args:
        manifest: The payload to verify.
        provided_algorithm: Algorithm string to compare (e.g. ``"hmac-sha256"``).
        provided_key_id: Key identifier to compare.
        provided_sha256: Expected content digest.
        provided_signature: Expected HMAC signature.
        domain: Domain identifier for key selection.

    Returns:
        Dictionary with ``"overall_valid"`` (bool) and ``"checks"`` mapping.
    """
    current = sign_manifest(manifest, domain)
    current_algorithm = "hmac-sha256"
    current_key_id = signing_key_id(domain)

    algo = str(provided_algorithm or current_algorithm).strip()
    kid = str(provided_key_id or current_key_id).strip()
    sha = str(provided_sha256 or current["sha256"]).strip()
    sig = str(provided_signature or current["signature"]).strip()

    checks: dict[str, bool] = {
        "algorithm_match": _hmac.compare_digest(algo, current_algorithm),
        "key_id_match": _hmac.compare_digest(kid, current_key_id),
        "sha256_match": _hmac.compare_digest(sha, current["sha256"]),
        "signature_match": _hmac.compare_digest(sig, current["signature"]),
    }
    overall_valid = all(checks.values())
    if not overall_valid:
        logger.warning("[%s] signature verification failed: %s", domain, checks)
    return {
        "overall_valid": overall_valid,
        "checks": checks,
    }
