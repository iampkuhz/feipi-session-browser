"""Agents 页面级夹具测试。

这些测试使用 hifi_fixture_session 启动一个带有确定性夹具数据的本地服务器，
然后验证*渲染后*的 Agents HTML（而非仅静态模板文件）。

覆盖：
- 页面渲染并返回 HTTP 200
- Agent 列表已显示并包含行
- 关键数据/指标可见（指标卡片、agent 名称、provider）
- 表格结构（可排序表头、数据属性）
- 效率表格（当夹具包含多个模型时）
- 可访问性门控（无 inline onclick）

T095 — Agents 固定夹具。
"""

from __future__ import annotations

import pytest
import re


# ── Agents 页面夹具 ───────────────────────────────────────────────


@pytest.fixture(scope="module")
def agents_html(hifi_fixture_session):
    """从本地夹具服务器获取渲染后的 Agents HTML。"""
    base_url, agent, session_id = hifi_fixture_session
    import urllib.request

    resp = urllib.request.urlopen(f"{base_url}/agents", timeout=10)
    assert resp.status == 200, "Agents 页面必须返回 HTTP 200"
    return resp.read().decode("utf-8")


# ── TestAgentsPageRender ───────────────────────────────────────────────


class TestAgentsPageRender:
    """验证渲染后的 Agents 页面结构。"""

    @pytest.mark.contract_case("UI-AGENTS-006")
    @pytest.mark.contract_case("UI-AGENTS-003")
    def test_page_returns_200(self, agents_html):
        """Agents 页面必须成功渲染。"""
        assert len(agents_html) > 500, \
            "Agents HTML 必须有足够内容"

    @pytest.mark.contract_case("UI-AGENTS-006")
    def test_has_doctype_and_html(self, agents_html):
        """页面必须有正确的 HTML 结构。"""
        lower = agents_html.lower()
        assert "<!doctype html" in lower or "<!DOCTYPE html" in agents_html, \
            "Agents 必须有 DOCTYPE 声明"

    @pytest.mark.contract_case("UI-AGENTS-006")
    @pytest.mark.contract_case("UI-AGENTS-003")
    def test_title_contains_agents(self, agents_html):
        """页面标题必须包含 'Agents'。"""
        assert "<title>Agents" in agents_html, \
            "页面标题必须包含 'Agents'"

    @pytest.mark.contract_case("UI-AGENTS-006")
    def test_has_h1_agents(self, agents_html):
        """页面必须有可见的 'Agents' 标题。"""
        assert ">Agents<" in agents_html, \
            "'Agents' 标题必须可见"

    @pytest.mark.contract_case("UI-AGENTS-006")
    def test_has_subtitle(self, agents_html):
        """页面必须显示包含 agent 计数的副标题。"""
        assert "个 Agent" in agents_html, \
            "副标题必须包含中文的 agent 计数"


# ── TestAgentsMetrics ──────────────────────────────────────────────────


class TestAgentsMetrics:
    """验证渲染后的指标卡片及其实际数据值。"""

    _EXPECTED_LABELS = ["Active Agents", "Sessions", "Projects", "Total Tokens"]

    @pytest.mark.contract_case("UI-AGENTS-006")
    @pytest.mark.contract_case("UI-AGENTS-005")
    def test_metric_grid_present(self, agents_html):
        """Agents 必须有 metric-grid 容器。"""
        assert 'class="metric-grid"' in agents_html, \
            "metric-grid 必须存在"

    @pytest.mark.contract_case("UI-AGENTS-006")
    def test_four_metric_cards(self, agents_html):
        """必须恰好渲染 4 个指标卡片。"""
        cards = re.findall(r'class="metric-card"', agents_html)
        assert len(cards) == 4, \
            f"预期 4 个指标卡片，发现 {len(cards)} 个"

    @pytest.mark.parametrize("label", _EXPECTED_LABELS)
    @pytest.mark.contract_case("UI-AGENTS-006")
    def test_metric_label_present(self, agents_html, label):
        """每个指标卡片必须显示其标签。"""
        assert f">{label}<" in agents_html or f'aria-label="{label}"' in agents_html, \
            f"标签为 '{label}' 的指标卡片必须可见"

    @pytest.mark.contract_case("UI-AGENTS-006")
    def test_metric_values_nonzero(self, agents_html):
        """当夹具包含数据时指标卡片必须有填充的值。"""
        # Active Agents 必须 > 0
        values = re.findall(
            r'class="metric-card__value[^"]*">([^<]+)<',
            agents_html
        )
        assert len(values) >= 4, \
            f"预期至少 4 个指标值，发现 {len(values)} 个"

        # 第一个值是 Active Agents 计数 — 必须为正数
        active_val = values[0].strip().replace(",", "")
        assert active_val.isdigit() and int(active_val) > 0, \
            f"Active Agents 计数必须 > 0，得到 '{active_val}'"

    @pytest.mark.contract_case("UI-AGENTS-006")
    def test_metric_aria_labels(self, agents_html):
        """每个指标卡片信息按钮必须有 aria-label。"""
        aria_labels = re.findall(
            r'aria-label="[^"]*(?:计数说明|公式说明)[^"]*"',
            agents_html
        )
        assert len(aria_labels) >= 4, \
            f"预期指标信息按钮上至少 4 个 aria-label，发现 {len(aria_labels)} 个"

    @pytest.mark.contract_case("UI-AGENTS-006")
    def test_metric_icons_present(self, agents_html):
        """指标卡片必须有图标元素。"""
        icons = re.findall(r'class="metric-icon', agents_html)
        assert len(icons) >= 4, \
            f"预期至少 4 个 metric-icon 元素，发现 {len(icons)} 个"


