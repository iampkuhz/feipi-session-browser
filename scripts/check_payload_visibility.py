#!/usr/bin/env python3
"""Check LLM call payload visibility.

Reads fixture / exported session JSON containing llm_calls, checks whether
token counts, rendered context length, and raw request payload are consistent.

Usage:
    python scripts/check_payload_visibility.py <json-file-or-dir>
    python scripts/check_payload_visibility.py tests/fixtures/payload-visibility-complete.json

Exit codes:
    0 — all calls OK or only warnings (non-fatal)
    1 — mismatch detected (warnings emitted)
    2 — input error (file not found, invalid JSON, etc.)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def load_calls(source: Path) -> list[dict[str, Any]]:
    """Load llm_calls from a JSON file.

    Supports:
    - {"llm_calls": [...]}
    - [{"id": ...}, ...]
    - {"id": ...}  (single call, wrapped in list)
    """
    text = source.read_text(encoding="utf-8")
    data = json.loads(text)

    if isinstance(data, dict) and "llm_calls" in data:
        return data["llm_calls"]
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return [data]

    raise ValueError(f"Unexpected JSON structure in {source}")


def compute_fields(call: dict[str, Any]) -> dict[str, Any]:
    """Derive diagnostic fields from a single LLM call dict."""
    input_tokens = call.get("input_tokens", 0)
    cache_read_tokens = call.get("cache_read_tokens", 0)
    cache_write_tokens = call.get("cache_write_tokens", 0)
    output_tokens = call.get("output_tokens", 0)

    request_full = call.get("request_full", "")
    request_payload_missing = request_full is None or request_full == ""

    request_payload_bytes = len(request_full.encode("utf-8")) if request_full else 0
    request_payload_message_count = 0
    if request_full:
        try:
            parsed = json.loads(request_full)
            if isinstance(parsed, dict) and "messages" in parsed:
                request_payload_message_count = len(parsed["messages"])
            elif isinstance(parsed, list):
                request_payload_message_count = len(parsed)
        except (json.JSONDecodeError, TypeError):
            request_payload_message_count = -1

    response_full = call.get("response_full", "")
    rendered_response_length = len(response_full) if response_full else 0

    rendered_context_length = len(request_full) if request_full else 0

    tool_calls = call.get("tool_calls", [])
    tool_calls_linked = isinstance(tool_calls, list) and len(tool_calls) >= 0

    return {
        "input_tokens": input_tokens,
        "cache_read_tokens": cache_read_tokens,
        "cache_write_tokens": cache_write_tokens,
        "output_tokens": output_tokens,
        "rendered_context_length": rendered_context_length,
        "request_payload_bytes": request_payload_bytes,
        "request_payload_message_count": request_payload_message_count,
        "request_payload_missing": request_payload_missing,
        "rendered_response_length": rendered_response_length,
        "response_payload_bytes": len(response_full.encode("utf-8")) if response_full else 0,
        "tool_calls_linked": tool_calls_linked,
    }


def check_call(call: dict[str, Any], call_number: int) -> list[str]:
    """Run all visibility checks on a single call. Returns list of warning strings."""
    f = compute_fields(call)
    warnings: list[str] = []

    # Check 1: input_tokens > 0 but rendered_context_length == 0
    if f["input_tokens"] > 0 and f["rendered_context_length"] == 0:
        warnings.append(
            f"[WARN] call #{call_number} Payload visibility mismatch: "
            f"input_tokens={f['input_tokens']} but rendered_context_length=0. "
            f"request_payload_missing={f['request_payload_missing']} — "
            f"request payload not persisted in data source, not just a blank preview."
        )

    # Check 2: input_tokens > 0 and request_payload_missing == true
    if f["input_tokens"] > 0 and f["request_payload_missing"]:
        if not any("request_payload_missing" in w for w in warnings):
            warnings.append(
                f"[WARN] call #{call_number} Payload visibility mismatch: "
                f"input_tokens={f['input_tokens']} but request_payload_missing=true. "
                f"request_payload_bytes=0 — raw request was not logged."
            )

    # Check 3: request_payload_bytes == 0 and input_tokens > 1000
    if f["request_payload_bytes"] == 0 and f["input_tokens"] > 1000:
        if not any("request_payload_bytes" in w for w in warnings):
            warnings.append(
                f"[WARN] call #{call_number} Payload visibility mismatch: "
                f"input_tokens={f['input_tokens']} but request_payload_bytes=0. "
                f"rendered_context_length={f['rendered_context_length']}."
            )

    return warnings


def run(source: Path) -> int:
    """Run checks on all calls in source. Returns exit code."""
    try:
        calls = load_calls(source)
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"[ERROR] Failed to load {source}: {exc}", file=sys.stderr)
        return 2
    except FileNotFoundError:
        print(f"[ERROR] File not found: {source}", file=sys.stderr)
        return 2

    if not calls:
        print(f"[WARN] No llm_calls found in {source}")
        return 0

    exit_code = 0
    ok_count = 0

    for i, call in enumerate(calls, start=1):
        warnings = check_call(call, i)
        if warnings:
            exit_code = 1
            for w in warnings:
                print(w)
        else:
            ok_count += 1
            response_full = call.get("response_full", "")
            if response_full:
                print(f"[OK] call #{i} response rendered + raw available")
            else:
                print(f"[OK] call #{i} ok")

    summary = f"Checked {len(calls)} call(s): {ok_count} OK, {len(calls) - ok_count} with warnings"
    if exit_code == 0:
        print(f"\n{summary}")
    else:
        print(f"\n{summary} — exit code 1 indicates mismatch detected")

    return exit_code


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2

    source = Path(sys.argv[1])
    if source.is_dir():
        json_files = sorted(source.glob("*.json"))
        if not json_files:
            print(f"[ERROR] No JSON files found in {source}", file=sys.stderr)
            return 2
        overall = 0
        for f in json_files:
            print(f"\n--- {f.name} ---")
            rc = run(f)
            overall = max(overall, rc)
        return overall

    return run(source)


if __name__ == "__main__":
    sys.exit(main())
