"""Tests for Glossary page (glossary.html).

Page-level pytest for glossary.html covering template structure, header,
metric grid, filter card, empty state, sections, tables, data actions,
accessibility, and absence of stale patterns.

T164 -- Glossary: Add page-specific pytest.
"""

from __future__ import annotations

import os
import re

import pytest

_GLOSSARY_PATH = "src/session_browser/web/templates/glossary.html"


def _read(path: str) -> str:
    with open(path) as f:
        return f.read()


def _read_template() -> str:
    return _read(_GLOSSARY_PATH)


# -- TestGlossaryTemplate ---------------------------------------------------


class TestGlossaryTemplate:
    """Verify the glossary Jinja2 template renders structurally."""

    def test_template_file_exists(self):
        """glossary.html must exist on disk."""
        assert os.path.isfile(_GLOSSARY_PATH), \
            f"{_GLOSSARY_PATH} must exist"

    def test_extends_base(self):
        """Glossary must extend base.html."""
        content = _read_template()
        assert '{% extends "base.html" %}' in content, \
            "Glossary must extend base.html"

    def test_active_page_set(self):
        """Glossary must set active_page = 'glossary'."""
        content = _read_template()
        assert "active_page = 'glossary'" in content, \
            "Glossary must set active_page = 'glossary'"

    def test_ui_primitives_imported(self):
        """Glossary must import ui_primitives.html."""
        content = _read_template()
        assert 'components/ui_primitives.html' in content, \
            "Glossary must import ui_primitives.html"

    def test_no_inline_onclick(self):
        """Glossary must not use inline onclick handlers."""
        content = _read_template()
        matches = re.findall(r'\bonclick\s*=', content, re.IGNORECASE)
        assert len(matches) == 0, \
            f"Glossary must not have inline onclick, found {len(matches)} occurrences"

    def test_page_specific_css_import(self):
        """Glossary must import page-specific CSS for glossary styling."""
        content = _read_template()
        assert 'href="/static/css/glossary.css"' in content, \
            "Glossary must import glossary.css"

    def test_page_specific_js_import(self):
        """Glossary must import page-specific JS for glossary functionality."""
        content = _read_template()
        assert 'src="/static/js/glossary.js"' in content, \
            "Glossary must import glossary.js"

    def test_script_extra_block(self):
        """Glossary must use script_extra block for JS."""
        content = _read_template()
        assert '{% block script_extra %}' in content, \
            "Glossary must use script_extra block"


# -- TestGlossaryHeader -----------------------------------------------------


class TestGlossaryHeader:
    """Verify header structure."""

    def test_page_head_present(self):
        """Glossary must use ui.page_head() macro (T15)."""
        content = _read_template()
        assert 'ui.page_head(' in content, \
            "Glossary must use ui.page_head() macro"

    def test_h1_title(self):
        """Page head must have 'Token Glossary' as title parameter."""
        content = _read_template()
        assert "'Token Glossary'" in content, \
            "Glossary page_head must have 'Token Glossary' as title"

    def test_subtitle_present(self):
        """Page head must have a subtitle passed to macro."""
        content = _read_template()
        assert '必要术语说明' in content, \
            "Glossary page_head must have subtitle about essential terminology"

    def test_subtitle_text(self):
        """Subtitle must describe the glossary purpose per HIFI."""
        content = _read_template()
        assert "必要术语说明" in content, \
            "Subtitle must describe glossary as essential terminology reference"

    def test_breadcrumb(self):
        """Breadcrumb must link to dashboard."""
        content = _read_template()
        assert 'href="/dashboard"' in content, \
            "Breadcrumb must link to /dashboard"

    def test_breadcrumb_current(self):
        """Breadcrumb must show glossary as current."""
        content = _read_template()
        assert "术语表" in content or "Glossary" in content, \
            "Breadcrumb must show glossary name"


# -- TestGlossaryMetricGrid -------------------------------------------------


