#!/usr/bin/env python3
"""P0 门禁：Jinja StrictUndefined 渲染检查。

使用 StrictUndefined 渲染关键模板和 macro，确保无 undefined variable / macro。

用法:
    python3 scripts/quality/check_jinja_strict_render.py

退出码:
    0 — 通过
    1 — 发现 undefined
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_DIR = REPO_ROOT / "src" / "session_browser" / "web" / "templates"


def _build_test_env():
    """创建 StrictUndefined 模板环境，注册所有必要 filter。

    使用 ChainableUndefined 替代 StrictUndefined，以便测试 macro 调用
    时不会因为 mock 数据缺失字段而报错 — 只关注 macro 是否被正确 import。
    """
    import jinja2

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(TEMPLATE_DIR)),
        undefined=jinja2.ChainableUndefined,
    )

    sys.path.insert(0, str(REPO_ROOT / "src"))
    from session_browser.web.template_env import (
        _format_compact_token,
        _format_compact_num,
        _format_bytes,
        _relative_time,
        _to_local_time,
        _renumber_lines,
    )
    from session_browser.web.safe_render import safe_json_display
    from session_browser.web.renderers.markdown import render_markdown

    def _format_duration(seconds):
        if seconds >= 3600:
            return f"{int(seconds // 3600)}h {int((seconds % 3600) // 60)}min"
        elif seconds >= 60:
            return f"{int(seconds // 60)}min {int(seconds % 60)}s"
        else:
            return f"{int(seconds)}s"

    env.filters["format_compact_token"] = _format_compact_token
    env.filters["format_number"] = _format_compact_num
    env.filters["format_duration"] = _format_duration
    env.filters["format_bytes"] = _format_bytes
    env.filters["relative_time"] = _relative_time
    env.filters["local_time"] = _to_local_time
    env.filters["renumber_lines"] = _renumber_lines
    env.filters["safe_json_display"] = safe_json_display
    env.filters["markdown"] = render_markdown

    return env


def _render_macro(env, template_name, macro_name, args):
    """渲染指定 macro，返回 HTML 或抛出 StrictUndefined 错误。"""
    tpl = env.get_template(template_name)
    fn = getattr(tpl.module, macro_name, None)
    if fn is None:
        raise RuntimeError(f"Macro '{macro_name}' not found in {template_name}")
    return str(fn(**args))


def main() -> None:
    env = _build_test_env()
    errors = []

    mock_timeline_item_llm = {
        "type": "llm_call",
        "index": 1,
        "id": "test-call-1",
        "call_id": "test-call-1",
        "call_index": 1,
        "method": "GET",
        "path": "/test",
        "status_code": 200,
        "status_label": "OK",
        "status_tone": "ok",
        "model": "claude-sonnet-4-20250514",
        "latency_label": "1.2s",
        "token_input": 100,
        "token_output": 50,
        "token_cache_read": 20,
        "token_cache_write": 10,
        "token_total": 180,
        "tool_count_label": "2 tools",
        "summary_title": "Test LLM Call",
        "is_open": True,
        "usage": {"input": 100, "cache_read": 20, "cache_write": 10, "output": 50},
        "context_payload_id": "ctx-1",
        "context_payload_title": "Test Request",
        "response_payload_id": "resp-1",
        "response_payload_title": "Test Response",
        "request_attribution_id": "attr-req-1",
        "response_attribution_id": "attr-resp-1",
        "request_full": None,
        "response_full": None,
        "tools": [],
        "lane": "main",
        "title": "Test LLM Call",
        "summary_label": "Test LLM",
        "meta": [],
    }
    mock_timeline_item_tool = {"type": "tool_batch", "tools": [], "batch_id": "batch-1", "title": "Tool Batch", "summary_label": "Tools", "meta": []}
    mock_timeline_item_sub = {
        "type": "subagent", "agent_id": "test-sa-1", "subagent_id": "test-sa-1",
        "agent_type": "implementer", "status": "completed", "name": "test-subagent",
        "status_label": "completed", "status_tone": "ok",
        "round_index": 1,
        "title": "Test Subagent",
        "summary_label": "Subagent",
        "meta": [],
    }
    # 覆盖 subagent 嵌套 llm_call / tool_batch step 的场景（Round API 500 根因）
    mock_timeline_item_sub_with_nested = {
        "type": "subagent", "agent_id": "test-sa-2", "subagent_id": "test-sa-2",
        "agent_type": "implementer", "status": "completed", "name": "nested-subagent",
        "status_label": "completed", "status_tone": "ok",
        "round_index": 1,
        "title": "Nested Subagent",
        "summary_label": "Nested Subagent",
        "meta": [],
        "sub_rounds": [{
            "sub_round_id": 1, "has_fail": False, "title": "SR1",
            "start_time": "12:01",
            "token_input": 100, "token_cache_read": 20, "token_cache_write": 10, "token_output": 50,
            "token_total_raw": 180, "token_total": 180,
            "token_mix": {"fresh": 55, "read": 11, "write": 6, "out": 28},
            "steps": [
                {"type": "llm_call", "call_id": "nested-call-1", "call_index": 1,
                 "status_label": "OK", "status_tone": "ok", "model": "claude-sonnet-4",
                 "usage": {"input": 100, "cache_read": 20, "cache_write": 10, "output": 50},
                 "context_payload_id": "ctx-n1", "response_payload_id": "resp-n1",
                 "request_attribution_id": None, "response_attribution_id": None,
                 "request_payload_missing_reason": None, "response_payload_missing_reason": None,
                 "context_payload_title": "Nested Request", "response_payload_title": "Nested Response"},
                {"type": "tool_batch", "batch_id": "nested-batch-1", "title": "Nested Tools",
                 "summary_label": "Tools", "meta": [], "tools": []},
            ],
        }],
    }
    mock_row = {
        "round_id": 1, "is_open": True, "status_key": "ok", "title": "Test Round",
        "preview_title": "Test Round", "tool_count_label": "3 tools",
        "token_total_raw": 500, "token_total": 500,
        "token_input": 300, "token_output": 100,
        "token_cache_read": 50, "token_cache_write": 50,
        "token_mix": {"fresh": 60, "read": 10, "write": 10, "out": 20},
        "has_subagent": True, "start_time": "12:00",
        "timeline_items": [mock_timeline_item_llm, mock_timeline_item_tool, mock_timeline_item_sub],
    }

    tests = [
        ("expanded_row (wrapper)", "components/session_detail_timeline.html", "expanded_row", {"row": mock_row}),
        ("expanded_row (round_table)", "components/session_detail_timeline/round_table.html", "expanded_row", {"row": mock_row}),
        ("llm_call_card", "components/session_detail_timeline/llm_call.html", "llm_call_card", {"call": mock_timeline_item_llm}),
        ("tool_batch", "components/session_detail_timeline/llm_call.html", "tool_batch", {"batch": mock_timeline_item_tool}),
        ("subagent_block", "components/session_detail_timeline/subagent.html", "subagent_block", {"block": mock_timeline_item_sub}),
        ("subagent_block (nested llm_call/tool_batch)", "components/session_detail_timeline/subagent.html", "subagent_block", {"block": mock_timeline_item_sub_with_nested}),
    ]

    for label, tpl_name, macro_name, args in tests:
        try:
            html = _render_macro(env, tpl_name, macro_name, args)
            print(f"[PASS] {label} 渲染成功 ({len(html)} chars)")
        except Exception as e:
            errors.append(f"[BLOCK] {label} 渲染失败: {e}")

    if errors:
        print("")
        for e in errors:
            print(e)
        sys.exit(1)
    else:
        print("\n[PASS] 全部 Jinja StrictUndefined 渲染检查通过。")
        sys.exit(0)


if __name__ == "__main__":
    main()
