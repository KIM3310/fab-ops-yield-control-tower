"""
Monitoring infrastructure for the semiconductor-ops-platform.

Provides:
- **Prometheus metrics endpoint** (``/metrics``): request counts, latency
  histograms, and active request gauge.
- **Structured JSON logging**: production-grade log formatter that outputs
  one JSON object per line for log aggregators.
- **Request ID middleware**: assigns a unique ``X-Request-ID`` to every
  request for distributed tracing.
"""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.responses import PlainTextResponse

logger = logging.getLogger("shared.monitoring")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ENABLE_METRICS = os.getenv("ENABLE_METRICS", "true").strip().lower() in ("true", "1", "yes")
METRICS_PATH = os.getenv("METRICS_PATH", "/metrics").strip()
LOG_FORMAT = os.getenv("LOG_FORMAT", "text").strip().lower()


# ---------------------------------------------------------------------------
# Structured JSON log formatter
# ---------------------------------------------------------------------------


class JSONFormatter(logging.Formatter):
    """Log formatter that outputs structured JSON lines.

    Each log record becomes a single JSON object with keys: ``timestamp``,
    ``level``, ``logger``, ``message``, and any ``extra`` fields.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = self.formatException(record.exc_info)
        if hasattr(record, "request_id"):
            log_entry["request_id"] = record.request_id  # type: ignore[attr-defined]
        return json.dumps(log_entry, ensure_ascii=False)


def configure_logging() -> None:
    """Configure the root logger based on the ``LOG_FORMAT`` env var.

    When ``LOG_FORMAT=json``, installs :class:`JSONFormatter` on the root
    handler for structured log output.  Otherwise uses the default text format.
    """
    log_level = os.getenv("LOG_LEVEL", "info").strip().upper()
    root = logging.getLogger()
    root.setLevel(getattr(logging, log_level, logging.INFO))

    if LOG_FORMAT == "json":
        handler = logging.StreamHandler()
        handler.setFormatter(JSONFormatter(datefmt="%Y-%m-%dT%H:%M:%S"))
        root.handlers = [handler]
        logger.info("Structured JSON logging enabled")


# ---------------------------------------------------------------------------
# Prometheus metrics (using prometheus_client)
# ---------------------------------------------------------------------------

try:
    from prometheus_client import (
        CollectorRegistry,
        Counter,
        Gauge,
        Histogram,
        generate_latest,
    )

    REGISTRY = CollectorRegistry()

    REQUEST_COUNT = Counter(
        "http_requests_total",
        "Total HTTP requests",
        ["method", "endpoint", "status"],
        registry=REGISTRY,
    )

    REQUEST_LATENCY = Histogram(
        "http_request_duration_seconds",
        "HTTP request latency in seconds",
        ["method", "endpoint"],
        buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
        registry=REGISTRY,
    )

    ACTIVE_REQUESTS = Gauge(
        "http_requests_active",
        "Number of active HTTP requests",
        registry=REGISTRY,
    )

    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False
    logger.warning("prometheus_client not installed -- metrics endpoint disabled")


def _metrics_endpoint(_request: Request) -> Response:
    """Serve Prometheus metrics in text exposition format."""
    if not _PROMETHEUS_AVAILABLE:
        return PlainTextResponse("# prometheus_client not installed\n", status_code=501)
    body = generate_latest(REGISTRY)
    return Response(content=body, media_type="text/plain; version=0.0.4; charset=utf-8")


# ---------------------------------------------------------------------------
# Request ID middleware
# ---------------------------------------------------------------------------


async def _request_id_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Assign a unique request ID to every inbound request.

    The ID is taken from the incoming ``X-Request-ID`` header when present,
    otherwise a new UUID4 is generated.  The ID is attached to the request
    state and echoed back in the response headers.
    """
    request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    request.state.request_id = request_id

    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# ---------------------------------------------------------------------------
# Metrics collection middleware
# ---------------------------------------------------------------------------


async def _metrics_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Collect Prometheus metrics for every request."""
    if not _PROMETHEUS_AVAILABLE or not ENABLE_METRICS:
        return await call_next(request)

    # Skip metrics collection for the metrics endpoint itself
    if request.url.path == METRICS_PATH:
        return await call_next(request)

    ACTIVE_REQUESTS.inc()
    start = time.perf_counter()

    try:
        response = await call_next(request)
    except Exception:
        REQUEST_COUNT.labels(
            method=request.method,
            endpoint=request.url.path,
            status="500",
        ).inc()
        raise
    finally:
        duration = time.perf_counter() - start
        ACTIVE_REQUESTS.dec()

    REQUEST_COUNT.labels(
        method=request.method,
        endpoint=request.url.path,
        status=str(response.status_code),
    ).inc()

    REQUEST_LATENCY.labels(
        method=request.method,
        endpoint=request.url.path,
    ).observe(duration)

    return response


# ---------------------------------------------------------------------------
# Public setup function
# ---------------------------------------------------------------------------


def setup_monitoring(app: FastAPI) -> None:
    """Register all monitoring middleware and endpoints on the FastAPI app.

    Call this once during application startup, after the app is created but
    before domain routers are included.

    Args:
        app: The FastAPI application instance.
    """
    configure_logging()

    # Request ID middleware (outermost -- runs first)
    app.middleware("http")(_request_id_middleware)

    # Metrics collection middleware
    if ENABLE_METRICS and _PROMETHEUS_AVAILABLE:
        app.middleware("http")(_metrics_middleware)
        app.add_api_route(
            METRICS_PATH,
            _metrics_endpoint,
            methods=["GET"],
            tags=["monitoring"],
            summary="Prometheus metrics",
            description="Returns Prometheus metrics in text exposition format.",
            include_in_schema=True,
        )
        logger.info("Prometheus metrics endpoint registered at %s", METRICS_PATH)

    logger.info(
        "Monitoring configured: metrics=%s, log_format=%s",
        "enabled" if ENABLE_METRICS and _PROMETHEUS_AVAILABLE else "disabled",
        LOG_FORMAT,
    )
