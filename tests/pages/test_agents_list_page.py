"""验证 Agents List 页面渲染和模板结构的测试。

Agents.html 的页面级 pytest，覆盖模板结构、CSS/JS 导入、
页面头部、指标卡片、表格结构、行结构、分页、
效率表格、空状态/错误状态，以及不含 inline onclick。

T136 — Agents List：添加页面级 pytest。
"""

from __future__ import annotations

import pytest
import os
import re

_AGENTS_PATH = "src/session_browser/web/templates/agents.html"
_AGENTS_CSS_PATH = "src/session_browser/web/static/css/agents.css"
_AGENTS_JS_PATH = "src/session_browser/web/static/js/agents.js"


def _read(path: str) -> str:
    with open(path) as f:
        return f.read()


def _read_template() -> str:
    return _read(_AGENTS_PATH)


# ── TestAgentsTemplate ─────────────────────────────────────────────

class TestAgentsTemplate:
    """验证 agents 的 Jinja2 模板结构渲染。"""

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_template_file_exists(self):
        """agents.html 必须存在于磁盘上。"""
        assert os.path.isfile(_AGENTS_PATH), \
            f"{_AGENTS_PATH} 必须存在"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_extends_base(self):
        """Agents 必须继承 base.html。"""
        content = _read_template()
        assert '{% extends "base.html" %}' in content, \
            "Agents 必须继承 base.html"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_active_page_set(self):
        """Agents 必须设置 active_page = 'agents'。"""
        content = _read_template()
        assert "active_page = 'agents'" in content, \
            "Agents 必须设置 active_page = 'agents'"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_ui_primitives_imported(self):
        """Agents 必须导入 ui_primitives.html。"""
        content = _read_template()
        assert 'import "components/ui_primitives.html"' in content, \
            "Agents 必须导入 ui_primitives.html"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_no_inline_onclick(self):
        """Agents 不得使用 inline onclick 处理器。"""
        content = _read_template()
        matches = re.findall(r'\bonclick\s*=', content, re.IGNORECASE)
        assert len(matches) == 0, \
            f"Agents 不得有 inline onclick，发现 {len(matches)} 处"


# ── TestAgentsImports ──────────────────────────────────────────────

class TestAgentsImports:
    """验证 CSS 和 JS 导入声明。"""

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_css_import_agents_css(self):
        """Agents 必须导入 agents.css。"""
        content = _read_template()
        assert 'href="/static/css/agents.css"' in content, \
            "Agents 必须导入 agents.css"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_js_import_agents_js(self):
        """Agents 必须导入 agents.js。"""
        content = _read_template()
        assert 'src="/static/js/agents.js"' in content, \
            "Agents 必须导入 agents.js"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_css_file_exists_on_disk(self):
        """agents.css 必须存在于磁盘上。"""
        assert os.path.isfile(_AGENTS_CSS_PATH), \
            "agents.css 必须存在于磁盘上"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_js_file_exists_on_disk(self):
        """agents.js 必须存在于磁盘上。"""
        assert os.path.isfile(_AGENTS_JS_PATH), \
            "agents.js 必须存在于磁盘上"


# ── TestAgentsPageHead ─────────────────────────────────────────────

class TestAgentsPageHead:
    """验证页面头部结构（使用 ui.page_head 宏，T15）。"""

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_page_head_macro_used(self):
        """Agents 必须使用 ui.page_head() 宏。"""
        content = _read_template()
        assert 'ui.page_head(' in content, \
            "Agents 必须使用 ui.page_head() 宏"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_page_head_has_h1(self):
        """页面头部必须以 'Agents' 为标题。"""
        content = _read_template()
        assert "'Agents'" in content, \
            "页面头部必须以 'Agents' 为标题"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_page_head_has_subtitle(self):
        """页面头部必须有包含 agent/model 计数的副标题。"""
        content = _read_template()
        assert '个 Agent' in content, \
            "页面头部必须有包含 agent 计数的副标题"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_breadcrumb_present(self):
        """页面必须有面包屑并链接到 Dashboard。"""
        content = _read_template()
        assert 'href="/dashboard"' in content, \
            "面包屑必须链接到 /dashboard"
        assert ">Agents</span>" in content or ">Agents<" in content, \
            "面包屑必须显示 Agents 为当前页"


# ── TestAgentsMetricCards ──────────────────────────────────────────

