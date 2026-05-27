"""Gate test T035: Unified copy action contract.
Verifies that all copy buttons in the codebase follow the canonical contract:

  data-action="copy" + data-copy-text="<text-to-copy>"

The canonical handler lives in ui_primitives.js:handleCopy() and only reads
data-copy-text.  Any button that uses a non-canonical data-action (e.g.
copy-session, copy-project-path, copy-path, copy-session-id) or the legacy
data-clipboard-text attribute will NOT be handled by the unified handler
and constitutes a contract violation.

This is a gate/regression test.  Current bugs are expected to FAIL until
the source templates and JS are migrated.
"""


from __future__ import annotations

import pytest
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
TEMPLATE_DIR = ROOT / "src" / "session_browser" / "web" / "templates"
JS_DIR = ROOT / "src" / "session_browser" / "web" / "static" / "js"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CANONICAL_ACTION = "copy"
CANONICAL_ATTR = "data-copy-text"
LEGACY_ATTR = "data-clipboard-text"

# data-action values that are NOT the canonical "copy".
# These are per-page JS handlers that bypass the unified ui_primitives.js handler.
NON_CANONICAL_ACTIONS = [
    "copy-session",
    "copy-session-id",
    "copy-project-path",
    "copy-path",
]


def _all_html_files():
    """Yield all .html files under the templates directory."""
    yield from TEMPLATE_DIR.rglob("*.html")


def _find_copy_buttons(html: str):
    """Return list of dicts describing each copy-like button in the HTML.

    Each dict has keys: data_action, has_copy_text, has_clipboard_text,
    has_session_id, file (the source file path).
    """
    results = []
    # Match <button ...> tags (single-line, no nested > in attributes)
    for btn in re.finditer(r'<button\b[^>]*>', html):
        attrs = btn.group(0)
        action_match = re.search(r'data-action="([^"]*)"', attrs)
        data_action = action_match.group(1) if action_match else None

        # Only care about copy-related buttons
        if data_action is None or "copy" not in data_action.lower():
            continue

        results.append({
            "data_action": data_action,
            "has_copy_text": "data-copy-text" in attrs,
            "has_clipboard_text": "data-clipboard-text" in attrs,
            "has_session_id": "data-session-id" in attrs,
        })
    return results


# ---------------------------------------------------------------------------
# T035-1: All HTML templates use canonical copy contract
# ---------------------------------------------------------------------------

class TestCopyActionContractTemplates:
    """Static scan: every copy button must use data-action="copy" + data-copy-text."""

    @pytest.mark.contract_case("UI-INTERACTION-005")
    def test_all_copy_buttons_use_canonical_data_action(self):
        """All copy buttons must use data-action="copy", not custom actions like
        copy-session, copy-project-path, copy-path, copy-session-id."""
        violations = []
        for html_file in _all_html_files():
            text = html_file.read_text(encoding="utf-8", errors="ignore")
            for btn in _find_copy_buttons(text):
                if btn["data_action"] != CANONICAL_ACTION:
                    violations.append(
                        f"{html_file.name}: data-action=\"{btn['data_action']}\" "
                        f"(expected \"{CANONICAL_ACTION}\")"
                    )
        assert not violations, (
            f"Non-canonical copy button actions found ({len(violations)}):\n"
            + "\n".join(violations)
        )

    @pytest.mark.contract_case("UI-INTERACTION-005")
    def test_all_copy_buttons_use_data_copy_text(self):
        """All copy buttons must carry data-copy-text, not the legacy data-clipboard-text."""
        violations = []
        for html_file in _all_html_files():
            text = html_file.read_text(encoding="utf-8", errors="ignore")
            for btn in _find_copy_buttons(text):
                if not btn["has_copy_text"]:
                    violations.append(
                        f"{html_file.name}: data-action=\"{btn['data_action']}\" "
                        f"missing {CANONICAL_ATTR}"
                    )
        assert not violations, (
            f"Copy buttons without {CANONICAL_ATTR} found ({len(violations)}):\n"
            + "\n".join(violations)
        )

    @pytest.mark.contract_case("UI-INTERACTION-005")
    def test_no_legacy_data_clipboard_text(self):
        """No copy button should use the legacy data-clipboard-text attribute."""
        violations = []
        for html_file in _all_html_files():
            text = html_file.read_text(encoding="utf-8", errors="ignore")
            for btn in _find_copy_buttons(text):
                if btn["has_clipboard_text"]:
                    violations.append(
                        f"{html_file.name}: data-action=\"{btn['data_action']}\" "
                        f"still uses legacy {LEGACY_ATTR}"
                    )
        assert not violations, (
            f"Copy buttons still using legacy {LEGACY_ATTR} ({len(violations)}):\n"
            + "\n".join(violations)
        )

    @pytest.mark.contract_case("UI-INTERACTION-005")
    def test_no_data_session_id_as_copy_fallback(self):
        """Buttons should not rely on data-session-id as a copy fallback;
        the text to copy should be in data-copy-text."""
        violations = []
        for html_file in _all_html_files():
            text = html_file.read_text(encoding="utf-8", errors="ignore")
            for btn in _find_copy_buttons(text):
                if btn["has_session_id"] and not btn["has_copy_text"]:
                    violations.append(
                        f"{html_file.name}: data-action=\"{btn['data_action']}\" "
                        f"uses data-session-id without data-copy-text"
                    )
        assert not violations, (
            f"Copy buttons using data-session-id without data-copy-text ({len(violations)}):\n"
            + "\n".join(violations)
        )


