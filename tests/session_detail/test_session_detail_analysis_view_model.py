"""Session Detail run-analysis view model contracts."""

from pathlib import Path

from session_browser.domain.models import ChatMessage, ConversationRound, LLMCall, ToolCall
from session_browser.web.routes import _build_v11_view_model
from session_browser.web.session_detail.payloads import _build_payload_lookup


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
        self.input_tokens = kwargs.get("input_tokens", 1400)
        self.output_tokens = kwargs.get("output_tokens", 300)
        self.cached_input_tokens = kwargs.get("cached_input_tokens", 600)
        self.cached_output_tokens = kwargs.get("cached_output_tokens", 200)
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
    row.compute_preview()
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
    assert {
        "run_health",
        "tokens",
        "cache_reuse",
        "workload",
        "active_time",
    }.issubset(metrics)
    assert int(metrics["tool_calls"]) == 2
    assert metrics["run_health"] == "Completed with issues"
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
        "cost_drivers",
        "call_distribution",
        "call_legend",
        "tool_impact",
        "subagent_breakdown",
        "payload_coverage",
        "context_segments",
    ]:
        assert key in diagnostics
    assert diagnostics["payload_coverage"]["rows"]
    assert len(diagnostics["token_stats"]) <= 4
    assert diagnostics["call_distribution"][0]["time_label"]
    assert diagnostics["call_legend"][0]["label"] == "Main call"
    first_payload_item = vm["payload_index"]["groups"][0]["items"][0]
    assert first_payload_item["request_attribution_status"] == "partial"
    assert first_payload_item["response_attribution_status"] == "partial"


def test_payload_lookup_uses_global_llm_call_ids():
    ix1 = _llm(0, "one", request_full="request 1", response_full="response 1")
    ix2 = _llm(1, "two", request_full="request 2", response_full="response 2")
    rounds = [_round(1, ix1, []), _round(2, ix2, [])]

    payloads = _build_payload_lookup(rounds, [], [], truncate=True)

    assert "llm-R1-IX1-context" in payloads
    assert "llm-R2-IX2-context" in payloads
    assert "llm-R2-IX1-context" not in payloads


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

    subagent_call_row = next(
        item for item in vm["diagnostics"]["call_distribution"]
        if item["lane"] == "subagent"
    )
    assert subagent_call_row["target_round"] == 1
    assert subagent_call_row["target_subagent"] == "sa-1"
    assert subagent_call_row["target_subagent_round"] == 2

    subagent_driver = next(
        item for item in vm["diagnostics"]["cost_drivers"]
        if item["type"] == "Subagent"
    )
    assert subagent_driver["target_subagent"] == "sa-1"

    payload_items = [
        item
        for group in vm["payload_index"]["groups"]
        for item in group["items"]
        if item["kind"] == "subagent"
    ]
    assert payload_items[0]["subagent_id"] == "sa-1"
    assert payload_items[0]["subagent_round_id"] == 1


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

    for title in [
        "Token Timeline + Cache Health",
        "Top Cost Drivers",
        "Call Cost Distribution",
        "Tool Impact",
        "Subagent Breakdown",
        "Issues &amp; Repro Seeds",
        "Payload Availability",
        "Context Budget",
    ]:
        assert title in session_html

    for label in ["Run Health", "Total Tokens", "Cache Health", "Workload", "Active Time"]:
        assert label in summary_html

    assert "sd-coverage-matrix" in session_html
    assert 'data-action="payload-filter"' in session_html
    assert 'data-payload-filter="failed"' in session_html
    assert 'data-request-attribution-status=' in session_html
    assert 'data-response-attribution-status=' in session_html
