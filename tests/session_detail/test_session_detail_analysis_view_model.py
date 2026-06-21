"""Session Detail 运行分析 view model 契约。"""

from pathlib import Path

from session_browser.domain.models import ChatMessage, ConversationRound, LLMCall, ToolCall
from session_browser.web.routes import _build_v11_view_model
from session_browser.web.session_detail.payloads import _build_payload_lookup
from session_browser.web.session_detail.preview import apply_round_preview


ROOT = Path(__file__).resolve().parents[2]


class _FakeSession:
    def __init__(self, **kwargs):
        self.agent = kwargs.get("agent", "claude_code")
        self.session_id = kwargs.get("session_id", "analysis-session")
        self.title = kwargs.get("title", "Analysis Session")
        self.model = kwargs.get("model", "claude-sonnet")
        self.git_branch = kwargs.get("git_branch", "main")
        self.started_at = kwargs.get("started_at", "2026-01-01T00:00:00Z")
        self.ended_at = kwargs.get("ended_at", "2026-01-01T00:02:00Z")
        self.project_key = kwargs.get("project_key", "/tmp/project")
        self.project_name = kwargs.get("project_name", "project")
        self.file_path = kwargs.get("file_path", "/tmp/project/.claude/session.jsonl")
        self.output_tokens = kwargs.get("output_tokens", 300)
        self.fresh_input_tokens = kwargs.get("fresh_input_tokens", 1400)
        self.cache_read_tokens = kwargs.get("cache_read_tokens", 600)
        self.cache_write_tokens = kwargs.get("cache_write_tokens", 200)
        self.total_tokens = kwargs.get("total_tokens", 2500)
        self.failed_tool_count = kwargs.get("failed_tool_count", 0)
        self.duration_seconds = kwargs.get("duration_seconds", 120)
        self.model_execution_seconds = kwargs.get("model_execution_seconds", 40)
        self.tool_execution_seconds = kwargs.get("tool_execution_seconds", 20)



class _FakeAnomalies:
    anomalies = []


def _round(index: int, interaction: LLMCall, tools: list[ToolCall]) -> ConversationRound:
    row = ConversationRound(
        user_msg=ChatMessage("user", f"Prompt {index}", "2026-01-01T00:00:00Z"),
        assistant_msg=ChatMessage("assistant", f"Answer {index}", "2026-01-01T00:00:01Z"),
        tool_calls=tools,
        interactions=[interaction],
        round_index=index - 1,
    )
    apply_round_preview(row)
    return row


def _llm(round_index: int, suffix: str, **kwargs) -> LLMCall:
    return LLMCall(
        id=f"llm-{suffix}",
        model="claude-sonnet",
        scope=kwargs.get("scope", "main"),
        subagent_id=kwargs.get("subagent_id", ""),
        round_index=round_index,
        parent_id=kwargs.get("parent_id", ""),
        parent_tool_name=kwargs.get("parent_tool_name", ""),
        timestamp=kwargs.get("timestamp", "2026-01-01T00:00:01Z"),
        status="ok",
        input_tokens=kwargs.get("input_tokens", 100),
        cache_read_tokens=kwargs.get("cache_read_tokens", 50),
        cache_write_tokens=kwargs.get("cache_write_tokens", 20),
        output_tokens=kwargs.get("output_tokens", 30),
        request_full=kwargs.get("request_full", "request"),
        response_full=kwargs.get("response_full", "response"),
        content_blocks=kwargs.get("content_blocks", []),
    )


