import argparse
import os
import subprocess
from pathlib import Path

import pytest
from scripts.agent_runtime.session import lifecycle as sessionctl
from scripts.agent_runtime.session.completion import begin_change
from scripts.agent_runtime.session.contract import resolve_runtime_root
from scripts.agent_runtime.session.errors import SessionctlError
from scripts.agent_runtime.stop import evidence as stop_evidence
from scripts.agent_runtime.stop import pipeline as stop_pipeline
from scripts.gates import executor as gate_executor
from scripts.gates import receipt as gate_receipt
from scripts.gates import report as gate_report
from scripts.gates.catalog import CATALOG_VERSION
from scripts.harness import complete_change


@pytest.fixture(autouse=True)
def isolated_runtime_root(tmp_path, monkeypatch):
    monkeypatch.setenv('FEIPI_AGENT_RUNTIME_ROOT', str(tmp_path / 'runtime'))


def run(cmd, cwd, check=True):
    result = subprocess.run(cmd, cwd=cwd, check=False, text=True, capture_output=True)
    if check and result.returncode != 0:
        raise AssertionError(
            f'command failed: {cmd}\nstdout={result.stdout}\nstderr={result.stderr}'
        )
    return result


def git_repo(tmp_path):
    repo = tmp_path / 'repo'
    repo.mkdir()
    run(['git', 'init', '-b', 'main_java'], repo)
    run(['git', 'config', 'user.email', 'complete@example.invalid'], repo)
    run(['git', 'config', 'user.name', 'Complete Test'], repo)
    (repo / 'README.md').write_text('initial\n', encoding='utf-8')
    (repo / 'obsolete.txt').write_text('obsolete\n', encoding='utf-8')
    run(['git', 'add', 'README.md', 'obsolete.txt'], repo)
    run(['git', 'commit', '-m', 'initial'], repo)
    (repo / '.git' / 'info' / 'exclude').write_text(
        'tmp/agent_logs/\ntmp/quality/\n', encoding='utf-8'
    )
    return repo


def linked_run(tmp_path, *, dirty_before_bootstrap=False, detached=False):
    primary = git_repo(tmp_path)
    linked = tmp_path / 'linked'
    branch_args = ['--detach'] if detached else ['-b', 'codex/change']
    run(['git', 'worktree', 'add', *branch_args, str(linked), 'HEAD'], primary)
    if dirty_before_bootstrap:
        (linked / 'before.txt').write_text('before\n', encoding='utf-8')
    sessionctl.cmd_bootstrap(
        argparse.Namespace(
            client='codex',
            session_id='session-complete',
            cwd=str(linked),
            hook_event='SessionStart',
            checkout_creator='codex',
            run_id=None,
            worktree_id=None,
            parent_run_id=None,
            repo_root=str(linked),
        )
    )
    registry = sessionctl.Registry(linked)
    with registry.locked():
        record = next(
            item
            for item in registry.all_runs()
            if item['sessionId'] == 'session-complete'
            and item['checkoutRoot'] == str(linked.resolve())
        )
    if not dirty_before_bootstrap:
        record = begin_change(
            linked,
            record['runId'],
            activation_source='test:before-mutation',
        )
    return primary, linked, record


@pytest.fixture
def cheap_capabilities(monkeypatch):
    fake = complete_change.PreflightResult(
        python=os.sys.executable,
        python_version='3.12.0',
        pre_commit='/usr/bin/true',
        node='/usr/bin/true:v1',
        playwright='/usr/bin/true',
        browser='/usr/bin/true',
        java='/usr/bin/true:v1',
        gradle='/usr/bin/true',
        fixture='synthetic',
        commit_path=os.environ.get('PATH', ''),
    )
    monkeypatch.setattr(complete_change, 'cheap_preflight', lambda _repo: fake)
    monkeypatch.setattr(complete_change, '_run_pre_commit', lambda _repo, _pre, _files: None)
    return fake


