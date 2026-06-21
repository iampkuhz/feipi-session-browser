"""Codex 专属 call mapping 与 token accounting mapper。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from session_browser.attribution.contracts import AttributedValue
from session_browser.attribution.mapping.call_mapping_resolver import CallMappingDecision
from session_browser.attribution.mapping.usage_shape_detector import detect_usage_shape
from session_browser.attribution.token_estimator import estimate_tokens_from_text


@dataclass(frozen=True)
class CodexCallMappingResolver:
    """解析 Codex call 的 API family/provider/billing 决策。"""

    def resolve(
        self,
        *,
        usage: dict | None = None,
        model: str | None = None,
        raw_request: dict | None = None,
        raw_response: dict | None = None,
    ) -> CallMappingDecision:
        usage_shape = detect_usage_shape(usage)
        reasons = ["agent is codex -> provider openai"]
        warnings: list[str] = []
        api_family = "openai_responses"
        confidence = 0.7
        usage_source = "provider_reported" if usage_shape != "unavailable" else "local_reconstruction"

        if usage_shape == "openai_responses_like":
            confidence = 0.95
            reasons.append("codex with OpenAI Responses usage -> openai_responses")
        elif usage_shape == "openai_chat_like":
            api_family = "openai_chat"
            confidence = 0.9
            reasons.append("codex with OpenAI Chat usage -> openai_chat")
        elif usage_shape == "token_reported_unknown_cache":
            confidence = 0.7
            reasons.append("codex with basic token usage -> openai_responses")
        else:
            api_family = "estimate_only"
            confidence = 0.4
            warnings.append("Codex 无预期 OpenAI usage，使用本地估算")

        return CallMappingDecision(
            agent_runtime="codex",
            api_family=api_family,
            provider_or_broker="openai",
            underlying_provider=None,
            model=model,
            billing_units=["tokens"],
            usage_source=usage_source,
            confidence=confidence,
            reasons=reasons,
            warnings=warnings,
        )


class CodexTokenAccountingMapper:
    """把 Codex normalized source_units 映射到 field-first accounting payload。"""

    FIELD_ORDER = [
        "fresh_input_tokens",
        "cache_read_tokens",
        "cache_write_tokens",
        "output_tokens",
    ]

    def source_units_for_direction(self, source_units: list[dict], direction: str) -> list[dict]:
        return [u for u in source_units or [] if isinstance(u, dict) and u.get("direction") == direction]

    def candidate_groups(self, source_units: list[dict], direction: str) -> dict[str, list[dict]]:
        groups: dict[str, list[dict]] = {}
        for unit in self.source_units_for_direction(source_units, direction):
            candidate = str(unit.get("candidate") or "")
            if candidate:
                groups.setdefault(candidate, []).append(unit)
        return groups

    def build_request_accounting(
        self,
        *,
        source_units: list[dict],
        fresh_input: AttributedValue,
        cache_read: AttributedValue,
        cache_write: AttributedValue,
    ) -> dict:
        fresh_total = _num(fresh_input.value)
        candidates, unattributed = self._candidate_entries(
            self.source_units_for_direction(source_units, "request"),
            denominator=fresh_total,
        )
        return {
            "schema": "token_accounting_fields.v1",
            "field_order": list(self.FIELD_ORDER),
            "fresh_input_tokens": self._field_payload(
                "fresh_input_tokens",
                fresh_input,
                candidates,
                unattributed_tokens=unattributed,
                notes=[
                    "Codex mapping 根据 normalized source_units 暴露 request-side candidates。",
                    "本地数据无法可靠拆分 candidate-level cache read；cache read 单独作为 provider accounting 展示。",
                ],
            ),
            "cache_read_tokens": self._field_payload(
                "cache_read_tokens",
                cache_read,
                [],
                notes=["Provider reported cached_input_tokens；不创建 provider_cached_context 来源。"],
            ),
            "cache_write_tokens": self._field_payload(
                "cache_write_tokens",
                cache_write,
                [],
                notes=["Codex/OpenAI Responses cache_write unavailable；不从 residual 推断。"],
            ),
            "output_tokens": self._field_payload(
                "output_tokens",
                _zero_value("Request attribution payload 不包含 response output allocation。"),
                [],
            ),
        }

    def build_response_accounting(
        self,
        *,
        source_units: list[dict],
        total_output: AttributedValue,
        reasoning_output_tokens: int = 0,
    ) -> dict:
        output_total = _num(total_output.value)
        candidates, unattributed = self._candidate_entries(
            self.source_units_for_direction(source_units, "response"),
            denominator=output_total,
            exact_candidate_tokens={
                "reasoning_output": max(int(reasoning_output_tokens or 0), 0),
            } if reasoning_output_tokens else None,
        )
        return {
            "schema": "token_accounting_fields.v1",
            "field_order": list(self.FIELD_ORDER),
            "fresh_input_tokens": self._field_payload(
                "fresh_input_tokens",
                _zero_value("Response attribution payload 不包含 request input allocation。"),
                [],
            ),
            "cache_read_tokens": self._field_payload(
                "cache_read_tokens",
                _zero_value("Response attribution payload 不包含 request cache-read allocation。"),
                [],
            ),
            "cache_write_tokens": self._field_payload(
                "cache_write_tokens",
                _zero_value("Response attribution payload 不包含 request cache-write allocation。"),
                [],
            ),
            "output_tokens": self._field_payload(
                "output_tokens",
                total_output,
                candidates,
                unattributed_tokens=unattributed,
                notes=["Codex mapping 根据 normalized response source_units 暴露 output candidates。"],
            ),
        }

    def _candidate_entries(
        self,
        units: list[dict],
        *,
        denominator: float,
        exact_candidate_tokens: dict[str, int] | None = None,
    ) -> tuple[list[dict], int]:
        entries: dict[str, dict[str, Any]] = {}
        exact_candidate_tokens = exact_candidate_tokens or {}
        for unit in units:
            candidate = str(unit.get("candidate") or "")
            if not candidate:
                continue
            content_estimate = _unit_tokens(unit)
            entry = entries.setdefault(candidate, {
                "candidate": candidate,
                "tokens": 0,
                "percent": 0.0,
                "token_status": "unknown_mass",
                "token_precision": "unknown_mass",
                "sources": [],
            })
            if candidate in exact_candidate_tokens:
                entry["tokens"] = exact_candidate_tokens[candidate]
                entry["token_status"] = "exact_provider"
                entry["token_precision"] = "provider_reported"
            entry["sources"].append({
                "source_id": unit.get("source_id", ""),
                "origin_path": unit.get("origin_path", ""),
                "unit_type": unit.get("unit_type", ""),
                "label": unit.get("label", ""),
                "tokens": 0,
                "token_status": entry["token_status"],
                "content_token_estimate": content_estimate,
                "preview": unit.get("preview", ""),
            })

        total = sum(float(entry["tokens"]) for entry in entries.values())
        result: list[dict] = []
        for entry in entries.values():
            tokens = min(int(entry["tokens"]), int(denominator)) if denominator > 0 else int(entry["tokens"])
            entry["tokens"] = tokens
            entry["percent"] = round((tokens / denominator) * 100.0, 1) if denominator > 0 else 0.0
            result.append(entry)
        result.sort(key=lambda item: item["candidate"])
        known = sum(int(item["tokens"]) for item in result)
        return result, max(int(denominator) - known, 0) if denominator > 0 else 0

    def _field_payload(
        self,
        field: str,
        value: AttributedValue,
        candidates: list[dict],
        *,
        unattributed_tokens: int = 0,
        notes: list[str] | None = None,
    ) -> dict:
        return {
            "field": field,
            "tokens": _num(value.value),
            "value": {
                "value": value.value,
                "unit": value.unit,
                "precision": value.precision,
                "source": value.source,
                "fill_strategy": value.fill_strategy,
                "note": value.note,
            },
            "candidates": candidates,
            "candidate_total_tokens": sum(_num(item.get("tokens")) for item in candidates),
            "unattributed_tokens": unattributed_tokens,
            "notes": notes or [],
        }


def _unit_tokens(unit: dict) -> int:
    if unit.get("text"):
        return estimate_tokens_from_text(str(unit.get("text") or ""))
    if "payload" in unit:
        import json
        return estimate_tokens_from_text(json.dumps(unit.get("payload"), ensure_ascii=False, sort_keys=True))
    return estimate_tokens_from_text(str(unit.get("preview") or ""))


def _num(value) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _zero_value(note: str) -> AttributedValue:
    return AttributedValue(
        value=0,
        unit="tokens",
        precision="unavailable",
        source="heuristic",
        fill_strategy="not applicable",
        note=note,
    )