def test_run_analysis_hero_kpi_contract_and_global_tool_count():
    failed_tool = ToolCall(name="Bash", result="failed", status="error", tool_use_id="tool-1")
    ok_tool = ToolCall(name="Read", result="ok", status="completed", tool_use_id="tool-2")
    ix1 = _llm(0, "one", input_tokens=500, cache_read_tokens=0, cache_write_tokens=0, output_tokens=100)
    ix1.tool_calls = [failed_tool]
    ix2 = _llm(1, "two", input_tokens=100, cache_read_tokens=600, cache_write_tokens=200, output_tokens=200)
    ix2.tool_calls = [ok_tool]
    rounds = [_round(1, ix1, [failed_tool]), _round(2, ix2, [ok_tool])]

    vm = _build_v11_view_model(
        session=_FakeSession(),
        rounds=rounds,
        llm_calls=[ix1, ix2],
        tool_calls=[failed_tool, ok_tool],
        subagent_runs=[],
        session_anomalies=_FakeAnomalies(),
        slim=True,
    )

    metrics = vm["hero_metrics"]
    assert vm["session_summary"]["session_file_path"] == "/tmp/project/.claude/session.jsonl"
    assert {
        "run_health",
        "tokens",
        "cache_reuse",
        "workload",
        "active_time",
    }.issubset(metrics)
    assert int(metrics["tool_calls"]) == 2
    assert metrics["run_health"] == "Completed with issue signals"
    assert int(metrics["failed_tools"]) == 1
    assert vm["diagnostics"]["issue_summary"]["tool_failures"] == 1
    assert any(row["has_issues"] for row in vm["trace_rows"])


def test_analysis_cards_view_model_fields_renderable():
    ix = _llm(0, "one")
    rounds = [_round(1, ix, [])]

    vm = _build_v11_view_model(
        session=_FakeSession(total_tokens=250),
        rounds=rounds,
        llm_calls=[ix],
        tool_calls=[],
        subagent_runs=[],
        session_anomalies=_FakeAnomalies(),
        slim=True,
    )

    diagnostics = vm["diagnostics"]
    for key in [
        "call_distribution",
        "call_legend",
        "tool_impact",
        "agent_breakdown",
        "agent_timelines",
        "subagent_breakdown",
        "subagent_timelines",
        "context_segments",
    ]:
        assert key in diagnostics
    assert "payload_coverage" not in diagnostics
    assert len(diagnostics["token_stats"]) <= 4
    assert diagnostics["call_distribution"][0]["time_label"]
    assert diagnostics["call_legend"][0]["label"] == "Main call"
    first_payload_item = vm["payload_index"]["groups"][0]["items"][0]
    assert first_payload_item["request_attribution_status"] == "partial"
    assert first_payload_item["response_attribution_status"] == "partial"


def test_agent_breakdown_rows_expose_truncated_copy_fields_and_failure_rate_na():
    main_ix = _llm(0, "one")
    rounds = [_round(1, main_ix, [])]
    main_session_id = "019ede24-67de-7b11-b46f-7922530907a9"
    main_file = (
        "/Users/example/.codex/sessions/2026/06/19/"
        "rollout-2026-06-19T10-14-27-019ede24-67de-7b11-b46f-7922530907a9.jsonl"
    )
    subagent_id = "019ede58-af12-7892-8fc4-0e8b2949608f"
    subagent_file = (
        "/Users/example/.codex/sessions/2026/06/19/"
        "rollout-2026-06-19T10-16-00-019ede58-af12-7892-8fc4-0e8b2949608f.jsonl"
    )
    subagent_call = _llm(
        0,
        "sub-copy",
        scope="subagent",
        subagent_id=subagent_id,
        input_tokens=80,
        output_tokens=20,
    )

    vm = _build_v11_view_model(
        session=_FakeSession(session_id=main_session_id, file_path=main_file),
        rounds=rounds,
        llm_calls=[main_ix, subagent_call],
        tool_calls=[],
        subagent_runs=[{
            "path": subagent_file,
            "summary": {
                "agent_id": subagent_id,
                "agent_type": "ui-architect",
                "path": subagent_file,
            },
            "messages": [],
        }],
        session_anomalies=_FakeAnomalies(),
        slim=True,
    )

    main_row, subagent_row = vm["diagnostics"]["agent_breakdown"][:2]
    assert main_row["session_file"] == main_file
    assert main_row["session_file_display"] != main_file
    assert "…" in main_row["session_file_display"]
    assert main_row["session_id"] == main_session_id
    assert main_row["session_id_display"] != main_session_id
    assert "…" in main_row["session_id_display"]
    assert main_row["failure_rate"] == "N/A"
    assert main_row["failure_label"] == "0 failed · N/A"
    assert "No main-scope tool calls" in main_row["failure_note"]

    assert subagent_row["session_file"] == subagent_file
    assert subagent_row["session_file_display"] != subagent_file
    assert subagent_row["session_id"] == subagent_id
    assert subagent_row["session_id_display"] != subagent_id
    assert subagent_row["failure_rate"] == "N/A"
    assert subagent_row["failure_label"] == "0 failed · N/A"


