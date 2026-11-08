"""离线执行 workflow 的真实发布与 Gate 凭据代码，防止安全边界退化。"""

from __future__ import annotations

import copy
import json
import os
import subprocess
import textwrap
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
SHA = 'a' * 40


def _inline(workflow, marker):
    source = (ROOT / '.github/workflows' / workflow).read_text().split(marker, 1)[1]
    return textwrap.dedent(
        source.split("<<'PYTHON_CODE'\n", 1)[1].split('\n          PYTHON_CODE', 1)[0]
    )


class Response:
    def __init__(self, value):
        self.body = value if isinstance(value, bytes) else json.dumps(value).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return self.body


def _publisher(tmp_path, monkeypatch, case='happy', version='0.4'):
    monkeypatch.chdir(tmp_path)
    for name, value in {
        'GH_TOKEN': 'synthetic-not-a-real-token',
        'GITHUB_API_URL': 'https://api.example.test',
        'GITHUB_REPOSITORY': 'owner/repo',
        'VERSION': version,
        'GITHUB_SHA': SHA,
    }.items():
        monkeypatch.setenv(name, value)
    candidate = tmp_path / 'verified-candidate'
    candidate.mkdir()
    archive = f'app-cli-{version}-runtime-macos-arm64.tar.gz'
    assets = {
        archive: b'archive',
        archive + '.provenance.json': b'provenance',
        archive + '.smoke.json': b'smoke',
        'MANIFEST.SHA256': b'manifest',
    }
    for name, data in assets.items():
        (candidate / name).write_bytes(data)
    if case == 'bad-local-name':
        (candidate / 'MANIFEST.SHA256').rename(candidate / 'surprise.txt')
    calls, handlers = [], []

    def transport(req, **_):
        url, method = req.full_url, req.get_method()
        payload = json.loads(req.data) if req.data and '/uploads?' not in url else None
        calls.append((method, url, payload))
        if '/releases/tags/' in url:
            raise urllib.error.HTTPError(url, 404, 'synthetic published lookup', {}, None)
        if method == 'GET' and '/releases?' in url:
            page = int(urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)['page'][0])
            if page == 1:
                return Response([{'tag_name': f'vother-{i}'} for i in range(100)])
            if page == 2 and case in ('draft', 'public'):
                return Response([{'tag_name': 'v' + version, 'draft': case == 'draft'}])
            return Response([])
        if method == 'POST' and url.endswith('/releases'):
            return Response(
                {
                    'id': 1,
                    'html_url': 'https://example.test/draft/1',
                    'upload_url': 'https://uploads.example.test/uploads{?name,label}',
                }
            )
        if method == 'POST' and '/uploads?' in url:
            return Response({'id': len(calls)})
        if method == 'GET' and '/assets?' in url:
            values = [
                {'name': name, 'size': len(data), 'url': 'https://api.example.test/blob/' + name}
                for name, data in assets.items()
            ]
            if case == 'missing':
                values.pop()
            return Response(values)
        if method == 'GET' and '/blob/' in url:
            data = assets[url.rsplit('/', 1)[1]]
            return Response(data[::-1] if case == 'hash' else data)
        if method == 'GET' and url.endswith('/releases/1'):
            return Response({'tag_name': 'v' + version, 'draft': True})
        if method == 'PATCH':
            assert payload == {'draft': False}
            assert sum('/blob/' in item[1] for item in calls) == 4
            assert sum('/uploads?' in item[1] for item in calls) == 4
            return Response({'draft': False, 'html_url': 'https://example.test/public/1'})
        raise AssertionError('Unexpected offline request: ' + method + ' ' + url)

    def opener(*values):
        handlers.extend(values)
        return SimpleNamespace(open=transport)

    monkeypatch.setattr(urllib.request, 'urlopen', transport)
    monkeypatch.setattr(urllib.request, 'build_opener', opener)
    namespace = {}
    error = None
    try:
        exec(
            compile(_inline('release.yml', '- name: Create draft,'), '<publisher>', 'exec'),
            namespace,
        )
    except (RuntimeError, OSError) as caught:
        error = caught
    return calls, handlers, error


def test_unexpected_local_candidate_name_never_creates_draft(tmp_path, monkeypatch):
    calls, _, error = _publisher(tmp_path, monkeypatch, case='bad-local-name')
    assert isinstance(error, RuntimeError)
    assert not any(method == 'POST' for method, _, _ in calls)


