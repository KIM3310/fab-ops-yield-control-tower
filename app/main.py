"""
Semiconductor Ops Platform - Unified FastAPI application entrypoint.

Serves two domains under a single FastAPI app:
  - /api/fab-ops/  : Fab Ops Yield Control Tower (alarms, lots, tools, recovery board)
  - /api/scanner/  : Scanner Field Response (scanners, field incidents, module escalations)

Shared infrastructure (operator access, runtime store, HMAC signatures) lives
in app/shared/ and is used by both domains without duplication.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

APP_DIR = Path(__file__).resolve().parent
REPO_ROOT = APP_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.domains.fab_ops.routes import router as fab_ops_router
from app.domains.scanner.routes import router as scanner_router

STATIC_DIR = APP_DIR / "static"

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="Semiconductor Ops Platform")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Domain routers
# ---------------------------------------------------------------------------

app.include_router(fab_ops_router)
app.include_router(scanner_router)


# ---------------------------------------------------------------------------
# Platform-level routes
# ---------------------------------------------------------------------------

@app.get("/health")
async def health() -> Dict[str, Any]:
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