def test_payload_lookup_uses_global_llm_call_ids():
    ix1 = _llm(0, "one", request_full="request 1", response_full="response 1")
    ix2 = _llm(1, "two", request_full="request 2", response_full="response 2")
    rounds = [_round(1, ix1, []), _round(2, ix2, [])]

    payloads = _build_payload_lookup(rounds, [], [], truncate=True)

    assert "llm-R1-IX1-context" in payloads
    assert "llm-R2-IX2-context" in payloads
    assert "llm-R2-IX1-context" not in payloads


def test_tool_result_payloads_include_estimated_tokens():
    result_text = "line one\n" + ("result payload text " * 80)
    tool = ToolCall(
        name="exec_command",
        parameters={"cmd": "pytest"},
        result=result_text,
        status="completed",
        tool_use_id="call_1",
    )
    ix = _llm(0, "one", response_full="assistant text")
    ix.tool_calls = [tool]
    rounds = [_round(1, ix, [tool])]

    payloads = _build_payload_lookup(rounds, [], [], truncate=False)
    api_payload = payloads["tool-R1-T1"]
    assert api_payload["kind"] == "tool.result"
    assert api_payload["token_estimate"] > 0
    assert api_payload["token_estimate_precision"] == "estimated"
    assert api_payload["token_estimate_source"] == "result text"

    vm = _build_v11_view_model(
        session=_FakeSession(agent="codex"),
        rounds=rounds,
        llm_calls=[ix],
        tool_calls=[tool],
        subagent_runs=[],
        session_anomalies=_FakeAnomalies(),
        slim=False,
        skip_attribution=True,
    )
    rendered_payloads = {p["payload_id"]: p for p in vm["payload_sources"]}
    modal_payload = rendered_payloads["tool-R1-T1"]
    assert modal_payload["token_estimate"] == api_payload["token_estimate"]
    assert modal_payload["token_estimate_precision"] == "estimated"


def test_assistant_text_payload_excludes_tool_use_blocks():
    tool = ToolCall(
        name="exec_command",
        parameters={"cmd": "pwd"},
        result="ok",
        status="completed",
        tool_use_id="call_1",
    )
    ix = _llm(
        0,
        "one",
        response_full="assistant text",
        content_blocks=[
            {"type": "text", "content": "assistant text", "source": "response_item.message"},
            {"type": "tool_use", "id": "call_1", "name": "exec_command", "parameters": {"cmd": "pwd"}},
        ],
    )
    ix.tool_calls = [tool]
    rounds = [_round(1, ix, [tool])]

    vm = _build_v11_view_model(
        session=_FakeSession(agent="codex"),
        rounds=rounds,
        llm_calls=[ix],
        tool_calls=[tool],
        subagent_runs=[],
        session_anomalies=_FakeAnomalies(),
        slim=False,
        skip_attribution=True,
    )

    payloads = {p["payload_id"]: p for p in vm["payload_sources"]}
    assistant_payload = payloads["llm-R1-IX1-assistant-text"]
    response_payload = payloads["llm-R1-IX1-output"]
    assistant_rows = [
        item for item in vm["trace_rows"][0]["timeline_items"]
        if item.get("type") == "assistant_text"
    ]

    assert assistant_rows
    assert assistant_rows[0]["payload_id"] == "llm-R1-IX1-assistant-text"
    assert "tool_use" not in assistant_payload.get("html", "")
    assert "exec_command" not in assistant_payload.get("html", "")
    assert "assistant text" in assistant_payload.get("html", "")
    assert "tool_use" in response_payload.get("html", "")
    assert "exec_command" in response_payload.get("html", "")


