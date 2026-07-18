from __future__ import annotations

import json
import os
import random
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from scripts.agent_runtime.change.controller import GateInputs, LifecycleController
from scripts.agent_runtime.change.model import current_change
from scripts.agent_runtime.change.protocol import LifecycleError
from scripts.agent_runtime.change.runtime import BoundedMetadataLock, LockBusyError


def run(repo: Path, *args: str, check: bool = True):
    result = subprocess.run(args, cwd=repo, text=True, capture_output=True, check=False)
    if check and result.returncode:
        raise AssertionError(f'{args}: {result.stdout}\n{result.stderr}')
    return result


@pytest.fixture
def checkout(tmp_path):
    primary = tmp_path / 'primary'
    primary.mkdir()
    run(primary, 'git', 'init', '-b', 'main_java')
    run(primary, 'git', 'config', 'user.email', 'controller@example.invalid')
    run(primary, 'git', 'config', 'user.name', 'Controller Test')
    for path, text in {
        'README.md': 'initial\n',
        'config/gates.yaml': 'version: 1\n',
        'openspec/changes/lifecycle-task/tasks.md': '- [ ] tracked lifecycle task\n',
        'scripts/gates/cli.py': '# gate entry\n',
    }.items():
        target = primary / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding='utf-8')
    run(primary, 'git', 'add', '.')
    run(primary, 'git', 'commit', '-m', 'initial')
    linked = tmp_path / 'linked'
    run(primary, 'git', 'worktree', 'add', '--detach', str(linked), 'HEAD')
    base = run(linked, 'git', 'rev-parse', 'HEAD').stdout.strip()
    record = {
        'schemaVersion': 2,
        'runId': 'run-controller',
        'sessionId': 'session-controller',
        'client': 'codex',
        'repoKey': 'repo-key',
        'gitCommonDir': str((primary / '.git').resolve()),
        'worktreeId': 'checkout-controller',
        'checkoutRoot': str(linked.resolve()),
        'checkoutKind': 'linked-worktree',
        'branch': '',
        'detached': True,
        'targetBranch': 'main_java',
        'primaryRepoRoot': str(primary.resolve()),
        'baseCommit': base,
        'targetHeadAtBootstrap': base,
        'changeId': 'lifecycle-task',
        'changeBegin': {
            'status': 'ATTESTED',
            'runId': 'run-controller',
            'checkoutRoot': str(linked.resolve()),
            'baseCommit': base,
        },
        'taskId': 'task:lifecycle',
        'allowedPaths': ['.'],
        'forbiddenPaths': ['.env', 'data', 'tmp/agent_logs'],
    }
    return primary, linked, record, tmp_path / 'runtime'


class FakeGates:
    def __init__(self, status='PASS'):
        self.status = status
        self.calls = 0

    def __call__(self, **kwargs):
        self.calls += 1
        out = Path(kwargs['out_dir'])
        out.mkdir(parents=True, exist_ok=True)
        artifact = out / 'fake-gate.json'
        artifact.write_text(json.dumps({'status': self.status}), encoding='utf-8')
        receipt = out / 'fake-receipt.json'
        receipt.write_text(json.dumps({'status': self.status}), encoding='utf-8')
        detail = SimpleNamespace(
            name='fake-required',
            status=self.status,
            executionState='EXECUTED',
            output='fix candidate' if self.status != 'PASS' else 'ok',
            command=['python3', '-m', 'pytest'],
        )
        return SimpleNamespace(
            status=self.status,
            details=(detail,),
            artifact_path=artifact,
            receipt_paths=(receipt,) if self.status == 'PASS' else (),
        )


class Inputs:
    def __init__(self):
        self.plan = 'plan-1'
        self.command = 'command-1'
        self.environment = 'environment-1'

    def __call__(self, _repo, _files, _base_url=None):
        return GateInputs(self.plan, self.command, self.environment, 1)


class FixtureInputs:
    def __init__(self):
        self.base_urls = []

    def __call__(self, _repo, _files, base_url=None):
        self.base_urls.append(base_url)
        suffix = base_url or 'discovery'
        return GateInputs(
            f'plan:{suffix}',
            'command:fixture',
            f'environment:{suffix}',
            1,
            requires_fixture=True,
        )


def controller(checkout, gates=None, inputs=None):
    _primary, linked, record, runtime = checkout
    return LifecycleController(
        linked,
        record,
        store_root=runtime,
        gate_runner=gates or FakeGates(),
        gate_input_builder=inputs or Inputs(),
    )