@pytest.mark.parametrize('case', ['draft', 'public'])
def test_all_release_pages_reject_same_tag_before_post(tmp_path, monkeypatch, case):
    calls, _, error = _publisher(tmp_path, monkeypatch, case)
    assert error is not None
    assert all(method == 'GET' for method, _, _ in calls)
    assert any('page=2' in url for _, url, _ in calls)


@pytest.mark.parametrize(
    'version,prerelease',
    [('0.4', False), ('0.4.1', False), ('0.4-rc.1', True), ('0.4.1.rc.1', True)],
)
def test_release_visibility_and_last_public_operation(tmp_path, monkeypatch, version, prerelease):
    calls, _, error = _publisher(tmp_path, monkeypatch, version=version)
    assert error is None
    payload = next(
        data for method, url, data in calls if method == 'POST' and url.endswith('/releases')
    )
    assert payload['draft'] is True
    assert payload['prerelease'] is prerelease
    assert payload['make_latest'] == ('false' if prerelease else 'true')
    assert calls[-1][0] == 'PATCH'
    assert sum(method == 'PATCH' for method, _, _ in calls) == 1


@pytest.mark.parametrize('case', ['missing', 'hash'])
def test_bad_remote_assets_never_become_public(tmp_path, monkeypatch, case):
    calls, _, error = _publisher(tmp_path, monkeypatch, case)
    assert error is not None
    assert not any(method == 'PATCH' for method, _, _ in calls)


def test_redirect_strips_cross_origin_credentials_only(tmp_path, monkeypatch):
    _, handlers, error = _publisher(tmp_path, monkeypatch)
    assert error is None
    redirect = next(
        (item for item in handlers if isinstance(item, urllib.request.HTTPRedirectHandler)), None
    )
    assert redirect is not None
    req = urllib.request.Request(
        'https://api.example.test/asset', headers={'Authorization': 'Bearer synthetic'}
    )
    for target, authenticated in [
        ('https://api.example.test/next', True),
        ('https://cdn.example.test/asset', False),
        ('https://api.example.test:444/asset', False),
        ('http://api.example.test/asset', False),
    ]:
        redirected = redirect.redirect_request(req, None, 302, 'Found', {}, target)
        assert bool(redirected.get_header('Authorization')) is authenticated


@pytest.mark.parametrize(
    'case', ['valid', 'empty', 'partial', 'sha', 'failed', 'skipped', 'step', 'invocations']
)
def test_full_gate_receipt_rejects_incomplete_evidence(tmp_path, monkeypatch, case):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('GITHUB_SHA', SHA)
    monkeypatch.setenv('GATE_MODE', 'full')
    plan = {
        'planFingerprint': 'test',
        'mode': 'full',
        'selector': None,
        'gates': [
            {'gate': 'g', 'recipeSteps': [{'name': 'step'}]},
            {'gate': 'h', 'recipeSteps': [{'name': 'step'}]},
        ],
    }
    gate = {
        'gate': 'g',
        'status': 'PASS',
        'recipeSteps': [
            {
                'recipeStep': 'step',
                'status': 'PASS',
                'invocationResults': [
                    {'status': 'PASS', 'returnCode': 0, 'taskFailureReasons': {}}
                ],
            }
        ],
    }
    other = copy.deepcopy(gate)
    other['gate'] = 'h'
    summary = {
        'kind': 'gate-run-receipt',
        'runId': 'r',
        'status': 'PASS',
        'snapshot': {'head': SHA},
        'planFingerprint': 'test',
        'mode': 'full',
        'gateResults': [gate, other],
    }
    if case == 'empty':
        plan['gates'] = []
        summary['gateResults'] = []
    if case == 'partial':
        summary['gateResults'].pop()
    if case == 'sha':
        summary['snapshot']['head'] = 'b' * 40
    if case in ('failed', 'skipped'):
        gate['status'] = 'FAIL' if case == 'failed' else 'SKIPPED'
    if case == 'step':
        gate['recipeSteps'] = []
    if case == 'invocations':
        gate['recipeSteps'][0]['invocationResults'] = []
    root = tmp_path / 'tmp/quality/runs/r'
    root.mkdir(parents=True)
    (root / 'plan.json').write_text(json.dumps(plan))
    (root / 'summary.json').write_text(json.dumps(summary))
    (root.parent / 'latest.json').write_text(
        json.dumps({'runId': 'r', 'summary': 'r/summary.json'})
    )
    code = compile(_inline('quality.yml', '- name: Require a complete'), '<receipt>', 'exec')
    if case == 'valid':
        exec(code, {})
    else:
        with pytest.raises(AssertionError):
            exec(code, {})