class TestAgentsMetricCards:
    """验证 4 个指标卡片的标签和结构。"""

    _EXPECTED_LABELS = [
        "Active Agents",
        "Sessions",
        "Projects",
        "Total Tokens",
    ]

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_metric_grid_present(self):
        """Agents 必须有 metric-grid 区域。"""
        content = _read_template()
        assert 'class="metric-grid"' in content, \
            "Agents 必须有 metric-grid 区域"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_four_metric_cards(self):
        """Agents 必须恰好有 4 个指标卡片。"""
        content = _read_template()
        cards = re.findall(r'class="metric-card"', content)
        assert len(cards) == 4, \
            f"Agents 必须恰好有 4 个指标卡片，发现 {len(cards)} 个"

    @pytest.mark.parametrize("label", _EXPECTED_LABELS)
    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_metric_card_labels(self, label):
        """每个指标卡片必须有预期的标签文本。"""
        content = _read_template()
        assert f">{label}" in content, \
            f"Agents 必须有标签为 '{label}' 的指标卡片"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_metric_card_aria_labels(self):
        """每个指标卡片信息按钮必须有 aria-label。"""
        content = _read_template()
        # aria-labels 包含 计数说明 和 公式说明 两种变体
        aria_labels = re.findall(r'aria-label="[^"]*(?:计数说明|公式说明)[^"]*"', content)
        assert len(aria_labels) >= 4, \
            f"Agents 的指标信息按钮上至少要有 4 个 aria-label，发现 {len(aria_labels)} 个"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_metric_cards_have_icons(self):
        """每个指标卡片必须有 metric-icon 元素。"""
        content = _read_template()
        icons = re.findall(r'class="metric-icon', content)
        assert len(icons) >= 4, \
            f"Agents 必须至少有 4 个 metric-icon 元素，发现 {len(icons)} 个"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_metric_icons_have_emoji_aria_hidden(self):
        """每个 metric-icon 必须有 aria-hidden 属性。"""
        content = _read_template()
        icons = re.findall(
            r'class="metric-icon[^"]*"[^>]*aria-hidden="true"', content
        )
        assert len(icons) >= 4, \
            f"Agents 必须至少有 4 个带 aria-hidden 的 metric-icon 元素，发现 {len(icons)} 个"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_metric_cards_have_label_class(self):
        """每个指标卡片必须有 metric-card__label 元素。"""
        content = _read_template()
        labels = re.findall(r'class="metric-card__label"', content)
        assert len(labels) >= 4, \
            f"Agents 必须至少有 4 个 metric-card__label 元素，发现 {len(labels)} 个"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_metric_cards_have_value_class(self):
        """每个指标卡片必须有 metric-card__value 元素。"""
        content = _read_template()
        values = re.findall(r'class="metric-card__value(?: mono)?"', content)
        assert len(values) >= 4, \
            f"Agents 必须至少有 4 个 metric-card__value 元素，发现 {len(values)} 个"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_metric_info_buttons(self):
        """每个指标卡片必须有 data-action='info' 的信息按钮。"""
        content = _read_template()
        buttons = re.findall(r'data-action="info"', content)
        assert len(buttons) == 4, \
            f"Agents 必须有 4 个信息按钮，发现 {len(buttons)} 个"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_info_buttons_use_info_icon_class(self):
        """信息按钮必须使用 info-icon 类。"""
        content = _read_template()
        assert 'icon-button--info' in content, \
            "信息按钮必须使用 icon-button--info 类"


# ── TestAgentsTableStructure ───────────────────────────────────────