def test_primary_or_invalid_worktree_identity_fails_before_mutation_within_two_seconds(checkout):
    _primary, linked, record, runtime = checkout
    invalid = dict(record, checkoutKind='primary')
    started = time.monotonic()

    with pytest.raises(LifecycleError) as captured:
        LifecycleController(linked, invalid, store_root=runtime)

    assert time.monotonic() - started < 2
    assert captured.value.code == 'PRIMARY_CHECKOUT_FORBIDDEN'
    assert not (runtime / 'sessions').exists()


def test_end_to_end_integrates_and_duplicate_stop_is_fast_with_zero_new_gate(checkout):
    primary, linked, _record, _runtime = checkout
    gates = FakeGates()
    ctl = controller(checkout, gates)
    first = ctl.ensure_session(event='prompt', task_key='first', task_title='First task')
    assert current_change(first)['changeEpoch'] == 1
    assert ctl.ensure_session(event='status')['currentChangeId'] == first['currentChangeId']
    (linked / 'README.md').write_text('changed\n', encoding='utf-8')

    completion_started = time.monotonic()
    result = ctl.on_stop(message='chore(lifecycle): first')

    assert time.monotonic() - completion_started < 5
    assert result['status'] == 'PASS'
    assert result['state'] == 'INTEGRATED'
    assert result['commitSha'] == run(primary, 'git', 'rev-parse', 'HEAD').stdout.strip()
    assert gates.calls == 1
    started = time.monotonic()
    repeated = ctl.on_stop(message='chore(lifecycle): first')
    assert time.monotonic() - started < 1
    assert repeated['idempotent'] is True
    assert gates.calls == 1


def test_initial_dirty_candidate_resumes_from_attested_baseline_in_place(checkout):
    primary, linked, _record, _runtime = checkout
    gates = FakeGates()
    (linked / 'resumed.txt').write_text('owned before controller bootstrap\n', encoding='utf-8')
    ctl = controller(checkout, gates)

    session = ctl.ensure_session(event='status')
    change = current_change(session)
    assert change is not None and change['changeEpoch'] == 1
    result = ctl.on_stop(message='chore: resume dirty')

    assert result['state'] == 'INTEGRATED'
    assert result['commitSha'] == run(primary, 'git', 'rev-parse', 'HEAD').stdout.strip()
    assert gates.calls == 1


def test_same_session_prompt_rolls_next_epoch_but_stop_does_not(checkout):
    _primary, linked, _record, _runtime = checkout
    gates = FakeGates()
    ctl = controller(checkout, gates)
    ctl.ensure_session(event='prompt', task_key='first')
    (linked / 'one.txt').write_text('one\n', encoding='utf-8')
    completed = ctl.on_stop(message='chore: first')
    assert completed['state'] == 'INTEGRATED'

    duplicate = ctl.ensure_session(event='stop')
    assert current_change(duplicate)['changeEpoch'] == 1
    started = time.monotonic()
    second = ctl.ensure_session(event='prompt', task_key='second', task_title='Second')

    assert time.monotonic() - started < 2
    assert second['sessionId'] == duplicate['sessionId']
    assert current_change(second)['changeEpoch'] == 2
    assert (
        current_change(second)['baseCommit']
        == run(linked, 'git', 'rev-parse', 'HEAD').stdout.strip()
    )


def test_no_change_turn_has_terminal_receipt_and_next_prompt_rolls_clean_epoch(checkout):
    _primary, _linked, _record, _runtime = checkout
    gates = FakeGates()
    ctl = controller(checkout, gates)
    first_session = ctl.ensure_session(event='prompt', task_key='turn-a')
    first_change = current_change(first_session)

    first_stop = ctl.on_stop(message='chore: no change', turn_key='turn-a')
    sealed = current_change(ctl.store.load_session('session-controller'))
    repeated = ctl.on_stop(message='chore: no change', turn_key='turn-a')

    assert first_stop['code'] == repeated['code'] == 'NO_CHANGES'
    assert first_stop['state'] == repeated['state'] == 'WORKING'
    assert sealed['terminalStopReceipt']['code'] == 'NO_CHANGES'
    assert sealed['terminalStopReceipt']['gateRuns'] == 0
    assert sealed['terminalStopReceipt']['commitCount'] == 0
    assert sealed['terminalStopReceipt']['integrationCount'] == 0
    assert gates.calls == 0

    second_session = ctl.ensure_session(event='prompt', task_key='turn-b')
    second_change = current_change(second_session)

    assert second_session['sessionId'] == first_session['sessionId']
    assert second_change['changeEpoch'] == first_change['changeEpoch'] + 1
    assert second_change['changeId'] != first_change['changeId']
    assert second_change['terminalStopReceipt'] == {}
    assert second_change['candidateTree'] == ''
    assert second_change['currentAttemptId'] == ''
    assert second_change['commitSha'] == ''
    assert second_change['integrationStatus'] == 'PENDING'