def test_release_requires_remote_main_before_and_after_approval(tmp_path):
    release = yaml.safe_load((ROOT / '.github/workflows/release.yml').read_text())['jobs']
    validate = next(s['run'] for s in release['validate']['steps'] if s.get('id') == 'resolve')
    approved = next(
        s['run'] for s in release['publish-release']['steps'] if 'git ls-remote' in s.get('run', '')
    )
    checkout = tmp_path / 'checkout'
    checkout.mkdir()

    def git(*args):
        return subprocess.check_output(
            [
                'git',
                '-c',
                'user.name=Test',
                '-c',
                'user.email=test@example.test',
                '-c',
                'commit.gpgsign=false',
                '-c',
                'tag.gpgsign=false',
                *args,
            ],
            cwd=checkout,
            text=True,
        ).strip()

    git('init', '-qb', 'main')
    origin = tmp_path / 'origin.git'
    git('init', '-q', '--bare', str(origin))
    git('remote', 'add', 'origin', str(origin))
    git('commit', '-qm', 'main base', '--allow-empty')
    git('push', '-q', 'origin', 'main')
    git('switch', '-qc', 'release')
    git('commit', '-qm', 'release', '--allow-empty')
    sha = git('rev-parse', 'HEAD')
    git('tag', '-am', 'release', 'v1.2')
    git('push', '-q', 'origin', 'refs/tags/v1.2')
    git('update-ref', 'refs/remotes/origin/main', sha)
    version_file = checkout / 'java/gradle/VERSION'
    version_file.parent.mkdir(parents=True)
    version_file.write_text('1.2\n')
    output = tmp_path / 'output'
    env = os.environ | {
        'GITHUB_EVENT_NAME': 'push',
        'GITHUB_REF_TYPE': 'tag',
        'GITHUB_REF_NAME': 'v1.2',
        'GITHUB_SHA': sha,
        'GITHUB_OUTPUT': str(output),
        'INPUT_PUBLISH': '',
        'VERSION': '1.2',
    }

    def run(script, settings):
        return subprocess.run(
            ['/bin/bash', '-c', script],
            cwd=checkout,
            env=settings,
            capture_output=True,
            text=True,
            check=False,
        )

    rc = env | {'GITHUB_EVENT_NAME': 'workflow_dispatch', 'GITHUB_REF_TYPE': 'branch'}
    assert run(validate, rc).returncode == 0
    assert 'publish=false\n' in output.read_text()
    # 仅替换 gh 鉴权，远端 tag 与 main 校验使用真实 Git。
    scripts = (validate, 'gh() { [[ "$*" == "auth setup-git" ]]; }\n' + approved)
    for script in scripts:
        result = run(script, env)
        assert result.returncode == 1 and '远端 main' in result.stderr
    git('commit', '-qm', 'main advanced after release', '--allow-empty')
    git('push', '-q', 'origin', 'HEAD:refs/heads/main')
    for script in scripts:
        result = run(script, env)
        assert result.returncode == 0, result.stderr
    assert 'publish=true\n' in output.read_text()


def test_shared_workflow_permissions_and_fresh_checkout_prerequisites():
    workflows = {
        name: yaml.safe_load((ROOT / '.github/workflows' / (name + '.yml')).read_text())
        for name in ('quality', 'release')
    }
    for workflow in workflows.values():
        assert workflow['permissions'] == {'contents': 'read'}
    release = workflows['release']['jobs']
    assert [
        name
        for name, job in release.items()
        if job.get('permissions', {}).get('contents') == 'write'
    ] == ['publish-release']
    assert release['publish-release']['environment']['name'] == 'github-release'
    assert release['release-candidate']['environment']['name'] == 'release-candidate'
    assert release['distribution']['uses'] == './.github/workflows/quality.yml'
    assert release['distribution']['needs'] == 'validate'
    triggers = workflows['quality'][True]
    assert 'tags' not in triggers['push']
    steps = workflows['quality']['jobs']['quality']['steps']
    setup = next(
        index
        for index, step in enumerate(steps)
        if 'mkdir -p openspec/changes' in step.get('run', '')
    )
    browsers = next(
        index
        for index, step in enumerate(steps)
        if 'npx playwright install chromium' in step.get('run', '')
    )
    gate = next(
        index for index, step in enumerate(steps) if step['name'] == 'Unified quality gates'
    )
    assert steps[browsers]['working-directory'] == 'java/tests/playwright'
    assert setup < gate and browsers < gate


