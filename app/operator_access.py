from __future__ import annotations

import hmac
import os
from typing import Any, Dict

from fastapi import HTTPException, Request


OPERATOR_TOKEN_HEADER = "x-operator-token"


def _expected_operator_token() -> str:
    return os.getenv("FAB_OPS_OPERATOR_TOKEN", "").strip()


def operator_token_enabled() -> bool:
    return bool(_expected_operator_token())


def build_operator_auth_status() -> Dict[str, Any]:
    return {
        "enabled": operator_token_enabled(),
        "header": OPERATOR_TOKEN_HEADER,
        "bearer_supported": True,
    }


def _read_presented_token(request: Request) -> str:
    header_token = request.headers.get(OPERATOR_TOKEN_HEADER, "").strip()
    if header_token:
        return header_token

    auth_header = request.headers.get("authorization", "").strip()
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()

    return ""


def require_operator_token(request: Request) -> None:
    expected = _expected_operator_token()
    if not expected:
        return

    presented = _read_presented_token(request)
    if presented and hmac.compare_digest(presented, expected):
        return

    raise HTTPException(
        status_code=401,
        detail={
            "message": "operator token required",
            "required_header": OPERATOR_TOKEN_HEADER,
        },
    )