def install_fake_stop_pass(monkeypatch, calls, *, with_receipt=True):
    def fake_run_stop(client, payload, *, handoff_on_failure=False, adapter_mode='hook'):
        assert adapter_mode == 'cli'
        calls.append(payload['runId'])
        checkout = Path(payload['cwd'])
        registry = sessionctl.Registry(checkout)
        with registry.locked():
            record = registry.load_run(payload['runId'])
        facts = stop_evidence.collect_git_evidence(checkout, record)
        facts['candidateTree'] = run(['git', 'write-tree'], checkout).stdout.strip()
        changed_files = sorted(facts['changedFiles'])
        command_groups = [
            {
                'groupId': 'fake-group',
                'kind': 'command',
                'gates': ['fake-required'],
                'command': ['/usr/bin/true'],
                'resources': [],
                'dependsOn': [],
                'aggregationReason': '',
            }
        ]
        plan_fingerprint = 'fake-plan-fingerprint'
        command_fingerprint = gate_executor._stable_hash(  # noqa: SLF001
            [group['command'] for group in command_groups]
        )
        summary = gate_report.build_summary(
            'required',
            record.get('changeId') or 'fake-change',
            gate_report.utc_now(),
            [
                gate_report.GateDetail(
                    name='fake-required',
                    status=gate_report.PASS,
                    command=['/usr/bin/true'],
                    groupId='fake-group',
                )
            ],
            repo_root=checkout,
            execution_metadata={
                'planId': 'fake-plan',
                'planFingerprint': plan_fingerprint,
                'checkoutFingerprint': gate_receipt.checkout_content_fingerprint(checkout),
                'catalogVersion': CATALOG_VERSION,
                'commandGroups': command_groups,
                'processCounts': {'gradle': 0, 'python': 0, 'bash': 0, 'total': 0},
            },
        )
        artifact = gate_report.write_quality_summary(
            checkout / 'tmp' / 'quality', summary, target_specific=True
        )
        facts['gateArtifactPath'] = str(artifact)
        if with_receipt:
            environment = {'BASE_URL': os.environ.get('BASE_URL', '')}
            attribution = {'explicitChangedFiles': True}
            gate_inputs = {'changedFiles': changed_files}
            cache_key = gate_receipt.content_cache_key(
                'harness',
                changed_files,
                checkout,
                environment,
                attribution=attribution,
                plan_fingerprint=plan_fingerprint,
                command_fingerprint=command_fingerprint,
                gate_inputs=gate_inputs,
            )
            receipt_path = gate_receipt.write_pass_receipt(
                checkout / 'tmp' / 'quality',
                target='harness',
                change_id=record.get('changeId') or 'fake-change',
                changed_files=changed_files,
                cache_key=cache_key,
                artifact_path=str(artifact),
                repo_root=checkout,
                attribution=attribution,
                plan_fingerprint=plan_fingerprint,
                command_fingerprint=command_fingerprint,
                environment=environment,
                gate_inputs=gate_inputs,
            )
            facts['gateReceiptPaths'] = [str(receipt_path)]
        else:
            facts['gateReceiptPaths'] = []
        facts['gateReused'] = False
        sessionctl.record_stop_result(
            checkout,
            payload['runId'],
            stop_exit=0,
            summary_status='PASS',
            validated_facts=facts,
            handoff_on_failure=handoff_on_failure,
        )
        return 0

    monkeypatch.setattr(stop_pipeline, 'run_stop', fake_run_stop)


def invoke(linked, record, *files):
    args = [
        '--repo-root',
        str(linked),
        '--run-id',
        record['runId'],
        '--message',
        'chore: complete change',
    ]
    for path in files:
        args.extend(['--file', path])
    return complete_change.main(args)


def read_run(linked, run_id):
    registry = sessionctl.Registry(linked)
    with registry.locked():
        return registry.load_run(run_id)


