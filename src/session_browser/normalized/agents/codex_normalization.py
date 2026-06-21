"""Convert Codex rollout JSONL payloads into normalized session records.

Codex session sources call this adapter with parsed rollout events or a rollout
file path. It owns the boundary from Codex session payloads, response items, token
events, and child rollout metadata into normalized call records, source units,
tool steps, and parse warnings.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

from session_browser.domain.subagent_models import SubagentRun, SubagentSummary
from session_browser.domain.token_normalizers.codex_token_normalizer import (
    CODEX_USAGE_FIELDS,
    codex_is_duplicate_cumulative,
    codex_usage_delta,
    extract_codex_usage,
    int_or_zero,
)
from session_browser.normalized.agents.codex_parts import (
    CodexSourceUnitDraft,
    draft_to_catalog_unit,
    hydrate_source_units,
    payload_unit,
    split_codex_prompt_text,
    text_unit,
)
from session_browser.normalized.semantic import build_normalized_session_model
from session_browser.sources.jsonl_reader import parse_jsonl_events


def parse_codex_rollout_file(
    path: str | Path,
    thread_info: dict | None = None,
) -> dict:
    """Parse one Codex rollout JSONL file into normalized session records.

    Triggered by Codex file loading with a rollout path and optional thread metadata. It
    reads the rollout payload and emits the semantic normalized session boundary.

    Args:
        path: Input value for normalized adapter processing.
        thread_info: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    rollout_path = Path(path)
    events, _ = parse_jsonl_events(rollout_path)
    session_id = (thread_info or {}).get('id') or _session_id_from_path(str(rollout_path))
    subagent_runs = _parse_subagent_rollouts_for_parent(rollout_path, session_id)
    return parse_codex_events(
        events,
        source_path=str(rollout_path),
        thread_info=thread_info or {},
        subagent_runs=subagent_runs,
    )