def test_terminal_same_prompt_replay_is_idempotent_but_implicit_mutation_rolls(checkout):
    _primary, linked, _record, _runtime = checkout
    gates = FakeGates()
    ctl = controller(checkout, gates)
    ctl.ensure_session(event='prompt', task_key='turn-1')
    (linked / 'one.txt').write_text('one\n', encoding='utf-8')
    ctl.on_stop(message='chore: first')

    replay = ctl.ensure_session(event='prompt', task_key='turn-1')
    assert current_change(replay)['changeEpoch'] == 1
    mutation = ctl.ensure_session(event='mutation')
    assert current_change(mutation)['changeEpoch'] == 2


@pytest.mark.parametrize('failure_status', ['FAIL', 'BLOCKED'])
def test_identical_failed_fingerprint_is_cached_without_second_heavy_gate(checkout, failure_status):
    _primary, linked, _record, _runtime = checkout
    gates = FakeGates(failure_status)
    ctl = controller(checkout, gates)
    ctl.ensure_session(event='prompt', task_key='failure')
    (linked / 'bad.txt').write_text('bad\n', encoding='utf-8')

    first = ctl.on_stop(message='chore: failure')
    started = time.monotonic()
    second = ctl.on_stop(message='chore: failure')

    assert first['state'] == second['state'] == 'REPAIR_REQUIRED'
    assert time.monotonic() - started < 1
    assert second['code'] == 'CACHED_GATE_FAILURE'
    assert second['metrics']['actualHeavyChildren'] == 1
    assert second['metrics']['cachedFailedAttempts'] == 1
    assert gates.calls == 1


def test_candidate_or_environment_change_allows_new_attempt(checkout):
    _primary, linked, _record, _runtime = checkout
    gates = FakeGates('FAIL')
    inputs = Inputs()
    ctl = controller(checkout, gates, inputs)
    ctl.ensure_session(event='prompt', task_key='repair')
    target = linked / 'bad.txt'
    target.write_text('bad\n', encoding='utf-8')
    ctl.on_stop(message='chore: repair')
    target.write_text('fixed candidate\n', encoding='utf-8')
    ctl.on_stop(message='chore: repair')
    inputs.environment = 'environment-2'
    target.write_text('third candidate\n', encoding='utf-8')
    ctl.on_stop(message='chore: repair')

    assert gates.calls == 3
    assert ctl.store.attempt_metrics('session-controller')['actualHeavyChildren'] == 3


def test_fixture_plan_uses_stable_actual_url_and_cached_failure_starts_no_second_child(
    checkout, monkeypatch
):
    _primary, linked, _record, _runtime = checkout
    gates = FakeGates('FAIL')
    inputs = FixtureInputs()
    ctl = controller(checkout, gates, inputs)
    starts = []

    def start_fixture(_change, base_url):
        starts.append(base_url)
        return SimpleNamespace(cleanup=lambda: None), base_url

    monkeypatch.setattr(ctl, '_start_fixture', start_fixture)
    ctl.ensure_session(event='prompt', task_key='fixture-cache')
    (linked / 'fixture.txt').write_text('candidate\n', encoding='utf-8')

    first = ctl.on_stop(message='chore: fixture cache')
    second = ctl.on_stop(message='chore: fixture cache')

    assert first['state'] == second['state'] == 'REPAIR_REQUIRED'
    assert gates.calls == 1
    assert len(starts) == 1
    assert starts[0].startswith('http://127.0.0.1:')
    assert inputs.base_urls == [None, starts[0], None, starts[0]]
    attempt = ctl.store.list_attempts('session-controller')[-1]
    assert attempt['planFingerprint'] == f'plan:{starts[0]}'
    assert attempt['environmentFingerprint'] == f'environment:{starts[0]}'


