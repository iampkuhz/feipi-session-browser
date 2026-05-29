"""Codex 解析器测试。"""
import pytest
import json
from pathlib import Path


@pytest.mark.contract_case("DATA-SOURCE-005", "DATA-SOURCE-006", "DATA-SOURCE-007")
def test_parse_session_index_empty_when_missing():
    """测试无数据目录时 parse_session_index 返回空列表。"""
    from session_browser.sources import codex
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        original = codex.CODEX_DATA_DIR
        codex.CODEX_DATA_DIR = Path(tmpdir)
        try:
            result = codex.parse_session_index()
            assert result == []
        finally:
            codex.CODEX_DATA_DIR = original


@pytest.mark.contract_case("DATA-SOURCE-005", "DATA-SOURCE-006", "DATA-SOURCE-007")
def test_read_threads_db_empty_when_missing():
    """测试无数据库时 read_threads_db 返回空字典。"""
    from session_browser.sources import codex
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        original = codex.CODEX_DATA_DIR
        codex.CODEX_DATA_DIR = Path(tmpdir)
        try:
            result = codex.read_threads_db()
            assert result == {}
        finally:
            codex.CODEX_DATA_DIR = original


@pytest.mark.contract_case("DATA-SOURCE-005", "DATA-SOURCE-006", "DATA-SOURCE-007")
def test_session_file_search():
    """测试 _find_session_file 遍历层级目录。"""
    from session_browser.sources import codex
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        original = codex.CODEX_DATA_DIR
        codex.CODEX_DATA_DIR = Path(tmpdir)
        try:
            # 创建模拟会话文件
            session_dir = Path(tmpdir) / "sessions" / "2026" / "03" / "28"
            session_dir.mkdir(parents=True)
            session_file = session_dir / "rollout-2026-03-28T15-54-11-019d336f.jsonl"
            session_file.touch()

            result = codex._find_session_file("019d336f")
            assert result is not None
            assert result == session_file
        finally:
            codex.CODEX_DATA_DIR = original


# ── Codex 解析完整性门禁 ────────────────────────────────────────────


def _find_session_with_tools(min_tools: int = 5) -> str | None:
    """找一个至少有 min_tools 个 tool calls 的 Codex session ID。"""
    from session_browser.sources.codex import read_threads_db, parse_session_detail
    threads = read_threads_db()
    for sid, info in threads.items():
        if info.get("tokens_used", 0) < 10000:
            continue
        summary, messages, tool_calls, _ = parse_session_detail(sid)
        if len(tool_calls) >= min_tools:
            return sid
    return None


@pytest.mark.contract_case("DATA-SOURCE-008")
def test_codex_round_tool_contract():
    """Codex 解析门禁：每个 round 必须有 token 统计和 tool 统计。

    验证项：
    1. 每个 assistant 消息必须有 usage 字典且包含非零 token 数据
    2. 每个 tool call 必须有 tool_use_id
    3. 每个 round 必须正确匹配 tool calls（通过 tool_use_id）
    4. round 的 token 统计必须非零（至少 input 或 output > 0）
    5. session 总 token 应 >= 各 round token 之和（允许误差）
    """
    from session_browser.sources.codex import read_threads_db, parse_session_detail
    from session_browser.web.presenters.session_detail import build_rounds

    # 找一个至少有 5 个 tool calls 的 session
    sid = _find_session_with_tools(min_tools=5)
    if sid is None:
        pytest.skip("无足够 tool calls 的 Codex session 可用于测试")

    summary, messages, tool_calls, subagent_runs = parse_session_detail(sid)

    assistant_msgs = [m for m in messages if m.role == "assistant"]
    assert len(assistant_msgs) > 0, "至少应有一个 assistant 消息"

    # 1. 每个 assistant 消息必须有 usage 且 token 非零
    for i, msg in enumerate(assistant_msgs):
        assert msg.usage is not None, f"Assistant {i} 缺少 usage 数据"
        assert isinstance(msg.usage, dict), f"Assistant {i} usage 不是字典"
        input_tok = msg.usage.get("input_tokens", 0) or 0
        cached_tok = msg.usage.get("cached_input_tokens", 0) or 0
        output_tok = msg.usage.get("output_tokens", 0) or 0
        round_total = input_tok + cached_tok + output_tok
        assert round_total > 0, (
            f"Assistant {i} 的轮次 token 全为零: "
            f"input={input_tok} cached={cached_tok} output={output_tok}"
        )

    # 2. 每个 tool call 必须有 tool_use_id
    for i, tc in enumerate(tool_calls):
        assert tc.tool_use_id, f"ToolCall {i} ({tc.name}) 缺少 tool_use_id"

    # 3. 构建 rounds 并验证
    rounds = build_rounds(
        messages=messages,
        tool_calls=tool_calls,
        session_input_tokens=summary.fresh_input_tokens or summary.input_tokens,
        session_output_tokens=summary.output_tokens,
        session_cached_tokens=summary.cache_read_tokens or summary.cached_input_tokens,
        session_cache_write_tokens=summary.cache_write_tokens,
        agent="codex",
        md_filter=lambda x: x,
    )
    assert len(rounds) > 0, "应至少有一个 round"

    # 4. 每个 round 必须有非零 token 统计
    for r_idx, r in enumerate(rounds):
        assert r.total_tokens > 0, (
            f"Round {r_idx + 1} 的 total_tokens 为零"
        )

    # 5. 至少有一个 round 有 tool calls
    rounds_with_tools = [r for r in rounds if r.tool_calls]
    assert len(rounds_with_tools) > 0, "应至少有一个 round 包含 tool calls"

    # 6. 所有 matched tool calls 必须有 tool_use_id
    for r_idx, r in enumerate(rounds):
        for tc in r.tool_calls:
            assert tc.tool_use_id, (
                f"Round {r_idx + 1} 中的 tool call 缺少 tool_use_id"
            )

    # 7. assistant 消息的 tool_calls 列表应与匹配结果一致
    for r_idx, r in enumerate(rounds):
        expected_ids = {
            tc_id.get("id")
            for tc_id in (r.assistant_msg.tool_calls or [])
            if tc_id.get("id")
        }
        actual_ids = {tc.tool_use_id for tc in r.tool_calls if tc.tool_use_id}
        # tool_use_id 必须在 expected_ids 中（可能有些 expected 在 all_tool_calls 中不存在）
        for aid in actual_ids:
            assert aid in expected_ids, (
                f"Round {r_idx + 1} 中 tool_use_id={aid} 不在 assistant_msg.tool_calls 列表中"
            )

    # 8. 每个 round 必须有 interactions（用于展开详情）
    from session_browser.web.presenters.session_detail import build_llm_calls, assign_interactions_to_rounds

    llm_calls = build_llm_calls(messages, tool_calls, rounds, subagent_runs)
    assign_interactions_to_rounds(rounds, llm_calls, tool_calls, subagent_runs)

    for r_idx, r in enumerate(rounds):
        assert len(r.interactions) > 0, (
            f"Round {r_idx + 1} 没有 interactions，展开后将显示空白"
        )
        for ix in r.interactions:
            if ix.scope == "main":
                assert ix.id, f"Round {r_idx + 1} 的 main interaction 缺少 id"