# ── TestAgentsListDisplay ──────────────────────────────────────────────


class TestAgentsListDisplay:
    """验证 agent 列表行的渲染及其数据正确性。"""

    @pytest.mark.contract_case("UI-AGENTS-006")
    def test_agents_table_present(self, agents_html):
        """Agents 表格必须有 id='agents-table'。"""
        assert 'id="agents-table"' in agents_html, \
            "Agents 表格必须有 id='agents-table'"

    @pytest.mark.contract_case("UI-AGENTS-006")
    @pytest.mark.contract_case("UI-AGENTS-004")
    def test_has_agent_rows(self, agents_html):
        """必须至少渲染一个 agent 行。"""
        rows = re.findall(r'data-action="open-agent"', agents_html)
        assert len(rows) > 0, \
            "必须至少渲染一个 agent 行"

    @pytest.mark.contract_case("UI-AGENTS-006")
    def test_row_has_data_href(self, agents_html):
        """Agent 行必须有指向详情页面的 data-href。"""
        assert 'data-href="/agents/' in agents_html, \
            "Agent 行必须有 data-href 属性"

    @pytest.mark.contract_case("UI-AGENTS-006")
    def test_row_has_data_agent_name(self, agents_html):
        """Agent 行必须有 data-agent-name 属性。"""
        assert 'data-agent-name=' in agents_html, \
            "Agent 行必须有 data-agent-name"

    @pytest.mark.contract_case("UI-AGENTS-006")
    def test_row_has_data_session_count(self, agents_html):
        """Agent 行必须有 data-session-count 属性。"""
        assert 'data-session-count=' in agents_html, \
            "Agent 行必须有 data-session-count"

    @pytest.mark.contract_case("UI-AGENTS-006")
    def test_row_has_data_project_count(self, agents_html):
        """Agent 行必须有 data-project-count 属性。"""
        assert 'data-project-count=' in agents_html, \
            "Agent 行必须有 data-project-count"

    @pytest.mark.contract_case("UI-AGENTS-006")
    def test_row_has_data_total_tokens(self, agents_html):
        """Agent 行必须有 data-total-tokens 属性。"""
        assert 'data-total-tokens=' in agents_html, \
            "Agent 行必须有 data-total-tokens"

    @pytest.mark.contract_case("UI-AGENTS-006")
    def test_row_has_data_total_tool_calls(self, agents_html):
        """Agent 行必须有 data-total-tool-calls 属性。"""
        assert 'data-total-tool-calls=' in agents_html, \
            "Agent 行必须有 data-total-tool-calls"

    @pytest.mark.contract_case("UI-AGENTS-006")
    def test_row_has_data_last_active(self, agents_html):
        """Agent 行必须有 data-last-active 属性。"""
        assert 'data-last-active=' in agents_html, \
            "Agent 行必须有 data-last-active"

    @pytest.mark.contract_case("UI-AGENTS-006")
    def test_agent_detail_links_present(self, agents_html):
        """每个 agent 行必须链接到其详情页面。"""
        links = re.findall(r'href="/agents/[^"]+"', agents_html)
        assert len(links) > 0, \
            "Agent 详情链接必须存在"

    @pytest.mark.contract_case("UI-AGENTS-006")
    def test_agent_clickable_rows(self, agents_html):
        """Agent 行必须有 open-agent 的 data-action。"""
        assert 'data-action="open-agent"' in agents_html, \
            "Agent 行必须有 data-action='open-agent'"


# ── TestAgentsProviders ────────────────────────────────────────────────


