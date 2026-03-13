from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX_HTML = ROOT / "site" / "index.html"


def test_focus_lot_static_surface_contract() -> None:
    html = INDEX_HTML.read_text(encoding="utf-8")
    required_tokens = [
        'id="focus-lot-panel"',
        'id="copyLotPathBtn"',
        'Lot-8812 stays visible from hold decision to signed handoff.',
        'Fast path: runtime brief → recovery board → release gate → shift handoff signature.',
    ]

    for token in required_tokens:
        assert token in html, token