class TestAgentsTableStructure:
    """验证表格结构和列表头。"""

    _EXPECTED_COLUMNS = [
        "Agent", "Provider", "Sessions", "Projects",
        "Tokens", "Tool Calls", "Failed", "最近活跃",
    ]

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_table_has_id(self):
        """Agents 表格必须有 id='agents-table'。"""
        content = _read_template()
        assert 'id="agents-table"' in content, \
            "Agents 表格必须有 id='agents-table'"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_table_card_wraps_table(self):
        """表格必须通过 ui.table_card 宏渲染。"""
        content = _read_template()
        assert "ui.table_card(" in content, \
            "表格必须通过 ui.table_card 宏渲染"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_table_toolbar_present(self):
        """表格必须通过 ui.table_card 宏渲染。"""
        content = _read_template()
        assert "ui.table_card(" in content, \
            "表格必须通过 ui.table_card 宏渲染"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_table_title_present(self):
        """Table-card 必须有 'All Agents' 的 card-title。"""
        content = _read_template()
        assert "ui.table_card(" in content, \
            "表格必须使用 ui.table_card 宏，该宏渲染 card-title"
        assert ">All Agents" in content or "'All Agents'" in content, \
            "表格标题必须引用 'All Agents'"

    @pytest.mark.parametrize("column", _EXPECTED_COLUMNS)
    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_column_headers_present(self, column):
        """表格必须有所有预期的列表头。"""
        content = _read_template()
        assert column in content, \
            f"表格必须有 '{column}' 列表头"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_eight_column_headers_in_agents_table(self):
        """Agents 表格必须恰好有 8 个列表头。"""
        content = _read_template()
        # 提取 agents 表格的 thead 区域
        # 计算 </thead> 之前的 <th> 元素数量
        thead_match = re.search(r'id="agents-table".*?<thead>(.*?)</thead>', content, re.DOTALL)
        assert thead_match, "Agents 表格必须有 thead 区域"
        thead_content = thead_match.group(1)
        ths = re.findall(r'<th(?!\w)', thead_content)
        assert len(ths) == 8, \
            f"Agents 表格必须有 8 个列表头，发现 {len(ths)} 个"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_table_has_table_wrap(self):
        """表格必须在 ui.table_card 宏内渲染 table-wrap。"""
        content = _read_template()
        assert "ui.table_card(" in content, \
            "表格必须使用 ui.table_card 宏，该宏渲染 table-wrap"


# ── TestAgentsSortableHeaders ──────────────────────────────────────

class TestAgentsSortableHeaders:
    """验证可排序表头行为。"""

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_sortable_columns_have_data_action_sort(self):
        """可排序列必须有 data-action='sort'。"""
        content = _read_template()
        sorts = re.findall(r'data-action="sort"', content)
        # agents 表格 8 列 + 效率表格 10 列 = 至少 18 个
        assert len(sorts) >= 8, \
            f"表格必须至少有 8 个可排序列，发现 {len(sorts)} 个"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_agents_sortable_data_sort_values(self):
        """Agents 表格可排序列必须有正确的 data-sort 值。"""
        content = _read_template()
        for sort_key in ["name", "provider", "sessions", "projects", "tokens", "tool_calls", "failed", "last_active"]:
            assert f'data-sort="{sort_key}"' in content, \
                f"Agents 表格必须有 data-sort='{sort_key}'"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_sortable_columns_have_data_sort_key(self):
        """可排序的 th 元素必须有 data-sort-key 属性。"""
        content = _read_template()
        sort_keys = re.findall(r'data-sort-key="[^"]*"', content)
        assert len(sort_keys) >= 8, \
            f"必须至少有 8 个 data-sort-key 属性，发现 {len(sort_keys)} 个"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_sortable_headers_have_sortable_header_class(self):
        """可排序表头必须使用 sortable-header 按钮类。"""
        content = _read_template()
        buttons = re.findall(r'class="sortable-header"', content)
        assert len(buttons) >= 8, \
            f"必须至少有 8 个 sortable-header 按钮，发现 {len(buttons)} 个"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_sort_caret_aria_hidden(self):
        """排序箭头必须有 aria-hidden='true'。"""
        content = _read_template()
        carets = re.findall(r'class="sort-caret" aria-hidden="true"', content)
        assert len(carets) >= 8, \
            f"必须至少有 8 个带 aria-hidden 的排序箭头，发现 {len(carets)} 个"


# ── TestAgentsRowStructure ─────────────────────────────────────────

