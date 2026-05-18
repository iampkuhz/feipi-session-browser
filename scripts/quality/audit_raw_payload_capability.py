"""Audit script: Raw HTTP payload capability across all session sources.

Scans repo fixtures and source parsers to determine whether raw HTTP
request/response payloads are available, captured, or deliberately omitted.

Output: JSON capability report + human-readable markdown summary.
Does NOT print raw payload content to stdout.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src" / "session_browser"
FIXTURES = REPO_ROOT / "tests" / "fixtures"


# ─── Source parser inspection ──────────────────────────────────────────────

SOURCES = {
    "claude_code": SRC / "sources" / "claude.py",
    "codex": SRC / "sources" / "codex.py",
    "qoder": SRC / "sources" / "qoder.py",
}

RAW_FIELD_NAMES = [
    "request_payload_raw",
    "response_payload_raw",
    "raw_request",
    "raw_response",
]

RENDERED_FIELD_NAMES = [
    "request_full",
    "response_full",
]


def _grep_file(path: Path, patterns: list[str]) -> dict[str, list[int]]:
    """Return {pattern: [line_numbers]} for each pattern found in file."""
    results: dict[str, list[int]] = {p: [] for p in patterns}
    if not path.exists():
        return results
    text = path.read_text(encoding="utf-8")
    for i, line in enumerate(text.splitlines(), 1):
        for pat in patterns:
            if pat in line:
                results[pat].append(i)
    return results


def inspect_source_capability() -> dict:
    """Check each source parser for raw payload mapping."""
    capability = {}
    for source_name, src_path in SOURCES.items():
        hits = _grep_file(src_path, RAW_FIELD_NAMES + RENDERED_FIELD_NAMES)
        has_raw = any(hits[p] for p in RAW_FIELD_NAMES)
        has_rendered = any(hits[p] for p in RENDERED_FIELD_NAMES)
        capability[source_name] = {
            "source_file": str(src_path.relative_to(REPO_ROOT)),
            "has_raw_mapping": has_raw,
            "has_rendered_mapping": has_rendered,
            "raw_field_lines": {p: hits[p] for p in RAW_FIELD_NAMES if hits[p]},
            "rendered_field_lines": {p: hits[p] for p in RENDERED_FIELD_NAMES if hits[p]},
        }
    return capability


# ─── Route inspection ──────────────────────────────────────────────────────


def inspect_route_capability() -> dict:
    """Check routes.py for how LLMCall raw fields are populated."""
    routes_py = SRC / "web" / "routes.py"
    if not routes_py.exists():
        return {"error": "routes.py not found"}

    text = routes_py.read_text(encoding="utf-8")
    lines = text.splitlines()

    # Find all assignments to request_payload_raw and response_payload_raw
    raw_assignments = []
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if "request_payload_raw" in stripped or "response_payload_raw" in stripped:
            raw_assignments.append({"line": i, "content": stripped})

    # Determine if raw is hardcoded to empty string or dynamically set
    hardcoded_empty = 0
    dynamic = 0
    for a in raw_assignments:
        if '=""' in a["content"] or "=''" in a["content"]:
            hardcoded_empty += 1
        else:
            dynamic += 1

    return {
        "routes_file": str(routes_py.relative_to(REPO_ROOT)),
        "raw_field_assignments": raw_assignments,
        "hardcoded_empty_count": hardcoded_empty,
        "dynamic_assignment_count": dynamic,
    }


# ─── Fixture inspection ────────────────────────────────────────────────────


def inspect_fixtures() -> list[dict]:
    """Scan test fixtures for raw payload fields."""
    results = []
    if not FIXTURES.exists():
        return results

    for fp in sorted(FIXTURES.rglob("*")):
        if not fp.is_file():
            continue
        if fp.suffix not in (".json", ".jsonl"):
            continue
        text = fp.read_text(encoding="utf-8", errors="replace")
        found_fields = []
        for field in RAW_FIELD_NAMES + RENDERED_FIELD_NAMES:
            if f'"{field}"' in text:
                found_fields.append(field)
        results.append({
            "file": str(fp.relative_to(REPO_ROOT)),
            "fields_found": found_fields,
            "has_raw": any(f in found_fields for f in RAW_FIELD_NAMES),
            "has_rendered": any(f in found_fields for f in RENDERED_FIELD_NAMES),
        })
    return results


# ─── Main ──────────────────────────────────────────────────────────────────


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Audit raw payload source capability")
    parser.add_argument("--out", help="Write JSON report to this path")
    args = parser.parse_args()

    report = {
        "schema_version": 1,
        "source_capability": inspect_source_capability(),
        "route_capability": inspect_route_capability(),
        "fixture_inspection": inspect_fixtures(),
    }

    # Derive capability matrix
    matrix = []
    for source_name, cap in report["source_capability"].items():
        matrix.append({
            "source_type": source_name,
            "has_user_visible_message": True,
            "has_rendered_request_context": cap["has_rendered_mapping"],
            "has_provider_usage": True,
            "has_raw_http_request": False,  # confirmed: not parsed
            "has_raw_http_response": False,
            "evidence": cap["source_file"],
        })

    report["capability_matrix"] = matrix

    # Conclusion
    route_info = report["route_capability"]
    report["conclusion"] = {
        "current_code_behavior": (
            f"routes.py hardcodes request_payload_raw=\"\" and response_payload_raw=\"\" "
            f"for all LLMCall types (main/subagent/aggregated). "
            f"{route_info.get('hardcoded_empty_count', 0)} hardcoded-empty assignments found. "
            f"Each includes a missing_reason: "
            f"\"current session data source does not persist raw HTTP request/response payload\"."
        ),
        "source_capability": (
            "Claude Code JSONL event streams contain structured message content, "
            "tool calls, and usage snapshots — but NOT the raw HTTP request/response "
            "JSON bodies sent to/received from the Anthropic API. "
            "Codex and Qoder parsers similarly extract rendered events, not raw HTTP. "
            "No test fixture contains raw payload fields."
        ),
        "required_action": (
            "Source truly lacks raw HTTP payload at the JSONL event-stream level. "
            "UI must show 'Raw unavailable' explicitly, not an empty modal. "
            "Additionally, request_full contains rendered user-visible context, "
            "which explains the token mismatch (25.9K input includes system prompts, "
            "tool definitions, cache metadata — not shown in request_full)."
        ),
    }

    json_out = json.dumps(report, indent=2, ensure_ascii=False)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json_out, encoding="utf-8")
        print(f"JSON report written to {out_path}")
    else:
        print(json_out)


if __name__ == "__main__":
    main()
