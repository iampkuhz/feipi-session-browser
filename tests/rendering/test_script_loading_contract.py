"""脚本加载契约测试（T016）。

验证 ui_primitives.js 仅被加载一次（仅由 base.html 加载），
且 sessions.html 不会重复加载它。

这可以防止重复的文档级事件监听器导致
下一页按钮分页一次跳过两页。
"""
import pytest
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_DIR = ROOT / "src" / "session_browser" / "web" / "templates"
BASE_HTML = TEMPLATE_DIR / "base.html"
SESSIONS_HTML = TEMPLATE_DIR / "sessions.html"

UI_PRIMITIVES_JS = "/static/js/ui_primitives.js"
SESSIONS_LIST_JS = "/static/js/sessions-list.js"


def _read(path: Path) -> str:
    """读取文件文本，如果缺失则跳过测试。"""
    if not path.exists():
        pytest.fail(f"{path.name} not found at {path}")
    return path.read_text(encoding="utf-8")


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def base_text():
    return _read(BASE_HTML)


@pytest.fixture(scope="module")
def sessions_text():
    return _read(SESSIONS_HTML)


# ── Script loading ownership ──────────────────────────────────────────────


def _count_script_src(text: str, script_path: str) -> int:
    """统计给定路径的实际 <script src="..."> 标签数量，忽略注释。"""
    # Strip Jinja {# ... #} block comments first
    stripped = re.sub(r'\{#.*?#\}', '', text, flags=re.DOTALL)
    # Strip HTML <!-- ... --> comments
    stripped = re.sub(r'<!--.*?-->', '', stripped, flags=re.DOTALL)
    pattern = r'<script[^>]+src=["\']' + re.escape(script_path) + r'["\'][^>]*>'
    return len(re.findall(pattern, stripped))


class TestScriptLoadingOwnership:
    """base.html 是 ui_primitives.js 加载的唯一所有者。"""

    @pytest.mark.contract_case("UI-VISUAL-001")
    def test_base_html_loads_ui_primitives_js(self, base_text):
        """base.html 必须加载 ui_primitives.js（它是规范源）。"""
        count = _count_script_src(base_text, UI_PRIMITIVES_JS)
        assert count >= 1, \
            f"base.html must load {UI_PRIMITIVES_JS} via <script> tag"

    @pytest.mark.contract_case("UI-VISUAL-001")
    def test_base_html_load_count_exactly_one(self, base_text):
        """base.html 必须恰好加载 ui_primitives.js 一次（通过 <script> 标签）。"""
        count = _count_script_src(base_text, UI_PRIMITIVES_JS)
        assert count == 1, \
            f"base.html loads {UI_PRIMITIVES_JS} {count} times (expected 1)"


class TestSessionsNoDuplicatePrimitives:
    """sessions.html must NOT load ui_primitives.js (inherits from base.html)."""

    @pytest.mark.contract_case("UI-VISUAL-001")
    def test_sessions_does_not_load_ui_primitives_js(self, sessions_text):
        """sessions.html must not contain a <script> tag for ui_primitives.js."""
        # Look for script src containing ui_primitives.js
        pattern = r'<script[^>]+src=["\']' + re.escape(UI_PRIMITIVES_JS) + r'["\'][^>]*>'
        matches = re.findall(pattern, sessions_text)
        assert len(matches) == 0, \
            (f"sessions.html must not load {UI_PRIMITIVES_JS} "
             f"(found {len(matches)} <script> tag(s); "
             "ui_primitives.js is already loaded by base.html)")

    @pytest.mark.contract_case("UI-VISUAL-001")
    def test_sessions_does_not_reference_ui_primitives_js_at_all(self, sessions_text):
        """sessions.html should not have a <script> tag for ui_primitives.js anywhere."""
        # Strip Jinja and HTML comments, then check for script tags only
        stripped = re.sub(r'\{#.*?#\}', '', sessions_text, flags=re.DOTALL)
        stripped = re.sub(r'<!--.*?-->', '', stripped, flags=re.DOTALL)
        pattern = r'<script[^>]+src=["\']' + re.escape(UI_PRIMITIVES_JS) + r'["\'][^>]*>'
        matches = re.findall(pattern, stripped)
        assert len(matches) == 0, \
            (f"sessions.html references {UI_PRIMITIVES_JS} in a <script> tag "
             "(ownership belongs to base.html)")


class TestSessionsAllowedScripts:
    """sessions.html is allowed to load its own page-specific scripts."""

    @pytest.mark.contract_case("UI-VISUAL-001")
    def test_sessions_loads_sessions_list_js(self, sessions_text):
        """sessions.html may (and should) load sessions-list.js."""
        pattern = r'<script[^>]+src=["\']' + re.escape(SESSIONS_LIST_JS) + r'["\'][^>]*>'
        matches = re.findall(pattern, sessions_text)
        assert len(matches) >= 1, \
            f"sessions.html should load {SESSIONS_LIST_JS}"


class TestBaseHtmlGlobalScripts:
    """base.html must load the expected global JS bundle (ownership reference)."""

    @pytest.mark.contract_case("UI-VISUAL-001")
    def test_base_loads_arp_storage(self, base_text):
        """base.html must load arp-storage.js."""
        assert "/static/js/arp-storage.js" in base_text, \
            "base.html must load arp-storage.js"

    @pytest.mark.contract_case("UI-VISUAL-001")
    def test_base_loads_view_state(self, base_text):
        """base.html must load view-state.js."""
        assert "/static/js/view-state.js" in base_text, \
            "base.html must load view-state.js"

    @pytest.mark.contract_case("UI-VISUAL-001")
    def test_base_loads_app_js(self, base_text):
        """base.html must load app.js."""
        assert "/static/js/app.js" in base_text, \
            "base.html must load app.js"
