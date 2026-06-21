"""Build Claude Code normalized session attribution records.

Claude Code sources call this adapter after parsing local JSONL session payloads
into summaries, messages, tool calls, subagent runs, and warnings. The adapter
converts that parsed boundary into normalized call records, source-unit catalogs,
subagent steps, and semantic session metadata.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from session_browser.domain.models import ChatMessage, SessionSummary, SubagentRun, ToolCall
from session_browser.normalized.agents.claude_code_parts import (
    ClaudeCodeSourceUnitDraft,
    draft_to_catalog_unit,
    hydrate_source_units,
    payload_unit,
    text_unit,
)
from session_browser.normalized.semantic import build_normalized_session_model
from session_browser.sources.jsonl_reader import parse_jsonl_events


class ClaudeCodeNormalizationAdapter:
    """Build Claude Code call drafts and source-unit catalogs.

    Instances are created by the module-level adapter entrypoints for one parsed
    session payload. They collect per-call request/response source units and return
    normalized records without owning raw JSONL parsing.
    """

    def __init__(self) -> None:
        """Initialize adapter state for one normalized session build."""  # noqa: RUF100  # noqa: DOC301,DOC101,DOC103
        self.source_unit_catalog: dict[str, dict] = {}
        self.source_unit_sequences: dict[str, list[str]] = {
            'persistent_request': [],
        }
        self.source_unit_sequence_sets: dict[str, set[str]] = {
            'persistent_request': set(),
        }

    def build(  # noqa: PLR0913 - Adapter entrypoint mirrors parsed session payload fields.
        self,
        *,
        summary: SessionSummary,
        messages: list[ChatMessage],
        tool_calls: list[ToolCall],
        source_path: str,
        subagent_runs: list[SubagentRun] | None = None,
        parse_warnings: list[dict] | None = None,
    ) -> dict:
        """Build normalized session records from parsed adapter payloads.

        Triggered by module-level adapter entrypoints with parsed session payloads. It returns
        normalized session records for downstream viewers and metrics consumers.

        Args:
            summary: Input value for normalized adapter processing.
            messages: Input value for normalized adapter processing.
            tool_calls: Input value for normalized adapter processing.
            source_path: Input value for normalized adapter processing.
            subagent_runs: Input value for normalized adapter processing.
            parse_warnings: Input value for normalized adapter processing.

        Returns:
            Normalized adapter result.
        """
        subagent_runs = subagent_runs or []
        main_tool_calls = [tc for tc in tool_calls if getattr(tc, 'scope', 'main') == 'main']
        rounds = self._build_rounds(
            summary=summary,
            messages=messages,
            tool_calls=main_tool_calls,
            source_path=source_path,
            scope='main',
            subagent_id='',
            parent_tool_use_id='',
            subagent_runs=subagent_runs,
        )
        source_files = [{'role': 'main_session', 'path': source_path}]
        for run in subagent_runs:
            path = run.get('path', '')
            source_files.append(
                {
                    'role': 'subagent_session',
                    'path': str(path) if path else '',
                    'subagent_id': (run.get('summary') or {}).get('agent_id', ''),
                    'parent_tool_use_id': _parent_tool_for_subagent(main_tool_calls, run),
                }
            )
        normalized = build_normalized_session_model(
            agent='claude_code',
            session=_session_payload(summary),
            source_files=source_files,
            call_drafts=rounds,
            parse_warnings=parse_warnings or [],
        )
        if self.source_unit_catalog:
            normalized['source_unit_catalog'] = self.source_unit_catalog
            normalized['source_unit_sequences'] = self.source_unit_sequences
        return normalized

    def _build_rounds(  # noqa: PLR0913 - Round builders need explicit normalized call context.
        self,
        *,
        summary: SessionSummary,
        messages: list[ChatMessage],
        tool_calls: list[ToolCall],
        source_path: str,
        scope: str,
        subagent_id: str,
        parent_tool_use_id: str,
        subagent_runs: list[SubagentRun],
    ) -> list[dict]:
        """Support normalized adapter processing for _build_rounds.

        Args:
            summary: Input value for normalized adapter processing.
            messages: Input value for normalized adapter processing.
            tool_calls: Input value for normalized adapter processing.
            source_path: Input value for normalized adapter processing.
            scope: Input value for normalized adapter processing.
            subagent_id: Input value for normalized adapter processing.
            parent_tool_use_id: Input value for normalized adapter processing.
            subagent_runs: Input value for normalized adapter processing.

        Returns:
            Normalized adapter result.
        """
        rounds: list[dict] = []
        tool_by_id = {tc.tool_use_id: tc for tc in tool_calls if tc.tool_use_id}
        subagent_by_parent = _subagent_runs_by_parent(tool_calls, subagent_runs)
        assistant_seen = 0
        instruction_units = _project_instruction_units(summary, source_path)
        self._catalog_refs_for_drafts(instruction_units, sequence_name='persistent_request')
        history_sequence_name = _history_sequence_name(scope, subagent_id)
        self.source_unit_sequences.setdefault(history_sequence_name, [])
        self.source_unit_sequence_sets.setdefault(history_sequence_name, set())

        for msg_index, msg in enumerate(messages):
            if msg.role != 'assistant' or not msg.llm_call_id:
                continue
            assistant_seen += 1
            round_id = len(rounds) + 1
            call_id = msg.llm_call_id
            tools = _tools_for_message(msg, tool_by_id, round_id)
            usage = _usage_from_message(msg)
            request_units = self._request_units_for_call(
                call_id=call_id,
                msg=msg,
                messages_before=messages[:msg_index],
                summary=summary,
                source_path=source_path,
                instruction_units=[],
                event_order=assistant_seen,
                include_history=False,
            )
            response_units = self._response_units_for_call(
                msg=msg,
                event_order=assistant_seen,
            )
            history_count = len(self.source_unit_sequences[history_sequence_name])
            request_refs = self._catalog_refs_for_drafts(request_units)
            response_refs = self._catalog_refs_for_drafts(response_units)
            source_unit_ref_ranges = self._source_unit_ref_ranges(
                history_sequence_name=history_sequence_name,
                history_count=history_count,
                request_refs=request_refs,
                response_refs=response_refs,
            )
            metrics = {
                'tokens': {
                    'fresh': usage['fresh'],
                    'cache_read': usage['cache_read'],
                    'cache_write': usage['cache_write'],
                    'output': usage['output'],
                    'total': usage['total'],
                },
            }
            if usage.get('usage_source'):
                metrics['usage_source'] = usage['usage_source']
            subagent_steps = _subagent_steps_for_tools(
                adapter=self,
                summary=summary,
                source_path=source_path,
                round_id=round_id,
                tools=tools,
                subagent_by_parent=subagent_by_parent,
            )
            rounds.append(
                {
                    'round_id': round_id,
                    'round_key': f'R{round_id}',
                    'main_call': {
                        'call_id': call_id,
                        'turn_id': '',
                        'model': msg.model,
                        'timestamp': msg.timestamp,
                        'scope': scope,
                        'subagent_id': subagent_id,
                        'parent_tool_use_id': parent_tool_use_id,
                    },
                    'metrics': metrics,
                    'request': {
                        'tool_result_ids': _tool_result_ids_from_request(msg.request_full or '')
                    },
                    'response': {'tool_call_ids': _tool_call_ids_from_message(msg, tools)},
                    'source_unit_ref_ranges': source_unit_ref_ranges,
                    'steps': _steps_for_round(
                        timestamp=msg.timestamp, tools=tools, subagent_steps=subagent_steps
                    ),
                }
            )
            self._append_history_refs(
                call_id=call_id,
                refs=request_refs + response_refs,
                history_sequence_name=history_sequence_name,
            )
        return rounds

    def _source_unit_ref_ranges(
        self,
        *,
        history_sequence_name: str,
        history_count: int,
        request_refs: list[str],
        response_refs: list[str],
    ) -> list[dict]:
        """Support normalized adapter processing for _source_unit_ref_ranges.

        Args:
            history_sequence_name: Input value for normalized adapter processing.
            history_count: Input value for normalized adapter processing.
            request_refs: Input value for normalized adapter processing.
            response_refs: Input value for normalized adapter processing.

        Returns:
            Normalized adapter result.
        """
        ranges: list[dict] = []
        persistent_count = len(self.source_unit_sequences['persistent_request'])
        if persistent_count:
            ranges.append(
                {
                    'sequence': 'persistent_request',
                    'start': 0,
                    'end': persistent_count,
                }
            )
        if history_count:
            ranges.append(
                {
                    'sequence': history_sequence_name,
                    'start': 0,
                    'end': history_count,
                }
            )
        if request_refs:
            ranges.append({'refs': request_refs, 'role': 'request_current'})
        if response_refs:
            ranges.append({'refs': response_refs, 'role': 'response'})
        return ranges

    def _append_history_refs(
        self,
        *,
        call_id: str,
        refs: list[str],
        history_sequence_name: str,
    ) -> None:
        """Support normalized adapter processing for _append_history_refs.

        Args:
            call_id: Input value for normalized adapter processing.
            refs: Input value for normalized adapter processing.
            history_sequence_name: Input value for normalized adapter processing.
        """
        source_units = hydrate_source_units(call_id, self._catalog_units_for_refs(refs))
        history_drafts: list[ClaudeCodeSourceUnitDraft] = []
        for unit in source_units:
            candidate = str(unit.get('candidate') or '')
            if candidate not in {
                'user_input',
                'assistant_output',
                'reasoning_output',
                'tool_calls',
                'structured_output',
            }:
                continue
            history_drafts.append(_history_source_unit(candidate, unit))
        self._catalog_refs_for_drafts(history_drafts, sequence_name=history_sequence_name)

    def _catalog_refs_for_drafts(
        self,
        drafts: list[ClaudeCodeSourceUnitDraft],
        *,
        sequence_name: str = '',
    ) -> list[str]:
        """Support normalized adapter processing for _catalog_refs_for_drafts.

        Args:
            drafts: Input value for normalized adapter processing.
            sequence_name: Input value for normalized adapter processing.

        Returns:
            Normalized adapter result.
        """
        refs: list[str] = []
        sequence = self.source_unit_sequences.get(sequence_name) if sequence_name else None
        sequence_set = self.source_unit_sequence_sets.get(sequence_name) if sequence_name else None
        for draft in drafts:
            unit = draft_to_catalog_unit(draft)
            key = str(unit['unit_key'])
            existing = self.source_unit_catalog.get(key)
            if existing is None or _catalog_rank(unit) > _catalog_rank(existing):
                self.source_unit_catalog[key] = unit
            refs.append(key)
            if sequence is not None and sequence_set is not None and key not in sequence_set:
                sequence.append(key)
                sequence_set.add(key)
        return refs

    def _catalog_units_for_refs(self, refs: list[str]) -> list[dict]:
        """Support normalized adapter processing for _catalog_units_for_refs.

        Args:
            refs: Input value for normalized adapter processing.

        Returns:
            Normalized adapter result.
        """
        return [self.source_unit_catalog[key] for key in refs if key in self.source_unit_catalog]

    def _request_units_for_call(  # noqa: PLR0913 - Source-unit attribution requires explicit call context.
        self,
        *,
        call_id: str,
        msg: ChatMessage,
        messages_before: list[ChatMessage],
        summary: SessionSummary,
        source_path: str,
        instruction_units: list[ClaudeCodeSourceUnitDraft],
        event_order: int,
        include_history: bool = True,
    ) -> list[ClaudeCodeSourceUnitDraft]:
        """Support normalized adapter processing for _request_units_for_call.

        Args:
            call_id: Input value for normalized adapter processing.
            msg: Input value for normalized adapter processing.
            messages_before: Input value for normalized adapter processing.
            summary: Input value for normalized adapter processing.
            source_path: Input value for normalized adapter processing.
            instruction_units: Input value for normalized adapter processing.
            event_order: Input value for normalized adapter processing.
            include_history: Input value for normalized adapter processing.

        Returns:
            Normalized adapter result.
        """
        units: list[ClaudeCodeSourceUnitDraft] = []
        timestamp = msg.timestamp
        units.extend(
            _clone_units_for_call(instruction_units, event_order=event_order, timestamp=timestamp)
        )
        runtime_payload = {
            'cwd': summary.cwd,
            'project_key': summary.project_key,
            'git_branch': summary.git_branch,
            'source': summary.source,
            'model': msg.model or summary.model,
        }
        units.append(
            payload_unit(
                origin_path='session.runtime',
                unit_type='claude_code_runtime_context',
                candidate='runtime_context',
                direction='request',
                payload={k: v for k, v in runtime_payload.items() if v},
                timestamp=timestamp,
                event_order=event_order,
                label='Claude Code 运行上下文',
                priority=40,
            )
        )

        current_user_index = _current_user_index_for_call(messages_before)
        if current_user_index >= 0:
            current_user = messages_before[current_user_index]
            if current_user.content:
                units.append(
                    text_unit(
                        origin_path=f'messages[{current_user_index}].content',
                        unit_type='current_user_message',
                        candidate='user_input',
                        direction='request',
                        text=current_user.content,
                        timestamp=current_user.timestamp or timestamp,
                        event_order=event_order,
                        label='当前用户输入',
                        priority=90,
                    )
                )
        if include_history:
            for idx, prior in enumerate(messages_before):
                if idx == current_user_index or not prior.content:
                    continue
                units.append(
                    text_unit(
                        origin_path=f'messages[{idx}].content',
                        unit_type=f'prior_{prior.role}_message',
                        candidate='conversation_history',
                        direction='request',
                        text=prior.content,
                        timestamp=prior.timestamp,
                        event_order=event_order,
                        part_index=idx,
                        label=f'历史 {prior.role} 消息',
                        priority=50,
                    )
                )

        for idx, segment in enumerate(_request_segments(msg.request_full), 1):
            parsed = _parse_tool_result_segment(segment)
            if parsed:
                tool_id, body = parsed
                units.append(
                    text_unit(
                        origin_path=f'request_full.tool_result[{idx}]',
                        canonical_source_locator=f'tool_result:{tool_id or idx}',
                        unit_type='tool_result_text',
                        candidate='tool_results',
                        direction='request',
                        text=body,
                        timestamp=timestamp,
                        event_order=event_order,
                        part_index=idx,
                        label=f'工具结果 {tool_id or idx}',
                        priority=85,
                    )
                )
            elif (
                include_history
                and segment
                and not _matches_current_user(segment, messages_before, current_user_index)
            ):
                units.append(
                    text_unit(
                        origin_path=f'request_full.fragment[{idx}]',
                        unit_type='request_context_fragment',
                        candidate='conversation_history',
                        direction='request',
                        text=segment,
                        timestamp=timestamp,
                        event_order=event_order,
                        part_index=idx,
                        label='request 上下文片段',
                        priority=35,
                    )
                )
        return units

    def _response_units_for_call(
        self,
        *,
        msg: ChatMessage,
        event_order: int,
    ) -> list[ClaudeCodeSourceUnitDraft]:
        """Support normalized adapter processing for _response_units_for_call.

        Args:
            msg: Input value for normalized adapter processing.
            event_order: Input value for normalized adapter processing.

        Returns:
            Normalized adapter result.
        """
        units: list[ClaudeCodeSourceUnitDraft] = []
        blocks = msg.content_blocks or []
        for idx, block in enumerate(blocks, 1):
            if not isinstance(block, dict):
                continue
            block_type = str(block.get('type') or '')
            if block_type == 'text':
                content = str(block.get('content') or block.get('text') or '')
                if content:
                    units.append(
                        text_unit(
                            origin_path=f'assistant.content_blocks[{idx}]',
                            unit_type='assistant_text',
                            candidate='assistant_output',
                            direction='response',
                            text=content,
                            timestamp=msg.timestamp,
                            event_order=event_order,
                            part_index=idx,
                            label='助手文本',
                        )
                    )
            elif block_type == 'thinking':
                content = str(block.get('content') or block.get('thinking') or '')
                units.append(
                    text_unit(
                        origin_path=f'assistant.content_blocks[{idx}]',
                        unit_type='visible_thinking',
                        candidate='reasoning_output',
                        direction='response',
                        text=content,
                        timestamp=msg.timestamp,
                        event_order=event_order,
                        part_index=idx,
                        label='可见 thinking',
                    )
                )
            elif block_type == 'tool_use':
                units.append(
                    payload_unit(
                        origin_path=f'assistant.content_blocks[{idx}]',
                        canonical_source_locator=f'tool_use:{block.get("id") or idx}',
                        unit_type='tool_use_block',
                        candidate='tool_calls',
                        direction='response',
                        payload=block,
                        timestamp=msg.timestamp,
                        event_order=event_order,
                        part_index=idx,
                        label=str(block.get('name') or 'tool_use'),
                    )
                )
            else:
                units.append(
                    payload_unit(
                        origin_path=f'assistant.content_blocks[{idx}]',
                        unit_type=f'structured_{block_type or "block"}',
                        candidate='structured_output',
                        direction='response',
                        payload=block,
                        timestamp=msg.timestamp,
                        event_order=event_order,
                        part_index=idx,
                        label='结构化输出',
                    )
                )
        if not units and msg.content:
            units.append(
                text_unit(
                    origin_path='assistant.content',
                    unit_type='assistant_text',
                    candidate='assistant_output',
                    direction='response',
                    text=msg.content,
                    timestamp=msg.timestamp,
                    event_order=event_order,
                    label='助手文本',
                )
            )
        return units


def build_claude_code_normalized_session(  # noqa: PLR0913 - Public adapter mirrors parsed session payload fields.
    *,
    summary: SessionSummary,
    messages: list[ChatMessage],
    tool_calls: list[ToolCall],
    source_path: str,
    subagent_runs: list[SubagentRun] | None = None,
    parse_warnings: list[dict] | None = None,
) -> dict:
    """Build Claude Code normalized records from parsed session models.

    Triggered by Claude Code parsers after building parsed session models. It emits
    normalized records, source-unit catalogs, subagent steps, and warnings.

    Args:
        summary: Input value for normalized adapter processing.
        messages: Input value for normalized adapter processing.
        tool_calls: Input value for normalized adapter processing.
        source_path: Input value for normalized adapter processing.
        subagent_runs: Input value for normalized adapter processing.
        parse_warnings: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    return ClaudeCodeNormalizationAdapter().build(
        summary=summary,
        messages=messages,
        tool_calls=tool_calls,
        source_path=source_path,
        subagent_runs=subagent_runs or [],
        parse_warnings=parse_warnings or [],
    )