@pytest.mark.parametrize(
    'failpoint',
    [
        'exact-stage-completed',
        'candidate-fingerprint-written',
        'gate-pass-receipt-written',
        'git-commit-succeeded',
        'result-ref-created',
        'primary-ff-completed',
    ],
)
def test_commit_and_integration_failpoints_resume_without_duplicate_gate_or_commit(
    checkout, monkeypatch, failpoint
):
    primary, linked, _record, _runtime = checkout
    gates = FakeGates()
    ctl = controller(checkout, gates)
    ctl.ensure_session(event='prompt', task_key=failpoint)
    (linked / 'change.txt').write_text(f'{failpoint}\n', encoding='utf-8')
    before_count = int(run(linked, 'git', 'rev-list', '--count', 'HEAD').stdout)
    monkeypatch.setenv('FEIPI_CHANGE_FAILPOINT', failpoint)

    with pytest.raises(Exception, match='injected crash'):
        ctl.on_stop(message=f'chore: {failpoint}')
    monkeypatch.delenv('FEIPI_CHANGE_FAILPOINT')
    result = ctl.on_stop(message=f'chore: {failpoint}')

    assert result['state'] == 'INTEGRATED'
    assert gates.calls == 1
    assert (
        int(run(linked, 'git', 'rev-list', '--count', result['commitSha']).stdout)
        == before_count + 1
    )
    assert run(linked, 'git', 'rev-parse', 'HEAD').stdout.strip() == result['commitSha']
    assert run(primary, 'git', 'rev-parse', 'HEAD').stdout.strip() == result['commitSha']


def test_primary_dirty_preserves_attested_commit_and_blocks_new_change(checkout):
    primary, linked, _record, _runtime = checkout
    gates = FakeGates()
    ctl = controller(checkout, gates)
    ctl.ensure_session(event='prompt', task_key='handoff')
    (linked / 'change.txt').write_text('change\n', encoding='utf-8')
    (primary / 'primary-dirty.txt').write_text('keep\n', encoding='utf-8')

    result = ctl.on_stop(message='chore: handoff')

    assert result['status'] == 'COMMITTED_HANDOFF'
    assert result['state'] == 'COMMITTED_HANDOFF'
    assert result['commitSha']
    assert (
        run(linked, 'git', 'rev-parse', result['resultRef']).stdout.strip() == result['commitSha']
    )
    (linked / 'later.txt').write_text('must remain\n', encoding='utf-8')
    repeated = ctl.on_stop(message='chore: must not commit')
    assert repeated['commitSha'] == result['commitSha']
    assert gates.calls == 1
    with pytest.raises(Exception, match='cannot create next Change'):
        ctl.next_change(task_key='forbidden', task_title='Forbidden')


def test_integrated_dirty_stop_self_heals_into_next_change(checkout):
    _primary, linked, _record, _runtime = checkout
    gates = FakeGates()
    ctl = controller(checkout, gates)
    ctl.ensure_session(event='prompt', task_key='first')
    (linked / 'one.txt').write_text('one\n', encoding='utf-8')
    ctl.on_stop(message='chore: first')
    (linked / 'two.txt').write_text('two\n', encoding='utf-8')

    result = ctl.on_stop(message='chore: second without PromptStart')

    assert result['state'] == 'INTEGRATED'
    assert result['changeId'].endswith('-e2')
    assert gates.calls == 2


