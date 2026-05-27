"""Web static contract: agents-cell layout discipline (P-20 / T026).
Ensures that:
1. `.agents-cell` in projects.css does NOT define `display: flex`
   (flex on <td> breaks consistent border-height with adjacent cells).
2. The agents-cell in the HTML template contains a wrapper element
   (e.g. `agents-cell__inner`) for layout isolation.
"""

import pytest

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROJECTS_CSS = ROOT / "src" / "session_browser" / "web" / "static" / "css" / "projects.css"
PROJECTS_HTML = ROOT / "src" / "session_browser" / "web" / "templates" / "projects.html"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ── Contract 1: .agents-cell must NOT define display:flex ─────────


@pytest.mark.contract_case("UI-VISUAL-001")
def test_agents_cell_no_display_flex_in_css():
    """.agents-cell 规则块内不得包含 display: flex / display:flex。"""
    css = _read(PROJECTS_CSS)
    # Extract the .agents-cell rule block (from selector to next selector or EOF)
    import re
    match = re.search(r"\.agents-cell\s*\{([^}]*)\}", css)
    assert match, ".agents-cell selector not found in projects.css"

    block = match.group(1)
    # Check for any form of display:flex (with/without space)
    has_flex = re.search(r"display\s*:\s*flex", block, re.IGNORECASE)
    assert not has_flex, (
        f".agents-cell rule block contains display:flex, which breaks "
        f"border-height alignment with adjacent cells. Found: '{has_flex.group(0)}'"
    )


# ── Contract 2: agents-cell must have an inner wrapper ────────────


@pytest.mark.contract_case("UI-VISUAL-001")
def test_agents_cell_has_inner_wrapper_in_html():
    """agents-cell 内部必须包含 wrapper 元素（如 agents-cell__inner）。"""
    html = _read(PROJECTS_HTML)
    # Look for the agents-cell td that contains an inner wrapper
    import re
    # Match <td class="agents-cell"> ... </td>
    td_match = re.search(
        r'<td\s+class="agents-cell">(.*?)</td>',
        html, re.DOTALL
    )
    assert td_match, "No <td class=\"agents-cell\"> found in projects.html"

    td_content = td_match.group(1)
    # Check for any inner wrapper element with agents-cell related class
    has_wrapper = re.search(r'class="agents-cell__\w+"', td_content)
    assert has_wrapper, (
        "agents-cell <td> lacks an inner wrapper element (e.g. agents-cell__inner). "
        "Wrap the badge macros inside a <div> or <span> with a dedicated class."
    )


@pytest.mark.contract_case("UI-VISUAL-001")
def test_agents_cell_inner_class_named_consistently():
    """agents-cell 的 wrapper 类名应遵循 BEM 约定（agents-cell__inner 或类似）。"""
    html = _read(PROJECTS_HTML)
    import re
    td_match = re.search(
        r'<td\s+class="agents-cell">(.*?)</td>',
        html, re.DOTALL
    )
    if not td_match:
        return  # covered by previous test

    td_content = td_match.group(1)
    has_inner = re.search(r'agents-cell__inner', td_content)
    assert has_inner, (
        "agents-cell wrapper should use BEM naming: agents-cell__inner"
    )
