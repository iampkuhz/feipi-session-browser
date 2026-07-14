from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import textwrap
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from scripts.agent_runtime.change.fixture import (
    DEFAULT_IDENTITY_ENDPOINT,
    FixtureIdentityError,
    FixtureSupervisor,
    FixtureUnavailableError,
)
from scripts.agent_runtime.change.runtime import spawn_managed, write_atomic_json

EXPECTED_IDENTITY = {'schemaVersion': 1, 'service': 'feipi-test-fixture'}


def _free_port() -> int:
    with socket.socket() as selected:
        selected.bind(('127.0.0.1', 0))
        return int(selected.getsockname()[1])


def _server_command(port: int, identity: dict[str, object], *, delay: float = 0) -> list[str]:
    code = textwrap.dedent(
        f'''
        import http.server, json, time
        time.sleep({delay!r})
        payload = {json.dumps(identity)!r}.encode()
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path != {DEFAULT_IDENTITY_ENDPOINT!r}:
                    self.send_response(404); self.end_headers(); return
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers(); self.wfile.write(payload)
            def log_message(self, *_args):
                pass
        http.server.ThreadingHTTPServer(('127.0.0.1', {port}), Handler).serve_forever()
        '''
    )
    return [sys.executable, '-c', code]


def _running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    status = subprocess.run(
        ['ps', '-o', 'stat=', '-p', str(pid)],
        text=True,
        capture_output=True,
        check=False,
        timeout=1,
    ).stdout.strip()
    return bool(status and not status.startswith('Z'))


@contextmanager
def _external_server(identity: dict[str, object]):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != DEFAULT_IDENTITY_ENDPOINT:
                self.send_response(404)
                self.end_headers()
                return
            payload = json.dumps(identity).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_address[1]}'
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_managed_fixture_ready_resume_and_cleanup_persist_process_identity(tmp_path):
    port = _free_port()
    assert (
        FixtureSupervisor(
            tmp_path / 'deadline-contract',
            expected_identity=EXPECTED_IDENTITY,
            readiness_timeout=99,
        ).readiness_timeout
        == 15
    )
    supervisor = FixtureSupervisor(
        tmp_path / 'runtime',
        expected_identity=EXPECTED_IDENTITY,
        readiness_timeout=2,
        request_timeout=0.2,
    )
    handle = supervisor.start_managed(
        _server_command(port, EXPECTED_IDENTITY),
        cwd=tmp_path,
        base_url=f'http://127.0.0.1:{port}',
    )

    state = json.loads(supervisor.state_path.read_text())
    assert handle.managed and not handle.resumed
    assert state['status'] == 'READY'
    assert state['pid'] == handle.pid == state['processGroupId']
    assert state['processStartTime']
    assert Path(state['logPath']).is_file()
    resumed = supervisor.resume()
    assert resumed is not None and resumed.resumed

    assert supervisor.cleanup()
    assert json.loads(supervisor.state_path.read_text())['status'] == 'STOPPED'
    assert not _running(handle.pid)


def test_managed_fixture_early_exit_returns_bounded_log_tail(tmp_path):
    supervisor = FixtureSupervisor(
        tmp_path / 'runtime', expected_identity=EXPECTED_IDENTITY, readiness_timeout=1
    )
    command = [
        sys.executable,
        '-c',
        'import sys; print("fixture-early-exit", flush=True); sys.exit(7)',
    ]

    with pytest.raises(FixtureUnavailableError) as captured:
        supervisor.start_managed(
            command,
            cwd=tmp_path,
            base_url=f'http://127.0.0.1:{_free_port()}',
        )

    state = json.loads(supervisor.state_path.read_text())
    assert captured.value.reason_code == 'FIXTURE_EARLY_EXIT'
    assert 'fixture-early-exit' in captured.value.tail
    assert len(captured.value.tail.encode()) <= 4096
    assert state['status'] == 'FAILED'
    assert state['reason'] == 'FIXTURE_EARLY_EXIT'


def test_managed_fixture_readiness_timeout_cleans_process_group(tmp_path):
    supervisor = FixtureSupervisor(
        tmp_path / 'runtime',
        expected_identity=EXPECTED_IDENTITY,
        readiness_timeout=0.3,
        request_timeout=0.05,
    )

    with pytest.raises(FixtureUnavailableError) as captured:
        supervisor.start_managed(
            [sys.executable, '-c', 'import time; print("waiting", flush=True); time.sleep(30)'],
            cwd=tmp_path,
            base_url=f'http://127.0.0.1:{_free_port()}',
        )

    state = json.loads(supervisor.state_path.read_text())
    assert captured.value.reason_code == 'FIXTURE_READINESS_TIMEOUT'
    assert state['status'] == 'FAILED'
    assert not _running(int(state['pid']))