def parse_claude_code_session_file(
    path: str | Path,
    *,
    project_key: str = '',
    session_id: str | None = None,
) -> dict:
    """Parse one Claude Code JSONL file into normalized session records.

    Triggered by Claude Code session loading for a local JSONL path. It reads raw events,
    derives parsed payload models, and emits normalized records.

    Args:
        path: Input value for normalized adapter processing.
        project_key: Input value for normalized adapter processing.
        session_id: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    from session_browser.normalized.agents.chat_jsonl import session_id_from_file  # noqa: I001,PLC0415 - Lazy import avoids parser/adapter cycles.
    from session_browser.sources.claude import (  # noqa: PLC0415 - Lazy import keeps parser internals optional for adapter users.
        _apply_subagent_totals,
        _attach_subagents_to_agent_tools,
        _build_summary_from_events,
        _extract_messages,
        _extract_tool_calls,
        _flatten_subagent_tool_calls,
        _parse_subagent_runs,
    )

    session_file = Path(path)
    sid = session_id or session_id_from_file(session_file)
    project = project_key or session_file.parent.name
    events, _ = parse_jsonl_events(session_file)
    subagent_runs = _parse_subagent_runs(session_file)
    summary = _build_summary_from_events(events, sid, project, subagent_runs)
    messages = _extract_messages(events)
    messages, parse_warnings = _with_away_summary_messages(events, messages)
    tool_calls = _extract_tool_calls(events, messages)
    _attach_subagents_to_agent_tools(tool_calls, subagent_runs)
    tool_calls.extend(_flatten_subagent_tool_calls(subagent_runs))
    _apply_subagent_totals(summary, subagent_runs, tool_calls)
    return build_claude_code_normalized_session(
        summary=summary,
        messages=messages,
        tool_calls=tool_calls,
        source_path=str(session_file),
        subagent_runs=subagent_runs,
        parse_warnings=parse_warnings,
    )


def _with_away_summary_messages(
    events: list[dict], messages: list[ChatMessage]
) -> tuple[list[ChatMessage], list[dict]]:
    """Add Claude Code recap calls that only exist as system events.

    Args:
        events: Input value for normalized adapter processing.
        messages: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    existing_ids = {msg.llm_call_id for msg in messages if msg.llm_call_id}
    last_prompts_by_leaf = _last_prompts_by_leaf_uuid(events)
    result = list(messages)
    warnings: list[dict] = []
    fallback_model = _last_assistant_model(messages)
    for record_index, ev in enumerate(events, 1):
        if ev.get('type') != 'system' or ev.get('subtype') != 'away_summary':
            continue
        content = str(ev.get('content') or '')
        if not content:
            continue
        call_id = str(ev.get('uuid') or f'away-summary-{len(result) + 1}')
        if last_prompts_by_leaf and call_id not in last_prompts_by_leaf:
            continue
        if call_id in existing_ids:
            continue
        last_prompt = last_prompts_by_leaf.get(call_id, '')
        result.append(
            ChatMessage(
                role='assistant',
                content=content,
                timestamp=str(ev.get('timestamp') or ''),
                model=fallback_model,
                usage=None,
                llm_call_id=call_id,
                request_full=last_prompt,
                stop_reason='away_summary',
            )
        )
        warnings.append(
            {
                'kind': 'away_summary_usage_estimated',
                'message': (
                    'Claude Code away_summary 表示一次 recap LLM call, 本地 JSONL 没有 '
                    'provider usage; usage 由 lastPrompt 和 summary 文本估算.'
                ),
                'record_index': record_index,
                'call_id': call_id,
            }
        )
        existing_ids.add(call_id)
    return result, warnings


