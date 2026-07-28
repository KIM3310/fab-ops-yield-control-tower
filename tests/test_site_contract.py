from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX_HTML = ROOT / "site" / "index.html"
README = ROOT / "README.md"


def test_focus_lot_static_surface_contract() -> None:
    html = INDEX_HTML.read_text(encoding="utf-8")
    required_tokens = [
        'id="focus-lot-panel"',
        'id="copyLotPathBtn"',
        "Lot-8812 stays visible from hold decision to signed handoff.",
        "Fast path: runtime brief → recovery board → release gate → shift handoff signature.",
    ]

    for token in required_tokens:
        assert token in html, token


def test_copy_lot_path_uses_mounted_fab_ops_routes() -> None:
    html = INDEX_HTML.read_text(encoding="utf-8")
    expected_paths = [
        "- /api/fab-ops/runtime/brief",
        "- /api/fab-ops/recovery-board?mode=hold",
        "- /api/fab-ops/release-gate?lot_id=lot-8812",
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
