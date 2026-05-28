"""session_detail_timeline.html 中 payload modal 渲染器契约测试。
验证 sd-payload-modal 面板包含标准的 `payload-modal__panel`
CSS 类且不使用全屏内联样式。

相关：SD-17 — sd-payload-modal 宽高变成整个页面
"""

import pytest

from pathlib import Path
import re

TEMPLATE_DIR = Path(__file__).parents[2] / "src" / "session_browser" / "web" / "templates"

TIMELINE_TEMPLATE = TEMPLATE_DIR / "components" / "session_detail_timeline.html"


def _timeline_html():
    return TIMELINE_TEMPLATE.read_text(encoding="utf-8")


def _has_canonical_panel_class(source: str) -> bool:
    """检查 payload_modal 宏中是否有 class 属性包含 `payload-modal__panel`
    作为独立的 CSS 类标记。

    独立标记意味着它在 class 属性值中由空白字符分隔，
    而不是较长标识符的子串（例如 'sd-payload-modal__panel' 不算）。
    """
    # 提取 payload_modal 宏块
    macro_match = re.search(
        r'\{% macro payload_modal\(\) -%\}(.*?){%- endmacro %}',
        source,
        re.DOTALL,
    )
    if not macro_match:
        return False
    macro_body = macro_match.group(1)

    # 查找宏体中所有 class="..." 属性
    class_attrs = re.findall(r'class="([^"]*)"', macro_body)
    for attr_value in class_attrs:
        # 按空白字符分割并检查每个标记
        tokens = attr_value.split()
        if 'payload-modal__panel' in tokens:
            return True
    return False


def _panel_inline_style(source: str) -> str | None:
    """返回 payload-modal__panel 元素的 inline style 字符串，
    如果未找到则返回 None。"""
    macro_match = re.search(
        r'\{% macro payload_modal\(\) -%\}(.*?){%- endmacro %}',
        source,
        re.DOTALL,
    )
    if not macro_match:
        return None
    macro_body = macro_match.group(1)

    # 查找引用 payload-modal__panel 的元素（独立或带命名空间）
    tags = re.findall(r'<[^>]*(?:payload-modal__panel)[^>]*>', macro_body)
    for tag in tags:
        style_match = re.search(r'style="([^"]*)"', tag)
        if style_match:
            return style_match.group(1)
    return None


# ── 面板类契约 ─────────────────────────────────────────────────────────


@pytest.mark.contract_case("UI-SD-020")
def test_payload_modal_panel_has_canonical_class():
    """sd-payload-modal 面板必须包含规范的 `payload-modal__panel` 类。

    payload-modal 对话框内的面板必须携带规范的 BEM 类
    `payload-modal__panel` 作为独立的 CSS 类标记，以便
    ui-primitives.css 中的选择器（如 `.payload-modal--sd .payload-modal__panel`）
    能够生效。仅带命名空间的类如 `sd-payload-modal__panel` 不满足此契约，
    因为规范选择器会匹配不到它（SD-17）。
    """
    source = _timeline_html()
    assert _has_canonical_panel_class(source), (
        "payload_modal panel must include 'payload-modal__panel' as a standalone "
        "CSS class (not just as a substring of a longer name like "
        "'sd-payload-modal__panel')"
    )


@pytest.mark.contract_case("UI-SD-020")
def test_payload_modal_panel_no_fullscreen_inline_style():
    """面板不得携带 width:100% 或 height:100vh 等全屏 inline 样式。"""
    source = _timeline_html()
    style = _panel_inline_style(source)
    if style is not None:
        style_lower = style.lower()
        assert '100%' not in style_lower and '100vh' not in style_lower and '100vw' not in style_lower, (
            f"payload-modal__panel must not have fullscreen inline style: {style!r}"
        )


@pytest.mark.contract_case("UI-SD-020")
def test_payload_modal_dialog_has_sd_namespace():
    """payload modal 对话框应携带 sd-payload-modal 类以便作用域定位。"""
    source = _timeline_html()
    assert 'sd-payload-modal' in source, (
        "payload modal dialog should include sd-payload-modal class"
    )
