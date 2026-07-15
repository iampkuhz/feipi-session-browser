from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING

import pytest
from scripts.agent_runtime.change.controller import ADOPT_CONFIRMATION
from scripts.agent_runtime.change.protocol import EXIT_CODES
from scripts.agent_runtime.session.lifecycle import bootstrap_session
from scripts.agent_runtime.session.registry import Registry
from scripts.harness import change as change_cli

if TYPE_CHECKING:
    from pathlib import Path


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ['git', *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def adopted_checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, dict]:
    repo = tmp_path / 'repo'
    repo.mkdir()
    _git(repo, 'init', '-b', 'main_java')
    _git(repo, 'config', 'user.email', 'change-cli@example.invalid')
    _git(repo, 'config', 'user.name', 'Change CLI Test')
    (repo / 'README.md').write_text('base\n', encoding='utf-8')
    _git(repo, 'add', 'README.md')
    _git(repo, 'commit', '-m', 'base')
    monkeypatch.setenv('FEIPI_AGENT_RUNTIME_ROOT', str(tmp_path / 'runtime'))
    record = bootstrap_session(
        client='codex',
        session_id='change-cli-session',
        cwd=repo,
        hook_event='SessionStart',
        checkout_creator='unknown',
    )
    return repo, record


@pytest.mark.parametrize(
    ('argv', 'command'),
    (
        (['ensure-session', '--run-id', 'run-1'], 'ensure-session'),
        (['status', '--run-id', 'run-1', '--compact'], 'status'),
        (['on-stop', '--run-id', 'run-1', '--message', 'done'], 'on-stop'),
        (['resume', '--run-id', 'run-1', '--message', 'resume'], 'resume'),
        (['next-change', '--run-id', 'run-1', '--task-key', 'task-b'], 'next-change'),
        (
            [
                'adopt-current',
                '--run-id',
                'run-1',
                '--base',
                'a' * 40,
                '--file',
                'owned.txt',
                '--confirmation',
                ADOPT_CONFIRMATION,
            ],
            'adopt-current',
        ),
        (['abort', '--run-id', 'run-1'], 'abort'),
    ),
)
def test_parser_exposes_only_seven_canonical_change_commands(argv: list[str], command: str):
    assert change_cli.build_parser().parse_args(argv).command == command