def _project_instruction_units(
    summary: SessionSummary, source_path: str
) -> list[ClaudeCodeSourceUnitDraft]:
    """Support normalized adapter processing for _project_instruction_units.

    Args:
        summary: Input value for normalized adapter processing.
        source_path: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    units: list[ClaudeCodeSourceUnitDraft] = []
    root = _project_root(summary, source_path)
    for rel in ('AGENTS.md', 'CLAUDE.md', '.claude/CLAUDE.md'):
        path = root / rel if root else Path(rel)
        if not path.exists() or not path.is_file():
            continue
        try:
            text = path.read_text(encoding='utf-8')
        except OSError:
            continue
        candidate = (
            'system_instructions' if _looks_like_instruction_file(rel, text) else 'repo_context'
        )
        units.append(
            text_unit(
                origin_path=str(path),
                canonical_source_locator=rel,
                unit_type='project_instruction_file',
                candidate=candidate,
                direction='request',
                text=text,
                timestamp='',
                event_order=0,
                label=rel,
                priority=75,
            )
        )
    return units


def _clone_units_for_call(
    drafts: list[ClaudeCodeSourceUnitDraft],
    *,
    event_order: int,
    timestamp: str,
) -> list[ClaudeCodeSourceUnitDraft]:
    """Support normalized adapter processing for _clone_units_for_call.

    Args:
        drafts: Input value for normalized adapter processing.
        event_order: Input value for normalized adapter processing.
        timestamp: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    return [
        ClaudeCodeSourceUnitDraft(
            origin_path=d.origin_path,
            canonical_source_locator=d.canonical_source_locator,
            unit_type=d.unit_type,
            candidate=d.candidate,
            direction=d.direction,
            event_order=event_order,
            part_index=d.part_index,
            byte_range=d.byte_range,
            text=d.text,
            payload=d.payload,
            timestamp=timestamp,
            label=d.label,
            priority=d.priority,
            sub_source=d.sub_source,
            source_candidate=d.source_candidate,
            diagnostics=list(d.diagnostics),
        )
        for d in drafts
    ]


