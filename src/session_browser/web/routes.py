"""session-browser 的 HTTP server 和路由.

Uses Python's built-in http.server + jinja2 templates.
No external web framework needed for MVP.
"""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.parse
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer
from pathlib import Path

from session_browser.attribution.agents.claude_code_parts.utils import (
    mask_sensitive_keys,
)
from session_browser.attribution.context import (
    _read_local_instructions,
    build_attribution_session_context,
)
from session_browser.attribution.serializers import (
    attribution_error_to_payload,
    request_attribution_to_payload,
    response_attribution_to_payload,
)
from session_browser.attribution.service import (
    build_llm_request_attribution,
    build_llm_response_attribution,
)
from session_browser.attribution.token_estimator import (
    estimate_tokens_from_text,
)
from session_browser.domain.serializers import session_summary_to_dict
from session_browser.index.anomalies import (
    SEVERITY_WARNING,
    Anomaly,
    AnomalyType,
    detect_session_anomalies,
)
from session_browser.index.indexer import (
    _get_connection,
    count_sessions,
    get_session,
)
from session_browser.index.metrics import (
    compute_derived_metrics,
)
from session_browser.sources.claude import parse_session_detail as parse_claude_session_detail
from session_browser.sources.codex_session_source import (
    parse_session_detail as parse_codex_session_detail,
)
from session_browser.sources.qoder import parse_session_detail as parse_qoder_session_detail
from session_browser.web import template_env as _template_mod
from session_browser.web.mhtml import get_context
from session_browser.web.presenters.dashboard import build_dashboard_view_model
from session_browser.web.presenters.projects import (
    build_project_detail_view_model,
    build_projects_view_model,
)
from session_browser.web.presenters.session_detail import (
    assign_interactions_to_rounds,
    build_llm_calls,
    build_rounds,
)
from session_browser.web.presenters.sessions import (
    compute_pagination,
    fetch_sessions_view_model,
    parse_sessions_query_params,
)
from session_browser.web.renderers.markdown import render_markdown as _md_filter
from session_browser.web.session_detail import (
    _get_cached_session_data,
    _set_cached_session_data,
)
from session_browser.web.session_detail.anomalies import (
    _merge_raw_into_db_summary,
    compute_round_signals,
)
from session_browser.web.session_detail.ids import (
    _resolve_qoder_short_id,
)
from session_browser.web.session_detail.payloads import (
    _build_payload_lookup,
)
from session_browser.web.session_detail.preview import build_round_preview
from session_browser.web.session_detail.render_helpers import (
    _build_tool_command_summary,  # noqa: F401 - compatibility re-export for tests/downstream imports.
)
from session_browser.web.session_detail.url_helpers import (
    _build_view_actions,
    build_sessions_url,  # noqa: F401 - compatibility re-export for tests/downstream imports.
)
from session_browser.web.session_detail.view_model import (
    _build_v11_view_model,
)
from session_browser.web.template_env import (
    env as _template_env,
)

logger = logging.getLogger('session_browser.web')

SESSION_PATH_PARTS = 2
API_PAYLOAD_PARTS = 7
API_ATTRIBUTION_SUBAGENT_PARTS = 10
API_ATTRIBUTION_MAIN_PARTS = 9
API_ROUND_PARTS = 7
API_BUCKET_DETAIL_PARTS = 8
ERROR_MESSAGE_MAX_CHARS = 240
ERROR_MESSAGE_PREFIX_CHARS = 237


@dataclass(frozen=True)
class AttributionRequest:
    """Bundle parameters needed to build one attribution API response."""

    source: str
    session_id: str
    session: object
    round_obj: object
    interaction: object
    interaction_index: int
    round_index: int
    kind: str
    llm_calls: list[object]
    messages: list[object]
    tool_calls: list[object]
    subagent_type: str | None = None


