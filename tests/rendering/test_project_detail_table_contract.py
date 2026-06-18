"""T034：项目详情表格结构门控测试。

将 project.html 会话表格结构锁定为三个契约：
1. 标题单元格包含指向会话详情页面的真实链接
   （模式：<a href="/sessions/{{ s.agent }}/{{ s.session_id }}"> 或等效形式）
2. Rounds 列不使用硬编码的 em dash '—' 作为静态文本；
   应引用 s.assistant_message_count 或显式的 round_count 变量
3. 表格包裹在 ui.table_card 宏中，产生 .table-card 类

预期：测试 1 和 2 在当前代码上应 FAIL（标题为纯文本，rounds 硬编码）。
测试 3 应 PASS（project.html 第 112 行已使用 table_card）。
"""
import pytest
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_DIR = ROOT / "src" / "session_browser" / "web" / "templates"

PROJECT_HTML = TEMPLATE_DIR / "project.html"
UI_PRIMITIVES = TEMPLATE_DIR / "components" / "ui_primitives.html"


def _read_template(path: Path) -> str:
    if not path.exists():
        pytest.fail(f"{path.name} not found at {path}")
    return path.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def project_html():
    return _read_template(PROJECT_HTML)


@pytest.fixture(scope="module")
def ui_primitives_html():
    return _read_template(UI_PRIMITIVES)


# ── T034：标题单元格必须有真实链接 ─────────────────────────────────────


class TestProjectDetailTitleLink:
    """project.html 会话行中的标题单元格必须包含 <a href> 链接
    到会话详情页面。

    契约：在 #project-sessions-table 的 tbody 内，第一个 <td>
    （标题列）必须包含 <a href="/sessions/..."> 元素。
    纯文本标题如 {{ s.title }} 不带链接是不够的。
    """

    def _extract_title_td_content(self, html: str) -> str:
        """提取 project.html 中会话行 tbody 内 Title <td> 的内容。"""
        # 查找表格体
        table_match = re.search(
            r'<table[^>]*id="project-sessions-table"[^>]*>(.*?)</table>',
            html, re.DOTALL,
        )
        if not table_match:
            return ""
        tbody_match = re.search(r'<tbody>(.*?)</tbody>', table_match.group(1), re.DOTALL)
        if not tbody_match:
            return ""
        tbody = tbody_match.group(1)
        # 提取 {% for s in sessions %} 循环内的第一个 <td>
        # 查找 Title 列 <td> 的内容
        td_match = re.search(r'<td>\s*<div class="title-main">(.*?)</div>', tbody, re.DOTALL)
        return td_match.group(1) if td_match else ""

    @pytest.mark.contract_case("UI-PROJECTS-003")
    def test_title_cell_contains_link(self, project_html):
        """标题单元格必须包含指向会话详情页面的 <a href> 链接。"""
        title_content = self._extract_title_td_content(project_html)
        assert title_content, "No Title <td> with <div class=\"title-main\"> found in project.html"

        has_link = "<a href" in title_content
        assert has_link, (
            "Title cell in project.html lacks an <a href> link to session detail. "
            f"Current title content: {title_content[:200]}. "
            "Must include <a href=\"/sessions/{{ s.agent }}/{{ s.session_id }}\"> or equivalent."
        )

    @pytest.mark.contract_case("UI-PROJECTS-003")
    def test_title_link_follows_session_url_pattern(self, project_html):
        """如果链接存在，应遵循规范的会话 URL 模式。"""
        title_content = self._extract_title_td_content(project_html)
        if not title_content:
            pytest.fail("No title cell content found")

        # 检查规范模式：/sessions/{{ s.agent }}/{{ s.session_id }}
        # 或渲染等效形式：/sessions/
        has_session_link = bool(re.search(
            r'/sessions/\{\{.*?s\.agent.*?\}/\{\{.*?s\.session_id.*?\}\}',
            title_content,
        )) or "/sessions/" in title_content

        assert has_session_link, (
            "Title link does not follow canonical session URL pattern "
            "/sessions/<agent>/<session_id>. "
            f"Current title content: {title_content[:200]}"
        )


# ── T034：Rounds 列不得硬编码 em dash ──────────────────────────────────


