"""Round-level signals and summary merging.

Extracted from routes.py. Computes actionable round-level signals for the
Timeline tab and merges raw parse summaries into DB canonical summaries.
"""

from __future__ import annotations

from session_browser.domain.models import ConversationRound


def compute_bar_scale(round_tokens: int, max_round_tokens: int) -> float:
    """Compute the proportional width for a round's token bar.

    Returns a percentage (0-100) representing how wide this round's
    bar should be relative to the maximum round in the timeline.
    The max round gets 100%, others are scaled proportionally.
    """
    if max_round_tokens <= 0:
        return 0
    return round_tokens / max_round_tokens * 100


def compute_round_signals(
    round,  # ConversationRound
    round_index: int,  # 1-based
    session_input_tokens: int = 0,
) -> list[dict]:
    """Compute actionable round-level signals for the Timeline tab.

    Only returns signals that represent "worth opening to investigate" events.
    Normal/positive/low-value states (warm-up, cache-hit, low-output) are
    intentionally excluded to reduce noise.

    Returns a list of dicts with keys: key, label, severity, reason.
    """
    signals: list[dict] = []

    rb = round.token_breakdown()
    round_input_total = rb["input"] + rb["cache_read"] + rb["cache_write"]
    round_tools = round.tool_calls
    failed_tools = [tc for tc in round_tools if tc.is_failed]
    # The caller should pass session input-side total:
    # fresh + cache read + cache write. Older callers may pass Fresh only;
    # in that case the relative guard remains conservative for tests.
    total_session_input = session_input_tokens

    # ── Critical signals ────────────────────────────────────────────

    # Failed tool calls in a single round: warning at 1-2, critical at >= 3
    if len(failed_tools) >= 3:
        count = len(failed_tools)
        names = ", ".join(tc.name for tc in failed_tools[:3])
        suffix = f" +{count - 3}" if count > 3 else ""
        signals.append({
            "key": "failed-tool",
            "label": "failed tool",
            "severity": "critical",
            "reason": f"{count} failed tools: {names}{suffix}",
        })
    elif len(failed_tools) >= 1:
        count = len(failed_tools)
        names = ", ".join(tc.name for tc in failed_tools[:3])
        signals.append({
            "key": "failed-tool",
            "label": "failed tool",
            "severity": "warning",
            "reason": f"{count} failed tool{'s' if count != 1 else ''}: {names}",
        })

    # LLM errors in a single round: warning at 1-2, critical at >= 3
    if round.llm_error_count >= 3:
        signals.append({
            "key": "llm-error",
            "label": "llm error",
            "severity": "critical",
            "reason": f"{round.llm_error_count} LLM errors in this round",
        })
    elif round.llm_error_count >= 1:
        signals.append({
            "key": "llm-error",
            "label": "llm error",
            "severity": "warning",
            "reason": f"{round.llm_error_count} LLM error{'s' if round.llm_error_count != 1 else ''} in this round",
        })

    # ── Warning signals ─────────────────────────────────────────────

    # Single tool taking >= 5 minutes
    long_tools = [tc for tc in round_tools if tc.duration_ms >= 300_000]
    if long_tools:
        names = ", ".join(tc.name for tc in long_tools[:2])
        suffix = f" +{len(long_tools) - 2}" if len(long_tools) > 2 else ""
        signals.append({
            "key": "long-tool",
            "label": "long tool",
            "severity": "warning",
            "reason": f"{len(long_tools)} tool{'s' if len(long_tools) != 1 else ''} >= 5 min: {names}{suffix}",
        })

    # >= 20 tool calls in a round (possible loop / efficiency issue)
    if len(round_tools) >= 20:
        # Exclude the case where it's just a handful of small repeated tools
        tool_name_counts: dict[str, int] = {}
        for tc in round_tools:
            tool_name_counts[tc.name] = tool_name_counts.get(tc.name, 0) + 1
        # If top 3 tools account for >= 90% of calls, it's likely a tight loop
        sorted_counts = sorted(tool_name_counts.values(), reverse=True)
        top3 = sum(sorted_counts[:3])
        is_tight_loop = top3 >= int(len(round_tools) * 0.9)
        if not is_tight_loop or len(tool_name_counts) >= 5:
            signals.append({
                "key": "tool-burst",
                "label": "tool burst",
                "severity": "warning",
                "reason": f"{len(round_tools)} tool calls in round {round_index}",
            })

    # Cache write >= 300K tokens in a single round
    # (100K is common in long sessions; 300K+ indicates unusual context accumulation)
    if rb["cache_write"] >= 300_000:
        signals.append({
            "key": "high-write",
            "label": "high write",
            "severity": "warning",
            "reason": f"{rb['cache_write']:,} cache write tokens in round {round_index}",
        })

    # Large input: requires BOTH absolute (>= 200K) AND relative (>= 50% of session)
    # thresholds. An absolute-only check fires constantly as session context grows;
    # the percentage guard ensures it only fires when the round is truly
    # disproportionate to the session overall.
    if (round_input_total >= 200_000
            and total_session_input > 0
            and round_input_total / total_session_input >= 0.5):
        pct = round_input_total / total_session_input * 100
        signals.append({
            "key": "large-input",
            "label": "large input",
            "severity": "warning",
            "reason": f"{round_input_total:,} input tokens in round {round_index} ({pct:.0f}% of session)",
        })

    return signals


def _merge_raw_into_db_summary(
    db_summary: "SessionSummary",
    raw_summary: "SessionSummary | None",
) -> "SessionSummary":
    """Merge raw parse summary into DB canonical summary.

    DB summary is authoritative. Raw values are only used when the DB field
    is empty/null/zero, so that list-page and detail-page counts stay
    consistent (SD-14 fix).

    Returns the (possibly mutated) db_summary object.
    """
    if raw_summary is None:
        return db_summary

    if not db_summary.user_message_count:
        db_summary.user_message_count = raw_summary.user_message_count
    if not db_summary.assistant_message_count:
        db_summary.assistant_message_count = raw_summary.assistant_message_count
    if not db_summary.tool_call_count:
        db_summary.tool_call_count = raw_summary.tool_call_count
    if not db_summary.failed_tool_count:
        db_summary.failed_tool_count = raw_summary.failed_tool_count
    if not db_summary.input_tokens:
        db_summary.input_tokens = raw_summary.input_tokens
    if not db_summary.output_tokens:
        db_summary.output_tokens = raw_summary.output_tokens
    if not db_summary.cached_input_tokens:
        db_summary.cached_input_tokens = raw_summary.cached_input_tokens
    if not db_summary.cached_output_tokens:
        db_summary.cached_output_tokens = raw_summary.cached_output_tokens
    db_summary.duration_seconds = raw_summary.duration_seconds or db_summary.duration_seconds

    return db_summary