def _history_sequence_name(scope: str, subagent_id: str) -> str:
    """Support normalized adapter processing for _history_sequence_name.

    Args:
        scope: Input value for normalized adapter processing.
        subagent_id: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    safe_scope = _safe_sequence_part(scope or 'main')
    safe_subagent = _safe_sequence_part(subagent_id or 'main')
    return f'{safe_scope}:{safe_subagent}:conversation_history'


def _safe_sequence_part(value: str) -> str:
    """Support normalized adapter processing for _safe_sequence_part.

    Args:
        value: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    return re.sub(r'[^A-Za-z0-9_.:-]+', '-', value or 'main')[:120]


def _history_source_unit(candidate: str, unit: dict) -> ClaudeCodeSourceUnitDraft:
    """Support normalized adapter processing for _history_source_unit.

    Args:
        candidate: Input value for normalized adapter processing.
        unit: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    text = str(unit.get('text') or '')
    payload = unit.get('payload') if 'payload' in unit else None
    if text:
        return text_unit(
            origin_path=f'conversation_history.{candidate}',
            unit_type=f'prior_{candidate}',
            candidate='conversation_history',
            direction='request',
            text=text,
            timestamp=str(unit.get('timestamp') or ''),
            event_order=int(unit.get('event_order') or 0),
            label=str(unit.get('label') or candidate),
            priority=40,
            sub_source=candidate,
            source_candidate=candidate,
        )
    return payload_unit(
        origin_path=f'conversation_history.{candidate}',
        unit_type=f'prior_{candidate}',
        candidate='conversation_history',
        direction='request',
        payload=payload
        if payload is not None
        else {
            'source_id': unit.get('source_id', ''),
            'unit_type': unit.get('unit_type', ''),
        },
        timestamp=str(unit.get('timestamp') or ''),
        event_order=int(unit.get('event_order') or 0),
        label=str(unit.get('label') or candidate),
        priority=40,
        sub_source=candidate,
        source_candidate=candidate,
    )


def _catalog_rank(unit: dict) -> tuple[int, int]:
    """Support normalized adapter processing for _catalog_rank.

    Args:
        unit: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    return (int(unit.get('priority') or 0), -int(unit.get('event_order') or 0))