def test_post_integrated_tracked_mutation_status_rolls_epoch_and_isolates_receipt(
    checkout, monkeypatch
):
    primary, linked, _record, _runtime = checkout
    gates = FakeGates()
    ctl = controller(checkout, gates)
    session_a = ctl.ensure_session(event='prompt', task_key='task-a')
    task_a_id = current_change(session_a)['changeId']
    (linked / 'task-a.txt').write_text('task a\n', encoding='utf-8')
    task_a_result = ctl.on_stop(message='chore: task a')
    sealed_session = ctl.store.load_session('session-controller')
    sealed_task_a = next(
        item for item in sealed_session['changes'] if item['changeId'] == task_a_id
    )
    task_a_attempt = ctl.store.list_attempts('session-controller', task_a_id)[0]
    task_file = linked / 'openspec' / 'changes' / 'lifecycle-task' / 'tasks.md'
    task_file.write_text('- [x] tracked lifecycle task\n', encoding='utf-8')

    status = ctl.status()
    session_b = ctl.store.load_session('session-controller')
    task_b = current_change(session_b)

    assert status['code'] != 'CHANGE_INTEGRATED'
    assert status['state'] == 'WORKING'
    assert status['sessionId'] == task_a_result['sessionId'] == session_b['sessionId']
    assert task_b['changeEpoch'] == sealed_task_a['changeEpoch'] + 1
    assert task_b['baseCommit'] == task_a_result['commitSha']
    assert (
        next(item for item in session_b['changes'] if item['changeId'] == task_a_id)
        == sealed_task_a
    )
    assert sealed_task_a['commitSha'] == task_a_result['commitSha']
    assert sealed_task_a['resultRef'] == task_a_result['resultRef']
    assert sealed_task_a['commitAttestation']['status'] == 'PASS'
    assert gates.calls == 1, 'status reconciliation must not run required Gate'

    monkeypatch.setenv('FEIPI_CHANGE_FAILPOINT', 'gate-pass-receipt-written')
    with pytest.raises(LifecycleError, match='injected crash'):
        ctl.on_stop(message='chore: task b')
    monkeypatch.delenv('FEIPI_CHANGE_FAILPOINT')
    task_b_attempt = ctl.store.list_attempts('session-controller', str(task_b['changeId']))[0]
    assert gates.calls == 2
    assert task_b_attempt['attemptId'] != task_a_attempt['attemptId']
    assert task_b_attempt['fingerprint'] != task_a_attempt['fingerprint']
    assert task_b_attempt['receiptPath'] != task_a_attempt['receiptPath']
    task_b_result = ctl.on_stop(message='chore: task b')

    assert task_b_result['state'] == 'INTEGRATED'
    assert task_b_result['commitSha'] != task_a_result['commitSha']
    assert gates.calls == 2, 'retry may reuse only Task B own completed PASS receipt'
    assert run(primary, 'git', 'rev-parse', 'HEAD').stdout.strip() == task_b_result['commitSha']
    assert run(
        linked,
        'git',
        'diff-tree',
        '--no-commit-id',
        '--name-only',
        '-r',
        f"{task_a_result['commitSha']}..{task_b_result['commitSha']}",
    ).stdout.splitlines() == ['openspec/changes/lifecycle-task/tasks.md']
    final_task_a = ctl.store.load_session('session-controller')['changes'][0]
    assert final_task_a == sealed_task_a


def test_post_integrated_staged_deletion_rolls_epoch_with_exact_manifest(checkout):
    _primary, linked, _record, _runtime = checkout
    gates = FakeGates()
    ctl = controller(checkout, gates)
    ctl.ensure_session(event='prompt', task_key='task-a')
    (linked / 'task-a.txt').write_text('task a\n', encoding='utf-8')
    task_a = ctl.on_stop(message='chore: task a')
    (linked / 'README.md').unlink()
    run(linked, 'git', 'add', '-u', '--', 'README.md')

    status = ctl.status()
    task_b = current_change(ctl.store.load_session('session-controller'))

    assert status['state'] == 'WORKING'
    assert status['code'] != 'CHANGE_INTEGRATED'
    assert task_b['changeEpoch'] == 2
    assert task_b['baseCommit'] == task_a['commitSha']
    assert gates.calls == 1
    task_b_result = ctl.on_stop(message='chore: remove readme')
    assert gates.calls == 2
    assert run(
        linked,
        'git',
        'diff-tree',
        '--no-commit-id',
        '--name-status',
        '-r',
        f"{task_a['commitSha']}..{task_b_result['commitSha']}",
    ).stdout.splitlines() == ['D\tREADME.md']


def test_post_integrated_untracked_file_rolls_epoch_with_exact_manifest(checkout):
    _primary, linked, _record, _runtime = checkout
    gates = FakeGates()
    ctl = controller(checkout, gates)
    ctl.ensure_session(event='prompt', task_key='task-a')
    (linked / 'task-a.txt').write_text('task a\n', encoding='utf-8')
    task_a = ctl.on_stop(message='chore: task a')
    (linked / 'post-terminal.txt').write_text('task b\n', encoding='utf-8')

    status = ctl.status()
    task_b = current_change(ctl.store.load_session('session-controller'))

    assert status['state'] == 'WORKING'
    assert status['code'] != 'CHANGE_INTEGRATED'
    assert task_b['changeEpoch'] == 2
    assert task_b['baseCommit'] == task_a['commitSha']
    assert gates.calls == 1
    task_b_result = ctl.on_stop(message='chore: add post terminal file')
    assert gates.calls == 2
    assert run(
        linked,
        'git',
        'diff-tree',
        '--no-commit-id',
        '--name-only',
        '-r',
        f"{task_a['commitSha']}..{task_b_result['commitSha']}",
    ).stdout.splitlines() == ['post-terminal.txt']


