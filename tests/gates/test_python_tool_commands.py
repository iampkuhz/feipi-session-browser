"""Python tooling Gate 的双 profile 命令声明 contract。"""

from pathlib import Path

from scripts.gates import executor
from scripts.gates.catalog import gate_by_name
from scripts.gates.model import ExecutionMode, RunKind


def test_python_tool_kinds_are_explicit() -> None:
    assert gate_by_name('pythonLint').run.kind is RunKind.COMMAND
    assert gate_by_name('pythonDependencyVulnerabilities').run.kind is RunKind.PYTHON_CHECK


def test_python_command_uses_selected_profile(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(executor, '_project_python', lambda _root, dev=False: '/python')
    incremental = executor.command_for_gate(
        gate_by_name('pythonLint'), tmp_path, ExecutionMode.INCREMENTAL
    )
    full = executor.command_for_gate(gate_by_name('pythonLint'), tmp_path, ExecutionMode.FULL)
    assert incremental == full
    assert incremental[:4] == ['/python', '-m', 'ruff', 'check']


def test_profile_timing_is_owned_by_gate() -> None:
    run = gate_by_name('pythonLint').run
    assert run.incremental.target_seconds == 15
    assert run.full.target_seconds == 30
