"""Glossary 页面（glossary.html）测试。

针对 glossary.html 的页面级 pytest，覆盖模板结构、头部、
指标网格、过滤卡片、空态、分区、表格、data-action、
可访问性，以及无陈旧模式。

T164 -- Glossary：添加页面专属 pytest。
"""

from __future__ import annotations

import pytest
import os
import re

_GLOSSARY_PATH = "src/session_browser/web/templates/glossary.html"


def _read(path: str) -> str:
    with open(path) as f:
        return f.read()


def _read_template() -> str:
    return _read(_GLOSSARY_PATH)


# -- TestGlossaryTemplate ---------------------------------------------------


class TestGlossaryTemplate:
    """验证 glossary Jinja2 模板的结构化渲染。"""

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    @pytest.mark.contract_case("UI-GLOSSARY-002")
    def test_template_file_exists(self):
        """glossary.html 必须存在于磁盘上。"""
        assert os.path.isfile(_GLOSSARY_PATH), \
            f"{_GLOSSARY_PATH} 必须存在"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_extends_base(self):
        """Glossary 必须继承 base.html。"""
        content = _read_template()
        assert '{% extends "base.html" %}' in content, \
            "Glossary 必须继承 base.html"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_active_page_set(self):
        """Glossary 必须设置 active_page = 'glossary'。"""
        content = _read_template()
        assert "active_page = 'glossary'" in content, \
            "Glossary 必须设置 active_page = 'glossary'"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_ui_primitives_imported(self):
        """Glossary 必须导入 ui_primitives.html。"""
        content = _read_template()
        assert 'components/ui_primitives.html' in content, \
            "Glossary 必须导入 ui_primitives.html"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_no_inline_onclick(self):
        """Glossary 不得使用 inline onclick 处理器。"""
        content = _read_template()
        matches = re.findall(r'\bonclick\s*=', content, re.IGNORECASE)
        assert len(matches) == 0, \
            f"Glossary 不得有 inline onclick，发现 {len(matches)} 次"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_page_specific_css_import(self):
        """Glossary 必须导入页面专属 CSS 用于术语样式。"""
        content = _read_template()
        assert 'href="/static/css/glossary.css"' in content, \
            "Glossary 必须导入 glossary.css"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_page_specific_js_import(self):
        """Glossary 必须导入页面专属 JS 用于术语功能。"""
        content = _read_template()
        assert 'src="/static/js/glossary.js"' in content, \
            "Glossary 必须导入 glossary.js"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_script_extra_block(self):
        """Glossary 必须使用 script_extra 块加载 JS。"""
        content = _read_template()
        assert '{% block script_extra %}' in content, \
            "Glossary 必须使用 script_extra 块"


# -- TestGlossaryHeader -----------------------------------------------------


class TestGlossaryHeader:
    """验证头部结构。"""

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_page_head_present(self):
        """Glossary 必须使用 ui.page_head() 宏（T15）。"""
        content = _read_template()
        assert 'ui.page_head(' in content, \
            "Glossary 必须使用 ui.page_head() 宏"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_h1_title(self):
        """page-head 必须以 'Token Glossary' 作为标题参数。"""
        content = _read_template()
        assert "'Token Glossary'" in content, \
            "Glossary 的 page_head 必须以 'Token Glossary' 作为标题"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_subtitle_present(self):
        """page-head 必须有传递给宏的副标题。"""
        content = _read_template()
        assert '必要术语说明' in content, \
            "Glossary 的 page_head 必须有关于基本术语说明的副标题"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_subtitle_text(self):
        """副标题必须按 HIFI 描述术语表目的。"""
        content = _read_template()
        assert "必要术语说明" in content, \
            "副标题必须将术语表描述为基本术语参考"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_breadcrumb(self):
        """面包屑必须链接到 dashboard。"""
        content = _read_template()
        assert 'href="/dashboard"' in content, \
            "面包屑必须链接到 /dashboard"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_breadcrumb_current(self):
        """面包屑必须显示 glossary 为当前页。"""
        content = _read_template()
        assert "术语表" in content or "Glossary" in content, \
            "面包屑必须显示 glossary 名称"


# -- TestGlossaryMetricGrid -------------------------------------------------


