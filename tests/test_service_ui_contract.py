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
        'id="synthetic-data-banner"',
        'id="spc-evidence-panel"',
        'id="spc-control-plan"',
        'id="spc-disposition"',
        'id="spc-flow-authority"',
        "Synthetic fixture only:",
        "HMAC Envelope (Not Approval)",
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
        'text: `/api/fab-ops/tool-ownership?tool_id=${selectedToolId || "pending-tool"}`',
        'text: `/api/fab-ops/recovery-board?mode=${selectedRecoveryMode}`',
    ]
    for text_assignment in safe_dynamic_text:
        assert text_assignment in javascript


def test_ui_calls_mounted_versioned_spc_routes_and_labels_simulation() -> None:
    html = INDEX_HTML.read_text(encoding="utf-8")
    javascript = APP_JS.read_text(encoding="utf-8")

    for route in (
        "/api/fab-ops/v1/control-plan",
        '/api/fab-ops/v1/lots/${encodeURIComponent(selectedLotId || "lot-8812")}/disposition',
        "/api/fab-ops/v1/evals/replays",
    ):
        assert route in javascript
    assert "/api/runtime/brief" not in javascript
    assert "/api/release-gate" not in javascript
    assert "Simulated Workflow Risk" in html
    assert "Human-Reviewed Recommendation" in html
    assert "signed_by" not in javascript
    assert "item.case_id || item.scenario" in javascript
    assert "item.actual?.recommendation" in javascript
    assert "assertions passed" in javascript


def test_recorded_fallback_never_claims_executed_replay_passes() -> None:
    javascript = APP_JS.read_text(encoding="utf-8")
    recorded = javascript.split("const RECORDED_FAB =", maxsplit=1)[1].split(
        "const REVIEW_LENSES", maxsplit=1
    )[0]
    all_failed = javascript.split("if (allFailed)", maxsplit=1)[1].split(
        "const degradedPanels", maxsplit=1
    )[0]

    assert 'status: "unavailable"' in recorded
    assert "score_pct" not in recorded
    assert 'status: "pass"' not in recorded
    assert "replay-passed" not in recorded
    assert "replay stays green" not in recorded
    assert 'replayScore.textContent = "--"' in all_failed
    assert "Executed replay evidence unavailable" in all_failed
    assert "no executed replay result is available as evidence" in recorded