def _session_payload(summary: SessionSummary) -> dict:
    """Support normalized adapter processing for _session_payload.

    Args:
        summary: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    return {
        'session_key': f'claude_code:{summary.session_id}',
        'session_id': summary.session_id,
        'title': _truncate_text(summary.title, 160),
        'agent': 'claude_code',
        'model': summary.model,
        'cwd': summary.cwd,
        'started_at': summary.started_at,
        'ended_at': summary.ended_at,
        'git_branch': summary.git_branch,
        'source': summary.source,
        'project_key': summary.project_key,
        'project_name': summary.project_name,
    }


def _usage_from_message(msg: ChatMessage) -> dict:
    """Support normalized adapter processing for _usage_from_message.

    Args:
        msg: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    usage = msg.usage if isinstance(msg.usage, dict) else {}
    if usage:
        fresh = _int(usage.get('input_tokens'))
        cache_read = _int(usage.get('cache_read_input_tokens') or usage.get('cached_input_tokens'))
        cache_write = _int(
            usage.get('cache_creation_input_tokens') or usage.get('cache_write_input_tokens')
        )
        output = _int(usage.get('output_tokens'))
        return {
            'fresh': fresh,
            'cache_read': cache_read,
            'cache_write': cache_write,
            'output': output,
            'total': fresh + cache_read + cache_write + output,
        }
    fresh = _estimate_tokens(msg.request_full)
    output = _estimate_tokens(msg.content)
    return {
        'fresh': fresh,
        'cache_read': 0,
        'cache_write': 0,
        'output': output,
        'total': fresh + output,
        'usage_source': {
            'kind': 'estimated',
            'method': 'chars_div_4',
            'reason': 'provider_usage_missing',
        },
    }


