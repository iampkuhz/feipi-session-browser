"""离线执行 workflow 的真实发布与 Gate 凭据代码，防止安全边界退化。"""

from __future__ import annotations

import copy
import json
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
    assets = {f'asset-{i:02}': f'body-{i}'.encode() for i in range(15)}
    for name, data in assets.items():
        (candidate / name).write_bytes(data)
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
            assert sum('/blob/' in item[1] for item in calls) == 15
            assert sum('/uploads?' in item[1] for item in calls) == 15
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
    monkeypatch.setenv('REQUIRE_FULL', 'true')
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


def test_shared_workflow_permissions_and_fresh_checkout_prerequisites():
    workflows = {
        name: yaml.safe_load((ROOT / '.github/workflows' / (name + '.yml')).read_text())
        for name in ('quality', 'distribution', 'release', 'ci-distribution')
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
    assert (
        workflows['ci-distribution']['jobs']['distribution']['uses']
        == './.github/workflows/distribution.yml'
    )
    triggers = workflows['ci-distribution'].get('on', workflows['ci-distribution'].get(True))
    assert 'tags' not in triggers['push']
    steps = workflows['quality']['jobs']['python-quality']['steps']
    setup = next(
        index
        for index, step in enumerate(steps)
        if 'mkdir -p openspec/changes' in step.get('run', '')
    )
    browsers = next(
        index
        for index, step in enumerate(steps)
        if 'npx playwright install --with-deps chromium' in step.get('run', '')
    )
    gate = next(
        index for index, step in enumerate(steps) if step['name'] == 'Unified quality gates'
    )
    assert steps[browsers]['working-directory'] == 'java/tests/playwright'
    assert setup < gate and browsers < gate
