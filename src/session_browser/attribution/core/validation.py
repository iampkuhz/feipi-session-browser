"""Validate invariant checks for reconstructed LLM attribution data."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from session_browser.attribution.core.models import PromptSpan, UsageBreakdown


def validate_attribution(
    *,
    spans: list[PromptSpan],
    usage: UsageBreakdown | None = None,
    api_family: str = 'unknown',
    agent_runtime: str = 'unknown',
    underlying_provider: str | None = None,
) -> list[dict[str, Any]]:
    """Validate attribution invariants for one reconstructed model call.

    The attribution service calls this after span construction, cache allocation, and
    usage parsing. The checks protect UI payloads from impossible token totals,
    unsupported OpenAI cache-write values, estimate-only provider labels, and Qoder
    provider inference that would misrepresent broker traffic.

    Args:
        spans: Request or response spans produced for the model call.
        usage: Optional provider or broker usage breakdown to compare with spans.
        api_family: Normalized API family label for provider-specific checks.
        agent_runtime: Runtime that produced the call, such as codex or qoder.
        underlying_provider: Optional provider inferred below broker/runtime layers.

    Returns:
        Invariant result dictionaries with name, passed flag, and diagnostic detail.
    """
    results: list[dict[str, Any]] = []
    _append_request_sum_result(results, spans, usage)
    _append_openai_cache_write_result(results, spans, api_family)
    _append_estimate_precision_result(results, spans, api_family)
    _append_usage_total_result(results, usage)
    _append_cache_bound_results(results, usage)
    _append_qoder_provider_result(results, agent_runtime, underlying_provider)
    _append_zero_value_result(results, usage)
    return results


def _has_positive_total(usage: UsageBreakdown | None) -> bool:
    """Return whether usage has a positive input total for arithmetic checks.

    Args:
        usage: Optional provider or broker usage breakdown.

    Returns:
        True when total_input is present and greater than zero.
    """
    return bool(usage and usage.total_input and usage.total_input > 0)


def _append_request_sum_result(
    results: list[dict[str, Any]],
    spans: list[PromptSpan],
    usage: UsageBreakdown | None,
) -> None:
    """Append the span allocation versus usage total invariant.

    Args:
        results: Mutable result list populated by the validator.
        spans: Attribution spans whose cache and fresh tokens are summed.
        usage: Optional usage breakdown containing the provider total.
    """
    if not _has_positive_total(usage):
        return

    total_input = usage.total_input if usage is not None else 0
    allocated_sum = sum(
        span.cache_read_tokens + span.cache_write_tokens + span.fresh_tokens for span in spans
    )
    passed = allocated_sum <= total_input
    results.append(
        {
            'name': 'request_sum_lte_total',
            'passed': passed,
            'detail': f'allocated_sum={allocated_sum}, total_input={total_input}',
        }
    )


def _append_openai_cache_write_result(
    results: list[dict[str, Any]],
    spans: list[PromptSpan],
    api_family: str,
) -> None:
    """Append the OpenAI cache-write unsupported invariant.

    Args:
        results: Mutable result list populated by the validator.
        spans: Attribution spans checked for cache-write token allocation.
        api_family: Normalized API family label.
    """
    if api_family not in ('openai_responses', 'openai_chat', 'openai_like'):
        return

    failing_span = next((span for span in spans if span.cache_write_tokens > 0), None)
    if failing_span is not None:
        results.append(
            {
                'name': 'openai_cache_write_unavailable',
                'passed': False,
                'detail': (
                    f'span {failing_span.span_id} has cache_write={failing_span.cache_write_tokens}'
                ),
            }
        )
        return

    results.append(
        {
            'name': 'openai_cache_write_unavailable',
            'passed': True,
            'detail': 'All spans have cache_write=0 or unavailable.',
        }
    )


def _append_estimate_precision_result(
    results: list[dict[str, Any]],
    spans: list[PromptSpan],
    api_family: str,
) -> None:
    """Append the estimate-only precision invariant.

    Args:
        results: Mutable result list populated by the validator.
        spans: Attribution spans checked for provider_reported precision.
        api_family: Normalized API family label.
    """
    if api_family != 'estimate_only':
        return

    failing_span = next((span for span in spans if span.precision == 'provider_reported'), None)
    if failing_span is not None:
        results.append(
            {
                'name': 'estimate_no_provider_reported',
                'passed': False,
                'detail': (
                    f'span {failing_span.span_id} has provider_reported precision in estimate_only'
                ),
            }
        )
        return

    results.append(
        {
            'name': 'estimate_no_provider_reported',
            'passed': True,
            'detail': 'All spans avoid provider_reported precision.',
        }
    )


def _append_usage_total_result(
    results: list[dict[str, Any]],
    usage: UsageBreakdown | None,
) -> None:
    """Append the usage component sum invariant.

    Args:
        results: Mutable result list populated by the validator.
        usage: Optional usage breakdown whose token components are compared.
    """
    if not _has_positive_total(usage):
        return

    total_input = usage.total_input if usage is not None else 0
    fresh = usage.fresh_input or 0
    cache_read = usage.cache_read or 0
    cache_write = usage.cache_write or 0
    reconstructed = fresh + cache_read + cache_write
    diff = abs(reconstructed - total_input)
    results.append(
        {
            'name': 'total_equals_fresh_plus_cache',
            'passed': diff <= 1,
            'detail': (
                f'total_input={total_input}, '
                f'fresh+cache_read+cache_write={reconstructed}, '
                f'diff={diff}'
            ),
        }
    )


def _append_cache_bound_results(
    results: list[dict[str, Any]],
    usage: UsageBreakdown | None,
) -> None:
    """Append cache-read and cache-write upper-bound invariants.

    Args:
        results: Mutable result list populated by the validator.
        usage: Optional usage breakdown containing cache and total fields.
    """
    if not _has_positive_total(usage):
        return

    total_input = usage.total_input if usage is not None else 0
    for name, value in (
        ('cache_read_lte_total', usage.cache_read or 0),
        ('cache_write_lte_total', usage.cache_write or 0),
    ):
        field_name = name.removesuffix('_lte_total')
        results.append(
            {
                'name': name,
                'passed': value <= total_input,
                'detail': f'{field_name}={value}, total_input={total_input}',
            }
        )


def _append_qoder_provider_result(
    results: list[dict[str, Any]],
    agent_runtime: str,
    underlying_provider: str | None,
) -> None:
    """Append the Qoder underlying-provider inference invariant.

    Args:
        results: Mutable result list populated by the validator.
        agent_runtime: Runtime that produced the call.
        underlying_provider: Optional provider inferred below broker/runtime layers.
    """
    if agent_runtime != 'qoder':
        return

    inferred_provider = underlying_provider in ('anthropic', 'openai')
    results.append(
        {
            'name': 'qoder_no_underlying_provider_inference',
            'passed': not inferred_provider,
            'detail': (
                f'Qoder should not infer underlying_provider={underlying_provider}.'
                if inferred_provider
                else f'underlying_provider={underlying_provider}'
            ),
        }
    )


def _append_zero_value_result(
    results: list[dict[str, Any]],
    usage: UsageBreakdown | None,
) -> None:
    """Append the invariant that explicit zero usage values remain known values.

    Args:
        results: Mutable result list populated by the validator.
        usage: Optional usage breakdown inspected for explicit zero fields.
    """
    if usage is None:
        return

    zero_details = []
    for field_name in ('fresh_input', 'cache_read', 'cache_write'):
        if getattr(usage, field_name, None) == 0:
            zero_details.append(f'{field_name}=0 (valid)')

    results.append(
        {
            'name': 'zero_values_are_known',
            'passed': True,
            'detail': '; '.join(zero_details) if zero_details else 'No explicit zero fields.',
        }
    )
