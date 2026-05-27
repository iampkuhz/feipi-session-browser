"""T034: Project detail table structure gate test.

Locks the project.html session table structure to three contracts:
1. Title cell contains a real link to the session detail page
   (pattern: <a href="/sessions/{{ s.agent }}/{{ s.session_id }}"> or equivalent)
2. Rounds column does NOT use hardcoded em dash '—' as static text;
   should reference s.assistant_message_count or an explicit round_count variable
3. Table is wrapped in ui.table_card macro, which produces a .table-card class

Expected: Tests 1 and 2 FAIL on current code (title plain text, rounds hardcoded).
Test 3 should PASS (table_card is already used on line 112 of project.html).
"""
import pytest
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_DIR = ROOT / "src" / "session_browser" / "web" / "templates"

PROJECT_HTML = TEMPLATE_DIR / "project.html"
UI_PRIMITIVES = TEMPLATE_DIR / "components" / "ui_primitives.html"


def _read_template(path: Path) -> str:
    if not path.exists():
        pytest.skip(f"{path.name} not found at {path}")
    return path.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def project_html():
    return _read_template(PROJECT_HTML)


@pytest.fixture(scope="module")
def ui_primitives_html():
    return _read_template(UI_PRIMITIVES)


# ── T034: title cell must have a real link ────────────────────────────────


class TestProjectDetailTitleLink:
    """

import Title cell in project.html session rows must contain an <a href>
    linking to the session detail page.

    Contract: inside the tbody of #project-sessions-table, the first <td>
    (Title column) must include an <a href="/sessions/..."> element.
    Plain text title like {{ s.title }} without a link is insufficient.
    """

    def _extract_title_td_content(self, html: str) -> str:
        """Extract the content of the Title <td> inside the session row tbody."""
        # Find the table body
        table_match = re.search(
            r'<table[^>]*id="project-sessions-table"[^>]*>(.*?)</table>',
            html, re.DOTALL,
        )
        if not table_match:
            return ""
        tbody_match = re.search(r'<tbody>(.*?)</tbody>', table_match.group(1), re.DOTALL)
        if not tbody_match:
            return ""
        tbody = tbody_match.group(1)
        # Extract first <td> inside a {% for s in sessions %} loop
        # Look for the Title column <td> content
        td_match = re.search(r'<td>\s*<div class="title-main">(.*?)</div>', tbody, re.DOTALL)
        return td_match.group(1) if td_match else ""

    @pytest.mark.contract_case("UI-PROJECTS-003")
    def test_title_cell_contains_link(self, project_html):
        """Title cell must contain an <a href> to session detail page."""
        title_content = self._extract_title_td_content(project_html)
        assert title_content, "No Title <td> with <div class=\"title-main\"> found in project.html"

        has_link = "<a href" in title_content
        assert has_link, (
            "Title cell in project.html lacks an <a href> link to session detail. "
            f"Current title content: {title_content[:200]}. "
            "Must include <a href=\"/sessions/{{ s.agent }}/{{ s.session_id }}\"> or equivalent."
        )

    @pytest.mark.contract_case("UI-PROJECTS-003")
    def test_title_link_follows_session_url_pattern(self, project_html):
        """If a link exists, it should follow the canonical session URL pattern."""
        title_content = self._extract_title_td_content(project_html)
        if not title_content:
            pytest.skip("No title cell content found")

        # Check for the canonical pattern: /sessions/{{ s.agent }}/{{ s.session_id }}
        # or the rendered equivalent: /sessions/
        has_session_link = bool(re.search(
            r'/sessions/\{\{.*?s\.agent.*?\}/\{\{.*?s\.session_id.*?\}\}',
            title_content,
        )) or "/sessions/" in title_content

        assert has_session_link, (
            "Title link does not follow canonical session URL pattern "
            "/sessions/<agent>/<session_id>. "
            f"Current title content: {title_content[:200]}"
        )


# ── T034: Rounds column must NOT hardcode em dash ─────────────────────────