def test_quality_prepares_clean_runner_without_weakening_gate_isolation():
    workflow = yaml.safe_load((ROOT / '.github/workflows/quality.yml').read_text())
    job = workflow['jobs']['quality']
    assert job['runs-on'] == 'macos-15'
    assert job['env']['PLAYWRIGHT_BROWSERS_PATH'] == (
        '${{ github.workspace }}/.local/playwright-browsers'
    )
    steps = job['steps']
    gate = next(i for i, step in enumerate(steps) if step['name'] == 'Unified quality gates')
    java = next(i for i, step in enumerate(steps) if step['name'] == 'Set up JDK 25')
    assert steps[java]['with']['architecture'] == 'arm64'
    host = next(
        i for i, step in enumerate(steps) if step['name'] == 'Check native macOS arm64 host'
    )
    assert 'Darwin arm64' in steps[host]['run']
    browsers = next(
        i for i, step in enumerate(steps) if step.get('run') == 'npx playwright install chromium'
    )
    assert host < java < gate
    assert all(':java:app-cli:installDist' not in step.get('run', '') for step in steps)
    assert browsers < gate
    for step in steps:
        assert 'PLAYWRIGHT_BROWSERS_PATH' not in step.get('env', {})
        assert 'XDG_CACHE_HOME' not in step.get('env', {})
    for index in (host, browsers, gate):
        assert 'if' not in steps[index]
        assert not steps[index].get('continue-on-error', False)
    assert 'XDG_CACHE_HOME' not in job['env']
    assert 'python3 scripts/gates/cli.py run --mode full' in steps[gate]['run']


def test_only_native_arm64_build_can_seal_candidate_after_full_gate():
    workflow = yaml.safe_load((ROOT / '.github/workflows/quality.yml').read_text())
    assert set(workflow['jobs']) == {'quality'}
    job = workflow['jobs']['quality']
    assert job['runs-on'] == 'macos-15' and 'strategy' not in job
    steps = job['steps']
    named = {step['name']: step for step in steps}
    assert named['Set up JDK 25']['with']['architecture'] == 'arm64'
    assert 'Darwin arm64' in named['Check native macOS arm64 host']['run']
    guard = named['Require a complete successful receipt from this checkout']
    archive = named['Build the macOS arm64 runtime']
    assert archive['run'] == './java/gradlew -p java :java:app-cli:runtimeDistTar --no-daemon'
    prepare = named['Prepare and launch actual native archive without external JDK']
    assert (
        'prepare --dist-dir java/app-cli/build/distributions --output-dir verified-candidate'
        in prepare['run']
    )
    upload = named['Upload the sole verified candidate']
    assert steps.index(guard) < steps.index(archive) < steps.index(prepare) < steps.index(upload)
    assert upload['with']['path'] == 'verified-candidate/'
    assert upload['with']['if-no-files-found'] == 'error'
    assert all(
        step['if'] == "steps.scope.outputs.mode == 'full'" for step in (archive, prepare, upload)
    )
    assert 'if' not in guard
    assert all('continue-on-error' not in item for item in (job, *steps))


def test_java_full_uses_current_entry_with_required_comment_language_rule():
    workflow = yaml.safe_load((ROOT / '.github/workflows/java-quality.yml').read_text())
    assert set(workflow[True]) == {'workflow_dispatch'}
    assert set(workflow['jobs']) == {'java-full'}
    job = workflow['jobs']['java-full']
    assert job['runs-on'] == 'macos-15' and 'strategy' not in job and 'needs' not in job
    steps = {step['name']: step for step in job['steps']}
    assert steps['Set up native arm64 JDK 25']['with']['architecture'] == 'arm64'
    assert 'Darwin arm64' in steps['Check native macOS arm64 host']['run']
    assert all(
        ':distZip' not in step.get('run', '')
        and ':java:app-cli:installDist' not in step.get('run', '')
        for step in steps.values()
    )
    uploads = [step for step in steps.values() if 'upload-artifact' in step.get('uses', '')]
    assert uploads == [steps['Upload quality reports']]
    assert uploads[0]['if'] == 'always()'
    assert '**/build/test-results/**/*.xml' in uploads[0]['with']['path']
    assert '**/build/reports/' in uploads[0]['with']['path']
    quality = next(step for step in job['steps'] if step['name'] == 'qualityFull')
    assert quality['run'] == './java/gradlew -p java qualityFull'
    assert 'if' not in quality
    assert 'continue-on-error' not in job
    assert all('continue-on-error' not in step for step in job['steps'])
    assert all('verifyChineseJavaComments' not in step.get('run', '') for step in job['steps'])
    root_build = (ROOT / 'java/build.gradle.kts').read_text()
    quality_full = root_build.split('tasks.register("qualityFull") {', 1)[1].split('\n}', 1)[0]
    assert 'dependsOn("check")' in quality_full
    assert '${it.path}:check' in root_build
    cli_build = (ROOT / 'java/app-cli/build.gradle.kts').read_text()
    assert 'tasks.named("check") {\n    dependsOn(cliSmokeTest)\n}' in cli_build
    assert (
        'tasks.named("check") {\n    dependsOn(":java:tests:quality-gates:runJavaQualityGates")\n}'
    ) in root_build
    source_rules = (ROOT / 'java/tests/quality-gates/build.gradle.kts').read_text()
    assert 'tasks.register<JavaExec>("runJavaQualityGates")' in source_rules
    assert '.orElse("java-comment-language,record-component-javadocs,no-pmd-suppressions")' in (
        source_rules
    )
    assert '"--rules", javaQualityRules.get()' in source_rules