def test_preflight_uses_project_python_path_and_starts_ready_managed_fixture(tmp_path, monkeypatch):
    repo = tmp_path / 'repo'
    for path in (
        repo / 'node_modules/.bin/playwright',
        repo / 'tests/playwright/start-java-fixture-server.js',
        repo / 'java/app-cli/build/install/app-cli/bin/app-cli',
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('fixture\n', encoding='utf-8')
    fixture_source = repo / 'tests/fixtures/generate-session-fixtures.js'
    fixture_source.parent.mkdir(parents=True, exist_ok=True)
    fixture_source.write_text('synthetic: true; baseTimestampMs = 1;\n', encoding='utf-8')
    gradle = repo / 'gradlew'
    gradle.write_text('#!/bin/sh\n', encoding='utf-8')
    gradle.chmod(0o755)
    project_python = tmp_path / 'python312/bin/python3.12'
    monkeypatch.setattr(
        complete_change, '_project_python', lambda _repo: (project_python, '3.12.11')
    )
    monkeypatch.setattr(complete_change, '_command_path', lambda _repo, _name: Path('/bin/true'))
    monkeypatch.setattr(complete_change, '_browser_binary', lambda: Path('/bin/true'))
    monkeypatch.setattr(complete_change, '_run_version', lambda *_args, **_kwargs: 'v1')
    monkeypatch.setattr(
        complete_change,
        '_start_managed_fixture_server',
        lambda *_args: ('http://127.0.0.1:32123', 4321),
    )
    monkeypatch.delenv('BASE_URL', raising=False)

    result = complete_change.cheap_preflight(repo)

    assert result.python == str(project_python)
    assert result.fixture == 'http://127.0.0.1:32123'
    assert result.fixture_managed is True
    assert result.fixture_pid == 4321
    assert result.commit_path.split(os.pathsep)[:2] == [
        str(project_python.parent),
        str(repo / '.venv/bin'),
    ]


def test_external_fixture_preflight_checks_dashboard_and_synthetic_session_identity(monkeypatch):
    visited = []

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def urlopen(url, timeout):
        visited.append((url, timeout))
        return Response()

    monkeypatch.setattr(complete_change.urllib.request, 'urlopen', urlopen)

    assert complete_change._check_external_server('http://127.0.0.1:9876') == (
        'http://127.0.0.1:9876'
    )
    assert [url for url, _timeout in visited] == [
        'http://127.0.0.1:9876/dashboard',
        'http://127.0.0.1:9876/sessions/claude_code/hifi-viz-session-001',
        'http://127.0.0.1:9876/sessions/claude_code/long-session-001',
    ]


def test_complete_change_runs_one_gate_commits_attests_and_ff_integrates(
    tmp_path, monkeypatch, cheap_capabilities
):
    primary, linked, record = linked_run(tmp_path)
    calls = []
    install_fake_stop_pass(monkeypatch, calls)
    (linked / 'README.md').write_text('updated\n', encoding='utf-8')
    (linked / 'added.txt').write_text('added\n', encoding='utf-8')
    (linked / 'obsolete.txt').unlink()

    assert invoke(linked, record, 'README.md', 'added.txt', 'obsolete.txt') == 0

    assert calls == [record['runId']]
    assert (
        run(['git', 'log', '-1', '--format=%s'], primary).stdout.strip() == 'chore: complete change'
    )
    assert (
        run(['git', 'rev-parse', 'HEAD'], primary).stdout
        == run(['git', 'rev-parse', 'HEAD'], linked).stdout
    )
    latest = read_run(linked, record['runId'])
    completion = latest['completion']
    assert completion['state'] == 'INTEGRATED'
    assert completion['heavyGateRuns'] == 1
    assert completion['postCommitHeavyProcessCount'] == 0
    assert completion['commitAttestation']['status'] == 'PASS'
    assert (
        completion['candidateTree']
        == run(['git', 'rev-parse', 'HEAD^{tree}'], linked).stdout.strip()
    )
    assert completion['resultRef'] == f"refs/heads/codex/result/{record['runId']}"
    assert resolve_runtime_root(linked) in Path(latest['integrationSummary']).parents


def test_detached_checkout_commits_and_creates_result_ref(
    tmp_path, monkeypatch, cheap_capabilities
):
    primary, linked, record = linked_run(tmp_path, detached=True)
    calls = []
    install_fake_stop_pass(monkeypatch, calls)
    (linked / 'change.txt').write_text('change\n', encoding='utf-8')

    assert invoke(linked, record, 'change.txt') == 0

    latest = read_run(linked, record['runId'])
    completion = latest['completion']
    assert calls == [record['runId']]
    assert (
        run(['git', 'rev-parse', completion['resultRef']], linked).stdout.strip()
        == completion['commitSha']
    )
    assert run(['git', 'rev-parse', 'HEAD'], primary).stdout.strip() == completion['commitSha']


def test_primary_dirty_does_not_block_commit_but_blocks_integration(
    tmp_path, monkeypatch, cheap_capabilities
):
    primary, linked, record = linked_run(tmp_path)
    install_fake_stop_pass(monkeypatch, [])
    (linked / 'change.txt').write_text('change\n', encoding='utf-8')
    (primary / 'primary.txt').write_text('dirty\n', encoding='utf-8')

    assert invoke(linked, record, 'change.txt') == 2

    latest = read_run(linked, record['runId'])
    completion = latest['completion']
    assert completion['state'] == 'HANDOFF_REQUIRED'
    assert completion['commitSha']
    assert (
        run(['git', 'rev-parse', completion['resultRef']], linked).stdout.strip()
        == completion['commitSha']
    )
    assert (
        run(['git', 'log', '-1', '--format=%s'], linked).stdout.strip() == 'chore: complete change'
    )
    assert run(['git', 'log', '-1', '--format=%s'], primary).stdout.strip() == 'initial'


@pytest.mark.parametrize('missing', ['python', 'path', 'playwright', 'server'])
def test_preflight_failure_is_retryable_and_starts_zero_heavy_gates(tmp_path, monkeypatch, missing):
    _primary, linked, record = linked_run(tmp_path)
    calls = []
    install_fake_stop_pass(monkeypatch, calls)
    (linked / 'change.txt').write_text('change\n', encoding='utf-8')

    def fail(_repo):
        raise complete_change.RetryableCompletionError(f'missing {missing}', f'fix-{missing}')

    monkeypatch.setattr(complete_change, 'cheap_preflight', fail)
    assert invoke(linked, record, 'change.txt') == 2
    completion = read_run(linked, record['runId'])['completion']
    assert completion['state'] == 'BLOCKED_RETRYABLE'
    assert completion['fixCommand'] == f'fix-{missing}'
    assert completion['heavyGateProcessCount'] == 0
    assert calls == []


def test_same_run_retry_after_preflight_failure_needs_no_new_worktree(
    tmp_path, monkeypatch, cheap_capabilities
):
    primary, linked, record = linked_run(tmp_path)
    before = run(['git', 'worktree', 'list', '--porcelain'], primary).stdout
    before_paths = [line for line in before.splitlines() if line.startswith('worktree ')]
    (linked / 'change.txt').write_text('change\n', encoding='utf-8')
    original = complete_change.cheap_preflight
    monkeypatch.setattr(
        complete_change,
        'cheap_preflight',
        lambda _repo: (_ for _ in ()).throw(
            complete_change.RetryableCompletionError('missing tool', 'fix-tool')
        ),
    )
    assert invoke(linked, record, 'change.txt') == 2
    monkeypatch.setattr(complete_change, 'cheap_preflight', original)
    install_fake_stop_pass(monkeypatch, [])

    assert invoke(linked, record, 'change.txt') == 0
    after = run(['git', 'worktree', 'list', '--porcelain'], primary).stdout
    assert [line for line in after.splitlines() if line.startswith('worktree ')] == before_paths
    assert read_run(linked, record['runId'])['completion']['state'] == 'INTEGRATED'


def test_exact_stage_preserves_delete_mode_and_symlink(tmp_path, monkeypatch, cheap_capabilities):
    _primary, linked, record = linked_run(tmp_path)
    calls = []
    install_fake_stop_pass(monkeypatch, calls)
    executable = linked / 'tool.sh'
    executable.write_text('#!/bin/sh\n', encoding='utf-8')
    run(['git', 'add', 'tool.sh'], linked)
    run(['git', 'commit', '-m', 'add tool'], linked)
    # Refresh run base facts for this synthetic case before task-owned mutations.
    with sessionctl.Registry(linked).locked():
        current = sessionctl.Registry(linked).load_run(record['runId'])
        current['baseCommit'] = run(['git', 'rev-parse', 'HEAD'], linked).stdout.strip()
        current['headCommit'] = current['baseCommit']
        current['completion']['oldHead'] = current['baseCommit']
        current['changeBegin']['baseCommit'] = current['baseCommit']
        sessionctl.Registry(linked).save_run(current)
    executable.chmod(0o755)
    (linked / 'obsolete.txt').unlink()
    (linked / 'link.txt').symlink_to('README.md')

    assert invoke(linked, current, 'tool.sh', 'obsolete.txt', 'link.txt') == 0
    assert calls == [record['runId']]
    modes = run(['git', 'ls-tree', 'HEAD', 'tool.sh', 'link.txt'], linked).stdout
    assert '100755' in modes and '120000' in modes
    assert not (linked / 'obsolete.txt').exists()


def test_unexpected_file_is_never_staged_or_committed(tmp_path, monkeypatch, cheap_capabilities):
    primary, linked, record = linked_run(tmp_path)
    (linked / 'declared.txt').write_text('ok\n', encoding='utf-8')
    (linked / 'extra.txt').write_text('no\n', encoding='utf-8')
    install_fake_stop_pass(monkeypatch, [])

    assert invoke(linked, record, 'declared.txt') == 2
    assert run(['git', 'diff', '--cached', '--name-only'], linked).stdout == ''
    assert (
        run(['git', 'rev-parse', 'HEAD'], linked).stdout
        == run(['git', 'rev-parse', 'HEAD'], primary).stdout
    )


def test_precommit_candidate_mutation_invalidates_before_gate(
    tmp_path, monkeypatch, cheap_capabilities
):
    _primary, linked, record = linked_run(tmp_path)
    (linked / 'change.txt').write_text('before\n', encoding='utf-8')
    calls = []
    install_fake_stop_pass(monkeypatch, calls)

    def mutate(_repo, _preflight, _expected):
        (linked / 'change.txt').write_text('after\n', encoding='utf-8')
        raise complete_change.RetryableCompletionError('candidate changed', 'pre-commit run')

    monkeypatch.setattr(complete_change, '_run_pre_commit', mutate)
    assert invoke(linked, record, 'change.txt') == 2
    assert calls == []
    assert read_run(linked, record['runId'])['completion']['state'] == 'BLOCKED_RETRYABLE'


def test_target_advance_disjoint_delta_reuses_validation_without_finalize_gate(
    tmp_path, monkeypatch, cheap_capabilities
):
    primary, linked, record = linked_run(tmp_path)
    calls = []
    install_fake_stop_pass(monkeypatch, calls)
    (linked / 'change.txt').write_text('change\n', encoding='utf-8')
    original_stop = complete_change._run_stop

    def stop_then_advance(repo, run_id, base_url):
        result = original_stop(repo, run_id, base_url)
        (primary / 'README.md').write_text('target advance\n', encoding='utf-8')
        run(['git', 'add', 'README.md'], primary)
        run(['git', 'commit', '-m', 'target advance'], primary)
        return result

    monkeypatch.setattr(complete_change, '_run_stop', stop_then_advance)
    assert invoke(linked, record, 'change.txt') == 0
    completion = read_run(linked, record['runId'])['completion']
    assert calls == [record['runId']]
    assert completion['state'] == 'INTEGRATED'
    assert completion['validationReuse']['status'] == 'REUSED'
    assert completion['validationReuse']['heavyGateRuns'] == 0
    assert completion['commitSha'] != completion['integratedCommitSha']
    assert (
        run(['git', 'rev-parse', completion['resultRef']], linked).stdout.strip()
        == completion['commitSha']
    )
    assert (
        run(['git', 'rev-parse', completion['integrationRef']], linked).stdout.strip()
        == completion['integratedCommitSha']
    )
    assert completion['integrationAttestation']['exactEntriesPreserved'] is True


def test_target_conflict_preserves_original_commit_and_result_ref(
    tmp_path, monkeypatch, cheap_capabilities
):
    primary, linked, record = linked_run(tmp_path)
    install_fake_stop_pass(monkeypatch, [])
    (linked / 'README.md').write_text('result\n', encoding='utf-8')
    original_stop = complete_change._run_stop

    def stop_then_conflict(repo, run_id, base_url):
        result = original_stop(repo, run_id, base_url)
        (primary / 'README.md').write_text('target\n', encoding='utf-8')
        run(['git', 'add', 'README.md'], primary)
        run(['git', 'commit', '-m', 'conflict'], primary)
        return result

    monkeypatch.setattr(complete_change, '_run_stop', stop_then_conflict)
    assert invoke(linked, record, 'README.md') == 2
    completion = read_run(linked, record['runId'])['completion']
    assert completion['state'] == 'HANDOFF_REQUIRED'
    assert completion['commitSha']
    assert (
        run(['git', 'rev-parse', completion['resultRef']], linked).stdout.strip()
        == completion['commitSha']
    )


def test_integrated_completion_is_idempotent(tmp_path, monkeypatch, cheap_capabilities):
    _primary, linked, record = linked_run(tmp_path)
    calls = []
    install_fake_stop_pass(monkeypatch, calls)
    (linked / 'change.txt').write_text('change\n', encoding='utf-8')
    assert invoke(linked, record, 'change.txt') == 0
    first = read_run(linked, record['runId'])['completion']['commitSha']

    assert invoke(linked, record, 'change.txt') == 0
    assert calls == [record['runId']]
    assert read_run(linked, record['runId'])['completion']['commitSha'] == first


def test_post_commit_attestation_failure_preserves_commit_identity_and_result_ref(
    tmp_path, monkeypatch, cheap_capabilities
):
    _primary, linked, record = linked_run(tmp_path)
    install_fake_stop_pass(monkeypatch, [])
    (linked / 'change.txt').write_text('change\n', encoding='utf-8')
    monkeypatch.setattr(
        complete_change,
        '_attest_commit',
        lambda *_args, **_kwargs: (_ for _ in ()).throw(SessionctlError('attestation failed')),
    )

    assert invoke(linked, record, 'change.txt') == 2
    completion = read_run(linked, record['runId'])['completion']
    assert completion['state'] == 'HANDOFF_REQUIRED'
    assert completion['commitSha'] == run(['git', 'rev-parse', 'HEAD'], linked).stdout.strip()
    assert (
        run(['git', 'rev-parse', completion['resultRef']], linked).stdout.strip()
        == completion['commitSha']
    )


def test_empty_gate_receipts_cannot_attest_even_when_summary_says_pass(
    tmp_path, monkeypatch, cheap_capabilities
):
    _primary, linked, record = linked_run(tmp_path)
    install_fake_stop_pass(monkeypatch, [], with_receipt=False)
    (linked / 'change.txt').write_text('change\n', encoding='utf-8')

    assert invoke(linked, record, 'change.txt') == 2
    completion = read_run(linked, record['runId'])['completion']
    assert completion['state'] == 'HANDOFF_REQUIRED'
    assert completion['commitSha']
    assert 'no target PASS receipts' in completion['reason']


def capture_exact_stage_adds(monkeypatch):
    original_run = subprocess.run
    calls = []

    def recording_run(command, *args, **kwargs):
        if isinstance(command, list) and '--pathspec-from-file=-' in command:
            payload = kwargs.get('input', b'')
            calls.append({value.decode() for value in payload.split(b'\0') if value})
        return original_run(command, *args, **kwargs)

    monkeypatch.setattr(subprocess, 'run', recording_run)
    return calls


def test_stage_exact_is_idempotent_for_staged_deletion(tmp_path, monkeypatch):
    repo = git_repo(tmp_path)
    (repo / 'README.md').write_text('staged change\n', encoding='utf-8')
    (repo / 'obsolete.txt').unlink()
    run(['git', 'add', '-A', '--', 'README.md', 'obsolete.txt'], repo)
    add_calls = capture_exact_stage_adds(monkeypatch)

    complete_change._stage_exact(repo, {'README.md', 'obsolete.txt'})

    assert add_calls == []
    assert run(['git', 'diff', '--cached', '--name-status'], repo).stdout.splitlines() == [
        'M\tREADME.md',
        'D\tobsolete.txt',
    ]


def test_stage_exact_stages_unstaged_deletion(tmp_path, monkeypatch):
    repo = git_repo(tmp_path)
    (repo / 'obsolete.txt').unlink()
    add_calls = capture_exact_stage_adds(monkeypatch)

    complete_change._stage_exact(repo, {'obsolete.txt'})

    assert add_calls == [{'obsolete.txt'}]
    assert run(['git', 'diff', '--cached', '--name-status'], repo).stdout == 'D\tobsolete.txt\n'


def test_stage_exact_restages_path_with_staged_and_unstaged_content(tmp_path, monkeypatch):
    repo = git_repo(tmp_path)
    (repo / 'README.md').write_text('staged version\n', encoding='utf-8')
    run(['git', 'add', 'README.md'], repo)
    (repo / 'README.md').write_text('latest version\n', encoding='utf-8')
    add_calls = capture_exact_stage_adds(monkeypatch)

    complete_change._stage_exact(repo, {'README.md'})

    assert add_calls == [{'README.md'}]
    assert run(['git', 'show', ':README.md'], repo).stdout == 'latest version\n'
    assert run(['git', 'diff', '--name-only'], repo).stdout == ''


def test_stage_exact_stages_declared_untracked_path(tmp_path, monkeypatch):
    repo = git_repo(tmp_path)
    (repo / 'new.txt').write_text('new\n', encoding='utf-8')
    add_calls = capture_exact_stage_adds(monkeypatch)

    complete_change._stage_exact(repo, {'new.txt'})

    assert add_calls == [{'new.txt'}]
    assert run(['git', 'show', ':new.txt'], repo).stdout == 'new\n'


@pytest.mark.parametrize('extra_state', ['staged', 'unstaged', 'untracked'])
def test_stage_exact_rejects_out_of_scope_path_before_index_mutation(
    tmp_path, monkeypatch, extra_state
):
    repo = git_repo(tmp_path)
    (repo / 'README.md').write_text('declared\n', encoding='utf-8')
    if extra_state == 'untracked':
        (repo / 'extra.txt').write_text('extra\n', encoding='utf-8')
    else:
        (repo / 'obsolete.txt').write_text('extra\n', encoding='utf-8')
        if extra_state == 'staged':
            run(['git', 'add', 'obsolete.txt'], repo)
    tree_before = run(['git', 'write-tree'], repo).stdout.strip()
    add_calls = capture_exact_stage_adds(monkeypatch)

    with pytest.raises(SessionctlError, match='exact stage scope mismatch before index mutation'):
        complete_change._stage_exact(repo, {'README.md'})

    assert add_calls == []
    assert run(['git', 'write-tree'], repo).stdout.strip() == tree_before


def test_stage_exact_skips_git_add_when_every_path_is_staged(tmp_path, monkeypatch):
    repo = git_repo(tmp_path)
    (repo / 'README.md').write_text('staged\n', encoding='utf-8')
    run(['git', 'add', 'README.md'], repo)
    add_calls = capture_exact_stage_adds(monkeypatch)

    complete_change._stage_exact(repo, {'README.md'})

    assert add_calls == []


def test_stage_exact_rejects_final_staged_scope_mismatch(tmp_path, monkeypatch):
    repo = git_repo(tmp_path)
    staged_results = iter([{'README.md'}, {'unexpected.txt'}])
    monkeypatch.setattr(complete_change, '_staged_paths', lambda _repo: next(staged_results))
    monkeypatch.setattr(complete_change, '_unstaged_paths', lambda _repo: set())
    monkeypatch.setattr(complete_change, '_untracked_paths', lambda _repo: set())

    with pytest.raises(SessionctlError, match='staged file scope mismatch'):
        complete_change._stage_exact(repo, {'README.md'})