def test_post_integrated_forbidden_mutation_fails_closed_without_epoch_roll(checkout):
    _primary, linked, _record, _runtime = checkout
    gates = FakeGates()
    ctl = controller(checkout, gates)
    ctl.ensure_session(event='prompt', task_key='task-a')
    (linked / 'task-a.txt').write_text('task a\n', encoding='utf-8')
    task_a = ctl.on_stop(message='chore: task a')
    (linked / '.env').write_text('PRIVATE=value\n', encoding='utf-8')

    with pytest.raises(LifecycleError) as captured:
        ctl.status()

    assert captured.value.status == 'TERMINAL_BLOCKED'
    assert ctl.store.load_session('session-controller')['changeEpoch'] == 1
    assert (
        current_change(ctl.store.load_session('session-controller'))['commitSha']
        == task_a['commitSha']
    )
    assert gates.calls == 1


def test_terminal_head_drift_fails_closed_instead_of_returning_pass(checkout):
    _primary, linked, _record, _runtime = checkout
    ctl = controller(checkout)
    ctl.ensure_session(event='prompt', task_key='first')
    (linked / 'one.txt').write_text('one\n', encoding='utf-8')
    ctl.on_stop(message='chore: first')
    run(linked, 'git', 'checkout', '--detach', 'HEAD^')

    with pytest.raises(LifecycleError, match='terminal Change') as captured:
        ctl.status()
    assert captured.value.code == 'STALE_TERMINAL_HEAD'


def test_post_integrated_external_linked_commit_is_stale_terminal_head(checkout):
    _primary, linked, _record, _runtime = checkout
    gates = FakeGates()
    ctl = controller(checkout, gates)
    ctl.ensure_session(event='prompt', task_key='task-a')
    (linked / 'task-a.txt').write_text('task a\n', encoding='utf-8')
    task_a = ctl.on_stop(message='chore: task a')
    (linked / 'external.txt').write_text('external commit\n', encoding='utf-8')
    run(linked, 'git', 'add', 'external.txt')
    run(linked, 'git', 'commit', '-m', 'external linked head move')

    with pytest.raises(LifecycleError) as captured:
        ctl.status()

    assert captured.value.status == 'TERMINAL_BLOCKED'
    assert captured.value.code == 'STALE_TERMINAL_HEAD'
    session = ctl.store.load_session('session-controller')
    assert session['changeEpoch'] == 1
    assert current_change(session)['commitSha'] == task_a['commitSha']
    assert gates.calls == 1


def test_primary_moved_without_integrated_commit_blocks_clean_terminal_status(checkout):
    primary, linked, _record, _runtime = checkout
    gates = FakeGates()
    ctl = controller(checkout, gates)
    ctl.ensure_session(event='prompt', task_key='task-a')
    (linked / 'task-a.txt').write_text('task a\n', encoding='utf-8')
    task_a = ctl.on_stop(message='chore: task a')
    session = ctl.store.load_session('session-controller')
    task_a_change = current_change(session)
    base = task_a_change['baseCommit']
    run(primary, 'git', 'checkout', '--detach', base)
    run(
        primary,
        'git',
        'update-ref',
        'refs/heads/main_java',
        base,
        task_a['commitSha'],
    )
    assert run(primary, 'git', 'status', '--porcelain').stdout == ''
    assert run(linked, 'git', 'status', '--porcelain').stdout == ''

    with pytest.raises(LifecycleError) as captured:
        ctl.status()

    assert captured.value.status == 'TERMINAL_BLOCKED'
    assert ctl.store.load_session('session-controller')['changeEpoch'] == 1
    assert (
        current_change(ctl.store.load_session('session-controller'))['commitSha']
        == task_a['commitSha']
    )
    assert gates.calls == 1


def test_repeated_clean_terminal_status_is_idempotent_under_one_second(checkout):
    _primary, linked, _record, _runtime = checkout
    gates = FakeGates()
    ctl = controller(checkout, gates)
    ctl.ensure_session(event='prompt', task_key='task-a')
    (linked / 'task-a.txt').write_text('task a\n', encoding='utf-8')
    task_a = ctl.on_stop(message='chore: task a')

    started = time.monotonic()
    first = ctl.status()
    second = ctl.status()

    assert time.monotonic() - started < 1
    assert first['status'] == second['status'] == 'PASS'
    assert first['state'] == second['state'] == 'INTEGRATED'
    assert first['code'] == second['code'] == 'CHANGE_INTEGRATED'
    assert first['commitSha'] == second['commitSha'] == task_a['commitSha']
    assert first['idempotent'] is second['idempotent'] is True
    assert gates.calls == 1


