"""Qoder 专属 call mapping 与 token accounting mapper。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from session_browser.attribution.contracts import AttributedValue
from session_browser.attribution.mapping.call_mapping_resolver import CallMappingDecision
from session_browser.attribution.mapping.usage_shape_detector import detect_usage_shape
from session_browser.attribution.token_estimator import estimate_tokens_from_text


@dataclass(frozen=True)
class QoderCallMappingResolver:
    """解析 Qoder call 的 API family/provider/billing 决策。"""

    def resolve(
        self,
        *,
        usage: dict | None = None,
        model: str | None = None,
        raw_request: dict | None = None,
        raw_response: dict | None = None,
    ) -> CallMappingDecision:
        usage_shape = detect_usage_shape(usage)
        reasons = ["agent is qoder -> provider/broker qoder"]
        warnings: list[str] = []
        confidence = 0.4
        usage_source = "local_reconstruction"
        api_family = "estimate_only"
        if usage_shape in {"anthropic_messages_like", "openai_responses_like", "openai_chat_like", "token_reported_unknown_cache"}:
            api_family = "qoder_broker"
            confidence = 0.9
            usage_source = "provider_reported"
            reasons.append("Qoder usage 由 broker 上报")
        else:
            warnings.append("Qoder 无可用 usage，使用本地可见 source_units")
        return CallMappingDecision(
            agent_runtime="qoder",
            api_family=api_family,
            provider_or_broker="qoder",
            underlying_provider=None,
            model=model,
            billing_units=["tokens", "credits"],
            usage_source=usage_source,
            confidence=confidence,
            reasons=reasons,
            warnings=warnings,
        )


class QoderTokenAccountingMapper:
    """把 Qoder source_units 映射为 field-first accounting payload。"""

    FIELD_ORDER = ["fresh_input_tokens", "cache_read_tokens", "cache_write_tokens", "output_tokens"]

    def source_units_for_direction(self, source_units: list[dict], direction: str) -> list[dict]:
        return [u for u in source_units or [] if isinstance(u, dict) and u.get("direction") == direction]

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
                    "Qoder request candidates 来自 normalized source_units。",
                    "cache read/write 是 Qoder accounting fields，不创建 provider cache 来源 candidate。",
                ],
            ),
            "cache_read_tokens": self._field_payload(
                "cache_read_tokens",
                cache_read,
                [],
                notes=["Qoder cache read 只作为 accounting field 展示，不做 per-candidate 拆分。"],
            ),
            "cache_write_tokens": self._field_payload(
                "cache_write_tokens",
                cache_write,
                [],
                notes=["Qoder cache write 只作为 accounting field 展示，不变成 content candidate。"],
            ),
            "output_tokens": self._field_payload(
                "output_tokens",
                _zero_value("Request attribution payload 不包含 response output allocation。"),
                [],
            ),
        }

    def build_response_accounting(self, *, source_units: list[dict], total_output: AttributedValue) -> dict:
        output_total = _num(total_output.value)
        candidates, unattributed = self._candidate_entries(
            self.source_units_for_direction(source_units, "response"),
            denominator=output_total,
        )
        return {
            "schema": "token_accounting_fields.v1",
            "field_order": list(self.FIELD_ORDER),
            "fresh_input_tokens": self._field_payload("fresh_input_tokens", _zero_value("Response attribution payload 不包含 request input allocation。"), []),
            "cache_read_tokens": self._field_payload("cache_read_tokens", _zero_value("Response attribution payload 不包含 request cache-read allocation。"), []),
            "cache_write_tokens": self._field_payload("cache_write_tokens", _zero_value("Response attribution payload 不包含 request cache-write allocation。"), []),
            "output_tokens": self._field_payload(
                "output_tokens",
                total_output,
                candidates,
                unattributed_tokens=unattributed,
                notes=["Qoder response candidates 来自 normalized source_units。"],
            ),
        }

    def _candidate_entries(self, units: list[dict], *, denominator: float) -> tuple[list[dict], int]:
        entries: dict[str, dict[str, Any]] = {}
        for unit in units:
            candidate = str(unit.get("candidate") or "")
            if not candidate:
                continue
            tokens = _unit_tokens(unit)
            entry = entries.setdefault(candidate, {"candidate": candidate, "tokens": 0, "percent": 0.0, "sources": []})
            entry["tokens"] += tokens
            entry["sources"].append({
                "source_id": unit.get("source_id", ""),
                "origin_path": unit.get("origin_path", ""),
                "unit_type": unit.get("unit_type", ""),
                "label": unit.get("label", ""),
                "tokens": tokens,
                "preview": unit.get("preview", ""),
            })
        total = sum(float(entry["tokens"]) for entry in entries.values())
        scale = denominator / total if denominator > 0 and total > denominator and total > 0 else 1.0
        result: list[dict] = []
        for entry in entries.values():
            tokens = int(entry["tokens"] * scale)
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
        return estimate_tokens_from_text(_stable_payload_text(unit.get("payload")))
    return estimate_tokens_from_text(str(unit.get("preview") or ""))


def _stable_payload_text(payload: Any) -> str:
    try:
        import json
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return str(payload)


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