def parse_codex_events(
    events: list[dict],
    source_path: str = '',
    thread_info: dict | None = None,
    subagent_runs: list[SubagentRun] | None = None,
) -> dict:
    """Convert parsed Codex rollout events into the normalized contract.

    Triggered when Codex events are already loaded. It converts event payloads, response
    items, token events, and subagent metadata into normalized records.

    Args:
        events: Input value for normalized adapter processing.
        source_path: Input value for normalized adapter processing.
        thread_info: Input value for normalized adapter processing.
        subagent_runs: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    thread_info = thread_info or {}
    state = _CodexBuildState(
        source_path=source_path,
        thread_info=thread_info,
        subagent_runs=subagent_runs or [],
    )

    for order, event in enumerate(events, 1):
        if not isinstance(event, dict):
            continue
        state.event_order = order
        etype = event.get('type', '')
        payload = event.get('payload') if isinstance(event.get('payload'), dict) else {}
        timestamp = str(event.get('timestamp') or '')

        if etype == 'session_meta':
            state.accept_session_meta(payload, timestamp)
        elif etype == 'turn_context':
            state.accept_turn_context(payload, timestamp)
        elif etype == 'compacted':
            state.accept_compacted(payload, timestamp)
        elif etype == 'response_item':
            state.accept_response_item(payload, timestamp)
        elif etype == 'event_msg':
            state.accept_event_msg(payload, timestamp)

    state.finish()
    return state.to_normalized()


class _CodexBuildState:
    """Coordinate _CodexBuildState normalized adapter state."""

    def __init__(  # noqa: PLR0913 - Build state carries source and subagent context explicitly.
        self,
        source_path: str,
        thread_info: dict,
        *,
        subagent_runs: list[SubagentRun] | None = None,
        scope: str = 'main',
        subagent_id: str = '',
        parent_tool_use_id: str = '',
        parent_tool_name: str = '',
        call_id_prefix: str = 'codex-call-',
    ) -> None:
        """Initialize adapter state for one normalized session build.

        Args:
            source_path: Input value for normalized adapter processing.
            thread_info: Input value for normalized adapter processing.
            subagent_runs: Input value for normalized adapter processing.
            scope: Input value for normalized adapter processing.
            subagent_id: Input value for normalized adapter processing.
            parent_tool_use_id: Input value for normalized adapter processing.
            parent_tool_name: Input value for normalized adapter processing.
            call_id_prefix: Input value for normalized adapter processing.
        """  # noqa: RUF100  # noqa: DOC301,DOC101,DOC103
        self.source_path = source_path
        self.thread_info = thread_info
        self.subagent_runs = subagent_runs or []
        self.subagent_runs_by_id = {
            str((run.get('summary') or {}).get('agent_id') or ''): run
            for run in self.subagent_runs
            if run.get('summary')
        }
        self.scope = scope
        self.subagent_id = subagent_id
        self.parent_tool_use_id = parent_tool_use_id
        self.parent_tool_name = parent_tool_name
        self.call_id_prefix = call_id_prefix
        self.event_order = 0
        self.session_meta: dict = {}
        self.latest_turn_context: dict = {}
        self.current_turn_id = ''
        self.first_ts = ''
        self.last_ts = ''

        self.pending_tool_results: list[dict] = []
        self.segment_response_items: list[dict] = []
        self.segment_tool_events: list[dict] = []
        self.persistent_request_units: list[CodexSourceUnitDraft] = []
        self.current_user_units: list[CodexSourceUnitDraft] = []
        self.conversation_history_units: list[CodexSourceUnitDraft] = []
        self.pending_tool_result_units: list[CodexSourceUnitDraft] = []
        self.segment_tool_result_units: list[CodexSourceUnitDraft] = []
        self.response_units: list[CodexSourceUnitDraft] = []
        self.source_unit_catalog: dict[str, dict] = {}
        self.source_unit_sequences: dict[str, list[str]] = {
            'persistent_request': [],
            'conversation_history': [],
        }
        self.source_unit_sequence_sets: dict[str, set[str]] = {
            'persistent_request': set(),
            'conversation_history': set(),
        }
        self._persistent_request_units_flushed = 0

        self.rounds: list[dict] = []
        self.parse_warnings: list[dict] = []
        self.previous_cumulative_usage: dict | None = None
        self.token_fragments: list[dict] = []

    def accept_session_meta(self, payload: dict, timestamp: str) -> None:
        """Support normalized adapter processing for accept_session_meta.

        Args:
            payload: Input value for normalized adapter processing.
            timestamp: Input value for normalized adapter processing.
        """
        self._touch(timestamp)
        self.session_meta = payload or {}
        base = payload.get('base_instructions')
        base_text = ''
        if isinstance(base, dict):
            base_text = str(base.get('text') or '')
        elif isinstance(base, str):
            base_text = base
        if base_text:
            self.persistent_request_units.append(
                text_unit(
                    origin_path='session_meta.payload.base_instructions.text',
                    unit_type='base_instructions_text',
                    candidate='system_instructions',
                    direction='request',
                    text=base_text,
                    timestamp=timestamp,
                    event_order=self.event_order,
                    label='base instructions',
                    priority=70,
                )
            )

    def accept_turn_context(self, payload: dict, timestamp: str) -> None:
        """Support normalized adapter processing for accept_turn_context.

        Args:
            payload: Input value for normalized adapter processing.
            timestamp: Input value for normalized adapter processing.
        """
        self._touch(timestamp)
        self.latest_turn_context = payload or {}
        self.current_turn_id = str(payload.get('turn_id') or self.current_turn_id)

    def accept_compacted(self, payload: dict, timestamp: str) -> None:
        """Support normalized adapter processing for accept_compacted.

        Args:
            payload: Input value for normalized adapter processing.
            timestamp: Input value for normalized adapter processing.
        """
        self._touch(timestamp)

    def accept_response_item(self, payload: dict, timestamp: str) -> None:
        """Support normalized adapter processing for accept_response_item.

        Args:
            payload: Input value for normalized adapter processing.
            timestamp: Input value for normalized adapter processing.
        """
        self._touch(timestamp)
        ptype = payload.get('type', '')
        if ptype == 'message' and payload.get('role') in {'developer', 'system'}:
            self._accept_instruction_message(payload, timestamp)
            return
        if ptype == 'message' and payload.get('role') == 'user':
            self._accept_user_request_message(payload, timestamp)
            return
        if ptype == 'message' and payload.get('role') == 'assistant':
            self._accept_assistant_message(payload, timestamp)
        elif ptype == 'reasoning':
            self.response_units.append(
                payload_unit(
                    origin_path='response_item.reasoning',
                    unit_type='reasoning_output',
                    candidate='reasoning_output',
                    direction='response',
                    payload=_reasoning_candidate_payload(payload),
                    timestamp=timestamp,
                    event_order=self.event_order,
                    label='reasoning output',
                )
            )
        elif ptype in {'function_call', 'custom_tool_call', 'tool_search_call', 'web_search_call'}:
            self.response_units.append(
                payload_unit(
                    origin_path=f'response_item.{ptype}',
                    unit_type='model_tool_call',
                    candidate='tool_calls',
                    direction='response',
                    payload=_tool_call_candidate_payload(payload),
                    timestamp=timestamp,
                    event_order=self.event_order,
                    label=str(payload.get('name') or ptype),
                )
            )
        elif ptype in {'function_call_output', 'custom_tool_call_output', 'tool_search_output'}:
            unit = _tool_result_source_unit(payload, timestamp, self.event_order)
            if unit:
                self.segment_tool_result_units.append(unit)
        self.segment_response_items.append(
            {
                'timestamp': timestamp,
                'event_order': self.event_order,
                'payload': payload,
            }
        )

    def accept_event_msg(self, payload: dict, timestamp: str) -> None:
        """Support normalized adapter processing for accept_event_msg.

        Args:
            payload: Input value for normalized adapter processing.
            timestamp: Input value for normalized adapter processing.
        """
        self._touch(timestamp)
        ptype = payload.get('type', '')
        if ptype == 'task_started':
            self.current_turn_id = str(payload.get('turn_id') or self.current_turn_id)
            return
        if ptype == 'user_message':
            text = _event_user_message_text(payload)
            if text:
                self.current_user_units.append(
                    text_unit(
                        origin_path='event_msg.user_message.message',
                        unit_type='current_user_text',
                        candidate='user_input',
                        direction='request',
                        text=text,
                        timestamp=timestamp,
                        event_order=self.event_order,
                        label='current user input',
                        priority=80,
                    )
                )
            return
        if ptype == 'agent_message':
            return
        if ptype == 'token_count':
            self._close_llm_call(payload, timestamp)
            return
        if ptype in {
            'function_call_output',
            'custom_tool_call_output',
            'exec_command_end',
            'mcp_tool_call_end',
            'patch_apply_end',
            'web_search_end',
            'view_image_tool_call',
        }:
            self.segment_tool_events.append(
                {
                    'timestamp': timestamp,
                    'event_order': self.event_order,
                    'payload': payload,
                }
            )
            return

    def _accept_instruction_message(self, payload: dict, timestamp: str) -> None:
        """Support normalized adapter processing for _accept_instruction_message.

        Args:
            payload: Input value for normalized adapter processing.
            timestamp: Input value for normalized adapter processing.
        """
        texts = _message_texts(payload)
        role = str(payload.get('role') or '')
        for idx, text in enumerate(texts):
            self.persistent_request_units.extend(
                split_codex_prompt_text(
                    text=text,
                    origin_path=f'response_item.message(role={role}).content[{idx}].text',
                    timestamp=timestamp,
                    event_order=self.event_order,
                    part_index=idx,
                    default_candidate='system_instructions',
                    default_unit_type='prompt_plain_text',
                    priority=68,
                )
            )

    def _accept_user_request_message(self, payload: dict, timestamp: str) -> None:
        """Support normalized adapter processing for _accept_user_request_message.

        Args:
            payload: Input value for normalized adapter processing.
            timestamp: Input value for normalized adapter processing.
        """
        texts = _message_texts(payload)
        for idx, text in enumerate(texts):
            self.persistent_request_units.extend(
                split_codex_prompt_text(
                    text=text,
                    origin_path=f'response_item.message(role=user).content[{idx}].text',
                    timestamp=timestamp,
                    event_order=self.event_order,
                    part_index=idx,
                    default_candidate=None,
                    priority=55,
                )
            )

    def _accept_assistant_message(self, payload: dict, timestamp: str) -> None:
        """Support normalized adapter processing for _accept_assistant_message.

        Args:
            payload: Input value for normalized adapter processing.
            timestamp: Input value for normalized adapter processing.
        """
        for part in payload.get('content') or []:
            if not isinstance(part, dict):
                continue
            text = str(part.get('text') or part.get('content') or '')
            if not text.strip():
                continue
            ptype = str(part.get('type') or '')
            if _looks_structured_output(text, ptype):
                self.response_units.append(
                    text_unit(
                        origin_path='response_item.message(role=assistant).content[].text',
                        unit_type='structured_output',
                        candidate='structured_output',
                        direction='response',
                        text=text,
                        timestamp=timestamp,
                        event_order=self.event_order,
                        label=ptype or 'structured output',
                    )
                )
            else:
                self.response_units.append(
                    text_unit(
                        origin_path='response_item.message(role=assistant).content[].text',
                        unit_type='assistant_output_text',
                        candidate='assistant_output',
                        direction='response',
                        text=text,
                        timestamp=timestamp,
                        event_order=self.event_order,
                        label=ptype or 'assistant output',
                    )
                )

    def finish(self) -> None:
        """Support normalized adapter processing for finish."""
        if self.segment_response_items:
            self.parse_warnings.append(
                {
                    'kind': 'unclosed_response_segment',
                    'message': 'Response items at end of file had no following token_count event.',
                    'event_order': self.event_order,
                }
            )

    def to_normalized(self) -> dict:
        """Support normalized adapter processing for to_normalized.

        Returns:
            Normalized adapter result.
        """
        session_id = (
            self.thread_info.get('id')
            or self.session_meta.get('id')
            or _session_id_from_path(self.source_path)
        )
        title = self.thread_info.get('title') or self.thread_info.get('first_user_message') or ''
        model = (
            self.thread_info.get('model')
            or self.latest_turn_context.get('model')
            or self.session_meta.get('model')
            or self.session_meta.get('model_provider')
            or ''
        )
        cwd = (
            self.thread_info.get('cwd')
            or self.session_meta.get('cwd')
            or self.latest_turn_context.get('cwd')
            or ''
        )
        session = {
            'session_key': f'codex:{session_id}',
            'session_id': session_id,
            'title': _truncate_text(title, 160),
            'agent': 'codex',
            'model': model,
            'cwd': cwd,
            'started_at': self.first_ts,
            'ended_at': self.last_ts,
            'git_branch': self.thread_info.get('git_branch')
            or (self.session_meta.get('git') or {}).get('branch', ''),
            'source': self.thread_info.get('source') or self.session_meta.get('source') or '',
        }
        source_files = [
            {
                'role': 'codex_rollout',
                'path': self.source_path,
            }
        ]
        for run in self.subagent_runs:
            summary = run.get('summary') or {}
            source_files.append(
                {
                    'role': 'subagent_session',
                    'path': str(run.get('path') or ''),
                    'subagent_id': str(summary.get('agent_id') or ''),
                    'parent_tool_use_id': str(run.get('parent_tool_use_id') or ''),
                }
            )
        normalized = build_normalized_session_model(
            agent='codex',
            session=session,
            source_files=source_files,
            call_drafts=self.rounds,
            parse_warnings=self.parse_warnings,
        )
        _annotate_subagent_calls(normalized, self.rounds)
        catalog = self._merged_source_unit_catalog()
        if catalog:
            normalized['source_unit_catalog'] = catalog
            normalized['source_unit_sequences'] = self.source_unit_sequences
        if self.token_fragments:
            normalized['diagnostics'].extend(self.token_fragments)
        return normalized

    def _merged_source_unit_catalog(self) -> dict[str, dict]:
        """Support normalized adapter processing for _merged_source_unit_catalog.

        Returns:
            Normalized adapter result.
        """
        catalog = dict(self.source_unit_catalog)
        for run in self.subagent_runs:
            child_catalog = run.get('source_unit_catalog')
            if not isinstance(child_catalog, dict):
                continue
            for key, unit in child_catalog.items():
                if isinstance(unit, dict):
                    existing = catalog.get(str(key))
                    if existing is None or _catalog_rank(unit) > _catalog_rank(existing):
                        catalog[str(key)] = unit
        return catalog

    def _close_llm_call(self, token_payload: dict, timestamp: str) -> None:
        """Support normalized adapter processing for _close_llm_call.

        Args:
            token_payload: Input value for normalized adapter processing.
            timestamp: Input value for normalized adapter processing.
        """
        fragment = self._token_fragment(token_payload, timestamp)
        if fragment.get('status') == 'duplicate_token_count':
            self.token_fragments.append(fragment)
            return

        usage = _extract_token_count_usage(token_payload)
        if not usage.get('source_total_tokens') and fragment.get('cumulative_delta'):
            delta = fragment['cumulative_delta']
            usage = {
                'input_tokens': delta.get('input_tokens', 0),
                'cached_input_tokens': delta.get('cached_input_tokens', 0),
                'output_tokens': delta.get('output_tokens', 0),
                'reasoning_output_tokens': delta.get('reasoning_output_tokens', 0),
                'source_total_tokens': delta.get('total_tokens', 0),
                'model_context_window': 0,
            }
        if fragment.get('status') == 'cumulative_reset_or_invalid':
            usage['quality_status'] = 'cumulative_reset_or_invalid'
            self.token_fragments.append(fragment)
        if not self.segment_response_items:
            self.parse_warnings.append(
                {
                    'kind': 'token_count_without_response_items',
                    'message': 'token_count had no preceding response items.',
                    'event_order': self.event_order,
                }
            )

        round_id = len(self.rounds) + 1
        call_id = f'{self.call_id_prefix}{round_id:04d}'
        request_tool_results = list(self.pending_tool_results)
        attribution_snapshot = self._freeze_attribution_snapshot(call_id)

        tools = _collect_tools(self.segment_response_items, self.segment_tool_events)

        round_obj = _build_round(
            round_id=round_id,
            call_id=call_id,
            turn_id=self.current_turn_id,
            timestamp=timestamp,
            model=(
                self.latest_turn_context.get('model')
                or self.thread_info.get('model')
                or self.session_meta.get('model')
                or self.session_meta.get('model_provider')
                or ''
            ),
            usage=usage,
            request_tool_results=request_tool_results,
            tools=tools,
            subagent_runs_by_id=self.subagent_runs_by_id,
            scope=self.scope,
            subagent_id=self.subagent_id,
            parent_tool_use_id=self.parent_tool_use_id,
            parent_tool_name=self.parent_tool_name,
            source_unit_ref_ranges=attribution_snapshot['source_unit_ref_ranges'],
        )
        self.rounds.append(round_obj)

        self.pending_tool_results = [
            _tool_result_for_next_request(t)
            for t in tools
            if t.get('tool_call_id') and t.get('status') != 'missing'
        ]
        self._advance_candidate_state_after_close(
            call_id,
            attribution_snapshot['new_history_source_refs'],
        )
        self.segment_response_items = []
        self.segment_tool_events = []
        self.segment_tool_result_units = []
        self.response_units = []

    def _freeze_attribution_snapshot(self, call_id: str) -> dict:
        """Support normalized adapter processing for _freeze_attribution_snapshot.

        Args:
            call_id: Input value for normalized adapter processing.

        Returns:
            Normalized adapter result.
        """
        new_persistent_units = self.persistent_request_units[
            self._persistent_request_units_flushed :
        ]
        self._catalog_refs_for_drafts(
            new_persistent_units,
            sequence_name='persistent_request',
        )
        self._persistent_request_units_flushed = len(self.persistent_request_units)
        history_count = len(self.source_unit_sequences['conversation_history'])
        pending_refs = self._catalog_refs_for_drafts(self.pending_tool_result_units)
        current_refs = self._catalog_refs_for_drafts(self.current_user_units)
        response_refs = self._catalog_refs_for_drafts(self.response_units)

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
                    'sequence': 'conversation_history',
                    'start': 0,
                    'end': history_count,
                }
            )
        if pending_refs:
            ranges.append({'refs': pending_refs, 'role': 'pending_tool_results'})
        if current_refs:
            ranges.append({'refs': current_refs, 'role': 'current'})
        if response_refs:
            ranges.append({'refs': response_refs, 'role': 'response'})

        return {
            'source_unit_ref_ranges': ranges,
            'new_history_source_refs': pending_refs + current_refs + response_refs,
        }

    def _advance_candidate_state_after_close(self, call_id: str, source_refs: list[str]) -> None:
        """Support normalized adapter processing for _advance_candidate_state_after_close.

        Args:
            call_id: Input value for normalized adapter processing.
            source_refs: Input value for normalized adapter processing.
        """
        source_units = hydrate_source_units(call_id, self._catalog_units_for_refs(source_refs))
        history_drafts: list[CodexSourceUnitDraft] = []
        for unit in source_units:
            candidate = str(unit.get('candidate') or '')
            if candidate not in {
                'user_input',
                'assistant_output',
                'reasoning_output',
                'tool_calls',
                'structured_output',
                'tool_results',
                'tool_definitions',
            }:
                continue
            history_drafts.append(_history_source_unit(candidate, unit))
        history_refs = self._catalog_refs_for_drafts(
            history_drafts,
            sequence_name='conversation_history',
        )
        if history_refs:
            # Keep the draft list empty; future calls refer to the sequence range instead.
            self.conversation_history_units = []
        self.current_user_units = []
        self.pending_tool_result_units = list(self.segment_tool_result_units)

    def _catalog_refs_for_drafts(
        self,
        drafts: list[CodexSourceUnitDraft],
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

    def _token_fragment(self, token_payload: dict, timestamp: str) -> dict:
        """Support normalized adapter processing for _token_fragment.

        Args:
            token_payload: Input value for normalized adapter processing.
            timestamp: Input value for normalized adapter processing.

        Returns:
            Normalized adapter result.
        """
        info = token_payload.get('info') if isinstance(token_payload.get('info'), dict) else {}
        last_usage = info.get('last_token_usage') or token_payload.get('last_token_usage') or {}
        cumulative_usage = (
            info.get('total_token_usage') or token_payload.get('total_token_usage') or {}
        )
        record = {
            'record_index': self.event_order,
            'timestamp': timestamp,
            'last_total_tokens': _int(last_usage.get('total_tokens'))
            if isinstance(last_usage, dict)
            else 0,
            'cumulative_total_tokens': _int(cumulative_usage.get('total_tokens'))
            if isinstance(cumulative_usage, dict)
            else 0,
        }
        if not isinstance(cumulative_usage, dict):
            return {
                **record,
                'status': 'fallback_last_usage',
                'contribution': record['last_total_tokens'],
            }

        delta = _token_usage_delta(cumulative_usage, self.previous_cumulative_usage)
        record['cumulative_delta'] = {field: max(delta[field], 0) for field in CODEX_USAGE_FIELDS}
        record['contribution'] = record['cumulative_delta']['total_tokens']

        if codex_is_duplicate_cumulative(cumulative_usage, self.previous_cumulative_usage):
            self.previous_cumulative_usage = cumulative_usage
            return {**record, 'status': 'duplicate_token_count', 'contribution': 0}

        status = 'counted'
        if any(delta[field] < 0 for field in CODEX_USAGE_FIELDS):
            status = 'cumulative_reset_or_invalid'
        self.previous_cumulative_usage = cumulative_usage
        return {**record, 'status': status}

    def _touch(self, timestamp: str) -> None:
        """Support normalized adapter processing for _touch.

        Args:
            timestamp: Input value for normalized adapter processing.
        """
        if timestamp and not self.first_ts:
            self.first_ts = timestamp
        if timestamp:
            self.last_ts = timestamp


def _history_source_unit(candidate: str, unit: dict) -> CodexSourceUnitDraft:
    """Support normalized adapter processing for _history_source_unit.

    Args:
        candidate: Input value for normalized adapter processing.
        unit: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    target_candidate = {
        'reasoning_output': 'reasoning_state',
        'tool_results': 'tool_results',
        'tool_definitions': 'tool_definitions',
    }.get(candidate, 'conversation_history')
    text = str(unit.get('text') or '')
    payload = unit.get('payload') if 'payload' in unit else None
    if text:
        return text_unit(
            origin_path=f'conversation_history.{candidate}',
            unit_type=f'prior_{candidate}',
            candidate=target_candidate,
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
        candidate=target_candidate,
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


def _message_texts(payload: dict) -> list[str]:
    """Support normalized adapter processing for _message_texts.

    Args:
        payload: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    texts: list[str] = []
    for part in payload.get('content') or []:
        if not isinstance(part, dict):
            continue
        text = str(part.get('text') or part.get('content') or '')
        if text.strip():
            texts.append(text)
    return texts


def _event_user_message_text(payload: dict) -> str:
    """Support normalized adapter processing for _event_user_message_text.

    Args:
        payload: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    message = payload.get('message', '')
    if isinstance(message, list):
        return '\n'.join(str(item) for item in message if item is not None)
    return str(message or '')


def _looks_structured_output(text: str, part_type: str) -> bool:
    """Support normalized adapter processing for _looks_structured_output.

    Args:
        text: Input value for normalized adapter processing.
        part_type: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    return part_type in {'json', 'structured', 'structured_output'}


def _reasoning_candidate_payload(payload: dict) -> dict:
    """Support normalized adapter processing for _reasoning_candidate_payload.

    Args:
        payload: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    summary = payload.get('summary') if isinstance(payload.get('summary'), list) else []
    return {
        'summary': _json_safe(summary),
        'has_encrypted_content': bool(payload.get('encrypted_content')),
        'encrypted_content_unavailable': bool(payload.get('encrypted_content')),
    }


def _tool_call_candidate_payload(payload: dict) -> dict:
    """Support normalized adapter processing for _tool_call_candidate_payload.

    Args:
        payload: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    return {
        'type': payload.get('type') or '',
        'call_id': payload.get('call_id') or '',
        'name': payload.get('name') or '',
        'arguments': payload.get('arguments', payload.get('input', '')),
    }


def _tool_result_source_unit(
    payload: dict, timestamp: str, event_order: int
) -> CodexSourceUnitDraft | None:
    """Support normalized adapter processing for _tool_result_source_unit.

    Args:
        payload: Input value for normalized adapter processing.
        timestamp: Input value for normalized adapter processing.
        event_order: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    call_id = str(payload.get('call_id') or '')
    output = payload.get('output')
    tools = payload.get('tools')
    if not call_id and output in (None, '') and not tools:
        return None
    ptype = str(payload.get('type') or '')
    text = output if isinstance(output, str) else ''
    if ptype == 'tool_search_output':
        unit_type = 'request_tool_search_output'
        candidate = 'tool_definitions'
        unit_payload = {
            'call_id': call_id,
            'status': payload.get('status') or '',
            'execution': payload.get('execution') or '',
            'tools': tools if isinstance(tools, list) else [],
        }
        label = call_id or 'tool search output'
        sub_source = 'tool_results'
    else:
        unit_type = 'request_tool_result'
        candidate = 'tool_results'
        unit_payload = {
            'call_id': call_id,
            'output': output,
            'status': payload.get('status') or '',
        }
        label = call_id or 'tool result'
        sub_source = ''
    origin_path = (
        'response_item.tool_search_output.tools'
        if ptype == 'tool_search_output'
        else f'response_item.{payload.get("type")}.output'
    )
    return payload_unit(
        origin_path=origin_path,
        unit_type=unit_type,
        candidate=candidate,
        direction='request',
        payload=unit_payload,
        timestamp=timestamp,
        event_order=event_order,
        label=label,
        priority=80,
        text=text,
        sub_source=sub_source,
    )


def _json_safe(value: object) -> object:
    """Support normalized adapter processing for _json_safe.

    Args:
        value: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except TypeError:
        return str(value)


def _catalog_rank(unit: dict) -> tuple[int, int]:
    """Support normalized adapter processing for _catalog_rank.

    Args:
        unit: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    return (int(unit.get('priority') or 0), -int(unit.get('event_order') or 0))


def _build_round(  # noqa: PLR0913 - Normalized round assembly requires explicit event slices.
    *,
    round_id: int,
    call_id: str,
    turn_id: str,
    timestamp: str,
    model: str,
    usage: dict,
    request_tool_results: list[dict],
    tools: list[dict],
    subagent_runs_by_id: dict[str, SubagentRun],
    scope: str,
    subagent_id: str,
    parent_tool_use_id: str,
    parent_tool_name: str,
    source_unit_ref_ranges: list[dict],
) -> dict:
    """Support normalized adapter processing for _build_round.

    Args:
        round_id: Input value for normalized adapter processing.
        call_id: Input value for normalized adapter processing.
        turn_id: Input value for normalized adapter processing.
        timestamp: Input value for normalized adapter processing.
        model: Input value for normalized adapter processing.
        usage: Input value for normalized adapter processing.
        request_tool_results: Input value for normalized adapter processing.
        tools: Input value for normalized adapter processing.
        subagent_runs_by_id: Input value for normalized adapter processing.
        scope: Input value for normalized adapter processing.
        subagent_id: Input value for normalized adapter processing.
        parent_tool_use_id: Input value for normalized adapter processing.
        parent_tool_name: Input value for normalized adapter processing.
        source_unit_ref_ranges: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    fresh_tokens = max(usage['input_tokens'] - usage['cached_input_tokens'], 0)
    token_total = fresh_tokens + usage['cached_input_tokens'] + usage['output_tokens']
    steps = _build_steps(
        timestamp=timestamp,
        tools=tools,
        subagent_runs_by_id=subagent_runs_by_id,
    )
    return {
        'round_id': round_id,
        'round_key': f'R{round_id}',
        'main_call': {
            'call_id': call_id,
            'turn_id': turn_id,
            'model': model,
            'timestamp': timestamp,
            'scope': scope,
            'subagent_id': subagent_id,
            'parent_tool_use_id': parent_tool_use_id,
            'parent_tool_name': parent_tool_name,
        },
        'metrics': {
            'tokens': {
                'fresh': fresh_tokens,
                'cache_read': usage['cached_input_tokens'],
                'cache_write': 0,
                'output': usage['output_tokens'],
                'total': token_total,
            },
        },
        'request': {
            'tool_result_ids': [
                t['tool_call_id'] for t in request_tool_results if t.get('tool_call_id')
            ],
        },
        'response': {
            'tool_call_ids': [t['tool_call_id'] for t in tools if t.get('tool_call_id')],
        },
        'source_unit_ref_ranges': source_unit_ref_ranges,
        'steps': steps,
    }


def _extract_token_count_usage(payload: dict) -> dict:
    """Support normalized adapter processing for _extract_token_count_usage.

    Args:
        payload: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    info = payload.get('info') if isinstance(payload.get('info'), dict) else {}
    usage = extract_codex_usage(
        info.get('last_token_usage') or payload.get('last_token_usage') or {}
    )
    return {
        'input_tokens': usage.get('input_tokens', 0),
        'cached_input_tokens': usage.get('cached_input_tokens', 0),
        'output_tokens': usage.get('output_tokens', 0),
        'reasoning_output_tokens': usage.get('reasoning_output_tokens', 0),
        'source_total_tokens': usage.get('total_tokens', 0)
        or usage.get('input_tokens', 0) + usage.get('output_tokens', 0),
        'model_context_window': int_or_zero(info.get('model_context_window')),
    }


def _token_usage_delta(current: dict, previous: dict | None) -> dict:
    """Support normalized adapter processing for _token_usage_delta.

    Args:
        current: Input value for normalized adapter processing.
        previous: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    return codex_usage_delta(current, previous)


def _collect_tools(  # noqa: PLR0912 - Codex tool event variants are normalized in one pass.
    response_items: list[dict], tool_events: list[dict]
) -> list[dict]:
    """Support normalized adapter processing for _collect_tools.

    Args:
        response_items: Input value for normalized adapter processing.
        tool_events: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    calls: list[dict] = []
    outputs: dict[str, dict] = {}
    for item in response_items:
        payload = item['payload']
        ptype = payload.get('type')
        if ptype in {'function_call_output', 'custom_tool_call_output', 'tool_search_output'}:
            call_id = payload.get('call_id') or ''
            if call_id:
                result = outputs.setdefault(call_id, {'observed': True})
                status = str(payload.get('status') or '')
                if status and status != 'completed':
                    result['status'] = status
                output = payload.get('output')
                if output is not None:
                    result['output'] = output
                if ptype == 'tool_search_output' and isinstance(payload.get('tools'), list):
                    result['output'] = {'tools': payload.get('tools') or []}
    for event in tool_events:
        payload = event['payload']
        call_id = payload.get('call_id') or ''
        if not call_id:
            continue
        rich = _tool_event_output(payload)
        if rich:
            outputs.setdefault(call_id, {}).update(rich)

    for item in response_items:
        payload = item['payload']
        ptype = payload.get('type')
        if ptype not in {
            'function_call',
            'custom_tool_call',
            'tool_search_call',
            'web_search_call',
        }:
            continue
        call_id = payload.get('call_id') or f'tool-{len(calls) + 1}'
        name = payload.get('name') or ptype.replace('_call', '')
        result_info = outputs.get(call_id, {})
        status = _tool_status(result_info)
        tool: dict[str, Any] = {
            'tool_call_id': call_id,
            'name': name,
            'exit_code': result_info.get('exit_code'),
            'duration_ms': result_info.get('duration_ms', 0),
        }
        subagent_summary = _subagent_summary_from_tool_result(name, result_info.get('output'))
        if subagent_summary:
            tool['subagent_id'] = subagent_summary['agent_id']
            tool['subagent_summary'] = subagent_summary
        if status != 'completed':
            tool['status'] = status
        calls.append(tool)
    return calls


def _tool_event_output(payload: dict) -> dict:
    """Support normalized adapter processing for _tool_event_output.

    Args:
        payload: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    ptype = payload.get('type')
    if ptype == 'exec_command_end':
        exit_code = payload.get('exit_code')
        result = {
            'observed': True,
            'duration_ms': _duration_ms(payload.get('duration') or {}),
        }
        if exit_code not in (None, 0):
            result['exit_code'] = exit_code
            result['status'] = 'error'
        return result
    if ptype == 'mcp_tool_call_end':
        return {
            'observed': True,
            'duration_ms': _duration_ms(payload.get('duration') or {}),
        }
    if ptype == 'patch_apply_end':
        result = {'observed': True}
        if not payload.get('success'):
            result['status'] = 'error'
        return result
    if ptype == 'web_search_end':
        return {
            'observed': True,
        }
    if ptype == 'view_image_tool_call':
        return {
            'observed': True,
        }
    return {}


def _build_steps(
    *,
    timestamp: str,
    tools: list[dict],
    subagent_runs_by_id: dict[str, SubagentRun],
) -> list[dict]:
    """Support normalized adapter processing for _build_steps.

    Args:
        timestamp: Input value for normalized adapter processing.
        tools: Input value for normalized adapter processing.
        subagent_runs_by_id: Input value for normalized adapter processing.

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
    for tool in tools:
        subagent_id = str(tool.get('subagent_id') or '')
        run = subagent_runs_by_id.get(subagent_id)
        if not subagent_id or not run:
            continue
        run['parent_tool_use_id'] = tool.get('tool_call_id') or ''
        summary = run.get('summary') or {}
        steps.append(
            {
                'type': 'subagent_run',
                'step_id': f'subagent-{subagent_id}',
                'parent_tool_call_id': tool.get('tool_call_id') or '',
                'subagent_id': subagent_id,
                'subagent_type': summary.get('agent_type') or '',
                'description': summary.get('description') or '',
                'sub_rounds': run.get('rounds') or [],
            }
        )
    return steps


def _tool_result_for_next_request(tool: dict) -> dict:
    """Support normalized adapter processing for _tool_result_for_next_request.

    Args:
        tool: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    return {
        'tool_call_id': tool.get('tool_call_id') or '',
    }


def _tool_status(result_info: dict) -> str:
    """Support normalized adapter processing for _tool_status.

    Args:
        result_info: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    if not result_info:
        return 'missing'
    if result_info.get('status') == 'error':
        return 'error'
    exit_code = result_info.get('exit_code')
    if exit_code not in (None, 0):
        return 'error'
    return 'completed'


def _subagent_summary_from_tool_result(name: str, output: object) -> dict:
    """Support normalized adapter processing for _subagent_summary_from_tool_result.

    Args:
        name: Input value for normalized adapter processing.
        output: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    if name != 'spawn_agent':
        return {}
    data = _json_dict(output)
    agent_id = str(data.get('agent_id') or '')
    if not agent_id:
        return {}
    return {
        'agent_id': agent_id,
        'agent_type': str(data.get('agent_role') or data.get('agent_type') or ''),
        'nickname': str(data.get('nickname') or data.get('agent_nickname') or ''),
    }


def _parse_subagent_rollouts_for_parent(
    parent_path: Path, parent_session_id: str
) -> list[SubagentRun]:
    """Support normalized adapter processing for _parse_subagent_rollouts_for_parent.

    Args:
        parent_path: Input value for normalized adapter processing.
        parent_session_id: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    if not parent_session_id or not parent_path.exists():
        return []
    runs: list[SubagentRun] = []
    from session_browser.sources.codex_session_source import get_codex_subagent_child_paths  # noqa: I001,PLC0415 - Lazy import avoids source discovery cycles.

    for candidate in get_codex_subagent_child_paths(parent_path, parent_session_id):
        events, _ = parse_jsonl_events(candidate)
        meta = _first_session_meta(events)
        spawn = _codex_subagent_spawn(meta)
        if spawn.get('parent_thread_id') != parent_session_id:
            continue
        agent_id = str(meta.get('id') or _session_id_from_path(str(candidate)))
        call_prefix = f'codex-subagent-{_safe_id_fragment(agent_id)}-call-'
        state = _CodexBuildState(
            source_path=str(candidate),
            thread_info={
                'id': agent_id,
                'title': f'subagent {spawn.get("agent_role") or ""}'.strip(),
                'cwd': meta.get('cwd') or '',
                'source': 'subagent',
                'model': '',
            },
            scope='subagent',
            subagent_id=agent_id,
            parent_tool_name='spawn_agent',
            call_id_prefix=call_prefix,
        )
        for order, event in enumerate(events, 1):
            if not isinstance(event, dict):
                continue
            state.event_order = order
            etype = event.get('type', '')
            payload = event.get('payload') if isinstance(event.get('payload'), dict) else {}
            timestamp = str(event.get('timestamp') or '')
            if etype == 'session_meta':
                state.accept_session_meta(payload, timestamp)
            elif etype == 'turn_context':
                state.accept_turn_context(payload, timestamp)
            elif etype == 'compacted':
                state.accept_compacted(payload, timestamp)
            elif etype == 'response_item':
                state.accept_response_item(payload, timestamp)
            elif etype == 'event_msg':
                state.accept_event_msg(payload, timestamp)
        state.finish()
        rounds = _rounds_with_expanded_source_refs(
            state.rounds,
            state.source_unit_sequences,
        )
        runs.append(
            SubagentRun(
                path=str(candidate),
                parent_tool_use_id='',
                summary=SubagentSummary.from_dict(
                    {
                        'agent_id': agent_id,
                        'agent_type': str(spawn.get('agent_role') or ''),
                        'agent_nickname': str(spawn.get('agent_nickname') or ''),
                        'parent_thread_id': parent_session_id,
                        'depth': _int(spawn.get('depth')),
                        'llm_call_count': len(state.rounds),
                        'tool_call_count': sum(
                            len(step.get('tools') or [])
                            for round_obj in state.rounds
                            for step in (round_obj.get('steps') or [])
                            if step.get('type') == 'tool_batch'
                        ),
                        'input_tokens': sum(
                            (r.get('metrics') or {}).get('tokens', {}).get('fresh', 0)
                            for r in state.rounds
                        ),
                        'cache_read_input_tokens': sum(
                            (r.get('metrics') or {}).get('tokens', {}).get('cache_read', 0)
                            for r in state.rounds
                        ),
                        'output_tokens': sum(
                            (r.get('metrics') or {}).get('tokens', {}).get('output', 0)
                            for r in state.rounds
                        ),
                    }
                ),
                extras={
                    'source_unit_catalog': dict(state.source_unit_catalog),
                    'rounds': rounds,
                },
            )
        )
    return runs


def _rounds_with_expanded_source_refs(
    rounds: list[dict],
    sequences: dict[str, list[str]],
) -> list[dict]:
    """Convert child-local sequence ranges into explicit refs before embedding.

    Args:
        rounds: Input value for normalized adapter processing.
        sequences: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    expanded: list[dict] = []
    for round_obj in rounds:
        if not isinstance(round_obj, dict):
            continue
        clone = dict(round_obj)
        ref_ranges = clone.get('source_unit_ref_ranges')
        if isinstance(ref_ranges, list):
            clone['source_unit_ref_ranges'] = [
                _expand_source_ref_range(ref_range, sequences)
                for ref_range in ref_ranges
                if isinstance(ref_range, dict)
            ]
        steps = clone.get('steps')
        if isinstance(steps, list):
            clone['steps'] = [
                _step_with_expanded_source_refs(step, sequences)
                for step in steps
                if isinstance(step, dict)
            ]
        expanded.append(clone)
    return expanded


def _step_with_expanded_source_refs(step: dict, sequences: dict[str, list[str]]) -> dict:
    """Support normalized adapter processing for _step_with_expanded_source_refs.

    Args:
        step: Input value for normalized adapter processing.
        sequences: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    clone = dict(step)
    sub_rounds = clone.get('sub_rounds')
    if isinstance(sub_rounds, list):
        clone['sub_rounds'] = _rounds_with_expanded_source_refs(
            [r for r in sub_rounds if isinstance(r, dict)],
            sequences,
        )
    return clone


def _expand_source_ref_range(ref_range: dict, sequences: dict[str, list[str]]) -> dict:
    """Support normalized adapter processing for _expand_source_ref_range.

    Args:
        ref_range: Input value for normalized adapter processing.
        sequences: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    refs: list[str] = []
    sequence_name = str(ref_range.get('sequence') or '')
    if sequence_name:
        sequence = sequences.get(sequence_name) if isinstance(sequences, dict) else None
        if isinstance(sequence, list):
            start = _int(ref_range.get('start'))
            end = _int(ref_range.get('end'))
            refs.extend(str(ref) for ref in sequence[start:end])
    item_refs = ref_range.get('refs')
    if isinstance(item_refs, list):
        refs.extend(str(ref) for ref in item_refs)
    clone = {
        key: value
        for key, value in ref_range.items()
        if key not in {'sequence', 'start', 'end', 'refs'}
    }
    if refs:
        clone['refs'] = refs
    return clone


def _first_session_meta(events: list[dict]) -> dict:
    """Support normalized adapter processing for _first_session_meta.

    Args:
        events: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    for event in events:
        if event.get('type') == 'session_meta' and isinstance(event.get('payload'), dict):
            return event['payload']
    return {}


def _codex_subagent_spawn(meta: dict) -> dict:
    """Support normalized adapter processing for _codex_subagent_spawn.

    Args:
        meta: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    source = meta.get('source') if isinstance(meta.get('source'), dict) else {}
    subagent = source.get('subagent') if isinstance(source.get('subagent'), dict) else {}
    return subagent.get('thread_spawn') if isinstance(subagent.get('thread_spawn'), dict) else {}


def _annotate_subagent_calls(normalized: dict, rounds: list[dict]) -> None:
    """Support normalized adapter processing for _annotate_subagent_calls.

    Args:
        normalized: Input value for normalized adapter processing.
        rounds: Input value for normalized adapter processing.
    """
    metadata_by_call: dict[str, dict] = {}

    def walk(round_list: list[dict], parent_tool_name: str = '') -> None:
        """Support normalized adapter processing for walk.

        Args:
            round_list: Input value for normalized adapter processing.
            parent_tool_name: Input value for normalized adapter processing.
        """
        for round_obj in round_list:
            main_call = (
                round_obj.get('main_call') if isinstance(round_obj.get('main_call'), dict) else {}
            )
            call_id = str(main_call.get('call_id') or '')
            if call_id:
                metadata_by_call[call_id] = {
                    'subagent_id': str(main_call.get('subagent_id') or ''),
                    'parent_tool_name': str(main_call.get('parent_tool_name') or parent_tool_name),
                }
            for step in round_obj.get('steps') or []:
                if not isinstance(step, dict) or step.get('type') != 'subagent_run':
                    continue
                for child in step.get('sub_rounds') or []:
                    if isinstance(child, dict):
                        walk([child], parent_tool_name='spawn_agent')

    walk(rounds)
    for call in normalized.get('calls') or []:
        meta = metadata_by_call.get(call.get('call_id') or '', {})
        if meta.get('subagent_id'):
            call['subagent_id'] = meta['subagent_id']
        if meta.get('parent_tool_name'):
            call['parent_tool_name'] = meta['parent_tool_name']


def _json_dict(value: object) -> dict:
    """Support normalized adapter processing for _json_dict.

    Args:
        value: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _safe_id_fragment(value: str) -> str:
    """Support normalized adapter processing for _safe_id_fragment.

    Args:
        value: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    fragment = re.sub(r'[^A-Za-z0-9]+', '-', value or '').strip('-')
    return fragment[:12] or 'unknown'


def _duration_ms(duration: dict) -> int:
    """Support normalized adapter processing for _duration_ms.

    Args:
        duration: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    return int(duration.get('secs') or 0) * 1000 + math.floor(
        int(duration.get('nanos') or 0) / 1_000_000
    )


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


def _nested_int(data: dict, outer: str, inner: str) -> int:
    """Support normalized adapter processing for _nested_int.

    Args:
        data: Input value for normalized adapter processing.
        outer: Input value for normalized adapter processing.
        inner: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    child = data.get(outer)
    if isinstance(child, dict):
        return _int(child.get(inner))
    return 0


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


def _truncate_text(text: object, limit: int = 240) -> str:
    """Support normalized adapter processing for _truncate_text.

    Args:
        text: Input value for normalized adapter processing.
        limit: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    value = re.sub(r'\s+', ' ', _stringify(text)).strip()
    if len(value) <= limit:
        return value
    return value[: limit - 3] + '...'


def _session_id_from_path(path: str) -> str:
    """Support normalized adapter processing for _session_id_from_path.

    Args:
        path: Input value for normalized adapter processing.

    Returns:
        Normalized adapter result.
    """
    name = Path(path).name
    if name.startswith('rollout-') and name.endswith('.jsonl'):
        return name.rsplit('-', 1)[-1].removesuffix('.jsonl')
    return ''