def test_commit_attestation_failure_keeps_commit_monotonic_and_resume_reuses_it(
    checkout, monkeypatch
):
    primary, linked, _record, _runtime = checkout
    gates = FakeGates()
    ctl = controller(checkout, gates)
    ctl.ensure_session(event='prompt', task_key='attestation')
    (linked / 'one.txt').write_text('one\n', encoding='utf-8')
    original = ctl._attest_commit
    monkeypatch.setattr(
        ctl,
        '_attest_commit',
        lambda *_args: (_ for _ in ()).throw(
            LifecycleError('TERMINAL_BLOCKED', 'ATTEST_FAIL', 'attestation failed')
        ),
    )

    with pytest.raises(LifecycleError, match='attestation failed'):
        ctl.on_stop(message='chore: attestation')
    committed = current_change(ctl.store.load_session('session-controller'))
    assert committed['state'] == 'COMMITTED'
    assert committed['commitSha'] == run(linked, 'git', 'rev-parse', 'HEAD').stdout.strip()
    monkeypatch.setattr(ctl, '_attest_commit', original)
    result = ctl.on_stop(message='chore: attestation')
    assert result['state'] == 'INTEGRATED'
    assert gates.calls == 1
    assert run(primary, 'git', 'rev-parse', 'HEAD').stdout.strip() == result['commitSha']


def test_tampered_pass_receipt_blocks_commit(checkout, monkeypatch):
    _primary, linked, _record, _runtime = checkout
    gates = FakeGates()
    ctl = controller(checkout, gates)
    ctl.ensure_session(event='prompt', task_key='tamper')
    (linked / 'one.txt').write_text('one\n', encoding='utf-8')
    monkeypatch.setenv('FEIPI_CHANGE_FAILPOINT', 'gate-pass-receipt-written')
    with pytest.raises(LifecycleError, match='injected crash'):
        ctl.on_stop(message='chore: tamper')
    monkeypatch.delenv('FEIPI_CHANGE_FAILPOINT')
    attempt = ctl.store.list_attempts('session-controller')[-1]
    Path(attempt['artifactPath']).write_text('{"status":"PASS","tampered":true}\n')

    with pytest.raises(LifecycleError) as captured:
        ctl.on_stop(message='chore: tamper')
    assert captured.value.code == 'PASS_RECEIPT_INVALID'
    assert run(linked, 'git', 'rev-parse', 'HEAD').stdout.strip() == checkout[2]['baseCommit']


def test_target_advanced_returns_committed_handoff_without_rewrite(checkout):
    primary, linked, _record, _runtime = checkout
    gates = FakeGates()
    ctl = controller(checkout, gates)
    ctl.ensure_session(event='prompt', task_key='advanced')
    (linked / 'linked.txt').write_text('linked\n', encoding='utf-8')
    (primary / 'primary.txt').write_text('primary\n', encoding='utf-8')
    run(primary, 'git', 'add', 'primary.txt')
    run(primary, 'git', 'commit', '-m', 'target advanced')
    target_head = run(primary, 'git', 'rev-parse', 'HEAD').stdout.strip()

    result = ctl.on_stop(message='chore: advanced')

    assert result['status'] == 'COMMITTED_HANDOFF'
    assert result['code'] == 'TARGET_ADVANCED'
    assert run(primary, 'git', 'rev-parse', 'HEAD').stdout.strip() == target_head
    assert run(linked, 'git', 'rev-parse', 'HEAD').stdout.strip() == result['commitSha']
    assert gates.calls == 1


def test_live_integration_lock_returns_committed_handoff_and_preserves_commit(
    checkout, monkeypatch
):
    primary, linked, _record, _runtime = checkout
    gates = FakeGates()
    ctl = controller(checkout, gates)
    ctl.ensure_session(event='prompt', task_key='lock-busy')
    (linked / 'linked.txt').write_text('linked\n', encoding='utf-8')
    monkeypatch.setenv('FEIPI_CHANGE_FAILPOINT', 'result-ref-created')
    with pytest.raises(LifecycleError, match='injected crash'):
        ctl.on_stop(message='chore: lock busy')
    monkeypatch.delenv('FEIPI_CHANGE_FAILPOINT')
    original_acquire = BoundedMetadataLock.acquire

    def busy_integration(selected):
        if selected.path.name == 'integration.lock':
            raise LockBusyError(
                selected.path,
                owner={'pid': os.getpid(), 'changeId': 'other'},
                waited_seconds=2.0,
                held_seconds=3.0,
            )
        return original_acquire(selected)

    monkeypatch.setattr(BoundedMetadataLock, 'acquire', busy_integration)
    result = ctl.on_stop(message='chore: lock busy')

    assert result['status'] == 'COMMITTED_HANDOFF'
    assert result['code'] == 'LOCK_BUSY'
    assert run(primary, 'git', 'rev-parse', 'HEAD').stdout.strip() == checkout[2]['baseCommit']
    assert run(linked, 'git', 'rev-parse', 'HEAD').stdout.strip() == result['commitSha']
    assert gates.calls == 1