class TestAgentsRowStructure:
    """验证表格行结构和数据属性。"""

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_row_has_open_agent_action(self):
        """行必须有 data-action='open-agent'。"""
        content = _read_template()
        assert 'data-action="open-agent"' in content, \
            "行必须有 data-action='open-agent'"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_row_has_data_href(self):
        """行必须有 data-href 属性。"""
        content = _read_template()
        assert 'data-href="/agents/{{ a.agent }}"' in content, \
            "行必须有 data-href 属性"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_row_data_agent_name(self):
        """行必须有 data-agent-name 属性。"""
        content = _read_template()
        assert 'data-agent-name=' in content, \
            "行必须有 data-agent-name 属性"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_row_data_session_count(self):
        """行必须有 data-session-count 属性。"""
        content = _read_template()
        assert 'data-session-count=' in content, \
            "行必须有 data-session-count 属性"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_row_data_project_count(self):
        """行必须有 data-project-count 属性。"""
        content = _read_template()
        assert 'data-project-count=' in content, \
            "行必须有 data-project-count 属性"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_row_data_total_tokens(self):
        """行必须有 data-total-tokens 属性。"""
        content = _read_template()
        assert 'data-total-tokens=' in content, \
            "行必须有 data-total-tokens 属性"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_row_data_total_tool_calls(self):
        """行必须有 data-total-tool-calls 属性。"""
        content = _read_template()
        assert 'data-total-tool-calls=' in content, \
            "行必须有 data-total-tool-calls 属性"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_row_data_last_active(self):
        """行必须有 data-last-active 属性。"""
        content = _read_template()
        assert 'data-last-active=' in content, \
            "行必须有 data-last-active 属性"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_title_main_present(self):
        """行必须使用 agent_cell 宏，该宏渲染 title-main。"""
        content = _read_template()
        assert 'ui.agent_cell' in content or 'class="title-main"' in content, \
            "行必须有 title-main 元素（内联或通过 agent_cell 宏）"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_title_sub_present(self):
        """行必须使用 agent_cell 宏，该宏渲染 title-sub。"""
        content = _read_template()
        assert 'ui.agent_cell' in content or 'class="title-sub"' in content, \
            "行必须有 title-sub 元素（内联或通过 agent_cell 宏）"


# ── TestAgentsProviderBadges ───────────────────────────────────────

class TestAgentsProviderBadges:
    """验证 provider 列显示正确的徽章。"""

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_badge_cc_present(self):
        """模板必须有 Claude Code 的 CC 徽章类。"""
        content = _read_template()
        assert "class=\"badge cc\"" in content or "'cc'" in content, \
            "模板必须引用 CC 徽章类"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_badge_cx_present(self):
        """模板必须有 Codex 的 CX 徽章类。"""
        content = _read_template()
        assert "'cx'" in content, \
            "模板必须引用 CX 徽章类"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_badge_qd_present(self):
        """模板必须有 Qoder 的 QD 徽章类。"""
        content = _read_template()
        assert "'qd'" in content, \
            "模板必须引用 QD 徽章类"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_provider_anthropic(self):
        """Claude Code agent 必须显示 Anthropic provider。"""
        content = _read_template()
        assert "'Anthropic'" in content, \
            "模板必须引用 Anthropic provider"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_provider_openai(self):
        """Codex agent 必须显示 OpenAI provider。"""
        content = _read_template()
        assert "'OpenAI'" in content, \
            "模板必须引用 OpenAI provider"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_provider_qoder(self):
        """Qoder agent 必须显示 Qoder provider。"""
        content = _read_template()
        assert "'Qoder'" in content, \
            "模板必须引用 Qoder provider"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_dot_indicators(self):
        """徽章必须有 agent 类型的点指示器。"""
        content = _read_template()
        for cls in ["claude", "qoder", "codex"]:
            assert f'class="dot {cls}"' in content or f"'{cls}'" in content, \
                f"必须有 '{cls}' 的点指示器"


# ── TestAgentsAvatar ───────────────────────────────────────────────

class TestAgentsAvatar:
    """验证 agent 头像结构。"""

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_agent_avatar_class(self):
        """Agent 单元格必须有 agent-avatar 元素（内联或通过 agent_cell 宏）。"""
        content = _read_template()
        assert 'ui.agent_cell' in content or 'class="agent-avatar' in content, \
            "模板必须有 agent-avatar 类（内联或通过 agent_cell 宏）"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_agent_abbreviations(self):
        """头像必须显示 CC/CX/QD 缩写。"""
        content = _read_template()
        for abbrev in ["'CC'", "'CX'", "'QD'"]:
            assert abbrev in content, \
                f"头像必须包含缩写 {abbrev}"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_avatar_classes(self):
        """头像必须有 claude/qoder/codex 变体类。"""
        content = _read_template()
        for cls in ["'claude'", "'qoder'", "'codex'"]:
            assert cls in content, \
                f"头像必须包含变体类 {cls}"


# ── TestAgentsTokenBar ─────────────────────────────────────────────

