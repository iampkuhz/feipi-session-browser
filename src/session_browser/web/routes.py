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
from session_browser.attribution.service import (
    build_llm_request_attribution,
    build_llm_response_attribution,
)
from session_browser.attribution.context import (
    build_attribution_session_context,
)
from session_browser.attribution.contracts import (
    LLMRequestAttribution,
    LLMResponseAttribution,
)  # noqa: F401 — contracts referenced by serializers and service layer
from session_browser.attribution.serializers import (
    request_attribution_to_payload,
    response_attribution_to_payload,
    attribution_error_to_payload,
)
from dataclasses import asdict

from session_browser.web.session_detail import (
    _get_cached_session_data,
    _set_cached_session_data,
)
from session_browser.web.session_detail.render_helpers import (
    _build_tool_command_summary,
    _to_local_time_hms,
    _render_response_content_blocks,
    _render_context_content_blocks,
    _html_escape,
)
from session_browser.web.session_detail.payloads import (
    _truncate_payload,
    _build_payload_lookup,
)
from session_browser.web.session_detail.ids import (
    _resolve_qoder_short_id,
)
from session_browser.web.session_detail.url_helpers import (
    build_sessions_url,
    _build_view_actions,
)
from session_browser.web.session_detail.anomalies import (
    compute_bar_scale,
    compute_round_signals,
    _merge_raw_into_db_summary,
)
from session_browser.web.session_detail.view_model import (
    _find_user_message_content,
    _find_tool_result_content,
    _find_assistant_message_content,
    _build_v11_view_model,
)