class TestGlossaryMetricGrid:
    """Verify summary metric grid structure."""

    def test_metric_grid_present(self):
        """Glossary must have a metric-grid section."""
        content = _read_template()
        assert 'class="metric-grid"' in content, \
            "Glossary must have a metric-grid section"

    def test_metric_grid_aria_label(self):
        """Metric grid must have an aria-label."""
        content = _read_template()
        assert 'aria-label="术语页摘要指标"' in content, \
            "Metric grid must have aria-label"

    def test_four_metric_cards(self):
        """Glossary must have exactly 4 metric cards."""
        content = _read_template()
        cards = re.findall(r'class="metric-card"', content)
        assert len(cards) == 4, \
            f"Glossary must have exactly 4 metric cards, found {len(cards)}"

    def test_metric_card_token_types(self):
        """Must have a metric card for Token Types."""
        content = _read_template()
        assert "Token Types" in content, \
            "Glossary must have a 'Token Types' metric card"

    def test_metric_card_derived_metrics(self):
        """Must have a metric card for Derived Metrics."""
        content = _read_template()
        assert "Derived Metrics" in content, \
            "Glossary must have a 'Derived Metrics' metric card"

    def test_metric_card_provider_fields(self):
        """Must have a metric card for Provider Fields."""
        content = _read_template()
        assert "Provider Fields" in content, \
            "Glossary must have a 'Provider Fields' metric card"

    def test_metric_card_round_signals(self):
        """Must have a metric card for Round Signals."""
        content = _read_template()
        assert "Round Signals" in content, \
            "Glossary must have a 'Round Signals' metric card"

    def test_metric_icons_present(self):
        """Each metric card must have a metric-icon element."""
        content = _read_template()
        icons = re.findall(r'class="metric-icon', content)
        assert len(icons) == 4, \
            f"Glossary must have 4 metric-icon elements, found {len(icons)}"

    def test_metric_icons_have_emoji_aria_hidden(self):
        """Each metric-icon must contain a span with aria-hidden."""
        content = _read_template()
        # Metric icons use <span aria-hidden="true"> for emoji (no class="emoji")
        metric_icons = re.findall(r'class="metric-icon[^"]*"[^>]*>', content)
        aria_count = content.count('aria-hidden="true"')
        assert aria_count >= 4, \
            f"Glossary must have at least 4 aria-hidden spans in metric icons, found {aria_count}"

    def test_metric_labels_present(self):
        """Each metric card must have a metric-card__label element."""
        content = _read_template()
        labels = re.findall(r'class="metric-card__label"', content)
        assert len(labels) >= 4, \
            f"Glossary must have at least 4 metric-card__label elements, found {len(labels)}"

    def test_metric_values_present(self):
        """Each metric card must have a metric-card__value element."""
        content = _read_template()
        # Template uses class="metric-card__value mono" (with additional class)
        values = re.findall(r'class="metric-card__value', content)
        assert len(values) >= 4, \
            f"Glossary must have at least 4 metric-card__value elements, found {len(values)}"

    def test_metric_notes_present(self):
        """Each metric card must have a metric-card__sub element."""
        content = _read_template()
        notes = re.findall(r'class="metric-card__sub"', content)
        assert len(notes) >= 4, \
            f"Glossary must have at least 4 metric-card__sub elements, found {len(notes)}"


# -- TestGlossaryFilterCard -------------------------------------------------


class TestGlossaryFilterCard:
    """Verify filter/search card structure."""

    def test_filter_card_present(self):
        """Glossary must have a filter-card."""
        content = _read_template()
        assert 'class="card filter-card' in content, \
            "Glossary must have a filter-card"

    def test_search_input_present(self):
        """Filter card must have a search input."""
        content = _read_template()
        assert 'class="input search"' in content, \
            "Glossary must have a search input with class 'input search'"

    def test_search_input_id(self):
        """Search input must have id='glossary-search'."""
        content = _read_template()
        assert 'id="glossary-search"' in content, \
            "Glossary search input must have id='glossary-search'"

    def test_search_data_search_attribute(self):
        """Search input must have data-search attribute."""
        content = _read_template()
        assert 'data-search="glossary-term"' in content, \
            "Glossary search input must have data-search='glossary-term'"

    def test_search_aria_label(self):
        """Search input must have aria-label."""
        content = _read_template()
        assert 'aria-label="Search glossary terms"' in content, \
            "Glossary search input must have aria-label='Search glossary terms'"

    def test_search_autocomplete_off(self):
        """Search input must have autocomplete='off'."""
        content = _read_template()
        assert 'autocomplete="off"' in content, \
            "Glossary search input must have autocomplete='off'"

    def test_search_placeholder(self):
        """Search input must have a placeholder."""
        content = _read_template()
        assert "搜索术语" in content or "Search" in content, \
            "Glossary search input must have a placeholder"

    def test_match_count_element(self):
        """Glossary must have a match count span."""
        content = _read_template()
        assert 'id="glossary-match-count"' in content, \
            "Glossary must have glossary-match-count span"

    def test_filter_row_present(self):
        """Filter card must have a filter-row."""
        content = _read_template()
        assert 'class="filter-row"' in content, \
            "Glossary must have a filter-row"


