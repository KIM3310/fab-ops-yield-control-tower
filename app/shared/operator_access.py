"""
Unified operator access control for the semiconductor-ops-platform.

Supports per-domain environment variable prefixes so that fab-ops and scanner
domains can use independent tokens while sharing the same auth logic.
"""
from __future__ import annotations

import hmac
import os
from typing import Any, Dict

from fastapi import HTTPException, Request


OPERATOR_TOKEN_HEADER = "x-operator-token"
OPERATOR_ROLE_HEADERS = ("x-operator-role", "x-operator-roles")

# Environment variable prefixes per domain
_ENV_PREFIXES = {
    "fab_ops": "FAB_OPS",
    "scanner": "SCANNER",
}


def _expected_operator_token(domain: str = "fab_ops") -> str:
    prefix = _ENV_PREFIXES.get(domain, "FAB_OPS")
    return os.getenv(f"{prefix}_OPERATOR_TOKEN", "").strip()


def operator_token_enabled(domain: str = "fab_ops") -> bool:
    return bool(_expected_operator_token(domain))


def _allowed_roles(domain: str = "fab_ops") -> list[str]:
    prefix = _ENV_PREFIXES.get(domain, "FAB_OPS")
    return [
        value.strip().lower()
        for value in os.getenv(f"{prefix}_OPERATOR_ALLOWED_ROLES", "").split(",")
        if value.strip()
    ]


def build_operator_auth_status(domain: str = "fab_ops") -> Dict[str, Any]:
    return {
        "enabled": operator_token_enabled(domain),
        "header": OPERATOR_TOKEN_HEADER,
        "bearer_supported": True,
        "role_headers": list(OPERATOR_ROLE_HEADERS),
        "required_roles": _allowed_roles(domain),
    }


def _read_presented_token(request: Request) -> str:
    header_token = request.headers.get(OPERATOR_TOKEN_HEADER, "").strip()
    if header_token:
        return header_token

    auth_header = request.headers.get("authorization", "").strip()
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()

    return ""


def _read_presented_roles(request: Request) -> list[str]:
    values: list[str] = []
    for header in OPERATOR_ROLE_HEADERS:
        raw = request.headers.get(header, "").strip()
        if raw:
            values.extend(raw.split(","))
    return [value.strip().lower() for value in values if value.strip()]


def require_operator_token(request: Request, domain: str = "fab_ops") -> None:
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
        raise HTTPException(
            status_code=403,
            detail={
                "message": "required operator role missing",
                "required_roles": allowed_roles,
                "role_headers": list(OPERATOR_ROLE_HEADERS),
            },
        )

    raise HTTPException(
        status_code=401,
        detail={
            "message": "operator token required",
            "required_header": OPERATOR_TOKEN_HEADER,
        },
    )