logger = logging.getLogger("session_browser.web")

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
                if "/attribution/" in path:
                    self._serve_api_attribution_path(path)
                elif "/round/" in path:
                    self._serve_api_round_path(path)
                elif "/bucket-detail/" in path:
                    self._serve_api_bucket_detail_path(path)
                elif "/payload/" in path:
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

        # Try in-memory cache first (avoids re-parsing large JSONL files on
        # every page refresh or round expansion).
        cache_key = f"{agent}:{session_id}"
        cached = _get_cached_session_data(agent, session_id)
        if cached is not None:
            raw_summary = cached["raw_summary"]
            messages = cached["messages"]
            tool_calls = cached["tool_calls"]
            subagent_runs = cached["subagent_runs"]
            logger.debug("Session data cache hit: %s", cache_key)
        else:
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

            # Cache parsed data for subsequent API calls (round lazy-load,
            # payload fetch, attribution).
            _set_cached_session_data(agent, session_id, {
                "raw_summary": raw_summary,
                "messages": messages,
                "tool_calls": tool_calls,
                "subagent_runs": subagent_runs,
            })

        # DB summary is canonical. raw parse only supplements detail; it must
        # NOT overwrite confirmed fields (session_id, project_key, model,
        # assistant_message_count, etc.). Only use raw values when the DB field
        # is empty/null/zero, so that list-page and detail-page round counts
        # stay consistent (SD-14 fix).
        session = _merge_raw_into_db_summary(session, raw_summary)

        # ── Subagent count consistency guard ─────────────────────────
        # The sessions list page reads subagent_instance_count from the DB.
        # The detail page counts len(subagent_runs) from source parsing.
        # If source parsing finds 0 but DB has a non-zero count (e.g. sidechain
        # files moved, parser regression), use the DB count to keep both pages
        # consistent and avoid showing "Subagents 0 runs" in the hero.
        if not subagent_runs and getattr(session, "subagent_instance_count", 0) > 0:
            logger.debug(
                "Source parsed 0 subagent runs but DB has %d; "
                "using DB count for hero display (session=%s)",
                session.subagent_instance_count, cache_key,
            )
            # Synthesize minimal subagent run entries so that
            # _build_v11_view_model produces the correct count.
            for _i in range(session.subagent_instance_count):
                subagent_runs.append({
                    "summary": {
                        "agent_id": f"synthetic-{_i}",
                        "agent_type": "",
                        "description": "",
                        "started_at": "",
                        "ended_at": "",
                    },
                    "messages": [],
                    "tool_calls": [],
                })

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
        llm_calls = build_llm_calls(messages, tool_calls, rounds, subagent_runs, agent)
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
                compute_round_signals(
                    r,
                    i + 1,
                    session.input_tokens + session.cached_input_tokens + session.cached_output_tokens,
                )
            )

        # Set repo root to session's project directory for relative path rendering
        _template_mod._SESSION_REPO_ROOT = _template_mod._get_repo_root(session.project_key) if session.project_key else None

        # Build timeline view model (slim for normal page load, full for MHTML export)
        slim_mode = not export_mhtml
        v11_vm = _build_v11_view_model(session, rounds, llm_calls, tool_calls, subagent_runs, sa, slim=slim_mode)

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
            slim_mode=slim_mode,
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
        llm_calls = build_llm_calls(messages, tool_calls, rounds, subagent_runs, agent)
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

    def _serve_api_attribution_path(self, path: str) -> None:
        """Dispatch /api/sessions/{source}/{session_id}/attribution/{...}.

        Supports two URL patterns:
        - Main LLM call: /api/sessions/{source}/{session_id}/attribution/{round}/{call}/{kind}
        - Subagent LLM call: /api/sessions/{source}/{session_id}/attribution/subagent/{sa_id}/{call_idx}/{kind}
        """
        parts = path.split("/")

        # Detect subagent pattern: parts[5] == "subagent"
        # sub-agent: ["", "api", "sessions", source, session_id, "attribution", "subagent", sa_id, call_idx, kind]
        if len(parts) == 10 and parts[5] == "attribution" and parts[6] == "subagent":
            source = urllib.parse.unquote(parts[3])
            session_id = urllib.parse.unquote(parts[4])
            sa_id = urllib.parse.unquote(parts[7])
            call_idx_str = parts[8]
            kind = urllib.parse.unquote(parts[9])
            if kind not in ("request", "response"):
                self._send_json({"error": f"invalid kind '{kind}', expected 'request' or 'response'"}, status=400)
                return
            try:
                call_idx = int(call_idx_str)
                if call_idx < 1:
                    raise ValueError("must be positive")
            except (ValueError, IndexError):
                self._send_json({
                    "error": f"invalid call_index='{call_idx_str}', must be positive integer",
                }, status=400)
                return
            self._serve_api_attribution_subagent(source, session_id, sa_id, call_idx, kind)
            return

        # Main LLM call pattern: parts: ["", "api", "sessions", source, session_id, "attribution", round_idx, call_idx, kind]
        if len(parts) == 9 and parts[5] == "attribution":
            source = urllib.parse.unquote(parts[3])
            session_id = urllib.parse.unquote(parts[4])
            kind = urllib.parse.unquote(parts[8])
            if kind not in ("request", "response"):
                self._send_json({"error": f"invalid kind '{kind}', expected 'request' or 'response'"}, status=400)
                return
            try:
                round_index = int(parts[6])
                call_index = int(parts[7])
                if round_index < 1 or call_index < 1:
                    raise ValueError("must be positive")
            except (ValueError, IndexError):
                self._send_json({
                    "error": f"invalid round_index='{parts[6]}' or call_index='{parts[7]}', must be positive integers",
                }, status=400)
                return
            self._serve_api_attribution_main(source, session_id, round_index, call_index, kind)
            return

        self._send_json({"error": "invalid API path", "expected": "/api/sessions/{source}/{session_id}/attribution/{round_index}/{call_index}/{kind} or /api/sessions/{source}/{session_id}/attribution/subagent/{sa_id}/{call_idx}/{kind}"}, status=400)

    def _serve_api_attribution_main(self, source: str, session_id: str, round_index: int, call_index: int, kind: str) -> None:
        """Handle attribution for main-agent LLM calls."""
        session, messages, tool_calls, subagent_runs, llm_calls, rounds = \
            self._load_session_and_build_rounds(source, session_id)
        if session is None:
            return  # Error already sent by helper

        target_round_idx = round_index - 1
        target_call_idx = call_index - 1

        if target_round_idx < 0 or target_round_idx >= len(rounds):
            self._send_json(attribution_error_to_payload(
                agent=source, call_id="", round_id=str(round_index),
                error_type="NotFound",
                message=f"round_index {round_index} out of range (1-{len(rounds)})",
            ), status=404)
            return

        r = rounds[target_round_idx]
        if target_call_idx < 0 or target_call_idx >= len(r.interactions):
            self._send_json(attribution_error_to_payload(
                agent=source, call_id="", round_id=str(round_index),
                error_type="NotFound",
                message=f"call_index {call_index} out of range for round {round_index} (1-{len(r.interactions)})",
            ), status=404)
            return

        ix = r.interactions[target_call_idx]
        self._build_and_send_attribution(source, session_id, session, r, ix, target_call_idx, round_index, kind, llm_calls, messages, tool_calls)

    def _serve_api_attribution_subagent(self, source: str, session_id: str, sa_id: str, call_idx: int, kind: str) -> None:
        """Handle attribution for subagent LLM calls."""
        session, messages, tool_calls, subagent_runs, llm_calls, rounds = \
            self._load_session_and_build_rounds(source, session_id)
        if session is None:
            return  # Error already sent by helper

        # Find subagent LLM calls matching sa_id
        sa_llm_calls = [c for c in llm_calls if c.scope == "subagent" and c.subagent_id == sa_id]
        if not sa_llm_calls:
            self._send_json(attribution_error_to_payload(
                agent=source, call_id="", round_id="",
                error_type="NotFound",
                message=f"subagent '{sa_id}' LLM calls not found",
            ), status=404)
            return

        # call_idx is 1-based per-subagent index; find the matching call
        # The per-subagent index maps to position in sa_llm_calls list
        if call_idx < 1 or call_idx > len(sa_llm_calls):
            self._send_json(attribution_error_to_payload(
                agent=source, call_id="", round_id="",
                error_type="NotFound",
                message=f"call_index {call_idx} out of range for subagent '{sa_id}' (1-{len(sa_llm_calls)})",
            ), status=404)
            return

        ix = sa_llm_calls[call_idx - 1]

        # Determine subagent_type from subagent_runs or tool_calls
        subagent_type = None
        for run in subagent_runs:
            if run["summary"]["agent_id"] == sa_id:
                subagent_type = run["summary"].get("agent_type", "") or None
                break
        # Fallback: check parent Agent tool call's subagent_summary
        if not subagent_type:
            for tc in tool_calls:
                if tc.name == "Agent" and tc.subagent_id == sa_id:
                    subagent_type = tc.subagent_summary.get("agent_type", "") or None
                    break

        # Find the parent round for this subagent call
        parent_round_idx = ix.round_index
        if parent_round_idx < 0 or parent_round_idx >= len(rounds):
            parent_round_idx = 0

        r = rounds[parent_round_idx]

        # For subagent, we don't have a meaningful interaction_index within
        # the round's interactions list. Use 0 as a safe default so that
        # preceding_tool_results is empty (subagent calls don't have local
        # preceding tool results in the same way).
        self._build_and_send_attribution(
            source, session_id, session, r, ix, 0,
            parent_round_idx + 1, kind, llm_calls, messages, tool_calls,
            subagent_type=subagent_type,
        )

    def _load_session_and_build_rounds(self, source: str, session_id: str):
        """Load session, parse data, build rounds and LLM calls.

        Uses in-memory cache to avoid re-parsing large JSONL files on every
        API call (round lazy-load, attribution, payload fetch).

        Returns (session, messages, tool_calls, subagent_runs, llm_calls, rounds)
        or (None, ...) on error (error response already sent).
        """
        session_key = f"{source}:{session_id}"
        conn = _get_connection()
        session = get_session(conn, session_key)
        conn.close()

        if session is None:
            if source == "qoder":
                resolved_id, err_msg = _resolve_qoder_short_id(session_id)
                if resolved_id:
                    session_key = f"{source}:{resolved_id}"
                    conn = _get_connection()
                    session = get_session(conn, session_key)
                    conn.close()
                    if session is not None:
                        session_id = resolved_id
                if session is None and err_msg:
                    self._send_json(attribution_error_to_payload(
                        agent=source, call_id="", round_id="",
                        error_type="NotFound", message=err_msg,
                    ), status=404)
                    return (None, [], [], [], [], [])
            if session is None:
                self._send_json(attribution_error_to_payload(
                    agent=source, call_id="", round_id="",
                    error_type="NotFound", message="session not found",
                ), status=404)
                return (None, [], [], [], [], [])

        # Try in-memory cache first
        cached = _get_cached_session_data(source, session_id)
        if cached is not None:
            raw_summary = cached["raw_summary"]
            messages = cached["messages"]
            tool_calls = cached["tool_calls"]
            subagent_runs = cached["subagent_runs"]
            logger.debug("_load_session_and_build_rounds cache hit: %s", session_key)
        else:
            # Parse session detail
            if source == "claude_code":
                from session_browser.sources.claude import parse_session_detail
                raw_summary, messages, tool_calls, subagent_runs = parse_session_detail(
                    session.project_key, session_id
                )
            elif source == "qoder":
                from session_browser.sources.qoder import parse_session_detail
                qoder_file = Path(session.file_path) if session.file_path and Path(session.file_path).exists() else None
                raw_summary, messages, tool_calls, subagent_runs = parse_session_detail(
                    session.project_key, session_id, session_file=qoder_file
                )
            else:
                from session_browser.sources.codex import parse_session_detail
                raw_summary, messages, tool_calls, subagent_runs = parse_session_detail(session_id)

            # Cache for subsequent API calls
            _set_cached_session_data(source, session_id, {
                "raw_summary": raw_summary,
                "messages": messages,
                "tool_calls": tool_calls,
                "subagent_runs": subagent_runs,
            })

        # Build rounds and LLM calls
        rounds = build_rounds(
            messages,
            tool_calls,
            session.input_tokens,
            session.output_tokens,
            session.cached_input_tokens,
            session.cached_output_tokens,
            source,
            md_filter=_md_filter,
        )
        llm_calls = build_llm_calls(messages, tool_calls, rounds, subagent_runs, source)
        assign_interactions_to_rounds(rounds, llm_calls, tool_calls, subagent_runs)

        return (session, messages, tool_calls, subagent_runs, llm_calls, rounds)

    def _serve_api_round_path(self, path: str) -> None:
        """Dispatch /api/sessions/{agent}/{session_id}/round/{round_index}."""
        parts = path.split("/")
        # parts: ["", "api", "sessions", agent, session_id, "round", round_index]
        if len(parts) == 7 and parts[5] == "round":
            try:
                round_index = int(parts[6])
                if round_index < 1:
                    raise ValueError("must be positive")
            except (ValueError, IndexError):
                self._send_json({
                    "error": f"invalid round_index='{parts[6]}', must be a positive integer",
                }, status=400)
                return
            agent = urllib.parse.unquote(parts[3])
            session_id = urllib.parse.unquote(parts[4])
            self._serve_api_round(agent, session_id, round_index)
        else:
            self._send_json({
                "error": "invalid API path",
                "expected": "/api/sessions/{agent}/{session_id}/round/{round_index}",
            }, status=400)

    def _serve_api_round(self, agent: str, session_id: str, round_index: int) -> None:
        """Return the expanded round detail HTML for a given round_index (1-based)."""
        result = self._load_session_and_build_rounds(agent, session_id)
        if result[0] is None:
            return  # Error already sent

        _session, _messages, _tool_calls, _subagent_runs, llm_calls, rounds = result

        # Validate round_index
        target_idx = round_index - 1  # convert to 0-based
        if target_idx < 0 or target_idx >= len(rounds):
            self._send_json({
                "error": f"round_index {round_index} out of range (1-{len(rounds)})",
            }, status=404)
            return

        # Compute preview text for rounds if not already done
        for r in rounds:
            if not getattr(r, "preview_text", ""):
                r.compute_preview()

        # Compute signals for the target round
        r = rounds[target_idx]
        signals = compute_round_signals(
            r, round_index,
            _session.input_tokens + _session.cached_input_tokens + _session.cached_output_tokens,
        )

        # Build view model for just this one round. Use skip_attribution=True
        # because the expanded row HTML only renders timeline items (LLM call
        # cards, tool batches, subagent blocks) — it never uses payload_sources
        # inline. Attribution data is fetched on-demand when the user clicks
        # Request/Response attribution buttons.
        vm = _build_v11_view_model(
            _session, rounds, llm_calls, _tool_calls, _subagent_runs,
            session_anomalies=type("FA", (), {"anomalies": []})(),
            slim=False,
            round_filter={target_idx},
            skip_attribution=True,
        )

        # Find the trace row for the target round
        trace_row = None
        for tr in vm["trace_rows"]:
            if tr["round_id"] == round_index:
                trace_row = tr
                break

        if trace_row is None:
            self._send_json({"error": "round detail not found"}, status=404)
            return

        # Render the expanded row HTML using Jinja template.
        # round_table.html now imports llm_call/subagent with context,
        # so the macro namespace is self-contained and works via template.module.
        template = _template_env.get_template("components/session_detail_timeline.html")
        expanded_html = template.module.expanded_row(trace_row)
        # Strip <tr>/<td> wrapper tags — JS creates its own <tr><td> and injects inner content
        expanded_html = re.sub(r'^<tr[^>]*>\s*<td[^>]*>', '', expanded_html)
        expanded_html = re.sub(r'</td>\s*</tr>\s*$', '', expanded_html)

        self._send_json({
            "html": expanded_html,
            "round_id": round_index,
            "has_user_input": trace_row.get("has_user_input", False),
            "has_subagent": trace_row.get("has_subagent", False),
            "signals": signals,
            "payload_sources": vm.get("payload_sources", []),
        })

    def _build_and_send_attribution(self, source, session_id, session, r, ix, interaction_index, round_index, kind, llm_calls, messages, tool_calls, subagent_type=None):
        """Build attribution for an LLM call and send JSON response."""
        all_messages = messages or []
        all_tool_calls = tool_calls or []

        # Build call-scoped session context with hydration
        attrib_ctx = build_attribution_session_context(
            session=session,
            round_obj=r,
            interaction_index=interaction_index,
            interactions=r.interactions if hasattr(r, 'interactions') else [],
            round_tool_calls=r.tool_calls,
            all_messages=all_messages,
            all_tool_calls=all_tool_calls,
            project_dir=session.project_key or None,
            agent_name=source,
            all_llm_calls=llm_calls,
            subagent_type=subagent_type,
        )

        # Build attribution
        try:
            if kind == "request":
                attr = build_llm_request_attribution(
                    agent=source,
                    llm_call=ix,
                    round_obj=r,
                    session_summary=session,
                    session_context=attrib_ctx,
                )
                data = request_attribution_to_payload(attr)
            else:
                attr = build_llm_response_attribution(
                    agent=source,
                    llm_call=ix,
                    round_obj=r,
                    session_summary=session,
                    session_context=attrib_ctx,
                )
                data = response_attribution_to_payload(attr)
        except Exception as exc:
            logger.debug("Attribution builder exception: %s", exc, exc_info=True)
            self._send_json(attribution_error_to_payload(
                agent=source,
                call_id=ix.id or "",
                round_id=str(round_index),
                error_type=type(exc).__name__,
                message=str(exc)[:200] if str(exc) else "attribution builder failed",
            ), status=500)
            return

        # Return API envelope
        envelope = {
            "kind": f"llm.{kind}_attribution",
            "source": source,
            "session_id": session_id,
            "round_index": round_index,
            "call_index": getattr(ix, "round_index", 0) + 1,
            "data": data,
        }
        self._send_json(envelope)

    def _serve_api_bucket_detail_path(self, path: str) -> None:
        """Dispatch /api/sessions/{source}/{session_id}/bucket-detail/{round_index}/{bucket_key}.

        Supports dynamic loading of bucket detail content:
        - current_user_message: full user message text for a given round
        - local_instruction_context: full CLAUDE.md content for the project
        """
        parts = path.split("/")
        # parts: ["", "api", "sessions", source, session_id, "bucket-detail", round_index, bucket_key]
        if len(parts) == 8 and parts[5] == "bucket-detail":
            source = urllib.parse.unquote(parts[3])
            session_id = urllib.parse.unquote(parts[4])
            round_index_str = parts[6]
            bucket_key = urllib.parse.unquote(parts[7])
            try:
                round_index = int(round_index_str)
            except (ValueError, IndexError):
                self._send_json({"error": f"invalid round_index='{round_index_str}'"}, status=400)
                return
            self._serve_api_bucket_detail(source, session_id, round_index, bucket_key)
        else:
            self._send_json({"error": "invalid API path", "expected": "/api/sessions/{source}/{session_id}/bucket-detail/{round_index}/{bucket_key}"}, status=400)

    def _serve_api_bucket_detail(self, source: str, session_id: str, round_index: int, bucket_key: str) -> None:
        """Return full, untruncated bucket detail content for dynamic loading."""
        session_key = f"{source}:{session_id}"
        conn = _get_connection()
        session = get_session(conn, session_key)
        conn.close()

        if session is None:
            if source == "qoder":
                resolved_id, err_msg = _resolve_qoder_short_id(session_id)
                if resolved_id:
                    session_key = f"{source}:{resolved_id}"
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

        if bucket_key == "current_user_message":
            # Fetch the user message for the given round
            if source == "claude_code":
                from session_browser.sources.claude import parse_session_detail
                raw_summary, messages, tool_calls, subagent_runs = parse_session_detail(
                    session.project_key, session_id
                )
            elif source == "qoder":
                from session_browser.sources.qoder import parse_session_detail
                qoder_file = Path(session.file_path) if session.file_path and Path(session.file_path).exists() else None
                raw_summary, messages, tool_calls, subagent_runs = parse_session_detail(
                    session.project_key, session_id, session_file=qoder_file
                )
            else:
                from session_browser.sources.codex import parse_session_detail
                raw_summary, messages, tool_calls, subagent_runs = parse_session_detail(session_id)

            rounds = build_rounds(
                messages, tool_calls,
                session.input_tokens, session.output_tokens,
                session.cached_input_tokens, session.cached_output_tokens,
                source, md_filter=_md_filter,
            )
            target_idx = round_index - 1
            if target_idx < 0 or target_idx >= len(rounds):
                self._send_json({"error": f"round_index {round_index} out of range (1-{len(rounds)})"}, status=404)
                return

            r = rounds[target_idx]
            content = r.user_msg.content if r.user_msg else ""
            from session_browser.attribution.agents.claude_code import _mask_sensitive_keys
            from session_browser.attribution.token_estimator import estimate_tokens_from_text
            masked = _mask_sensitive_keys(content or "")
            self._send_json({
                "kind": "bucket_detail",
                "bucket_key": bucket_key,
                "round_index": round_index,
                "text": masked,
                "tokens": estimate_tokens_from_text(content or ""),
            })
            return

        elif bucket_key == "local_instruction_context":
            # Read CLAUDE.md from project directory
            project_dir = session.project_key
            if not project_dir:
                self._send_json({"error": "project directory unknown", "text": ""}, status=404)
                return

            from session_browser.attribution.context import _read_local_instructions
            from pathlib import Path as _Path
            local_text = _read_local_instructions(_Path(project_dir), source)

            if not local_text:
                self._send_json({
                    "kind": "bucket_detail",
                    "bucket_key": bucket_key,
                    "text": "",
                    "note": "未检测到本地指令上下文。",
                })
                return

            from session_browser.attribution.agents.claude_code import _mask_sensitive_keys
            from session_browser.attribution.token_estimator import estimate_tokens_from_text
            masked = _mask_sensitive_keys(local_text)
            self._send_json({
                "kind": "bucket_detail",
                "bucket_key": bucket_key,
                "text": masked,
                "tokens": estimate_tokens_from_text(local_text),
                "source_file": "CLAUDE.md",
            })
            return

        elif bucket_key.startswith("full_messages_array_item:"):
            # Fetch a specific message item from the full_messages_array
            try:
                msg_index = int(bucket_key.split(":", 1)[1])
            except (ValueError, IndexError):
                self._send_json({"error": f"invalid message_index in bucket_key '{bucket_key}'"}, status=400)
                return

            if source == "claude_code":
                from session_browser.sources.claude import parse_session_detail
                raw_summary, messages, tool_calls, subagent_runs = parse_session_detail(
                    session.project_key, session_id
                )
            elif source == "qoder":
                from session_browser.sources.qoder import parse_session_detail
                qoder_file = Path(session.file_path) if session.file_path and Path(session.file_path).exists() else None
                raw_summary, messages, tool_calls, subagent_runs = parse_session_detail(
                    session.project_key, session_id, session_file=qoder_file
                )
            else:
                from session_browser.sources.codex import parse_session_detail
                raw_summary, messages, tool_calls, subagent_runs = parse_session_detail(session_id)

            rounds = build_rounds(
                messages, tool_calls,
                session.input_tokens, session.output_tokens,
                session.cached_input_tokens, session.cached_output_tokens,
                source, md_filter=_md_filter,
            )
            llm_calls = build_llm_calls(messages, tool_calls, rounds, subagent_runs, source)
            assign_interactions_to_rounds(rounds, llm_calls, tool_calls, subagent_runs)

            from session_browser.attribution.context import build_attribution_session_context
            from session_browser.attribution.agents.claude_code import _mask_sensitive_keys
            from session_browser.attribution.token_estimator import estimate_tokens_from_text

            # Build full_messages_array for the first interaction of the first round
            # as a representative sample
            target_idx = round_index - 1
            if target_idx < 0 or target_idx >= len(rounds):
                self._send_json({"error": f"round_index {round_index} out of range (1-{len(rounds)})"}, status=404)
                return

            r = rounds[target_idx]
            attrib_ctx = build_attribution_session_context(
                session=session,
                round_obj=r,
                interaction_index=0,
                interactions=r.interactions if hasattr(r, 'interactions') else [],
                round_tool_calls=r.tool_calls,
                all_messages=messages,
                all_tool_calls=tool_calls,
                project_dir=session.project_key or None,
                agent_name=source,
                all_llm_calls=llm_calls,
            )

            msg_array = attrib_ctx.get("full_messages_array", [])
            if msg_index < 0 or msg_index >= len(msg_array):
                self._send_json({
                    "error": f"message_index {msg_index} out of range (0-{len(msg_array) - 1})",
                    "total_messages": len(msg_array),
                }, status=404)
                return

            msg_entry = msg_array[msg_index]
            # For full content, we need to reconstruct from the original messages
            content_text = ""
            if msg_entry.get("content_type") == "user_text":
                content_text = self._find_user_message_content(messages, msg_array, msg_index)
            elif msg_entry.get("content_type") == "tool_result":
                content_text = self._find_tool_result_content(messages, msg_array, msg_index)
            elif msg_entry.get("content_type") == "assistant_text":
                content_text = self._find_assistant_message_content(messages, msg_array, msg_index)

            masked = _mask_sensitive_keys(content_text or "")
            self._send_json({
                "kind": "bucket_detail",
                "bucket_key": "full_messages_array_item",
                "message_index": msg_index,
                "role": msg_entry.get("role", ""),
                "content_type": msg_entry.get("content_type", ""),
                "tool_name": msg_entry.get("tool_name", ""),
                "text": masked,
                "tokens": estimate_tokens_from_text(content_text or ""),
            })
            return

        else:
            self._send_json({"error": f"bucket_key '{bucket_key}' not supported for dynamic loading"}, status=400)

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
            "application/javascript" if filename.endswith(".js") else (
                "image/svg+xml" if filename.endswith(".svg") else "text/plain"
            )
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



def create_server(
    host: str = "127.0.0.1",
    port: int = 8899,
) -> HTTPServer:
    """Create and return an HTTPServer instance."""
    server = HTTPServer((host, port), SessionBrowserHandler)
    server.allow_reuse_address = True
    return server