# ---------------------------------------------------------------------------
# T035-2: ui_primitives.js handleCopy supports canonical + backward compat
# ---------------------------------------------------------------------------

class TestUiPrimitivesCopyHandler:
    """Verify ui_primitives.js handleCopy reads both data-copy-text (canonical)
    and data-clipboard-text (backward compat fallback)."""

    _js_file = JS_DIR / "ui_primitives.js"

    @pytest.mark.contract_case("UI-INTERACTION-005")
    def test_handleCopy_exists(self):
        """The handleCopy function must be defined."""
        text = self._js_file.read_text(encoding="utf-8")
        assert "function handleCopy" in text, (
            f"{self._js_file}: handleCopy function not found"
        )

    @pytest.mark.contract_case("UI-INTERACTION-005")
    def test_handleCopy_reads_data_copy_text(self):
        """handleCopy must read data-copy-text as the primary source."""
        text = self._js_file.read_text(encoding="utf-8")
        # Extract the handleCopy function body
        match = re.search(
            r'function handleCopy\([^)]*\)\s*\{(.*?)(?=\n  //|  function |\n  window\.|}$)',
            text,
            re.DOTALL,
        )
        assert match, f"{self._js_file}: could not parse handleCopy body"
        body = match.group(1)
        assert "data-copy-text" in body, (
            f"{self._js_file}: handleCopy does not read data-copy-text"
        )

    @pytest.mark.contract_case("UI-INTERACTION-005")
    def test_handleCopy_data_copy_text_is_primary(self):
        """data-copy-text must be the FIRST attribute checked (primary), not a fallback."""
        text = self._js_file.read_text(encoding="utf-8")
        match = re.search(
            r'function handleCopy\([^)]*\)\s*\{(.*?)(?=\n  //|  function |\n  window\.|}$)',
            text,
            re.DOTALL,
        )
        assert match, f"{self._js_file}: could not parse handleCopy body"
        body = match.group(1)
        # The first getAttribute or getAttribute-style call should be for data-copy-text
        first_attr = re.search(
            r"(?:getAttribute\(['\"]|\.dataset\.)([^'\"]+)",
            body,
        )
        assert first_attr, f"{self._js_file}: no attribute read in handleCopy"
        assert first_attr.group(1) in ("data-copy-text", "copyText"), (
            f"{self._js_file}: handleCopy reads '{first_attr.group(1)}' first, "
            f"expected 'data-copy-text' as primary"
        )

    @pytest.mark.contract_case("UI-INTERACTION-005")
    def test_handleCopy_supports_backward_compat(self):
        """handleCopy should optionally fall back to data-clipboard-text or title for
        backward compatibility with legacy buttons."""
        text = self._js_file.read_text(encoding="utf-8")
        match = re.search(
            r'function handleCopy\([^)]*\)\s*\{(.*?)(?=\n  //|  function |\n  window\.|}$)',
            text,
            re.DOTALL,
        )
        assert match, f"{self._js_file}: could not parse handleCopy body"
        body = match.group(1)
        has_fallback = (
            "data-clipboard-text" in body
            or "clipboardText" in body
            or "title" in body
            or "textContent" in body
        )
        assert has_fallback, (
            f"{self._js_file}: handleCopy has no backward compat fallback "
            f"(expected data-clipboard-text or title/textContent)"
        )

    @pytest.mark.contract_case("UI-INTERACTION-005")
    def test_copy_registered_in_switch(self):
        """The click delegation switch must have a 'copy' case that calls handleCopy."""
        text = self._js_file.read_text(encoding="utf-8")
        assert "case 'copy':" in text, (
            f"{self._js_file}: no 'case \"copy\":' in the click delegation switch"
        )
        # Verify it calls handleCopy
        assert "handleCopy(" in text, (
            f"{self._js_file}: handleCopy is not called from the delegation switch"
        )


