"""HTTP server and routes for session-browser.

Uses Python's built-in http.server + jinja2 templates.
No external web framework needed for MVP.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

from session_browser.index.indexer import (
    _get_connection,
    get_dashboard_stats,
    list_sessions,
    count_sessions,
    get_sessions_list_aggregate,
    get_session,
    get_trend_data,
    get_prompt_activity_trend,
)
from session_browser.index.metrics import (
    get_token_breakdown,
    get_model_distribution,
    get_agent_distribution,
    compute_derived_metrics,
    compute_aggregate_metrics,
)
from session_browser.index.anomalies import (
    detect_all_anomalies,
    get_needs_attention,
    enrich_sessions_with_anomalies,
    AnomalyType,
)
from session_browser.web.presenters.sessions import (
    parse_sessions_query_params,
    compute_pagination,
    fetch_sessions_view_model,
)
from session_browser.web.presenters.dashboard import build_dashboard_view_model
from session_browser.web.presenters.agents import (
    build_agents_view_model,
    build_agent_view_model,
)
from session_browser.web.presenters.projects import (
    build_projects_view_model,
    build_project_view_model,
)
from session_browser.domain.models import (
    ChatMessage,
    ConversationRound,
    LLMCall,
    ToolCall,
)
from session_browser.web.presenters.session_detail import (
    build_rounds,
    build_llm_calls,
    assign_interactions_to_rounds,
)
from session_browser.web.template_env import (
    env as _template_env,
    _relative_to_repo,
    _shorten_path,
    _truncate_path,
    _display_path,
    normalize_llm_content,
    render_llm_blocks_html,
    _format_compact_token,
    _format_bytes,
    _to_local_time,
    _renumber_lines,
    _content_parts_to_blocks,
    _parts_mode_from_raw,
    _tojson_repo_html,
)
from session_browser.web.renderers.markdown import render_markdown as _md_filter
from session_browser.web import template_env as _template_mod

logger = logging.getLogger("session_browser.web")


def _build_tool_command_summary(tool_name: str, params: dict) -> str:
    """Build a short command/summary string for a tool call.

    For Read/Write/Edit tools: show file path.
    For Bash: show first 120 chars of the command.
    For Grep: show pattern + path/glob.
    For Glob: show pattern.
    For LS: show path.
    For MCP: show server/tool + key args.
    For Agent: show agent_type/agent_id.
    For unknown tools: show compact JSON key subset of parameters.

    Returns an HTML-safe string (caller must still escape if rendering).
    """
    name = (tool_name or "").strip()
    if params is None:
        params = {}

    # ── File tools: show file_path ──────────────────────────────
    if name in ("Read", "Write", "Edit"):
        return str(params.get("file_path", "") or params.get("path", ""))

    # ── Bash: first 120 chars of command ────────────────────────
    if name == "Bash":
        cmd = params.get("command", "")
        if cmd:
            cmd = str(cmd).strip()
            return cmd[:120] + ("..." if len(cmd) > 120 else "")
        return name

    # ── Grep: pattern + path/glob ───────────────────────────────
    if name == "Grep":
        parts = []
        pattern = params.get("pattern", "")
        if pattern:
            parts.append(f'"{pattern}"')
        path = params.get("paths", "")
        if path:
            if isinstance(path, list):
                path = ", ".join(str(p) for p in path[:3])
            parts.append(str(path))
        glob_p = params.get("glob", "")
        if glob_p:
            parts.append(f"--glob {glob_p}")
        return " ".join(parts) if parts else name

    # ── Glob: show pattern ──────────────────────────────────────
    if name == "Glob":
        pattern = params.get("pattern", "")
        if pattern:
            return str(pattern)
        return name

    # ── LS: show path ───────────────────────────────────────────
    if name == "LS":
        path = params.get("path", "")
        if path:
            return str(path)
        return name

    # ── MCP: show server/tool + key args ────────────────────────
    if name == "MCP" or name.lower().startswith("mcp"):
        parts = []
        server = params.get("server", "")
        tool = params.get("tool", "")
        if server:
            parts.append(str(server))
        if tool:
            parts.append(str(tool))
        # Add a few key args
        for key in ("query", "input", "text", "url", "path"):
            val = params.get(key, "")
            if val:
                val_str = str(val)
                parts.append(val_str[:60])
                break
        return "/".join(parts) if parts else name

    # ── Agent: show agent_type ──────────────────────────────────
    if name == "Agent":
        agent_type = params.get("agent_type", "")
        if agent_type:
            return str(agent_type)
        return name

    # ── Unknown: compact JSON key subset ────────────────────────
    # Show up to 3 key=value pairs (values truncated to 40 chars)
    if params:
        parts = []
        for key in list(params.keys())[:3]:
            val = params[key]
            if isinstance(val, (dict, list)):
                try:
                    val_str = json.dumps(val, ensure_ascii=False)[:40]
                except Exception:
                    val_str = str(val)[:40]
            else:
                val_str = str(val)[:40]
            parts.append(f"{key}={val_str}")
        summary = " ".join(parts)
        if summary:
            return summary

    return name


# ── Qoder short ID resolution ─────────────────────────────────────────────

_UUID_PATTERN = re.compile(
    r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
)


def _resolve_qoder_short_id(short_id: str) -> tuple[str | None, str | None]:
    """Resolve a Qoder short ID to its canonical full UUID.

    Returns (resolved_id, error_message):
    - (full_uuid, None) when exactly one full UUID has short_id as prefix.
    - (None, error_message) when multiple matches exist (ambiguous).
    - (None, None) when no match found or short_id looks like a full UUID.
    """
    if not short_id or _UUID_PATTERN.match(short_id):
        return None, None

    from session_browser.sources.qoder import _build_canonical_id_map
    canonical_map = _build_canonical_id_map()
    resolved = canonical_map.get(short_id.lower())
    if resolved:
        return resolved, None

    # Not in pre-built map — fall back to direct prefix scan
    from session_browser.sources.qoder import _discover_sessions
    uuid_pattern = _UUID_PATTERN
    full_uuids: list[str] = []
    for _pk, sid, _fp in _discover_sessions():
        if uuid_pattern.match(sid) and sid.lower().startswith(short_id.lower()):
            full_uuids.append(sid.lower())

    if len(full_uuids) == 1:
        return full_uuids[0], None
    elif len(full_uuids) > 1:
        return None, (
            f"Short ID '{short_id}' matches {len(full_uuids)} sessions "
            f"(ambiguous). Use the full UUID to disambiguate."
        )
    return None, None


# ── Query state / URL builder for /sessions ────────────────────────

_SESSIONS_URL_PARAM_ORDER = [
    "q", "agent", "model", "project",
    "sort", "dir", "page", "page_size",
]


def build_sessions_url(
    *,
    current: dict[str, str] | None = None,
    updates: dict[str, str | None] | None = None,
    reset_page: bool = False,
) -> str:
    """Build a /sessions URL preserving query state.

    Args:
        current: Existing query params (e.g. from template context).
        updates: Keys to add/override. Value ``None`` removes the key.
        reset_page: When filters/sort change, reset page to 1.
    """
    current = current or {}
    updates = updates or {}

    merged = dict(current)

    # Apply updates (None means delete)
    for key, value in updates.items():
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = str(value)

    if reset_page:
        merged.pop("page", None)

    # Filter out empty values
    params = [(k, v) for k, v in merged.items() if v and v.strip()]

    # Stable ordering
    ordered = []
    for key in _SESSIONS_URL_PARAM_ORDER:
        if key in {k for k, _ in params}:
            ordered.append((key, merged[key]))
    # Append any keys not in the standard order
    seen = {k for k, _ in ordered}
    for k, v in params:
        if k not in seen:
            ordered.append((k, v))

    qs = urllib.parse.urlencode(ordered)
    return "/sessions" + ("?" + qs if qs else "")


def _build_view_actions(
    filters: dict[str, str],
    sort_key: str,
    sort_dir: str,
    page: int,
    page_size: int | str,
    has_prev: bool,
    has_next: bool,
) -> dict:
    """Build action URLs for template rendering."""
    current = {k: v for k, v in filters.items() if v}
    if sort_key:
        current["sort"] = sort_key
    if sort_dir:
        current["dir"] = sort_dir
    if page > 1:
        current["page"] = str(page)
    if page_size and page_size != 20:
        current["page_size"] = str(page_size)

    # Sort URLs: toggle dir on active column, set new column otherwise
    sort_keys = ["tokens", "rounds", "tools", "duration", "updated"]
    sort_urls = {}
    for sk in sort_keys:
        new_dir = "asc" if (sk == sort_key and sort_dir == "asc") else "desc"
        sort_urls[sk] = build_sessions_url(
            current=current,
            updates={"sort": sk, "dir": new_dir},
            reset_page=True,
        )

    # Pagination URLs
    prev_url = ""
    next_url = ""
    if has_prev:
        prev_url = build_sessions_url(
            current=current,
            updates={"page": str(page - 1)},
        )
    if has_next:
        next_url = build_sessions_url(
            current=current,
            updates={"page": str(page + 1)},
        )

    # Page size URLs
    page_size_urls = {}
    for ps in ("20", "50", "100", "500", "all"):
        page_size_urls[ps] = build_sessions_url(
            current=current,
            updates={"page_size": ps},
            reset_page=True,
        )

    # Filter chip removal URLs
    remove_urls = {}
    for fk in ("q", "agent", "model", "project"):
        if filters.get(fk):
            remove_urls[fk] = build_sessions_url(
                current=current,
                updates={fk: None},
                reset_page=True,
            )

    # Clear All: remove all filters, keep sort
    clear_all_url = build_sessions_url(
        current={},
        updates={"sort": sort_key} if sort_key else None,
    )

    # Clear Session ID only
    clear_session_id_url = build_sessions_url(
        current=current,
        updates={"q": None},
        reset_page=True,
    )

    return {
        "clear_session_id_url": clear_session_id_url,
        "clear_all_url": clear_all_url,
        "sort_urls": sort_urls,
        "remove_filter_urls": remove_urls,
        "prev_url": prev_url,
        "next_url": next_url,
        "page_size_urls": page_size_urls,
    }


def _to_local_time_hms(iso_str: str) -> str:
    """Convert UTC ISO8601 timestamp to local-time HH:MM:SS only."""
    if not iso_str:
        return ""
    from datetime import datetime
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        local_dt = dt.astimezone()
        return local_dt.strftime("%H:%M:%S")
    except (ValueError, TypeError):
        return str(iso_str)[-8:]


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
    raw_summary: Optional["SessionSummary"],
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


class SessionBrowserHandler(BaseHTTPRequestHandler):
    """HTTP request handler for session-browser."""

    def do_GET(self) -> None:  # noqa: N802
        started_at = time.time()
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        params = urllib.parse.parse_qs(parsed.query)

        try:
            if path == "/" or path == "/dashboard":
                self._serve_dashboard()
            elif path == "/favicon.ico":
                self._send_empty(204)
            elif path == "/projects":
                self._serve_projects()
            elif path.startswith("/projects/"):
                project_key = urllib.parse.unquote(path[len("/projects/"):])
                self._serve_project(project_key)
            elif path == "/sessions":
                self._serve_all_sessions()
            elif path.startswith("/sessions/"):
                # Parse query params for export=mhtml
                path_only = path.split("?", 1)[0]
                export_mhtml = params.get("export") == ["mhtml"]

                parts = path_only[len("/sessions/"):].split("/", 1)
                if len(parts) == 2:
                    agent, session_id = parts
                    self._serve_session(agent, session_id, export_mhtml=export_mhtml)
                else:
                    self._serve_all_sessions()
            elif path == "/agents":
                self._serve_agents()
            elif path.startswith("/agents/"):
                agent = urllib.parse.unquote(path[len("/agents/"):])
                self._serve_agent(agent)
            elif path == "/glossary":
                self._serve_glossary()
            elif path.startswith("/static/"):
                self._serve_static(path[len("/static/"):])
            elif path.startswith("/api/sessions/"):
                self._serve_api_payload_path(path)
            else:
                self._send_404()
            elapsed_ms = (time.time() - started_at) * 1000
            logger.debug(
                "HTTP request handled: method=GET path=%s elapsed_ms=%.1f",
                path,
                elapsed_ms,
            )
        except BrokenPipeError:
            # Client closed the connection before we could respond — normal.
            logger.debug("Client disconnected before response: path=%s", path)
        except Exception as exc:
            logger.exception("HTTP request failed: method=GET path=%s query=%s", path, parsed.query)
            self._send_500(str(exc))

    def log_message(self, format: str, *args) -> None:
        """Route BaseHTTPRequestHandler access logs through configured logging."""
        logger.info(
            "HTTP access: client=%s message=%s",
            self.client_address[0] if self.client_address else "-",
            format % args,
        )

    def log_error(self, format: str, *args) -> None:
        """Route BaseHTTPRequestHandler error logs through configured logging."""
        logger.error(
            "HTTP handler error: client=%s message=%s",
            self.client_address[0] if self.client_address else "-",
            format % args,
        )

    def _render_template(self, name: str, **context) -> str:
        template = _template_env.get_template(name)
        return template.render(**context)

    def _send_html(self, html: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def _send_empty(self, status: int = 204) -> None:
        self.send_response(status)
        self.end_headers()

    def _send_404(self) -> None:
        self._send_html(self._render_template("404.html"), 404)

    def _send_500(self, error: str) -> None:
        logger.error("Rendering 500 response: %s", error)
        self._send_html(self._render_template("error.html", error=error), 500)

    def _send_json(self, data: dict, status: int = 200) -> None:
        body = json.dumps(data, ensure_ascii=False, default=str)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def _serve_dashboard(self) -> None:
        conn = _get_connection()
        view_model = build_dashboard_view_model(conn)
        conn.close()

        html = self._render_template("dashboard.html", **view_model)
        self._send_html(html)

    def _serve_projects(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        raw_params = urllib.parse.parse_qs(parsed.query)

        conn = _get_connection()
        view_model = build_projects_view_model(raw_params, conn)
        conn.close()

        html = self._render_template("projects.html", **view_model)
        self._send_html(html)

    def _serve_project(self, project_key: str) -> None:
        parsed = urllib.parse.urlparse(self.path)
        raw_params = urllib.parse.parse_qs(parsed.query)

        conn = _get_connection()
        view_model = build_project_view_model(conn, project_key, raw_params)
        conn.close()

        html = self._render_template("project.html", **view_model)
        self._send_html(html)

    def _serve_session(self, agent: str, session_id: str, export_mhtml: bool = False) -> None:
        session_key = f"{agent}:{session_id}"
        conn = _get_connection()
        session = get_session(conn, session_key)
        conn.close()

        if session is None:
            # For qoder, try resolving short ID -> canonical full UUID
            if agent == "qoder":
                resolved_id, err_msg = _resolve_qoder_short_id(session_id)
                if resolved_id:
                    session_key = f"{agent}:{resolved_id}"
                    conn = _get_connection()
                    session = get_session(conn, session_key)
                    conn.close()
                    if session is not None:
                        session_id = resolved_id
                if session is None and err_msg:
                    self._send_json({"error": err_msg}, status=404)
                    return
            if session is None:
                self._send_404()
                return

        # Get raw conversation data from source
        if agent == "claude_code":
            from session_browser.sources.claude import parse_session_detail
            raw_summary, messages, tool_calls, subagent_runs = parse_session_detail(
                session.project_key, session_id
            )
        elif agent == "qoder":
            from session_browser.sources.qoder import parse_session_detail
            # Prefer DB file_path; fallback to search if missing/invalid
            qoder_file = Path(session.file_path) if session.file_path and Path(session.file_path).exists() else None
            raw_summary, messages, tool_calls, subagent_runs = parse_session_detail(
                session.project_key, session_id, session_file=qoder_file
            )
        else:
            from session_browser.sources.codex import parse_session_detail
            raw_summary, messages, tool_calls, subagent_runs = parse_session_detail(session_id)

        # DB summary is canonical. raw parse only supplements detail; it must
        # NOT overwrite confirmed fields (session_id, project_key, model,
        # assistant_message_count, etc.). Only use raw values when the DB field
        # is empty/null/zero, so that list-page and detail-page round counts
        # stay consistent (SD-14 fix).
        session = _merge_raw_into_db_summary(session, raw_summary)

        # Build conversation rounds with token data and markdown rendering
        rounds = build_rounds(
            messages,
            tool_calls,
            session.input_tokens,
            session.output_tokens,
            session.cached_input_tokens,
            session.cached_output_tokens,
            agent,
            md_filter=_md_filter,
        )

        # Build LLM calls and assign interactions to rounds
        llm_calls = build_llm_calls(messages, tool_calls, rounds, subagent_runs)
        assign_interactions_to_rounds(rounds, llm_calls, tool_calls, subagent_runs)

        # Compute preview text for each round after interactions are assigned
        for r in rounds:
            r.compute_preview()

        # Compute derived metrics
        session_data = compute_derived_metrics(session.to_dict())

        # Detect anomalies for this session
        from session_browser.index.anomalies import detect_session_anomalies
        sa = detect_session_anomalies(session_data)

        # Payload visibility mismatch: check actual llm_calls for missing payloads.
        # Only flag when input tokens exist but NO call has request_full data.
        has_input = session.input_tokens > 0
        has_any_request = any(c.request_full for c in llm_calls) if llm_calls else False
        has_any_response = any(c.response_full for c in llm_calls) if llm_calls else False
        if has_input and not has_any_request and not has_any_response:
            from session_browser.index.anomalies import Anomaly, AnomalyType, SEVERITY_WARNING
            sa.anomalies.append(Anomaly(
                type=AnomalyType.PAYLOAD_VISIBILITY_MISMATCH,
                severity=SEVERITY_WARNING,
                label="Payload visibility mismatch",
                reason="Session has input tokens, but no LLM call has request/response payload data.",
            ))

        # Compute signals for each round after interactions are assigned
        round_signals = []
        for i, r in enumerate(rounds):
            round_signals.append(
                compute_round_signals(r, i + 1, session.input_tokens)
            )

        # Set repo root to session's project directory for relative path rendering
        _template_mod._SESSION_REPO_ROOT = _template_mod._get_repo_root(session.project_key) if session.project_key else None

        # Build v11 timeline view model
        v11_vm = _build_v11_view_model(session, rounds, llm_calls, tool_calls, subagent_runs, sa)

        # MHTML context
        if export_mhtml:
            logger.info("MHTML export: agent=%s session_id=%s", agent, session_id)
            from session_browser.web.mhtml import get_context
            mhtml_ctx = get_context(page="session", export_mhtml=True)
        else:
            mhtml_ctx = {}

        html = self._render_template(
            "session.html",
            session=session,
            session_data=session_data,
            rounds=rounds,
            round_signals=round_signals,
            tool_calls=tool_calls,
            llm_calls=llm_calls,
            current_agent=agent,
            session_anomalies=sa,
            active_page="session",
            session_url=f"/sessions/{agent}/{session_id}",
            session_rounds=[
                {"idx": i + 1, "name": r.preview_text or f"Round {i + 1}",
                 "status": getattr(r, "status", ""), "is_current": False}
                for i, r in enumerate(rounds)
            ],
            **v11_vm,
            **mhtml_ctx,
        )
        self._send_html(html)

    def _serve_api_payload_path(self, path: str) -> None:
        """Dispatch /api/sessions/{agent}/{session_id}/payload/{payload_id}."""
        parts = path.split("/")
        # parts: ["", "api", "sessions", agent, session_id, "payload", payload_id]
        if len(parts) == 7 and parts[5] == "payload":
            agent = urllib.parse.unquote(parts[3])
            session_id = urllib.parse.unquote(parts[4])
            payload_id = urllib.parse.unquote(parts[6])
            self._serve_api_payload(agent, session_id, payload_id)
        else:
            self._send_json({"error": "invalid API path", "expected": "/api/sessions/{agent}/{session_id}/payload/{payload_id}"}, status=400)

    def _serve_api_payload(self, agent: str, session_id: str, payload_id: str) -> None:
        """Return the full, untruncated payload for a given session and payload_id."""
        session_key = f"{agent}:{session_id}"
        conn = _get_connection()
        session = get_session(conn, session_key)
        conn.close()

        if session is None:
            # For qoder, try resolving short ID -> canonical full UUID
            if agent == "qoder":
                resolved_id, err_msg = _resolve_qoder_short_id(session_id)
                if resolved_id:
                    session_key = f"{agent}:{resolved_id}"
                    conn = _get_connection()
                    session = get_session(conn, session_key)
                    conn.close()
                    if session is not None:
                        session_id = resolved_id
                if session is None and err_msg:
                    self._send_json({"error": err_msg}, status=404)
                    return
            if session is None:
                self._send_json({"error": "session not found"}, status=404)
                return

        # Parse session detail using the same agent-specific logic as _serve_session
        if agent == "claude_code":
            from session_browser.sources.claude import parse_session_detail
            raw_summary, messages, tool_calls, subagent_runs = parse_session_detail(
                session.project_key, session_id
            )
        elif agent == "qoder":
            from session_browser.sources.qoder import parse_session_detail
            # Prefer DB file_path; fallback to search if missing/invalid
            qoder_file = Path(session.file_path) if session.file_path and Path(session.file_path).exists() else None
            raw_summary, messages, tool_calls, subagent_runs = parse_session_detail(
                session.project_key, session_id, session_file=qoder_file
            )
        else:
            from session_browser.sources.codex import parse_session_detail
            raw_summary, messages, tool_calls, subagent_runs = parse_session_detail(session_id)

        # Build conversation rounds (same as _serve_session)
        rounds = build_rounds(
            messages,
            tool_calls,
            session.input_tokens,
            session.output_tokens,
            session.cached_input_tokens,
            session.cached_output_tokens,
            agent,
            md_filter=_md_filter,
        )

        # Build LLM calls and assign interactions to rounds
        llm_calls = build_llm_calls(messages, tool_calls, rounds, subagent_runs)
        assign_interactions_to_rounds(rounds, llm_calls, tool_calls, subagent_runs)

        # Build payload lookup with NO truncation
        payload_map = _build_payload_lookup(rounds, tool_calls, subagent_runs, truncate=False)

        payload = payload_map.get(payload_id)
        if not payload:
            self._send_json({
                "error": f"payload {payload_id} not found",
                "available_keys": list(payload_map.keys())[:10],
            }, status=404)
            return

        self._send_json(payload)

    def _serve_agent(self, agent: str) -> None:
        conn = _get_connection()
        view_model = build_agent_view_model(conn, agent)
        conn.close()

        html = self._render_template("agent.html", **view_model)
        self._send_html(html)

    def _serve_agents(self) -> None:
        conn = _get_connection()
        view_model = build_agents_view_model(conn)
        conn.close()

        html = self._render_template("agents.html", **view_model)
        self._send_html(html)

    def _serve_static(self, filename: str) -> None:
        static_dir = Path(__file__).parent / "static"
        filepath = static_dir / filename
        if not filepath.exists():
            self._send_404()
            return

        content_type = "text/css" if filename.endswith(".css") else (
            "application/javascript" if filename.endswith(".js") else "text/plain"
        )
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.end_headers()
        self.wfile.write(filepath.read_bytes())

    def _serve_all_sessions(self) -> None:
        """Global sessions page — all sessions across all projects."""
        conn = _get_connection()

        # ── Parse query parameters ──────────────────────────────────
        parsed = urllib.parse.urlparse(self.path)
        raw_params = urllib.parse.parse_qs(parsed.query)

        params = parse_sessions_query_params(raw_params)

        # ── Fetch view model ────────────────────────────────────────
        total_count = count_sessions(
            conn,
            agent=params["filter_agent"],
            project_key=params["filter_project"],
            model=params["filter_model"],
            title_like=params["filter_q"],
        )

        pagination = compute_pagination(
            total_count=total_count,
            page=params["page"],
            page_size=params["page_size"],
        )

        vm = fetch_sessions_view_model(
            conn=conn,
            filter_agent=params["filter_agent"],
            filter_model=params["filter_model"],
            filter_project=params["filter_project"],
            filter_q=params["filter_q"],
            sort_by=params["sort_by"],
            sort_dir=params["sort_dir"],
            limit=pagination["limit"],
            offset=pagination["offset"],
        )

        conn.close()

        # Normalize sort key for template (ui uses 'updated' for 'ended-at')
        ui_sort = "updated" if params["raw_sort"] == "ended-at" else (params["raw_sort"] or "ended-at")

        filters_for_actions = {
            "q": params["filter_q"] or "",
            "agent": params["filter_agent"] or "",
            "model": params["filter_model"] or "",
            "project": params["filter_project"] or "",
        }
        actions = _build_view_actions(
            filters=filters_for_actions,
            sort_key=ui_sort,
            sort_dir=params["sort_dir"],
            page=pagination["page"],
            page_size=params["page_size"],
            has_prev=pagination["has_prev"],
            has_next=pagination["has_next"],
        )

        # ── AJAX partial response (X-Requested-With header) ─────────
        is_ajax = self.headers.get("X-Requested-With") == "XMLHttpRequest"
        if is_ajax:
            html = self._render_template(
                "partials/sessions_ajax_page.html",
                sessions=vm["sessions_enriched"],
                total_count=vm["total_count"],
                page=pagination["page"],
                page_size=params["page_size"],
                total_pages=pagination["total_pages"],
                page_start=pagination["page_start"],
                page_end=pagination["page_end"],
                has_prev=pagination["has_prev"],
                has_next=pagination["has_next"],
                sort_key=ui_sort,
                sort_dir=params["sort_dir"],
                actions=actions,
                sessions_aggregate=vm["sessions_aggregate"],
                filter_q=params["filter_q"] or "",
                filter_agent=params["filter_agent"] or "",
                filter_model=params["filter_model"] or "",
                filter_project=params["filter_project"] or "",
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))
            return

        html = self._render_template(
            "sessions.html",
            sessions=vm["sessions_enriched"],
            total_count=vm["total_count"],
            page=pagination["page"],
            current_page=pagination["page"],
            page_size=params["page_size"],
            total_pages=pagination["total_pages"],
            page_start=pagination["page_start"],
            page_end=pagination["page_end"],
            has_prev=pagination["has_prev"],
            has_next=pagination["has_next"],
            filter_agent=params["filter_agent"] or "",
            filter_model=params["filter_model"] or "",
            filter_project=params["filter_project"] or "",
            filter_q=params["filter_q"] or "",
            sort_by=ui_sort,
            sort_dir=params["sort_dir"],
            model_list=vm["model_list"],
            project_list=vm["project_list"],
            active_page="sessions",
            actions=actions,
            sessions_aggregate=vm["sessions_aggregate"],
        )
        self._send_html(html)

    def _serve_glossary(self) -> None:
        """Token glossary page."""
        html = self._render_template(
            "glossary.html",
            active_page="glossary",
        )
        self._send_html(html)


# ─── v9 Timeline view model ──────────────────────────────────────────

def _render_response_content_blocks(content_blocks: list[dict] = None,
                                     response_text: str = "",
                                     tool_calls: list = None,
                                     max_blocks: int = 20) -> str:
    """Generate HTML content blocks for a response payload.

    Renders all API-level content block types (text, thinking, tool_use)
    in their original interleaved order. Falls back to legacy
    response_text + tool_calls when content_blocks is unavailable.
    """
    blocks = []
    block_index = 0

    if content_blocks:
        # New path: render structured blocks in original order
        for block in content_blocks:
            if block_index >= max_blocks:
                break
            block_type = block.get("type", "")
            block_index += 1

            if block_type == "text":
                content = block.get("content", "")
                if not content or not content.strip():
                    block_index -= 1
                    continue
                char_count = len(content.encode("utf-8"))
                preview = content[:500]
                blocks.append(
                    f'<article class="sd-content-block sd-content-block--text">'
                    f'<div class="sd-block-head">'
                    f'<span class="sd-block-index">#{block_index}</span>'
                    f'<span class="sd-block-title">text</span>'
                    f'<span class="sd-block-meta">{_format_compact_token(char_count)} chars</span>'
                    f'</div>'
                    f'<div class="sd-block-body">{_html_escape(preview)}</div>'
                    f'</article>'
                )

            elif block_type == "thinking":
                content = block.get("content", "")
                if not content or not content.strip():
                    block_index -= 1
                    continue
                char_count = len(content.encode("utf-8"))
                preview = content[:500]
                blocks.append(
                    f'<article class="sd-content-block sd-content-block--thinking">'
                    f'<div class="sd-block-head">'
                    f'<span class="sd-block-index">#{block_index}</span>'
                    f'<span class="sd-block-title">thinking</span>'
                    f'<span class="sd-block-meta">{_format_compact_token(char_count)} chars</span>'
                    f'</div>'
                    f'<div class="sd-block-body">{_html_escape(preview)}</div>'
                    f'</article>'
                )

            elif block_type == "tool_use":
                tool_id = (block.get("id", "") or "")[:12]
                tool_name = block.get("name", "unknown")
                params = block.get("parameters", {}) or {}

                grid_rows = []
                grid_rows.append(f'<div class="key">name</div><div>{_html_escape(tool_name)}</div>')
                if params.get("file_path"):
                    grid_rows.append(f'<div class="key">file_path</div><div>{_html_escape(_shorten_path(str(params["file_path"])))}</div>')
                if params.get("command"):
                    grid_rows.append(f'<div class="key">command</div><div>{_html_escape(_shorten_path(str(params["command"]))[:200])}</div>')
                # Unified command summary for all tool types
                cmd_summary = _build_tool_command_summary(tool_name, params)
                if cmd_summary and cmd_summary != tool_name:
                    grid_rows.append(f'<div class="key">summary</div><div>{_html_escape(_shorten_path(str(cmd_summary))[:200])}</div>')

                try:
                    raw_json = json.dumps(params, ensure_ascii=False, indent=2)[:500]
                except Exception:
                    raw_json = "{}"

                blocks.append(
                    f'<article class="sd-content-block sd-content-block--tool">'
                    f'<div class="sd-block-head">'
                    f'<span class="sd-block-index">#{block_index}</span>'
                    f'<span class="sd-block-title">tool_use · {_html_escape(tool_name)}</span>'
                    f'<span class="sd-block-meta">{_html_escape(tool_id)}</span>'
                    f'</div>'
                    f'<div class="sd-block-body">'
                    f'<div class="sd-tool-input-grid">{"".join(grid_rows)}</div>'
                    f'<div class="sd-json-inline">{_html_escape(raw_json)}</div>'
                    f'</div>'
                    f'</article>'
                )
    else:
        # Legacy fallback: text then tool_uses (no interleaving)
        if response_text and response_text.strip():
            block_index += 1
            char_count = len(response_text.encode("utf-8"))
            preview = response_text[:500]
            blocks.append(
                f'<article class="sd-content-block sd-content-block--text">'
                f'<div class="sd-block-head">'
                f'<span class="sd-block-index">#{block_index}</span>'
                f'<span class="sd-block-title">text</span>'
                f'<span class="sd-block-meta">{_format_compact_token(char_count)} chars</span>'
                f'</div>'
                f'<div class="sd-block-body">{_html_escape(preview)}</div>'
                f'</article>'
            )

        if tool_calls:
            for tc in tool_calls:
                if block_index >= max_blocks:
                    break
                block_index += 1
                tool_id = getattr(tc, "tool_use_id", "")[:12] or ""
                tool_name = getattr(tc, "name", "unknown")
                params = getattr(tc, "parameters", {}) or {}

                grid_rows = []
                grid_rows.append(f'<div class="key">name</div><div>{_html_escape(tool_name)}</div>')
                if params.get("file_path"):
                    grid_rows.append(f'<div class="key">file_path</div><div>{_html_escape(_shorten_path(str(params["file_path"])))}</div>')
                if params.get("command"):
                    grid_rows.append(f'<div class="key">command</div><div>{_html_escape(_shorten_path(str(params["command"]))[:200])}</div>')
                # Unified command summary for all tool types
                cmd_summary = _build_tool_command_summary(tool_name, params)
                if cmd_summary and cmd_summary != tool_name:
                    grid_rows.append(f'<div class="key">summary</div><div>{_html_escape(_shorten_path(str(cmd_summary))[:200])}</div>')

                try:
                    raw_json = json.dumps(params, ensure_ascii=False, indent=2)[:500]
                except Exception:
                    raw_json = "{}"

                blocks.append(
                    f'<article class="sd-content-block sd-content-block--tool">'
                    f'<div class="sd-block-head">'
                    f'<span class="sd-block-index">#{block_index}</span>'
                    f'<span class="sd-block-title">tool_use · {_html_escape(tool_name)}</span>'
                    f'<span class="sd-block-meta">{_html_escape(tool_id)}</span>'
                    f'</div>'
                    f'<div class="sd-block-body">'
                    f'<div class="sd-tool-input-grid">{"".join(grid_rows)}</div>'
                    f'<div class="sd-json-inline">{_html_escape(raw_json)}</div>'
                    f'</div>'
                    f'</article>'
                )

    if not blocks:
        return '<div class="sd-payload-warning">Response 内容为空</div>'

    return f'<div class="sd-payload-block-list">{"".join(blocks)}</div>'


def _render_context_content_blocks(content_blocks: list[dict], max_blocks: int = 30) -> str:
    """Render context (request) content as structured block cards.

    Takes blocks from normalize_llm_content() which parses request_full text
    into typed blocks: tool_result, file_code, file_markdown, plain_text, unknown.
    Each block becomes a styled card matching the response payload design.
    """
    cards = []
    block_index = 0

    for block in content_blocks:
        if block_index >= max_blocks:
            break

        kind = block.get("kind", "unknown")
        title = block.get("title", "")
        subtitle = block.get("subtitle", "")
        content = block.get("content", "")

        if not content or not content.strip():
            continue

        block_index += 1

        # normalize_llm_content returns plain_text/file_* kinds;
        # tool results are identified by title prefix "Tool Result:"
        is_tool_result = title.startswith("Tool Result:")
        is_file = kind in ("file_code", "file_markdown")

        if is_tool_result:
            char_count = len(content.encode("utf-8"))
            preview = content[:500]
            tool_id_display = title.replace("Tool Result: ", "")[:30]
            cards.append(
                f'<article class="sd-content-block sd-content-block--tool-result">'
                f'<div class="sd-block-head">'
                f'<span class="sd-block-index">#{block_index}</span>'
                f'<span class="sd-block-title">tool_result</span>'
                f'<span class="sd-block-meta">{_html_escape(tool_id_display)}</span>'
                f'<span class="sd-block-meta">{_format_compact_token(char_count)} chars</span>'
                f'</div>'
                f'<div class="sd-block-body">{_html_escape(preview)}</div>'
                f'</article>'
            )

        elif is_file:
            char_count = len(content.encode("utf-8"))
            preview = content[:500]
            file_display = title.replace("File: ", "") if title else "file"
            lang = block.get("language", "")
            lang_display = f' · {lang}' if lang else ''
            cards.append(
                f'<article class="sd-content-block sd-content-block--file">'
                f'<div class="sd-block-head">'
                f'<span class="sd-block-index">#{block_index}</span>'
                f'<span class="sd-block-title">file{lang_display}</span>'
                f'<span class="sd-block-meta" title="{_html_escape(file_display)}">{_html_escape(file_display[:60])}</span>'
                f'<span class="sd-block-meta">{_format_compact_token(char_count)} chars</span>'
                f'</div>'
                f'<div class="sd-block-body">{_html_escape(preview)}</div>'
                f'</article>'
            )

        else:
            # plain_text or unknown
            char_count = len(content.encode("utf-8"))
            preview = content[:500]
            block_title = title if title else (subtitle if subtitle else "text")
            cards.append(
                f'<article class="sd-content-block sd-content-block--context-text">'
                f'<div class="sd-block-head">'
                f'<span class="sd-block-index">#{block_index}</span>'
                f'<span class="sd-block-title">{_html_escape(block_title)}</span>'
                f'<span class="sd-block-meta">{_format_compact_token(char_count)} chars</span>'
                f'</div>'
                f'<div class="sd-block-body">{_html_escape(preview)}</div>'
                f'</article>'
            )

    if not cards:
        return '<div class="sd-payload-warning">Context 内容为空</div>'

    return f'<div class="sd-payload-block-list">{"".join(cards)}</div>'


def _html_escape(text: str) -> str:
    """Escape HTML special characters."""
    text = str(text or "")
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
    )


def _truncate_payload(text: str, limit: int) -> str:
    """Truncate payload text if it exceeds the byte limit."""
    if not text:
        return ""
    if len(text.encode("utf-8")) > limit:
        truncated = text
        while len(truncated.encode("utf-8")) > limit:
            truncated = truncated[:-1]
        return truncated
    return text


def _build_payload_lookup(
    rounds: list,
    tool_calls: list,
    subagent_runs: list,
    truncate: bool = True,
) -> dict:
    """Build a payload lookup dict from parsed session data.

    Returns dict: {payload_id: {payload_id, kind, title, status, size, text}}

    When truncate=True, applies the same truncation limits as _build_v11_view_model:
      - subagent request/response: 5000 bytes
      - user message: 5000 bytes
      - tool result: 5000 bytes
      - LLM context/output: 10000 bytes
    When truncate=False, returns the full, untruncated text.
    """
    payload_map = {}

    def _add(payload_id: str, kind: str, title: str, text: str = "",
             status: str = "available", byte_limit: int = 5000,
             tool_name: str = "", tool_command: str = "",
             tool_parameters: dict = None, tool_status: str = ""):
        final_text = _truncate_payload(text, byte_limit) if truncate else (text or "")
        byte_count = len(final_text.encode("utf-8")) if final_text else 0
        entry = {
            "payload_id": payload_id,
            "kind": kind,
            "title": title,
            "status": status if text else "empty",
            "size": _format_bytes(byte_count) if byte_count else "—",
            "text": final_text,
        }
        if tool_name:
            entry["tool_name"] = tool_name
        if tool_command:
            entry["tool_command"] = tool_command
        if tool_parameters:
            entry["tool_parameters"] = tool_parameters
        if tool_status:
            entry["tool_status"] = tool_status
        payload_map[payload_id] = entry

    # -- Subagent payloads --
    for run in subagent_runs:
        sa_id = run["summary"]["agent_id"]
        sa_messages = run.get("messages", [])
        for m_idx, m in enumerate(sa_messages):
            if m.role == "assistant":
                call_ref = m.llm_call_id or f"sub-{sa_id}-{m_idx + 1}"
                if m.request_full:
                    _add(
                        payload_id=f"sub-{sa_id}-{m_idx + 1}-ctx",
                        kind="subagent.request",
                        title=f"Subagent · Request ({call_ref})",
                        text=m.request_full,
                        byte_limit=5000,
                    )
                if m.content:
                    _add(
                        payload_id=f"sub-{sa_id}-{m_idx + 1}-rsp",
                        kind="subagent.response",
                        title=f"Subagent · Response ({call_ref})",
                        text=m.content,
                        byte_limit=5000,
                    )

    # -- Round-level payloads (user messages, tool results, LLM calls) --
    for r_idx, r in enumerate(rounds):
        rid = r_idx + 1

        # User message
        if r.user_msg.content:
            _add(
                payload_id=f"msg-R{rid}-user",
                kind="message.user",
                title=f"R{rid} · User request",
                text=r.user_msg.content,
                byte_limit=5000,
            )

        # Interaction-level payloads
        for ix_idx, ix in enumerate(r.interactions):
            iix = ix_idx + 1

            # Subagent interactions — payloads already handled above
            if ix.scope == "subagent" and ix.subagent_id:
                continue

            # Tool batch payloads
            if hasattr(ix, 'tool_calls') and ix.tool_calls:
                for tc in ix.tool_calls:
                    if tc.subagent_id or not tc.result:
                        continue
                    tc_global_idx = -1
                    for gi, gtc in enumerate(r.tool_calls):
                        if gtc is tc:
                            tc_global_idx = gi + 1
                            break
                    if tc_global_idx == -1:
                        tc_global_idx = len([t for t in ix.tool_calls if not t.subagent_id])
                    _add(
                        payload_id=f"tool-R{rid}-T{tc_global_idx}",
                        kind="tool.result",
                        title=f"R{rid} · {tc.name} · Result",
                        text=tc.result,
                        byte_limit=5000,
                        tool_name=tc.name,
                        tool_command=_build_tool_command_summary(tc.name, tc.parameters),
                        tool_parameters=tc.parameters,
                        tool_status=f"exit {tc.exit_code}" if getattr(tc, "exit_code", None) is not None else (getattr(tc, "status", "") or "ok"),
                    )

            # LLM context and output payloads
            if ix.request_full:
                _add(
                    payload_id=f"llm-R{rid}-IX{iix}-context",
                    kind="llm.context",
                    title=f"R{rid} · LLM Call #{iix} · Context",
                    text=ix.request_full,
                    byte_limit=10000,
                )
            if ix.response_full:
                _add(
                    payload_id=f"llm-R{rid}-IX{iix}-output",
                    kind="llm.output",
                    title=f"R{rid} · LLM Call #{iix} · Output",
                    text=ix.response_full,
                    byte_limit=10000,
                )

        # Standalone tool calls (rounds with no interactions but tool_calls present)
        if not r.interactions and r.tool_calls:
            for tc_idx, tc in enumerate(r.tool_calls):
                if tc.subagent_id or not tc.result:
                    continue
                _add(
                    payload_id=f"tool-R{rid}-T{tc_idx + 1}",
                    kind="tool.result",
                    title=f"R{rid} · {tc.name} · Result",
                    text=tc.result,
                    byte_limit=5000,
                    tool_name=tc.name,
                    tool_command=_build_tool_command_summary(tc.name, tc.parameters),
                    tool_parameters=tc.parameters,
                    tool_status=f"exit {tc.exit_code}" if getattr(tc, "exit_code", None) is not None else (getattr(tc, "status", "") or "ok"),
                )

    return payload_map


def _build_v11_view_model(
    session,
    rounds: list,
    llm_calls: list,
    tool_calls: list,
    subagent_runs: list,
    session_anomalies,
) -> dict:
    """Build the v11 timeline view model for session.html template.

    Returns dict with: session_summary, hero_metrics, issue_links, trace_rows, payload_sources.

    Key differences from v9:
    - payload_sources is a LIST (not dict) matching 1:1 with all open-payload buttons
    - Each trace row has an items list with user_message, llm_call, tool_batch, subagent items
    - Subagent sub_rounds have steps[] with type field
    - LLM calls carry context_payload_title, response_payload_title, note_tone
    - User rounds produce user_message items with data-status="user"
    """
    agent_name = "Claude" if session.agent == "claude_code" else "Qoder" if session.agent == "qoder" else "Codex"
    short_id = session.session_id[-8:] if session.session_id else ""
    started = session.started_at[:10] if session.started_at else "—"

    total_tokens = session.input_tokens + session.output_tokens + session.cached_input_tokens + session.cached_output_tokens
    total_rounds = len(rounds)
    total_tools = sum(len(r.tool_calls) for r in rounds)
    total_failed = session.failed_tool_count or 0

    # -- Issue links --
    issue_links = []
    for r_idx, r in enumerate(rounds):
        failed = [tc for tc in r.tool_calls if tc.is_failed]
        if failed or r.llm_error_count > 0:
            parts = []
            if failed:
                parts.append(f"{len(failed)} failed")
            if r.llm_error_count > 0:
                parts.append(f"{r.llm_error_count} llm err")
            issue_links.append({
                "round_id": r_idx + 1,
                "label": f"R{r_idx + 1} · {', '.join(parts)}",
                "tone": "err",
            })
    issue_links = issue_links[:4]

    # -- Payload sources (LIST, not dict) --
    payload_sources = []

    def add_payload(payload_id: str, kind: str, title: str, status: str = "available",
                    size: str = "—", text: str = "", html: str = "", warning: str = "",
                    context_blocks: list = None, source_status: str = "",
                    response_blocks: list = None, response_diagnostics: str = "",
                    user_input: str = "", preceding_tool_results: list = None,
                    tool_name: str = "", tool_command: str = "",
                    tool_parameters: dict = None, tool_status: str = ""):
        entry = {
            "payload_id": payload_id,
            "kind": kind,
            "title": title,
            "status": status,
            "size": size,
        }
        if warning:
            entry["warning"] = warning
        if html:
            entry["html"] = html
        elif text:
            entry["text"] = text
        else:
            entry["text"] = ""
        # v17 typed payload fields
        if context_blocks:
            entry["context_blocks"] = context_blocks
        if source_status:
            entry["source_status"] = source_status
        if response_blocks:
            entry["response_blocks"] = response_blocks
        if response_diagnostics:
            entry["response_diagnostics"] = response_diagnostics
        if user_input:
            entry["user_input"] = user_input
        if preceding_tool_results:
            entry["preceding_tool_results"] = preceding_tool_results
        # Tool result metadata
        if tool_name:
            entry["tool_name"] = tool_name
        if tool_command:
            entry["tool_command"] = tool_command
        if tool_parameters:
            entry["tool_parameters"] = tool_parameters
        if tool_status:
            entry["tool_status"] = tool_status
        payload_sources.append(entry)

    def tool_vm(tc, tool_id: str, payload_id: str = "", payload_title: str = "") -> dict:
        params = getattr(tc, "parameters", {}) or {}
        raw_command = _build_tool_command_summary(getattr(tc, "name", "tool"), params)
        command = _shorten_path(str(raw_command))
        result_text = (getattr(tc, "result", "") or "").strip()
        if result_text:
            result_summary = result_text[:60]
        elif getattr(tc, "exit_code", None) is not None:
            result_summary = f"exit {tc.exit_code}"
        else:
            result_summary = getattr(tc, "status", "") or "ok"
        return {
            "tool_id": tool_id,
            "kind": (getattr(tc, "name", "tool") or "tool")[:4].upper(),
            "command": str(command)[:100],
            "result_summary": result_summary,
            "exit_label": f"exit {tc.exit_code}" if getattr(tc, "exit_code", None) is not None else (getattr(tc, "status", "") or "ok"),
            "status_tone": "fail" if getattr(tc, "is_failed", False) else ("warn" if getattr(tc, "has_nonzero_exit", False) else "ok"),
            "payload_id": payload_id,
            "payload_title": payload_title or "Tool Result",
        }

    def count_raw_tool_uses(ix) -> int:
        raw = getattr(ix, "tool_calls_raw", "") or ""
        if not raw:
            return 0
        try:
            parsed = json.loads(raw)
        except Exception:
            return 0
        if isinstance(parsed, list):
            return len([p for p in parsed if isinstance(p, dict) and p.get("type", "tool_use") == "tool_use"])
        return 0

    # -- Build subagent lookup --
    subagent_lookup = {}
    for run in subagent_runs:
        sa_id = run["summary"]["agent_id"]
        sa_name = run["summary"].get("agent_type", "subagent")
        sa_tools = [tc for tc in tool_calls if tc.subagent_id == sa_id]
        parent_tc = next(
            (
                tc for tc in tool_calls
                if tc.name == "Agent" and tc.subagent_summary.get("agent_id") == sa_id
            ),
            None,
        )
        display_tools = sa_tools if sa_tools else ([parent_tc] if parent_tc else [])
        sa_messages = run.get("messages", [])
        sa_input = sum((m.usage or {}).get("input_tokens", 0) for m in sa_messages)
        sa_output = sum((m.usage or {}).get("output_tokens", 0) for m in sa_messages)
        sa_failed = sum(1 for tc in display_tools if tc.is_failed)

        # Build tool_use_id → ToolCall mapping for per-round distribution
        sa_tool_by_id = {tc.tool_use_id: tc for tc in display_tools if tc.tool_use_id}
        matched_tool_ids = set()

        sub_rounds = []
        for m_idx, m in enumerate(sa_messages):
            if m.role == "assistant":
                usage = m.usage or {}
                call_ref = m.llm_call_id or f"sub-{sa_id}-{m_idx + 1}"
                ctx_payload_id = f"sub-{sa_id}-{m_idx + 1}-ctx"
                rsp_payload_id = f"sub-{sa_id}-{m_idx + 1}-rsp"

                # Register context payload for subagent LLM call (always created)
                if m.request_full:
                    ctx_norm_blocks = normalize_llm_content(m.request_full)
                    ctx_content_html = _render_context_content_blocks(ctx_norm_blocks) if ctx_norm_blocks else ""
                    add_payload(
                        payload_id=ctx_payload_id,
                        kind="subagent.request",
                        title=f"Subagent · Request ({call_ref})",
                        html=ctx_content_html,
                        source_status="raw",
                    )
                else:
                    add_payload(
                        payload_id=ctx_payload_id,
                        kind="subagent.request",
                        title=f"Subagent · Request ({call_ref})",
                        text="",
                        warning="Subagent request context not available",
                        source_status="diagnostic",
                    )

                # Register response payload for subagent LLM call (always created)
                if m.content or m.content_blocks:
                    # Generate content blocks for subagent response
                    sa_tool_calls = []
                    for tc_ref in (m.tool_calls or []):
                        # Create a minimal ToolCall-like object from the dict
                        class _FakeTC:
                            def __init__(self, d):
                                self.name = d.get("name", d.get("type", "unknown"))
                                self.parameters = d.get("input", {})
                                self.tool_use_id = d.get("id", "")
                                self.subagent_id = ""
                        sa_tool_calls.append(_FakeTC(tc_ref))
                    sa_blocks_html = _render_response_content_blocks(
                        content_blocks=m.content_blocks if m.content_blocks else None,
                        response_text=m.content[:5000] if not m.content_blocks else "",
                        tool_calls=sa_tool_calls if not m.content_blocks else [],
                    )

                    # Build structured response blocks
                    sa_rsp_blocks = []
                    if m.content_blocks:
                        for cb in m.content_blocks:
                            cb_type = cb.get("type", "")
                            if cb_type == "text":
                                sa_rsp_blocks.append({
                                    "type": "text",
                                    "size_label": _format_bytes(min(len(cb.get("content", "")), 10000)),
                                })
                            elif cb_type == "thinking":
                                sa_rsp_blocks.append({
                                    "type": "thinking",
                                    "size_label": _format_bytes(min(len(cb.get("content", "")), 10000)),
                                })
                            elif cb_type == "tool_use":
                                sa_rsp_blocks.append({
                                    "type": "tool_use",
                                    "name": cb.get("name", "unknown")[:40],
                                    "tool_id": cb.get("id", "") or "",
                                })
                    else:
                        if m.content and m.content.strip():
                            sa_rsp_blocks.append({
                                "type": "text",
                                "size_label": _format_bytes(min(len(m.content), 10000)),
                            })
                        for tc in sa_tool_calls:
                            sa_rsp_blocks.append({
                                "type": "tool_use",
                                "name": getattr(tc, "name", "unknown")[:40],
                                "tool_id": getattr(tc, "tool_use_id", "") or "",
                            })

                    block_count = len(sa_rsp_blocks) if sa_rsp_blocks else 1
                    sa_size_label = f"{block_count} content block{'s' if block_count != 1 else ''}"
                    add_payload(
                        payload_id=rsp_payload_id,
                        kind="subagent.response",
                        title=f"Subagent · Response ({call_ref})",
                        html=sa_blocks_html,
                        size=sa_size_label,
                        response_blocks=sa_rsp_blocks,
                        source_status="raw",
                    )
                else:
                    add_payload(
                        payload_id=rsp_payload_id,
                        kind="subagent.response",
                        title=f"Subagent · Response ({call_ref})",
                        text="",
                        warning="Subagent response content not available",
                        source_status="diagnostic",
                    )

                # Dynamic note for subagent LLM step
                if m.request_full:
                    sa_note_text = (m.request_full or "")[:200]
                    sa_note_tone = "info" if len(m.request_full) > 200 else "ok"
                else:
                    sa_note_text = "Subagent LLM call"
                    sa_note_tone = "warn"

                # Inner card title: LLM Call #N (SR title keeps thinking preview)
                sa_inner_title = f"LLM Call #{m_idx + 1}"

                steps = [{
                    "type": "llm_call",
                    "call_id": call_ref,
                    "title": sa_inner_title,
                    "model": (m.model or "unknown")[:40],
                    "status_label": "OK",
                    "status_tone": "ok",
                    "usage": {
                        "input": _format_compact_token(usage.get("input_tokens", 0)),
                        "cache_read": _format_compact_token(usage.get("cache_read_input_tokens", 0)),
                        "cache_write": _format_compact_token(usage.get("cache_creation_input_tokens", 0)),
                        "output": _format_compact_token(usage.get("output_tokens", 0)),
                    },
                    "context_payload_id": ctx_payload_id,
                    "context_payload_title": f"Subagent · Request ({call_ref})",
                    "response_payload_id": rsp_payload_id,
                    "response_payload_title": f"Subagent · Response ({call_ref})",
                    "note": sa_note_text,
                    "note_tone": sa_note_tone,
                    "finish_reason": getattr(m, "stop_reason", "") or "",
                }]

                # Match tool calls belonging to this specific round
                round_tool_tcs = []
                for tc_ref in (m.tool_calls or []):
                    tc_id = tc_ref.get("id", "") if isinstance(tc_ref, dict) else ""
                    if tc_id and tc_id in sa_tool_by_id and tc_id not in matched_tool_ids:
                        round_tool_tcs.append(sa_tool_by_id[tc_id])
                        matched_tool_ids.add(tc_id)

                if round_tool_tcs:
                    round_tool_rows = []
                    for t_idx, tc in enumerate(round_tool_tcs, start=1):
                        t_payload_id = f"sub-{sa_id}-{m_idx + 1}-T{t_idx}-result" if tc.result else ""
                        t_payload_title = f"Subagent · {tc.name} · Result"
                        if tc.result:
                            add_payload(
                                payload_id=t_payload_id,
                                kind="subagent.tool.result",
                                title=t_payload_title,
                                text=tc.result[:5000] if len(tc.result) > 5000 else tc.result,
                                tool_name=tc.name,
                                tool_command=_build_tool_command_summary(tc.name, tc.parameters),
                                tool_parameters=tc.parameters,
                                tool_status=f"exit {tc.exit_code}" if getattr(tc, "exit_code", None) is not None else (getattr(tc, "status", "") or "ok"),
                            )
                        round_tool_rows.append(tool_vm(tc, f"sub-{sa_id}-T{t_idx}", t_payload_id, t_payload_title))

                    steps.append({
                        "type": "tool_batch",
                        "batch_id": f"sub-{sa_id}-R{m_idx + 1}-batch",
                        "title": f"Subagent tool batch ({len(round_tool_rows)} call{'s' if len(round_tool_rows) != 1 else ''})",
                        "summary_label": f"{len(round_tool_rows)} tools",
                        "status_label": "error" if any(t["status_tone"] == "fail" for t in round_tool_rows) else "",
                        "status_tone": "err" if any(t["status_tone"] == "fail" for t in round_tool_rows) else "tool",
                        "tools": round_tool_rows,
                    })
                    is_open_for_round = True
                else:
                    is_open_for_round = False

                # Compute token mix for sub-round tokenbar
                st_input = usage.get("input_tokens", 0)
                st_cache_read = usage.get("cache_read_input_tokens", 0)
                st_cache_write = usage.get("cache_creation_input_tokens", 0)
                st_output = usage.get("output_tokens", 0)
                st_total = st_input + st_cache_read + st_cache_write + st_output
                st_mix = {"fresh": 0, "read": 0, "write": 0, "out": 0}
                if st_total > 0:
                    st_mix["fresh"] = round(st_input / st_total * 100, 1)
                    st_mix["read"] = round(st_cache_read / st_total * 100, 1)
                    st_mix["write"] = round(st_cache_write / st_total * 100, 1)
                    st_mix["out"] = round(st_output / st_total * 100, 1)

                # Check if any tool in this sub-round failed
                sr_has_fail = any(
                    t["status_tone"] == "fail"
                    for s in steps if s["type"] == "tool_batch"
                    for t in s["tools"]
                )

                sub_rounds.append({
                    "sub_round_id": m_idx + 1,
                    "title": (m.content or "")[:80] or "Assistant response",
                    "start_time": _to_local_time_hms(m.timestamp or ""),
                    "metric": _format_compact_token(st_output),
                    "token_input": st_input,
                    "token_cache_read": st_cache_read,
                    "token_cache_write": st_cache_write,
                    "token_output": st_output,
                    "token_total_raw": st_total,
                    "token_mix": st_mix,
                    "status": "error" if sr_has_fail else "ok",
                    "status_label": "fail tool" if sr_has_fail else "ok",
                    "status_tone": "err" if sr_has_fail else "ok",
                    "has_fail": sr_has_fail,
                    "is_open": is_open_for_round,
                    "steps": steps,
                })

        # Handle unmatched tools (fallback: no tool_use_id or not matched to any message)
        unmatched_tools = [tc for tc in display_tools if not tc.tool_use_id or tc.tool_use_id not in matched_tool_ids]
        if unmatched_tools:
            unmatched_rows = []
            for u_idx, tc in enumerate(unmatched_tools, start=1):
                u_payload_id = f"sub-{sa_id}-unmatched-T{u_idx}-result" if tc.result else ""
                u_payload_title = f"Subagent · {tc.name} · Result"
                if tc.result:
                    add_payload(
                        payload_id=u_payload_id,
                        kind="subagent.tool.result",
                        title=u_payload_title,
                        text=tc.result[:5000] if len(tc.result) > 5000 else tc.result,
                        tool_name=tc.name,
                        tool_command=_build_tool_command_summary(tc.name, tc.parameters),
                        tool_parameters=tc.parameters,
                        tool_status=f"exit {tc.exit_code}" if getattr(tc, "exit_code", None) is not None else (getattr(tc, "status", "") or "ok"),
                    )
                unmatched_rows.append(tool_vm(tc, f"sub-{sa_id}-UT{u_idx}", u_payload_id, u_payload_title))

            if sub_rounds:
                sub_rounds[-1]["steps"].append({
                    "type": "tool_batch",
                    "batch_id": f"sub-{sa_id}-unmatched-batch",
                    "title": f"Subagent tool batch ({len(unmatched_rows)} call{'s' if len(unmatched_rows) != 1 else ''})",
                    "summary_label": f"{len(unmatched_rows)} tools",
                    "status_label": "error" if any(t["status_tone"] == "fail" for t in unmatched_rows) else "",
                    "status_tone": "err" if any(t["status_tone"] == "fail" for t in unmatched_rows) else "tool",
                    "tools": unmatched_rows,
                })
                sub_rounds[-1]["is_open"] = True
            else:
                sub_rounds.append({
                    "sub_round_id": 1,
                    "title": f"{len(unmatched_tools)} tool call{'s' if len(unmatched_tools) != 1 else ''}",
                    "metric": _format_compact_token(sa_output),
                    "token_input": 0,
                    "token_cache_read": 0,
                    "token_cache_write": 0,
                    "token_output": sa_output,
                    "token_total_raw": sa_output,
                    "token_mix": {"fresh": 0, "read": 0, "write": 0, "out": 100} if sa_output > 0 else {"fresh": 0, "read": 0, "write": 0, "out": 0},
                    "status": "failed" if sa_failed > 0 else "ok",
                    "status_tone": "err" if sa_failed > 0 else "ok",
                    "is_open": True,
                    "steps": [{
                        "type": "tool_batch",
                        "batch_id": f"sub-{sa_id}-unmatched-batch",
                        "title": f"Subagent tool batch ({len(unmatched_rows)} call{'s' if len(unmatched_rows) != 1 else ''})",
                        "summary_label": f"{len(unmatched_rows)} tools",
                        "status_label": "error" if any(t["status_tone"] == "fail" for t in unmatched_rows) else "",
                        "status_tone": "err" if any(t["status_tone"] == "fail" for t in unmatched_rows) else "tool",
                        "tools": unmatched_rows,
                    }],
                })

        # If no sub-rounds from messages, synthesize from tool calls
        if not sub_rounds and display_tools:
            sub_rounds.append({
                "sub_round_id": 1,
                "title": f"{len(display_tools)} tool call{'s' if len(display_tools) > 1 else ''}",
                "metric": _format_compact_token(sa_output),
                "token_input": 0,
                "token_cache_read": 0,
                "token_cache_write": 0,
                "token_output": sa_output,
                "token_total_raw": sa_output,
                "token_mix": {"fresh": 0, "read": 0, "write": 0, "out": 100} if sa_output > 0 else {"fresh": 0, "read": 0, "write": 0, "out": 0},
                "status": "failed" if sa_failed > 0 else "ok",
                "status_tone": "err" if sa_failed > 0 else "ok",
                "is_open": False,
                "steps": [
                    {
                        "type": "tool_step",
                        "kind": tc.name[:4].upper(),
                        "text": _shorten_path(_build_tool_command_summary(tc.name, tc.parameters))[:80] or tc.name,
                        "result": f"exit {tc.exit_code}" if tc.exit_code is not None else "ok",
                    }
                    for tc in display_tools[:10]
                ],
            })

        subagent_lookup[sa_id] = {
            "name": sa_name,
            "agent_id": sa_id,
            "status_label": "failed" if sa_failed > 0 else "completed",
            "status_tone": "err" if sa_failed > 0 else "ok",
            "meta": f"{len(display_tools)} tools, {_format_compact_token(sa_input + sa_output)} tokens",
            "sub_rounds": sub_rounds,
        }

    # -- Trace rows --
    trace_rows = []
    for r_idx, r in enumerate(rounds):
        rid = r_idx + 1
        rb = r.token_breakdown()
        rt = rb["input"] + rb["cache_read"] + rb["cache_write"] + rb["output"]
        # Classify round status: failed takes priority, then user input, then ok
        has_failed = any(tc.is_failed for tc in r.tool_calls)
        has_llm_err = r.llm_error_count > 0
        has_user_input = bool(r.user_msg.content)

        if has_failed or has_llm_err:
            status_key = "failed"
            status_label = "Failed"
            status_tone = "fail"
        elif has_user_input:
            status_key = "user"
            status_label = "OK"
            status_tone = "ok"
        else:
            status_key = "ok"
            status_label = "OK"
            status_tone = "ok"

        # Round summary: user input first if available
        start_time = _to_local_time_hms(r.user_msg.timestamp or r.assistant_msg.timestamp or "")
        if r.user_msg.content:
            preview_title = (r.user_msg.content or "")[:120]
        else:
            preview_title = (r.preview_text or "")[:120]
        for _fw in ["Map", "Inspector", "Focus", "Open selected", "Calls", "Hotspots", "High token", "Jump input"]:
            preview_title = preview_title.replace(_fw, "***")
        preview_subtitle = f"{len(r.tool_calls)} tool{'s' if len(r.tool_calls) != 1 else ''}" if r.tool_calls else "no tools"

        # token_total = sum of all LLM calls in this round. If interactions
        # are unavailable, fall back to the round's assistant message usage.
        total_input = 0
        total_cache_read = 0
        total_cache_write = 0
        total_output = 0
        for _ix in r.interactions:
            total_input += getattr(_ix, "input_tokens", 0) or 0
            total_cache_read += getattr(_ix, "cache_read_tokens", 0) or 0
            total_cache_write += getattr(_ix, "cache_write_tokens", 0) or 0
            total_output += getattr(_ix, "output_tokens", 0) or 0
        if not r.interactions:
            total_input = rb["input"]
            total_cache_read = rb["cache_read"]
            total_cache_write = rb["cache_write"]
            total_output = rb["output"]
        rt_sum = total_input + total_cache_read + total_cache_write + total_output
        token_total = _format_compact_token(rt_sum) if rt_sum > 0 else "—"

        # tool_count_label = sum of all current-round tool_use/tool calls.
        all_tools = set()
        raw_tool_uses = 0
        for _ix in r.interactions:
            raw_tool_uses += count_raw_tool_uses(_ix)
            for _tc in (getattr(_ix, "tool_calls", []) or []):
                key = getattr(_tc, "tool_use_id", "") or id(_tc)
                all_tools.add(key)
        for tc in r.tool_calls:
            key = getattr(tc, "tool_use_id", "") or id(tc)
            all_tools.add(key)
        tool_total = max(len(all_tools), raw_tool_uses)
        tool_count_label = f"{tool_total} tools" if tool_total else "0 tools"

        token_mix = {"fresh": 0, "read": 0, "write": 0, "out": 0}
        if rt_sum > 0:
            token_mix["fresh"] = round(total_input / rt_sum * 100, 1)
            token_mix["read"] = round(total_cache_read / rt_sum * 100, 1)
            token_mix["write"] = round(total_cache_write / rt_sum * 100, 1)
            token_mix["out"] = round(total_output / rt_sum * 100, 1)

        # Build items for round detail
        items = []

        # 1. User message item (NEW in v11 - highlights user input rounds)
        if r.user_msg.content:
            user_payload_id = f"msg-R{rid}-user"
            add_payload(
                payload_id=user_payload_id,
                kind="message.user",
                title=f"R{rid} · User request",
                text=r.user_msg.content[:5000] if len(r.user_msg.content) > 5000 else r.user_msg.content,
            )
            # Detect language from user message content
            lang_label = ""
            first_line = r.user_msg.content.strip().split("\n")[0] if r.user_msg.content else ""
            if first_line.startswith("```"):
                lang_label = first_line.strip("`").strip()
            items.append({
                "type": "user_message",
                "title": "User Message",
                "text": (r.user_msg.content or "")[:300],
                "language_label": lang_label,
                "payload_id": user_payload_id,
                "payload_title": f"R{rid} · User request",
            })

        for ix_idx, ix in enumerate(r.interactions):
            iix = ix_idx + 1

            # Subagent interaction
            if ix.scope == "subagent" and ix.subagent_id:
                sa_info = subagent_lookup.get(ix.subagent_id)
                if sa_info:
                    items.append({
                        "type": "subagent",
                        "subagent_id": ix.subagent_id,
                        "name": sa_info["name"],
                        "status_label": sa_info["status_label"],
                        "status_tone": sa_info["status_tone"],
                        "meta": sa_info["meta"],
                        "sub_rounds": sa_info["sub_rounds"],
                    })
                continue

            # LLM call interaction
            call_id = f"R{rid}-IX{iix}"
            model_short = (ix.model or "unknown")[:40]
            lane = "main" if ix.scope == "main" else ""

            ix_tools = []
            if hasattr(ix, 'tool_calls') and ix.tool_calls:
                for tc in ix.tool_calls:
                    if not tc.subagent_id:
                        ix_tools.append(tc)

            parallel_batches = []
            if ix_tools:
                batch_tools = []
                for tc in ix_tools:
                    tc_global_idx = -1
                    for gi, gtc in enumerate(r.tool_calls):
                        if gtc is tc:
                            tc_global_idx = gi + 1
                            break
                    if tc_global_idx == -1:
                        tc_global_idx = len(batch_tools) + 1

                    tool_payload_id = f"tool-R{rid}-T{tc_global_idx}" if tc.result else ""
                    if tc.result:
                        add_payload(
                            payload_id=tool_payload_id,
                            kind="tool.result",
                            title=f"R{rid} · {tc.name} · Result",
                            text=tc.result[:5000] if len(tc.result) > 5000 else tc.result,
                            tool_name=tc.name,
                            tool_command=_build_tool_command_summary(tc.name, tc.parameters),
                            tool_parameters=tc.parameters,
                            tool_status=f"exit {tc.exit_code}" if getattr(tc, "exit_code", None) is not None else (getattr(tc, "status", "") or "ok"),
                        )

                    batch_tools.append(tool_vm(
                        tc,
                        f"R{rid}-T{tc_global_idx}",
                        tool_payload_id,
                        f"R{rid} · {tc.name} · Result",
                    ))

                if batch_tools:
                    parallel_batches.append({
                        "type": "tool_batch",
                        "batch_id": f"R{rid}-IX{iix}-batch",
                        "title": f"Tool batch ({len(batch_tools)} call{'s' if len(batch_tools) > 1 else ''})",
                        "summary_label": f"{len(batch_tools)} tools",
                        "status_label": "error" if any(t["status_tone"] == "fail" for t in batch_tools) else "",
                        "status_tone": "err" if any(t["status_tone"] == "fail" for t in batch_tools) else "tool",
                        "tone": "err" if any(t["status_tone"] == "fail" for t in batch_tools) else "tool",
                        "note": "",
                        "tools": batch_tools,
                    })

            usage_input = getattr(ix, "input_tokens", 0) or 0
            usage_cr = getattr(ix, "cache_read_tokens", 0) or 0
            usage_cw = getattr(ix, "cache_write_tokens", 0) or 0
            usage_out = getattr(ix, "output_tokens", 0) or 0

            ix_status_label = "OK"
            ix_status_tone = "ok"
            if any(t["status_tone"] == "fail" for batch in parallel_batches for t in batch["tools"]):
                ix_status_label = "Failed"
                ix_status_tone = "fail"

            # ── Context payload: always created with typed structure ──
            # Contract: relevant user input + all preceding tool results + source status
            context_payload_id = f"llm-R{rid}-IX{iix}-context"
            ix_tool_calls_for_llm = [tc for tc in (getattr(ix, "tool_calls", []) or []) if not getattr(tc, "subagent_id", "")]

            if ix.request_full:
                source_status = "raw"
                ctx_norm_blocks = normalize_llm_content(ix.request_full)
                ctx_content_html = _render_context_content_blocks(ctx_norm_blocks) if ctx_norm_blocks else ""
                add_payload(
                    payload_id=context_payload_id,
                    kind="llm.context",
                    title=f"R{rid} · LLM Call #{iix} · Context",
                    html=ctx_content_html,
                )
            else:
                # Reconstruct context from available data: user input + preceding tool results
                source_status = "reconstructed" if r.user_msg.content else "diagnostic"
                ctx_blocks = []
                if r.user_msg.content:
                    ctx_blocks.append({
                        "kind": "user_input",
                        "summary": (r.user_msg.content or "")[:120],
                    })
                # Preceding tool results: from earlier interactions in this round
                for prev_ix_idx in range(ix_idx):
                    prev_ix = r.interactions[prev_ix_idx]
                    if hasattr(prev_ix, 'tool_calls') and prev_ix.tool_calls:
                        for tc in prev_ix.tool_calls:
                            if not getattr(tc, "subagent_id", ""):
                                tc_result = getattr(tc, "result", "") or ""
                                ctx_blocks.append({
                                    "kind": "tool_result",
                                    "summary": f"{tc.name}: {(tc_result or '')[:80]}",
                                    "status_tone": "fail" if getattr(tc, "is_failed", False) else "ok",
                                })
                # Also include tool results from current interaction's tool_calls
                # (these are the tools that feed the NEXT LLM call, not this one)

                ctx_warning = ""
                if source_status == "diagnostic":
                    ctx_warning = "上下文数据缺失；以下为诊断信息。"
                add_payload(
                    payload_id=context_payload_id,
                    kind="llm.context",
                    title=f"R{rid} · LLM Call #{iix} · Context",
                    text="",
                    warning=ctx_warning,
                    context_blocks=ctx_blocks,
                    source_status=source_status,
                    user_input=(r.user_msg.content or "")[:500] if r.user_msg.content else "",
                    preceding_tool_results=ctx_blocks,
                )

            # ── Response payload: always created with typed structure ──
            # Contract: text blocks + tool_use/tool command blocks + diagnostics
            response_payload_id = f"llm-R{rid}-IX{iix}-output"

            if ix.response_full or ix.content_blocks:
                rsp_source_status = "raw"
                ix_tool_calls_for_response = ix_tool_calls_for_llm
                content_blocks_html = _render_response_content_blocks(
                    content_blocks=ix.content_blocks,
                    response_text=ix.response_full if not ix.content_blocks else "",
                    tool_calls=ix_tool_calls_for_response if not ix.content_blocks else [],
                )

                # Build structured response blocks from content_blocks (preferred) or fallback
                rsp_blocks = []
                if ix.content_blocks:
                    for cb in ix.content_blocks:
                        cb_type = cb.get("type", "")
                        if cb_type == "text":
                            rsp_blocks.append({
                                "type": "text",
                                "size_label": _format_bytes(min(len(cb.get("content", "")), 10000)),
                            })
                        elif cb_type == "thinking":
                            rsp_blocks.append({
                                "type": "thinking",
                                "size_label": _format_bytes(min(len(cb.get("content", "")), 10000)),
                            })
                        elif cb_type == "tool_use":
                            tc_params = cb.get("parameters", {}) or {}
                            tc_command_raw = (tc_params.get("command", "")
                                          or tc_params.get("file_path", "")
                                          or tc_params.get("path", "")
                                          or cb.get("name", "tool"))
                            tc_command = _shorten_path(str(tc_command_raw))[:100]
                            rsp_blocks.append({
                                "type": "tool_use",
                                "name": cb.get("name", "unknown")[:40],
                                "tool_id": cb.get("id", "") or "",
                                "command": tc_command,
                            })
                else:
                    # Fallback to legacy response_text + tool_calls
                    if ix.response_full and ix.response_full.strip():
                        rsp_blocks.append({
                            "type": "text",
                            "size_label": _format_bytes(min(len(ix.response_full), 10000)),
                        })
                    for tc in ix_tool_calls_for_response:
                        tc_params = getattr(tc, "parameters", {}) or {}
                        tc_command_raw = (tc_params.get("command", "")
                                      or tc_params.get("file_path", "")
                                      or tc_params.get("path", "")
                                      or getattr(tc, "name", "tool"))
                        tc_command = _shorten_path(str(tc_command_raw))[:100]
                        rsp_blocks.append({
                            "type": "tool_use",
                            "name": getattr(tc, "name", "unknown")[:40],
                            "tool_id": getattr(tc, "tool_use_id", "") or "",
                            "command": tc_command,
                        })

                block_count = len(rsp_blocks) if rsp_blocks else 1
                size_label = f"{block_count} content block{'s' if block_count != 1 else ''}"

                rsp_diagnostic = ""
                finish_r = getattr(ix, "finish_reason", "") or getattr(ix, "status", "unknown")
                if finish_r and finish_r not in ("end_turn", "stop", "ok", ""):
                    rsp_diagnostic = f"finish_reason: {finish_r}"

                add_payload(
                    payload_id=response_payload_id,
                    kind="llm.output",
                    title=f"R{rid} · LLM Call #{iix} · Response",
                    html=content_blocks_html,
                    size=size_label,
                    response_blocks=rsp_blocks,
                    response_diagnostics=rsp_diagnostic,
                    source_status=rsp_source_status,
                )
            else:
                rsp_source_status = "diagnostic"
                # Build diagnostic response blocks from available tool calls
                rsp_blocks = []
                for tc in ix_tool_calls_for_llm:
                    tc_params = getattr(tc, "parameters", {}) or {}
                    tc_command_raw = (tc_params.get("command", "")
                                  or tc_params.get("file_path", "")
                                  or tc_params.get("path", "")
                                  or getattr(tc, "name", "tool"))
                    tc_command = _shorten_path(str(tc_command_raw))[:100]
                    rsp_blocks.append({
                        "type": "tool_use",
                        "name": getattr(tc, "name", "unknown")[:40],
                        "tool_id": getattr(tc, "tool_use_id", "") or "",
                        "command": tc_command,
                    })

                finish_r = getattr(ix, "finish_reason", "") or getattr(ix, "status", "unknown")
                rsp_diagnostic = f"响应内容缺失；finish_reason: {finish_r}" if finish_r else "响应内容缺失"

                add_payload(
                    payload_id=response_payload_id,
                    kind="llm.output",
                    title=f"R{rid} · LLM Call #{iix} · Response",
                    text="",
                    warning=rsp_diagnostic,
                    response_blocks=rsp_blocks,
                    response_diagnostics=rsp_diagnostic,
                    source_status=rsp_source_status,
                )

            # Dynamic note: replaced hardcoded meaningless text with actionable info
            note_text = ""
            note_tone_val = "ok"
            if ix.request_full:
                req_len = len(ix.request_full)
                if req_len > 10000:
                    note_text = f"上下文已截断（{_format_compact_token(req_len)} 字符），完整内容见 payload"
                    note_tone_val = "info"
                # else: no note needed; context is available
            else:
                note_text = f"上下文为 {source_status}，由用户输入和前置 tool results 重建"
                note_tone_val = "warn" if source_status == "reconstructed" else "err"

            llm_item = {
                "type": "llm_call",
                "call_id": call_id,
                "title": f"LLM Call #{iix}",
                "model": model_short,
                "lane": lane,
                "status_label": ix_status_label,
                "status_tone": ix_status_tone,
                "usage": {
                    "input": _format_compact_token(usage_input) if usage_input else "—",
                    "cache_read": _format_compact_token(usage_cr) if usage_cr else "—",
                    "cache_write": _format_compact_token(usage_cw) if usage_cw else "—",
                    "output": _format_compact_token(usage_out) if usage_out else "—",
                },
                "context_payload_id": context_payload_id,
                "context_payload_title": f"R{rid} · LLM Call #{iix} · Context",
                "response_payload_id": response_payload_id,
                "response_payload_title": f"R{rid} · LLM Call #{iix} · Response",
                "note": note_text,
                "note_tone": note_tone_val,
                "finish_reason": finish_r,
                "timestamp": getattr(ix, "timestamp", ""),
                "tool_call_count": len(ix_tool_calls_for_llm),
                "failed_tool_count": sum(1 for tc in ix_tool_calls_for_llm if getattr(tc, "is_failed", False)),
            }
            items.append(llm_item)
            items.extend(parallel_batches)

        # If no interactions but round has tool_calls, render them standalone
        if not items and r.tool_calls:
            batch_tools = []
            for tc_idx, tc in enumerate(r.tool_calls):
                if tc.subagent_id:
                    sa_info = subagent_lookup.get(tc.subagent_id)
                    if sa_info:
                        items.append({
                            "type": "subagent",
                            "subagent_id": tc.subagent_id,
                            "name": sa_info["name"],
                            "status_label": sa_info["status_label"],
                            "status_tone": sa_info["status_tone"],
                            "meta": sa_info["meta"],
                            "sub_rounds": sa_info["sub_rounds"],
                        })
                    continue
                tool_payload_id = f"tool-R{rid}-T{tc_idx + 1}" if tc.result else ""
                if tc.result:
                    add_payload(
                        payload_id=tool_payload_id,
                        kind="tool.result",
                        title=f"R{rid} · {tc.name} · Result",
                        text=tc.result[:5000] if len(tc.result) > 5000 else tc.result,
                        tool_name=tc.name,
                        tool_command=_build_tool_command_summary(tc.name, tc.parameters),
                        tool_parameters=tc.parameters,
                        tool_status=f"exit {tc.exit_code}" if getattr(tc, "exit_code", None) is not None else (getattr(tc, "status", "") or "ok"),
                    )
                batch_tools.append(tool_vm(
                    tc,
                    f"R{rid}-T{tc_idx + 1}",
                    tool_payload_id,
                    f"R{rid} · {tc.name} · Result",
                ))
            if batch_tools:
                items.append({
                    "type": "tool_batch",
                    "batch_id": f"R{rid}-batch",
                    "title": f"Tool batch ({len(batch_tools)} call{'s' if len(batch_tools) > 1 else ''})",
                    "summary_label": f"{len(batch_tools)} tools",
                    "status_label": "error" if any(t["status_tone"] == "fail" for t in batch_tools) else "",
                    "status_tone": "err" if any(t["status_tone"] == "fail" for t in batch_tools) else "tool",
                    "tone": "err" if any(t["status_tone"] == "fail" for t in batch_tools) else "tool",
                    "note": "",
                    "tools": batch_tools,
                })

        trace_rows.append({
            "round_id": rid,
            "round_label": f"R{rid}",
            "status_key": status_key,
            "status_label": status_label,
            "status_tone": status_tone,
            "preview_title": preview_title or f"Round {rid}",
            "preview_subtitle": preview_subtitle,
            "token_total": token_total,
            "token_total_raw": rt_sum,
            "token_mix": token_mix,
            "token_input": total_input,
            "token_cache_read": total_cache_read,
            "token_cache_write": total_cache_write,
            "token_output": total_output,
            "tool_count": tool_total,
            "tool_count_label": tool_count_label,
            "has_user_input": bool(r.user_msg.content),
            "start_time": start_time,
            "is_open": False,
            "timeline_items": items,
        })

    # ── Summary strip ──
    manual_input_count = sum(1 for r in rounds if r.user_msg and r.user_msg.content)

    subagent_count = 0
    for tr in trace_rows:
        for item in tr.get("timeline_items", []):
            if item.get("type") == "subagent":
                subagent_count += 1

    cache_write_pct = ""
    if total_tokens > 0 and session.cached_output_tokens:
        cache_write_pct = f"{session.cached_output_tokens / total_tokens * 100:.1f}%"

    status_label = "Completed"
    if session_anomalies.anomalies:
        status_label = "Completed with issues"
    if total_failed > 0:
        status_label = "Completed with issues"

    total_llm_calls = sum(r.llm_call_count for r in rounds)

    return {
        "session_summary": {
            "agent_label": agent_name,
            "agent_key": session.agent,
            "title": session.title or "Untitled",
            "model": session.model or "unknown",
            "branch": session.git_branch or "branch main",
            "date": started,
            "short_id": short_id,
            "session_id": session.session_id,
            "project_name": session.project_name if hasattr(session, "project_name") else "",
            "status_label": status_label,
            "manual_input_count": manual_input_count,
            "subagent_count": subagent_count,
            "cache_write_pct": cache_write_pct,
        },
        "hero_metrics": {
            "tokens": _format_compact_token(total_tokens),
            "rounds": str(total_rounds),
            "tools": str(total_tools),
            "failed": str(total_failed) if total_failed > 0 else "0",
            "llm_calls": str(total_llm_calls),
        },
        "issue_links": issue_links,
        "trace_rows": trace_rows,
        "payload_sources": payload_sources,
    }


def _build_v9_view_model(
    session,
    rounds: list,
    llm_calls: list,
    tool_calls: list,
    subagent_runs: list,
    session_anomalies,
) -> dict:
    """Build the v9 timeline view model for session.html template.

    Returns dict with: session_summary, hero_metrics, issue_links, trace_rows, payload_index.
    """
    agent_name = "Claude" if session.agent == "claude_code" else "Qoder" if session.agent == "qoder" else "Codex"
    short_id = session.session_id[-8:] if session.session_id else ""
    started = session.started_at[:10] if session.started_at else "—"

    total_tokens = session.input_tokens + session.output_tokens + session.cached_input_tokens + session.cached_output_tokens
    total_rounds = len(rounds)
    total_tools = sum(len(r.tool_calls) for r in rounds)
    total_failed = session.failed_tool_count or 0
    total_llm_calls = sum(r.llm_call_count for r in rounds)

    # ── Issue links ──
    issue_links = []
    for r_idx, r in enumerate(rounds):
        failed = [tc for tc in r.tool_calls if tc.is_failed]
        if failed or r.llm_error_count > 0:
            parts = []
            if failed:
                parts.append(f"{len(failed)} failed")
            if r.llm_error_count > 0:
                parts.append(f"{r.llm_error_count} llm err")
            issue_links.append({
                "round_id": r_idx + 1,
                "label": f"R{r_idx + 1} · {', '.join(parts)}",
                "tone": "err",
            })
    # Limit to 4
    issue_links = issue_links[:4]

    # ── Payload index ──
    payload_index = {}
    for r_idx, r in enumerate(rounds):
        rid = r_idx + 1
        if r.user_msg.content:
            payload_index[f"msg-R{rid}-user"] = {
                "type": "message.user",
                "title": f"R{rid} · User request",
                "rendered": r.user_msg.content,
                "raw": "",
                "missing_reason": "",
            }
            payload_index[f"msg-R{rid}-user-raw"] = {
                "type": "message.user.raw",
                "title": f"R{rid} · User request · Raw",
                "rendered": r.user_msg.content,
                "raw": r.user_msg.content,
                "missing_reason": "",
            }
        if r.assistant_msg.content:
            payload_index[f"msg-R{rid}-assistant"] = {
                "type": "message.assistant",
                "title": f"R{rid} · Assistant response",
                "rendered": r.assistant_msg.content,
                "raw": "",
                "missing_reason": "",
            }
            payload_index[f"msg-R{rid}-assistant-raw"] = {
                "type": "message.assistant.raw",
                "title": f"R{rid} · Assistant response · Raw",
                "rendered": r.assistant_msg.content,
                "raw": r.assistant_msg.content,
                "missing_reason": "",
            }
        for ix_idx, ix in enumerate(r.interactions):
            iix = ix_idx + 1
            if ix.request_full:
                payload_index[f"llm-R{rid}-IX{iix}-context"] = {
                    "type": "llm.context",
                    "title": f"R{rid} · LLM Call #{iix} · Context",
                    "rendered": ix.request_full,
                    "raw": "",
                    "missing_reason": "",
                }
            if ix.response_full:
                payload_index[f"llm-R{rid}-IX{iix}-output"] = {
                    "type": "llm.output",
                    "title": f"R{rid} · LLM Call #{iix} · Output",
                    "rendered": ix.response_full,
                    "raw": "",
                    "missing_reason": "",
                }
            raw_val = getattr(ix, "request_payload_raw", "") or getattr(ix, "response_payload_raw", "")
            if raw_val:
                payload_index[f"llm-R{rid}-IX{iix}-raw"] = {
                    "type": "llm.raw",
                    "title": f"R{rid} · LLM Call #{iix} · Raw",
                    "rendered": raw_val,
                    "raw": raw_val,
                    "missing_reason": "",
                }
            else:
                missing = getattr(ix, "request_payload_missing_reason", "") or "Raw payload not captured by source log"
                payload_index[f"llm-R{rid}-IX{iix}-raw"] = {
                    "type": "llm.raw",
                    "title": f"R{rid} · LLM Call #{iix} · Raw",
                    "rendered": "",
                    "raw": "",
                    "missing_reason": missing,
                }
        for tc_idx, tc in enumerate(r.tool_calls):
            tid = tc_idx + 1
            if tc.result:
                payload_index[f"tool-R{rid}-T{tid}"] = {
                    "type": "tool.result",
                    "title": f"R{rid} · {tc.name} · Result",
                    "rendered": tc.result[:2000] if len(tc.result) > 2000 else tc.result,
                    "raw": tc.result,
                    "missing_reason": "",
                }

    # ── Build subagent lookup: group subagent tool_calls by subagent_id ──
    subagent_lookup = {}
    for run in subagent_runs:
        sa_id = run["summary"]["agent_id"]
        sa_name = run["summary"].get("agent_type", "subagent")
        sa_tools = [tc for tc in tool_calls if tc.subagent_id == sa_id]
        sa_messages = run.get("messages", [])
        sa_input = sum((m.usage or {}).get("input_tokens", 0) for m in sa_messages)
        sa_output = sum((m.usage or {}).get("output_tokens", 0) for m in sa_messages)
        sa_failed = sum(1 for tc in sa_tools if tc.is_failed)

        # Build sub-rounds from subagent messages
        sub_rounds = []
        for m_idx, m in enumerate(sa_messages):
            if m.role == "assistant":
                usage = m.usage or {}
                call_ref = m.llm_call_id or f"sub-{sa_id}-{m_idx + 1}"
                ctx_payload_id = f"sub-{sa_id}-{m_idx + 1}-ctx"
                rsp_payload_id = f"sub-{sa_id}-{m_idx + 1}-rsp"

                # Register payload sources for subagent LLM call
                if m.request_full:
                    payload_index[ctx_payload_id] = {
                        "type": "subagent.request",
                        "title": f"Subagent · Request ({call_ref})",
                        "rendered": m.request_full[:5000],
                        "raw": m.request_full,
                        "missing_reason": "",
                    }
                if m.content:
                    payload_index[rsp_payload_id] = {
                        "type": "subagent.response",
                        "title": f"Subagent · Response ({call_ref})",
                        "rendered": m.content[:5000],
                        "raw": m.content,
                        "missing_reason": "",
                    }

                # Dynamic note for subagent LLM step (second pass)
                if m.request_full:
                    sa_note_text = (m.request_full or "")[:200]
                    sa_note_tone = "info" if len(m.request_full) > 200 else "ok"
                else:
                    sa_note_text = "Subagent LLM call"
                    sa_note_tone = "warn"

                # Inner card title: LLM Call #N (SR title keeps thinking preview)
                sa_inner_title = f"LLM Call #{m_idx + 1}"

                steps = [{
                    "type": "llm_call",
                    "call_id": call_ref,
                    "title": sa_inner_title,
                    "model": (m.model or "unknown")[:40],
                    "status_label": "OK",
                    "status_tone": "ok",
                    "usage": {
                        "input": _format_compact_token(usage.get("input_tokens", 0)),
                        "cache_read": _format_compact_token(usage.get("cache_read_input_tokens", 0)),
                        "cache_write": _format_compact_token(usage.get("cache_creation_input_tokens", 0)),
                        "output": _format_compact_token(usage.get("output_tokens", 0)),
                    },
                    "context_payload_id": ctx_payload_id if m.request_full else "",
                    "context_payload_title": f"Subagent · Request ({call_ref})",
                    "response_payload_id": rsp_payload_id if m.content else "",
                    "response_payload_title": f"Subagent · Response ({call_ref})",
                    "note": sa_note_text,
                    "note_tone": sa_note_tone,
                    "finish_reason": getattr(m, "stop_reason", "") or "",
                }]

                # Check if any tool in this sub-round failed
                sr_has_fail = any(
                    t["status_tone"] == "fail"
                    for s in steps if s["type"] == "tool_batch"
                    for t in s["tools"]
                )

                sub_rounds.append({
                    "sub_round_id": m_idx + 1,
                    "title": (m.content or "")[:80] or "Assistant response",
                    "start_time": _to_local_time_hms(m.timestamp or ""),
                    "metric": _format_compact_token(usage.get("output_tokens", 0)),
                    "status": "error" if sr_has_fail else "ok",
                    "status_label": "fail tool" if sr_has_fail else "ok",
                    "status_tone": "err" if sr_has_fail else "ok",
                    "has_fail": sr_has_fail,
                    "steps": steps,
                })

        # If no sub-rounds from messages, synthesize from tool calls
        if not sub_rounds and sa_tools:
            sub_rounds.append({
                "sub_round_id": 1,
                "title": f"{len(sa_tools)} tool call{'s' if len(sa_tools) > 1 else ''}",
                "metric": _format_compact_token(sa_output),
                "status": "failed" if sa_failed > 0 else "ok",
                "steps": [
                    {
                        "kind": tc.name[:4].upper(),
                        "text": _shorten_path(_build_tool_command_summary(tc.name, tc.parameters))[:80] or tc.name,
                        "result": f"exit {tc.exit_code}" if tc.exit_code is not None else "ok",
                    }
                    for tc in sa_tools[:10]
                ],
            })

        subagent_lookup[sa_id] = {
            "name": sa_name,
            "agent_id": sa_id,
            "status_label": "failed" if sa_failed > 0 else "completed",
            "status_tone": "err" if sa_failed > 0 else "ok",
            "meta": f"{len(sa_tools)} tools, {_format_compact_token(sa_input + sa_output)} tokens",
            "sub_rounds": sub_rounds,
        }

    # ── Trace rows ──
    trace_rows = []
    for r_idx, r in enumerate(rounds):
        rid = r_idx + 1
        rb = r.token_breakdown()
        rt = rb["input"] + rb["cache_read"] + rb["cache_write"] + rb["output"]
        # Classify round status: failed takes priority, then user input, then ok
        has_failed = any(tc.is_failed for tc in r.tool_calls)
        has_llm_err = r.llm_error_count > 0
        has_user_input = bool(r.user_msg.content)

        if has_failed or has_llm_err:
            status_key = "failed"
            status_label = "Failed"
            status_tone = "fail"
        elif has_user_input:
            status_key = "user"
            status_label = "OK"
            status_tone = "ok"
        else:
            status_key = "ok"
            status_label = "OK"
            status_tone = "ok"

        # Preview: user input first if available
        start_time = _to_local_time_hms(r.user_msg.timestamp or r.assistant_msg.timestamp or "")
        if r.user_msg.content:
            preview_title = (r.user_msg.content or "")[:120]
        else:
            preview_title = (r.preview_text or "")[:120]
        # Sanitize preview title to avoid forbidden QA text substrings
        for _fw in ["Map", "Inspector", "Focus", "Open selected", "Calls", "Hotspots", "High token", "Jump input"]:
            preview_title = preview_title.replace(_fw, "***")
        preview_subtitle = f"{len(r.tool_calls)} tool{'s' if len(r.tool_calls) != 1 else ''}" if r.tool_calls else "no tools"

        # token_total = sum of all LLM calls in this round
        total_input = rb["input"]
        total_cache_read = rb["cache_read"]
        total_cache_write = rb["cache_write"]
        total_output = rb["output"]
        for _ix in r.interactions:
            if _ix.scope == "main":
                total_input += getattr(_ix, "input_tokens", 0) or 0
                total_cache_read += getattr(_ix, "cache_read_tokens", 0) or 0
                total_cache_write += getattr(_ix, "cache_write_tokens", 0) or 0
                total_output += getattr(_ix, "output_tokens", 0) or 0
        rt_sum = total_input + total_cache_read + total_cache_write + total_output
        token_total = _format_compact_token(rt_sum) if rt_sum > 0 else "—"

        # tool_count_label = sum of all tool calls across all interactions
        all_tools = set()
        for _ix in r.interactions:
            for _tc in (getattr(_ix, "tool_calls", []) or []):
                if not getattr(_tc, "subagent_id", ""):
                    all_tools.add(id(_tc))
        all_tools.update(id(tc) for tc in r.tool_calls if not getattr(tc, "subagent_id", ""))
        tool_count_label = f"{len(all_tools)} tools" if all_tools else "0 tools"
        tool_total = len(all_tools)

        # Token mix percentages
        token_mix = {"fresh": 0, "read": 0, "write": 0, "out": 0}
        if rt > 0:
            token_mix["fresh"] = round(rb["input"] / rt * 100, 1)
            token_mix["read"] = round(rb["cache_read"] / rt * 100, 1)
            token_mix["write"] = round(rb["cache_write"] / rt * 100, 1)
            token_mix["out"] = round(rb["output"] / rt * 100, 1)

        # Build items for round detail
        items = []

        for ix_idx, ix in enumerate(r.interactions):
            iix = ix_idx + 1

            # Subagent interaction
            if ix.scope == "subagent" and ix.subagent_id:
                sa_info = subagent_lookup.get(ix.subagent_id)
                if sa_info:
                    items.append({
                        "type": "subagent",
                        "subagent_id": ix.subagent_id,
                        "name": sa_info["name"],
                        "status_label": sa_info["status_label"],
                        "status_tone": sa_info["status_tone"],
                        "meta": sa_info["meta"],
                        "sub_rounds": sa_info["sub_rounds"],
                    })
                continue

            # LLM call interaction
            call_id = f"R{rid}-IX{iix}"
            model_short = (ix.model or "unknown")[:40]
            lane = "main" if ix.scope == "main" else ""

            # Gather tool calls for this interaction
            ix_tools = []
            if hasattr(ix, 'tool_calls') and ix.tool_calls:
                for tc in ix.tool_calls:
                    if not tc.subagent_id:
                        ix_tools.append(tc)

            # Build tool_batch items if there are tools
            parallel_batches = []
            if ix_tools:
                # Group by whether they were dispatched in parallel (all tools from one LLM call are parallel)
                batch_tools = []
                for tc in ix_tools:
                    tc_global_idx = -1
                    for gi, gtc in enumerate(r.tool_calls):
                        if gtc is tc:
                            tc_global_idx = gi + 1
                            break
                    if tc_global_idx == -1:
                        tc_global_idx = len(batch_tools) + 1
                    batch_tools.append({
                        "tool_id": f"R{rid}-T{tc_global_idx}",
                        "kind": tc.name[:4].upper(),
                        "command": _shorten_path(_build_tool_command_summary(tc.name, tc.parameters))[:100],
                        "result_summary": (tc.result or "")[:60] or f"exit {tc.exit_code}" if tc.exit_code is not None else "ok",
                        "exit_label": f"exit {tc.exit_code}" if tc.exit_code is not None else "ok",
                        "status_tone": "fail" if tc.is_failed else ("warn" if (tc.has_nonzero_exit and not tc.is_failed) else "ok"),
                        "payload_id": f"tool-R{rid}-T{tc_global_idx}" if tc.result else "",
                    })

                if batch_tools:
                    parallel_batches.append({
                        "type": "tool_batch",
                        "batch_id": f"R{rid}-IX{iix}-batch",
                        "title": f"Tool batch ({len(batch_tools)} call{'s' if len(batch_tools) > 1 else ''})",
                        "summary_label": f"{len(batch_tools)} tools",
                        "status_label": "error" if any(t["status_tone"] == "fail" for t in batch_tools) else "",
                        "status_tone": "err" if any(t["status_tone"] == "fail" for t in batch_tools) else "tool",
                        "tone": "err" if any(t["status_tone"] == "fail" for t in batch_tools) else "tool",
                        "note": "",
                        "tools": batch_tools,
                    })

            # Usage data
            usage_input = getattr(ix, "input_tokens", 0) or 0
            usage_cr = getattr(ix, "cache_read_tokens", 0) or 0
            usage_cw = getattr(ix, "cache_write_tokens", 0) or 0
            usage_out = getattr(ix, "output_tokens", 0) or 0

            ix_status_label = "OK"
            ix_status_tone = "ok"
            if any(t["status_tone"] == "fail" for batch in parallel_batches for t in batch["tools"]):
                ix_status_label = "Failed"
                ix_status_tone = "fail"

            llm_item = {
                "type": "llm_call",
                "call_id": call_id,
                "title": f"LLM Call #{iix}",
                "model": model_short,
                "lane": lane,
                "status_label": ix_status_label,
                "status_tone": ix_status_tone,
                "usage": {
                    "input": _format_compact_token(usage_input) if usage_input else "—",
                    "cache_read": _format_compact_token(usage_cr) if usage_cr else "—",
                    "cache_write": _format_compact_token(usage_cw) if usage_cw else "—",
                    "output": _format_compact_token(usage_out) if usage_out else "—",
                },
                "context_payload_id": f"llm-R{rid}-IX{iix}-context" if ix.request_full else "",
                "response_payload_id": f"llm-R{rid}-IX{iix}-output" if (ix.response_full or ix.content_blocks) else "",
                "note": "",
            }
            items.append(llm_item)
            items.extend(parallel_batches)

        # If no interactions but round has tool_calls, render them standalone
        if not items and r.tool_calls:
            batch_tools = []
            for tc_idx, tc in enumerate(r.tool_calls):
                if tc.subagent_id:
                    sa_info = subagent_lookup.get(tc.subagent_id)
                    if sa_info:
                        items.append({
                            "type": "subagent",
                            "subagent_id": tc.subagent_id,
                            "name": sa_info["name"],
                            "status_label": sa_info["status_label"],
                            "status_tone": sa_info["status_tone"],
                            "meta": sa_info["meta"],
                            "sub_rounds": sa_info["sub_rounds"],
                        })
                    continue
                batch_tools.append({
                    "tool_id": f"R{rid}-T{tc_idx + 1}",
                    "kind": tc.name[:4].upper(),
                    "command": _shorten_path(tc.parameters.get("command", "") or tc.parameters.get("file_path", "") or tc.name)[:100],
                    "result_summary": (tc.result or "")[:60] or f"exit {tc.exit_code}" if tc.exit_code is not None else "ok",
                    "exit_label": f"exit {tc.exit_code}" if tc.exit_code is not None else "ok",
                    "status_tone": "fail" if tc.is_failed else ("warn" if (tc.has_nonzero_exit and not tc.is_failed) else "ok"),
                    "payload_id": f"tool-R{rid}-T{tc_idx + 1}" if tc.result else "",
                })
            if batch_tools:
                items.append({
                    "type": "tool_batch",
                    "batch_id": f"R{rid}-batch",
                    "title": f"Tool batch ({len(batch_tools)} call{'s' if len(batch_tools) > 1 else ''})",
                    "summary_label": f"{len(batch_tools)} tools",
                    "status_label": "error" if any(t["status_tone"] == "fail" for t in batch_tools) else "",
                    "status_tone": "err" if any(t["status_tone"] == "fail" for t in batch_tools) else "tool",
                    "tone": "err" if any(t["status_tone"] == "fail" for t in batch_tools) else "tool",
                    "note": "",
                    "tools": batch_tools,
                })

        trace_rows.append({
            "round_id": rid,
            "status_key": status_key,
            "status_label": status_label,
            "status_tone": status_tone,
            "preview_title": preview_title or f"Round {rid}",
            "preview_subtitle": preview_subtitle,
            "token_total": token_total,
            "token_total_raw": rt_sum,
            "token_mix": token_mix,
            "token_input": total_input,
            "token_cache_read": total_cache_read,
            "token_cache_write": total_cache_write,
            "token_output": total_output,
            "tool_count": tool_total,
            "tool_count_label": tool_count_label,
            "is_open": False,
            "start_time": start_time,
            "timeline_items": items,
        })

    return {
        "session_summary": {
            "agent_label": agent_name,
            "agent_key": session.agent,
            "title": session.title or "Untitled",
            "model": session.model or "unknown",
            "branch": session.git_branch or "branch main",
            "date": started,
            "short_id": short_id,
        },
        "hero_metrics": {
            "tokens": _format_compact_token(total_tokens),
            "rounds": str(total_rounds),
            "tools": str(total_tools),
            "failed": str(total_failed) if total_failed > 0 else "0",
            "llm_calls": str(total_llm_calls),
        },
        "issue_links": issue_links,
        "trace_rows": trace_rows,
        "payload_index": payload_index,
    }


def create_server(
    host: str = "127.0.0.1",
    port: int = 8899,
) -> HTTPServer:
    """Create and return an HTTPServer instance."""
    server = HTTPServer((host, port), SessionBrowserHandler)
    server.allow_reuse_address = True
    return server
