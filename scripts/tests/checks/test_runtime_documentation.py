"""Use synthetic task identities and real Git objects for runtime document boundaries."""

from __future__ import annotations

import subprocess
from dataclasses import replace

import pytest
from scripts.gates.checks.agent import check_documentation as policy
from scripts.gates.checks.check_protocol import CheckStatus


def git(root, *arguments):
    return subprocess.run(
        ['git', '-C', str(root), *arguments],
        check=True,
        capture_output=True,
    )


@pytest.fixture
def repository(tmp_path, monkeypatch):
    git(tmp_path, 'init', '-q')
    git(tmp_path, 'config', 'user.name', 'Synthetic Test')
    git(tmp_path, 'config', 'user.email', 'synthetic@example.invalid')
    (tmp_path / 'AGENTS.md').write_text('source rules', encoding='utf-8')
    git(tmp_path, 'add', 'AGENTS.md')
    git(tmp_path, 'commit', '-qm', 'synthetic source')
    monkeypatch.setattr(policy, 'ROOT', tmp_path)
    for key in policy.MULTICA_IDENTITY_KEYS:
        monkeypatch.delenv(key, raising=False)
    return tmp_path


@pytest.fixture
def identity(monkeypatch):
    for key in policy.MULTICA_IDENTITY_KEYS:
        value = '00000000-0000-4000-8000-000000000001' if key.endswith('_ID') else 'synthetic'
        if key == 'MULTICA_SERVER_URL':
            value = 'https://synthetic.example.invalid'
        monkeypatch.setenv(key, value)


def inputs(text, *, source_limit=2800, runtime_limit=32768, budget=36864):
    return policy.DocumentInputs(
        manifest={
            'size_limits': {'AGENTS.md': source_limit, 'multica_runtime_bytes': runtime_limit}
        },
        agents_text=text,
        codex_config={'project_doc_max_bytes': budget},
        documents={},
    )


def injected(source='source rules', body='synthetic instructions'):
    return source + '\n\n' + policy.MULTICA_BEGIN + '\n' + body + '\n' + policy.MULTICA_END + '\n'


def test_valid_runtime_and_cleanup(repository, identity):
    assert policy._check_sizes(inputs(injected())) == []
    assert policy._check_sizes(inputs(injected(source='source rules\n'))) == []
    assert policy._check_sizes(inputs('source rules')) == []


@pytest.mark.parametrize('boundary', ['', r'\n', r'\r\n', r'\n\n'])
def test_runtime_boundary_metadata_keeps_exact_byte_limits(repository, identity, boundary):
    metadata = '<!-- MULTICA-RUNTIME original-boundary: "' + boundary + '" -->'
    text = injected(source='中\n', body=metadata + '\nsynthetic instructions')
    source, runtime, errors = policy._runtime_source(text)
    assert errors == []
    assert source == '中\n'
    assert metadata in runtime
    assert (
        policy._check_sizes(inputs(text, source_limit=4, runtime_limit=len(runtime.encode()))) == []
    )
    assert policy._check_sizes(inputs(text, source_limit=3))
    assert policy._check_sizes(inputs(text, runtime_limit=len(runtime.encode()) - 1))


@pytest.mark.parametrize(
    'body',
    [
        '<!-- MULTICA-RUNTIME original-boundary: "arbitrary" -->\ninstructions',
        '<!-- MULTICA-RUNTIME original-boundary: "\n" -->\ninstructions',
        '<!-- MULTICA-RUNTIME original-boundary: "\\t" -->\ninstructions',
        '<!-- MULTICA-RUNTIME original-boundary: "\\n" -->',
        'instructions\n<!-- MULTICA-RUNTIME original-boundary: "\\n" -->',
        '<!-- MULTICA-RUNTIME original-boundary: "\\n" -->\n'
        '<!-- MULTICA-RUNTIME original-boundary: "\\n" -->\ninstructions',
    ],
)
def test_runtime_rejects_malformed_or_misplaced_boundary_metadata(repository, identity, body):
    assert policy._check_sizes(inputs(injected(body=body)))


@pytest.mark.parametrize(
    'missing',
    [
        'all',
        'MULTICA_TOKEN',
        'MULTICA_TASK_ID',
        'MULTICA_AGENT_ID',
        'MULTICA_WORKSPACE_ID',
        'MULTICA_SERVER_URL',
    ],
)
def test_runtime_requires_complete_identity(repository, identity, monkeypatch, missing):
    for key in policy.MULTICA_IDENTITY_KEYS if missing == 'all' else [missing]:
        monkeypatch.delenv(key)
    assert policy._check_sizes(inputs(injected()))


@pytest.mark.parametrize('value', ['', 'not-a-task', '../task', 'TASK-55\nextra'])
def test_runtime_rejects_unreasonable_task_identity(repository, identity, monkeypatch, value):
    monkeypatch.setenv('MULTICA_TASK_ID', value)
    assert policy._check_sizes(inputs(injected()))