class TestProjectDetailRoundsColumn:
    """project.html 的 Rounds 列不得使用硬编码的 em dash '—'。

    契约：Rounds <td> 应引用 s.assistant_message_count
    或从会话数据派生的显式 round_count 变量。
    静态的 <td class="num mono">—</td> 是已知 bug。
    """

    def _extract_rounds_td(self, html: str) -> str:
        """从会话行 tbody 中提取 Rounds 列 <td>。

        project.html tbody 中的列顺序：
          1. Title（普通 <td>）
          2. Agent（普通 <td>）
          3. Model（<td class="mono">）
          4. Tokens（<td class="token-cell">）
          5. Rounds（<td class="num mono">）  ← 第一个 num mono
          6. Tools（<td class="num mono">）    ← 第二个 num mono
          7. Duration（<td class="col-num mono">）

        因此 Rounds 列是第一个 <td class="num mono">。
        """
        table_match = re.search(
            r'<table[^>]*id="project-sessions-table"[^>]*>(.*?)</table>',
            html, re.DOTALL,
        )
        if not table_match:
            return ""
        tbody_match = re.search(r'<tbody>(.*?)</tbody>', table_match.group(1), re.DOTALL)
        if not tbody_match:
            return ""
        tbody = tbody_match.group(1)

        # 查找所有 <td class="num mono"> — Rounds 是第一个
        num_mono_tds = re.findall(r'<td class="num mono">(.*?)</td>', tbody, re.DOTALL)
        if num_mono_tds:
            return num_mono_tds[0]  # Rounds 是 token-cell 后的第一个数值列
        return ""

    @pytest.mark.contract_case("UI-PROJECTS-003")
    def test_rounds_not_hardcoded_em_dash(self, project_html):
        """Rounds 列不得为硬编码的 em dash。"""
        rounds_td = self._extract_rounds_td(project_html)

        # em dash 字符 '—'（U+2014）或 HTML 实体 &#8212; 或 &mdash;
        hardcoded_em_dash = (
            rounds_td.strip() == '—'
            or rounds_td.strip() == '&#8212;'
            or rounds_td.strip() == '&mdash;'
        )

        assert not hardcoded_em_dash, (
            "Rounds column in project.html uses a hardcoded em dash '—'. "
            f"Current content: {rounds_td!r}. "
            "Must use s.assistant_message_count or an explicit round_count variable."
        )

    @pytest.mark.contract_case("UI-PROJECTS-003")
    def test_rounds_uses_session_data(self, project_html):
        """Rounds 列应引用会话数据如 assistant_message_count。"""
        rounds_td = self._extract_rounds_td(project_html)

        # 查找引用会话回合数据的模板变量
        uses_session_data = bool(re.search(
            r's\.assistant_message_count|s\.round_count|s\.num_rounds|round_count',
            rounds_td,
        ))

        assert uses_session_data, (
            "Rounds column does not reference any session data variable "
            "(s.assistant_message_count or similar). "
            f"Current content: {rounds_td[:200]!r}. "
            "Must display actual round counts from session data."
        )


# ── T033: 表格必须使用 table_card 宏 ─────────────────────────────────


class TestProjectDetailTableCardWrapper:
    """project.html 中的会话表格必须包裹在 ui.table_card 中，
    生成 <section class="card table-card"> 元素。

    契约：project.html 必须：
    - 调用 {% call ui.table_card(...) %}，或
    - 在表格包裹的 section 上产生 class="table-card" 的 HTML
    """

    @pytest.mark.contract_case("UI-PROJECTS-003")
    def test_uses_table_card_macro(self, project_html):
        """project.html 必须调用 ui.table_card 宏。"""
        uses_macro = "ui.table_card" in project_html
        assert uses_macro, (
            "project.html does not call ui.table_card macro. "
            "The session table must be wrapped in the table_card composite."
        )

    @pytest.mark.contract_case("UI-PROJECTS-003")
    def test_table_card_produces_correct_class(self, ui_primitives_html):
        """ui_primitives 中的 table_card 宏必须产生 .table-card 类。"""
        # 查找 table_card 宏定义并检查它产生 card table-card
        macro_match = re.search(
            r'{% macro table_card\(.*?%}(.*?){%- endmacro %}',
            ui_primitives_html, re.DOTALL,
        )
        assert macro_match, "table_card macro not found in ui_primitives.html"

        macro_body = macro_match.group(1)
        has_table_card_class = "'table-card'" in macro_body or '"table-card"' in macro_body
        assert has_table_card_class, (
            "table_card macro does not produce 'table-card' class. "
            "The macro must include 'table-card' in its section class."
        )
