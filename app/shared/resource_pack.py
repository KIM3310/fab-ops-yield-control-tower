from __future__ import annotations

from typing import Any

from app.domains.fab_ops.domain import ALARMS, LOTS_AT_RISK
from app.domains.scanner.domain import FIELD_INCIDENTS


def build_platform_resource_pack() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "semiconductor-ops-platform-resource-pack",
        "contract_version": "semiconductor-ops-resource-pack-v1",
        "intended_use": "review-safe manufacturing scenarios and controls without plant telemetry",
        "summary": {
            "fab_alarm_count": len(ALARMS),
            "fab_lot_count": len(LOTS_AT_RISK),
            "scanner_incident_count": len(FIELD_INCIDENTS),
            "operator_check_count": 4,
            "validation_case_count": 4,
        },
        "fab_review_cases": [
            {
                "case_id": "fab-critical-plasma-instability",
                "focus_lot": "lot-8812",
                "goal": "Explain why a severe lot remains blocked until maintenance and reroute review align.",
                "next_surface": "/api/fab-ops/release-board",
            },
            {
                "case_id": "fab-temperature-drift-watch",
                "focus_lot": "lot-8821",
                "goal": "Show how watch posture differs from a hard release block.",
                "next_surface": "/api/fab-ops/recovery-board?mode=watch",
            },
        ],
        "scanner_review_cases": [
            {
                "case_id": "scanner-euv-shift-brief",
                "focus_tool": "scanner-euv-02",
                "goal": "Keep field response, subsystem escalation, and qualification review tied together.",
                "next_surface": "/api/scanner/review-pack",
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
                "why_it_matters": "Reviewers should confirm both domains are online before drilling into lots or incidents.",
            },
            {
                "check_id": "fab-review-pack",
                "surface": "/api/fab-ops/review-pack",
                "why_it_matters": "Fab posture should stay reviewable from alarm to signed handoff.",
            },
            {
                "check_id": "scanner-review-pack",
                "surface": "/api/scanner/review-pack",
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
                "case_id": "fab-handoff-signature",
                "goal": "Shift handoff signatures should expose digest, algorithm, and verification details together.",
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
        "reviewer_fast_path": [
            "/health",
            "/api/resource-pack",
            "/api/fab-ops/runtime/brief",
            "/api/fab-ops/review-pack",
            "/api/scanner/runtime/brief",
            "/api/scanner/review-pack",
            "/metrics",
        ],
    }