def test_rc_attests_to_sealed_artifact_without_downloading_another_copy():
    release = yaml.safe_load((ROOT / '.github/workflows/release.yml').read_text())['jobs']
    distribution = yaml.safe_load((ROOT / '.github/workflows/quality.yml').read_text())
    entry = distribution.get('on', distribution.get(True))['workflow_call']
    build = distribution['jobs']['quality']
    assert entry['outputs']['candidate-id']['value'] == '${{ jobs.quality.outputs.candidate-id }}'
    assert build['outputs']['candidate-id'] == '${{ steps.seal.outputs.artifact-id }}'
    upload = build['steps'][-1]
    assert upload['id'] == 'seal'
    assert (
        upload['with']['name']
        == 'verified-candidate-${{ github.run_id }}-${{ github.run_attempt }}'
    )
    assert upload['with']['compression-level'] == 0

    rc = release['release-candidate']
    assert 'distribution' in rc['needs']
    assert all('download-artifact' not in step.get('uses', '') for step in rc['steps'])
    assert rc['steps'][0]['env']['CANDIDATE_ID'] == '${{ needs.distribution.outputs.candidate-id }}'
    publisher = release['publish-release']
    assert 'release-candidate' in publisher['needs']
    steps = publisher['steps']
    download = next(step for step in steps if 'download-artifact' in step.get('uses', ''))
    assert download['with'] == {
        'artifact-ids': '${{ needs.distribution.outputs.candidate-id }}',
        'merge-multiple': True,
        'path': 'verified-candidate/',
    }
    remote_tag = next(step for step in steps if 'git ls-remote' in step.get('run', ''))
    verify_candidate = next(step for step in steps if 'verify-candidate' in step.get('run', ''))
    verify_args = verify_candidate['run'].split()
    candidate_dir = verify_args[verify_args.index('--candidate-dir') + 1]
    assert candidate_dir == download['with']['path'].rstrip('/')
    preflight = next(step for step in steps if step['name'].startswith('Reject a missing'))
    assert steps.index(preflight) < steps.index(download) < steps.index(verify_candidate)
    assert steps.index(verify_candidate) < steps.index(remote_tag)
    assert entry['outputs']['candidate-key']['value'] == '${{ jobs.quality.outputs.candidate-key }}'
    assert build['outputs']['candidate-key'] == (
        "${{ steps.seal.outputs.artifact-id && format('{0}:{1}:{2}', github.sha, github.run_id, github.run_attempt) }}"
    )
    for check in (rc['steps'][0], preflight):
        assert check['env']['CANDIDATE_KEY'] == '${{ needs.distribution.outputs.candidate-key }}'
        env = {'GITHUB_SHA': SHA, 'GITHUB_RUN_ID': '42', 'GITHUB_RUN_ATTEMPT': '2'}
        for candidate_id, key, expected in [
            ('17', f'{SHA}:42:2', 0),
            ('17', f'{SHA}:42:1', 1),
            ('', f'{SHA}:42:2', 1),
            ('17,18', f'{SHA}:42:2', 1),
        ]:
            result = subprocess.run(
                ['/bin/bash', '-c', check['run']],
                env={**env, 'CANDIDATE_ID': candidate_id, 'CANDIDATE_KEY': key},
                capture_output=True,
                check=False,
            )
            assert result.returncode == expected
