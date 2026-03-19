"""
Semiconductor Ops Platform - Unified FastAPI application entrypoint.

Serves two domains under a single FastAPI app:
  - /api/fab-ops/  : Fab Ops Yield Control Tower (alarms, lots, tools, recovery board)
  - /api/scanner/  : Scanner Field Response (scanners, field incidents, module escalations)

Shared infrastructure (operator access, runtime store, HMAC signatures) lives
in app/shared/ and is used by both domains without duplication.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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
from app.shared.monitoring import setup_monitoring  # noqa: E402

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
        "description": "Fab Ops Yield Control Tower -- alarms, lots, tools, recovery board, release gate, and shift handoff.",
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
        "tool ownership, release gate, recovery board, shift handoff) and "
        "**Scanner Field Response** (field incidents, subsystem escalation, "
        "qualification review, customer readiness, signed handoff) under a single "
        "API with shared infrastructure."
    ),
    version="1.0.0",
    openapi_tags=OPENAPI_TAGS,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    license_info={"name": "MIT"},
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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

@app.get("/health", tags=["platform"])
async def health() -> dict[str, Any]:
    """Return platform health status and navigation links for both domains.

    This is the top-level readiness probe. It enumerates the two domains
    and their respective entry-point routes so operators and automated
    monitors can verify the service is responsive.

    Returns:
        JSON object with ``status``, ``service``, ``domains``, and ``links``.
    """
    logger.info("Health check requested")
    return {
        "status": "ok",
        "service": "semiconductor-ops-platform",
        "domains": {
            "fab_ops": {
                "service": "fab-ops-yield-control-tower",
                "meta": "/api/fab-ops/meta",
                "runtime_brief": "/api/fab-ops/runtime/brief",
            },
            "scanner": {
                "service": "scanner-field-response",
                "meta": "/api/scanner/meta",
                "runtime_brief": "/api/scanner/runtime/brief",
            },
        },
        "links": {
            "fab_ops_health": "/api/fab-ops/meta",
            "scanner_health": "/api/scanner/meta",
        },
    }


app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="frontend")