@pytest.mark.parametrize(
    'case',
    [
        'duplicate',
        'nested',
        'missing-begin',
        'missing-end',
        'reversed',
        'separator',
        'altered-marker',
        'trailing',
        'empty',
        'body-newline',
    ],
)
def test_malformed_runtime_rejected(repository, identity, case):
    text = injected()
    variants = {
        'duplicate': text + '\n' + injected(''),
        'nested': injected(body=policy.MULTICA_BEGIN + '\ninner'),
        'missing-begin': text.replace(policy.MULTICA_BEGIN, ''),
        'missing-end': text.replace(policy.MULTICA_END, ''),
        'reversed': 'source rules\n\n'
        + policy.MULTICA_END
        + '\nbody\n'
        + policy.MULTICA_BEGIN
        + '\n',
        'separator': text.replace('\n\n', '\n', 1),
        'altered-marker': text.replace('(auto-managed; do not edit)', '(altered)'),
        'trailing': text + 'extra prose',
        'empty': injected(body=''),
        'body-newline': injected(body='synthetic\n'),
    }
    assert policy._check_sizes(inputs(variants[case]))


def test_separate_byte_limits_and_physical_codex_budget(repository, identity):
    text = injected(source='中' * 934)
    assert any('AGENTS.md' in error for error in policy._check_sizes(inputs(text)))
    text = injected(body='中' * 11000)
    assert any('runtime' in error for error in policy._check_sizes(inputs(text)))
    text = injected()
    assert policy._check_sizes(inputs(text, budget=len(text.encode()) + 99))
    assert policy._check_sizes(inputs(text, budget=len(text.encode()) + 100)) == []
    assert policy._check_sizes(replace(inputs(text), codex_config={}))
    assert policy._check_sizes(inputs(text, runtime_limit=True))


@pytest.mark.parametrize('tracked', ['staged', 'committed'])
@pytest.mark.parametrize('metadata', [False, True])
def test_git_objects_cannot_hide_runtime_even_after_worktree_cleanup(
    repository, identity, tracked, metadata
):
    body = 'synthetic instructions'
    if metadata:
        body = '<!-- MULTICA-RUNTIME original-boundary: "\\n" -->\n' + body
    (repository / 'AGENTS.md').write_text(injected(body=body), encoding='utf-8')
    git(repository, 'add', 'AGENTS.md')
    if tracked == 'committed':
        git(repository, 'commit', '-qm', 'synthetic forbidden runtime')
        (repository / 'AGENTS.md').write_text('clean source', encoding='utf-8')
        git(repository, 'add', 'AGENTS.md')
    assert policy._check_sizes(inputs('clean source'))


def test_unreadable_git_identity_fails_closed(repository, identity, monkeypatch):
    git(repository, 'rm', '--cached', 'AGENTS.md')
    monkeypatch.setattr(policy, '_load_document_inputs', lambda: inputs(injected()))
    result = policy.check([])
    assert result.status is CheckStatus.FAIL
    assert result.reason == 'input-unavailable'


def test_ordinary_documents_keep_size_and_optional_budget_rules(repository):
    assert policy._check_sizes(replace(inputs('source'), codex_config={})) == []
    assert policy._check_sizes(inputs('中' * 934))


@pytest.mark.parametrize('problem', ['missing-head', 'invalid-utf8'])
def test_git_source_unavailable_or_unreadable_is_rejected(
    repository, identity, monkeypatch, problem
):
    if problem == 'missing-head':
        git(repository, 'update-ref', '-d', 'HEAD')
    else:
        (repository / 'AGENTS.md').write_bytes(b'\xff')
        git(repository, 'add', 'AGENTS.md')
    monkeypatch.setattr(policy, '_load_document_inputs', lambda: inputs(injected()))
    result = policy.check([])
    assert result.status is CheckStatus.FAIL
    assert result.reason == 'input-unavailable'


def test_runtime_byte_boundaries_include_separator_without_trimming_source(repository, identity):
    text = injected(source='中\n')
    _, runtime, errors = policy._runtime_source(text)
    assert errors == []
    assert (
        policy._check_sizes(inputs(text, source_limit=4, runtime_limit=len(runtime.encode()))) == []
    )
    assert policy._check_sizes(inputs(text, source_limit=3))
    assert policy._check_sizes(inputs(text, runtime_limit=len(runtime.encode()) - 1))


@pytest.mark.parametrize('tracked', ['staged', 'committed'])
def test_public_check_persisted_marker_remains_policy_blocked(
    repository,
    identity,
    monkeypatch,
    tracked,
):
    (repository / 'AGENTS.md').write_text(injected(), encoding='utf-8')
    git(repository, 'add', 'AGENTS.md')
    if tracked == 'committed':
        git(repository, 'commit', '-qm', 'synthetic runtime marker')
    snapshot = replace(
        inputs('clean source'),
        documents=dict.fromkeys(policy.PROTOCOL_DOCS.values(), ''),
    )
    monkeypatch.setattr(policy, '_load_document_inputs', lambda: snapshot)
    result = policy.check([])
    assert result.status is CheckStatus.BLOCKED
    assert any(
        'runtime marker forbidden in Git source' in item.message for item in result.diagnostics
    )


@pytest.mark.parametrize(
    'failure', [OSError('synthetic-unavailable'), subprocess.TimeoutExpired('synthetic-git', 10)]
)
def test_public_check_git_execution_failure_is_input_unavailable(
    repository,
    monkeypatch,
    failure,
):
    def unavailable(*args, **kwargs):
        raise failure

    monkeypatch.setattr(policy, '_load_document_inputs', lambda: inputs('clean source'))
    monkeypatch.setattr(policy.subprocess, 'run', unavailable)
    result = policy.check([])
    assert result.status is CheckStatus.FAIL
    assert result.reason == 'input-unavailable'
