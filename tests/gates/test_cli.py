"""CLI 子命令、输入边界和空运行 receipt 合同。"""

from __future__ import annotations

import argparse
import json
import subprocess
from typing import TYPE_CHECKING

import pytest
from scripts.gates import cli

if TYPE_CHECKING:
    from pathlib import Path


def _init_repo(root: Path) -> None:
    subprocess.run(['git', 'init', '-q'], cwd=root, check=True)
    subprocess.run(['git', 'config', 'user.email', 'gate@example.invalid'], cwd=root, check=True)
    subprocess.run(['git', 'config', 'user.name', 'Gate Test'], cwd=root, check=True)
    (root / 'README.md').write_text('fixture\n', encoding='utf-8')
    subprocess.run(['git', 'add', 'README.md'], cwd=root, check=True)
    subprocess.run(['git', 'commit', '-qm', 'fixture'], cwd=root, check=True)


def test_list_json_exposes_catalog_names(capsys) -> None:
    assert cli.main(['list', '--format', 'json']) == 0
    payload = json.loads(capsys.readouterr().out)
    assert len(payload['gates']) == 20
    assert len(payload['targetPresets']) == 6
    assert 'javaBuildVerification' in {item['id'] for item in payload['gates']}
    assert 'agent-governance' in {item['id'] for item in payload['targetPresets']}


def test_explain_requires_one_subject(capsys) -> None:
    assert cli.main(['explain']) == 2
    assert 'requires exactly one' in capsys.readouterr().err


def test_plan_reports_match_and_process_count(capsys) -> None:
    assert (
        cli.main(
            [
                'plan',
                '--mode',
                'incremental',
                '--changed-files',
                '["scripts/gates/cli.py"]',
                '--format',
                'json',
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload['snapshot']['source'] == 'explicit-changed-files'
    assert payload['matches']
    assert payload['processCount'] > 0


def test_plan_allows_empty_automatic_input(tmp_path: Path, monkeypatch, capsys) -> None:
    _init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert cli.main(['plan', '--mode', 'incremental', '--changed-files', '[]']) == 0
    assert 'gates=0' in capsys.readouterr().out


@pytest.mark.contract_case('HOOK-HARNESS-012')
def test_run_empty_input_writes_fail_receipt(tmp_path: Path, monkeypatch, capsys) -> None:
    _init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert cli.main(['run', '--mode', 'incremental', '--changed-files', '[]']) == 2
    summary = next((tmp_path / 'tmp/quality/runs').glob('*/summary.json'))
    payload = json.loads(summary.read_text(encoding='utf-8'))
    assert payload['status'] == 'FAIL'
    assert payload['reason'] == 'input-empty'
    event_output = capsys.readouterr().err
    assert 'DONE ' in event_output
    assert 'status=FAIL' in event_output


def test_incremental_selector_without_input_requires_full(tmp_path: Path, monkeypatch) -> None:
    _init_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    assert (
        cli.main(
            [
                'run',
                '--mode',
                'incremental',
                '--gate',
                'javaBuildVerification',
                '--changed-files',
                '[]',
            ]
        )
        == 2
    )


def test_parser_exposes_exact_current_command_surface() -> None:
    parser = cli._parser()
    subcommands = next(
        action for action in parser._actions if isinstance(action, argparse._SubParsersAction)
    )

    assert set(subcommands.choices) == {'list', 'explain', 'plan', 'run', 'health'}
    health_options = {
        option
        for action in subcommands.choices['health']._actions
        for option in action.option_strings
    }
    assert health_options == {'-h', '--help', '--format'}
