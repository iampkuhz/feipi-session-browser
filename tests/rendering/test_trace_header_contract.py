"""Trace header 契约测试（T021 / SD-15）。

验证 session detail 的 trace_header 宏：
- 不包含 sd-trace-title 类
- 不包含 data-action="collapse-all"
- 包含 data-action="toggle-all"（或 toggle-all 类）

此契约确保 trace header 只需要一个 toggle-all 按钮，
而不需要独立的 sd-trace-title 或 collapse-all 元素。
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TIMELINE_HTML = (
    ROOT
    / 'src'
    / 'session_browser'
    / 'web'
    / 'templates'
    / 'components'
    / 'session_detail_timeline.html'
)
TIMELINE_DIR = (
    ROOT
    / 'src'
    / 'session_browser'
    / 'web'
    / 'templates'
    / 'components'
    / 'session_detail_timeline'
)
SUMMARY_SPLIT = TIMELINE_DIR / 'summary.html'


def _read_trace_header_source() -> str:
    """Read trace_header macro from split module or wrapper."""
    # Try split module first
    if SUMMARY_SPLIT.exists():
        return SUMMARY_SPLIT.read_text(encoding='utf-8')
    # Fallback to wrapper
    if TIMELINE_HTML.exists():
        return TIMELINE_HTML.read_text(encoding='utf-8')
    pytest.fail('trace_header template not found')


@pytest.fixture(scope='module')
def trace_header_source():
    """从模板中提取 trace_header 宏体。"""
    text = _read_trace_header_source()
    # 定位 trace_header 宏块
    start = text.find('{% macro trace_header()')
    if start == -1:
        pytest.fail('trace_header macro not found')
    end = text.find('{%- endmacro %}', start)
    if end == -1:
        pytest.fail('trace_header macro lacks closing endmacro')
    # 包含 endmacro 标记
    return text[start : end + len('{%- endmacro %}')]


class TestTraceHeaderContract:
    """trace_header must NOT contain sd-trace-title or collapse-all,
    and MUST contain toggle-all.
    """

    @pytest.mark.contract_case('UI-SD-022')
    def test_no_sd_trace_title(self, trace_header_source):
        """trace_header must not contain sd-trace-title class."""
        assert 'sd-trace-title' not in trace_header_source, (
            'trace_header must NOT contain sd-trace-title class'
        )

    @pytest.mark.contract_case('UI-SD-022')
    def test_no_collapse_all_action(self, trace_header_source):
        """trace_header must not contain data-action=\"collapse-all\"."""
        assert 'data-action="collapse-all"' not in trace_header_source, (
            'trace_header must NOT contain data-action="collapse-all"'
        )

    @pytest.mark.contract_case('UI-SD-022')
    def test_no_collapse_all_class(self, trace_header_source):
        """trace_header must not contain sd-collapse-all-btn class."""
        assert 'sd-collapse-all-btn' not in trace_header_source, (
            'trace_header must NOT contain sd-collapse-all-btn class'
        )

    @pytest.mark.contract_case('UI-SD-022')
    def test_has_toggle_all(self, trace_header_source):
        """trace_header must contain data-action=\"toggle-all\" or toggle-all class."""
        has_action = 'data-action="toggle-all"' in trace_header_source
        has_class = 'toggle-all' in trace_header_source
        assert has_action or has_class, (
            'trace_header must contain data-action="toggle-all" or toggle-all class'
        )
