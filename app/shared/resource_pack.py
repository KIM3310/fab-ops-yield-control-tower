from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from app.domains.fab_ops.domain import ALARMS, LOTS_AT_RISK
from app.domains.scanner.domain import FIELD_INCIDENTS

EXTERNAL_DIR = Path(__file__).resolve().parents[2] / "data" / "external" / "uci_secom"


def build_platform_resource_pack() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "semiconductor-ops-platform-resource-pack",
        "contract_version": "semiconductor-ops-resource-pack-v1",
        "intended_use": "review-safe synthetic manufacturing scenarios and controls without plant telemetry",
        "evidence_boundary": {
            "fab_data_classification": "synthetic_fixture",
            "measured_yield": False,
            "human_release_authority_required": True,
        },
        "summary": {
            "fab_alarm_count": len(ALARMS),
            "fab_lot_count": len(LOTS_AT_RISK),
            "scanner_incident_count": len(FIELD_INCIDENTS),
            "operator_check_count": 6,
            "validation_case_count": 5,
            "external_dataset_count": 1 if (EXTERNAL_DIR / "uci-secom.csv").exists() else 0,
        },
        "external_data": {
            "present": (EXTERNAL_DIR / "uci-secom.csv").exists(),
            "path": "data/external/uci_secom/uci-secom.csv",
            "row_count": _count_csv_rows(EXTERNAL_DIR / "uci-secom.csv"),
            "preview_rows": _preview_csv_rows(EXTERNAL_DIR / "uci-secom.csv"),
        },
        "fab_architecture_cases": [
            {
                "case_id": "fab-critical-plasma-instability",
                "focus_lot": "lot-8812",
                "goal": "Explain why a severe lot remains blocked until maintenance and reroute review align.",
                "next_surface": "/api/fab-ops/v1/lots/lot-8812/disposition",
            },
            {
                "case_id": "fab-temperature-drift-watch",
                "focus_lot": "lot-8821",
                "goal": "Show how watch posture differs from a hard release block.",
                "next_surface": "/api/fab-ops/recovery-board?mode=watch",
            },
        ],
        "scanner_architecture_cases": [
            {
                "case_id": "scanner-euv-shift-brief",
                "focus_tool": "scanner-euv-02",
                "goal": "Keep field response, subsystem escalation, and qualification review tied together.",
                "next_surface": "/api/scanner/architecture-pack",
            },
            {
                "case_id": "scanner-customer-readiness",
                "focus_tool": "scanner-arg-11",
                "goal": "Explain why a customer milestone should pause until qualification blockers clear.",
                "next_surface": "/api/scanner/customer-readiness",
            },
        ],
        "operator_checks": [
            {
                "check_id": "health-first",
                "surface": "/health",
                "why_it_matters": "Operators should confirm both domains are online before drilling into lots or incidents.",
            },
            {
                "check_id": "export-proof-board",
                "surface": "/api/export-proof-board",
                "why_it_matters": "Platform-level export proof should stay visible before reviewers trust either domain handoff story.",
            },
            {
                "check_id": "fab-architecture-pack",
                "surface": "/api/fab-ops/architecture-pack",
                "why_it_matters": "Fab posture should stay reviewable from synthetic SPC evidence to an HMAC integrity envelope.",
            },
            {
                "check_id": "fab-spc-executed-evidence",
                "surface": "/api/fab-ops/v1/evals/replays",
                "why_it_matters": "Expected and actual SPC/disposition assertions should execute rather than appear as static pass labels.",
            },
            {
                "check_id": "scanner-architecture-pack",
                "surface": "/api/scanner/architecture-pack",
                "why_it_matters": "Scanner qualification and handoff evidence should stay visible without extra tooling.",
            },
            {
                "check_id": "metrics-check",
                "surface": "/metrics",
                "why_it_matters": "Latency and request counters should back the runtime story after the review surfaces line up.",
            },
        ],
        "validation_cases": [
            {
                "case_id": "fab-release-block",
                "goal": "A critical lot should remain blocked until maintenance and review gates clear.",
                "proof_surface": "/api/fab-ops/release-gate?lot_id=lot-8812",
            },
            {
                "case_id": "fab-spc-boundaries",
                "goal": "Western Electric boundaries and the centerline negative case should execute against the packaged fixture.",
                "proof_surface": "/api/fab-ops/v1/evals/replays",
            },
            {
                "case_id": "fab-handoff-signature",
                "goal": "HMAC envelopes should expose digest, algorithm, and verification details without claiming human approval.",
                "proof_surface": "/api/fab-ops/shift-handoff/signature",
            },
            {
                "case_id": "scanner-qualification",
                "goal": "Qualification blockers should remain visible in scanner review surfaces.",
                "proof_surface": "/api/scanner/qualification-board",
            },
            {
                "case_id": "scanner-handoff-proof",
                "goal": "Scanner handoff verification should remain tied to signed export evidence.",
                "proof_surface": "/api/scanner/shift-handoff/verify",
            },
        ],
        "architecture_fast_path": [
            "/health",
            "/api/resource-pack",
            "/api/export-proof-board",
            "/api/fab-ops/runtime/brief",
            "/api/fab-ops/v1/control-plan",
            "/api/fab-ops/v1/lots/lot-8812/disposition",
            "/api/fab-ops/v1/evals/replays",
            "/api/fab-ops/architecture-pack",
            "/api/scanner/runtime/brief",
            "/api/scanner/architecture-pack",
            "/metrics",
        ],
    }


def _count_csv_rows(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open(newline="", encoding="utf-8") as handle:
        return max(0, sum(1 for _ in csv.reader(handle)) - 1)


def _preview_csv_rows(path: Path, limit: int = 2, width: int = 6) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        rows: list[dict[str, str]] = []
        for index, row in enumerate(reader):
            if index >= limit:
                break
            rows.append({f"col_{offset + 1}": value for offset, value in enumerate(row[:width])})
    return rows