def test_execute_dispatches_every_controller_command(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    calls: list[tuple[str, object]] = []

    class FakeController:
        @classmethod
        def from_run_id(cls, repo: Path, run_id: str):
            calls.append(('from_run_id', (repo, run_id)))
            return cls()

        def ensure_session(self, **kwargs):
            calls.append(('ensure_session', kwargs))
            return {'sessionId': 'session-1', 'changes': [], 'changeEpoch': 0}

        def _payload(self, _session, **kwargs):
            return {'status': 'PASS', 'state': 'WORKING', 'code': kwargs['code']}

        def status(self):
            calls.append(('status', None))
            return {'status': 'PASS', 'state': 'WORKING', 'code': 'CHANGE_STATUS'}

        def on_stop(self, **kwargs):
            calls.append(('on_stop', kwargs))
            return {'status': 'PASS', 'state': 'INTEGRATED', 'code': 'CHANGE_INTEGRATED'}

        def next_change(self, **kwargs):
            calls.append(('next_change', kwargs))
            return {'status': 'PASS', 'state': 'WORKING', 'code': 'NEXT_CHANGE_STARTED'}

        def abort(self):
            calls.append(('abort', None))
            return {'status': 'TERMINAL_BLOCKED', 'state': 'TERMINAL_BLOCKED', 'code': 'ABORTED'}

    monkeypatch.setattr(change_cli, '_repo', lambda _value: tmp_path)
    monkeypatch.setattr(change_cli, 'LifecycleController', FakeController)
    parser = change_cli.build_parser()
    commands = (
        ['ensure-session', '--run-id', 'run-1'],
        ['status', '--run-id', 'run-1'],
        ['on-stop', '--run-id', 'run-1', '--message', 'done'],
        ['resume', '--run-id', 'run-1', '--message', 'again'],
        ['next-change', '--run-id', 'run-1', '--task-key', 'task-b'],
        ['abort', '--run-id', 'run-1'],
    )
    for argv in commands:
        change_cli.execute(parser.parse_args(argv))

    invoked = [name for name, _value in calls if name != 'from_run_id']
    assert invoked == ['ensure_session', 'status', 'on_stop', 'on_stop', 'next_change', 'abort']
    on_stop_calls = [value for name, value in calls if name == 'on_stop']
    assert on_stop_calls[1] == {
        'message': 'again',
        'expect_manifest_hash': '',
        'expect_candidate_tree': '',
    }


@pytest.mark.parametrize(
    ('status', 'exit_code'),
    tuple(EXIT_CODES.items()),
)
def test_main_uses_protocol_exit_codes_and_one_compact_object(
    status: str,
    exit_code: int,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
):
    monkeypatch.setattr(
        change_cli,
        'execute',
        lambda _args: {
            'status': status,
            'state': 'WORKING',
            'code': 'TEST_RESULT',
            'rootFailure': {'message': 'x' * 3000},
        },
    )

    assert change_cli.main(['status', '--run-id', 'run-1']) == exit_code
    output = capsys.readouterr().out
    assert json.loads(output)['status'] == status
    assert len(output.encode()) <= 4096
    assert output.count('\n') == 1


def _adopt(
    repo: Path,
    record: dict,
    *,
    base: str | None = None,
    files: tuple[str, ...] = ('owned.txt',),
    confirmation: str | None = ADOPT_CONFIRMATION,
) -> tuple[int, dict]:
    argv = [
        '--repo-root',
        str(repo),
        'adopt-current',
        '--run-id',
        str(record['runId']),
        '--base',
        base or str(record['baseCommit']),
    ]
    for path in files:
        argv.extend(('--file', path))
    if confirmation is not None:
        argv.extend(('--confirmation', confirmation))
    exit_code = change_cli.main(argv)
    return exit_code, {}


def test_adopt_current_success_is_audited(
    adopted_checkout: tuple[Path, dict], capsys: pytest.CaptureFixture[str]
):
    repo, record = adopted_checkout
    (repo / 'owned.txt').write_text('owned\n', encoding='utf-8')

    exit_code, _ = _adopt(repo, record)

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload['code'] == 'CURRENT_CHECKOUT_ADOPTED'
    assert payload['sessionId'] == record['sessionId']
    persisted = Registry(repo).load_run(str(record['runId']))
    assert persisted['changeBegin']['adoptedFiles'] == ['owned.txt']
    assert any(event['event'] == 'CURRENT_CHECKOUT_ADOPTED' for event in persisted['auditEvents'])


@pytest.mark.parametrize(
    ('case', 'base', 'files', 'confirmation', 'message'),
    (
        ('wrong-base', 'f' * 40, ('owned.txt',), ADOPT_CONFIRMATION, 'base'),
        ('manifest-mismatch', None, ('other.txt',), ADOPT_CONFIRMATION, 'manifest mismatch'),
        ('confirmation', None, ('owned.txt',), 'not-confirmed', 'confirmation'),
    ),
)
def test_adopt_current_rejects_unsafe_inputs(
    adopted_checkout: tuple[Path, dict],
    capsys: pytest.CaptureFixture[str],
    case: str,
    base: str | None,
    files: tuple[str, ...],
    confirmation: str,
    message: str,
):
    del case
    repo, record = adopted_checkout
    (repo / 'owned.txt').write_text('owned\n', encoding='utf-8')

    exit_code, _ = _adopt(repo, record, base=base, files=files, confirmation=confirmation)

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == EXIT_CODES['TERMINAL_BLOCKED']
    assert payload['code'] == 'SESSION_INVARIANT'
    assert message in payload['rootFailure']['message']


def test_adopt_current_rejects_forbidden_path(
    adopted_checkout: tuple[Path, dict], capsys: pytest.CaptureFixture[str]
):
    repo, record = adopted_checkout
    forbidden = repo / 'data' / 'private.txt'
    forbidden.parent.mkdir()
    forbidden.write_text('private\n', encoding='utf-8')

    exit_code, _ = _adopt(repo, record, files=('data/private.txt',))

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == EXIT_CODES['TERMINAL_BLOCKED']
    assert payload['code'] == 'SESSION_INVARIANT'
    assert 'FORBIDDEN_PATH' in payload['rootFailure']['message']


def test_adopt_current_requires_explicit_confirmation(
    adopted_checkout: tuple[Path, dict], capsys: pytest.CaptureFixture[str]
):
    repo, record = adopted_checkout
    (repo / 'owned.txt').write_text('owned\n', encoding='utf-8')

    with pytest.raises(SystemExit) as captured:
        _adopt(repo, record, confirmation=None)

    assert captured.value.code == 2
    assert '--confirmation' in capsys.readouterr().err
