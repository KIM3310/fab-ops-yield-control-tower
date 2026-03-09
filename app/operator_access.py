from __future__ import annotations

import hmac
import os
from typing import Any, Dict

from fastapi import HTTPException, Request


OPERATOR_TOKEN_HEADER = "x-operator-token"
OPERATOR_ROLE_HEADERS = ("x-operator-role", "x-operator-roles")


def _expected_operator_token() -> str:
    return os.getenv("FAB_OPS_OPERATOR_TOKEN", "").strip()


def operator_token_enabled() -> bool:
    return bool(_expected_operator_token())


def _allowed_roles() -> list[str]:
    return [
        value.strip().lower()
        for value in os.getenv("FAB_OPS_OPERATOR_ALLOWED_ROLES", "").split(",")
        if value.strip()
    ]


def build_operator_auth_status() -> Dict[str, Any]:
    return {
        "enabled": operator_token_enabled(),
        "header": OPERATOR_TOKEN_HEADER,
        "bearer_supported": True,
        "role_headers": list(OPERATOR_ROLE_HEADERS),
        "required_roles": _allowed_roles(),
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


def require_operator_token(request: Request) -> None:
    expected = _expected_operator_token()
    if not expected:
        return

    presented = _read_presented_token(request)
    if presented and hmac.compare_digest(presented, expected):
        allowed_roles = _allowed_roles()
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