def test_managed_fixture_identity_mismatch_is_terminal_and_cleans_group(tmp_path):
    port = _free_port()
    supervisor = FixtureSupervisor(
        tmp_path / 'runtime',
        expected_identity=EXPECTED_IDENTITY,
        readiness_timeout=2,
        request_timeout=0.2,
    )

    with pytest.raises(FixtureIdentityError) as captured:
        supervisor.start_managed(
            _server_command(port, {'schemaVersion': 1, 'service': 'wrong'}),
            cwd=tmp_path,
            base_url=f'http://127.0.0.1:{port}',
        )

    state = json.loads(supervisor.state_path.read_text())
    assert captured.value.reason_code == 'FIXTURE_IDENTITY_MISMATCH'
    assert state['status'] == 'FAILED'
    assert state['observedIdentity']['service'] == 'wrong'
    assert not _running(int(state['pid']))


def test_external_fixture_requires_explicit_matching_identity(tmp_path, monkeypatch):
    monkeypatch.setenv('BASE_URL', 'http://127.0.0.1:1/implicit-must-not-be-read')
    with _external_server(EXPECTED_IDENTITY) as base_url:
        matching = FixtureSupervisor(
            tmp_path / 'matching', expected_identity=EXPECTED_IDENTITY, request_timeout=0.2
        )
        handle = matching.use_external(base_url=base_url)
        assert not handle.managed
        assert handle.base_url == base_url

        mismatch = FixtureSupervisor(
            tmp_path / 'mismatch',
            expected_identity={'schemaVersion': 1, 'service': 'another-fixture'},
            request_timeout=0.2,
        )
        with pytest.raises(FixtureIdentityError) as captured:
            mismatch.use_external(base_url=base_url)
        assert captured.value.reason_code == 'EXTERNAL_FIXTURE_IDENTITY_MISMATCH'
        mismatch_state = json.loads(mismatch.state_path.read_text())
        assert mismatch_state['status'] == 'FAILED'
        assert mismatch_state['observedIdentity'] == EXPECTED_IDENTITY


def test_resume_reclaims_orphan_group_after_leader_exit(tmp_path):
    child_pid_path = tmp_path / 'orphan.pid'
    command = [
        sys.executable,
        '-c',
        (
            'import pathlib, subprocess, sys; '
            'child=subprocess.Popen([sys.executable,"-c","import time; time.sleep(30)"]); '
            f'pathlib.Path({str(child_pid_path)!r}).write_text(str(child.pid))'
        ),
    ]
    managed = spawn_managed(command, cwd=tmp_path, env={}, log_path=tmp_path / 'orphan.log')
    assert managed.process.wait(timeout=3) == 0
    child_pid = int(child_pid_path.read_text())
    assert _running(child_pid)

    supervisor = FixtureSupervisor(tmp_path / 'runtime', expected_identity=EXPECTED_IDENTITY)
    write_atomic_json(
        supervisor.state_path,
        {
            'schemaVersion': 1,
            'mode': 'MANAGED',
            'status': 'STARTING',
            'pid': managed.pid,
            'processStartTime': managed.process_start_time,
            'processGroupId': managed.process_group_id,
            'baseUrl': f'http://127.0.0.1:{_free_port()}',
            'identityEndpoint': DEFAULT_IDENTITY_ENDPOINT,
            'expectedIdentity': EXPECTED_IDENTITY,
            'logPath': managed.log_path,
        },
    )

    assert supervisor.resume() is None
    state = json.loads(supervisor.state_path.read_text())
    assert state['status'] == 'STOPPED'
    assert state['reason'] == 'FIXTURE_ORPHAN_RECLAIMED'
    deadline = time.monotonic() + 2
    while _running(child_pid) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert not _running(child_pid)


def test_resume_rejects_pid_reuse_without_signalling_unknown_process(tmp_path):
    supervisor = FixtureSupervisor(tmp_path / 'runtime', expected_identity=EXPECTED_IDENTITY)
    write_atomic_json(
        supervisor.state_path,
        {
            'schemaVersion': 1,
            'mode': 'MANAGED',
            'status': 'STARTING',
            'pid': os.getpid(),
            'processStartTime': 'not-the-current-process-start',
            'processGroupId': os.getpid(),
            'baseUrl': f'http://127.0.0.1:{_free_port()}',
            'identityEndpoint': DEFAULT_IDENTITY_ENDPOINT,
            'expectedIdentity': EXPECTED_IDENTITY,
            'logPath': str(tmp_path / 'unknown.log'),
        },
    )

    with pytest.raises(FixtureIdentityError) as captured:
        supervisor.resume()

    assert captured.value.reason_code == 'FIXTURE_PROCESS_IDENTITY_UNPROVEN'
    assert json.loads(supervisor.state_path.read_text())['status'] == 'STARTING'
