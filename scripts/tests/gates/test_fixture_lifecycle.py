"""Browser fixture uses one normal serve and cleans runtime only after its exit."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_browser_fixture_removes_pre_scan_and_keeps_scan_content_readiness() -> None:
    source = (ROOT / 'java/tests/playwright/start-java-fixture-server.js').read_text()
    assert "['scan', '--full'" not in source
    assert "'--no-scan'" not in source
    assert "scan.status === 'success' && scan.errorCount === 0" in source
    assert 'scan.publishedDataAvailable' in source
    assert source.count("console.log('[playwright-fixture] build: one installDist')") == 1
    assert source.count("console.log('[playwright-fixture] start: one normal serve") == 1
    stop = source.split('const stop = (signal, exitCode = 0) => {', 1)[1].split('};', 1)[0]
    assert 'server.kill(signal)' in stop
    assert 'cleanup();' not in stop
    exited = source.split("server.on('exit', (code, signal) => {", 1)[1].split('});', 1)[0]
    assert exited.index('cleanup();') < exited.index('process.exit(')
