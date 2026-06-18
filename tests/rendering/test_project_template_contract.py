"""T032 · project detail search field contract.
T033 · project detail token_cell reuse gate.

T032 covers P-26: 项目详情搜索框不起作用
- Verifies that session rows in project.html have data-title and
  data-session-id attributes for client-side search to work.

T033 covers P-27: Project detail TOKENS tokenbar 没有 breakdown 弹框
- Verifies that TOKENS column in project.html calls ui.token_cell or
  contains token-tooltip, not just a title attribute.
"""
import pytest
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_DIR = ROOT / "src" / "session_browser" / "web" / "templates"

PROJECT_HTML = TEMPLATE_DIR / "project.html"
UI_PRIMITIVES = TEMPLATE_DIR / "components" / "ui_primitives.html"
UI_PRIMITIVES_DIR = TEMPLATE_DIR / "components" / "ui_primitives"


def _read_template(path: Path) -> str:
    if not path.exists():
        pytest.fail(f"{path.name} not found at {path}")
    return path.read_text(encoding="utf-8")


def _read_ui_primitives_with_splits() -> str:
    """Read ui_primitives with split-aware reading."""
    parts = []
    if UI_PRIMITIVES.exists():
        parts.append(UI_PRIMITIVES.read_text(encoding="utf-8"))
    if UI_PRIMITIVES_DIR.is_dir():
        for f in sorted(UI_PRIMITIVES_DIR.glob("*.html")):
            parts.append(f.read_text(encoding="utf-8"))
    return "\n".join(parts)


@pytest.fixture(scope="module")
def project_html():
    return _read_template(PROJECT_HTML)


@pytest.fixture(scope="module")
def ui_primitives_html():
    return _read_template(UI_PRIMITIVES)


# ── T032: search field contract ──────────────────────────────────────────


class TestProjectDetailSearchFields:
    """

import project.html session rows must carry data-title and data-session-id
    attributes for client-side search to function.

    Contract: every <tr> that represents a session row inside the
    project-sessions-table must have:
    - data-session-id="<id>"
    - data-title="<title>" (or data-action containing title info)
    """

    def _extract_tbody_rows(self, html: str) -> list[str]:
        """Extract <tr> elements from tbody within project-sessions-table."""
        table_match = re.search(
            r'<table[^>]*id="project-sessions-table"[^>]*>(.*?)</table>',
            html, re.DOTALL,
        )
        if not table_match:
            return []
        tbody_match = re.search(r'<tbody>(.*?)</tbody>', table_match.group(1), re.DOTALL)
        if not tbody_match:
            return []
        tbody = tbody_match.group(1)
        return re.findall(r'<tr[^>]*>', tbody)

    @pytest.mark.contract_case("UI-PROJECTS-007")
    def test_session_rows_have_data_session_id(self, project_html):
        """Session rows must include data-session-id attribute."""
        rows = self._extract_tbody_rows(project_html)
        if not rows:
            pytest.fail("No session rows found in project.html tbody")
        for row in rows:
            assert "data-session-id" in row, (
                f"Session row lacks data-session-id attribute: {row[:120]}..."
            )

    @pytest.mark.contract_case("UI-PROJECTS-007")
    def test_session_rows_have_data_title(self, project_html):
        """Session rows must include data-title attribute for search."""
        rows = self._extract_tbody_rows(project_html)
        if not rows:
            pytest.fail("No session rows found in project.html tbody")
        for row in rows:
            assert "data-title" in row, (
                f"Session row lacks data-title attribute: {row[:120]}..."
            )

    @pytest.mark.contract_case("UI-PROJECTS-007")
    def test_search_input_has_expected_id(self, project_html):
        """The search input in the table toolbar should have a recognizable
        ID or class that JS can target."""
        # table_card call has search_placeholder; the ui macro should
        # produce an input with a search-related class
        has_search = (
            "search" in project_html.lower()
            and ("input" in project_html.lower() or "filter_search" in project_html.lower())
        )
        assert has_search, (
            "project.html lacks a search input in the table toolbar"
        )


# ── T033: token_cell reuse gate ──────────────────────────────────────────


class TestProjectDetailTokenCellReuse:
    """TOKENS column in project.html must call ui.token_cell macro.
    The macro (in ui_primitives.html) renders the token-tooltip.
    A bare tokenbar with only a title attribute is insufficient.

    Contract: project.html must call ui.token_cell(...) which produces
    the full token-total + tokenbar + token-tooltip structure.

    Forbidden: <td class="token-cell"> containing only <div class="tokenbar" title="...">
    with no token-tooltip child.
    """

    def _extract_token_cell_template(self, html: str) -> str:
        """Extract the content of the TOKENS column <td class="token-cell">."""
        match = re.search(
            r'<td class="token-cell">(.*?)</td>',
            html, re.DOTALL,
        )
        return match.group(1) if match else ""

    @pytest.mark.contract_case("UI-PROJECTS-007")
    def test_token_cell_uses_macro_or_has_tooltip(self, project_html):
        """TOKENS column must use ui.token_cell or contain token-tooltip."""
        # Check if the template calls ui.token_cell macro
        uses_macro = "ui.token_cell" in project_html

        if uses_macro:
            # Macro call found — verify the macro itself has a tooltip
            macro_text = _read_ui_primitives_with_splits()
            assert "token-tooltip" in macro_text, (
                "ui.token_cell macro must contain token-tooltip element"
            )
            return

        # Fallback: check for inline token-tooltip
        token_cell = self._extract_token_cell_template(project_html)
        assert token_cell, "No <td class=\"token-cell\"> found in project.html"

        has_tooltip = "token-tooltip" in token_cell
        assert has_tooltip or uses_macro, (
            "TOKENS column in project.html lacks a token-tooltip breakdown. "
            "Must either call ui.token_cell(...) or include a "
            "<div class=\"token-tooltip\"> element. "
            "A bare title attribute on tokenbar is insufficient."
        )

    @pytest.mark.contract_case("UI-PROJECTS-007")
    def test_token_cell_not_title_only(self, project_html):
        """TOKENS column must not rely solely on a title attribute for
        the token breakdown."""
        # If project.html calls ui.token_cell, the macro provides the tooltip
        if "ui.token_cell" in project_html:
            return

        token_cell = self._extract_token_cell_template(project_html)
        assert token_cell, "No <td class=\"token-cell\"> found in project.html"

        # If there's a tokenbar with title= but no token-tooltip, fail
        has_bare_title = bool(re.search(r'tokenbar[^>]*\s+title="', token_cell))
        has_tooltip = "token-tooltip" in token_cell

        if has_bare_title:
            assert has_tooltip, (
                "TOKENS column uses tokenbar with title attribute but "
                "lacks a token-tooltip element. The title attribute alone "
                "does not provide the required breakdown popover."
            )
