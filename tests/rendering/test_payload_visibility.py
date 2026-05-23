"""Tests for check_payload_visibility.py diagnostic script."""

import json
import subprocess
import sys
from pathlib import Path

FIXTURE_DIR = Path(__file__).parent / "fixtures"
SCRIPT = Path(__file__).parent.parent / "scripts" / "check_payload_visibility.py"


def _run_script(fixture: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(fixture)],
        capture_output=True,
        text=True,
    )


# ── Fixture 1: payload and context both present ──────────────────────


def test_complete_payload_visibility():
    """All fields populated — should report OK for each call."""
    result = _run_script(FIXTURE_DIR / "payload-visibility-complete.json")
    assert result.returncode == 0, f"Expected exit 0, got {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}"
    assert "[OK]" in result.stdout
    assert "call #1" in result.stdout
    assert "call #2" in result.stdout
    assert "response rendered + raw available" in result.stdout


# ── Fixture 2: input_tokens > 0 but rendered context is empty ────────


def test_empty_context_visibility():
    """input_tokens > 0, request_full empty — should warn about context."""
    result = _run_script(FIXTURE_DIR / "payload-visibility-empty-context.json")
    assert result.returncode == 1, f"Expected exit 1, got {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}"
    assert "[WARN]" in result.stdout
    assert "call #1" in result.stdout
    assert "input_tokens=" in result.stdout
    assert "rendered_context_length=0" in result.stdout
    assert "Payload visibility mismatch" in result.stdout


# ── Fixture 3: input_tokens > 0 but raw request payload missing ──────


def test_missing_request_payload_visibility():
    """No request_full field at all — should warn about missing payload."""
    result = _run_script(FIXTURE_DIR / "payload-visibility-missing-request.json")
    assert result.returncode == 1, f"Expected exit 1, got {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}"
    assert "[WARN]" in result.stdout
    assert "call #1" in result.stdout
    assert "input_tokens=" in result.stdout
    assert "Payload visibility mismatch" in result.stdout


# ── Unit tests for compute_fields and check_call ─────────────────────


def test_compute_fields_empty_request():
    """When request_full is missing, all derived fields should reflect that."""
    from scripts.check_payload_visibility import compute_fields

    call = {"input_tokens": 5000, "response_full": "hello"}
    f = compute_fields(call)
    assert f["request_payload_missing"] is True
    assert f["request_payload_bytes"] == 0
    assert f["rendered_context_length"] == 0
    assert f["rendered_response_length"] == 5


def test_compute_fields_full_request():
    """When request_full is present, derived fields should be populated."""
    from scripts.check_payload_visibility import compute_fields

    call = {
        "input_tokens": 5000,
        "request_full": '{"messages": [{"role": "user", "content": "hi"}]}',
        "response_full": "hello",
    }
    f = compute_fields(call)
    assert f["request_payload_missing"] is False
    assert f["request_payload_bytes"] > 0
    assert f["rendered_context_length"] > 0
    assert f["request_payload_message_count"] == 1


def test_check_call_triggers_warning():
    """A call with input_tokens but empty request_full should produce warnings."""
    from scripts.check_payload_visibility import check_call

    call = {"input_tokens": 12000, "request_full": "", "response_full": "ok"}
    warnings = check_call(call, 1)
    assert len(warnings) > 0
    assert "Payload visibility mismatch" in warnings[0]
    assert "call #1" in warnings[0]
    assert "input_tokens=" in warnings[0]


def test_check_call_no_warning():
    """A call with both input_tokens and request_full should produce no warnings."""
    from scripts.check_payload_visibility import check_call

    call = {
        "input_tokens": 5000,
        "request_full": '{"messages": []}',
        "response_full": "ok",
    }
    warnings = check_call(call, 1)
    assert len(warnings) == 0