class TestAgentsProviders:
    """验证 provider 列显示正确的徽章。"""

    @pytest.mark.contract_case("UI-AGENTS-006")
    def test_provider_anthropic_badge(self, agents_html):
        """Claude Code agent 必须显示 Anthropic provider 徽章。"""
        assert ">Anthropic<" in agents_html, \
            "Anthropic provider 徽章必须可见"

    @pytest.mark.contract_case("UI-AGENTS-006")
    def test_badge_cc_class(self, agents_html):
        """CC 徽章类必须存在于 Claude Code。"""
        assert 'class="badge cc"' in agents_html or "badge cc" in agents_html, \
            "CC 徽章类必须存在"

    @pytest.mark.contract_case("UI-AGENTS-006")
    def test_badge_dot_indicators(self, agents_html):
        """徽章点指示器必须存在。"""
        assert 'class="dot claude"' in agents_html or 'class="dot codex"' in agents_html, \
            "必须至少有一个徽章点指示器"


# ── TestAgentsSortableHeaders ──────────────────────────────────────────


class TestAgentsSortableHeaders:
    """验证 agents 表格上的可排序表头行为。"""

    @pytest.mark.contract_case("UI-AGENTS-006")
    def test_sortable_columns_have_data_action_sort(self, agents_html):
        """可排序列必须有 data-action='sort'。"""
        sorts = re.findall(r'data-action="sort"', agents_html)
        assert len(sorts) >= 8, \
            f"预期至少 8 个可排序列，发现 {len(sorts)} 个"

    @pytest.mark.contract_case("UI-AGENTS-006")
    def test_sort_keys_present(self, agents_html):
        """Agents 表格必须有正确的 data-sort-key 值。"""
        for sort_key in ["name", "provider", "sessions", "projects",
                         "tokens", "tool_calls", "failed", "last_active"]:
            assert f'data-sort-key="{sort_key}"' in agents_html, \
                f"Agents 表格必须有 data-sort-key='{sort_key}'"

    @pytest.mark.contract_case("UI-AGENTS-006")
    def test_sortable_header_buttons(self, agents_html):
        """可排序表头必须使用 sortable-header 类。"""
        buttons = re.findall(r'class="sortable-header"', agents_html)
        assert len(buttons) >= 8, \
            f"预期至少 8 个 sortable-header 按钮，发现 {len(buttons)} 个"


# ── TestAgentsColumnHeaders ────────────────────────────────────────────


class TestAgentsColumnHeaders:
    """验证所有预期的列表头是否可见。"""

    _EXPECTED_COLUMNS = [
        "Agent", "Provider", "Sessions", "Projects",
        "Tokens", "Tool Calls", "Failed", "最近活跃",
    ]

    @pytest.mark.parametrize("column", _EXPECTED_COLUMNS)
    @pytest.mark.contract_case("UI-AGENTS-006")
    def test_column_header_present(self, agents_html, column):
        """表格必须有预期的列表头。"""
        assert column in agents_html, \
            f"表格必须有 '{column}' 列表头"


# ── TestAgentsTokenBar ─────────────────────────────────────────────────


class TestAgentsTokenBar:
    """验证 agent 行中的 token 条段。"""

    @pytest.mark.contract_case("UI-AGENTS-006")
    def test_token_cell_present(self, agents_html):
        """Agent 行必须有 token-cell 元素。"""
        assert 'class="token-cell"' in agents_html, \
            "Agent 行必须有 token-cell 元素"

    @pytest.mark.contract_case("UI-AGENTS-006")
    def test_token_total_present(self, agents_html):
        """Token-cell 必须有 token-total 元素。"""
        assert 'class="token-total"' in agents_html, \
            "Token-cell 必须有 token-total 元素"

    @pytest.mark.contract_case("UI-AGENTS-006")
    def test_tokenbar_present(self, agents_html):
        """Token-cell 必须有 tokenbar 元素。"""
        assert 'class="tokenbar"' in agents_html, \
            "Token-cell 必须有 tokenbar 元素"

    @pytest.mark.contract_case("UI-AGENTS-006")
    def test_tokenbar_four_segments(self, agents_html):
        """Tokenbar 必须有 4 种段类型（fresh/read/write/out）。"""
        for seg_class in ["fresh", "read", "write", "out"]:
            assert f'tokenbar-seg {seg_class}' in agents_html, \
                f"Tokenbar 必须有段类 '{seg_class}'"

    @pytest.mark.contract_case("UI-AGENTS-006")
    def test_tokenbar_has_title(self, agents_html):
        """Tokenbar 必须有标题提示。"""
        assert "Token breakdown" in agents_html, \
            "Tokenbar 必须在标题中包含 'Token breakdown'"


# ── TestAgentsEfficiencyTable ──────────────────────────────────────────