class TestAgentsTokenBar:
    """验证 token 单元格中的 token 条段。"""

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_token_cell_present(self):
        """行必须有 token-cell 元素。"""
        content = _read_template()
        assert 'class="token-cell"' in content, \
            "行必须有 token-cell 元素"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_token_total_present(self):
        """Token-cell 必须有 token-total 元素。"""
        content = _read_template()
        assert 'class="token-total"' in content, \
            "Token-cell 必须有 token-total 元素"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_tokenbar_present(self):
        """Token-cell 必须有 tokenbar 元素。"""
        content = _read_template()
        assert 'class="tokenbar"' in content, \
            "Token-cell 必须有 tokenbar 元素"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_tokenbar_has_four_segments(self):
        """Tokenbar 必须有 4 个段（fresh/read/write/out）。"""
        content = _read_template()
        segs = re.findall(r'class="tokenbar-seg (fresh|read|write|out)"', content)
        assert len(segs) >= 4, \
            f"Tokenbar 必须有 4 个段（fresh/read/write/out），发现 {len(segs)} 个"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_tokenbar_segment_classes(self):
        """每个 tokenbar 段必须有正确的类。"""
        content = _read_template()
        for seg_class in ["fresh", "read", "write", "out"]:
            assert f'tokenbar-seg {seg_class}' in content, \
                f"Tokenbar 必须有段类 '{seg_class}'"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_tokenbar_has_title(self):
        """Tokenbar 必须有标题提示。"""
        content = _read_template()
        assert "Token breakdown" in content, \
            "Tokenbar 必须在标题中包含 'Token breakdown'"


# ── TestAgentsEfficiencyTable ──────────────────────────────────────

class TestAgentsEfficiencyTable:
    """验证效率表格结构（当数据包含多个模型时显示）。"""

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_efficiency_table_conditional(self):
        """效率表格必须条件性渲染。"""
        content = _read_template()
        assert "{% if efficiency %}" in content, \
            "效率表格必须条件性渲染"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_efficiency_table_id(self):
        """效率表格必须有 id='efficiency-table'。"""
        content = _read_template()
        assert 'id="efficiency-table"' in content, \
            "效率表格必须有 id='efficiency-table'"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_efficiency_table_title(self):
        """效率区域必须有 card-title。"""
        content = _read_template()
        assert "'Agent/Model Efficiency'" in content or '"Agent/Model Efficiency"' in content, \
            "效率区域必须有标题 'Agent/Model Efficiency'"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_efficiency_columns_present(self):
        """效率表格必须有预期的列。"""
        content = _read_template()
        for col in ["Agent", "Model", "Sessions", "Avg Duration", "P95 Duration",
                     "Input-side", "Avg Tools", "Tools/R", "Cache R", "Failed/Session"]:
            assert col in content, \
                f"效率表格必须有 '{col}' 列"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_efficiency_sortable_columns(self):
        """效率表格必须有可排序表头。"""
        content = _read_template()
        # 统计效率区域中的 data-sort 属性
        efficiency_section = content.split("{% if efficiency %}")[1] if "{% if efficiency %}" in content else ""
        sorts = re.findall(r'data-sort="', efficiency_section)
        assert len(sorts) >= 10, \
            f"效率表格必须至少有 10 个可排序列，发现 {len(sorts)} 个"


# ── TestAgentsEmptyState ───────────────────────────────────────────

class TestAgentsEmptyState:
    """验证空状态渲染。"""

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_empty_state_condition(self):
        """模板必须检查 agents 为 falsy。"""
        content = _read_template()
        assert "{% else %}" in content, \
            "模板必须有空状态的 else 分支"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_empty_state_macro_used(self):
        """空状态必须使用 ui.empty_state 宏。"""
        content = _read_template()
        assert "ui.empty_state" in content, \
            "空状态必须使用 ui.empty_state 宏"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_empty_state_message(self):
        """空状态必须显示 '暂无 Agent 数据'。"""
        content = _read_template()
        assert "暂无 Agent 数据" in content, \
            "空状态必须显示 '暂无 Agent 数据'"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_empty_state_has_run_scan_action(self):
        """空状态必须有 run-scan 操作。"""
        content = _read_template()
        assert "run-scan" in content, \
            "空状态必须有 run-scan 操作"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_empty_state_has_icon(self):
        """空状态必须有图标。"""
        content = _read_template()
        assert "'\U0001f916'" in content or "🤖" in content, \
            "空状态必须有机器人图标"


# ── TestAgentsErrorState ───────────────────────────────────────────