def test_subagent_workload_and_breakdown_use_normalized_llm_calls():
    main_ix = _llm(0, "main", input_tokens=80, cache_read_tokens=120, cache_write_tokens=20, output_tokens=40)
    parent_result = "parent result " + ("x" * 400)
    sub_result = "sub tool result " + ("y" * 120)
    parent_tool = ToolCall(
        name="Agent",
        result=parent_result,
        status="completed",
        tool_use_id="agent-tool-1",
        subagent_summary={"agent_id": "sa-1", "agent_type": "repo-mapper"},
    )
    sub_tool = ToolCall(
        name="Read",
        result=sub_result,
        status="completed",
        tool_use_id="sub-tool-1",
        scope="subagent",
        subagent_id="sa-1",
    )
    rounds = [_round(1, main_ix, [parent_tool])]
    subagent_call = _llm(
        0,
        "sub",
        scope="subagent",
        subagent_id="sa-1",
        parent_id="agent-tool-1",
        parent_tool_name="Agent",
        input_tokens=200,
        cache_read_tokens=300,
        cache_write_tokens=50,
        output_tokens=70,
        request_full="sub request",
        response_full="sub response",
    )
    subagent_runs = [{
        "summary": {"agent_id": "sa-1", "agent_type": "repo-mapper"},
        "messages": [
            ChatMessage("assistant", "first raw message", "2026-01-01T00:00:02Z"),
            ChatMessage(
                "assistant",
                "indexed sub response",
                "2026-01-01T00:00:03Z",
                llm_call_id=subagent_call.id,
                usage={
                    "input_tokens": 9,
                    "cache_read_input_tokens": 0,
                    "cache_creation_input_tokens": 0,
                    "output_tokens": 5,
                },
            ),
        ],
    }]

    vm = _build_v11_view_model(
        session=_FakeSession(total_tokens=1200),
        rounds=rounds,
        llm_calls=[main_ix, subagent_call],
        tool_calls=[parent_tool, sub_tool],
        subagent_runs=subagent_runs,
        session_anomalies=_FakeAnomalies(),
        slim=True,
    )

    token_round = vm["diagnostics"]["token_rounds"][0]
    assert any("Token Driver R1" in badge for badge in token_round["badges"])

    assert vm["hero_metrics"]["subagent_llm_calls"] == "1"
    assert vm["hero_metrics"]["workload"] == "2"
    row = vm["diagnostics"]["subagent_breakdown"][0]
    expected_footprint = (
        200 + 300 + 50 + 70
        + len(parent_result) // 4
        + len(sub_result) // 4
    )
    assert row["tokens_raw"] == expected_footprint
    assert "Parent result" in row["token_note"]
    assert "Tool results" in row["token_note"]
    assert row["subagent_id"] == "sa-1"
    assert row["is_selected"] is True
    assert row["cost_share"] != "N/A"
    assert "LLM call" in row["cost_reason"]

    assert "call_summary" not in token_round

    agent_rows = vm["diagnostics"]["agent_breakdown"]
    assert agent_rows[0]["scope"] == "main"
    assert agent_rows[0]["subagent"] == "main agent"
    assert agent_rows[0]["is_selected"] is True
    assert agent_rows[1]["scope"] == "subagent"
    assert agent_rows[1]["subagent_id"] == "sa-1"

    agent_timelines = vm["diagnostics"]["agent_timelines"]
    assert agent_timelines[0]["scope"] == "main"
    assert agent_timelines[0]["is_selected"] is True
    assert agent_timelines[0]["token_rounds"][0]["round_id"] == 1
    assert agent_timelines[1]["scope"] == "subagent"
    assert agent_timelines[1]["is_selected"] is False

    subagent_timeline = vm["diagnostics"]["subagent_timelines"][0]
    assert subagent_timeline["subagent_id"] == "sa-1"
    assert subagent_timeline["is_selected"] is True
    assert subagent_timeline["token_rounds"][0]["round_label"] == "SR2"
    assert subagent_timeline["token_rounds"][0]["parent_round"] == 1

    subagent_call_row = next(
        item for item in vm["diagnostics"]["call_distribution"]
        if item["lane"] == "subagent"
    )
    assert subagent_call_row["target_round"] == 1
    assert subagent_call_row["target_subagent"] == "sa-1"
    assert subagent_call_row["target_subagent_round"] == 2

    payload_items = [
        item
        for group in vm["payload_index"]["groups"]
        for item in group["items"]
        if item["kind"] == "subagent"
    ]
    assert payload_items[0]["subagent_id"] == "sa-1"
    assert payload_items[0]["subagent_round_id"] == 1


