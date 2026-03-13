from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX_HTML = ROOT / "app" / "static" / "index.html"


def test_service_ui_focus_route_contract() -> None:
    html = INDEX_HTML.read_text(encoding="utf-8")
    required_tokens = [
        'id="focus-severe-lot-btn"',
        'id="copy-review-route-btn"',
        'id="copy-shift-snapshot-btn"',
        'id="continuity-checkpoint-panel"',
        'id="continuity-owner-lane"',
        'id="continuity-proof-freshness"',
        'id="continuity-signature"',
        'id="continuity-guard"',
        'id="continuity-blockers"',
        'id="storyline-route"',
        'Start with the severe lot, then compare recovery and release posture before copying a handoff.',
        'Shift continuity stays blocked until owner, release gate, and signature line up.',
        'Gate blockers stay visible with the focused lot before any shift handoff is copied.',
    ]

    for token in required_tokens:
        assert token in html, token
