from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import app


TOKEN = os.getenv("FAB_OPS_OPERATOR_TOKEN", "").strip()


def build_headers() -> dict[str, str]:
    headers: dict[str, str] = {}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    return headers


def main() -> None:
    headers = build_headers()
    with TestClient(app) as client:
        health = client.get("/health")
        health.raise_for_status()
        client.get("/api/runtime/brief").raise_for_status()
        client.get("/api/review-summary?severity=critical").raise_for_status()
        recovery = client.get("/api/recovery-board?mode=hold")
        recovery.raise_for_status()
        release_gate = client.get("/api/release-gate?lot_id=lot-8812", headers=headers)
        release_gate.raise_for_status()
        scorecard = client.get("/api/runtime/scorecard")
        scorecard.raise_for_status()
        scorecard_body = scorecard.json()

    print(
        json.dumps(
            {
                "ok": True,
                "service": health.json()["service"],
                "critical_alarm_count": scorecard_body["summary"]["critical_alarm_count"],
                "hold_lots": scorecard_body["summary"]["hold_lots"],
                "persisted_events": scorecard_body["runtime"]["persistence"]["event_count"],
                "event_type_counts": scorecard_body["runtime"]["persistence"]["event_type_counts"],
                "operator_auth": scorecard_body["runtime"]["operator_auth"],
                "release_decision": release_gate.json()["payload"]["decision"],
                "recovery_spotlight": recovery.json()["spotlight"]["lot_id"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