def test_codex_spawn_agent_subagent_appears_in_breakdown_and_trace():
    main_ix = _llm(
        0,
        "codex-main",
        input_tokens=120,
        cache_read_tokens=0,
        cache_write_tokens=0,
        output_tokens=40,
    )
    parent_tool = ToolCall(
        name="spawn_agent",
        result='{"agent_id":"codex-sa-1","nickname":"Chandrasekhar"}',
        status="completed",
        tool_use_id="spawn-tool-1",
        scope="main",
        subagent_id="codex-sa-1",
        subagent_summary={
            "agent_id": "codex-sa-1",
            "agent_type": "implementer",
            "agent_nickname": "Chandrasekhar",
        },
    )
    main_ix.tool_calls = [parent_tool]
    rounds = [_round(1, main_ix, [parent_tool])]

    subagent_call = _llm(
        0,
        "codex-sub",
        scope="subagent",
        subagent_id="codex-sa-1",
        parent_id="spawn-tool-1",
        parent_tool_name="spawn_agent",
        input_tokens=200,
        cache_read_tokens=50,
        cache_write_tokens=0,
        output_tokens=70,
        request_full="subagent request",
        response_full="subagent response",
    )
    subagent_runs = [{
        "summary": {
            "agent_id": "codex-sa-1",
            "agent_type": "implementer",
            "agent_nickname": "Chandrasekhar",
        },
        "messages": [
            ChatMessage(
                "assistant",
                "subagent response",
                "2026-01-01T00:00:03Z",
                llm_call_id=subagent_call.id,
                usage={
                    "input_tokens": 200,
                    "cached_input_tokens": 50,
                    "output_tokens": 70,
                },
                request_full="subagent request",
            ),
        ],
    }]

    vm = _build_v11_view_model(
        session=_FakeSession(agent="codex", model="gpt-5.1-codex", total_tokens=480),
        rounds=rounds,
        llm_calls=[main_ix, subagent_call],
        tool_calls=[parent_tool],
        subagent_runs=subagent_runs,
        session_anomalies=_FakeAnomalies(),
        slim=False,
        skip_attribution=True,
    )

    agent_rows = vm["diagnostics"]["agent_breakdown"]
    assert agent_rows[0]["scope"] == "main"
    assert agent_rows[1]["scope"] == "subagent"
    assert agent_rows[1]["subagent_id"] == "codex-sa-1"

    trace_row = vm["trace_rows"][0]
    assert trace_row["has_subagent"] is True
    subagent_item = next(
        item for item in trace_row["timeline_items"]
        if item.get("type") == "subagent"
    )
    assert subagent_item["subagent_id"] == "codex-sa-1"
    assert subagent_item["parent_call_index"] == 1
    assert subagent_item["sub_rounds"][0]["request_attribution"]["payload_id"]
    assert subagent_item["sub_rounds"][0]["response_attribution"]["payload_id"]

    tool_item = next(
        item for item in trace_row["timeline_items"]
        if item.get("type") == "tool_call"
    )
    assert tool_item["tool_name"] == "spawn_agent"
    assert trace_row["token_input"] == 120
    assert trace_row["token_output"] == 40


def test_call_distribution_time_labels_and_per_subagent_legend():
    main_ix = _llm(0, "main", timestamp="2026-01-01T01:02:03")
    rounds = [_round(1, main_ix, [])]
    subagent_runs = []
    subagent_calls = []
    for idx in range(6):
        sa_num = idx + 1
        sa_id = f"agent_{sa_num:03d}"
        agent_type = f"agent-{sa_num}"
        started_at = f"2026-01-01T01:02:{sa_num + 3:02d}"
        subagent_runs.append({
            "summary": {
                "agent_id": sa_id,
                "agent_type": agent_type,
                "started_at": started_at,
            },
            "messages": [],
        })
        subagent_calls.append(_llm(
            0,
            f"sub-{sa_num}",
            scope="subagent",
            subagent_id=sa_id,
            timestamp=started_at,
            input_tokens=100 + idx,
            cache_read_tokens=20,
            cache_write_tokens=10,
            output_tokens=5,
        ))

    vm = _build_v11_view_model(
        session=_FakeSession(total_tokens=1200),
        rounds=rounds,
        llm_calls=[main_ix, *subagent_calls],
        tool_calls=[],
        subagent_runs=subagent_runs,
        session_anomalies=_FakeAnomalies(),
        slim=True,
    )

    distribution = vm["diagnostics"]["call_distribution"]
    assert distribution[0]["time_label"] == "01:02:03"
    assert all(row["time_label"] for row in distribution)

    legend = vm["diagnostics"]["call_legend"]
    subagent_items = [item for item in legend if item["kind"] == "subagent"]
    assert len(subagent_items) == 6
    assert subagent_items[0]["label"] == "agent-1 · agent_001"
    assert subagent_items[0]["agent_id"] == "agent_001"
    assert subagent_items[5]["label"] == "agent-6 · agent_006"
    assert subagent_items[5]["agent_id"] == "agent_006"
    assert subagent_items[0]["color"] == subagent_items[5]["color"]


