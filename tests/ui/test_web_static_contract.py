"""Java web static contracts for Projects resources."""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PROJECTS_CSS = ROOT / 'java/web/src/main/resources/static/css/projects.css'
PROJECTS_HTML = ROOT / 'java/web/src/main/resources/templates/projects.html'
PROJECTS_JS = ROOT / 'java/web/src/main/resources/static/js/projects.js'


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


@pytest.mark.contract_case('UI-VISUAL-001')
def test_projects_table_matches_main_dom_contract():
    html = _read(PROJECTS_HTML)
    js = _read(PROJECTS_JS)
    for label in [
        'Project',
        'Agents',
        'Sessions',
        'Tokens',
        'Tools',
        'Failed',
        'First Seen',
        'Last Active',
    ]:
        assert label in html
    assert 'id="projects-table"' in html
    assert 'data-api-rows="/api/projects/rows"' in html
    assert 'class="agents-cell"' in js
    assert 'class="agents-cell__inner"' in js
    assert 'tokenbar-seg fresh' in js
    assert 'Token Breakdown' in js


@pytest.mark.contract_case('UI-VISUAL-001')
def test_agents_cell_layout_isolated_in_inner_wrapper():
    css = _read(PROJECTS_CSS)
    agents_rule_match = None
    import re

    for match in re.finditer(r'\.p-projects\s+\.agents-cell\s*\{([^}]*)\}', css, re.S):
        agents_rule_match = match.group(1)
        break
    assert agents_rule_match is not None
    assert 'display: flex' not in agents_rule_match
    assert '.agents-cell__inner' in css
