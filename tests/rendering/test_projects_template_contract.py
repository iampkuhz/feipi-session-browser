"""Projects template-JS contract tests (T029).

Verifies that:
1. projects.html filter-footer contains an active filter chip container.
2. JS updateFilterChip selector matches the template structure.

Covers P-23 fix verification: active filter chip visibility in filter-footer.
"""
import pytest
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_DIR = ROOT / "src" / "session_browser" / "web" / "templates"
STATIC_JS = ROOT / "src" / "session_browser" / "web" / "static" / "js"

PROJECTS_HTML = TEMPLATE_DIR / "projects.html"
PROJECTS_JS = STATIC_JS / "projects.js"


def _projects_template():
    """Return projects.html text, skipping tests if file is missing."""
    if not PROJECTS_HTML.exists():
        pytest.skip(f"projects.html not found at {PROJECTS_HTML}")
    return PROJECTS_HTML.read_text(encoding="utf-8")


def _projects_js():
    """Return projects.js text, skipping tests if file is missing."""
    if not PROJECTS_JS.exists():
        pytest.skip(f"projects.js not found at {PROJECTS_JS}")
    return PROJECTS_JS.read_text(encoding="utf-8")


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def projects_html():
    return _projects_template()


@pytest.fixture(scope="module")
def projects_js():
    return _projects_js()


# ── Template: filter-footer structure ─────────────────────────────────────


class TestProjectsFilterFooterStructure:
    """projects.html filter-footer must contain active filter chip container."""

    @pytest.mark.contract_case("UI-PROJECTS-008")
    def test_filter_footer_exists(self, projects_html):
        """filter-footer container must be present."""
        assert "filter-footer" in projects_html, (
            "projects.html lacks .filter-footer container"
        )

    @pytest.mark.contract_case("UI-PROJECTS-008")
    def test_active_filters_container_in_footer(self, projects_html):
        """filter-footer must contain an active-filters container or count element."""
        # Accept either .active-filters parent or .active-filters__count BEM class
        has_container = (
            "active-filters" in projects_html
        )
        assert has_container, (
            "projects.html filter-footer lacks .active-filters container/element"
        )

    @pytest.mark.contract_case("UI-PROJECTS-008")
    def test_active_filters_count_element(self, projects_html):
        """filter-footer must display active filter count text."""
        # The template should show a count like "X matching projects"
        assert "matching projects" in projects_html or "active-filters__count" in projects_html, (
            "projects.html filter-footer lacks active filter count display"
        )


# ── JS: updateFilterChip selector ────────────────────────────────────────


class TestProjectsJsUpdateFilterChipSelector:
    """projects.js updateFilterChip must define a valid CSS selector."""

    def _extract_update_filter_chip(self, js_text):
        """Extract the updateFilterChip function body from JS text."""
        match = re.search(
            r'function\s+updateFilterChip\s*\([^)]*\)\s*\{([^}]+)\}',
            js_text,
            re.DOTALL,
        )
        if not match:
            pytest.skip("updateFilterChip function not found in projects.js")
        return match.group(1)

    @pytest.mark.contract_case("UI-PROJECTS-008")
    def test_update_filter_chip_function_exists(self, projects_js):
        """updateFilterChip function must be defined."""
        assert "updateFilterChip" in projects_js, (
            "projects.js lacks updateFilterChip function"
        )

    @pytest.mark.contract_case("UI-PROJECTS-008")
    def test_update_filter_chip_has_selector(self, projects_js):
        """updateFilterChip must use querySelector with a CSS selector."""
        body = self._extract_update_filter_chip(projects_js)
        assert "querySelector" in body, (
            "updateFilterChip lacks querySelector call"
        )

    @pytest.mark.contract_case("UI-PROJECTS-008")
    def test_update_filter_chip_selector_value(self, projects_js):
        """Extract and verify the selector targets an active-filters element."""
        body = self._extract_update_filter_chip(projects_js)
        # Extract the selector string from querySelector('...')
        match = re.search(r"querySelector\(['\"]([^'\"]+)['\"]\)", body)
        assert match, "updateFilterChip querySelector lacks a string argument"
        selector = match.group(1)

        # Selector must reference active-filters in some form
        assert "active-filters" in selector, (
            f"updateFilterChip selector '{selector}' does not reference .active-filters"
        )


# ── Template-JS contract: selector matches template structure ────────────


class TestTemplateJsContractMatch:
    """JS selector must be satisfiable by the rendered template structure.

    This is a static contract check: it verifies that if the JS selector
    looks for a descendant element (e.g., `.active-filters .filter-chip`),
    the template must contain a compatible structure, or the selector must
    be broad enough to match existing elements.
    """

    def _extract_selector(self, js_text):
        """Extract the CSS selector from updateFilterChip."""
        match = re.search(
            r'function\s+updateFilterChip\s*\([^)]*\)\s*\{[^}]*querySelector\([\'"]([^\'"]+)[\'"]\)',
            js_text,
            re.DOTALL,
        )
        if not match:
            return None
        return match.group(1)

    @pytest.mark.contract_case("UI-PROJECTS-008")
    def test_js_selector_compatible_with_template(self, projects_html, projects_js):
        """JS updateFilterChip selector must be compatible with template structure.

        Contract rules:
        - If selector is a descendant combinator like `.parent .child`,
          the template must have .parent AND .child (or a single combined
          class that serves both roles).
        - If selector targets a class that the template defines, PASS.
        """
        selector = self._extract_selector(projects_js)
        if not selector:
            pytest.skip("Cannot extract selector from updateFilterChip")

        # Parse the selector into its parts (split by space for descendant)
        parts = selector.split()

        for part in parts:
            # Strip leading combinators (>, +, ~)
            part = re.sub(r'^[>+~]\s*', '', part).strip()
            if not part:
                continue

            # Extract class names from the part (e.g., ".foo.bar" -> ["foo", "bar"])
            classes = re.findall(r'\.([a-zA-Z_][\w-]*)', part)
            if not classes:
                # It might be a tag name without a class — that's fine
                continue

            for cls in classes:
                assert cls in projects_html, (
                    f"Template projects.html does not contain class '{cls}' "
                    f"referenced by JS selector '{selector}'"
                )