def test_run_analysis_template_sections_exist():
    session_html = (ROOT / "src/session_browser/web/templates/session.html").read_text(encoding="utf-8")
    summary_html = (
        ROOT / "src/session_browser/web/templates/components/session_detail_timeline/summary.html"
    ).read_text(encoding="utf-8")

    diagnostic_titles = [
        "Agents Breakdown",
        "Context Budget",
        "Tool Impact",
        "Issues &amp; Repro Seeds",
    ]
    for title in diagnostic_titles:
        assert title in session_html
    diagnostic_positions = [session_html.index(title) for title in diagnostic_titles]
    assert diagnostic_positions == sorted(diagnostic_positions)

    for label in ["Run Health", "Total Tokens", "Cache Health", "Workload", "Active Time"]:
        assert label in summary_html

    assert "Payload Availability" not in session_html
    assert "sd-coverage-matrix" not in session_html
    assert "Call Token Footprint Distribution" not in session_html
    assert "Top Token Drivers" not in session_html
    assert "Main Agent Breakdown" not in session_html
    assert "Subagent Breakdown" not in session_html
    assert "sd-driver-table" not in session_html
    assert "sd-diagnostic-card--context" in session_html
    assert "sd-subagent-workbench" in session_html
    assert "sd-subagent-table-scroll" in session_html
    assert "sd-subagent-table" in session_html
    assert "Session file" in session_html
    assert "Session id" in session_html
    assert "Failures" in session_html
    assert 'data-action="select-subagent"' in session_html
    assert 'data-copy-text="{{ row.session_file }}"' in session_html
    assert 'data-copy-text="{{ row.session_id }}"' in session_html
    assert "sd-subagent-timeline" in session_html
    assert "Call Selector" not in session_html
    assert 'data-action="payload-filter"' not in session_html
    assert 'data-payload-filter="failed"' not in session_html
    assert "data-payload-tab-panel" not in session_html


def test_context_budget_uses_shared_segment_bar_and_legend_colors():
    session_html = (ROOT / "src/session_browser/web/templates/session.html").read_text(encoding="utf-8")
    css = (
        ROOT / "src/session_browser/web/static/css/session-detail/08-payload-tab.css"
    ).read_text(encoding="utf-8")

    assert "sd-context-budget__track" not in session_html
    assert "sd-context-budget__track" not in css
    assert "sd-context-segment__label" in session_html
    assert "sd-context-segment__pct" in session_html
    assert "sd-context-segment--{{ loop.index }}" in session_html
    assert "sd-context-budget__dot--{{ loop.index }}" in session_html
    assert ".sd-diagnostic-card--context" in css
    assert "grid-column: 1 / -1" in css

    for index in range(1, 7):
        assert f".sd-context-segment--{index}," in css
        assert f".sd-context-budget__dot--{index}" in css


def test_agents_breakdown_table_scroll_and_copy_styles_exist():
    css = (
        ROOT / "src/session_browser/web/static/css/session-detail/08-payload-tab.css"
    ).read_text(encoding="utf-8")

    assert "--sd-subagent-row-height: 40px" in css
    assert ".sd-subagent-table-scroll" in css
    assert "overflow: auto" in css
    assert ".sd-subagent-table {\n  min-width: 820px;" in css
    assert "white-space: nowrap" in css
    assert ".sd-subagent-row.is-active td" in css
    assert ".sd-subagent-copy-btn" in css
    assert ".sd-subagent-select {\n" in css
    assert ".sd-subagent-select__main {\n  min-width: 0;\n  display: inline-flex;" in css