class TestProjectDetailRoundsColumn:
    """Rounds column in project.html must NOT use a hardcoded em dash '—'.

    Contract: the Rounds <td> should reference s.assistant_message_count
    or an explicit round_count variable derived from session data.
    A static <td class="num mono">—</td> is a known bug.
    """

    def _extract_rounds_td(self, html: str) -> str:
        """Extract the Rounds column <td> from the session row tbody.

        Column order in project.html tbody:
          1. Title (plain <td>)
          2. Agent (plain <td>)
          3. Model (<td class="mono">)
          4. Tokens (<td class="token-cell">)
          5. Rounds (<td class="num mono">)  ← first num mono
          6. Tools (<td class="num mono">)    ← second num mono
          7. Duration (<td class="col-num mono">)

        So the Rounds column is the FIRST <td class="num mono">.
        """
        table_match = re.search(
            r'<table[^>]*id="project-sessions-table"[^>]*>(.*?)</table>',
            html, re.DOTALL,
        )
        if not table_match:
            return ""
        tbody_match = re.search(r'<tbody>(.*?)</tbody>', table_match.group(1), re.DOTALL)
        if not tbody_match:
            return ""
        tbody = tbody_match.group(1)

        # Find all <td class="num mono"> — Rounds is the FIRST one
        num_mono_tds = re.findall(r'<td class="num mono">(.*?)</td>', tbody, re.DOTALL)
        if num_mono_tds:
            return num_mono_tds[0]  # Rounds is the first numeric column after token-cell
        return ""

    @pytest.mark.contract_case("UI-PROJECTS-003")
    def test_rounds_not_hardcoded_em_dash(self, project_html):
        """Rounds column must NOT be a hardcoded em dash."""
        rounds_td = self._extract_rounds_td(project_html)

        # The em dash character '—' (U+2014) or HTML entity &#8212; or &mdash;
        hardcoded_em_dash = (
            rounds_td.strip() == '—'
            or rounds_td.strip() == '&#8212;'
            or rounds_td.strip() == '&mdash;'
        )

        assert not hardcoded_em_dash, (
            "Rounds column in project.html uses a hardcoded em dash '—'. "
            f"Current content: {rounds_td!r}. "
            "Must use s.assistant_message_count or an explicit round_count variable."
        )

    @pytest.mark.contract_case("UI-PROJECTS-003")
    def test_rounds_uses_session_data(self, project_html):
        """Rounds column should reference session data like assistant_message_count."""
        rounds_td = self._extract_rounds_td(project_html)

        # Look for template variables that reference session round data
        uses_session_data = bool(re.search(
            r's\.assistant_message_count|s\.round_count|s\.num_rounds|round_count',
            rounds_td,
        ))

        assert uses_session_data, (
            "Rounds column does not reference any session data variable "
            "(s.assistant_message_count or similar). "
            f"Current content: {rounds_td[:200]!r}. "
            "Must display actual round counts from session data."
        )


# ── T034: Table must use table_card macro ─────────────────────────────────


class TestProjectDetailTableCardWrapper:
    """The session table in project.html must be wrapped in ui.table_card,
    which produces a <section class="card table-card"> element.

    Contract: project.html must either:
    - Call {% call ui.table_card(...) %}, OR
    - Produce HTML with class="table-card" on the table wrapper section
    """

    @pytest.mark.contract_case("UI-PROJECTS-003")
    def test_uses_table_card_macro(self, project_html):
        """project.html must call ui.table_card macro."""
        uses_macro = "ui.table_card" in project_html
        assert uses_macro, (
            "project.html does not call ui.table_card macro. "
            "The session table must be wrapped in the table_card composite."
        )

    @pytest.mark.contract_case("UI-PROJECTS-003")
    def test_table_card_produces_correct_class(self, ui_primitives_html):
        """The table_card macro in ui_primitives must produce .table-card class."""
        # Find the table_card macro definition and check it produces card table-card
        macro_match = re.search(
            r'{% macro table_card\(.*?%}(.*?){%- endmacro %}',
            ui_primitives_html, re.DOTALL,
        )
        assert macro_match, "table_card macro not found in ui_primitives.html"

        macro_body = macro_match.group(1)
        has_table_card_class = "'table-card'" in macro_body or '"table-card"' in macro_body
        assert has_table_card_class, (
            "table_card macro does not produce 'table-card' class. "
            "The macro must include 'table-card' in its section class."
        )
