from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX_HTML = ROOT / "app" / "static" / "index.html"
APP_JS = ROOT / "app" / "static" / "app.js"


def test_service_ui_focus_route_contract() -> None:
    html = INDEX_HTML.read_text(encoding="utf-8")
    required_tokens = [
        'id="focus-severe-lot-btn"',
        'id="copy-architecture-route-btn"',
        'id="copy-shift-snapshot-btn"',
        'id="continuity-checkpoint-panel"',
        'id="continuity-owner-lane"',
        'id="continuity-proof-freshness"',
        'id="continuity-signature"',
        'id="continuity-guard"',
        'id="continuity-blockers"',
        'id="storyline-route"',
        "Start with the severe lot, then compare recovery and release posture before copying a handoff.",
        "Shift continuity stays blocked until owner, release gate, and signature line up.",
        "Gate blockers stay visible with the focused lot before any shift handoff is copied.",
    ]

    for token in required_tokens:
        assert token in html, token


def test_storyline_rich_text_does_not_reinterpret_dom_values_as_html() -> None:
    javascript = APP_JS.read_text(encoding="utf-8")
    renderer = javascript.split("function renderRichBulletList", maxsplit=1)[1].split(
        "function renderList", maxsplit=1
    )[0]

    assert "innerHTML" not in renderer
    assert "document.createTextNode(segment)" in renderer
    assert 'node.textContent = String(segment.text ?? "")' in renderer
    assert "html:" not in javascript

    safe_dynamic_text = [
        '{ tag: "strong", text: storyLotId }',
        'text: `/api/tool-ownership?tool_id=${selectedToolId || "pending-tool"}`',
        'text: `/api/recovery-board?mode=${selectedRecoveryMode}`',
    ]
    for text_assignment in safe_dynamic_text:
        assert text_assignment in javascript