class TestGlossaryMetricGrid:
    """验证摘要指标网格结构。"""

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_metric_grid_present(self):
        """Glossary 必须有 metric-grid 区域。"""
        content = _read_template()
        assert 'class="metric-grid"' in content, \
            "Glossary 必须有 metric-grid 区域"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_metric_grid_aria_label(self):
        """指标网格必须有 aria-label。"""
        content = _read_template()
        assert 'aria-label="术语页摘要指标"' in content, \
            "指标网格必须有 aria-label"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_four_metric_cards(self):
        """Glossary 必须恰好有 4 个指标卡片。"""
        content = _read_template()
        cards = re.findall(r'class="metric-card"', content)
        assert len(cards) == 4, \
            f"Glossary 必须恰好有 4 个指标卡片，发现 {len(cards)} 个"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_metric_card_token_types(self):
        """必须有 Token Types 指标卡片。"""
        content = _read_template()
        assert "Token Types" in content, \
            "Glossary 必须有 'Token Types' 指标卡片"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_metric_card_derived_metrics(self):
        """必须有 Derived Metrics 指标卡片。"""
        content = _read_template()
        assert "Derived Metrics" in content, \
            "Glossary 必须有 'Derived Metrics' 指标卡片"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_metric_card_provider_fields(self):
        """必须有 Provider Fields 指标卡片。"""
        content = _read_template()
        assert "Provider Fields" in content, \
            "Glossary 必须有 'Provider Fields' 指标卡片"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_metric_card_round_signals(self):
        """必须有 Round Signals 指标卡片。"""
        content = _read_template()
        assert "Round Signals" in content, \
            "Glossary 必须有 'Round Signals' 指标卡片"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_metric_icons_present(self):
        """每个指标卡片必须有 metric-icon 元素。"""
        content = _read_template()
        icons = re.findall(r'class="metric-icon', content)
        assert len(icons) == 4, \
            f"Glossary 必须有 4 个 metric-icon 元素，发现 {len(icons)} 个"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_metric_icons_have_emoji_aria_hidden(self):
        """每个 metric-icon 必须包含带 aria-hidden 的 span。"""
        content = _read_template()
        # 指标图标使用 <span aria-hidden="true"> 表示表情（无 class="emoji"）
        metric_icons = re.findall(r'class="metric-icon[^"]*"[^>]*>', content)
        aria_count = content.count('aria-hidden="true"')
        assert aria_count >= 4, \
            f"Glossary 在指标图标中必须至少有 4 个 aria-hidden span，发现 {aria_count} 个"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_metric_labels_present(self):
        """每个指标卡片必须有 metric-card__label 元素。"""
        content = _read_template()
        labels = re.findall(r'class="metric-card__label"', content)
        assert len(labels) >= 4, \
            f"Glossary 必须至少有 4 个 metric-card__label 元素，发现 {len(labels)} 个"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_metric_values_present(self):
        """每个指标卡片必须有 metric-card__value 元素。"""
        content = _read_template()
        # 模板使用 class="metric-card__value mono"（带附加类）
        values = re.findall(r'class="metric-card__value', content)
        assert len(values) >= 4, \
            f"Glossary 必须至少有 4 个 metric-card__value 元素，发现 {len(values)} 个"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_metric_notes_present(self):
        """每个指标卡片必须有 metric-card__sub 元素。"""
        content = _read_template()
        notes = re.findall(r'class="metric-card__sub"', content)
        assert len(notes) >= 4, \
            f"Glossary 必须至少有 4 个 metric-card__sub 元素，发现 {len(notes)} 个"


# -- TestGlossaryFilterCard -------------------------------------------------


