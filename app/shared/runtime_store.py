"""
Unified runtime event store for the semiconductor-ops-platform.

Supports per-domain store paths via environment variable prefixes so that
fab-ops and scanner domains write to separate event files while sharing
the same persistence logic.

The persistence backend is selected by the ``PERSISTENCE_BACKEND`` env var:
- ``sqlite`` (default): delegates to :mod:`app.shared.database`
- ``jsonl``: uses the legacy JSONL flat-file store
"""

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger("shared.runtime_store")

REPO_ROOT = Path(__file__).resolve().parents[2]

_DEFAULT_STORE_FILES: dict[str, str] = {
    "fab_ops": "fab-ops-events.jsonl",
    "scanner": "scanner-response-events.jsonl",
}

_ENV_PREFIXES: dict[str, str] = {
    "fab_ops": "FAB_OPS",
    "scanner": "SCANNER",
}


def runtime_store_path(domain: str = "fab_ops") -> Path:
    """Return the filesystem path for the runtime event store of a given domain.

    The path is resolved from the environment variable ``{PREFIX}_RUNTIME_STORE_PATH``
    when set, otherwise falls back to ``<repo_root>/.runtime/<default_file>``.

    Args:
        domain: Domain identifier, e.g. ``"fab_ops"`` or ``"scanner"``.

    Returns:
        Absolute ``Path`` to the JSONL event store file.
    """
    prefix = _ENV_PREFIXES.get(domain, "FAB_OPS")
    configured = os.getenv(f"{prefix}_RUNTIME_STORE_PATH", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    default_file = _DEFAULT_STORE_FILES.get(domain, "events.jsonl")
    return REPO_ROOT / ".runtime" / default_file


def _ensure_store_file(domain: str = "fab_ops") -> Path:
    """Ensure the runtime store file and its parent directory exist.

    Args:
        domain: Domain identifier.

    Returns:
        Absolute ``Path`` to the (now guaranteed-to-exist) store file.
    """
    store_path = runtime_store_path(domain)
    store_path.parent.mkdir(parents=True, exist_ok=True)
    store_path.touch(exist_ok=True)
    return store_path


def record_runtime_event(event_type: str, domain: str = "fab_ops", **payload: Any) -> None:
    """Append a single runtime event to the configured persistence backend.

    When ``PERSISTENCE_BACKEND=sqlite`` (the default), events are written to
    the SQLite database.  Otherwise they are appended to the domain's JSONL
    flat-file store.

    Args:
        event_type: Categorical label for the event (e.g. ``"route_hit"``).
        domain: Domain identifier.
        **payload: Arbitrary key-value pairs serialised into the event record.

    Raises:
        OSError: If the JSONL store file cannot be opened for writing.
    """
    from app.shared.database import is_sqlite_backend, record_event_sqlite

    if is_sqlite_backend():
        record_event_sqlite(event_type, domain, **payload)
        return

    store_path = _ensure_store_file(domain)
    event: dict[str, Any] = {"event_type": event_type, **payload}
    try:
        with store_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=True) + "\n")
        logger.debug("[%s] recorded event %s", domain, event_type)
    except OSError:
        logger.exception("[%s] failed to write runtime event %s", domain, event_type)
        raise


def summarize_runtime_events(domain: str = "fab_ops", limit: int = 4000) -> dict[str, Any]:
    """Read the most recent events from the store and return an aggregated summary.

    Delegates to the SQLite backend when ``PERSISTENCE_BACKEND=sqlite``.

    Args:
        domain: Domain identifier.
        limit: Maximum number of trailing lines to consider.

    Returns:
        Dictionary containing counts, recent events, and last-event timestamp.
    """
    from app.shared.database import is_sqlite_backend, summarize_events_sqlite

    if is_sqlite_backend():
        return summarize_events_sqlite(domain, limit)

    store_path = runtime_store_path(domain)
    summary: dict[str, Any] = {
        "enabled": True,
        "path": str(store_path),
        "event_count": 0,
        "route_hits": 0,
        "release_gate_checks": 0,
        "handoff_exports": 0,
        "signature_exports": 0,
        "event_type_counts": {},
        "last_event_at": None,
        "recent_events": [],
    }
    if not store_path.exists():
        return summary

    try:
        lines = store_path.read_text(encoding="utf-8").splitlines()[-max(1, limit):]
    except OSError:
        logger.exception("[%s] failed to read runtime store at %s", domain, store_path)
        return summary

    for line in lines:
        if not line.strip():
            continue
        try:
            event: dict[str, Any] = json.loads(line)
        except json.JSONDecodeError:
            logger.warning("[%s] skipping malformed event line in store", domain)
            continue
        summary["event_count"] += 1
        summary["recent_events"].append(event)
        at = event.get("at")
        if isinstance(at, str) and (summary["last_event_at"] is None or at > summary["last_event_at"]):
            summary["last_event_at"] = at
        event_type = event.get("event_type")
        event_counts: dict[str, int] = summary["event_type_counts"]
        event_counts[event_type] = event_counts.get(event_type, 0) + 1
        if event_type == "route_hit":
            summary["route_hits"] += 1
        elif event_type in ("release_gate_check", "module_escalation_check"):
            summary["release_gate_checks"] += 1
        elif event_type == "handoff_export":
            summary["handoff_exports"] += 1
        elif event_type == "handoff_signature_export":
            summary["signature_exports"] += 1
    return summary
