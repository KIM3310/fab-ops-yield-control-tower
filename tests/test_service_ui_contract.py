from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX_HTML = ROOT / "app" / "static" / "index.html"


def test_service_ui_focus_route_contract() -> None:
    html = INDEX_HTML.read_text(encoding="utf-8")
    required_tokens = [
        'id="focus-severe-lot-btn"',
        'id="copy-review-route-btn"',
        'id="copy-shift-snapshot-btn"',
        'id="storyline-route"',
        'Start with the severe lot, then compare recovery and release posture before copying a handoff.',
    ]

    for token in required_tokens:
        assert token in html, token