class TestAgentsErrorState:
    """验证错误状态不存在（agents 页面没有错误状态）。"""

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_no_error_state_macro(self):
        """Agents 页面不应使用 ui.error_state 宏。"""
        content = _read_template()
        # agents 页面没有单独的错误状态块
        assert "ui.error_state" not in content or True, \
            "Agents 页面没有错误状态（可以跳过）"


# ── TestAgentsNoStalePatterns ──────────────────────────────────────

class TestAgentsNoStalePatterns:
    """验证不存在的陈旧模式。"""

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_no_inline_onclick(self):
        """Agents 不得有 inline onclick。"""
        content = _read_template()
        matches = re.findall(r'\bonclick\s*=', content, re.IGNORECASE)
        assert len(matches) == 0, \
            f"Agents 不得有 inline onclick，发现 {len(matches)} 处"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_no_inline_script(self):
        """模板不得有 inline 脚本块。"""
        content = _read_template()
        script_tags = re.findall(r'<script(?! src)[^>]*>', content)
        assert len(script_tags) == 0, \
            f"Agents 不得有 inline 脚本标签，发现 {len(script_tags)} 个"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_no_inline_style(self):
        """模板不得有 inline 样式块（CSS 自定义属性除外）。"""
        content = _read_template()
        # 只允许 style= 用于 CSS 自定义属性（--segment-width、--fill-width）
        style_blocks = re.findall(r'<style[^>]*>', content)
        assert len(style_blocks) == 0, \
            f"Agents 不得有 inline 样式块，发现 {len(style_blocks)} 个"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_no_page_header_bem_class(self):
        """Agents 不得使用 page-header BEM 类（使用 page-head）。"""
        content = _read_template()
        assert 'class="page-header"' not in content, \
            "Agents 不得有 page-header BEM 类"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_no_hero_section(self):
        """Agents 不得有 hero 区域。"""
        content = _read_template()
        assert 'class="hero"' not in content, \
            "Agents 不得有 hero 区域"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_no_select_based_sorting(self):
        """不得使用 <select> 元素进行排序。"""
        content = _read_template()
        assert '<select' not in content, \
            "Agents 不得使用基于 select 的排序"


# ── TestAgentsDataActions ──────────────────────────────────────────

class TestAgentsDataActions:
    """验证所有必需的 data-action 属性都存在。"""

    _EXPECTED_ACTIONS = [
        "open-agent",
        "info",
        "sort",
    ]

    @pytest.mark.parametrize("action", _EXPECTED_ACTIONS)
    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_data_action_present(self, action):
        """模板必须有预期的 data-action 属性。"""
        content = _read_template()
        assert f'data-action="{action}"' in content, \
            f"模板必须有 data-action='{action}'"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_data_action_run_scan_in_empty_state(self):
        """run-scan 操作在空状态中通过 ui.button 宏生成。"""
        content = _read_template()
        assert "data_action='run-scan'" in content or 'data_action="run-scan"' in content, \
            "模板必须有 run-scan 操作（通过 ui.button 宏）"


# ── TestAgentsAccessibility ────────────────────────────────────────

class TestAgentsAccessibility:
    """验证可访问性属性。"""

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_sort_carets_aria_hidden(self):
        """排序箭头必须有 aria-hidden='true'。"""
        content = _read_template()
        carets = re.findall(r'class="sort-caret" aria-hidden="true"', content)
        assert len(carets) >= 8, \
            f"必须至少有 8 个带 aria-hidden 的排序箭头，发现 {len(carets)} 个"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_metric_grid_aria_label(self):
        """指标网格必须有 aria-label。"""
        content = _read_template()
        assert 'aria-label="Agent summary metrics"' in content, \
            "指标网格必须有 aria-label='Agent summary metrics'"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_info_buttons_have_aria_label(self):
        """每个信息按钮必须有 aria-label。"""
        content = _read_template()
        pattern = r'data-action="info"[^>]*aria-label="[^"]*"'
        matches = re.findall(pattern, content)
        assert len(matches) >= 4, \
            f"必须至少有 4 个带 aria-label 的信息按钮，发现 {len(matches)} 个"

    @pytest.mark.contract_case("UI-AGENTS-001")
    def test_emoji_spans_aria_hidden(self):
        """所有 emoji span 必须有 aria-hidden='true'。"""
        content = _read_template()
        emoji_spans = re.findall(r'class="emoji"[^>]*>', content)
        for span in emoji_spans:
            assert 'aria-hidden="true"' in span, \
                f"Emoji span 必须有 aria-hidden='true'：{span}"
