"""时间线预览用户输入测试 (v9)。
v9 在视图模型 (routes.py) 中构建预览文本:
- preview_title: 来自 round.preview_text 或 user_msg.content[:80]（已清洗）
- preview_subtitle: 工具数量字符串
- 用户输入指示已嵌入 preview_title，而非单独标签
"""

import pytest

import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ROUTES = os.path.join(ROOT, "src", "session_browser", "web", "routes.py")


def _read_routes():
    with open(ROUTES) as f:
        return f.read()


class TestPreviewTextBuiltInViewmodel:
    """验证预览文本在 routes.py 中由 user_msg.content 构建。"""

    @pytest.mark.contract_case("UI-SD-024")
    def test_preview_title_uses_user_msg(self):
        source = _read_routes()
        assert "user_msg.content" in source
        assert "preview_title" in source

    @pytest.mark.contract_case("UI-SD-024")
    def test_preview_title_sanitized(self):
        """preview_title 应清洗禁止出现的框架词汇。"""
        source = _read_routes()
        # 应将禁止词汇替换为 ***
        assert "***" in source

    @pytest.mark.contract_case("UI-SD-024")
    def test_preview_subtitle_shows_tool_count(self):
        """preview_subtitle 应显示工具数量。"""
        source = _read_routes()
        assert "preview_subtitle" in source
        assert "tool" in source.lower()


class TestPreviewTagDoesNotLeakUserContent:
    """验证用户输入内容不会直接泄露到模板中。"""

    @pytest.mark.contract_case("UI-SD-024")
    def test_no_direct_user_msg_in_session_template(self):
        """session.html 不应直接引用 user_msg.content。"""
        session_html = os.path.join(
            ROOT, "src", "session_browser", "web", "templates", "session.html"
        )
        with open(session_html) as f:
            content = f.read()
        # user_msg.content 不应直接出现在模板中
        assert "user_msg.content" not in content, (
            "模板不应直接引用 user_msg.content"
        )

    @pytest.mark.contract_case("UI-SD-024")
    def test_preview_uses_view_model_vars(self):
        """模板应使用视图模型中的 row.preview_title，而非原始内容。"""
        timeline = os.path.join(
            ROOT, "src", "session_browser", "web", "templates",
            "components", "session_detail_timeline.html"
        )
        with open(timeline) as f:
            content = f.read()
        assert "row.preview_title" in content, "Should use row.preview_title"
        assert "row.preview_subtitle" in content, "Should use row.preview_subtitle"


class TestPreviewTextTruncation:
    """验证视图模型中预览文本的截断处理。"""

    @pytest.mark.contract_case("UI-SD-024")
    def test_truncation_in_routes(self):
        source = _read_routes()
        # preview_title 截断至 120 字符
        assert "[:120]" in source or "[:80]" in source
