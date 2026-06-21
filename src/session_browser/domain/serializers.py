"""Domain layer models and helpers for normalized session data.

Parser, attribution, and presenter flows import this module for stable contracts.
It performs no I/O.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from session_browser.domain._validation import enum_value
from session_browser.domain.content_part import ContentPart, ContentPartType, ContextPartType

if TYPE_CHECKING:
    from session_browser.domain.session_models import SessionSummary
    from session_browser.domain.subagent_models import SubagentRun, SubagentSummary
    from session_browser.domain.token_models import NormalizedTokenBreakdown


def normalized_token_breakdown_to_dict(breakdown: NormalizedTokenBreakdown) -> dict[str, Any]:
    """normalized_token_breakdown_to_dict function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        breakdown: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.
    """
    return {
        'fresh_input_tokens': breakdown.fresh_input_tokens,
        'cache_read_tokens': breakdown.cache_read_tokens,
        'cache_write_tokens': breakdown.cache_write_tokens,
        'output_tokens': breakdown.output_tokens,
        'total_tokens': breakdown.total_tokens,
        'precision': enum_value(breakdown.precision),
        'total_semantics': enum_value(breakdown.total_semantics),
        'source_kind': enum_value(breakdown.source_kind),
        'raw_fields': breakdown.raw_fields,
        'notes': breakdown.notes,
    }


def session_summary_to_dict(summary: SessionSummary) -> dict[str, Any]:
    """session_summary_to_dict function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        summary: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.
    """
    return {
        'agent': summary.agent,
        'session_id': summary.session_id,
        'title': summary.title,
        'project_key': summary.project_key,
        'project_name': summary.project_name,
        'cwd': summary.cwd,
        'started_at': summary.started_at,
        'ended_at': summary.ended_at,
        'duration_seconds': summary.duration_seconds,
        'model_execution_seconds': summary.model_execution_seconds,
        'tool_execution_seconds': summary.tool_execution_seconds,
        'model': summary.model,
        'git_branch': summary.git_branch,
        'source': summary.source,
        'user_message_count': summary.user_message_count,
        'assistant_message_count': summary.assistant_message_count,
        'tool_call_count': summary.tool_call_count,
        'output_tokens': summary.output_tokens,
        'has_sensitive_data': summary.has_sensitive_data,
        'fresh_input_tokens': summary.fresh_input_tokens,
        'cache_read_tokens': summary.cache_read_tokens,
        'cache_write_tokens': summary.cache_write_tokens,
        'total_tokens': summary.total_tokens,
        'failed_tool_count': summary.failed_tool_count,
        'subagent_instance_count': summary.subagent_instance_count,
        'parse_diagnostics': summary.parse_diagnostics,
        'file_path': summary.file_path,
        'session_key': summary.session_key,
    }


def subagent_summary_to_dict(summary: SubagentSummary) -> dict[str, Any]:
    """subagent_summary_to_dict function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        summary: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.
    """
    return summary._as_legacy_dict()


def subagent_run_to_dict(run: SubagentRun) -> dict[str, Any]:
    """subagent_run_to_dict function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        run: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.
    """
    return run._as_legacy_dict()


def content_part_to_dict(part: ContentPart) -> dict[str, Any]:
    """content_part_to_dict function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        part: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.
    """
    return {
        'part_type': part.part_type,
        'content': part.content,
        'language': part.language,
        'filename': part.filename,
        'metadata': part.metadata,
        'context_type': part.context_type,
        'title': part.title,
        'content_bytes': part.content_bytes,
        'token_hint': part.token_hint,
    }


def content_part_from_dict(data: dict[str, Any]) -> ContentPart:
    """content_part_from_dict function used by the session browser pipeline.

    The active parsing or normalization flow calls this entry point.
    It preserves the existing domain behavior and return shape.

    Args:
        data: Input value supplied by the caller for this pipeline step.

    Returns:
        Existing return value produced by this parser or domain helper.
    """
    return ContentPart(
        part_type=data.get('part_type', ContentPartType.TEXT),
        content=data.get('content', ''),
        language=data.get('language', ''),
        filename=data.get('filename', ''),
        metadata=data.get('metadata', {}),
        context_type=data.get('context_type', ContextPartType.UNKNOWN),
        title=data.get('title', ''),
        content_bytes=data.get('content_bytes', 0),
        token_hint=data.get('token_hint', 0),
    )