# -- TestGlossaryEmptyState -------------------------------------------------


class TestGlossaryEmptyState:
    """Verify empty state rendering."""

    def test_empty_state_present(self):
        """Glossary must have a state-strip for empty state."""
        content = _read_template()
        assert 'class="state-strip' in content, \
            "Glossary must have a state-strip for empty state"

    def test_empty_state_id(self):
        """Empty state must have id='glossary-empty'."""
        content = _read_template()
        assert 'id="glossary-empty"' in content, \
            "Glossary empty state must have id='glossary-empty'"

    def test_empty_state_role_status(self):
        """Empty state must have role='status'."""
        content = _read_template()
        assert 'role="status"' in content, \
            "Glossary empty state must have role='status'"

    def test_empty_state_aria_live(self):
        """Empty state must have aria-live='polite'."""
        content = _read_template()
        assert 'aria-live="polite"' in content, \
            "Glossary empty state must have aria-live='polite'"

    def test_empty_state_is_hidden(self):
        """Empty state must start with is-hidden class."""
        content = _read_template()
        assert 'is-hidden' in content, \
            "Glossary empty state must have is-hidden class"

    def test_empty_state_icon_aria_hidden(self):
        """Empty state icon must have aria-hidden='true'."""
        content = _read_template()
        # The state icon uses class="state-icon" with aria-hidden
        assert 'class="state-icon"' in content, \
            "Glossary empty state must have state-icon"
        assert 'aria-hidden="true"' in content, \
            "Glossary empty state icon must have aria-hidden='true'"

    def test_empty_state_no_match_message(self):
        """Empty state must have a no-match message."""
        content = _read_template()
        assert "没有匹配的术语" in content, \
            "Glossary empty state must show no-match message"

    def test_empty_state_try_again_message(self):
        """Empty state must suggest trying again."""
        content = _read_template()
        assert "尝试更换关键词" in content or "清空搜索框" in content, \
            "Glossary empty state must suggest trying different keywords"


# -- TestGlossarySections ---------------------------------------------------


class TestGlossarySections:
    """Verify 8 card.section elements."""

    def test_card_section_class(self):
        """Glossary must use card.section.section-card.full-width class for sections."""
        content = _read_template()
        assert 'class="card section section-card full-width"' in content, \
            "Glossary must use card.section.section-card.full-width class"

    def test_eight_sections(self):
        """Glossary must have exactly 8 card.section elements."""
        content = _read_template()
        # Sections may have additional classes like glossary-table-section
        sections = re.findall(r'class="card section[^"]*"', content)
        assert len(sections) == 8, \
            f"Glossary must have exactly 8 card.section elements, found {len(sections)}"

    def test_badge_reference_section(self):
        """Must have a Badge Reference section."""
        content = _read_template()
        assert "Badge Reference" in content, \
            "Glossary must have a Badge Reference section"

    def test_token_overview_section(self):
        """Must have a Token 概览 (Token Overview) section."""
        content = _read_template()
        assert "Token 概览" in content, \
            "Glossary must have a Token Overview section"

    def test_token_composition_section(self):
        """Must have a Token 组成 (Token Composition) section."""
        content = _read_template()
        assert "Token 组成" in content, \
            "Glossary must have a Token Composition section"

    def test_derived_metrics_section(self):
        """Must have a 派生指标 (Derived Metrics) section."""
        content = _read_template()
        assert "派生指标" in content, \
            "Glossary must have a Derived Metrics section"

    def test_provider_mapping_section(self):
        """Must have a Provider 映射 (Provider Mapping) section."""
        content = _read_template()
        assert "Provider 映射" in content or "Provider Mapping" in content, \
            "Glossary must have a Provider Mapping section"

    def test_provider_mapping_anchor_id(self):
        """Provider mapping section must have anchor id='provider-mapping'."""
        content = _read_template()
        assert 'id="provider-mapping"' in content, \
            "Provider mapping section must have id='provider-mapping'"

    def test_limitations_section(self):
        """Must have a 已知限制 (Known Limitations) section."""
        content = _read_template()
        assert "已知限制" in content, \
            "Glossary must have a Known Limitations section"

    def test_session_anomalies_section(self):
        """Must have a Session Anomalies section."""
        content = _read_template()
        assert "Session Anomalies" in content, \
            "Glossary must have a Session Anomalies section"

    def test_round_signals_section(self):
        """Must have a Round Signals section."""
        content = _read_template()
        assert "Round Signals" in content, \
            "Glossary must have a Round Signals section"

    def test_section_head_elements(self):
        """Each section must have a section-head element."""
        content = _read_template()
        heads = re.findall(r'class="section-head"', content)
        assert len(heads) == 8, \
            f"Glossary must have 8 section-head elements, found {len(heads)}"

    def test_section_title_elements(self):
        """Each section must have a section-title element."""
        content = _read_template()
        titles = re.findall(r'class="section-title"', content)
        assert len(titles) == 8, \
            f"Glossary must have 8 section-title elements, found {len(titles)}"

    def test_section_sub_elements(self):
        """Sections must have section-desc descriptions (HIFI-aligned alias)."""
        content = _read_template()
        subs = re.findall(r'class="section-desc"', content)
        assert len(subs) == 5, \
            f"Glossary must have exactly 5 section-desc elements, found {len(subs)}"