def test_seeded_100_cycle_crash_restart_soak_preserves_all_invariants(checkout, monkeypatch):
    """固定种子覆盖终态后 mutation 与六个 phase boundary，连续 100 次唯一收敛。"""
    primary, linked, _record, _runtime = checkout
    gates = FakeGates()
    ctl = controller(checkout, gates)
    chooser = random.Random(20260715)
    failpoints = (
        'exact-stage-completed',
        'candidate-fingerprint-written',
        'gate-pass-receipt-written',
        'git-commit-succeeded',
        'result-ref-created',
        'primary-ff-completed',
    )
    initial_count = int(run(linked, 'git', 'rev-list', '--count', 'HEAD').stdout)
    reconciliation_paths = {'status': 0, 'on-stop': 0}

    for cycle in range(100):
        if cycle == 0:
            ctl.ensure_session(event='prompt', task_key='chaos-0')
            (linked / 'chaos-live.txt').write_text('0\n', encoding='utf-8')
        else:
            mutation_kind = chooser.choice(('tracked', 'staged', 'untracked'))
            if mutation_kind == 'tracked':
                with (linked / 'chaos-live.txt').open('a', encoding='utf-8') as stream:
                    stream.write(f'{cycle}\n')
            else:
                relative = f'chaos-{cycle:03d}.txt'
                (linked / relative).write_text(f'{cycle}\n', encoding='utf-8')
                if mutation_kind == 'staged':
                    run(linked, 'git', 'add', '--', relative)

            reconciliation = chooser.choice(('status', 'on-stop'))
            reconciliation_paths[reconciliation] += 1
            if reconciliation == 'status':
                reconciled = ctl.status()
                assert reconciled['state'] == 'WORKING'
                assert reconciled['code'] != 'CHANGE_INTEGRATED'
                assert gates.calls == cycle

        failpoint = chooser.choice(failpoints)
        monkeypatch.setenv('FEIPI_CHANGE_FAILPOINT', failpoint)
        with pytest.raises(Exception, match='injected crash'):
            ctl.on_stop(message=f'chore: chaos {cycle}')
        monkeypatch.delenv('FEIPI_CHANGE_FAILPOINT')
        result = ctl.on_stop(message=f'chore: chaos {cycle}')
        assert result['state'] == 'INTEGRATED'
        assert result['metrics']['actualHeavyChildren'] == cycle + 1

    linked_head = run(linked, 'git', 'rev-parse', 'HEAD').stdout.strip()
    assert linked_head == run(primary, 'git', 'rev-parse', 'HEAD').stdout.strip()
    assert int(run(linked, 'git', 'rev-list', '--count', 'HEAD').stdout) == initial_count + 100
    assert gates.calls == 100
    assert all(count > 0 for count in reconciliation_paths.values())
    assert run(linked, 'git', 'status', '--porcelain').stdout == ''


def test_change_core_has_one_bounded_subprocess_owner() -> None:
    change_root = Path(__file__).parents[1] / 'scripts' / 'agent_runtime' / 'change'
    offenders = []
    for path in sorted(change_root.glob('*.py')):
        if path.name == 'runtime.py':
            continue
        source = path.read_text(encoding='utf-8')
        if 'subprocess.run(' in source or 'subprocess.Popen(' in source:
            offenders.append(path.name)
    assert offenders == []


def test_state_transition_and_lifecycle_business_have_single_owners() -> None:
    root = Path(__file__).parents[1]
    transition_offenders = []
    for path in sorted((root / 'scripts').rglob('*.py')):
        relative = path.relative_to(root).as_posix()
        if relative in {
            'scripts/agent_runtime/change/model.py',
            'scripts/agent_runtime/change/store.py',
        }:
            continue
        if 'transition_change(' in path.read_text(encoding='utf-8'):
            transition_offenders.append(relative)
    assert transition_offenders == []

    retired = (
        'scripts/harness/complete_change.py',
        'scripts/harness/stop_entry.py',
        'scripts/agent_runtime/stop/entry.py',
        'scripts/agent_runtime/stop/pipeline.py',
        'scripts/agent_runtime/session/completion.py',
        'scripts/agent_runtime/session/finalize.py',
    )
    assert [relative for relative in retired if (root / relative).exists()] == []
