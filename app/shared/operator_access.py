"""
Unified operator access control for the semiconductor-ops-platform.

Supports per-domain environment variable prefixes so that fab-ops and scanner
domains can use independent tokens while sharing the same auth logic.
"""

import hmac
import logging
import os
from typing import Any

from fastapi import HTTPException, Request

logger = logging.getLogger("shared.operator_access")

OPERATOR_TOKEN_HEADER: str = "x-operator-token"
OPERATOR_ROLE_HEADERS: tuple[str, ...] = ("x-operator-role", "x-operator-roles")

# Environment variable prefixes per domain
_ENV_PREFIXES: dict[str, str] = {
    "fab_ops": "FAB_OPS",
    "scanner": "SCANNER",
}

RUNTIME_MODE_ENV: str = "SEMICONDUCTOR_OPS_MODE"
DEMO_RUNTIME_MODE: str = "demo"
DEFAULT_RUNTIME_MODE: str = "locked"


def runtime_mode() -> str:
    """Return the normalized profile; an unset/empty mode is locked, not demo."""
    return os.getenv(RUNTIME_MODE_ENV, DEFAULT_RUNTIME_MODE).strip().lower() or DEFAULT_RUNTIME_MODE


def demo_mode_enabled() -> bool:
    """Return whether the explicit credential-free demo profile is active."""
    return runtime_mode() == DEMO_RUNTIME_MODE


def _expected_operator_token(domain: str = "fab_ops") -> str:
    """Read the expected operator token from the domain's environment variable.

    Args:
        domain: Domain identifier (``"fab_ops"`` or ``"scanner"``).

    Returns:
        The expected token string, or ``""`` when token auth is disabled.
    """
    prefix = _ENV_PREFIXES.get(domain, "FAB_OPS")
    return os.getenv(f"{prefix}_OPERATOR_TOKEN", "").strip()


def operator_token_enabled(domain: str = "fab_ops") -> bool:
    """Return ``True`` when operator token authentication is enabled for *domain*.

    Args:
        domain: Domain identifier.

    Returns:
        Whether a non-empty token is configured.
    """
    return bool(_expected_operator_token(domain))


def _allowed_roles(domain: str = "fab_ops") -> list[str]:
    """Return the list of operator roles permitted for *domain*.

    Reads from ``{PREFIX}_OPERATOR_ALLOWED_ROLES`` (comma-separated).

    Args:
        domain: Domain identifier.

    Returns:
        Lowercase role strings that are allowed access.
    """
    prefix = _ENV_PREFIXES.get(domain, "FAB_OPS")
    return [value.strip().lower() for value in os.getenv(f"{prefix}_OPERATOR_ALLOWED_ROLES", "").split(",") if value.strip()]


def build_operator_auth_status(domain: str = "fab_ops") -> dict[str, Any]:
    """Build a JSON-safe summary of the current operator auth configuration.

    Useful for diagnostic endpoints that expose whether auth is enabled and
    which roles are required.

    Args:
        domain: Domain identifier.

    Returns:
        Dictionary describing the authentication posture.
    """
    token_configured = operator_token_enabled(domain)
    is_demo = demo_mode_enabled()
    if token_configured:
        enforcement = "token_required"
    elif is_demo:
        enforcement = "credential_free_demo_bypass"
    else:
        enforcement = "misconfigured_fail_closed"
    return {
        "enabled": token_configured,
        "token_configured": token_configured,
        "runtime_mode": runtime_mode(),
        "demo_mode": is_demo,
        "enforcement": enforcement,
        "credential_free_demo": is_demo and not token_configured,
        "header": OPERATOR_TOKEN_HEADER,
        "bearer_supported": True,
        "role_headers": list(OPERATOR_ROLE_HEADERS),
        "required_roles": _allowed_roles(domain),
    }


def _read_presented_token(request: Request) -> str:
    """Extract the operator token from the incoming request.

    Checks the ``x-operator-token`` header first, then falls back to the
    ``Authorization: Bearer ...`` header.

    Args:
        request: The inbound FastAPI request.

    Returns:
        The presented token string, or ``""`` if none found.
    """
    header_token = request.headers.get(OPERATOR_TOKEN_HEADER, "").strip()
    if header_token:
        return header_token

    auth_header = request.headers.get("authorization", "").strip()
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()

    return ""


def _read_presented_roles(request: Request) -> list[str]:
    """Extract operator role claims from the incoming request headers.

    Args:
        request: The inbound FastAPI request.

    Returns:
        Lowercase list of role strings.
    """
    values: list[str] = []
    for header in OPERATOR_ROLE_HEADERS:
        raw = request.headers.get(header, "").strip()
        if raw:
            values.extend(raw.split(","))
    return [value.strip().lower() for value in values if value.strip()]


def _require_persistence_ready_for_sensitive_route(domain: str) -> None:
    """Close authenticated non-demo routes when audit persistence is unusable."""
    if demo_mode_enabled():
        return
    from app.shared.database import persistence_readiness

    readiness = persistence_readiness()
    if readiness.get("ready") is True:
        return
    logger.error("[%s] sensitive route closed: persistence backend is not ready", domain)
    raise HTTPException(
        status_code=503,
        detail={
            "message": "runtime persistence is unavailable; sensitive route is closed",
            "runtime_mode": runtime_mode(),
            "backend": readiness.get("backend"),
        },
    )


def require_operator_token(request: Request, domain: str = "fab_ops") -> None:
    """Guard a route by requiring a valid operator token and (optionally) role.

    A missing token configuration is bypassed only in the explicit ``demo``
    runtime profile. Every other profile fails closed until a token is set.

    Args:
        request: The inbound FastAPI request.
        domain: Domain identifier.

    Raises:
        HTTPException: 401 when no valid token is presented, 403 when the
            token is valid but the operator lacks a required role, or 503 when
            required non-demo auth/persistence configuration is unavailable.
    """
    expected = _expected_operator_token(domain)
    if not expected:
        if demo_mode_enabled():
            return
        logger.error("[%s] sensitive route closed: operator token is not configured", domain)
        raise HTTPException(
            status_code=503,
            detail={
                "message": "operator authentication is not configured; sensitive route is closed",
                "runtime_mode": runtime_mode(),
            },
        )

    presented = _read_presented_token(request)
    if presented and hmac.compare_digest(presented, expected):
        allowed_roles = _allowed_roles(domain)
        if allowed_roles:
            presented_roles = _read_presented_roles(request)
            if not any(role in allowed_roles for role in presented_roles):
                logger.warning("[%s] operator role denied - presented: %s", domain, presented_roles)
                raise HTTPException(
                    status_code=403,
                    detail={
                        "message": "required operator role missing",
                        "required_roles": allowed_roles,
                        "role_headers": list(OPERATOR_ROLE_HEADERS),
                    },
                )
        _require_persistence_ready_for_sensitive_route(domain)
        return

    logger.warning("[%s] operator token missing or invalid", domain)
    raise HTTPException(
        status_code=401,
        detail={
            "message": "operator token required",
            "required_header": OPERATOR_TOKEN_HEADER,
        },
    )
