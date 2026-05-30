"""Base attribution builder shared by all agent-specific implementations."""

from __future__ import annotations

from dataclasses import asdict
from typing import Optional

from session_browser.domain.models import (
    LLMCall,
    ConversationRound,
    SessionSummary,
)
from session_browser.attribution.contracts import (
    AttributedValue,
    RequestAttributionBucket,
    ResponseAttributionBucket,
    LLMRequestAttribution,
    LLMResponseAttribution,
    ValuePrecision,
    ValueSource,
)
from session_browser.attribution.token_estimator import estimate_tokens_from_text


class BaseAttributionBuilder:
    """Minimal fallback attribution when no agent-specific builder is available."""

    def __init__(
        self,
        llm_call: LLMCall,
        round_obj: ConversationRound,
        session_summary: Optional[SessionSummary] = None,
        session_context: Optional[dict] = None,
    ):
        self.llm_call = llm_call
        self.round_obj = round_obj
        self.session_summary = session_summary
        self.session_context = session_context or {}

    def _avail(
        self,
        field_name: str,
        label: str,
        available: bool,
        exact: bool = False,
        precision: str = "",
        source: str = "",
        fill_strategy: str = "",
        note: str = "",
    ) -> dict:
        """Build a full availability row for UI parameter table."""
        if not precision:
            precision = ValuePrecision.EXACT if exact else (
                ValuePrecision.UNAVAILABLE if not available else ValuePrecision.ESTIMATED
            )
        if not source:
            source = ValueSource.HEURISTIC if available else ValueSource.HEURISTIC
        if not fill_strategy:
            fill_strategy = "direct" if available else "not available"
        return {
            "field": field_name,
            "label": label,
            "exact": exact,
            "available": available,
            "precision": precision,
            "source": source,
            "fill_strategy": fill_strategy,
            "note": note or ("available from " + field_name if available else "not available"),
        }

    def _request_id(self) -> str:
        """Fallback chain: provider request_id > llm_call.id > unavailable."""
        lc = self.llm_call
        return lc.id or "unavailable"

    def build_request(self) -> LLMRequestAttribution:
        """Build a minimal request attribution with all unknowns."""
        lc = self.llm_call
        total = lc.input_tokens or 0

        total_input = AttributedValue(
            value=total,
            unit="tokens",
            precision=ValuePrecision.PROVIDER_REPORTED if total > 0 else ValuePrecision.UNAVAILABLE,
            source=ValueSource.PROVIDER_USAGE if total > 0 else ValueSource.HEURISTIC,
            fill_strategy="direct from llm_call.input_tokens" if total > 0 else "unavailable",
        )

        buckets: list[RequestAttributionBucket] = []
        if total > 0:
            buckets.append(RequestAttributionBucket(
                key="unknown_overhead",
                label="Unknown / unattributed",
                tokens=total,
                percent=100.0,
                precision=ValuePrecision.HEURISTIC,
                source=ValueSource.HEURISTIC,
                confidence_label="低",
                summary="未区分 agent 时，所有 token 归入 unknown。",
            ))

        return LLMRequestAttribution(
            agent="unknown",
            model=lc.model or "unknown",
            request_id=self._request_id(),
            call_id=lc.id,
            source_label="local logs",
            confidence_label="低",
            raw_body_available=False,
            total_input=total_input,
            fresh_input=AttributedValue(value=None, unit="tokens", precision=ValuePrecision.UNAVAILABLE, source=ValueSource.HEURISTIC, fill_strategy="unknown"),
            cache_read=AttributedValue(value=None, unit="tokens", precision=ValuePrecision.UNAVAILABLE, source=ValueSource.HEURISTIC, fill_strategy="unknown"),
            cache_write=AttributedValue(value=None, unit="tokens", precision=ValuePrecision.UNAVAILABLE, source=ValueSource.HEURISTIC, fill_strategy="unknown"),
            coverage=AttributedValue(value=0.0, unit="ratio", precision=ValuePrecision.UNAVAILABLE, source=ValueSource.HEURISTIC, fill_strategy="no buckets"),
            unknown=AttributedValue(value=total, unit="tokens", precision=ValuePrecision.HEURISTIC, source=ValueSource.RESIDUAL, fill_strategy="all unknown"),
            buckets=buckets,
            captured_context_preview="",
            attribution_notes=["No agent-specific builder available."],
            availability_rows=[
                self._avail("total_input", "Total input tokens", total > 0,
                            precision=ValuePrecision.PROVIDER_REPORTED if total > 0 else ValuePrecision.UNAVAILABLE,
                            source=ValueSource.PROVIDER_USAGE if total > 0 else ValueSource.HEURISTIC,
                            fill_strategy="direct from llm_call.input_tokens" if total > 0 else "unavailable"),
                self._avail("fresh_input", "Fresh input tokens", False,
                            precision=ValuePrecision.UNAVAILABLE,
                            source=ValueSource.HEURISTIC,
                            fill_strategy="unknown"),
                self._avail("cache_read", "Cache read tokens", False,
                            precision=ValuePrecision.UNAVAILABLE,
                            source=ValueSource.HEURISTIC,
                            fill_strategy="unknown"),
                self._avail("cache_write", "Cache write tokens", False,
                            precision=ValuePrecision.UNAVAILABLE,
                            source=ValueSource.HEURISTIC,
                            fill_strategy="unknown"),
            ],
        )

    def build_response(self) -> LLMResponseAttribution:
        """Build a minimal response attribution with all unknowns."""
        lc = self.llm_call
        total = lc.output_tokens or 0

        total_output = AttributedValue(
            value=total,
            unit="tokens",
            precision=ValuePrecision.PROVIDER_REPORTED if total > 0 else ValuePrecision.UNAVAILABLE,
            source=ValueSource.PROVIDER_USAGE if total > 0 else ValueSource.HEURISTIC,
            fill_strategy="direct from llm_call.output_tokens" if total > 0 else "unavailable",
        )

        buckets: list[ResponseAttributionBucket] = []
        if total > 0:
            buckets.append(ResponseAttributionBucket(
                key="unknown",
                label="Unknown",
                tokens=total,
                percent=100.0,
                precision=ValuePrecision.HEURISTIC,
                source=ValueSource.HEURISTIC,
                confidence_label="低",
                summary="未区分 agent 时，所有 output token 归入 unknown。",
            ))

        finish_str = lc.finish_reason or ""
        return LLMResponseAttribution(
            agent="unknown",
            model=lc.model or "unknown",
            request_id=self._request_id(),
            call_id=lc.id,
            source_label="local logs",
            confidence_label="低",
            raw_body_available=False,
            total_output=total_output,
            visible_text=AttributedValue(value=None, unit="tokens", precision=ValuePrecision.UNAVAILABLE, source=ValueSource.HEURISTIC, fill_strategy="unknown"),
            tool_use=AttributedValue(value=None, unit="tokens", precision=ValuePrecision.UNAVAILABLE, source=ValueSource.HEURISTIC, fill_strategy="unknown"),
            metadata=AttributedValue(value=None, unit="tokens", precision=ValuePrecision.UNAVAILABLE, source=ValueSource.HEURISTIC, fill_strategy="unknown"),
            coverage=AttributedValue(value=0.0, unit="ratio", precision=ValuePrecision.UNAVAILABLE, source=ValueSource.HEURISTIC, fill_strategy="no buckets"),
            unknown=AttributedValue(value=total, unit="tokens", precision=ValuePrecision.HEURISTIC, source=ValueSource.RESIDUAL, fill_strategy="all unknown"),
            finish_reason=AttributedValue(value=finish_str, unit="str", precision=ValuePrecision.EXACT if finish_str else ValuePrecision.UNAVAILABLE, source=ValueSource.TRANSCRIPT, fill_strategy="from llm_call.finish_reason"),
            buckets=buckets,
            blocks=lc.content_blocks or [],
            captured_output_preview=lc.response_preview or "",
            attribution_notes=["No agent-specific builder available."],
            availability_rows=[
                self._avail("total_output", "Total output tokens", total > 0,
                            precision=ValuePrecision.PROVIDER_REPORTED if total > 0 else ValuePrecision.UNAVAILABLE,
                            source=ValueSource.PROVIDER_USAGE if total > 0 else ValueSource.HEURISTIC,
                            fill_strategy="direct from llm_call.output_tokens" if total > 0 else "unavailable"),
                self._avail("visible_text", "Visible text tokens", False,
                            precision=ValuePrecision.UNAVAILABLE,
                            source=ValueSource.HEURISTIC,
                            fill_strategy="unknown"),
                self._avail("tool_use", "Tool use tokens", False,
                            precision=ValuePrecision.UNAVAILABLE,
                            source=ValueSource.HEURISTIC,
                            fill_strategy="unknown"),
                self._avail("finish_reason", "Finish reason", bool(finish_str),
                            precision=ValuePrecision.EXACT if finish_str else ValuePrecision.UNAVAILABLE,
                            source=ValueSource.TRANSCRIPT,
                            fill_strategy="from llm_call.finish_reason"),
            ],
        )
