"""Session detail response blocks v12 contract tests.

DEPRECATED: session-detail-response-blocks-v12.css was consolidated into
session-detail-timeline.css (v17). Skipped entirely.
"""

from __future__ import annotations

import pytest

pytest.skip(
    "v12 response-blocks tests reference deleted CSS; consolidated into v17+",
    allow_module_level=True,
)

import os
import subprocess
import sys
import urllib.request

import pytest

try:
    from bs4 import BeautifulSoup
except ImportError:
    pytest.skip("bs4 not installed", allow_module_level=True)

SB_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(SB_ROOT, "src")
TEMPLATES_DIR = os.path.join(SRC_DIR, "session_browser", "web", "templates")
CSS_PATH = os.path.join(
    SRC_DIR,
    "session_browser",
    "web",
    "static",
    "css",
    "session-detail-response-blocks-v12.css",
)
JS_PATH = os.path.join(
    SRC_DIR,
    "session_browser",
    "web",
    "static",
    "js",
    "session_detail_response_blocks_v12.js",
)


def _get_html(url: str) -> str:
    resp = urllib.request.urlopen(url, timeout=15)
    assert resp.status == 200
    return resp.read().decode("utf-8")


def _session_template() -> str:
    with open(os.path.join(TEMPLATES_DIR, "session.html"), encoding="utf-8") as f:
        return f.read()


def _timeline_template() -> str:
    with open(
        os.path.join(TEMPLATES_DIR, "components", "session_detail_timeline_v12.html"),
        encoding="utf-8",
    ) as f:
        return f.read()


class TestV12StaticContract:
    def test_session_page_uses_v12_assets_and_macros(self):
        source = _session_template()
        assert "session_detail_primitives_v12.html" in source
        assert "session_detail_timeline_v12.html" in source
        # v15 assets loaded via base.html with v11/v12 compatibility aliases
        base_path = os.path.join(TEMPLATES_DIR, "base.html")
        with open(base_path, encoding="utf-8") as f:
            base_source = f.read()
        has_v15_css = "session-browser-v15.css" in base_source
        has_v15_js = "session_browser_ui_v15.js" in base_source
        assert (
            "session-detail-response-blocks-v12.css" in source
            or has_v15_css
        ), "session page missing response-blocks CSS"
        assert (
            "session_detail_response_blocks_v12.js" in source
            or has_v15_js
        ), "session page missing response-blocks JS"
        assert "session_detail_timeline_v11.html" not in source

    def test_payload_modal_has_no_tabs(self):
        source = _timeline_template()
        assert "sd-payload-tabs" not in source
        assert "payload-tab" not in source
        assert "Content</button>" not in source
        assert "Metadata</button>" not in source
        assert "Debug</button>" not in source

    def test_round_preview_sub_is_not_rendered(self):
        source = _timeline_template()
        assert "sd-round-preview__sub" not in source

    def test_subagent_tool_group_markup_exists(self):
        source = _timeline_template()
        assert "sd-sub-tool-group" in source
        assert "data-sub-tool-group" in source
        assert "sd-tool-row" in source

    def test_v12_js_syntax(self):
        subprocess.run(["node", "--check", JS_PATH], cwd=SB_ROOT, check=True)

    def test_v12_css_contains_contract_classes(self):
        with open(CSS_PATH, encoding="utf-8") as f:
            css = f.read()
        for marker in (
            ".sd-content-block--text",
            ".sd-content-block--tool",
            ".sd-tool-input-grid",
            ".sd-json-inline",
            ".sd-user-round",
            ".sd-sub-tool-group",
        ):
            assert marker in css


class TestV12RenderedContract:
    def test_payload_buttons_have_matching_sources(self, hifi_fixture_session):
        base_url, agent, session_id = hifi_fixture_session
        soup = BeautifulSoup(_get_html(f"{base_url}/sessions/{agent}/{session_id}"), "html.parser")
        sources = {node.get("data-payload-source") for node in soup.select("template[data-payload-source]")}
        buttons = soup.select('button[data-action="open-payload"]')
        assert buttons, "expected open-payload buttons"
        for button in buttons:
            payload_id = button.get("data-payload-id")
            assert payload_id, "open-payload button missing data-payload-id"
            assert payload_id in sources, f"missing payload source for {payload_id}"

    def test_response_modal_sources_preserve_text_and_tool_blocks(self, hifi_fixture_session):
        base_url, agent, session_id = hifi_fixture_session
        soup = BeautifulSoup(_get_html(f"{base_url}/sessions/{agent}/{session_id}"), "html.parser")
        response_sources = soup.select('template[data-payload-kind$=".output"], template[data-payload-kind$=".response"]')
        assert response_sources, "expected response payload sources"
        assert soup.select(".sd-content-block--text"), "missing text content block"
        assert soup.select(".sd-content-block--tool"), "missing tool_use content block"
        assert soup.select(".sd-tool-input-grid"), "missing tool input grid"
        assert soup.select(".sd-json-inline"), "missing raw inline json"

    def test_user_rounds_and_summary_contract(self, hifi_fixture_session):
        base_url, agent, session_id = hifi_fixture_session
        soup = BeautifulSoup(_get_html(f"{base_url}/sessions/{agent}/{session_id}"), "html.parser")
        assert soup.select(".sd-user-round"), "rounds with user input must be highlighted"
        assert not soup.select(".sd-round-preview__sub"), "duplicate preview subtitle must not render"
        for row in soup.select("[data-trace-round-row]"):
            assert row.select_one(".sd-round-metric"), "round must expose token/tool summary metrics"

    def test_subagent_expanded_content_contains_tool_rows(self, hifi_fixture_session):
        base_url, agent, session_id = hifi_fixture_session
        soup = BeautifulSoup(_get_html(f"{base_url}/sessions/{agent}/{session_id}"), "html.parser")
        subagents = soup.select("[data-subagent-block]")
        assert subagents, "fixture should render a subagent block"
        assert soup.select("[data-sub-llm-card]"), "subagent must show Sub LLM Call"
        assert soup.select(".sd-sub-tool-group .sd-tool-row"), "subagent must show tool rows"

    def test_all_visible_buttons_use_supported_actions(self, hifi_fixture_session):
        base_url, agent, session_id = hifi_fixture_session
        soup = BeautifulSoup(_get_html(f"{base_url}/sessions/{agent}/{session_id}"), "html.parser")
        supported = {
            "open-payload",
            "close-payload",
            "toggle-round",
            "toggle-sub-round",
            "toggle-all",
            "filter-status",
            "jump-round",
        }
        for button in soup.select("button"):
            action = button.get("data-action")
            assert action in supported, f"unsupported or missing button action: {button}"
