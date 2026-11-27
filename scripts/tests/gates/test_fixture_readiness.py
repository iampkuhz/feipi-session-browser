"""Synthetic HTTP and filesystem checks for the fixture's startup boundary."""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / 'java/tests/playwright/start-java-fixture-server.js'


def run_node(source: str) -> None:
    result = subprocess.run(
        ['node', '-e', f'const fixture = require({str(FIXTURE)!r});\n' + source],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    ('mode', 'diagnostic'),
    [
        ('success', ''),
        ('commented-success', ''),
        ('server-error', 'HTTP 500'),
        ('wrong-mime', 'content-type=text/html'),
        ('html-body', 'expected javascript'),
        ('html-comment-body', 'expected javascript'),
        ('block-comment-body', 'expected javascript'),
        ('empty-body', 'expected javascript'),
        ('whitespace-body', 'expected javascript'),
        ('comment-only-body', 'expected javascript'),
        ('no-resources', 'no same-origin JS/CSS'),
        ('redirect', 'HTTP 302'),
    ],
)
def test_static_readiness_fails_once_with_specific_diagnostic(mode: str, diagnostic: str) -> None:
    run_node(
        r"""
const assert = require('node:assert/strict');
const http = require('node:http');
const mode = MODE;
const diagnostic = DIAGNOSTIC;
let assetRequests = 0;
let cssRequests = 0;
const server = http.createServer((request, response) => {
  if (request.url === '/api/scan-status') {
    response.setHeader('content-type', 'application/json');
    response.end(JSON.stringify({ status: 'success', errorCount: 0, publishedDataAvailable: true }));
  } else if (request.url.startsWith('/assets/')) {
    assetRequests++;
    if (mode === 'server-error') response.statusCode = 500;
    if (mode === 'redirect') {
      response.statusCode = 302;
      response.setHeader('location', '/dashboard');
    }
    const css = request.url === '/assets/site.css';
    if (css) cssRequests++;
    response.setHeader('content-type', mode === 'wrong-mime' ? 'text/html' : css ? 'text/css' : 'text/javascript; charset=utf-8');
    let body = css ? 'body {}' : 'console.log("ok")';
    if (mode === 'commented-success') body = '/* synthetic header */\n' + body;
    if (['wrong-mime', 'html-body'].includes(mode)) body = '<!doctype html><html>error</html>';
    if (mode === 'html-comment-body') body = '<!-- synthetic fallback -->\n<!doctype html><html>error</html>';
    if (mode === 'block-comment-body') body = '/* synthetic fallback */\n<html>error</html>';
    if (mode === 'empty-body') body = '';
    if (mode === 'whitespace-body') body = ' \n\t';
    if (mode === 'comment-only-body') body = '/* synthetic empty */';
    response.end(body);
  } else {
    response.setHeader('content-type', 'text/html');
    response.end(mode === 'no-resources' ? '<html>empty</html>' : `
      <script src='/assets/main.js?v=1&amp;x=2'></script>
      <link href="/assets/site.css" rel="stylesheet">
      <script src="https://external.invalid/ignored.js"></script>`);
  }
});
(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  try {
    const baseURL = `http://127.0.0.1:${server.address().port}`;
    const ready = fixture.waitUntilReady(baseURL, { exitCode: null });
    if (diagnostic) {
      await assert.rejects(ready, error => error.message.includes(diagnostic));
      assert.equal(assetRequests, mode === 'no-resources' ? 0 : 1);
    } else {
      assert.equal(await ready, true);
      assert.equal(assetRequests, 2, 'shared resources are validated once');
      assert.equal(cssRequests, 1);
    }
  } finally {
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
""".replace('MODE', repr(mode)).replace('DIAGNOSTIC', repr(diagnostic))
    )