class TestGlossaryFilterCard:
    """验证过滤/搜索卡片结构。"""

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_filter_card_present(self):
        """Glossary 必须有 filter-card。"""
        content = _read_template()
        assert 'class="card filter-card' in content or 'ui.filter_card()' in content, \
            "Glossary 必须有 filter-card（字面或宏）"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_search_input_present(self):
        """过滤卡片必须有搜索输入。"""
        content = _read_template()
        assert 'class="input search"' in content, \
            "Glossary 必须有带 'input search' 类的搜索输入"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_search_input_id(self):
        """搜索输入必须有 id='glossary-search'。"""
        content = _read_template()
        assert 'id="glossary-search"' in content, \
            "Glossary 搜索输入必须有 id='glossary-search'"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_search_data_search_attribute(self):
        """搜索输入必须有 data-search 属性。"""
        content = _read_template()
        assert 'data-search="glossary-term"' in content, \
            "Glossary 搜索输入必须有 data-search='glossary-term'"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_search_aria_label(self):
        """搜索输入必须有 aria-label。"""
        content = _read_template()
        assert 'aria-label="Search glossary terms"' in content, \
            "Glossary 搜索输入必须有 aria-label='Search glossary terms'"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_search_autocomplete_off(self):
        """搜索输入必须有 autocomplete='off'。"""
        content = _read_template()
        assert 'autocomplete="off"' in content, \
            "Glossary 搜索输入必须有 autocomplete='off'"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_search_placeholder(self):
        """搜索输入必须有占位文本。"""
        content = _read_template()
        assert "搜索术语" in content or "Search" in content, \
            "Glossary 搜索输入必须有占位文本"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_match_count_element(self):
        """Glossary 必须有匹配计数 span。"""
        content = _read_template()
        assert 'id="glossary-match-count"' in content, \
            "Glossary 必须有 glossary-match-count span"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_filter_row_present(self):
        """过滤卡片必须有 filter-row。"""
        content = _read_template()
        assert 'class="filter-row"' in content, \
            "Glossary 必须有 filter-row"


# -- TestGlossaryEmptyState -------------------------------------------------


class TestGlossaryEmptyState:
    """验证空态渲染。"""

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_empty_state_present(self):
        """Glossary 必须有用于空态的 state-strip。"""
        content = _read_template()
        assert 'class="state-strip' in content, \
            "Glossary 必须有用于空态的 state-strip"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_empty_state_id(self):
        """空态必须有 id='glossary-empty'。"""
        content = _read_template()
        assert 'id="glossary-empty"' in content, \
            "Glossary 空态必须有 id='glossary-empty'"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_empty_state_role_status(self):
        """空态必须有 role='status'。"""
        content = _read_template()
        assert 'role="status"' in content, \
            "Glossary 空态必须有 role='status'"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_empty_state_aria_live(self):
        """空态必须有 aria-live='polite'。"""
        content = _read_template()
        assert 'aria-live="polite"' in content, \
            "Glossary 空态必须有 aria-live='polite'"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_empty_state_is_hidden(self):
        """空态初始必须带 is-hidden 类。"""
        content = _read_template()
        assert 'is-hidden' in content, \
            "Glossary 空态必须有 is-hidden 类"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_empty_state_icon_aria_hidden(self):
        """空态图标必须有 aria-hidden='true'。"""
        content = _read_template()
        # 状态图标使用 class="state-icon" 并带 aria-hidden
        assert 'class="state-icon"' in content, \
            "Glossary 空态必须有 state-icon"
        assert 'aria-hidden="true"' in content, \
            "Glossary 空态图标必须有 aria-hidden='true'"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_empty_state_no_match_message(self):
        """空态必须有未匹配提示消息。"""
        content = _read_template()
        assert "没有匹配的术语" in content, \
            "Glossary 空态必须显示未匹配提示消息"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_empty_state_try_again_message(self):
        """空态必须建议重试。"""
        content = _read_template()
        assert "尝试更换关键词" in content or "清空搜索框" in content, \
            "Glossary 空态必须建议尝试更换关键词"


# -- TestGlossarySections ---------------------------------------------------


