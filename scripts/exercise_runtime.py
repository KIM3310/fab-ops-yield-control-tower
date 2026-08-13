from __future__ import annotations

import json
import os
import sys
import warnings
from pathlib import Path

from starlette.exceptions import StarletteDeprecationWarning

warnings.filterwarnings(
    "ignore",
    message="Using `httpx` with `starlette.testclient` is deprecated",
    category=StarletteDeprecationWarning,
)

from fastapi.testclient import TestClient  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import app  # noqa: E402, I001


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
        readiness = client.get("/ready")
        readiness.raise_for_status()
        assert readiness.json()["ready"] is True

        # Fab ops domain
        client.get("/api/fab-ops/runtime/brief").raise_for_status()
        client.get("/api/fab-ops/architecture-summary?severity=critical").raise_for_status()
        recovery = client.get("/api/fab-ops/recovery-board?mode=hold")
        recovery.raise_for_status()
        control_plan = client.get("/api/fab-ops/v1/control-plan")
        control_plan.raise_for_status()
        disposition = client.get("/api/fab-ops/v1/lots/lot-8812/disposition", headers=headers)
        disposition.raise_for_status()
        replay = client.get("/api/fab-ops/v1/evals/replays")
        replay.raise_for_status()
        release_gate = client.get("/api/fab-ops/release-gate?lot_id=lot-8812", headers=headers)
        release_gate.raise_for_status()
        signature = client.get("/api/fab-ops/shift-handoff/signature", headers=headers)
        signature.raise_for_status()
        signature_envelope = signature.json()["payload"]
        verification = client.post(
            "/api/fab-ops/shift-handoff/verify",
            headers=headers,
            json=signature_envelope,
        )
        verification.raise_for_status()
        assert verification.json()["payload"]["overall_valid"] is True
        tampered_envelope = json.loads(json.dumps(signature_envelope))
        tampered_envelope["manifest"]["spc_evidence_binding"]["fixture_sha256"] = "0" * 64
        tampered_verification = client.post(
            "/api/fab-ops/shift-handoff/verify",
            headers=headers,
            json=tampered_envelope,
        )
        tampered_verification.raise_for_status()
        assert tampered_verification.json()["payload"]["overall_valid"] is False
        scorecard = client.get("/api/fab-ops/runtime/scorecard")
        scorecard.raise_for_status()
        scorecard_body = scorecard.json()
        disposition_body = disposition.json()
        replay_body = replay.json()
        assert control_plan.json()["dataset"]["measured_fab_data"] is False
        assert disposition_body["gate"]["recommendation"] == "HOLD_FOR_CONTAINMENT"
        assert disposition_body["gate"]["material_state_changed"] is False
        assert disposition_body["flow_indicators"]["q_time"]["status"] == "breached"
        assert replay_body["status"] == "pass"
        assert replay_body["summary"]["failed_assertions"] == 0

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
                    "spc_recommendation": disposition_body["gate"]["recommendation"],
                    "q_time_status": disposition_body["flow_indicators"]["q_time"]["status"],
                    "executed_replay_assertions": replay_body["summary"]["passed_assertions"],
                    "failed_replay_assertions": replay_body["summary"]["failed_assertions"],
                    "handoff_manifest_verified": verification.json()["payload"]["overall_valid"],
                    "tampered_lineage_rejected": not tampered_verification.json()["payload"]["overall_valid"],
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