# -- TestGlossaryTables -----------------------------------------------------


class TestGlossaryTables:
    """Verify 6 data-tables present."""

    _TABLE_SECTIONS = [
        ("Token 组成", "Token composition"),
        ("派生指标", "Derived metrics"),
        ("Provider 映射", "Provider mapping"),
        ("已知限制", "Known limitations"),
        ("Session Anomalies", "Anomalies"),
        ("Round Signals", "Signals"),
    ]

    def test_six_data_tables(self):
        """Glossary must have exactly 6 data-table elements (may have additional classes like glossary-table)."""
        content = _read_template()
        tables = re.findall(r'class="data-table[^"]*"', content)
        assert len(tables) == 6, \
            f"Glossary must have exactly 6 data-table elements, found {len(tables)}"

    def test_all_tables_enhanced(self):
        """All tables must have data-table-enhanced attribute."""
        content = _read_template()
        enhanced = re.findall(r'data-table-enhanced', content)
        assert len(enhanced) == 6, \
            f"Glossary must have 6 data-table-enhanced attributes, found {len(enhanced)}"

    def test_all_tables_in_wrap(self):
        """All tables must be inside a table-wrap."""
        content = _read_template()
        wraps = re.findall(r'class="table-wrap"', content)
        assert len(wraps) == 6, \
            f"Glossary must have 6 table-wrap elements, found {len(wraps)}"

    @pytest.mark.parametrize("section_name,_", _TABLE_SECTIONS)
    def test_table_section_exists(self, section_name, _):
        """Each expected table section must exist."""
        content = _read_template()
        assert section_name in content, \
            f"Glossary must have a '{section_name}' table section"

    def test_token_composition_table_has_thead(self):
        """Token composition table must have thead."""
        content = _read_template()
        assert '<thead>' in content, \
            "Token composition table must have thead"

    def test_token_composition_table_has_tbody(self):
        """Token composition table must have tbody."""
        content = _read_template()
        assert '<tbody>' in content, \
            "Token composition table must have tbody"

    def test_data_table_has_code_elements(self):
        """Data tables must have code elements for formulas/fields."""
        content = _read_template()
        assert '<code>' in content, \
            "Glossary tables must have code elements"

    def test_badge_elements_in_tables(self):
        """Tables must use badge elements."""
        content = _read_template()
        badges = re.findall(r'class="badge', content)
        assert len(badges) >= 4, \
            f"Glossary must have at least 4 badge elements, found {len(badges)}"


# -- TestGlossaryDataActions ------------------------------------------------