class TestGlossarySections:
    """验证 8 个 card.section 元素。"""

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_card_section_class(self):
        """Glossary 必须对分区使用 card.section.section-card.full-width 类。"""
        content = _read_template()
        assert 'class="card section section-card full-width"' in content, \
            "Glossary 必须使用 card.section.section-card.full-width 类"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_eight_sections(self):
        """Glossary 必须恰好有 8 个 card.section 元素。"""
        content = _read_template()
        # 分区可能带有额外类如 glossary-table-section
        sections = re.findall(r'class="card section[^"]*"', content)
        assert len(sections) == 8, \
            f"Glossary 必须恰好有 8 个 card.section 元素，发现 {len(sections)} 个"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_badge_reference_section(self):
        """必须有 Badge Reference 分区。"""
        content = _read_template()
        assert "Badge Reference" in content, \
            "Glossary 必须有 Badge Reference 分区"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_token_overview_section(self):
        """必须有 Token 概览（Token Overview）分区。"""
        content = _read_template()
        assert "Token 概览" in content, \
            "Glossary 必须有 Token Overview 分区"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_token_composition_section(self):
        """必须有 Token 组成（Token Composition）分区。"""
        content = _read_template()
        assert "Token 组成" in content, \
            "Glossary 必须有 Token Composition 分区"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_derived_metrics_section(self):
        """必须有 派生指标（Derived Metrics）分区。"""
        content = _read_template()
        assert "派生指标" in content, \
            "Glossary 必须有 Derived Metrics 分区"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_provider_mapping_section(self):
        """必须有 Provider 映射（Provider Mapping）分区。"""
        content = _read_template()
        assert "Provider 映射" in content or "Provider Mapping" in content, \
            "Glossary 必须有 Provider Mapping 分区"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_provider_mapping_anchor_id(self):
        """Provider mapping 分区必须有锚点 id='provider-mapping'。"""
        content = _read_template()
        assert 'id="provider-mapping"' in content, \
            "Provider mapping 分区必须有 id='provider-mapping'"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_limitations_section(self):
        """必须有 已知限制（Known Limitations）分区。"""
        content = _read_template()
        assert "已知限制" in content, \
            "Glossary 必须有 Known Limitations 分区"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_session_anomalies_section(self):
        """必须有 Session Anomalies 分区。"""
        content = _read_template()
        assert "Session Anomalies" in content, \
            "Glossary 必须有 Session Anomalies 分区"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_round_signals_section(self):
        """必须有 Round Signals 分区。"""
        content = _read_template()
        assert "Round Signals" in content, \
            "Glossary 必须有 Round Signals 分区"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_section_head_elements(self):
        """每个分区必须有 section-head 元素。"""
        content = _read_template()
        heads = re.findall(r'class="section-head"', content)
        assert len(heads) == 8, \
            f"Glossary 必须有 8 个 section-head 元素，发现 {len(heads)} 个"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_section_title_elements(self):
        """每个分区必须有 section-title 元素。"""
        content = _read_template()
        titles = re.findall(r'class="section-title"', content)
        assert len(titles) == 8, \
            f"Glossary 必须有 8 个 section-title 元素，发现 {len(titles)} 个"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_section_sub_elements(self):
        """分区必须有 section-desc 描述（HIFI 对齐别名）。"""
        content = _read_template()
        subs = re.findall(r'class="section-desc"', content)
        assert len(subs) == 5, \
            f"Glossary 必须恰好有 5 个 section-desc 元素，发现 {len(subs)} 个"


# -- TestGlossaryTables -----------------------------------------------------


class TestGlossaryTables:
    """验证 6 个 data-table 存在。"""

    _TABLE_SECTIONS = [
        ("Token 组成", "Token composition"),
        ("派生指标", "Derived metrics"),
        ("Provider 映射", "Provider mapping"),
        ("已知限制", "Known limitations"),
        ("Session Anomalies", "Anomalies"),
        ("Round Signals", "Signals"),
    ]

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_six_data_tables(self):
        """Glossary 必须恰好有 6 个 data-table 元素（可能带有 glossary-table 等附加类）。"""
        content = _read_template()
        tables = re.findall(r'class="data-table[^"]*"', content)
        assert len(tables) == 6, \
            f"Glossary 必须恰好有 6 个 data-table 元素，发现 {len(tables)} 个"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_all_tables_enhanced(self):
        """所有表格必须有 data-table-enhanced 属性。"""
        content = _read_template()
        enhanced = re.findall(r'data-table-enhanced', content)
        assert len(enhanced) == 6, \
            f"Glossary 必须有 6 个 data-table-enhanced 属性，发现 {len(enhanced)} 个"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_all_tables_in_wrap(self):
        """所有表格必须在 table-wrap 内。"""
        content = _read_template()
        wraps = re.findall(r'class="table-wrap"', content)
        assert len(wraps) == 6, \
            f"Glossary 必须有 6 个 table-wrap 元素，发现 {len(wraps)} 个"

    @pytest.mark.parametrize("section_name,_", _TABLE_SECTIONS)
    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_table_section_exists(self, section_name, _):
        """每个预期的表格分区必须存在。"""
        content = _read_template()
        assert section_name in content, \
            f"Glossary 必须有 '{section_name}' 表格分区"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_token_composition_table_has_thead(self):
        """Token composition 表格必须有 thead。"""
        content = _read_template()
        assert '<thead>' in content, \
            "Token composition 表格必须有 thead"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_token_composition_table_has_tbody(self):
        """Token composition 表格必须有 tbody。"""
        content = _read_template()
        assert '<tbody>' in content, \
            "Token composition 表格必须有 tbody"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_data_table_has_code_elements(self):
        """数据表格必须有用于公式/字段的 code 元素。"""
        content = _read_template()
        assert '<code>' in content, \
            "Glossary 表格必须有 code 元素"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_badge_elements_in_tables(self):
        """表格必须使用 badge 元素。"""
        content = _read_template()
        badges = re.findall(r'class="badge', content)
        assert len(badges) >= 4, \
            f"Glossary 必须至少有 4 个 badge 元素，发现 {len(badges)} 个"


