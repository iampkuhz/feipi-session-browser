from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def test_no_inline_onclick_in_templates():
    for path in (ROOT / 'src/session_browser/web/templates').rglob('*.html'):
        text = path.read_text(encoding='utf-8', errors='ignore')
        assert 'onclick=' not in text, path

def test_no_versioned_css_imports():
    bad = ['session-browser-v', 'dashboard-v', '-patch.css', '-fix.css', '-overlay.css']
    for path in (ROOT / 'src/session_browser/web/templates').rglob('*.html'):
        text = path.read_text(encoding='utf-8', errors='ignore')
        for marker in bad:
            assert marker not in text, f'{marker} in {path}'
