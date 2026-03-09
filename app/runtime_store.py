from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict


REPO_ROOT = Path(__file__).resolve().parents[1]


def runtime_store_path() -> Path:
    configured = os.getenv("FAB_OPS_RUNTIME_STORE_PATH", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return REPO_ROOT / ".runtime" / "fab-ops-events.jsonl"


def _ensure_store_file() -> Path:
    store_path = runtime_store_path()
    store_path.parent.mkdir(parents=True, exist_ok=True)
    store_path.touch(exist_ok=True)
    return store_path


def record_runtime_event(event_type: str, **payload: Any) -> None:
    store_path = _ensure_store_file()
    event = {"event_type": event_type, **payload}
    with store_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=True) + "\n")


def summarize_runtime_events(limit: int = 4000) -> Dict[str, Any]:
    store_path = runtime_store_path()
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

    lines = store_path.read_text(encoding="utf-8").splitlines()[-max(1, limit) :]
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
        elif event_type == "release_gate_check":
            summary["release_gate_checks"] += 1
        elif event_type == "handoff_export":
            summary["handoff_exports"] += 1
        elif event_type == "handoff_signature_export":
            summary["signature_exports"] += 1
    return summary
