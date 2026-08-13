"""
Semiconductor Ops Platform - Unified FastAPI application entrypoint.

Serves two domains under a single FastAPI app:
  - /api/fab-ops/  : Fab Ops Yield Control Tower (alarms, lots, tools, recovery board)
  - /api/scanner/  : Scanner Field Response (scanners, field incidents, module escalations)

Shared infrastructure (operator access, runtime store, HMAC signatures) lives
in app/shared/ and is used by both domains without duplication.
"""

import logging
import os
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

# ---------------------------------------------------------------------------
# Structured logging configuration
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("platform")

APP_DIR = Path(__file__).resolve().parent
REPO_ROOT = APP_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.domains.fab_ops.routes import router as fab_ops_router  # noqa: E402
from app.domains.scanner.routes import router as scanner_router  # noqa: E402
from app.shared.aws_adapter import aws_status  # noqa: E402
from app.shared.database import persistence_readiness  # noqa: E402
from app.shared.monitoring import setup_monitoring  # noqa: E402
from app.shared.operator_access import build_operator_auth_status, runtime_mode  # noqa: E402
from app.shared.resource_pack import build_platform_resource_pack  # noqa: E402
from app.shared.signatures import SigningConfigurationError, signing_status  # noqa: E402

STATIC_DIR = APP_DIR / "static"

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

OPENAPI_TAGS: list[dict[str, str]] = [
    {
        "name": "platform",
        "description": "Platform-level health checks and diagnostics.",
    },
    {
        "name": "fab-ops",
        "description": "Synthetic Fab Ops evidence -- Western Electric SPC, advisory disposition, flow indicators, workflow boards, and HMAC handoff integrity.",
    },
    {
        "name": "scanner",
        "description": "Scanner Field Response -- field incidents, subsystem escalation, qualification review, and signed handoff.",
    },
    {
        "name": "monitoring",
        "description": "Prometheus metrics and observability endpoints.",
    },
]

