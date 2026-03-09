from __future__ import annotations

import json
import os
import urllib.request


BASE_URL = os.getenv("FAB_OPS_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
TOKEN = os.getenv("FAB_OPS_OPERATOR_TOKEN", "").strip()


def fetch_json(path: str, *, include_token: bool = False) -> dict:
    headers = {}
    if include_token and TOKEN:
        headers["x-operator-token"] = TOKEN
    request = urllib.request.Request(f"{BASE_URL}{path}", headers=headers)
    with urllib.request.urlopen(request) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


payload = {
    "health": fetch_json("/health"),
    "runtime_brief": fetch_json("/api/runtime/brief"),
    "runtime_scorecard": fetch_json("/api/runtime/scorecard"),
    "release_gate": fetch_json("/api/release-gate?lot_id=lot-8812", include_token=True),
}

print(
    json.dumps(
        {
            "ok": True,
            "service": payload["health"]["service"],
            "critical_alarm_count": payload["runtime_scorecard"]["summary"]["critical_alarm_count"],
            "persisted_events": payload["runtime_scorecard"]["runtime"]["persistence"]["event_count"],
            "operator_auth": payload["runtime_scorecard"]["runtime"]["operator_auth"],
            "release_decision": payload["release_gate"]["payload"]["decision"],
        },
        indent=2,
    )
)
