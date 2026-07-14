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
    """固定种子覆盖六个 phase boundary，验证 100 个连续 Change 最终唯一收敛。"""
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

    for cycle in range(100):
        ctl.ensure_session(event='prompt', task_key=f'chaos-{cycle}')
        (linked / f'chaos-{cycle:03d}.txt').write_text(f'{cycle}\n', encoding='utf-8')
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

    for relative in (
        'scripts/harness/complete_change.py',
        'scripts/harness/stop_entry.py',
        'scripts/agent_runtime/stop/entry.py',
        'scripts/agent_runtime/stop/pipeline.py',
    ):
        source = (root / relative).read_text(encoding='utf-8')
        for forbidden in (
            'run_service',
            'BoundedMetadataLock',
            'FixtureSupervisor',
            'git commit',
            'gradlew',
        ):
            assert forbidden not in source, f'{relative} duplicates lifecycle owner: {forbidden}'
