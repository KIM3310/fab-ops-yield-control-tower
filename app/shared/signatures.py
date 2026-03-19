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
import os
from typing import Any


_SIGNING_KEY_DEFAULTS = {
    "fab_ops": "fab-ops-demo-signing-key",
    "scanner": "scanner-demo-signing-key",
}

_SIGNING_KEY_ID_DEFAULTS = {
    "fab_ops": "fab-ops-demo-v1",
    "scanner": "scanner-demo-v1",
}

_SIGNING_KEY_ENVS = {
    "fab_ops": "FAB_OPS_HANDOFF_SIGNING_KEY",
    "scanner": "SCANNER_RESPONSE_SIGNING_KEY",
}

_SIGNING_KEY_ID_ENVS = {
    "fab_ops": "FAB_OPS_HANDOFF_SIGNING_KEY_ID",
    "scanner": "SCANNER_RESPONSE_SIGNING_KEY_ID",
}


def signing_key(domain: str = "fab_ops") -> str:
    env_name = _SIGNING_KEY_ENVS.get(domain, "FAB_OPS_HANDOFF_SIGNING_KEY")
    default = _SIGNING_KEY_DEFAULTS.get(domain, "demo-signing-key")
    return str(os.getenv(env_name, default)).strip() or default


def signing_key_id(domain: str = "fab_ops") -> str:
    env_name = _SIGNING_KEY_ID_ENVS.get(domain, "FAB_OPS_HANDOFF_SIGNING_KEY_ID")
    default = _SIGNING_KEY_ID_DEFAULTS.get(domain, "demo-v1")
    return str(os.getenv(env_name, default)).strip() or default


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def compute_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compute_hmac_sha256(key: str, data: bytes) -> str:
    return _hmac.new(key.encode("utf-8"), data, hashlib.sha256).hexdigest()


def sign_manifest(manifest: Any, domain: str = "fab_ops") -> dict[str, str]:
    """Sign a manifest dict and return sha256 + hmac signature."""
    body = stable_json(manifest).encode("utf-8")
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
    """Verify a manifest signature and return check results."""
    current = sign_manifest(manifest, domain)
    current_algorithm = "hmac-sha256"
    current_key_id = signing_key_id(domain)

    algo = str(provided_algorithm or current_algorithm).strip()
    kid = str(provided_key_id or current_key_id).strip()
    sha = str(provided_sha256 or current["sha256"]).strip()
    sig = str(provided_signature or current["signature"]).strip()

    checks = {
        "algorithm_match": _hmac.compare_digest(algo, current_algorithm),
        "key_id_match": _hmac.compare_digest(kid, current_key_id),
        "sha256_match": _hmac.compare_digest(sha, current["sha256"]),
        "signature_match": _hmac.compare_digest(sig, current["signature"]),
    }
    return {
        "overall_valid": all(checks.values()),
        "checks": checks,
    }