class SessionBrowserHandler(BaseHTTPRequestHandler):
    """Serve dashboard, session, static, and JSON API requests.

    The local HTTP server creates one handler per request. The handler keeps no
    durable state beyond the response stream and delegates data loading to the
    index, presenter, and session-detail helpers.
    """

    def do_GET(self) -> None:
        """Route one HTTP GET request to a page, static asset, or JSON API."""
        started_at = time.time()
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        params = urllib.parse.parse_qs(parsed.query)

        try:
            self._dispatch_get_request(path, params)
            elapsed_ms = (time.time() - started_at) * 1000
            logger.debug(
                'HTTP request handled: method=GET path=%s elapsed_ms=%.1f',
                path,
                elapsed_ms,
            )
        except BrokenPipeError:
            # Client closed 该 connection,在之前 we could respond — normal.
            logger.debug('Client disconnected before response: path=%s', path)
        except Exception as exc:
            logger.exception('HTTP request failed: method=GET path=%s query=%s', path, parsed.query)
            self._send_500(exc, request_path=path)

    def _dispatch_get_request(self, path: str, params: dict[str, list[str]]) -> None:
        """Dispatch one parsed GET path to its route handler."""
        exact_routes = {
            '/': self._serve_dashboard,
            '/dashboard': self._serve_dashboard,
            '/projects': self._serve_projects,
            '/sessions': self._serve_all_sessions,
            '/glossary': self._serve_glossary,
        }
        if path == '/favicon.ico':
            self._send_empty(204)
            return
        if path in exact_routes:
            exact_routes[path]()
            return
        if path.startswith('/projects/'):
            project_key = urllib.parse.unquote(path[len('/projects/') :])
            self._serve_project(project_key)
            return
        if path.startswith('/sessions/'):
            self._dispatch_session_path(path, params)
            return
        if path.startswith('/static/'):
            self._serve_static(path[len('/static/') :])
            return
        if path.startswith('/api/sessions/'):
            self._dispatch_api_path(path)
            return
        self._send_404()

    def _dispatch_session_path(self, path: str, params: dict[str, list[str]]) -> None:
        """Dispatch session detail URLs and fallback to the sessions list."""
        path_only = path.split('?', 1)[0]
        export_mhtml = params.get('export') == ['mhtml']
        parts = path_only[len('/sessions/') :].split('/', 1)
        if len(parts) != SESSION_PATH_PARTS:
            self._serve_all_sessions()
            return
        agent, session_id = parts
        self._serve_session(
            urllib.parse.unquote(agent),
            urllib.parse.unquote(session_id),
            export_mhtml=export_mhtml,
        )

    def _dispatch_api_path(self, path: str) -> None:
        """Dispatch session-scoped JSON API paths by URL segment."""
        api_routes = {
            '/attribution/': self._serve_api_attribution_path,
            '/round/': self._serve_api_round_path,
            '/bucket-detail/': self._serve_api_bucket_detail_path,
            '/payload/': self._serve_api_payload_path,
        }
        for marker, handler in api_routes.items():
            if marker in path:
                handler(path)
                return
        self._send_json({'error': 'invalid API path'}, status=400)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        """转发 BaseHTTPRequestHandler access logs through configured logging.

        Args:
            format: Access log printf-style format provided by the base class.
            *args: Values interpolated into ``format`` by the base class.
        """
        logger.info(
            'HTTP access: client=%s message=%s',
            self.client_address[0] if self.client_address else '-',
            format % args,
        )

    def log_error(self, format: str, *args: object) -> None:  # noqa: A002
        """转发 BaseHTTPRequestHandler error logs through configured logging.

        Args:
            format: Error log printf-style format provided by the base class.
            *args: Values interpolated into ``format`` by the base class.
        """
        logger.error(
            'HTTP handler error: client=%s message=%s',
            self.client_address[0] if self.client_address else '-',
            format % args,
        )

    def _render_template(self, name: str, **context: object) -> str:
        """Render one Jinja template for a route response.

        Args:
            name: Template name relative to the configured template directory.
            **context: Template variables assembled by the route handler.

        Returns:
            Rendered HTML text.
        """
        template = _template_env.get_template(name)
        return template.render(**context)

    def _send_html(self, html: str, status: int = 200) -> None:
        """Write an HTML response to the current request stream.

        Args:
            html: Rendered HTML body encoded as UTF-8 for the client.
            status: HTTP status code to send with the response.
        """
        self.send_response(status)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html.encode('utf-8'))

    def _send_empty(self, status: int = 204) -> None:
        """Write an empty response with the requested status.

        Args:
            status: HTTP status code for no-body responses such as favicon.
        """
        self.send_response(status)
        self.end_headers()

    def _send_404(self) -> None:
        """Render and send the shared 404 page for the active request."""
        self._send_html(self._render_template('404.html'), 404)

    def _send_500(self, error: Exception, *, request_path: str) -> None:
        """Render a sanitized 500 page for unexpected route failures.

        Args:
            error: Exception raised while handling the request.
            request_path: URL path being handled when the failure occurred.
        """
        logger.error('Rendering 500 response: %s', error)
        details = {
            'error_type': type(error).__name__,
            'request_path': request_path,
            'request_id': uuid.uuid4().hex[:12],
            'timestamp': datetime.now(timezone.utc)
            .isoformat(timespec='seconds')
            .replace('+00:00', 'Z'),
            'message_summary': self._summarize_error_message(error),
        }
        self._send_html(
            self._render_template('error.html', error_details=details, request_path=request_path),
            500,
        )

    @staticmethod
    def _summarize_error_message(error: Exception) -> str:
        """Create a short, redacted error string safe for browser display.

        Args:
            error: Exception whose message should be shown on the error page.

        Returns:
            Redacted single-line summary capped to the UI display limit.
        """
        message = str(error) or type(error).__name__
        message = re.sub(r"/Users/[^\s'\"<>]+", '[path]', message)
        message = re.sub(r'/(?:[A-Za-z0-9._-]+/){2,}[A-Za-z0-9._-]+', '[path]', message)
        message = re.sub(
            r'(?i)(token|secret|api[_-]?key|password)=([^\s&]+)', r'\1=[redacted]', message
        )
        message = re.sub(r'\s+', ' ', message).strip()
        if len(message) > ERROR_MESSAGE_MAX_CHARS:
            return message[:ERROR_MESSAGE_PREFIX_CHARS].rstrip() + '...'
        return message

    def _send_json(self, data: dict, status: int = 200) -> None:
        """Serialize and send one JSON API response.

        Args:
            data: JSON-serializable response envelope or error payload.
            status: HTTP status code to send with the JSON body.
        """
        body = json.dumps(data, ensure_ascii=False, default=str)
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.end_headers()
        self.wfile.write(body.encode('utf-8'))

    def _serve_dashboard(self) -> None:
        """Render the dashboard page from query parameters and index metrics."""
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        agent_scope = params.get('agent', ['all'])[0]
        grain = params.get('grain', ['day'])[0]
        page_param = params.get('page', [None])[0]
        page = int(page_param) if page_param and page_param.isdigit() else None

        conn = _get_connection()
        view_model = build_dashboard_view_model(
            conn,
            agent_scope=agent_scope,
            grain=grain,
            page=page,
        )
        conn.close()

        html = self._render_template('dashboard.html', **view_model)
        self._send_html(html)

    def _serve_projects(self) -> None:
        """Render the projects listing page from query filters."""
        parsed = urllib.parse.urlparse(self.path)
        raw_params = urllib.parse.parse_qs(parsed.query)

        conn = _get_connection()
        view_model = build_projects_view_model(raw_params, conn)
        conn.close()

        html = self._render_template('projects.html', **view_model)
        self._send_html(html)

    def _serve_project(self, project_key: str) -> None:
        """Render one project detail page.

        Args:
            project_key: Project identifier decoded from the route path.
        """
        parsed = urllib.parse.urlparse(self.path)
        raw_params = urllib.parse.parse_qs(parsed.query)

        conn = _get_connection()
        view_model = build_project_detail_view_model(conn, project_key, raw_params)
        conn.close()

        html = self._render_template('project.html', **view_model)
        self._send_html(html)

    def _serve_session(self, agent: str, session_id: str, export_mhtml: bool = False) -> None:  # noqa: PLR0912, PLR0915 - session page composes fixed legacy view sections
        """Render a session detail page or self-contained MHTML export.

        Args:
            agent: Source agent namespace from the session URL.
            session_id: Session identifier decoded from the route path.
            export_mhtml: Whether to inline static assets for export.
        """
        session_key = f'{agent}:{session_id}'
        conn = _get_connection()
        session = get_session(conn, session_key)
        conn.close()

        if session is None:
            # Qoder URL 可能只带短 ID;先解析为 canonical UUID 再查 DB.
            if agent == 'qoder':
                resolved_id, err_msg = _resolve_qoder_short_id(session_id)
                if resolved_id:
                    session_key = f'{agent}:{resolved_id}'
                    conn = _get_connection()
                    session = get_session(conn, session_key)
                    conn.close()
                    if session is not None:
                        session_id = resolved_id
                if session is None and err_msg:
                    self._send_json({'error': err_msg}, status=404)
                    return
            if session is None:
                self._send_404()
                return

        # 优先使用内存缓存,避免页面刷新、round 展开和 attribution 请求重复解析大 JSONL.
        cache_key = f'{agent}:{session_id}'
        cached = _get_cached_session_data(agent, session_id)
        if cached is not None:
            raw_summary = cached['raw_summary']
            messages = cached['messages']
            tool_calls = cached['tool_calls']
            subagent_runs = cached['subagent_runs']
            logger.debug('Session data cache hit: %s', cache_key)
        else:
            # 缓存未命中时才从各 agent source 读取原始会话详情.
            if agent == 'claude_code':
                raw_summary, messages, tool_calls, subagent_runs = parse_claude_session_detail(
                    session.project_key, session_id
                )
            elif agent == 'qoder':
                # Qoder 优先使用 DB 记录的文件路径;缺失或失效时再走搜索兜底.
                qoder_file = (
                    Path(session.file_path)
                    if session.file_path and Path(session.file_path).exists()
                    else None
                )
                raw_summary, messages, tool_calls, subagent_runs = parse_qoder_session_detail(
                    session.project_key, session_id, session_file=qoder_file
                )
            else:
                raw_summary, messages, tool_calls, subagent_runs = parse_codex_session_detail(
                    session_id
                )

            # 同一次会话详情页后续会 lazy-load round、payload 和 attribution,共享解析结果.
            _set_cached_session_data(
                agent,
                session_id,
                {
                    'raw_summary': raw_summary,
                    'messages': messages,
                    'tool_calls': tool_calls,
                    'subagent_runs': subagent_runs,
                },
            )

        # DB summary 是列表页和详情页的一致性基准;raw parse 只能补齐空字段,
        # 不覆盖已确认的 session_id、project_key、model、round count 等信息.
        session = _merge_raw_into_db_summary(session, raw_summary)

        # ── Subagent count 一致性保护 ─────────────────────────
        # 列表页读取 DB 中的 subagent_instance_count,详情页通常读取 source 解析出的
        # subagent_runs.若 sidechain 文件移动或 parser 回归导致解析结果为空,则以 DB
        # 计数兜底,避免同一会话在 hero 中显示为 "Subagents 0 runs".
        if not subagent_runs and getattr(session, 'subagent_instance_count', 0) > 0:
            logger.debug(
                'Source parsed 0 subagent runs but DB has %d; '
                'using DB count for hero display (session=%s)',
                session.subagent_instance_count,
                cache_key,
            )
            # 只合成最小 summary,让 ViewModel 维持正确计数;不伪造消息或工具调用.
            for _i in range(session.subagent_instance_count):
                subagent_runs.append(
                    {
                        'summary': {
                            'agent_id': f'synthetic-{_i}',
                            'agent_type': '',
                            'description': '',
                            'started_at': '',
                            'ended_at': '',
                        },
                        'messages': [],
                        'tool_calls': [],
                    }
                )

        # 构建带 token 数据和 Markdown 渲染结果的 conversation rounds.
        rounds = build_rounds(
            messages,
            tool_calls,
            session.fresh_input_tokens,
            session.output_tokens,
            session.cache_read_tokens,
            session.cache_write_tokens,
            agent,
            md_filter=_md_filter,
        )

        # 先构建 LLM calls,再把工具调用和 subagent 交互分配回对应 round.
        llm_calls = build_llm_calls(messages, tool_calls, rounds, subagent_runs, agent)
        assign_interactions_to_rounds(rounds, llm_calls, tool_calls, subagent_runs)

        # 派生指标基于合并后的 session summary,保持与列表页口径一致.
        session_data = compute_derived_metrics(session_summary_to_dict(session))

        # anomaly 检测使用页面最终展示口径,避免 raw parse 和 DB summary 双轨.
        sa = detect_session_anomalies(session_data)

        # payload 可见性异常只在存在输入 token 且所有 call 都缺少 request/response
        # 可见内容时触发,避免单个 call 缺字段造成误报.
        has_input = session.fresh_input_tokens > 0
        has_any_request = any(c.request_full for c in llm_calls) if llm_calls else False
        has_any_response = any(c.response_full for c in llm_calls) if llm_calls else False
        if has_input and not has_any_request and not has_any_response:
            sa.anomalies.append(
                Anomaly(
                    type=AnomalyType.PAYLOAD_VISIBILITY_MISMATCH,
                    severity=SEVERITY_WARNING,
                    label='Payload visibility mismatch',
                    reason=(
                        'Session has input tokens, but no LLM call has request/response '
                        'payload data.'
                    ),
                )
            )

        # 计算 signals,用于 each round,在之后 interactions are assigned
        round_signals = []
        for i, r in enumerate(rounds):
            round_signals.append(
                compute_round_signals(
                    r,
                    i + 1,
                    session.fresh_input_tokens
                    + session.cache_read_tokens
                    + session.cache_write_tokens,
                )
            )

        # Set repo root to session's project directory,用于 relative path rendering
        _template_mod._SESSION_REPO_ROOT = (
            _template_mod._get_repo_root(session.project_key) if session.project_key else None
        )

        # 构建 timeline view model (slim,用于 normal page load, full,用于 MHTML export)
        slim_mode = not export_mhtml
        v11_vm = _build_v11_view_model(
            session, rounds, llm_calls, tool_calls, subagent_runs, sa, slim=slim_mode
        )

        # 说明:MHTML context
        if export_mhtml:
            logger.info('MHTML export: agent=%s session_id=%s', agent, session_id)
            mhtml_ctx = get_context(page='session', export_mhtml=True)
        else:
            mhtml_ctx = {}

        html = self._render_template(
            'session.html',
            session=session,
            session_data=session_data,
            rounds=rounds,
            round_signals=round_signals,
            tool_calls=tool_calls,
            llm_calls=llm_calls,
            current_agent=agent,
            session_anomalies=sa,
            active_page='session',
            session_url=(
                f'/sessions/{urllib.parse.quote(agent, safe="")}/'
                f'{urllib.parse.quote(session_id, safe="")}'
            ),
            slim_mode=slim_mode,
            session_rounds=[
                {
                    'idx': i + 1,
                    'name': build_round_preview(r)['preview_text'] or f'Round {i + 1}',
                    'status': getattr(r, 'status', ''),
                    'is_current': False,
                }
                for i, r in enumerate(rounds)
            ],
            **v11_vm,
            **mhtml_ctx,
        )
        self._send_html(html)

    def _serve_api_payload_path(self, path: str) -> None:
        """分发 payload API route to the payload JSON handler.

        Args:
            path: Request path matching
                ``/api/sessions/{agent}/{session_id}/payload/{payload_id}``.
        """
        parts = path.split('/')
        # 说明:parts: ["", "api", "sessions", agent, session_id, "payload", payload_id]
        if len(parts) == API_PAYLOAD_PARTS and parts[5] == 'payload':
            agent = urllib.parse.unquote(parts[3])
            session_id = urllib.parse.unquote(parts[4])
            payload_id = urllib.parse.unquote(parts[6])
            self._serve_api_payload(agent, session_id, payload_id)
        else:
            self._send_json(
                {
                    'error': 'invalid API path',
                    'expected': '/api/sessions/{agent}/{session_id}/payload/{payload_id}',
                },
                status=400,
            )

    def _serve_api_payload(self, agent: str, session_id: str, payload_id: str) -> None:
        """返回 the full, untruncated payload for one session payload id.

        Args:
            agent: Source agent namespace for the session.
            session_id: Session identifier from the API route.
            payload_id: Payload key generated by the session detail view model.
        """
        session_key = f'{agent}:{session_id}'
        conn = _get_connection()
        session = get_session(conn, session_key)
        conn.close()

        if session is None:
            # 说明:For qoder, try resolving short ID -> canonical full UUID
            if agent == 'qoder':
                resolved_id, err_msg = _resolve_qoder_short_id(session_id)
                if resolved_id:
                    session_key = f'{agent}:{resolved_id}'
                    conn = _get_connection()
                    session = get_session(conn, session_key)
                    conn.close()
                    if session is not None:
                        session_id = resolved_id
                if session is None and err_msg:
                    self._send_json({'error': err_msg}, status=404)
                    return
            if session is None:
                self._send_json({'error': 'session not found'}, status=404)
                return

        # 解析 session detail using 该 same agent-specific logic as _serve_session
        if agent == 'claude_code':
            _raw_summary, messages, tool_calls, subagent_runs = parse_claude_session_detail(
                session.project_key, session_id
            )
        elif agent == 'qoder':
            # 优先使用 DB file_path; fallback to search,如果 missing/invalid
            qoder_file = (
                Path(session.file_path)
                if session.file_path and Path(session.file_path).exists()
                else None
            )
            _raw_summary, messages, tool_calls, subagent_runs = parse_qoder_session_detail(
                session.project_key, session_id, session_file=qoder_file
            )
        else:
            _raw_summary, messages, tool_calls, subagent_runs = parse_codex_session_detail(
                session_id
            )

        # 构建 conversation rounds (same as _serve_session)
        rounds = build_rounds(
            messages,
            tool_calls,
            session.fresh_input_tokens,
            session.output_tokens,
            session.cache_read_tokens,
            session.cache_write_tokens,
            agent,
            md_filter=_md_filter,
        )

        # 构建 LLM calls 和 assign interactions to rounds
        llm_calls = build_llm_calls(messages, tool_calls, rounds, subagent_runs, agent)
        assign_interactions_to_rounds(rounds, llm_calls, tool_calls, subagent_runs)

        # 构建 payload lookup,使用 NO truncation
        payload_map = _build_payload_lookup(rounds, tool_calls, subagent_runs, truncate=False)

        payload = payload_map.get(payload_id)
        if not payload:
            self._send_json(
                {
                    'error': f'payload {payload_id} not found',
                    'available_keys': list(payload_map.keys())[:10],
                },
                status=404,
            )
            return

        self._send_json(payload)

    def _serve_api_attribution_path(self, path: str) -> None:
        """分发 attribution API route to main-agent or subagent handlers.

        Supports two URL patterns:
        - Main LLM call: /api/sessions/{source}/{session_id}/attribution/{round}/{call}/{kind}
        - Subagent LLM call:
          /api/sessions/{source}/{session_id}/attribution/subagent/{sa_id}/{call_idx}/{kind}

        Args:
            path: Request path containing the attribution route segments.

        Raises:
            ValueError: Raised and caught locally when numeric route segments
                are not positive integers.
        """
        parts = path.split('/')

        # 说明:Detect subagent pattern: parts[5] == "subagent"
        # sub-agent:
        # ["", "api", "sessions", source, session_id, "attribution", "subagent", ...]
        if (
            len(parts) == API_ATTRIBUTION_SUBAGENT_PARTS
            and parts[5] == 'attribution'
            and parts[6] == 'subagent'
        ):
            source = urllib.parse.unquote(parts[3])
            session_id = urllib.parse.unquote(parts[4])
            sa_id = urllib.parse.unquote(parts[7])
            call_idx_str = parts[8]
            kind = urllib.parse.unquote(parts[9])
            if kind not in ('request', 'response'):
                self._send_json(
                    {'error': f"invalid kind '{kind}', expected 'request' or 'response'"},
                    status=400,
                )
                return
            try:
                call_idx = int(call_idx_str)
                if call_idx < 1:
                    raise ValueError('must be positive')
            except (ValueError, IndexError):
                self._send_json(
                    {
                        'error': f"invalid call_index='{call_idx_str}', must be positive integer",
                    },
                    status=400,
                )
                return
            self._serve_api_attribution_subagent(source, session_id, sa_id, call_idx, kind)
            return

        # Main LLM call pattern:
        # ["", "api", "sessions", source, session_id, "attribution", round_idx, ...]
        if len(parts) == API_ATTRIBUTION_MAIN_PARTS and parts[5] == 'attribution':
            source = urllib.parse.unquote(parts[3])
            session_id = urllib.parse.unquote(parts[4])
            kind = urllib.parse.unquote(parts[8])
            if kind not in ('request', 'response'):
                self._send_json(
                    {'error': f"invalid kind '{kind}', expected 'request' or 'response'"},
                    status=400,
                )
                return
            try:
                round_index = int(parts[6])
                call_index = int(parts[7])
                if round_index < 1 or call_index < 1:
                    raise ValueError('must be positive')
            except (ValueError, IndexError):
                self._send_json(
                    {
                        'error': (
                            f"invalid round_index='{parts[6]}' or call_index='{parts[7]}', "
                            'must be positive integers'
                        ),
                    },
                    status=400,
                )
                return
            self._serve_api_attribution_main(source, session_id, round_index, call_index, kind)
            return

        self._send_json(
            {
                'error': 'invalid API path',
                'expected': (
                    '/api/sessions/{source}/{session_id}/attribution/'
                    '{round_index}/{call_index}/{kind} or /api/sessions/{source}/'
                    '{session_id}/attribution/subagent/{sa_id}/{call_idx}/{kind}'
                ),
            },
            status=400,
        )

    def _serve_api_attribution_main(
        self, source: str, session_id: str, round_index: int, call_index: int, kind: str
    ) -> None:
        """处理 attribution for a main-agent LLM call.

        Args:
            source: Source agent namespace for the session.
            session_id: Session identifier from the API route.
            round_index: One-based round index selected by the client.
            call_index: One-based interaction index within the round.
            kind: Attribution payload kind, either ``request`` or ``response``.
        """
        session, messages, tool_calls, _subagent_runs, llm_calls, rounds = (
            self._load_session_and_build_rounds(source, session_id)
        )
        if session is None:
            return  # 说明:Error already sent by helper

        target_round_idx = round_index - 1
        target_call_idx = call_index - 1

        if target_round_idx < 0 or target_round_idx >= len(rounds):
            self._send_json(
                attribution_error_to_payload(
                    agent=source,
                    call_id='',
                    round_id=str(round_index),
                    error_type='NotFound',
                    message=f'round_index {round_index} out of range (1-{len(rounds)})',
                ),
                status=404,
            )
            return

        r = rounds[target_round_idx]
        if target_call_idx < 0 or target_call_idx >= len(r.interactions):
            self._send_json(
                attribution_error_to_payload(
                    agent=source,
                    call_id='',
                    round_id=str(round_index),
                    error_type='NotFound',
                    message=(
                        f'call_index {call_index} out of range for round {round_index} '
                        f'(1-{len(r.interactions)})'
                    ),
                ),
                status=404,
            )
            return

        ix = r.interactions[target_call_idx]
        self._build_and_send_attribution(
            AttributionRequest(
                source=source,
                session_id=session_id,
                session=session,
                round_obj=r,
                interaction=ix,
                interaction_index=target_call_idx,
                round_index=round_index,
                kind=kind,
                llm_calls=llm_calls,
                messages=messages,
                tool_calls=tool_calls,
            )
        )

    def _serve_api_attribution_subagent(
        self, source: str, session_id: str, sa_id: str, call_idx: int, kind: str
    ) -> None:
        """处理 attribution for a subagent LLM call.

        Args:
            source: Source agent namespace for the parent session.
            session_id: Session identifier from the API route.
            sa_id: Subagent run identifier selected by the route.
            call_idx: One-based LLM call index within the subagent run.
            kind: Attribution payload kind, either ``request`` or ``response``.
        """
        session, messages, tool_calls, subagent_runs, llm_calls, rounds = (
            self._load_session_and_build_rounds(source, session_id)
        )
        if session is None:
            return  # 说明:Error already sent by helper

        # 查找 subagent LLM calls matching sa_id
        sa_llm_calls = [c for c in llm_calls if c.scope == 'subagent' and c.subagent_id == sa_id]
        if not sa_llm_calls:
            self._send_json(
                attribution_error_to_payload(
                    agent=source,
                    call_id='',
                    round_id='',
                    error_type='NotFound',
                    message=f"subagent '{sa_id}' LLM calls not found",
                ),
                status=404,
            )
            return

        # call_idx is 1-based per-subagent index; find 该 matching call
        # 说明:The per-subagent index maps to position in sa_llm_calls list
        if call_idx < 1 or call_idx > len(sa_llm_calls):
            self._send_json(
                attribution_error_to_payload(
                    agent=source,
                    call_id='',
                    round_id='',
                    error_type='NotFound',
                    message=(
                        f"call_index {call_idx} out of range for subagent '{sa_id}' "
                        f'(1-{len(sa_llm_calls)})'
                    ),
                ),
                status=404,
            )
            return

        ix = sa_llm_calls[call_idx - 1]

        # Determine subagent_type,来源于 subagent_runs 或 tool_calls
        subagent_type = None
        for run in subagent_runs:
            if run['summary']['agent_id'] == sa_id:
                subagent_type = run['summary'].get('agent_type', '') or None
                break
        # 说明:Fallback: check parent Agent tool call's subagent_summary
        if not subagent_type:
            for tc in tool_calls:
                if tc.name == 'Agent' and tc.subagent_id == sa_id:
                    subagent_type = tc.subagent_summary.get('agent_type', '') or None
                    break

        # 查找 该 parent round,用于 this subagent call
        parent_round_idx = ix.round_index
        if parent_round_idx < 0 or parent_round_idx >= len(rounds):
            parent_round_idx = 0

        r = rounds[parent_round_idx]

        # For subagent, we don't have 一个 meaningful interaction_index within
        # the round's interactions list. Use 0 as 一个 安全 default so that
        # 说明:preceding_tool_results is empty (subagent calls don't have local
        # preceding tool results in 该 same way).
        self._build_and_send_attribution(
            AttributionRequest(
                source=source,
                session_id=session_id,
                session=session,
                round_obj=r,
                interaction=ix,
                interaction_index=0,
                round_index=parent_round_idx + 1,
                kind=kind,
                llm_calls=llm_calls,
                messages=messages,
                tool_calls=tool_calls,
                subagent_type=subagent_type,
            )
        )

    def _load_session_and_build_rounds(
        self, source: str, session_id: str
    ) -> tuple[object | None, list[object], list[object], list[object], list[object], list[object]]:
        """加载 session, parse data, build rounds 和 LLM calls for API handlers.

        Uses in-memory cache to avoid re-parsing large JSONL files on every
        API call (round lazy-load, attribution, payload fetch).

        Args:
            source: Source agent namespace used by index keys and parsers.
            session_id: Session identifier from the API route.

        Returns:
            Tuple of ``session``, ``messages``, ``tool_calls``,
            ``subagent_runs``, ``llm_calls``, and ``rounds``. The first item is
            ``None`` when an error response was already sent.
        """
        session_key = f'{source}:{session_id}'
        conn = _get_connection()
        session = get_session(conn, session_key)
        conn.close()

        if session is None:
            if source == 'qoder':
                resolved_id, err_msg = _resolve_qoder_short_id(session_id)
                if resolved_id:
                    session_key = f'{source}:{resolved_id}'
                    conn = _get_connection()
                    session = get_session(conn, session_key)
                    conn.close()
                    if session is not None:
                        session_id = resolved_id
                if session is None and err_msg:
                    self._send_json(
                        attribution_error_to_payload(
                            agent=source,
                            call_id='',
                            round_id='',
                            error_type='NotFound',
                            message=err_msg,
                        ),
                        status=404,
                    )
                    return (None, [], [], [], [], [])
            if session is None:
                self._send_json(
                    attribution_error_to_payload(
                        agent=source,
                        call_id='',
                        round_id='',
                        error_type='NotFound',
                        message='session not found',
                    ),
                    status=404,
                )
                return (None, [], [], [], [], [])

        # 说明:Try in-memory cache first
        cached = _get_cached_session_data(source, session_id)
        if cached is not None:
            raw_summary = cached['raw_summary']
            messages = cached['messages']
            tool_calls = cached['tool_calls']
            subagent_runs = cached['subagent_runs']
            logger.debug('_load_session_and_build_rounds cache hit: %s', session_key)
        else:
            # 解析 session detail
            if source == 'claude_code':
                raw_summary, messages, tool_calls, subagent_runs = parse_claude_session_detail(
                    session.project_key, session_id
                )
            elif source == 'qoder':
                qoder_file = (
                    Path(session.file_path)
                    if session.file_path and Path(session.file_path).exists()
                    else None
                )
                raw_summary, messages, tool_calls, subagent_runs = parse_qoder_session_detail(
                    session.project_key, session_id, session_file=qoder_file
                )
            else:
                raw_summary, messages, tool_calls, subagent_runs = parse_codex_session_detail(
                    session_id
                )

            # Cache,用于 subsequent API calls
            _set_cached_session_data(
                source,
                session_id,
                {
                    'raw_summary': raw_summary,
                    'messages': messages,
                    'tool_calls': tool_calls,
                    'subagent_runs': subagent_runs,
                },
            )

        # 构建 rounds 和 LLM calls
        rounds = build_rounds(
            messages,
            tool_calls,
            session.fresh_input_tokens,
            session.output_tokens,
            session.cache_read_tokens,
            session.cache_write_tokens,
            source,
            md_filter=_md_filter,
        )
        llm_calls = build_llm_calls(messages, tool_calls, rounds, subagent_runs, source)
        assign_interactions_to_rounds(rounds, llm_calls, tool_calls, subagent_runs)

        return (session, messages, tool_calls, subagent_runs, llm_calls, rounds)

    def _serve_api_round_path(self, path: str) -> None:
        """分发 round lazy-load API route.

        Args:
            path: Request path matching
                ``/api/sessions/{agent}/{session_id}/round/{round_index}``.

        Raises:
            ValueError: Raised and caught locally when the round index is not a
                positive integer.
        """
        parts = path.split('/')
        # 说明:parts: ["", "api", "sessions", agent, session_id, "round", round_index]
        if len(parts) == API_ROUND_PARTS and parts[5] == 'round':
            try:
                round_index = int(parts[6])
                if round_index < 1:
                    raise ValueError('must be positive')
            except (ValueError, IndexError):
                self._send_json(
                    {
                        'error': f"invalid round_index='{parts[6]}', must be a positive integer",
                    },
                    status=400,
                )
                return
            agent = urllib.parse.unquote(parts[3])
            session_id = urllib.parse.unquote(parts[4])
            self._serve_api_round(agent, session_id, round_index)
        else:
            self._send_json(
                {
                    'error': 'invalid API path',
                    'expected': '/api/sessions/{agent}/{session_id}/round/{round_index}',
                },
                status=400,
            )

    def _serve_api_round(self, agent: str, session_id: str, round_index: int) -> None:
        """返回 expanded round detail HTML for a one-based round index.

        Args:
            agent: Source agent namespace for the session.
            session_id: Session identifier from the API route.
            round_index: One-based round index requested by the client.
        """
        result = self._load_session_and_build_rounds(agent, session_id)
        if result[0] is None:
            return  # 说明:Error already sent

        _session, _messages, _tool_calls, _subagent_runs, llm_calls, rounds = result

        # 说明:Validate round_index
        target_idx = round_index - 1  # 说明:convert to 0-based
        if target_idx < 0 or target_idx >= len(rounds):
            self._send_json(
                {
                    'error': f'round_index {round_index} out of range (1-{len(rounds)})',
                },
                status=404,
            )
            return

        # 计算 signals,用于 该 target round
        r = rounds[target_idx]
        signals = compute_round_signals(
            r,
            round_index,
            _session.fresh_input_tokens + _session.cache_read_tokens + _session.cache_write_tokens,
        )

        # 构建 view model,用于 just this 一个 round. Use skip_attribution=True
        # because 该 expanded row HTML 仅 renders timeline items (LLM call
        # 说明:cards, tool batches, subagent blocks) — it never uses payload_sources
        # inline. Attribution data is fetched on-demand,当 该 user clicks
        # 说明:Request/Response attribution buttons.
        vm = _build_v11_view_model(
            _session,
            rounds,
            llm_calls,
            _tool_calls,
            _subagent_runs,
            session_anomalies=type('FA', (), {'anomalies': []})(),
            slim=False,
            round_filter={target_idx},
            skip_attribution=True,
        )

        # 查找 该 trace row,用于 该 target round
        trace_row = None
        for tr in vm['trace_rows']:
            if tr['round_id'] == round_index:
                trace_row = tr
                break

        if trace_row is None:
            self._send_json({'error': 'round detail not found'}, status=404)
            return

        # Render 该 expanded row HTML using Jinja template.
        # round_table.html now imports llm_call/subagent,使用 context,
        # so 该 macro namespace is self-contained 和 works via template.module.
        template = _template_env.get_template('components/session_detail_timeline.html')
        expanded_html = template.module.expanded_row(trace_row)
        # Strip <tr>/<td> wrapper tags — JS creates its own <tr><td> 和 injects inner content
        expanded_html = re.sub(r'^<tr[^>]*>\s*<td[^>]*>', '', expanded_html)
        expanded_html = re.sub(r'</td>\s*</tr>\s*$', '', expanded_html)

        self._send_json(
            {
                'html': expanded_html,
                'round_id': round_index,
                'has_user_input': trace_row.get('has_user_input', False),
                'has_subagent': trace_row.get('has_subagent', False),
                'signals': signals,
                'payload_sources': vm.get('payload_sources', []),
            }
        )

    def _build_and_send_attribution(self, request: AttributionRequest) -> None:
        """构建 attribution for one LLM call and send a JSON response.

        Args:
            request: Complete attribution request context assembled by the route.
        """
        source = request.source
        session_id = request.session_id
        session = request.session
        r = request.round_obj
        ix = request.interaction
        interaction_index = request.interaction_index
        round_index = request.round_index
        kind = request.kind
        llm_calls = request.llm_calls
        messages = request.messages
        tool_calls = request.tool_calls
        subagent_type = request.subagent_type

        all_messages = messages or []
        all_tool_calls = tool_calls or []

        # 构建 call-scoped session context,使用 hydration
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

        # 构建 attribution
        try:
            if kind == 'request':
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
            logger.debug('Attribution builder exception: %s', exc, exc_info=True)
            self._send_json(
                attribution_error_to_payload(
                    agent=source,
                    call_id=ix.id or '',
                    round_id=str(round_index),
                    error_type=type(exc).__name__,
                    message=str(exc)[:200] if str(exc) else 'attribution builder failed',
                ),
                status=500,
            )
            return

        # 返回 API envelope
        envelope = {
            'kind': f'llm.{kind}_attribution',
            'source': source,
            'session_id': session_id,
            'round_index': round_index,
            'call_index': getattr(ix, 'round_index', 0) + 1,
            'data': data,
        }
        self._send_json(envelope)

    def _serve_api_bucket_detail_path(self, path: str) -> None:
        """分发 bucket detail API route for dynamic attribution drill-down.

        Supports dynamic loading of bucket detail content:
        - current_user_message: full user message text for a given round
        - local_instruction_context: full CLAUDE.md content for the project

        Args:
            path: Request path matching
                ``/api/sessions/{source}/{session_id}/bucket-detail/{round_index}/{bucket_key}``.
        """
        parts = path.split('/')
        # parts: ["", "api", "sessions", source, session_id, "bucket-detail", ...]
        if len(parts) == API_BUCKET_DETAIL_PARTS and parts[5] == 'bucket-detail':
            source = urllib.parse.unquote(parts[3])
            session_id = urllib.parse.unquote(parts[4])
            round_index_str = parts[6]
            bucket_key = urllib.parse.unquote(parts[7])
            try:
                round_index = int(round_index_str)
            except (ValueError, IndexError):
                self._send_json({'error': f"invalid round_index='{round_index_str}'"}, status=400)
                return
            self._serve_api_bucket_detail(source, session_id, round_index, bucket_key)
        else:
            self._send_json(
                {
                    'error': 'invalid API path',
                    'expected': (
                        '/api/sessions/{source}/{session_id}/bucket-detail/'
                        '{round_index}/{bucket_key}'
                    ),
                },
                status=400,
            )

    def _serve_api_bucket_detail(  # noqa: PLR0911, PLR0912, PLR0915 - fixed bucket protocol branches
        self, source: str, session_id: str, round_index: int, bucket_key: str
    ) -> None:
        """返回 full bucket detail content for dynamic attribution loading.

        Args:
            source: Source agent namespace for the session.
            session_id: Session identifier from the API route.
            round_index: One-based round index used to locate context.
            bucket_key: Drill-down bucket key selected by the attribution UI.
        """
        session_key = f'{source}:{session_id}'
        conn = _get_connection()
        session = get_session(conn, session_key)
        conn.close()

        if session is None:
            if source == 'qoder':
                resolved_id, err_msg = _resolve_qoder_short_id(session_id)
                if resolved_id:
                    session_key = f'{source}:{resolved_id}'
                    conn = _get_connection()
                    session = get_session(conn, session_key)
                    conn.close()
                    if session is not None:
                        session_id = resolved_id
                if session is None and err_msg:
                    self._send_json({'error': err_msg}, status=404)
                    return
            if session is None:
                self._send_json({'error': 'session not found'}, status=404)
                return

        if bucket_key == 'current_user_message':
            # Fetch 该 user message,用于 该 given round
            if source == 'claude_code':
                _raw_summary, messages, tool_calls, subagent_runs = parse_claude_session_detail(
                    session.project_key, session_id
                )
            elif source == 'qoder':
                qoder_file = (
                    Path(session.file_path)
                    if session.file_path and Path(session.file_path).exists()
                    else None
                )
                _raw_summary, messages, tool_calls, subagent_runs = parse_qoder_session_detail(
                    session.project_key, session_id, session_file=qoder_file
                )
            else:
                _raw_summary, messages, tool_calls, subagent_runs = parse_codex_session_detail(
                    session_id
                )

            rounds = build_rounds(
                messages,
                tool_calls,
                session.fresh_input_tokens,
                session.output_tokens,
                session.cache_read_tokens,
                session.cache_write_tokens,
                source,
                md_filter=_md_filter,
            )
            target_idx = round_index - 1
            if target_idx < 0 or target_idx >= len(rounds):
                self._send_json(
                    {'error': f'round_index {round_index} out of range (1-{len(rounds)})'},
                    status=404,
                )
                return

            r = rounds[target_idx]
            content = r.user_msg.content if r.user_msg else ''
            masked = mask_sensitive_keys(content or '')
            self._send_json(
                {
                    'kind': 'bucket_detail',
                    'bucket_key': bucket_key,
                    'round_index': round_index,
                    'text': masked,
                    'tokens': estimate_tokens_from_text(content or ''),
                }
            )
            return

        if bucket_key == 'local_instruction_context':
            # 读取 CLAUDE.md,来源于 project directory
            project_dir = session.project_key
            if not project_dir:
                self._send_json({'error': 'project directory unknown', 'text': ''}, status=404)
                return

            local_text = _read_local_instructions(Path(project_dir), source)

            if not local_text:
                self._send_json(
                    {
                        'kind': 'bucket_detail',
                        'bucket_key': bucket_key,
                        'text': '',
                        'note': '未检测到本地指令上下文.',
                    }
                )
                return

            masked = mask_sensitive_keys(local_text)
            self._send_json(
                {
                    'kind': 'bucket_detail',
                    'bucket_key': bucket_key,
                    'text': masked,
                    'tokens': estimate_tokens_from_text(local_text),
                    'source_file': 'CLAUDE.md',
                }
            )
            return

        if bucket_key.startswith('full_messages_array_item:'):
            # Fetch 一个 specific message item,来源于 该 full_messages_array
            try:
                msg_index = int(bucket_key.split(':', 1)[1])
            except (ValueError, IndexError):
                self._send_json(
                    {'error': f"invalid message_index in bucket_key '{bucket_key}'"}, status=400
                )
                return

            if source == 'claude_code':
                _raw_summary, messages, tool_calls, subagent_runs = parse_claude_session_detail(
                    session.project_key, session_id
                )
            elif source == 'qoder':
                qoder_file = (
                    Path(session.file_path)
                    if session.file_path and Path(session.file_path).exists()
                    else None
                )
                _raw_summary, messages, tool_calls, subagent_runs = parse_qoder_session_detail(
                    session.project_key, session_id, session_file=qoder_file
                )
            else:
                _raw_summary, messages, tool_calls, subagent_runs = parse_codex_session_detail(
                    session_id
                )

            rounds = build_rounds(
                messages,
                tool_calls,
                session.fresh_input_tokens,
                session.output_tokens,
                session.cache_read_tokens,
                session.cache_write_tokens,
                source,
                md_filter=_md_filter,
            )
            llm_calls = build_llm_calls(messages, tool_calls, rounds, subagent_runs, source)
            assign_interactions_to_rounds(rounds, llm_calls, tool_calls, subagent_runs)

            # 构建 full_messages_array,用于 该 first interaction of 该 first round
            # as 一个 representative sample
            target_idx = round_index - 1
            if target_idx < 0 or target_idx >= len(rounds):
                self._send_json(
                    {'error': f'round_index {round_index} out of range (1-{len(rounds)})'},
                    status=404,
                )
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

            msg_array = attrib_ctx.get('full_messages_array', [])
            if msg_index < 0 or msg_index >= len(msg_array):
                self._send_json(
                    {
                        'error': f'message_index {msg_index} out of range (0-{len(msg_array) - 1})',
                        'total_messages': len(msg_array),
                    },
                    status=404,
                )
                return

            msg_entry = msg_array[msg_index]
            # For full content, we need to reconstruct,来源于 该 original messages
            content_text = ''
            if msg_entry.get('content_type') == 'user_text':
                content_text = self._find_user_message_content(messages, msg_array, msg_index)
            elif msg_entry.get('content_type') == 'tool_result':
                content_text = self._find_tool_result_content(messages, msg_array, msg_index)
            elif msg_entry.get('content_type') == 'assistant_text':
                content_text = self._find_assistant_message_content(messages, msg_array, msg_index)

            masked = mask_sensitive_keys(content_text or '')
            self._send_json(
                {
                    'kind': 'bucket_detail',
                    'bucket_key': 'full_messages_array_item',
                    'message_index': msg_index,
                    'role': msg_entry.get('role', ''),
                    'content_type': msg_entry.get('content_type', ''),
                    'tool_name': msg_entry.get('tool_name', ''),
                    'text': masked,
                    'tokens': estimate_tokens_from_text(content_text or ''),
                }
            )
            return

        self._send_json(
            {'error': f"bucket_key '{bucket_key}' not supported for dynamic loading"},
            status=400,
        )

    def _serve_static(self, filename: str) -> None:
        """Serve one file from the packaged web static directory.

        Args:
            filename: Relative static asset path from the URL after
                ``/static/``.
        """
        static_dir = Path(__file__).parent / 'static'
        filepath = static_dir / filename
        if not filepath.exists():
            self._send_404()
            return

        content_type = (
            'text/css'
            if filename.endswith('.css')
            else (
                'application/javascript'
                if filename.endswith('.js')
                else ('image/svg+xml' if filename.endswith('.svg') else 'text/plain')
            )
        )
        self.send_response(200)
        self.send_header('Content-Type', content_type)
        self.end_headers()
        self.wfile.write(filepath.read_bytes())

    def _serve_all_sessions(self) -> None:
        """Render the global sessions page across all projects."""
        conn = _get_connection()

        # 说明:── Parse query parameters ──────────────────────────────────
        parsed = urllib.parse.urlparse(self.path)
        raw_params = urllib.parse.parse_qs(parsed.query)

        params = parse_sessions_query_params(raw_params)

        # 说明:── Fetch view model ────────────────────────────────────────
        total_count = count_sessions(
            conn,
            agent=params['filter_agent'],
            project_key=params['filter_project'],
            model=params['filter_model'],
            title_like=params['filter_q'],
            failure_status=params['filter_status'],
        )

        pagination = compute_pagination(
            total_count=total_count,
            page=params['page'],
            page_size=params['page_size'],
        )

        vm = fetch_sessions_view_model(
            conn=conn,
            filter_agent=params['filter_agent'],
            filter_model=params['filter_model'],
            filter_project=params['filter_project'],
            filter_q=params['filter_q'],
            filter_status=params['filter_status'],
            sort_by=params['sort_by'],
            sort_dir=params['sort_dir'],
            limit=pagination['limit'],
            offset=pagination['offset'],
        )

        conn.close()

        # 归一化 sort key,用于 template (ui uses 'updated',用于 'ended-at')
        ui_sort = (
            'updated' if params['raw_sort'] == 'ended-at' else (params['raw_sort'] or 'ended-at')
        )

        filters_for_actions = {
            'q': params['filter_q'] or '',
            'agent': params['filter_agent'] or '',
            'model': params['filter_model'] or '',
            'project': params['filter_project'] or '',
            'status': params['filter_status'] or '',
        }
        actions = _build_view_actions(
            filters=filters_for_actions,
            sort_key=ui_sort,
            sort_dir=params['sort_dir'],
            page=pagination['page'],
            page_size=params['page_size'],
            has_prev=pagination['has_prev'],
            has_next=pagination['has_next'],
        )

        # 说明:── AJAX partial response (X-Requested-With header) ─────────
        is_ajax = self.headers.get('X-Requested-With') == 'XMLHttpRequest'
        if is_ajax:
            html = self._render_template(
                'partials/sessions_ajax_page.html',
                sessions=vm['sessions_enriched'],
                total_count=vm['total_count'],
                page=pagination['page'],
                page_size=params['page_size'],
                total_pages=pagination['total_pages'],
                page_start=pagination['page_start'],
                page_end=pagination['page_end'],
                has_prev=pagination['has_prev'],
                has_next=pagination['has_next'],
                sort_key=ui_sort,
                sort_dir=params['sort_dir'],
                actions=actions,
                sessions_aggregate=vm['sessions_aggregate'],
                filter_q=params['filter_q'] or '',
                filter_agent=params['filter_agent'] or '',
                filter_model=params['filter_model'] or '',
                filter_project=params['filter_project'] or '',
                filter_status=params['filter_status'] or '',
            )
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(html.encode('utf-8'))
            return

        html = self._render_template(
            'sessions.html',
            sessions=vm['sessions_enriched'],
            total_count=vm['total_count'],
            page=pagination['page'],
            current_page=pagination['page'],
            page_size=params['page_size'],
            total_pages=pagination['total_pages'],
            page_start=pagination['page_start'],
            page_end=pagination['page_end'],
            has_prev=pagination['has_prev'],
            has_next=pagination['has_next'],
            filter_agent=params['filter_agent'] or '',
            filter_model=params['filter_model'] or '',
            filter_project=params['filter_project'] or '',
            filter_q=params['filter_q'] or '',
            filter_status=params['filter_status'] or '',
            sort_by=ui_sort,
            sort_dir=params['sort_dir'],
            model_list=vm['model_list'],
            project_list=vm['project_list'],
            active_page='sessions',
            actions=actions,
            sessions_aggregate=vm['sessions_aggregate'],
        )
        self._send_html(html)

    def _serve_glossary(self) -> None:
        """Render the token glossary page."""
        html = self._render_template(
            'glossary.html',
            active_page='glossary',
        )
        self._send_html(html)


class SessionBrowserServer(ThreadingHTTPServer):
    """Threaded server keeps parallel browser tests from starving requests.

    Attributes:
        daemon_threads: Whether request worker threads should exit with the
            server process.
    """

    daemon_threads = True


def create_server(
    host: str = '127.0.0.1',
    port: int = 8899,
) -> HTTPServer:
    """创建 and return a reusable HTTP server instance.

    .. deprecated:: WEB-110
       生产 serve/stop 已切换至 Java launcher。此函数仅保留供
       Python 侧单元测试 fixture 使用，不应在生产路径调用。

    Args:
        host: Interface address used by the local browser server.
        port: TCP port used by the local browser server.

    Returns:
        Configured threaded HTTP server using ``SessionBrowserHandler``.
    """
    server = SessionBrowserServer((host, port), SessionBrowserHandler)
    server.allow_reuse_address = True
    return server
