"""T035 门控测试：统一复制操作契约。
验证代码库中所有复制按钮遵循标准契约：

  data-action="copy" + data-copy-text="<要复制的文本>"

标准处理器位于 ui_primitives.js:handleCopy()，仅读取
data-copy-text。任何使用非标准 data-action（如
copy-session、copy-project-path、copy-path、copy-session-id）或遗留
data-clipboard-text 属性的按钮都不会被统一处理器处理，
构成契约违反。

这是门控/回归测试。在源模板和 JS 迁移完成之前，
预期的 bug 会 FAIL。
"""


from __future__ import annotations

import pytest
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
TEMPLATE_DIR = ROOT / "src" / "session_browser" / "web" / "templates"
JS_DIR = ROOT / "src" / "session_browser" / "web" / "static" / "js"

# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

CANONICAL_ACTION = "copy"
CANONICAL_ATTR = "data-copy-text"
LEGACY_ATTR = "data-clipboard-text"

# 非标准 data-action 值。
# 这些是页面级 JS 处理器，会绕过统一的 ui_primitives.js 处理器。
NON_CANONICAL_ACTIONS = [
    "copy-session",
    "copy-session-id",
    "copy-project-path",
    "copy-path",
]


def _all_html_files():
    """遍历 templates 目录下所有 .html 文件。"""
    yield from TEMPLATE_DIR.rglob("*.html")


def _find_copy_buttons(html: str):
    """返回 HTML 中所有类复制按钮的描述列表。

    每个字典包含键：data_action、has_copy_text、has_clipboard_text、
    has_session_id、file（源文件路径）。
    """
    results = []
    # 匹配 <button ...> 标签（单行，属性中不含嵌套 >）
    for btn in re.finditer(r'<button\b[^>]*>', html):
        attrs = btn.group(0)
        action_match = re.search(r'data-action="([^"]*)"', attrs)
        data_action = action_match.group(1) if action_match else None

        # 只关注与复制相关的按钮
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
# T035-1：所有 HTML 模板使用标准复制契约
# ---------------------------------------------------------------------------

class TestCopyActionContractTemplates:
    """静态扫描：每个复制按钮必须使用 data-action="copy" + data-copy-text。"""

    @pytest.mark.contract_case("UI-INTERACTION-005")
    def test_all_copy_buttons_use_canonical_data_action(self):
        """所有复制按钮必须使用 data-action="copy"，不能使用自定义 action 如
        copy-session、copy-project-path、copy-path、copy-session-id。"""
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
        """所有复制按钮必须携带 data-copy-text，不能使用遗留的 data-clipboard-text。"""
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
        """复制按钮不得使用遗留的 data-clipboard-text 属性。"""
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
        """按钮不应依赖 data-session-id 作为复制后备；
        要复制的文本应放在 data-copy-text 中。"""
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
# T035-2：ui_primitives.js handleCopy 只支持当前标准
# ---------------------------------------------------------------------------

