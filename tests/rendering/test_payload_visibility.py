"""check_payload_visibility.py 诊断脚本的测试。
import pytest
import json
import subprocess
import sys
from pathlib import Path

FIXTURE_DIR = Path(__file__).parent / "fixtures"
SCRIPT = Path(__file__).parents[2] / "scripts" / "check_payload_visibility.py"


def _run_script(fixture: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(fixture)],
        capture_output=True,
        text=True,
    )


# ── 夹具 1：payload 和 context 均存在 ──────────────────────────────


@pytest.mark.contract_case("UI-SD-008")
def test_complete_payload_visibility():
    """所有字段均已填充 — 每个调用应报告 OK。"""
    result = _run_script(FIXTURE_DIR / "payload-visibility-complete.json")
    assert result.returncode == 0, f"Expected exit 0, got {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}"
    assert "[OK]" in result.stdout
    assert "call #1" in result.stdout
    assert "call #2" in result.stdout
    assert "response rendered + raw available" in result.stdout


# ── 夹具 2：input_tokens > 0 但 rendered context 为空 ────────────────


@pytest.mark.contract_case("UI-SD-008")
def test_empty_context_visibility():
    """input_tokens > 0，request_full 为空 — 应警告 context 问题。"""
    result = _run_script(FIXTURE_DIR / "payload-visibility-empty-context.json")
    assert result.returncode == 1, f"Expected exit 1, got {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}"
    assert "[WARN]" in result.stdout
    assert "call #1" in result.stdout
    assert "input_tokens=" in result.stdout
    assert "rendered_context_length=0" in result.stdout
    assert "Payload visibility mismatch" in result.stdout


# ── 夹具 3：input_tokens > 0 但原始 request payload 缺失 ──────────────


@pytest.mark.contract_case("UI-SD-008")
def test_missing_request_payload_visibility():
    """完全没有 request_full 字段 — 应警告 payload 缺失。"""
    result = _run_script(FIXTURE_DIR / "payload-visibility-missing-request.json")
    assert result.returncode == 1, f"Expected exit 1, got {result.returncode}\nstdout: {result.stdout}\nstderr: {result.stderr}"
    assert "[WARN]" in result.stdout
    assert "call #1" in result.stdout
    assert "input_tokens=" in result.stdout
    assert "Payload visibility mismatch" in result.stdout


# ── compute_fields 和 check_call 的单元测试 ────────────────────────────


@pytest.mark.contract_case("UI-SD-008")
def test_compute_fields_empty_request():
    """当 request_full 缺失时，所有派生字段应反映该情况。"""
    from scripts.check_payload_visibility import compute_fields

    call = {"input_tokens": 5000, "response_full": "hello"}
    f = compute_fields(call)
    assert f["request_payload_missing"] is True
    assert f["request_payload_bytes"] == 0
    assert f["rendered_context_length"] == 0
    assert f["rendered_response_length"] == 5


@pytest.mark.contract_case("UI-SD-008")
def test_compute_fields_full_request():
    """当 request_full 存在时，派生字段应被正确填充。"""
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


@pytest.mark.contract_case("UI-SD-008")
def test_check_call_triggers_warning():
    """一个 input_tokens 存在但 request_full 为空的调用应产生警告。"""
    from scripts.check_payload_visibility import check_call

    call = {"input_tokens": 12000, "request_full": "", "response_full": "ok"}
    warnings = check_call(call, 1)
    assert len(warnings) > 0
    assert "Payload visibility mismatch" in warnings[0]
    assert "call #1" in warnings[0]
    assert "input_tokens=" in warnings[0]


@pytest.mark.contract_case("UI-SD-008")
def test_check_call_no_warning():
    """一个 input_tokens 和 request_full 均存在的调用不应产生警告。"""
    from scripts.check_payload_visibility import check_call

    call = {
        "input_tokens": 5000,
        "request_full": '{"messages": []}',
        "response_full": "ok",
    }
    warnings = check_call(call, 1)
    assert len(warnings) == 0
