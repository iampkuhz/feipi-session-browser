"""Tests for Glossary page (glossary.html).

Page-level pytest for glossary.html covering template structure, header,
metric grid, filter card, empty state, sections, tables, data actions,
accessibility, and absence of stale patterns.

T164 -- Glossary: Add page-specific pytest.
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
    """Verify the glossary Jinja2 template renders structurally."""

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    @pytest.mark.contract_case("UI-GLOSSARY-002")
    def test_template_file_exists(self):
        """glossary.html must exist on disk."""
        assert os.path.isfile(_GLOSSARY_PATH), \
            f"{_GLOSSARY_PATH} must exist"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_extends_base(self):
        """Glossary must extend base.html."""
        content = _read_template()
        assert '{% extends "base.html" %}' in content, \
            "Glossary must extend base.html"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_active_page_set(self):
        """Glossary must set active_page = 'glossary'."""
        content = _read_template()
        assert "active_page = 'glossary'" in content, \
            "Glossary must set active_page = 'glossary'"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_ui_primitives_imported(self):
        """Glossary must import ui_primitives.html."""
        content = _read_template()
        assert 'components/ui_primitives.html' in content, \
            "Glossary must import ui_primitives.html"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_no_inline_onclick(self):
        """Glossary must not use inline onclick handlers."""
        content = _read_template()
        matches = re.findall(r'\bonclick\s*=', content, re.IGNORECASE)
        assert len(matches) == 0, \
            f"Glossary must not have inline onclick, found {len(matches)} occurrences"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_page_specific_css_import(self):
        """Glossary must import page-specific CSS for glossary styling."""
        content = _read_template()
        assert 'href="/static/css/glossary.css"' in content, \
            "Glossary must import glossary.css"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_page_specific_js_import(self):
        """Glossary must import page-specific JS for glossary functionality."""
        content = _read_template()
        assert 'src="/static/js/glossary.js"' in content, \
            "Glossary must import glossary.js"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_script_extra_block(self):
        """Glossary must use script_extra block for JS."""
        content = _read_template()
        assert '{% block script_extra %}' in content, \
            "Glossary must use script_extra block"


# -- TestGlossaryHeader -----------------------------------------------------


class TestGlossaryHeader:
    """Verify header structure."""

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_page_head_present(self):
        """Glossary must use ui.page_head() macro (T15)."""
        content = _read_template()
        assert 'ui.page_head(' in content, \
            "Glossary must use ui.page_head() macro"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_h1_title(self):
        """Page head must have 'Token Glossary' as title parameter."""
        content = _read_template()
        assert "'Token Glossary'" in content, \
            "Glossary page_head must have 'Token Glossary' as title"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_subtitle_present(self):
        """Page head must have a subtitle passed to macro."""
        content = _read_template()
        assert '必要术语说明' in content, \
            "Glossary page_head must have subtitle about essential terminology"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_subtitle_text(self):
        """Subtitle must describe the glossary purpose per HIFI."""
        content = _read_template()
        assert "必要术语说明" in content, \
            "Subtitle must describe glossary as essential terminology reference"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_breadcrumb(self):
        """Breadcrumb must link to dashboard."""
        content = _read_template()
        assert 'href="/dashboard"' in content, \
            "Breadcrumb must link to /dashboard"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_breadcrumb_current(self):
        """Breadcrumb must show glossary as current."""
        content = _read_template()
        assert "术语表" in content or "Glossary" in content, \
            "Breadcrumb must show glossary name"


# -- TestGlossaryMetricGrid -------------------------------------------------


class TestGlossaryMetricGrid:
    """Verify summary metric grid structure."""

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_metric_grid_present(self):
        """Glossary must have a metric-grid section."""
        content = _read_template()
        assert 'class="metric-grid"' in content, \
            "Glossary must have a metric-grid section"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_metric_grid_aria_label(self):
        """Metric grid must have an aria-label."""
        content = _read_template()
        assert 'aria-label="术语页摘要指标"' in content, \
            "Metric grid must have aria-label"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_four_metric_cards(self):
        """Glossary must have exactly 4 metric cards."""
        content = _read_template()
        cards = re.findall(r'class="metric-card"', content)
        assert len(cards) == 4, \
            f"Glossary must have exactly 4 metric cards, found {len(cards)}"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_metric_card_token_types(self):
        """Must have a metric card for Token Types."""
        content = _read_template()
        assert "Token Types" in content, \
            "Glossary must have a 'Token Types' metric card"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_metric_card_derived_metrics(self):
        """Must have a metric card for Derived Metrics."""
        content = _read_template()
        assert "Derived Metrics" in content, \
            "Glossary must have a 'Derived Metrics' metric card"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_metric_card_provider_fields(self):
        """Must have a metric card for Provider Fields."""
        content = _read_template()
        assert "Provider Fields" in content, \
            "Glossary must have a 'Provider Fields' metric card"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_metric_card_round_signals(self):
        """Must have a metric card for Round Signals."""
        content = _read_template()
        assert "Round Signals" in content, \
            "Glossary must have a 'Round Signals' metric card"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_metric_icons_present(self):
        """Each metric card must have a metric-icon element."""
        content = _read_template()
        icons = re.findall(r'class="metric-icon', content)
        assert len(icons) == 4, \
            f"Glossary must have 4 metric-icon elements, found {len(icons)}"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_metric_icons_have_emoji_aria_hidden(self):
        """Each metric-icon must contain a span with aria-hidden."""
        content = _read_template()
        # Metric icons use <span aria-hidden="true"> for emoji (no class="emoji")
        metric_icons = re.findall(r'class="metric-icon[^"]*"[^>]*>', content)
        aria_count = content.count('aria-hidden="true"')
        assert aria_count >= 4, \
            f"Glossary must have at least 4 aria-hidden spans in metric icons, found {aria_count}"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_metric_labels_present(self):
        """Each metric card must have a metric-card__label element."""
        content = _read_template()
        labels = re.findall(r'class="metric-card__label"', content)
        assert len(labels) >= 4, \
            f"Glossary must have at least 4 metric-card__label elements, found {len(labels)}"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_metric_values_present(self):
        """Each metric card must have a metric-card__value element."""
        content = _read_template()
        # Template uses class="metric-card__value mono" (with additional class)
        values = re.findall(r'class="metric-card__value', content)
        assert len(values) >= 4, \
            f"Glossary must have at least 4 metric-card__value elements, found {len(values)}"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_metric_notes_present(self):
        """Each metric card must have a metric-card__sub element."""
        content = _read_template()
        notes = re.findall(r'class="metric-card__sub"', content)
        assert len(notes) >= 4, \
            f"Glossary must have at least 4 metric-card__sub elements, found {len(notes)}"


# -- TestGlossaryFilterCard -------------------------------------------------


class TestGlossaryFilterCard:
    """Verify filter/search card structure."""

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_filter_card_present(self):
        """Glossary must have a filter-card."""
        content = _read_template()
        assert 'class="card filter-card' in content or 'ui.filter_card()' in content, \
            "Glossary must have a filter-card (literal or macro)"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_search_input_present(self):
        """Filter card must have a search input."""
        content = _read_template()
        assert 'class="input search"' in content, \
            "Glossary must have a search input with class 'input search'"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_search_input_id(self):
        """Search input must have id='glossary-search'."""
        content = _read_template()
        assert 'id="glossary-search"' in content, \
            "Glossary search input must have id='glossary-search'"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_search_data_search_attribute(self):
        """Search input must have data-search attribute."""
        content = _read_template()
        assert 'data-search="glossary-term"' in content, \
            "Glossary search input must have data-search='glossary-term'"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_search_aria_label(self):
        """Search input must have aria-label."""
        content = _read_template()
        assert 'aria-label="Search glossary terms"' in content, \
            "Glossary search input must have aria-label='Search glossary terms'"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_search_autocomplete_off(self):
        """Search input must have autocomplete='off'."""
        content = _read_template()
        assert 'autocomplete="off"' in content, \
            "Glossary search input must have autocomplete='off'"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_search_placeholder(self):
        """Search input must have a placeholder."""
        content = _read_template()
        assert "搜索术语" in content or "Search" in content, \
            "Glossary search input must have a placeholder"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_match_count_element(self):
        """Glossary must have a match count span."""
        content = _read_template()
        assert 'id="glossary-match-count"' in content, \
            "Glossary must have glossary-match-count span"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_filter_row_present(self):
        """Filter card must have a filter-row."""
        content = _read_template()
        assert 'class="filter-row"' in content, \
            "Glossary must have a filter-row"


# -- TestGlossaryEmptyState -------------------------------------------------


class TestGlossaryEmptyState:
    """Verify empty state rendering."""

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_empty_state_present(self):
        """Glossary must have a state-strip for empty state."""
        content = _read_template()
        assert 'class="state-strip' in content, \
            "Glossary must have a state-strip for empty state"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_empty_state_id(self):
        """Empty state must have id='glossary-empty'."""
        content = _read_template()
        assert 'id="glossary-empty"' in content, \
            "Glossary empty state must have id='glossary-empty'"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_empty_state_role_status(self):
        """Empty state must have role='status'."""
        content = _read_template()
        assert 'role="status"' in content, \
            "Glossary empty state must have role='status'"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_empty_state_aria_live(self):
        """Empty state must have aria-live='polite'."""
        content = _read_template()
        assert 'aria-live="polite"' in content, \
            "Glossary empty state must have aria-live='polite'"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_empty_state_is_hidden(self):
        """Empty state must start with is-hidden class."""
        content = _read_template()
        assert 'is-hidden' in content, \
            "Glossary empty state must have is-hidden class"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_empty_state_icon_aria_hidden(self):
        """Empty state icon must have aria-hidden='true'."""
        content = _read_template()
        # The state icon uses class="state-icon" with aria-hidden
        assert 'class="state-icon"' in content, \
            "Glossary empty state must have state-icon"
        assert 'aria-hidden="true"' in content, \
            "Glossary empty state icon must have aria-hidden='true'"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_empty_state_no_match_message(self):
        """Empty state must have a no-match message."""
        content = _read_template()
        assert "没有匹配的术语" in content, \
            "Glossary empty state must show no-match message"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_empty_state_try_again_message(self):
        """Empty state must suggest trying again."""
        content = _read_template()
        assert "尝试更换关键词" in content or "清空搜索框" in content, \
            "Glossary empty state must suggest trying different keywords"


# -- TestGlossarySections ---------------------------------------------------


class TestGlossarySections:
    """Verify 8 card.section elements."""

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_card_section_class(self):
        """Glossary must use card.section.section-card.full-width class for sections."""
        content = _read_template()
        assert 'class="card section section-card full-width"' in content, \
            "Glossary must use card.section.section-card.full-width class"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_eight_sections(self):
        """Glossary must have exactly 8 card.section elements."""
        content = _read_template()
        # Sections may have additional classes like glossary-table-section
        sections = re.findall(r'class="card section[^"]*"', content)
        assert len(sections) == 8, \
            f"Glossary must have exactly 8 card.section elements, found {len(sections)}"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_badge_reference_section(self):
        """Must have a Badge Reference section."""
        content = _read_template()
        assert "Badge Reference" in content, \
            "Glossary must have a Badge Reference section"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_token_overview_section(self):
        """Must have a Token 概览 (Token Overview) section."""
        content = _read_template()
        assert "Token 概览" in content, \
            "Glossary must have a Token Overview section"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_token_composition_section(self):
        """Must have a Token 组成 (Token Composition) section."""
        content = _read_template()
        assert "Token 组成" in content, \
            "Glossary must have a Token Composition section"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_derived_metrics_section(self):
        """Must have a 派生指标 (Derived Metrics) section."""
        content = _read_template()
        assert "派生指标" in content, \
            "Glossary must have a Derived Metrics section"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_provider_mapping_section(self):
        """Must have a Provider 映射 (Provider Mapping) section."""
        content = _read_template()
        assert "Provider 映射" in content or "Provider Mapping" in content, \
            "Glossary must have a Provider Mapping section"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_provider_mapping_anchor_id(self):
        """Provider mapping section must have anchor id='provider-mapping'."""
        content = _read_template()
        assert 'id="provider-mapping"' in content, \
            "Provider mapping section must have id='provider-mapping'"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_limitations_section(self):
        """Must have a 已知限制 (Known Limitations) section."""
        content = _read_template()
        assert "已知限制" in content, \
            "Glossary must have a Known Limitations section"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_session_anomalies_section(self):
        """Must have a Session Anomalies section."""
        content = _read_template()
        assert "Session Anomalies" in content, \
            "Glossary must have a Session Anomalies section"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_round_signals_section(self):
        """Must have a Round Signals section."""
        content = _read_template()
        assert "Round Signals" in content, \
            "Glossary must have a Round Signals section"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_section_head_elements(self):
        """Each section must have a section-head element."""
        content = _read_template()
        heads = re.findall(r'class="section-head"', content)
        assert len(heads) == 8, \
            f"Glossary must have 8 section-head elements, found {len(heads)}"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_section_title_elements(self):
        """Each section must have a section-title element."""
        content = _read_template()
        titles = re.findall(r'class="section-title"', content)
        assert len(titles) == 8, \
            f"Glossary must have 8 section-title elements, found {len(titles)}"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
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

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_six_data_tables(self):
        """Glossary must have exactly 6 data-table elements (may have additional classes like glossary-table)."""
        content = _read_template()
        tables = re.findall(r'class="data-table[^"]*"', content)
        assert len(tables) == 6, \
            f"Glossary must have exactly 6 data-table elements, found {len(tables)}"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_all_tables_enhanced(self):
        """All tables must have data-table-enhanced attribute."""
        content = _read_template()
        enhanced = re.findall(r'data-table-enhanced', content)
        assert len(enhanced) == 6, \
            f"Glossary must have 6 data-table-enhanced attributes, found {len(enhanced)}"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_all_tables_in_wrap(self):
        """All tables must be inside a table-wrap."""
        content = _read_template()
        wraps = re.findall(r'class="table-wrap"', content)
        assert len(wraps) == 6, \
            f"Glossary must have 6 table-wrap elements, found {len(wraps)}"

    @pytest.mark.parametrize("section_name,_", _TABLE_SECTIONS)
    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_table_section_exists(self, section_name, _):
        """Each expected table section must exist."""
        content = _read_template()
        assert section_name in content, \
            f"Glossary must have a '{section_name}' table section"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_token_composition_table_has_thead(self):
        """Token composition table must have thead."""
        content = _read_template()
        assert '<thead>' in content, \
            "Token composition table must have thead"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_token_composition_table_has_tbody(self):
        """Token composition table must have tbody."""
        content = _read_template()
        assert '<tbody>' in content, \
            "Token composition table must have tbody"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_data_table_has_code_elements(self):
        """Data tables must have code elements for formulas/fields."""
        content = _read_template()
        assert '<code>' in content, \
            "Glossary tables must have code elements"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_badge_elements_in_tables(self):
        """Tables must use badge elements."""
        content = _read_template()
        badges = re.findall(r'class="badge', content)
        assert len(badges) >= 4, \
            f"Glossary must have at least 4 badge elements, found {len(badges)}"


# -- TestGlossaryDataActions ------------------------------------------------


class TestGlossaryDataActions:
    """Verify all required data-action and data-search attributes."""

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_sort_action_on_headers(self):
        """Sortable headers must have data-action='sort'."""
        content = _read_template()
        sorts = re.findall(r'data-action="sort"', content)
        assert len(sorts) >= 6, \
            f"Glossary must have at least 6 sortable columns, found {len(sorts)}"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
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

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_search_data_search(self):
        """Search input must have data-search attribute."""
        content = _read_template()
        assert 'data-search="glossary-term"' in content, \
            "Glossary search input must have data-search='glossary-term'"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_sortable_th_elements(self):
        """Sortable columns must have sortable class on th."""
        content = _read_template()
        sortable_ths = re.findall(r'class="sortable"', content)
        assert len(sortable_ths) >= 6, \
            f"Glossary must have at least 6 sortable th elements, found {len(sortable_ths)}"


# -- TestGlossaryAccessibility ----------------------------------------------


class TestGlossaryAccessibility:
    """Verify accessibility attributes."""

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_metric_icon_emojis_aria_hidden(self):
        """Metric icon emojis must have aria-hidden='true'."""
        content = _read_template()
        # Metric icons use <span aria-hidden="true"> without class="emoji"
        aria_hidden = content.count('aria-hidden="true"')
        assert aria_hidden >= 4, \
            f"Glossary must have at least 4 aria-hidden spans, found {aria_hidden}"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_empty_state_icon_aria_hidden(self):
        """Empty state icon must have aria-hidden='true'."""
        content = _read_template()
        # The state-strip icon uses aria-hidden on the state-icon div
        state_icon_section = content[content.find('class="state-strip'):]
        state_icon_section = state_icon_section[:state_icon_section.find('</div>') + 6]
        assert 'aria-hidden="true"' in state_icon_section, \
            "Empty state icon must have aria-hidden='true'"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_search_input_aria_label(self):
        """Search input must have aria-label."""
        content = _read_template()
        assert 'aria-label="Search glossary terms"' in content, \
            "Glossary search input must have aria-label"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_empty_state_aria_live(self):
        """Empty state must have aria-live='polite'."""
        content = _read_template()
        assert 'aria-live="polite"' in content, \
            "Glossary empty state must have aria-live='polite'"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_empty_state_role_status(self):
        """Empty state must have role='status'."""
        content = _read_template()
        assert 'role="status"' in content, \
            "Glossary empty state must have role='status'"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_metric_grid_aria_label(self):
        """Metric grid must have an aria-label."""
        content = _read_template()
        assert 'aria-label="术语页摘要指标"' in content, \
            "Glossary metric grid must have aria-label"


# -- TestGlossaryNoStalePatterns --------------------------------------------


class TestGlossaryNoStalePatterns:
    """Verify stale patterns are NOT present."""

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_no_inline_onclick(self):
        """Glossary must not have inline onclick."""
        content = _read_template()
        matches = re.findall(r'\bonclick\s*=', content, re.IGNORECASE)
        assert len(matches) == 0, \
            f"Glossary must not have inline onclick, found {len(matches)}"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_no_inline_script(self):
        """Template must not have inline script blocks."""
        content = _read_template()
        script_tags = re.findall(r'<script(?! src)[^>]*>', content)
        assert len(script_tags) == 0, \
            f"Glossary must not have inline script tags, found {len(script_tags)}"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_no_inline_style_blocks(self):
        """Template must not have inline style blocks."""
        content = _read_template()
        style_blocks = re.findall(r'<style[^>]*>', content)
        assert len(style_blocks) == 0, \
            f"Glossary must not have inline style blocks, found {len(style_blocks)}"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_no_filter_bar_class(self):
        """Glossary must not use .filter-bar class (uses .filter-card)."""
        content = _read_template()
        assert 'class="filter-bar"' not in content, \
            "Glossary must not have filter-bar class"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_no_table_scroll_class(self):
        """Glossary must not use .table-scroll class (uses .table-wrap)."""
        content = _read_template()
        assert 'class="table-scroll"' not in content, \
            "Glossary must not have table-scroll class"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_no_select_elements(self):
        """No <select> elements."""
        content = _read_template()
        assert '<select' not in content, \
            "Glossary must not use select elements"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_no_hero_section(self):
        """Glossary must not have hero section."""
        content = _read_template()
        assert 'class="hero"' not in content, \
            "Glossary must not have hero section"


# ── Glossary fixed fixture tests (T097) ─────────────────────────────
# Uses the hifi_fixture_session fixture to spin up a live server with
# deterministic fixture data, then verifies the *rendered* Glossary HTML.
# Covers: page renders, terms list, key data display.


@pytest.fixture(scope="module")
def glossary_html(hifi_fixture_session):
    """Fetch rendered Glossary HTML from the live fixture server."""
    base_url, agent, session_id = hifi_fixture_session
    import urllib.request

    resp = urllib.request.urlopen(f"{base_url}/glossary", timeout=10)
    assert resp.status == 200, "Glossary must return HTTP 200"
    return resp.read().decode("utf-8")


# -- TestGlossaryPageRender -----------------------------------------------


class TestGlossaryPageRender:
    """Verify the rendered Glossary page structure."""

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_page_returns_200(self, glossary_html):
        """Glossary must render successfully."""
        assert len(glossary_html) > 500, \
            "Glossary HTML must be substantial"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_has_doctype_and_html(self, glossary_html):
        """Page must have proper HTML structure."""
        lower = glossary_html.lower()
        assert "<!doctype html" in lower or "<!DOCTYPE html" in glossary_html, \
            "Glossary must have DOCTYPE declaration"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_title_contains_glossary(self, glossary_html):
        """Page title must contain '术语表' or 'Glossary'."""
        assert "<title>" in glossary_html, \
            "Glossary must have a title tag"
        assert "术语表" in glossary_html or "Glossary" in glossary_html or "Token Glossary" in glossary_html, \
            "Page title must reference Glossary"


# -- TestGlossaryPageDisplay ----------------------------------------------


class TestGlossaryPageDisplay:
    """Verify Glossary page displays terms and key data from rendered HTML."""

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_has_page_head(self, glossary_html):
        """Page must show the 'Token Glossary' heading."""
        assert "Token Glossary" in glossary_html, \
            "'Token Glossary' heading must be visible"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_has_subtitle(self, glossary_html):
        """Page must show the subtitle about terminology."""
        assert "必要术语说明" in glossary_html or "术语说明" in glossary_html or "术语" in glossary_html, \
            "Subtitle about terminology must appear"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_has_metric_grid(self, glossary_html):
        """Glossary must render the summary metric grid."""
        assert 'class="metric-grid"' in glossary_html, \
            "Metric grid must be rendered"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_four_metric_cards_rendered(self, glossary_html):
        """Glossary must have exactly 4 metric cards in rendered output."""
        cards = re.findall(r'class="metric-card"', glossary_html)
        assert len(cards) == 4, \
            f"Glossary must have 4 metric cards, found {len(cards)}"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_token_types_card(self, glossary_html):
        """Must display Token Types metric card."""
        assert "Token Types" in glossary_html, \
            "Token Types metric card must be visible"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_derived_metrics_card(self, glossary_html):
        """Must display Derived Metrics metric card."""
        assert "Derived Metrics" in glossary_html, \
            "Derived Metrics metric card must be visible"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_provider_fields_card(self, glossary_html):
        """Must display Provider Fields metric card."""
        assert "Provider Fields" in glossary_html, \
            "Provider Fields metric card must be visible"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_round_signals_card(self, glossary_html):
        """Must display Round Signals metric card."""
        assert "Round Signals" in glossary_html, \
            "Round Signals metric card must be visible"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_search_input_rendered(self, glossary_html):
        """Glossary must render the search/filter input."""
        assert 'id="glossary-search"' in glossary_html, \
            "Search input must be rendered"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_filter_card_rendered(self, glossary_html):
        """Glossary must render the filter card."""
        assert "filter-card" in glossary_html or "filter" in glossary_html, \
            "Filter card must be rendered"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_sections_rendered(self, glossary_html):
        """Glossary must render section cards."""
        sections = re.findall(r'class="card section', glossary_html)
        assert len(sections) >= 6, \
            f"Glossary must have at least 6 section cards, found {len(sections)}"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_data_tables_rendered(self, glossary_html):
        """Glossary must render data tables."""
        tables = re.findall(r'class="data-table', glossary_html)
        assert len(tables) >= 4, \
            f"Glossary must have at least 4 data tables, found {len(tables)}"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_token_overview_section(self, glossary_html):
        """Must render Token 概览 section."""
        assert "Token 概览" in glossary_html, \
            "Token Overview section must be visible"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_token_composition_section(self, glossary_html):
        """Must render Token 组成 section."""
        assert "Token 组成" in glossary_html, \
            "Token Composition section must be visible"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_derived_metrics_section(self, glossary_html):
        """Must render 派生指标 section."""
        assert "派生指标" in glossary_html, \
            "Derived Metrics section must be visible"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_provider_mapping_section(self, glossary_html):
        """Must render Provider 映射 section."""
        assert "Provider 映射" in glossary_html, \
            "Provider Mapping section must be visible"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_badge_reference_section(self, glossary_html):
        """Must render Badge Reference section."""
        assert "Badge Reference" in glossary_html, \
            "Badge Reference section must be visible"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_known_terms_present(self, glossary_html):
        """Glossary must display key terms like 'cache read'."""
        assert "cache" in glossary_html.lower() or "Cache" in glossary_html, \
            "Key terms like 'cache' must appear in glossary"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_no_inline_onclick(self, glossary_html):
        """Rendered Glossary must not have inline onclick handlers."""
        matches = re.findall(r'\bonclick\s*=', glossary_html, re.IGNORECASE)
        assert len(matches) == 0, \
            f"Glossary must not have inline onclick, found {len(matches)}"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_empty_state_rendered(self, glossary_html):
        """Glossary must render the empty state element."""
        assert "state-strip" in glossary_html or "glossary-empty" in glossary_html, \
            "Empty state element must be rendered"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_breadcrumb_rendered(self, glossary_html):
        """Glossary must show the breadcrumb."""
        assert 'href="/dashboard"' in glossary_html, \
            "Breadcrumb must link to dashboard"


# -- TestGlossaryNoStalePatterns ------------------------------------------


class TestGlossaryNoStalePatternsFixture:
    """Verify stale patterns are NOT present in rendered HTML."""

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_no_filter_bar_class(self, glossary_html):
        """Glossary must not use .filter-bar class."""
        assert 'class="filter-bar"' not in glossary_html, \
            "Glossary must not have filter-bar class"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_no_hero_section(self, glossary_html):
        """Glossary must not have hero section."""
        assert 'class="hero"' not in glossary_html, \
            "Glossary must not have hero section"

    @pytest.mark.contract_case("UI-GLOSSARY-001")
    def test_no_inline_script(self, glossary_html):
        """Rendered HTML must not have inline script blocks."""
        script_tags = re.findall(r'<script(?! src)[^>]*>', glossary_html)
        assert len(script_tags) == 0, \
            f"Glossary must not have inline script tags, found {len(script_tags)}"