class TestUiPrimitivesCopyHandler:
    """验证 ui_primitives.js handleCopy 只读取 data-copy-text。"""

    _js_file = JS_DIR / "ui_primitives.js"

    @pytest.mark.contract_case("UI-INTERACTION-005")
    def test_handleCopy_exists(self):
        """handleCopy 函数必须已定义。"""
        text = self._js_file.read_text(encoding="utf-8")
        assert "function handleCopy" in text, (
            f"{self._js_file}: handleCopy function not found"
        )

    @pytest.mark.contract_case("UI-INTERACTION-005")
    def test_handleCopy_reads_data_copy_text(self):
        """handleCopy 必须以 data-copy-text 作为主要数据源读取。"""
        text = self._js_file.read_text(encoding="utf-8")
        # 提取 handleCopy 函数体
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
        """data-copy-text 必须是 FIRST 个被检查的属性（主要来源），而非后备。"""
        text = self._js_file.read_text(encoding="utf-8")
        match = re.search(
            r'function handleCopy\([^)]*\)\s*\{(.*?)(?=\n  //|  function |\n  window\.|}$)',
            text,
            re.DOTALL,
        )
        assert match, f"{self._js_file}: could not parse handleCopy body"
        body = match.group(1)
        # 第一个 getAttribute 或类似调用应针对 data-copy-text
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
    def test_handleCopy_has_no_legacy_fallback(self):
        """handleCopy 不得读取旧复制属性或从按钮文本猜测复制内容。"""
        text = self._js_file.read_text(encoding="utf-8")
        match = re.search(
            r'function handleCopy\([^)]*\)\s*\{(.*?)(?=\n  //|  function |\n  window\.|}$)',
            text,
            re.DOTALL,
        )
        assert match, f"{self._js_file}: could not parse handleCopy body"
        body = match.group(1)
        banned = ["data-clipboard-text", "clipboardText", "title", "textContent"]
        found = [item for item in banned if item in body]
        assert not found, (
            f"{self._js_file}: handleCopy reads non-canonical copy fallback(s): "
            + ", ".join(found)
        )

    @pytest.mark.contract_case("UI-INTERACTION-005")
    def test_copy_registered_in_switch(self):
        """点击委托开关必须包含 'copy' 分支并调用 handleCopy。"""
        text = self._js_file.read_text(encoding="utf-8")
        assert "case 'copy':" in text, (
            f"{self._js_file}: no 'case \"copy\":' in the click delegation switch"
        )
        # 验证它调用了 handleCopy
        assert "handleCopy(" in text, (
            f"{self._js_file}: handleCopy is not called from the delegation switch"
        )


# ---------------------------------------------------------------------------
# T035-3：projects.js 无冲突的私有复制处理器
# ---------------------------------------------------------------------------

class TestProjectsJsCopyHandlers:
    """验证 projects.js 不存在与统一 ui_primitives.js 契约冲突的私有复制处理器。

    标准契约要求：
    - 不得在非标准 copy action 上注册绕过统一处理器的 addEventListener。
    - 如果存在页面级复制逻辑，它必须读取 data-copy-text。
    """

    _js_file = JS_DIR / "projects.js"

    @pytest.mark.contract_case("UI-INTERACTION-005")
    def test_no_private_copy_project_path_handler(self):
        """projects.js 不得在旧 project copy action 上注册私有处理器。"""
        text = self._js_file.read_text(encoding="utf-8")
        # 检查是否直接对 copy-project-path 使用 querySelectorAll
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
        """projects.js 不得在旧 session copy action 上注册私有处理器。"""
        text = self._js_file.read_text(encoding="utf-8")
        has_direct_handler = (
            'copy-session' in text
            and 'addEventListener' in text
        )
        # 更精确地检查：查找 copy-session 相关的 addEventListener
        if has_direct_handler:
        # 检查是否真的是 copy-session 处理器（而非注释中的 copy-session-id）
            lines = text.split("\n")
            for i, line in enumerate(lines):
                if "copy-session" in line and "addEventListener" in line:
                    assert False, (
                        f"{self._js_file}:{i + 1}: has a private handler for copy-session "
                        f"that bypasses the unified ui_primitives.js copy handler"
                    )
                if "copy-session" in line:
                    # 检查附近行是否有 addEventListener
                    nearby = "\n".join(lines[max(0, i - 3):i + 5])
                    if "addEventListener" in nearby and "forEach" in nearby:
                        assert False, (
                            f"{self._js_file}:{i + 1}: has a private handler for copy-session "
                            f"that bypasses the unified ui_primitives.js copy handler"
                        )

    @pytest.mark.contract_case("UI-INTERACTION-005")
    def test_projects_js_copy_handlers_use_canonical_attribute(self):
        """如果 projects.js 中仍存在复制处理器，它必须读取 data-copy-text。"""
        text = self._js_file.read_text(encoding="utf-8")
        # 提取与复制相关的函数体
        copy_functions = re.findall(
            r'(?:function\s+\w+|var\s+\w+)\s*[^{]*\{[^}]*(?:copy|clipboard)[^}]*\}',
            text,
            re.DOTALL | re.IGNORECASE,
        )
        for func in copy_functions:
            if "addEventListener" in func or "clipboard" in func.lower():
                # 这是复制相关处理器；检查它是否支持标准属性
                has_canonical = "data-copy-text" in func or "copyText" in func
                assert has_canonical, (
                    f"{self._js_file}: copy-related handler does not read "
                    f"data-copy-text (canonical attribute)"
                )