class TestGlossaryDataActions:
    """Verify all required data-action and data-search attributes."""

    def test_sort_action_on_headers(self):
        """Sortable headers must have data-action='sort'."""
        content = _read_template()
        sorts = re.findall(r'data-action="sort"', content)
        assert len(sorts) >= 6, \
            f"Glossary must have at least 6 sortable columns, found {len(sorts)}"

    def test_sort_keys_present(self):
        """Sortable columns must have data-sort-key attributes."""
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
                f"Glossary must have data-sort-key='{sort_key}'"

    def test_search_data_search(self):
        """Search input must have data-search attribute."""
        content = _read_template()
        assert 'data-search="glossary-term"' in content, \
            "Glossary search input must have data-search='glossary-term'"

    def test_sortable_th_elements(self):
        """Sortable columns must have sortable class on th."""
        content = _read_template()
        sortable_ths = re.findall(r'class="sortable"', content)
        assert len(sortable_ths) >= 6, \
            f"Glossary must have at least 6 sortable th elements, found {len(sortable_ths)}"


# -- TestGlossaryAccessibility ----------------------------------------------


class TestGlossaryAccessibility:
    """Verify accessibility attributes."""

    def test_metric_icon_emojis_aria_hidden(self):
        """Metric icon emojis must have aria-hidden='true'."""
        content = _read_template()
        # Metric icons use <span aria-hidden="true"> without class="emoji"
        aria_hidden = content.count('aria-hidden="true"')
        assert aria_hidden >= 4, \
            f"Glossary must have at least 4 aria-hidden spans, found {aria_hidden}"

    def test_empty_state_icon_aria_hidden(self):
        """Empty state icon must have aria-hidden='true'."""
        content = _read_template()
        # The state-strip icon uses aria-hidden on the state-icon div
        state_icon_section = content[content.find('class="state-strip'):]
        state_icon_section = state_icon_section[:state_icon_section.find('</div>') + 6]
        assert 'aria-hidden="true"' in state_icon_section, \
            "Empty state icon must have aria-hidden='true'"

    def test_search_input_aria_label(self):
        """Search input must have aria-label."""
        content = _read_template()
        assert 'aria-label="Search glossary terms"' in content, \
            "Glossary search input must have aria-label"

    def test_empty_state_aria_live(self):
        """Empty state must have aria-live='polite'."""
        content = _read_template()
        assert 'aria-live="polite"' in content, \
            "Glossary empty state must have aria-live='polite'"

    def test_empty_state_role_status(self):
        """Empty state must have role='status'."""
        content = _read_template()
        assert 'role="status"' in content, \
            "Glossary empty state must have role='status'"

    def test_metric_grid_aria_label(self):
        """Metric grid must have an aria-label."""
        content = _read_template()
        assert 'aria-label="术语页摘要指标"' in content, \
            "Glossary metric grid must have aria-label"


# -- TestGlossaryNoStalePatterns --------------------------------------------


class TestGlossaryNoStalePatterns:
    """Verify stale patterns are NOT present."""

    def test_no_inline_onclick(self):
        """Glossary must not have inline onclick."""
        content = _read_template()
        matches = re.findall(r'\bonclick\s*=', content, re.IGNORECASE)
        assert len(matches) == 0, \
            f"Glossary must not have inline onclick, found {len(matches)}"

    def test_no_inline_script(self):
        """Template must not have inline script blocks."""
        content = _read_template()
        script_tags = re.findall(r'<script(?! src)[^>]*>', content)
        assert len(script_tags) == 0, \
            f"Glossary must not have inline script tags, found {len(script_tags)}"

    def test_no_inline_style_blocks(self):
        """Template must not have inline style blocks."""
        content = _read_template()
        style_blocks = re.findall(r'<style[^>]*>', content)
        assert len(style_blocks) == 0, \
            f"Glossary must not have inline style blocks, found {len(style_blocks)}"

    def test_no_filter_bar_class(self):
        """Glossary must not use .filter-bar class (uses .filter-card)."""
        content = _read_template()
        assert 'class="filter-bar"' not in content, \
            "Glossary must not have filter-bar class"

    def test_no_table_scroll_class(self):
        """Glossary must not use .table-scroll class (uses .table-wrap)."""
        content = _read_template()
        assert 'class="table-scroll"' not in content, \
            "Glossary must not have table-scroll class"

    def test_no_select_elements(self):
        """No <select> elements."""
        content = _read_template()
        assert '<select' not in content, \
            "Glossary must not use select elements"

    def test_no_hero_section(self):
        """Glossary must not have hero section."""
        content = _read_template()
        assert 'class="hero"' not in content, \
            "Glossary must not have hero section"
