#!/usr/bin/env python3
"""PostToolUse file change logger with quality gate awareness.

Writes tmp/changed-files.jsonl (primary) and .claude/change-log.jsonl (compat).

Usage:
    python3 scripts/hooks/log_file_change.py <file_path>
    echo '{"file_path": "..."}' | python3 scripts/hooks/log_file_change.py
    python3 scripts/hooks/log_file_change.py --self-test
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CHANGED_FILES_LOG = REPO_ROOT / "tmp" / "changed-files.jsonl"
CHANGE_LOG = REPO_ROOT / ".claude" / "change-log.jsonl"

QUALITY_GATE_CATEGORIES = {"ui-css", "ui-template", "ui-js", "quality-gate", "hook"}

CATEGORY_RULES = [
    (r"src/session_browser/web/static/.*\.css$", "ui-css"),
    (r"src/session_browser/web/templates/.*\.html$", "ui-template"),
    (r"src/session_browser/web/static/js/.*\.js$", "ui-js"),
    (r"src/session_browser/web/static/.*\.js$", "ui-js"),
    (r"tests/.*", "test"),
    (r"scripts/quality/.*", "quality-gate"),
    (r"scripts/hooks/.*", "hook"),
    (r"scripts/agent_hooks/.*", "hook"),
    (r"\.claude/hooks/.*", "hook"),
    (r"\.claude/commands/.*", "llm-command"),
    (r"harness/quality/.*", "quality-doc"),
    (r"openspec/changes/.*", "openspec"),
]

import re


def _classify(file_path: str) -> tuple[str, bool]:
    """Return (category, requires_quality_gate) for a relative file path."""
    rel = file_path.replace("\\", "/")
    for pattern, category in CATEGORY_RULES:
        if re.match(pattern, rel):
            return category, category in QUALITY_GATE_CATEGORIES
    return "other", False


def _extract_tool_name(payload: dict) -> str:
    """Extract tool name from a hook payload."""
    for key in ("tool_name", "tool"):
        if key in payload and payload[key]:
            return str(payload[key])
    return "unknown"


def _extract_file_path(payload: dict) -> str | None:
    """Extract file path from a hook payload."""
    for key in ("file_path", "path"):
        if key in payload and payload[key]:
            return str(payload[key])
    if "tool_input" in payload and isinstance(payload["tool_input"], dict):
        ti = payload["tool_input"]
        for key in ("file_path", "path", "notebook_path"):
            if key in ti and ti[key]:
                return str(ti[key])
        if "edits" in ti and isinstance(ti["edits"], list) and ti["edits"]:
            first_edit = ti["edits"][0]
            if isinstance(first_edit, dict):
                for key in ("file_path", "path"):
                    if key in first_edit and first_edit[key]:
                        return str(first_edit[key])
    return None


def _parse_file_path() -> str | None:
    """Resolve the changed file path from all possible input sources."""
    # 1. argv explicit path
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg != "--self-test":
            return arg

    # 2. stdin JSON payload
    if not sys.stdin.isatty():
        try:
            raw = sys.stdin.read().strip()
            if raw:
                parsed = json.loads(raw)
                fp = _extract_file_path(parsed)
                if fp:
                    return fp
        except (json.JSONDecodeError, EOFError, OSError):
            pass

    return None


def _parse_tool_name() -> str:
    """Resolve the tool name from stdin JSON payload."""
    if not sys.stdin.isatty():
        try:
            raw = sys.stdin.read().strip()
            if raw:
                parsed = json.loads(raw)
                tn = _extract_tool_name(parsed)
                if tn != "unknown":
                    return tn
        except (json.JSONDecodeError, EOFError, OSError):
            pass

    return "unknown"


def _make_entry(file_path: str, tool: str) -> dict:
    """Build a single changed-file log entry."""
    category, requires_qg = _classify(file_path)
    return {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tool": tool,
        "file": file_path,
        "category": category,
        "requiresQualityGate": requires_qg,
    }


def _ensure_log(log_path: Path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    if not log_path.exists():
        log_path.touch()


def _append_log(log_path: Path, entry: dict) -> None:
    _ensure_log(log_path)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def log_change(file_path: str, tool: str = "unknown") -> dict:
    """Log a file change to both primary and compat logs."""
    entry = _make_entry(file_path, tool)
    _append_log(CHANGED_FILES_LOG, entry)
    # Compat: keep .claude/change-log.jsonl too
    _ensure_log(CHANGE_LOG)
    with CHANGE_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": entry["ts"], "event": "post-edit", "file": file_path, "tool": tool}, ensure_ascii=False) + "\n")
    return entry


def main():
    if "--self-test" in sys.argv:
        return _self_test()

    file_path = _parse_file_path()
    if not file_path:
        # Nothing to log
        return

    tool = _parse_tool_name()
    entry = log_change(file_path, tool)
    # Print to stdout for hook visibility
    print(json.dumps(entry, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

def _self_test():
    """Run self-tests covering all input sources and category mappings."""
    import tempfile
    failures = 0

    def _run_test(name, func):
        nonlocal failures
        try:
            func()
            print(f"  PASS: {name}")
        except AssertionError as e:
            failures += 1
            print(f"  FAIL: {name} — {e}")
        except Exception as e:
            failures += 1
            print(f"  FAIL: {name} — {type(e).__name__}: {e}")

    def _t1_argv_path():
        """argv path can be recorded."""
        with tempfile.TemporaryDirectory() as td:
            log = Path(td) / "changed-files.jsonl"
            entry = _make_entry("src/session_browser/web/static/style.css", "Edit")
            _append_log(log, entry)
            lines = log.read_text().strip().split("\n")
            assert len(lines) == 1
            parsed = json.loads(lines[0])
            assert parsed["file"] == "src/session_browser/web/static/style.css"

    def _t2_stdin_cc_style():
        """stdin Claude Code style payload extracts tool_name and file_path."""
        payload = json.dumps({"tool_name": "Edit", "tool_input": {"file_path": "src/x.css"}})
        # We can't easily test stdin parsing without subprocess, so test the extraction function directly
        parsed = json.loads(payload)
        assert _extract_tool_name(parsed) == "Edit"
        assert _extract_file_path(parsed) == "src/x.css"

    def _t3_multiedit_single_evidence():
        """MultiEdit payload only records one evidence (first file)."""
        payload = {
            "tool_name": "MultiEdit",
            "tool_input": {
                "edits": [
                    {"file_path": "src/a.css"},
                    {"file_path": "src/b.css"},
                ]
            },
        }
        assert _extract_file_path(payload) == "src/a.css"

    def _t4_css_category():
        """UI CSS file classified as ui-css, requiresQualityGate=true."""
        cat, qg = _classify("src/session_browser/web/static/style.css")
        assert cat == "ui-css", f"Got {cat}"
        assert qg is True

    def _t5_other_category():
        """Non-UI file classified as other, requiresQualityGate=false."""
        cat, qg = _classify("README.md")
        assert cat == "other", f"Got {cat}"
        assert qg is False

    def _t6_template_category():
        """HTML template classified as ui-template."""
        cat, qg = _classify("src/session_browser/web/templates/session.html")
        assert cat == "ui-template", f"Got {cat}"
        assert qg is True

    def _t7_quality_gate_category():
        """Quality gate script classified as quality-gate."""
        cat, qg = _classify("scripts/quality/run_quality_gate.py")
        assert cat == "quality-gate", f"Got {cat}"
        assert qg is True

    def _t8_hook_category():
        """Hook script classified as hook."""
        cat, qg = _classify(".claude/hooks/stop.sh")
        assert cat == "hook", f"Got {cat}"
        assert qg is True

    _run_test("argv path", _t1_argv_path)
    _run_test("stdin CC style payload extraction", _t2_stdin_cc_style)
    _run_test("MultiEdit single evidence", _t3_multiedit_single_evidence)
    _run_test("CSS category", _t4_css_category)
    _run_test("Other category", _t5_other_category)
    _run_test("Template category", _t6_template_category)
    _run_test("Quality-gate category", _t7_quality_gate_category)
    _run_test("Hook category", _t8_hook_category)

    if failures:
        print(f"\n{failures} test(s) failed")
        sys.exit(1)
    else:
        print(f"\nAll tests passed")
        sys.exit(0)


if __name__ == "__main__":
    main()