app = FastAPI(
    title="Semiconductor Ops Platform",
    description=(
        "Unified manufacturing operations platform for semiconductor environments. "
        "Combines **Fab Ops Yield Control Tower** (alarms, lot-risk prioritization, "
        "tool ownership, advisory release gate, synthetic SPC disposition, recovery board, shift handoff) and "
        "**Scanner Field Response** (field incidents, subsystem escalation, "
        "qualification review, customer readiness, signed handoff) under a single "
        "API with shared infrastructure."
    ),
    version="1.1.0",
    openapi_tags=OPENAPI_TAGS,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    license_info={"name": "MIT"},
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:8000").split(","),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(SigningConfigurationError)
async def signing_configuration_error_handler(
    _request: Request,
    _exc: SigningConfigurationError,
) -> JSONResponse:
    """Fail closed without exposing signing configuration details."""
    return JSONResponse(
        status_code=503,
        content={
            "detail": {
                "message": "handoff signing is unavailable because credentials are not configured",
                "fail_closed": True,
            }
        },
    )

# ---------------------------------------------------------------------------
# Monitoring (Prometheus metrics, structured logging, request ID)
# ---------------------------------------------------------------------------

setup_monitoring(app)

# ---------------------------------------------------------------------------
# Domain routers
# ---------------------------------------------------------------------------

app.include_router(fab_ops_router)
app.include_router(scanner_router)

logger.info("Registered domain routers: fab-ops, scanner")


# ---------------------------------------------------------------------------
# Platform-level routes
# ---------------------------------------------------------------------------


def build_readiness_report() -> dict[str, Any]:
    """Evaluate critical runtime configuration without exposing credentials."""
    persistence = persistence_readiness()
    fab_auth = build_operator_auth_status("fab_ops")
    scanner_auth = build_operator_auth_status("scanner")
    fab_signing = signing_status("fab_ops")
    scanner_signing = signing_status("scanner")
    checks = {
        "persistence": bool(persistence.get("ready")),
        "fab_ops_operator_auth": bool(fab_auth["token_configured"] or fab_auth["demo_mode"]),
        "scanner_operator_auth": bool(scanner_auth["token_configured"] or scanner_auth["demo_mode"]),
        "fab_ops_handoff_signing": bool(fab_signing["available"]),
        "scanner_handoff_signing": bool(scanner_signing["available"]),
        "static_ui": STATIC_DIR.is_dir() and (STATIC_DIR / "index.html").is_file(),
    }
    ready = all(checks.values())
    return {
        "status": "ready" if ready else "not_ready",
        "ready": ready,
        "runtime_mode": runtime_mode(),
        "checks": checks,
        "persistence": persistence,
        "critical_configuration": {
            "fab_ops_operator_auth": fab_auth,
            "scanner_operator_auth": scanner_auth,
            "fab_ops_signing": fab_signing,
            "scanner_signing": scanner_signing,
        },
        "credential_values_exposed": False,
    }


@app.get("/ready", tags=["platform"])
async def readiness() -> JSONResponse:
    """Kubernetes readiness: fail with 503 when critical configuration is absent."""
    report = build_readiness_report()
    return JSONResponse(status_code=200 if report["ready"] else 503, content=report)


@app.get("/health", tags=["platform"])
async def health() -> dict[str, Any]:
    """Return platform health status and navigation links for both domains.

    This is the liveness and diagnostic surface. Kubernetes readiness uses
    ``/ready``, which returns HTTP 503 when critical non-demo configuration is
    missing. This route remains HTTP 200 so liveness does not restart a running
    but deliberately fail-closed process.

    Returns:
        JSON object with ``status``, ``service``, ``domains``, and ``links``.
    """
    logger.info("Health check requested")
    readiness_report = build_readiness_report()
    return {
        "status": "ok" if readiness_report["ready"] else "degraded",
        "service": "semiconductor-ops-platform",
        "readiness": readiness_report,
        "persistence": readiness_report["persistence"],
        "aws": aws_status(),
        "architecture_fast_path": [
            "/health",
            "/ready",
            "/api/resource-pack",
            "/api/export-proof-board",
            "/api/fab-ops/runtime/brief",
            "/api/fab-ops/v1/control-plan",
            "/api/fab-ops/v1/evals/replays",
            "/api/scanner/runtime/brief",
        ],
        "proof_routes": {
            "resource_pack": "/api/resource-pack",
            "export_proof_board": "/api/export-proof-board",
            "fab_ops_release_board": "/api/fab-ops/release-board",
            "fab_ops_spc_control_plan": "/api/fab-ops/v1/control-plan",
            "fab_ops_executed_replays": "/api/fab-ops/v1/evals/replays",
            "fab_ops_architecture_pack": "/api/fab-ops/architecture-pack",
            "scanner_field_response": "/api/scanner/field-response-board",
            "scanner_architecture_pack": "/api/scanner/architecture-pack",
        },
        "domains": {
            "fab_ops": {
                "service": "fab-ops-yield-control-tower",
                "meta": "/api/fab-ops/meta",
                "runtime_brief": "/api/fab-ops/runtime/brief",
                "spc_control_plan": "/api/fab-ops/v1/control-plan",
                "executed_replays": "/api/fab-ops/v1/evals/replays",
                "data_classification": "synthetic_fixture",
            },
            "scanner": {
                "service": "scanner-field-response",
                "meta": "/api/scanner/meta",
                "runtime_brief": "/api/scanner/runtime/brief",
            },
        },
        "links": {
            "resource_pack": "/api/resource-pack",
            "export_proof_board": "/api/export-proof-board",
            "fab_ops_health": "/api/fab-ops/meta",
            "scanner_health": "/api/scanner/meta",
        },
    }


def build_export_proof_board() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "semiconductor-ops-export-proof-board",
        "contract_version": "semiconductor-ops-export-proof-board-v1",
        "headline": "Platform-level export proof board that ties both domain ledgers into one review surface.",
        "aws": aws_status(),
        "persistence": persistence_readiness(),
        "domains": {
            "fab_ops": {
                "runtime_contract": "fab-ops-export-ledger-v1",
                "surface": "/api/fab-ops/runtime/export-ledger",
            },
            "scanner": {
                "runtime_contract": "scanner-export-ledger-v1",
                "surface": "/api/scanner/runtime/export-ledger",
            },
        },
        "links": {
            "resource_pack": "/api/resource-pack",
            "fab_ops_export_ledger": "/api/fab-ops/runtime/export-ledger",
            "scanner_export_ledger": "/api/scanner/runtime/export-ledger",
        },
    }


@app.get("/api/resource-pack", tags=["platform"])
async def platform_resource_pack() -> dict[str, Any]:
    return build_platform_resource_pack()


@app.get("/api/export-proof-board", tags=["platform"])
async def platform_export_proof_board() -> dict[str, Any]:
    return build_export_proof_board()


app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="frontend")