def test_distribution_snapshot_survives_shared_install_replacement() -> None:
    run_node(
        r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const root = fs.mkdtempSync(path.join(os.tmpdir(), 'fixture-copy-test-'));
try {
  const shared = path.join(root, 'shared');
  const runtime = path.join(root, 'runtime');
  fs.mkdirSync(path.join(shared, 'bin'), { recursive: true });
  fs.mkdirSync(path.join(shared, 'lib'));
  fs.writeFileSync(path.join(shared, 'bin', 'app-cli'), '#!/bin/sh\nexit 0\n', { mode: 0o755 });
  fs.writeFileSync(path.join(shared, 'lib', 'web.jar'), 'initial-assets');
  fs.symlinkSync('web.jar', path.join(shared, 'lib', 'linked.jar'));
  const launcher = fixture.copyDistribution(runtime, shared);
  assert.equal(launcher, path.join(runtime, 'app-cli', 'bin', 'app-cli'));
  fs.accessSync(launcher, fs.constants.X_OK);
  fs.writeFileSync(path.join(shared, 'lib', 'web.jar'), 'replaced-assets');
  fs.rmSync(shared, { recursive: true });
  for (const name of ['web.jar', 'linked.jar']) {
    assert.equal(fs.readFileSync(path.join(runtime, 'app-cli', 'lib', name), 'utf8'), 'initial-assets');
    assert.equal(fs.lstatSync(path.join(runtime, 'app-cli', 'lib', name)).isSymbolicLink(), false);
  }
} finally {
  fs.rmSync(root, { recursive: true, force: true });
}
"""
    )


@pytest.mark.parametrize('status', (201, 409))
def test_import_readiness_reports_capacity_without_retry_and_cleans_success(status: int) -> None:
    run_node(
        r"""
const assert = require('node:assert/strict');
const http = require('node:http');
const id = '11111111-1111-4111-8111-111111111111';
const requests = [];
const server = http.createServer((request, response) => {
  requests.push(request.method + ' ' + request.url);
  assert.equal(request.headers.origin, 'http://' + request.headers.host);
  if (request.method === 'POST') {
    request.resume();
    response.writeHead(STATUS, { 'content-type': 'application/json' });
    response.end(JSON.stringify({ import_id: id }));
  } else {
    response.writeHead(204);
    response.end();
  }
});
(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  try {
    const ready = fixture.validateImportReadiness('http://127.0.0.1:' + server.address().port);
    if (STATUS === 201) {
      await ready;
      assert.deepEqual(requests, ['POST /api/imports', 'DELETE /api/imports/' + id]);
    } else {
      await assert.rejects(ready, /fixture import readiness: POST returned HTTP 409/);
      assert.deepEqual(requests, ['POST /api/imports']);
    }
  } finally {
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
""".replace('STATUS', str(status))
    )


def test_scan_wait_checks_the_publication_boundary_and_not_the_first_listen() -> None:
    run_node(
        r"""
const assert = require('node:assert/strict');
const http = require('node:http');
let reads = 0;
const server = http.createServer((req, res) => {
  assert.equal(req.url, '/api/scan-status');
  res.setHeader('content-type', 'application/json');
  const status = ++reads === 1 ? 'running' : reads === 2 ? 'success' :
    reads === 3 ? 'success' : 'failure';
  res.end(JSON.stringify({status, publishedDataAvailable: reads === 3, errorCount: 0}));
});
(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const base = 'http://127.0.0.1:' + server.address().port;
  try {
    await fixture.waitForPublishedScan(base);
    assert.equal(reads, 3);
    await assert.rejects(fixture.waitForPublishedScan(base), /scan publication failed/);
    assert.equal(reads, 4);
  } finally {
    await new Promise(resolve => server.close(resolve));
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    )


def test_hosted_ci_does_not_take_success_evidence_screenshots() -> None:
    run_node(
        r"""
const assert = require('node:assert/strict');
let captures = 0;
const target = { screenshot: () => captures++ };
(async () => {
  delete process.env.GITHUB_ACTIONS;
  assert.equal(await fixture.captureDiagnosticScreenshot(target), true);
  process.env.GITHUB_ACTIONS = 'true';
  assert.equal(await fixture.captureDiagnosticScreenshot(target), false);
  assert.equal(captures, 1);
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
    )


def test_fixture_freezes_shared_jdk_before_home_isolation() -> None:
    run_node(
        r"""
const assert = require('node:assert/strict');
const childProcess = require('node:child_process');
const original = childProcess.spawnSync;
let result = { status: 0, stdout: '/synthetic/jdk 25\n' };
childProcess.spawnSync = (command, args, options) => {
  assert.equal(command, 'bash');
  assert.ok(args[0].endsWith('/scripts/harness/java_env.sh'));
  assert.equal(options.env.HOME, process.env.HOME);
  return result;
};
// Reload so the fixture uses the synthetic process boundary, not the machine's JDK.
delete require.cache[require.resolve(FIXTURE_PATH)];
const isolated = require(FIXTURE_PATH);
try {
  const environment = isolated.resolveJavaEnvironment();
  assert.equal(environment.JAVA_HOME, '/synthetic/jdk 25');
  assert.equal(environment.PATH, '/synthetic/jdk 25/bin:' + process.env.PATH);
  result = { status: 1, stderr: 'invalid explicit JAVA_HOME' };
  assert.throws(() => isolated.resolveJavaEnvironment(), /invalid explicit JAVA_HOME/);
  result = { status: 0, stdout: '' };
  assert.throws(() => isolated.resolveJavaEnvironment(), /invalid home/);
} finally {
  childProcess.spawnSync = original;
}
""".replace('FIXTURE_PATH', repr(str(FIXTURE)))
    )
