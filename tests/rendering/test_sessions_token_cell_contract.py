"""契约测试：ui.token_cell token breakdown 渲染。

Token cell 必须让条形图段和 tooltip breakdown 使用同一套
Fresh / Cached Rd / Cached Wr / Output 分类。

契约：
- 所有 provider 都显示 4 行 — Fresh / Cached Rd / Cached Wr / Output
- provider 不改变分类行或颜色段
"""

from __future__ import annotations

import pathlib

import jinja2
import pytest

# ── Jinja2 环境（镜像 test_ui_primitives.py） ─────────────────────────

_TEMPLATE_DIR = (
    pathlib.Path(__file__).resolve().parents[2] / 'src' / 'session_browser' / 'web' / 'templates'
)


def _make_env() -> jinja2.Environment:
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=True,
    )
    return env


def _render_token_cell(**kwargs) -> str:
    """使用给定 kwargs 渲染 token_cell 宏。"""
    env = _make_env()
    args = ', '.join(f'{k}={v!r}' for k, v in kwargs.items())
    tmpl_str = (
        '{% from "components/ui_primitives.html" import token_cell %}{{ token_cell(' + args + ') }}'
    )
    return env.from_string(tmpl_str).render()


def _render_with_profile(provider: str) -> str:
    """渲染 token_cell，如同为给定 provider 调用。"""
    return _render_token_cell(
        total='2.0K',
        fresh_pct=40.0,
        read_pct=20.0,
        write_pct=10.0,
        out_pct=30.0,
        fresh_val='800',
        read_val='400',
        write_val='200',
        out_val='600',
        fresh_pct_val='40.0',
        read_pct_val='20.0',
        write_pct_val='10.0',
        out_pct_val='30.0',
    )


# ── Token cell 类型名称行 ────────────────────────────────────────────────

_TOKEN_TYPE_NAMES = {'Fresh input', 'Cached Rd', 'Cached Wr', 'Output'}


class TestTokenCellQoderContract:
    """Qoder profile：完整 4 段细目。

    Qoder 也使用统一 token 模型，tooltip 行必须与 tokenbar 段一致。
    """

    @pytest.mark.contract_case('UI-SESSIONS-016')
    def test_qoder_has_cached_read_row(self):
        html = _render_with_profile('qoder')
        assert 'Cached Rd' in html, "Qoder token_cell must contain 'Cached Rd' row"

    @pytest.mark.contract_case('UI-SESSIONS-016')
    def test_qoder_has_cached_write_row(self):
        html = _render_with_profile('qoder')
        assert 'Cached Wr' in html, "Qoder token_cell must contain 'Cached Wr' row"

    @pytest.mark.contract_case('UI-SESSIONS-016')
    def test_qoder_has_read_dot_class(self):
        html = _render_with_profile('qoder')
        assert 'dot--read' in html, 'Qoder token_cell must contain dot--read class'

    @pytest.mark.contract_case('UI-SESSIONS-016')
    def test_qoder_has_write_dot_class(self):
        html = _render_with_profile('qoder')
        assert 'dot--write' in html, 'Qoder token_cell must contain dot--write class'

    @pytest.mark.contract_case('UI-SESSIONS-016')
    def test_qoder_has_fresh_row(self):
        html = _render_with_profile('qoder')
        assert 'Fresh' in html, 'Qoder token_cell must contain Fresh row'

    @pytest.mark.contract_case('UI-SESSIONS-016')
    def test_qoder_has_output_row(self):
        html = _render_with_profile('qoder')
        assert 'Output' in html, 'Qoder token_cell must contain Output row'

    @pytest.mark.contract_case('UI-SESSIONS-016')
    def test_qoder_type_name_count(self):
        """Qoder 提示框应恰好有 4 个类型名称行。"""
        html = _render_with_profile('qoder')
        type_names = _extract_type_names(html)
        assert len(type_names) == 4, (
            f'Qoder token_cell should have exactly 4 type rows, got {len(type_names)}: {type_names}'
        )

    @pytest.mark.contract_case('UI-SESSIONS-016')
    def test_qoder_only_allowed_type_names(self):
        """Qoder 类型名称必须使用统一 token 分类。"""
        html = _render_with_profile('qoder')
        type_names = _extract_type_names(html)
        assert type_names == _TOKEN_TYPE_NAMES, (
            f'Qoder token_cell has unexpected type names: {type_names ^ _TOKEN_TYPE_NAMES}'
        )


class TestTokenCellNonQoderContract:
    """非 Qoder（例如 claude_code）：完整 4 段细目。

    必须仍然显示 Fresh、Cached Rd、Cached Wr 和 Output 行。
    """

    @pytest.mark.contract_case('UI-SESSIONS-016')
    def test_claude_has_cached_read(self):
        html = _render_with_profile('claude_code')
        assert 'Cached Rd' in html, 'Non-Qoder token_cell must contain Cached Rd row'

    @pytest.mark.contract_case('UI-SESSIONS-016')
    def test_claude_has_cached_write(self):
        html = _render_with_profile('claude_code')
        assert 'Cached Wr' in html, 'Non-Qoder token_cell must contain Cached Wr row'

    @pytest.mark.contract_case('UI-SESSIONS-016')
    def test_claude_has_fresh(self):
        html = _render_with_profile('claude_code')
        assert 'Fresh' in html, 'Non-Qoder token_cell must contain Fresh row'

    @pytest.mark.contract_case('UI-SESSIONS-016')
    def test_claude_has_output(self):
        html = _render_with_profile('claude_code')
        assert 'Output' in html, 'Non-Qoder token_cell must contain Output row'

    @pytest.mark.contract_case('UI-SESSIONS-016')
    def test_claude_four_type_names(self):
        """非 Qoder 提示框应恰好有 4 个类型名称行。"""
        html = _render_with_profile('claude_code')
        type_names = _extract_type_names(html)
        assert len(type_names) == 4, (
            f'Non-Qoder token_cell should have exactly 4 type rows, got {len(type_names)}: {type_names}'
        )

    @pytest.mark.contract_case('UI-SESSIONS-016')
    def test_claude_all_expected_type_names(self):
        """非 Qoder 类型名称必须匹配预期集合。"""
        html = _render_with_profile('claude_code')
        type_names = _extract_type_names(html)
        assert type_names == _TOKEN_TYPE_NAMES, (
            f'Non-Qoder token_cell type names mismatch: got {type_names}'
        )


# ── Helper ───────────────────────────────────────────────────────────────


def _extract_type_names(html: str) -> set[str]:
    """Extract all token-tooltip__type-name values from rendered HTML."""
    import re

    pattern = r'<span class="token-tooltip__type-name">([^<]+)</span>'
    return set(re.findall(pattern, html))