def _tools_for_message(
    msg: ChatMessage, tool_by_id: dict[str, ToolCall], round_id: int
) -> list[dict]:
    """Support normalized adapter processing for _tools_for_message.

    Args:
        msg: Input value for normalized adapter processing.
        tool_by_id: Input value for normalized adapter processing.
        round_id: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    tools: list[dict] = []
    for idx, raw in enumerate(msg.tool_calls or [], 1):
        tool_id = str(raw.get('id') or raw.get('tool_use_id') or f'{msg.llm_call_id}-tool-{idx}')
        tool = tool_by_id.get(tool_id)
        if tool is None:
            tool = ToolCall(
                name=str(raw.get('name') or 'tool'), timestamp=msg.timestamp, tool_use_id=tool_id
            )
        tools.append(_tool_payload(tool, round_id))
    return tools


def _tool_payload(tool: ToolCall, round_id: int) -> dict:
    """Support normalized adapter processing for _tool_payload.

    Args:
        tool: Input value for normalized adapter processing.
        round_id: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    payload: dict[str, Any] = {
        'tool_call_id': tool.tool_use_id or f'tool-{round_id}',
        'name': tool.name,
        'scope': tool.scope,
        'exit_code': tool.exit_code,
        'duration_ms': int(tool.duration_ms or 0),
        'files_touched': list(tool.files_touched or []),
        'parent_tool_use_id': tool.parent_tool_use_id,
        'subagent_id': tool.subagent_id,
    }
    if tool.status and tool.status != 'completed':
        payload['status'] = tool.status
    return payload