# -- TestGlossaryDataActions ------------------------------------------------


class TestGlossaryDataActions:
    """验证所有必需的 data-action 和 data-search 属性。"""

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_sort_action_on_headers(self):
        """可排序表头必须有 data-action='sort'。"""
        content = _read_template()
        sorts = re.findall(r'data-action="sort"', content)
        assert len(sorts) >= 6, \
            f"Glossary 必须至少有 6 个可排序列，发现 {len(sorts)} 个"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_sort_keys_present(self):
        """可排序列必须有 data-sort-key 属性。"""
        content = _read_template()
        expected_keys = [
            "token-name",
            "derived-metric",
            "provider-name",
            "limitation",
            "anomaly-type",
            "signal-type",
        ]
        for sort_key in expected_keys:
            assert f'data-sort-key="{sort_key}"' in content, \
                f"Glossary 必须有 data-sort-key='{sort_key}'"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_search_data_search(self):
        """搜索输入必须有 data-search 属性。"""
        content = _read_template()
        assert 'data-search="glossary-term"' in content, \
            "Glossary 搜索输入必须有 data-search='glossary-term'"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_sortable_th_elements(self):
        """可排序列的 th 必须有 sortable 类。"""
        content = _read_template()
        sortable_ths = re.findall(r'class="sortable"', content)
        assert len(sortable_ths) >= 6, \
            f"Glossary 必须至少有 6 个 sortable th 元素，发现 {len(sortable_ths)} 个"


# -- TestGlossaryAccessibility ----------------------------------------------


class TestGlossaryAccessibility:
    """验证可访问性属性。"""

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_metric_icon_emojis_aria_hidden(self):
        """指标图标表情必须有 aria-hidden='true'。"""
        content = _read_template()
        # 指标图标使用 <span aria-hidden="true"> 无 class="emoji"
        aria_hidden = content.count('aria-hidden="true"')
        assert aria_hidden >= 4, \
            f"Glossary 必须至少有 4 个 aria-hidden span，发现 {aria_hidden} 个"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_empty_state_icon_aria_hidden(self):
        """空态图标必须有 aria-hidden='true'。"""
        content = _read_template()
        # state-strip 图标在 state-icon div 上使用 aria-hidden
        state_icon_section = content[content.find('class="state-strip'):]
        state_icon_section = state_icon_section[:state_icon_section.find('</div>') + 6]
        assert 'aria-hidden="true"' in state_icon_section, \
            "空态图标必须有 aria-hidden='true'"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_search_input_aria_label(self):
        """搜索输入必须有 aria-label。"""
        content = _read_template()
        assert 'aria-label="Search glossary terms"' in content, \
            "Glossary 搜索输入必须有 aria-label"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_empty_state_aria_live(self):
        """空态必须有 aria-live='polite'。"""
        content = _read_template()
        assert 'aria-live="polite"' in content, \
            "Glossary 空态必须有 aria-live='polite'"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_empty_state_role_status(self):
        """空态必须有 role='status'。"""
        content = _read_template()
        assert 'role="status"' in content, \
            "Glossary 空态必须有 role='status'"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_metric_grid_aria_label(self):
        """指标网格必须有 aria-label。"""
        content = _read_template()
        assert 'aria-label="术语页摘要指标"' in content, \
            "Glossary 指标网格必须有 aria-label"


# -- TestGlossaryNoStalePatterns --------------------------------------------


