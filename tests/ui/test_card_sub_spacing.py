"""T030 · card-sub spacing static gate.

Verifies that canonical .card-sub has bottom spacing (margin-bottom or
parent gap) so subtitle text does not collide with the content below it.

Covers P-24 / S-12: card-sub 没有 margin-bottom
"""
import pytest
from pathlib import Path
import re

CSS_PATH = Path(__file__).resolve().parents[2] / "src" / "session_browser" / "web" / "static" / "css" / "ui-primitives.css"


@pytest.fixture(scope="module")
def css_text():
    if not CSS_PATH.exists():
        pytest.skip(f"ui-primitives.css not found at {CSS_PATH}")
    return CSS_PATH.read_text(encoding="utf-8")


def _extract_canonical_card_sub_block(css_text: str) -> str:
    """提取规范的 .card-sub 块（非遗留/迁移版本）。

    规范定义位于 TableToolbar 区域，
    不以 'Originally at style.css' 注释为前缀。
    我们取第一个裸 .card-sub { ... } 块（不包括 .card .card-sub）。
    """
    # 查找所有 .card-sub 块（不包括带前缀的选择器如 .card .card-sub）
    # 模式：可选注释 + .card-sub { ... }
    pattern = r"(?<![\w-])\.card-sub\s*\{([^}]+)\}"
    matches = list(re.finditer(pattern, css_text))
    if not matches:
        return ""
    # 规范定义是第一个不在迁移块中的出现
    # （迁移块附近有 "Originally at style.css" 注释）
    for m in matches:
        start = max(0, m.start() - 200)
        preceding = css_text[start:m.start()]
        if "Originally at style.css" not in preceding:
            return m.group(1)
    # 回退到第一个匹配
    return matches[0].group(1)


class TestCardSubSpacing:
    """规范的 .card-sub 必须有底部间距。"""

    @pytest.mark.contract_case("UI-VISUAL-014")
    def test_card_sub_has_margin_bottom_or_parent_gap(self, css_text):
        """规范的 .card-sub 块必须定义 margin-bottom，
        或在含 gap 的容器内（如 .table-toolbar 使用 flex gap）。

        可接受：
        - .card-sub { margin-bottom: ... }
        - .card-sub { margin: ... X Y Z } 其中 bottom 值 > 0
        - 父容器（如 .table-toolbar）有 gap 覆盖间距
        """
        block = _extract_canonical_card_sub_block(css_text)
        assert block, "No canonical .card-sub block found in ui-primitives.css"

        # 检查显式 margin-bottom
        has_margin_bottom = re.search(r'margin-bottom\s*:', block) is not None

        # 检查 shorthand margin 的 bottom 值
        # margin: top right bottom left 或 margin: vertical horizontal
        margin_shorthand = re.search(r'margin\s*:\s*([^;]+);', block)
        has_margin_shorthand_bottom = False
        if margin_shorthand:
            values = margin_shorthand.group(1).strip().split()
            if len(values) >= 3:
                # 3 或 4 个值：第三个是 bottom
                bottom_val = values[2]
                has_margin_shorthand_bottom = bottom_val != "0" and bottom_val != "0px"
            elif len(values) == 2:
                # 2 个值：vertical（top=bottom），第二个是 bottom
                bottom_val = values[1]
                has_margin_shorthand_bottom = bottom_val != "0" and bottom_val != "0px"
            elif len(values) == 1:
                bottom_val = values[0]
                has_margin_shorthand_bottom = bottom_val != "0" and bottom_val != "0px"

        # 检查 .table-toolbar 父容器是否有 gap（flex 间距）
        toolbar_match = re.search(r'\.table-toolbar\s*\{([^}]+)\}', css_text)
        has_parent_gap = False
        if toolbar_match:
            has_parent_gap = re.search(r'gap\s*:\s*[^0]', toolbar_match.group(1)) is not None

        # .card-sub 自身有 bottom margin，或父容器使用 gap，
        # 或存在 .section-head / .table-toolbar 模式通过自身布局提供间距
        assert has_margin_bottom or has_margin_shorthand_bottom or has_parent_gap, (
            f"Canonical .card-sub lacks bottom spacing. "
            f"Block content: '{block.strip()}'. "
            f"margin-bottom: {bool(has_margin_bottom)}, "
            f"margin-shorthand-bottom: {has_margin_shorthand_bottom}, "
            f"parent-gap (.table-toolbar): {has_parent_gap}"
        )

    @pytest.mark.contract_case("UI-VISUAL-014")
    def test_card_sub_no_zero_margin_bottom(self, css_text):
        """规范的 .card-sub 不应显式设置 margin-bottom: 0。"""
        block = _extract_canonical_card_sub_block(css_text)
        # 完全没有 margin-bottom 也可以；只是不要显式设为 0
        zero_bottom = re.search(r'margin-bottom\s*:\s*0', block)
        assert zero_bottom is None, (
            f"Canonical .card-sub explicitly sets margin-bottom: 0"
        )