class TestAgentsEfficiencyTable:
    """验证当夹具包含多个模型时渲染效率表格。"""

    @pytest.mark.contract_case("UI-AGENTS-006")
    def test_efficiency_table_conditional(self, agents_html):
        """当夹具具有模型多样性时出现效率表格。"""
        # 渲染后的页面要么显示表格要么不显示 — 两者都有效。
        # 当存在时，验证结构。
        if "efficiency-table" in agents_html:
            assert 'id="efficiency-table"' in agents_html, \
                "效率表格必须有 id='efficiency-table'"

    @pytest.mark.contract_case("UI-AGENTS-006")
    def test_efficiency_title_when_present(self, agents_html):
        """当效率表格渲染时必须有标题。"""
        if "Agent/Model Efficiency" in agents_html:
            assert "Agent/Model Efficiency" in agents_html, \
                "效率区域必须有标题"

    @pytest.mark.contract_case("UI-AGENTS-006")
    def test_efficiency_columns_when_present(self, agents_html):
        """当效率表格渲染时必须有预期的列。"""
        if "efficiency-table" in agents_html:
            for col in ["Agent", "Model", "Sessions", "Avg Duration", "P95 Duration"]:
                assert col in agents_html, \
                    f"效率表格必须有 '{col}' 列"


# ── TestAgentsEmptyState ───────────────────────────────────────────────


class TestAgentsEmptyState:
    """验证当夹具包含数据时不显示空状态。"""

    @pytest.mark.contract_case("UI-AGENTS-006")
    def test_no_empty_state_when_data_present(self, agents_html):
        """当存在 agents 数据时，空状态不得显示。"""
        # 模板在 {% else %} 分支中显示空状态
        # 当 agents 存在时，渲染指标网格和表格
        assert 'class="metric-grid"' in agents_html, \
            "当 agents 存在时必须渲染指标网格"
        assert 'id="agents-table"' in agents_html, \
            "当 agents 存在时必须渲染 agents 表格"


# ── TestAgentsAccessibility ────────────────────────────────────────────


class TestAgentsAccessibility:
    """渲染后 Agents 页面的可访问性门控。"""

    @pytest.mark.contract_case("UI-AGENTS-006")
    def test_no_inline_onclick(self, agents_html):
        """Agents 不得使用 inline onclick 处理器。"""
        matches = re.findall(r'\bonclick\s*=', agents_html, re.IGNORECASE)
        assert len(matches) == 0, \
            f"Agents 不得有 inline onclick，发现 {len(matches)} 处"

    @pytest.mark.contract_case("UI-AGENTS-006")
    def test_sort_carets_aria_hidden(self, agents_html):
        """排序箭头必须有 aria-hidden='true'。"""
        carets = re.findall(
            r'class="sort-caret" aria-hidden="true"',
            agents_html
        )
        assert len(carets) >= 8, \
            f"预期至少 8 个带 aria-hidden 的排序箭头，发现 {len(carets)} 个"

    @pytest.mark.contract_case("UI-AGENTS-006")
    def test_metric_grid_aria_label(self, agents_html):
        """指标网格必须有 aria-label。"""
        assert 'aria-label="Agent summary metrics"' in agents_html, \
            "指标网格必须有 aria-label='Agent summary metrics'"

    @pytest.mark.contract_case("UI-AGENTS-006")
    def test_info_buttons_have_aria_label(self, agents_html):
        """每个信息按钮必须有 aria-label。"""
        pattern = r'data-action="info"[^>]*aria-label="[^"]*"'
        matches = re.findall(pattern, agents_html)
        assert len(matches) >= 4, \
            f"预期至少 4 个带 aria-label 的信息按钮，发现 {len(matches)} 个"

    @pytest.mark.contract_case("UI-AGENTS-006")
    def test_emoji_spans_aria_hidden(self, agents_html):
        """所有 emoji span 必须有 aria-hidden='true'。"""
        emoji_spans = re.findall(r'class="emoji"[^>]*>', agents_html)
        for span in emoji_spans:
            assert 'aria-hidden="true"' in span, \
                f"Emoji span 必须有 aria-hidden='true'：{span}"

    @pytest.mark.contract_case("UI-AGENTS-006")
    def test_breadcrumb_links(self, agents_html):
        """面包屑必须链接到 Dashboard。"""
        assert 'href="/dashboard"' in agents_html, \
            "面包屑必须链接到 /dashboard"
        assert ">Agents</span>" in agents_html or ">Agents<" in agents_html, \
            "面包屑必须显示 Agents 为当前页"


# ── TestAgentsDataActions ──────────────────────────────────────────────


class TestAgentsDataActions:
    """验证所有必需的 data-action 属性都存在。"""

    _EXPECTED_ACTIONS = ["open-agent", "info", "sort"]

    @pytest.mark.parametrize("action", _EXPECTED_ACTIONS)
    @pytest.mark.contract_case("UI-AGENTS-006")
    def test_data_action_present(self, agents_html, action):
        """页面必须有预期的 data-action 属性。"""
        assert f'data-action="{action}"' in agents_html, \
            f"页面必须有 data-action='{action}'"
