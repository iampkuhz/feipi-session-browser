"""Consume one real, isolated serve candidate; never trust HTTP 200 alone."""

from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import socket
import subprocess
import time
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, build_opener

import pytest
from test_session_browser_scan_smoke import (
    REPO_ROOT,
    SCRIPT_PATH,
    _create_claude_fixture,
    _create_codex_fixture,
    _create_qoder_fixture,
)

INSTALL = REPO_ROOT / 'java/app-cli/build/install/app-cli'
OPENER = build_opener(ProxyHandler({}))
SESSION = 'smoke-test-session-001'


def _fingerprint() -> dict[str, str]:
    files = {
        str(p.relative_to(INSTALL)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(INSTALL.rglob('*'))
        if p.is_file()
    }
    assert files and 'bin/app-cli' in files, 'Installed candidate is missing'
    return files


def _environment(root: Path) -> tuple[dict[str, str], Path]:
    home = root / 'test home'
    home.mkdir(parents=True)
    _create_claude_fixture(home / '.claude')
    _create_codex_fixture(home / '.codex')
    _create_qoder_fixture(home / '.qoder')
    index = root / 'index'
    env = os.environ.copy()
    # 隔离产品源和索引，不为每次验收重建 Gradle 的下载/依赖缓存。
    env.setdefault('GRADLE_USER_HOME', str(Path.home() / '.gradle'))
    env.update(
        HOME=str(home),
        INDEX_DIR=str(index),
        JAVA_OPTS=f'"-Duser.home={home}"',
        SESSION_BROWSER_SCAN_LOCK_TIMEOUT_SECONDS='0',
    )
    for key in ('APP_CLI_OPTS', 'JAVA_TOOL_OPTIONS', 'JDK_JAVA_OPTIONS', '_JAVA_OPTIONS'):
        env[key] = ''
    return env, index


def _get(url: str) -> str:
    with OPENER.open(url, timeout=5) as response:
        assert response.status == 200
        return response.read().decode('utf-8')


def _wait_ready(process: subprocess.Popen, log: Path, timeout: int) -> str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        output = log.read_text(encoding='utf-8', errors='replace')
        match = re.search(r'serve 已就绪: (http://127\.0\.0\.1:[0-9]+)', output)
        if match:
            return match.group(1)
        assert process.poll() is None, f'serve exited before ready:\n{output[-8000:]}'
        time.sleep(0.1)
    raise AssertionError(f'serve readiness timed out:\n{output[-8000:]}')


def _identity(
    url: str,
    expected_url: str,
    process: subprocess.Popen,
    index: Path,
    metadata: str,
    frozen: dict[str, str],
    expected_pid: int | None = None,
) -> None:
    assert url == expected_url, 'Candidate URL mismatch'
    assert process.poll() is None, 'Owned candidate exited'
    assert _fingerprint() == frozen, 'Installed candidate changed'
    assert (index / 'server.pid').read_text() == metadata, 'PID metadata changed'
    values = dict(line.split('=', 1) for line in metadata.splitlines())
    parsed = urlsplit(url)
    assert int(values['pid']) == (process.pid if expected_pid is None else expected_pid), (
        'PID mismatch'
    )
    os.kill(process.pid, 0)
    assert values['host'] == parsed.hostname == '127.0.0.1'
    assert int(values['port']) == parsed.port and parsed.port > 0
    assert Path(values['index_dir']) == index.resolve()
    assert values['app_name'] == 'feipi-session-browser'
    assert values['started_at']


def _wait_scan(url: str, process: subprocess.Popen) -> None:
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        assert process.poll() is None, 'Candidate exited during automatic scan'
        status = json.loads(_get(url + '/api/scan-status'))
        assert status['status'] != 'failure', status
        if status['status'] == 'success':
            assert status['errorCount'] == 0 and status['publishedDataAvailable'], status
            return
        time.sleep(0.2)
    raise AssertionError(f'Automatic scan did not complete: {status}')


def _assert_content(url: str) -> None:
    rows = json.loads(_get(url + '/api/sessions/rows'))['rows']
    assert any(row['sessionId'] == SESSION and row['agent'] == 'claude_code' for row in rows), rows
    detail = '/sessions/claude_code/' + SESSION
    assert '<html' in _get(url + '/sessions').lower()
    assert SESSION in _get(url + detail)
    api = url + '/api' + detail
    assert SESSION in _get(api + '/meta')
    payloads = json.loads(_get(api + '/payloads?visibility=full'))

    # Follow the product's own lazy-content URLs rather than guessing payload IDs.
    def links(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key == 'apiUrl':
                    yield child
                else:
                    yield from links(child)
        elif isinstance(value, list):
            for child in value:
                yield from links(child)

    paths = list(links(payloads))
    assert paths, payloads
    bodies = []
    for path in paths:
        assert path.startswith('/api/sessions/claude_code/' + SESSION + '/payload/')
        separator = '&' if '?' in path else '?'
        bodies.append(_get(url + path + separator + 'visibility=full'))
    text = '\n'.join(bodies)
    assert 'Hello, this is a smoke test session.' in text
    assert 'Hello! How can I help you today?' in text


def test_serve_consumes_only_owned_frozen_candidate(tmp_path: Path) -> None:
    """One public build/start, automatic scan, content, and live wrong-instance rejection."""
    owned = []
    started = time.monotonic()
    frozen = None
    build_count = 0
    try:
        for number in (1, 2):
            root = tmp_path / str(number)
            env, index = _environment(root)
            log = root / 'serve.log'
            command = ['bash', str(SCRIPT_PATH)] if number == 1 else [str(INSTALL / 'bin/app-cli')]
            command += ['serve', '--host', '127.0.0.1', '--port', '0']
            launch_time = time.monotonic()
            with log.open('w') as output:
                process = subprocess.Popen(
                    command,
                    cwd=REPO_ROOT,
                    env=env,
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            owned.append((process, index, None))
            url = _wait_ready(process, log, 180 if number == 1 else 60)
            owned[-1] = (process, index, url)
            metadata = (index / 'server.pid').read_text()
            if number == 1:
                frozen = _fingerprint()
                first = (url, process, index, metadata)
                output = log.read_text()
                build_count = len(
                    re.findall(r'^> Task :java:app-cli:installDist(?: |$)', output, re.MULTILINE)
                )
                assert build_count == 1, f'Expected one installDist task, got {build_count}'
                print(
                    f'build/start primary={time.monotonic() - launch_time:.3f}s build_invocations={build_count} starts=1'
                )
            _identity(url, url, process, index, metadata, frozen)
            digest = hashlib.sha256(json.dumps(frozen, sort_keys=True).encode()).hexdigest()
            print(f'candidate instance={number} url={url} pid={process.pid} package={digest}')
            scan_time = time.monotonic()
            _wait_scan(url, process)
            print(f'automatic scan instance={number} elapsed={time.monotonic() - scan_time:.3f}s')
            if number == 1:
                content_time = time.monotonic()
                _assert_content(url)
                _identity(url, url, process, index, metadata, frozen)
                print(f'list/detail content={time.monotonic() - content_time:.3f}s')
            else:
                assert '<html' in _get(url + '/sessions').lower()
                first_url, first_process, first_index, first_metadata = first
                with pytest.raises(AssertionError, match='Candidate URL mismatch'):
                    _identity(url, first_url, first_process, first_index, first_metadata, frozen)
                with pytest.raises(AssertionError, match='PID mismatch'):
                    _identity(
                        first_url,
                        first_url,
                        first_process,
                        first_index,
                        first_metadata,
                        frozen,
                        expected_pid=process.pid,
                    )
                changed = dict(frozen)
                changed['bin/app-cli'] = 'wrong-candidate'
                with pytest.raises(AssertionError, match='Installed candidate changed'):
                    _identity(
                        first_url, first_url, first_process, first_index, first_metadata, changed
                    )
                _identity(first_url, first_url, first_process, first_index, first_metadata, frozen)
                print('rejected live HTTP200 second URL; rejected same-URL wrong PID and candidate')
    finally:
        failures = []
        for process, index, url in reversed(owned):
            if process.poll() is None:
                # 包括启动构建尚未 exec Java 时的子进程；只终止自己创建的 session。
                os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                failures.append(f'Owned PID {process.pid} did not exit after TERM timeout')
            if (index / 'server.pid').exists():
                failures.append(f'Owned PID metadata not removed: {index}')
            if url:
                with socket.socket() as probe:
                    if probe.connect_ex(('127.0.0.1', urlsplit(url).port)) == 0:
                        failures.append(f'Owned port still listening: {url}')
        if frozen is not None and _fingerprint() != frozen:
            failures.append('Installed candidate changed before cleanup completed')
        print(
            f'cleanup owned_starts={len(owned)} build_invocations={build_count} elapsed={time.monotonic() - started:.3f}s failures={len(failures)}'
        )
        assert not failures, failures
