"""串行 Gate runner 的原生资源隔离 contract。"""

from __future__ import annotations

import json
import os
import select
import shutil
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

from scripts.gates import executor


def test_two_real_playwright_runtimes_are_checkout_scoped_and_cleaned(
    tmp_path: Path,
) -> None:
    """两个 checkout 并发运行真实 Node server 时，端口、输出和生命周期互不干扰。"""
    runtime = tmp_path / 'runtime'
    first_checkout = tmp_path / 'checkout-a'
    second_checkout = tmp_path / 'checkout-b'
    source_root = Path('tests/playwright')
    starters: list[Path] = []
    for checkout in (first_checkout, second_checkout):
        target = checkout / 'tests/playwright'
        target.mkdir(parents=True)
        for filename in ('runtime-paths.js', 'start-java-fixture-server.js'):
            shutil.copy2(source_root / filename, target / filename)
        starters.append(target / 'start-java-fixture-server.js')

    node = shutil.which('node')
    assert node is not None, 'Node.js is required by the Playwright resource contract'
    environment = {
        **os.environ,
        'FEIPI_AGENT_RUNTIME_ROOT': str(runtime),
        'FEIPI_RUN_ID': 'same-run',
    }
    reservation_processes = [
        subprocess.Popen(  # noqa: S603
            [node, str(starter), '--reserve-port'],
            cwd=starter.parents[2],
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for starter in starters
    ]
    reservations_output = [process.communicate(timeout=10) for process in reservation_processes]
    assert [process.returncode for process in reservation_processes] == [0, 0], reservations_output
    reservations = [json.loads(stdout) for stdout, _stderr in reservations_output]
    assert reservations[0]['port'] != reservations[1]['port']
    claim_root = runtime / 'playwright-port-claims'
    claim_documents = [
        json.loads((claim_root / f"{reservation['port']}.json").read_text(encoding='utf-8'))
        for reservation in reservations
    ]
    assert all(set(document) == {'checkoutScope', 'token'} for document in claim_documents)

    processes = [
        subprocess.Popen(  # noqa: S603
            [
                node,
                str(starter),
                '--contract-child',
                '--claim-token',
                reservation['token'],
            ],
            cwd=starter.parents[2],
            env={**environment, 'BASE_URL': f"http://127.0.0.1:{reservation['port']}"},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for starter, reservation in zip(starters, reservations, strict=True)
    ]
    try:
        ready: dict[int, dict[str, object]] = {}
        starting: dict[int, dict[str, object]] = {}
        deadline = time.monotonic() + 10
        while len(ready) < len(processes) and time.monotonic() < deadline:
            streams = [
                process.stdout for process in processes if process.stdout and process.poll() is None
            ]
            readable, _, _ = select.select(streams, [], [], 0.2)
            for stream in readable:
                line = stream.readline()
                process_index = next(
                    i for i, process in enumerate(processes) if process.stdout is stream
                )
                event = json.loads(line)
                if event['status'] == 'starting':
                    starting[process_index] = event
                elif event['status'] == 'ready':
                    ready[process_index] = event
        assert len(ready) == 2, [
            process.stderr.read() if process.poll() is not None and process.stderr else ''
            for process in processes
        ]

        results = [ready[index] for index in range(len(processes))]
        assert all(result['status'] == 'ready' for result in results)
        assert results[0]['checkoutScope'] != results[1]['checkoutScope']
        assert results[0]['playwrightRoot'] != results[1]['playwrightRoot']
        assert results[0]['runtimeDir'] != results[1]['runtimeDir']
        assert results[0]['port'] != results[1]['port']
        assert results[0]['innerPort'] != results[1]['innerPort']
        assert all(starting[index]['innerPort'] == results[index]['innerPort'] for index in ready)

        # 读取生产 identity proxy 路径，证明不是仅监听端口的测试替身。
        for result in results:
            with urllib.request.urlopen(  # noqa: S310
                f"http://127.0.0.1:{result['port']}/__feipi_fixture_identity",
                timeout=2,
            ) as response:
                identity = json.loads(response.read())
                assert identity['kind'] == 'feipi-session-browser-fixture'

        for process in processes:
            process.terminate()
        completed = [process.communicate(timeout=10) for process in processes]
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
    assert [process.returncode for process in processes] == [0, 0], completed
    assert all(not Path(result['runtimeDir']).exists() for result in results)
    assert all(process.poll() is not None for process in processes)
    assert list(claim_root.glob('*.json')) == []

    # contract 进程退出后端口必须已关闭，不能遗留后台 server。
    for result in results:
        for port in (result['port'], result['innerPort']):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
                client.settimeout(0.2)
                assert client.connect_ex(('127.0.0.1', port)) != 0


def test_playwright_failure_releases_both_claims_child_and_runtime(tmp_path: Path) -> None:
    """生产生命周期 readiness 失败时必须释放 outer/inner 全部资源。"""
    runtime = tmp_path / 'runtime'
    checkout = tmp_path / 'checkout-failure'
    target = checkout / 'tests/playwright'
    target.mkdir(parents=True)
    source_root = Path('tests/playwright')
    for filename in ('runtime-paths.js', 'start-java-fixture-server.js'):
        shutil.copy2(source_root / filename, target / filename)

    node = shutil.which('node')
    assert node is not None, 'Node.js is required by the Playwright resource contract'
    environment = {
        **os.environ,
        'FEIPI_AGENT_RUNTIME_ROOT': str(runtime),
        'FEIPI_RUN_ID': 'failure-run',
    }
    starter = target / 'start-java-fixture-server.js'
    reserved = subprocess.run(  # noqa: S603
        [node, str(starter), '--reserve-port'],
        cwd=checkout,
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )
    outer = json.loads(reserved.stdout)
    process = subprocess.Popen(  # noqa: S603
        [node, str(starter), '--contract-child-fail', '--claim-token', outer['token']],
        cwd=checkout,
        env={**environment, 'BASE_URL': f"http://127.0.0.1:{outer['port']}"},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    stdout, stderr = process.communicate(timeout=10)
    assert process.returncode != 0, stderr
    starting = json.loads(stdout.splitlines()[0])
    assert starting['status'] == 'starting'
    assert not Path(starting['runtimeDir']).exists()
    assert list((runtime / 'playwright-port-claims').glob('*.json')) == []
    assert process.poll() is not None
    for port in (starting['port'], starting['innerPort']):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
            client.settimeout(0.2)
            assert client.connect_ex(('127.0.0.1', port)) != 0


def test_child_temp_directories_are_checkout_scoped(tmp_path: Path, monkeypatch) -> None:
    runtime = tmp_path / 'runtime'
    first_checkout = tmp_path / 'checkout-a'
    second_checkout = tmp_path / 'checkout-b'
    first_checkout.mkdir()
    second_checkout.mkdir()
    monkeypatch.setenv('FEIPI_AGENT_RUNTIME_ROOT', str(runtime))
    monkeypatch.setenv('FEIPI_RUN_ID', 'same-run')

    first = executor._run_tmp_dir(first_checkout, 'child-environment')  # noqa: SLF001
    second = executor._run_tmp_dir(second_checkout, 'child-environment')  # noqa: SLF001

    assert first != second
    assert first.is_dir() and second.is_dir()


def test_catalog_has_no_scheduler_or_resource_graph_fields() -> None:
    catalog = Path('config/gates.yaml').read_text(encoding='utf-8')
    playwright_config = Path('tests/playwright/playwright.config.js').read_text(encoding='utf-8')
    fixture_starter = Path('tests/playwright/start-java-fixture-server.js').read_text(
        encoding='utf-8'
    )

    assert '\n  parallel:' not in catalog
    assert '\n  resources:' not in catalog
    assert '--find-port' not in playwright_config + fixture_starter
    assert '--reserve-port' in playwright_config + fixture_starter
    assert 'portClaim.token' in playwright_config
    assert 'consumePortClaim(port, claimToken)' in fixture_starter
    assert 'allocatePort' not in fixture_starter
    assert 'runId' not in fixture_starter
    assert 'sessionId' not in fixture_starter
