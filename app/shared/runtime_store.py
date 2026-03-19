"""
Unified runtime event store for the semiconductor-ops-platform.

Supports per-domain store paths via environment variable prefixes so that
fab-ops and scanner domains write to separate event files while sharing
the same persistence logic.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict


REPO_ROOT = Path(__file__).resolve().parents[2]

_DEFAULT_STORE_FILES = {
    "fab_ops": "fab-ops-events.jsonl",
    "scanner": "scanner-response-events.jsonl",
}

_ENV_PREFIXES = {
    "fab_ops": "FAB_OPS",
    "scanner": "SCANNER",
}


def runtime_store_path(domain: str = "fab_ops") -> Path:
    prefix = _ENV_PREFIXES.get(domain, "FAB_OPS")
    configured = os.getenv(f"{prefix}_RUNTIME_STORE_PATH", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    default_file = _DEFAULT_STORE_FILES.get(domain, "events.jsonl")
    return REPO_ROOT / ".runtime" / default_file


def _ensure_store_file(domain: str = "fab_ops") -> Path:
    store_path = runtime_store_path(domain)
    store_path.parent.mkdir(parents=True, exist_ok=True)
    store_path.touch(exist_ok=True)
    return store_path


def record_runtime_event(event_type: str, domain: str = "fab_ops", **payload: Any) -> None:
    store_path = _ensure_store_file(domain)
    event = {"event_type": event_type, **payload}
    with store_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=True) + "\n")


def summarize_runtime_events(domain: str = "fab_ops", limit: int = 4000) -> Dict[str, Any]:
    store_path = runtime_store_path(domain)
    summary: Dict[str, Any] = {
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

    lines = store_path.read_text(encoding="utf-8").splitlines()[-max(1, limit):]
    for line in lines:
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except Exception:
            continue
        summary["event_count"] += 1
        summary["recent_events"].append(event)
        at = event.get("at")
        if isinstance(at, str) and (summary["last_event_at"] is None or at > summary["last_event_at"]):
            summary["last_event_at"] = at
        event_type = event.get("event_type")
        event_counts = summary["event_type_counts"]
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