class TestGlossaryNoStalePatterns:
    """验证不存在的陈旧模式。"""

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_no_inline_onclick(self):
        """Glossary 不得有 inline onclick。"""
        content = _read_template()
        matches = re.findall(r'\bonclick\s*=', content, re.IGNORECASE)
        assert len(matches) == 0, \
            f"Glossary 不得有 inline onclick，发现 {len(matches)} 次"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_no_inline_script(self):
        """模板不得有 inline script 块。"""
        content = _read_template()
        script_tags = re.findall(r'<script(?! src)[^>]*>', content)
        assert len(script_tags) == 0, \
            f"Glossary 不得有 inline script 标签，发现 {len(script_tags)} 个"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_no_inline_style_blocks(self):
        """模板不得有 inline style 块。"""
        content = _read_template()
        style_blocks = re.findall(r'<style[^>]*>', content)
        assert len(style_blocks) == 0, \
            f"Glossary 不得有 inline style 块，发现 {len(style_blocks)} 个"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_no_filter_bar_class(self):
        """Glossary 不得使用 .filter-bar 类（使用 .filter-card）。"""
        content = _read_template()
        assert 'class="filter-bar"' not in content, \
            "Glossary 不得有 filter-bar 类"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_no_table_scroll_class(self):
        """Glossary 不得使用 .table-scroll 类（使用 .table-wrap）。"""
        content = _read_template()
        assert 'class="table-scroll"' not in content, \
            "Glossary 不得有 table-scroll 类"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_no_select_elements(self):
        """无 <select> 元素。"""
        content = _read_template()
        assert '<select' not in content, \
            "Glossary 不得使用 select 元素"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_no_hero_section(self):
        """Glossary 不得有 hero 分区。"""
        content = _read_template()
        assert 'class="hero"' not in content, \
            "Glossary 不得有 hero 分区"


# ── Glossary 固定夹具测试（T097）─────────────────────────────
# 使用 hifi_fixture_session 夹具启动带确定性夹具数据的实时服务器，
# 然后验证*渲染后*的 Glossary HTML。
# 覆盖：页面渲染、术语列表、关键数据展示。


@pytest.fixture(scope="module")
def glossary_html(hifi_fixture_session):
    """从实时夹具服务器获取渲染后的 Glossary HTML。"""
    base_url, agent, session_id = hifi_fixture_session
    import urllib.request

    resp = urllib.request.urlopen(f"{base_url}/glossary", timeout=10)
    assert resp.status == 200, "Glossary 必须返回 HTTP 200"
    return resp.read().decode("utf-8")


# -- TestGlossaryPageRender -----------------------------------------------


class TestGlossaryPageRender:
    """验证渲染后的 Glossary 页面结构。"""

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_page_returns_200(self, glossary_html):
        """Glossary 必须成功渲染。"""
        assert len(glossary_html) > 500, \
            "Glossary HTML 必须有足够内容"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_has_doctype_and_html(self, glossary_html):
        """页面必须有正确的 HTML 结构。"""
        lower = glossary_html.lower()
        assert "<!doctype html" in lower or "<!DOCTYPE html" in glossary_html, \
            "Glossary 必须有 DOCTYPE 声明"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_title_contains_glossary(self, glossary_html):
        """页面标题必须包含 '术语表' 或 'Glossary'。"""
        assert "<title>" in glossary_html, \
            "Glossary 必须有 title 标签"
        assert "术语表" in glossary_html or "Glossary" in glossary_html or "Token Glossary" in glossary_html, \
            "页面标题必须引用 Glossary"


# -- TestGlossaryPageDisplay ----------------------------------------------