def _subagent_steps_for_tools(  # noqa: PLR0913 - Subagent step records need parent call context.
    *,
    adapter: ClaudeCodeNormalizationAdapter,
    summary: SessionSummary,
    source_path: str,
    round_id: int,
    tools: list[dict],
    subagent_by_parent: dict[str, SubagentRun],
) -> list[dict]:
    """Support normalized adapter processing for _subagent_steps_for_tools.

    Args:
        adapter: Input value for normalized adapter processing.
        summary: Input value for normalized adapter processing.
        source_path: Input value for normalized adapter processing.
        round_id: Input value for normalized adapter processing.
        tools: Input value for normalized adapter processing.
        subagent_by_parent: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    steps: list[dict] = []
    for tool in tools:
        parent_tool_id = tool.get('tool_call_id', '')
        run = subagent_by_parent.get(parent_tool_id)
        if not run:
            continue
        run_summary = run.get('summary') or {}
        sub_rounds = adapter._build_rounds(
            summary=summary,
            messages=run.get('messages') or [],
            tool_calls=run.get('tool_calls') or [],
            source_path=source_path,
            scope='subagent',
            subagent_id=run_summary.get('agent_id', ''),
            parent_tool_use_id=parent_tool_id,
            subagent_runs=[],
        )
        for sub_round in sub_rounds:
            sub_round['round_key'] = f'R{round_id}.{sub_round["round_id"]}'
        tool['subagent_id'] = run_summary.get('agent_id', '')
        tool['subagent_summary'] = run_summary
        tool['sub_round_count'] = len(sub_rounds)
        steps.append(
            {
                'type': 'subagent_run',
                'step_id': f'R{round_id}-subagent-{run_summary.get("agent_id") or parent_tool_id}',
                'parent_tool_call_id': parent_tool_id,
                'subagent_id': run_summary.get('agent_id', ''),
                'subagent_type': run_summary.get('agent_type', ''),
                'description': run_summary.get('description', ''),
                'sub_rounds': sub_rounds,
            }
        )
    return steps


def _steps_for_round(
    *, timestamp: str, tools: list[dict], subagent_steps: list[dict]
) -> list[dict]:
    """Support normalized adapter processing for _steps_for_round.

    Args:
        timestamp: Input value for normalized adapter processing.
        tools: Input value for normalized adapter processing.
        subagent_steps: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    steps: list[dict] = []
    if tools:
        steps.append(
            {
                'type': 'tool_batch',
                'started_at': timestamp,
                'ended_at': timestamp,
                'duration_ms': sum(int(t.get('duration_ms') or 0) for t in tools),
                'tools': tools,
            }
        )
    steps.extend(subagent_steps)
    return steps


def _subagent_runs_by_parent(
    tool_calls: list[ToolCall], subagent_runs: list[SubagentRun]
) -> dict[str, SubagentRun]:
    """Support normalized adapter processing for _subagent_runs_by_parent.

    Args:
        tool_calls: Input value for normalized adapter processing.
        subagent_runs: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    by_id = {(run.get('summary') or {}).get('agent_id', ''): run for run in subagent_runs}
    result: dict[str, SubagentRun] = {}
    for tc in tool_calls:
        if tc.name != 'Agent' or not tc.tool_use_id or not tc.subagent_id:
            continue
        run = by_id.get(tc.subagent_id)
        if run:
            result[tc.tool_use_id] = run
    return result


def _parent_tool_for_subagent(tool_calls: list[ToolCall], run: SubagentRun) -> str:
    """Support normalized adapter processing for _parent_tool_for_subagent.

    Args:
        tool_calls: Input value for normalized adapter processing.
        run: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    agent_id = (run.get('summary') or {}).get('agent_id', '')
    for tc in tool_calls:
        if tc.subagent_id == agent_id:
            return tc.tool_use_id
    return ''


