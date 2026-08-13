from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX_HTML = ROOT / "site" / "index.html"
GUIDE_HTML = ROOT / "site" / "guide.html"
README = ROOT / "README.md"


def test_focus_lot_static_surface_contract() -> None:
    html = INDEX_HTML.read_text(encoding="utf-8")
    required_tokens = [
        'id="focus-lot-panel"',
        'id="copyLotPathBtn"',
        "Lot-8812 stays visible from synthetic SPC containment to HMAC integrity evidence.",
        "Fast path: control plan → executed disposition → replay assertions → HMAC integrity envelope.",
    ]

    for token in required_tokens:
        assert token in html, token

    assert "run.app" not in html
    assert "now live on Cloud Run" not in html


def test_copy_lot_path_uses_mounted_fab_ops_routes() -> None:
    html = INDEX_HTML.read_text(encoding="utf-8")
    expected_paths = [
        "- /api/fab-ops/runtime/brief",
        "- /api/fab-ops/recovery-board?mode=hold",
        "- /api/fab-ops/release-gate?lot_id=lot-8812",
        "- /api/fab-ops/v1/lots/lot-8812/disposition",
        "- /api/fab-ops/shift-handoff/signature",
    ]

    for path in expected_paths:
        assert path in html, path

    stale_paths = [
        "- /api/runtime/brief",
        "- /api/recovery-board?mode=hold",
        "- /api/release-gate?lot_id=lot-8812",
        "- /api/shift-handoff/signature",
    ]
    for path in stale_paths:
        assert path not in html, path


def test_readme_aws_activation_matches_runtime_gate() -> None:
    readme = README.read_text(encoding="utf-8")
    aws_section = readme.split("**AWS**", maxsplit=1)[1].split("\n\n", maxsplit=1)[0]

    assert "set both" in aws_section
    assert "AWS_ACCESS_KEY_ID" in aws_section
    assert "AWS_SECRET_ACCESS_KEY" in aws_section
    assert "AWS_SQS_QUEUE_URL" in aws_section
    assert "AWS_DYNAMODB_TABLE" in aws_section


def test_linked_guide_matches_synthetic_advisory_evidence_boundary() -> None:
    html = GUIDE_HTML.read_text(encoding="utf-8")
    required = (
        "Synthetic advisory demo",
        "hand-authored synthetic fixtures",
        "human_approval_status",
        "material_state_changed: false",
        "GET /api/fab-ops/v1/control-plan",
        "GET /api/fab-ops/v1/lots/lot-8812/disposition",
        "GET /api/fab-ops/v1/evals/replays",
        "POST /api/fab-ops/shift-handoff/verify",
        "If this API is unavailable, there is no replay-pass evidence.",
        "integrity and shared-key authenticity only",
        "not a signed human approval",
        "ENGINEERING_REVIEW",
        "simulated risk, never measured yield",
    )
    for token in required:
        assert token in html, token

    stale_claims = (
        "multi-cloud deployment",
        "Lots at risk by yield score",
        "Release gate decision (auth)",
        "Signed shift handoff envelope",
    )
    for claim in stale_claims:
        assert claim not in html, claim
