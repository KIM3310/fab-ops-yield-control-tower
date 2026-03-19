"""
Unified operator access control for the semiconductor-ops-platform.

Supports per-domain environment variable prefixes so that fab-ops and scanner
domains can use independent tokens while sharing the same auth logic.
"""
from __future__ import annotations

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
    return [
        value.strip().lower()
        for value in os.getenv(f"{prefix}_OPERATOR_ALLOWED_ROLES", "").split(",")
        if value.strip()
    ]


def build_operator_auth_status(domain: str = "fab_ops") -> dict[str, Any]:
    """Build a JSON-safe summary of the current operator auth configuration.

    Useful for diagnostic endpoints that expose whether auth is enabled and
    which roles are required.

    Args:
        domain: Domain identifier.

    Returns:
        Dictionary describing the authentication posture.
    """
    return {
        "enabled": operator_token_enabled(domain),
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


def require_operator_token(request: Request, domain: str = "fab_ops") -> None:
    """Guard a route by requiring a valid operator token and (optionally) role.

    When no token is configured for the domain this function is a no-op,
    allowing unauthenticated access during development.

    Args:
        request: The inbound FastAPI request.
        domain: Domain identifier.

    Raises:
        HTTPException: 401 when no valid token is presented, or 403 when the
            token is valid but the operator lacks a required role.
    """
    expected = _expected_operator_token(domain)
    if not expected:
        return

    presented = _read_presented_token(request)
    if presented and hmac.compare_digest(presented, expected):
        allowed_roles = _allowed_roles(domain)
        if not allowed_roles:
            return
        presented_roles = _read_presented_roles(request)
        if any(role in allowed_roles for role in presented_roles):
            return
        logger.warning("[%s] operator role denied - presented: %s", domain, presented_roles)
        raise HTTPException(
            status_code=403,
            detail={
                "message": "required operator role missing",
                "required_roles": allowed_roles,
                "role_headers": list(OPERATOR_ROLE_HEADERS),
            },
        )

    logger.warning("[%s] operator token missing or invalid", domain)
    raise HTTPException(
        status_code=401,
        detail={
            "message": "operator token required",
            "required_header": OPERATOR_TOKEN_HEADER,
        },
    )