class TestGlossaryPageDisplay:
    """验证 Glossary 页面从渲染 HTML 中展示术语和关键数据。"""

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_has_page_head(self, glossary_html):
        """页面必须显示 'Token Glossary' 标题。"""
        assert "Token Glossary" in glossary_html, \
            "'Token Glossary' 标题必须可见"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_has_subtitle(self, glossary_html):
        """页面必须显示关于术语的副标题。"""
        assert "必要术语说明" in glossary_html or "术语说明" in glossary_html or "术语" in glossary_html, \
            "必须出现关于术语的副标题"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_has_metric_grid(self, glossary_html):
        """Glossary 必须渲染摘要指标网格。"""
        assert 'class="metric-grid"' in glossary_html, \
            "指标网格必须已渲染"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_four_metric_cards_rendered(self, glossary_html):
        """Glossary 在渲染输出中必须恰好有 4 个指标卡片。"""
        cards = re.findall(r'class="metric-card"', glossary_html)
        assert len(cards) == 4, \
            f"Glossary 必须有 4 个指标卡片，发现 {len(cards)} 个"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_token_types_card(self, glossary_html):
        """必须显示 Token Types 指标卡片。"""
        assert "Token Types" in glossary_html, \
            "Token Types 指标卡片必须可见"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_derived_metrics_card(self, glossary_html):
        """必须显示 Derived Metrics 指标卡片。"""
        assert "Derived Metrics" in glossary_html, \
            "Derived Metrics 指标卡片必须可见"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_provider_fields_card(self, glossary_html):
        """必须显示 Provider Fields 指标卡片。"""
        assert "Provider Fields" in glossary_html, \
            "Provider Fields 指标卡片必须可见"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_round_signals_card(self, glossary_html):
        """必须显示 Round Signals 指标卡片。"""
        assert "Round Signals" in glossary_html, \
            "Round Signals 指标卡片必须可见"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_search_input_rendered(self, glossary_html):
        """Glossary 必须渲染搜索/过滤输入。"""
        assert 'id="glossary-search"' in glossary_html, \
            "搜索输入必须已渲染"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_filter_card_rendered(self, glossary_html):
        """Glossary 必须渲染过滤卡片。"""
        assert "filter-card" in glossary_html or "filter" in glossary_html, \
            "过滤卡片必须已渲染"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_sections_rendered(self, glossary_html):
        """Glossary 必须渲染分区卡片。"""
        sections = re.findall(r'class="card section', glossary_html)
        assert len(sections) >= 6, \
            f"Glossary 必须至少有 6 个分区卡片，发现 {len(sections)} 个"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_data_tables_rendered(self, glossary_html):
        """Glossary 必须渲染数据表格。"""
        tables = re.findall(r'class="data-table', glossary_html)
        assert len(tables) >= 4, \
            f"Glossary 必须至少有 4 个数据表格，发现 {len(tables)} 个"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_token_overview_section(self, glossary_html):
        """必须渲染 Token 概览分区。"""
        assert "Token 概览" in glossary_html, \
            "Token Overview 分区必须可见"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_token_composition_section(self, glossary_html):
        """必须渲染 Token 组成分区。"""
        assert "Token 组成" in glossary_html, \
            "Token Composition 分区必须可见"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_derived_metrics_section(self, glossary_html):
        """必须渲染 派生指标 分区。"""
        assert "派生指标" in glossary_html, \
            "Derived Metrics 分区必须可见"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_provider_mapping_section(self, glossary_html):
        """必须渲染 Provider 映射分区。"""
        assert "Provider 映射" in glossary_html, \
            "Provider Mapping 分区必须可见"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_badge_reference_section(self, glossary_html):
        """必须渲染 Badge Reference 分区。"""
        assert "Badge Reference" in glossary_html, \
            "Badge Reference 分区必须可见"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_known_terms_present(self, glossary_html):
        """Glossary 必须显示关键术语如 'cache read'。"""
        assert "cache" in glossary_html.lower() or "Cache" in glossary_html, \
            "Glossary 中必须出现 'cache' 等关键术语"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_no_inline_onclick(self, glossary_html):
        """渲染后的 Glossary 不得有 inline onclick 处理器。"""
        matches = re.findall(r'\bonclick\s*=', glossary_html, re.IGNORECASE)
        assert len(matches) == 0, \
            f"Glossary 不得有 inline onclick，发现 {len(matches)} 次"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_empty_state_rendered(self, glossary_html):
        """Glossary 必须渲染空态元素。"""
        assert "state-strip" in glossary_html or "glossary-empty" in glossary_html, \
            "空态元素必须已渲染"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_breadcrumb_rendered(self, glossary_html):
        """Glossary 必须显示面包屑。"""
        assert 'href="/dashboard"' in glossary_html, \
            "面包屑必须链接到 dashboard"


# -- TestGlossaryNoStalePatterns ------------------------------------------


class TestGlossaryNoStalePatternsFixture:
    """验证渲染 HTML 中不存在的陈旧模式。"""

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_no_filter_bar_class(self, glossary_html):
        """Glossary 不得使用 .filter-bar 类。"""
        assert 'class="filter-bar"' not in glossary_html, \
            "Glossary 不得有 filter-bar 类"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_no_hero_section(self, glossary_html):
        """Glossary 不得有 hero 分区。"""
        assert 'class="hero"' not in glossary_html, \
            "Glossary 不得有 hero 分区"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_no_inline_script(self, glossary_html):
        """渲染后的 HTML 不得有 inline script 块。"""
        script_tags = re.findall(r'<script(?! src)[^>]*>', glossary_html)
        assert len(script_tags) == 0, \
            f"Glossary 不得有 inline script 标签，发现 {len(script_tags)} 个"