def _tool_result_ids_from_request(request_text: str) -> list[str]:
    """Support normalized adapter processing for _tool_result_ids_from_request.

    Args:
        request_text: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    ids: list[str] = []
    for segment in _request_segments(request_text):
        parsed = _parse_tool_result_segment(segment)
        if parsed and parsed[0]:
            ids.append(parsed[0])
    return ids


def _tool_call_ids_from_message(msg: ChatMessage, tools: list[dict]) -> list[str]:
    """Support normalized adapter processing for _tool_call_ids_from_message.

    Args:
        msg: Input value for normalized adapter processing.
        tools: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    ids: list[str] = []
    for block in msg.content_blocks or []:
        if isinstance(block, dict) and block.get('type') == 'tool_use' and block.get('id'):
            ids.append(str(block['id']))
    known = set(ids)
    for tool in tools:
        tid = tool.get('tool_call_id', '')
        if tid and tid not in known:
            ids.append(str(tid))
    return ids


def _request_segments(text: str) -> list[str]:
    """Support normalized adapter processing for _request_segments.

    Args:
        text: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    return [part.strip() for part in re.split(r'\n{2,}', text or '') if part.strip()]


def _parse_tool_result_segment(segment: str) -> tuple[str, str] | None:
    """Support normalized adapter processing for _parse_tool_result_segment.

    Args:
        segment: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    match = re.match(r'^Tool result for ([^:\n]+):\n?(?P<body>.*)$', segment, re.DOTALL)
    if not match:
        return None
    return str(match.group(1) or ''), str(match.group('body') or '').strip()


def _current_user_index_for_call(messages: list[ChatMessage]) -> int:
    """Support normalized adapter processing for _current_user_index_for_call.

    Args:
        messages: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    last_assistant = -1
    for idx in range(len(messages) - 1, -1, -1):
        if messages[idx].role == 'assistant':
            last_assistant = idx
            break
    for idx in range(len(messages) - 1, -1, -1):
        if messages[idx].role == 'user' and idx > last_assistant:
            return idx
    return -1


def _matches_current_user(segment: str, messages: list[ChatMessage], index: int) -> bool:
    """Support normalized adapter processing for _matches_current_user.

    Args:
        segment: Input value for normalized adapter processing.
        messages: Input value for normalized adapter processing.
        index: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    if index < 0:
        return False
    return _normalize_ws(segment) == _normalize_ws(messages[index].content)


def _project_root(summary: SessionSummary, source_path: str) -> Path | None:
    """Support normalized adapter processing for _project_root.

    Args:
        summary: Input value for normalized adapter processing.
        source_path: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    for candidate in (
        summary.cwd,
        summary.project_key,
        str(Path(source_path).parent if source_path else ''),
    ):
        if not candidate:
            continue
        try:
            path = Path(candidate)
            if path.exists() and path.is_dir():
                return path
        except OSError:
            continue
    return None


def _looks_like_instruction_file(rel: str, text: str) -> bool:
    """Support normalized adapter processing for _looks_like_instruction_file.

    Args:
        rel: Input value for normalized adapter processing.
        text: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    rel_lower = rel.lower()
    sample = text[:2000].lower()
    return any(name in rel_lower for name in ('agents.md', 'claude.md')) or any(
        word in sample for word in ('instruction', '规则', 'system', 'agent')
    )


def _last_prompts_by_leaf_uuid(events: list[dict]) -> dict[str, str]:
    """Support normalized adapter processing for _last_prompts_by_leaf_uuid.

    Args:
        events: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    return {
        str(ev.get('leafUuid') or ''): str(ev.get('lastPrompt') or '')
        for ev in events
        if ev.get('type') == 'last-prompt' and ev.get('leafUuid')
    }


def _last_assistant_model(messages: list[ChatMessage]) -> str:
    """Support normalized adapter processing for _last_assistant_model.

    Args:
        messages: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    for msg in reversed(messages):
        if msg.role == 'assistant' and msg.model:
            return msg.model
    return ''


def _truncate_text(text: str, limit: int) -> str:
    """Support normalized adapter processing for _truncate_text.

    Args:
        text: Input value for normalized adapter processing.
        limit: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    value = str(text or '')
    return value if len(value) <= limit else value[:limit]


def _normalize_ws(text: str) -> str:
    """Support normalized adapter processing for _normalize_ws.

    Args:
        text: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    return re.sub(r'\s+', ' ', text or '').strip()


def _int(value: object) -> int:
    """Support normalized adapter processing for _int.

    Args:
        value: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    try:
        if value is None:
            return 0
        return int(value)
    except (TypeError, ValueError):
        return 0


def _estimate_tokens(text: object) -> int:
    """Support normalized adapter processing for _estimate_tokens.

    Args:
        text: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    value = _stringify(text).strip()
    if not value:
        return 0
    return max(1, (len(value) + 3) // 4)


def _stringify(value: object) -> str:
    """Support normalized adapter processing for _stringify.

    Args:
        value: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    if value is None:
        return ''
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return '\n'.join(_stringify(v) for v in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)