# ---------------------------------------------------------------------------
# T035-3: projects.js has no conflicting private copy handlers
# ---------------------------------------------------------------------------

class TestProjectsJsCopyHandlers:
    """Verify projects.js does not have private copy handlers that conflict
    with the unified ui_primitives.js contract.

    The canonical contract requires:
    - No addEventListener on [data-action="copy-project-path"] or
      [data-action="copy-session"] that bypasses the unified handler.
    - If page-specific copy logic exists, it must be compatible (i.e. reads
      both data-copy-text AND data-clipboard-text).
    """

    _js_file = JS_DIR / "projects.js"

    @pytest.mark.contract_case("UI-INTERACTION-005")
    def test_no_private_copy_project_path_handler(self):
        """projects.js must not register a private click handler on
        [data-action="copy-project-path"] that bypasses the unified handler."""
        text = self._js_file.read_text(encoding="utf-8")
        # Check for direct querySelectorAll on copy-project-path
        has_direct_handler = (
            'copy-project-path' in text
            and 'addEventListener' in text
        )
        assert not has_direct_handler, (
            f"{self._js_file}: has a private handler for copy-project-path "
            f"that bypasses the unified ui_primitives.js copy handler"
        )

    @pytest.mark.contract_case("UI-INTERACTION-005")
    def test_no_private_copy_session_handler(self):
        """projects.js must not register a private click handler on
        [data-action="copy-session"] that bypasses the unified handler."""
        text = self._js_file.read_text(encoding="utf-8")
        has_direct_handler = (
            'copy-session' in text
            and 'addEventListener' in text
        )
        # Be more precise: look for copy-session related addEventListener
        if has_direct_handler:
            # Check if it's really a copy-session handler (not just copy-session-id in a comment)
            lines = text.split("\n")
            for i, line in enumerate(lines):
                if "copy-session" in line and "addEventListener" in line:
                    assert False, (
                        f"{self._js_file}:{i + 1}: has a private handler for copy-session "
                        f"that bypasses the unified ui_primitives.js copy handler"
                    )
                if "copy-session" in line:
                    # Check nearby lines for addEventListener
                    nearby = "\n".join(lines[max(0, i - 3):i + 5])
                    if "addEventListener" in nearby and "forEach" in nearby:
                        assert False, (
                            f"{self._js_file}:{i + 1}: has a private handler for copy-session "
                            f"that bypasses the unified ui_primitives.js copy handler"
                        )

    @pytest.mark.contract_case("UI-INTERACTION-005")
    def test_projects_js_copy_handlers_use_canonical_attribute(self):
        """If any copy handler remains in projects.js, it must read data-copy-text
        (canonical) in addition to data-clipboard-text (legacy)."""
        text = self._js_file.read_text(encoding="utf-8")
        # Extract function bodies that deal with copy
        copy_functions = re.findall(
            r'(?:function\s+\w+|var\s+\w+)\s*[^{]*\{[^}]*(?:copy|clipboard)[^}]*\}',
            text,
            re.DOTALL | re.IGNORECASE,
        )
        for func in copy_functions:
            if "addEventListener" in func or "clipboard" in func.lower():
                # This is a copy-related handler; check it supports canonical attr
                has_canonical = "data-copy-text" in func or "copyText" in func
                assert has_canonical, (
                    f"{self._js_file}: copy-related handler does not read "
                    f"data-copy-text (canonical attribute)"
                )
