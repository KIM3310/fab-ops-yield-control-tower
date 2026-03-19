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

        # Fab ops domain
        client.get("/api/fab-ops/runtime/brief").raise_for_status()
        client.get("/api/fab-ops/review-summary?severity=critical").raise_for_status()
        recovery = client.get("/api/fab-ops/recovery-board?mode=hold")
        recovery.raise_for_status()
        release_gate = client.get("/api/fab-ops/release-gate?lot_id=lot-8812", headers=headers)
        release_gate.raise_for_status()
        scorecard = client.get("/api/fab-ops/runtime/scorecard")
        scorecard.raise_for_status()
        scorecard_body = scorecard.json()

        # Scanner domain
        client.get("/api/scanner/runtime/brief").raise_for_status()
        scanner_field = client.get("/api/scanner/field-response-board")
        scanner_field.raise_for_status()

    print(
        json.dumps(
            {
                "ok": True,
                "service": health.json()["service"],
                "fab_ops": {
                    "critical_alarm_count": scorecard_body["summary"]["critical_alarm_count"],
                    "hold_lots": scorecard_body["summary"]["hold_lots"],
                    "persisted_events": scorecard_body["runtime"]["persistence"]["event_count"],
                    "release_decision": release_gate.json()["payload"]["decision"],
                    "recovery_spotlight": recovery.json()["spotlight"]["lot_id"],
                },
                "scanner": {
                    "incidents": scanner_field.json()["summary"]["incidents"],
                    "qualification_blockers": scanner_field.json()["summary"]["qualification_blockers"],
                },
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
