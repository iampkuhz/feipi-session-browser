#!/usr/bin/env node

const fs = require('fs');
const http = require('http');
const net = require('net');
const os = require('os');
const path = require('path');
const { spawn, spawnSync } = require('child_process');
const { generateSessionFixtures } = require('../fixtures/generate-session-fixtures');

const ROOT = path.resolve(__dirname, '..', '..');
const MAIN_SESSION_ID = 'hifi-viz-session-001';
const LONG_SESSION_ID = 'long-session-001';
const MAX_DIAGNOSTIC_CHARS = 8_000;
const FIXTURE_IDENTITY = Object.freeze({
  dataset: 'synthetic-hifi-v1',
  kind: 'feipi-session-browser-fixture',
  schemaVersion: 1,
});

function tail(value) {
  return String(value || '').slice(-MAX_DIAGNOSTIC_CHARS);
}

function findPort() {
  const server = net.createServer();
  server.on('error', (error) => {
    console.error(`[playwright-fixture] port allocation failed: ${error.message}`);
    process.exitCode = 1;
  });
  server.listen(0, '127.0.0.1', () => {
    const address = server.address();
    console.log(address.port);
    server.close();
  });
}

function allocatePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const address = server.address();
      server.close(() => resolve(address.port));
    });
  });
}

function startIdentityProxy(port, innerPort) {
  const proxy = http.createServer((request, response) => {
    if (request.url === '/__feipi_fixture_identity') {
      response.writeHead(200, { 'content-type': 'application/json; charset=utf-8' });
      response.end(JSON.stringify(FIXTURE_IDENTITY));
      return;
    }
    const upstream = http.request({
      headers: request.headers,
      host: '127.0.0.1',
      method: request.method,
      path: request.url,
      port: innerPort,
    }, (upstreamResponse) => {
      response.writeHead(upstreamResponse.statusCode || 502, upstreamResponse.headers);
      upstreamResponse.pipe(response);
    });
    upstream.on('error', (error) => {
      if (!response.headersSent) response.writeHead(502, { 'content-type': 'text/plain' });
      response.end(`fixture upstream unavailable: ${error.message}`);
    });
    request.pipe(upstream);
  });
  return new Promise((resolve, reject) => {
    proxy.once('error', reject);
    proxy.listen(port, '127.0.0.1', () => resolve(proxy));
  });
}

function runChecked(command, args, label, options = {}) {
  const result = spawnSync(command, args, {
    cwd: ROOT,
    encoding: 'utf8',
    env: { ...process.env, ...(options.env || {}) },
    maxBuffer: 16 * 1024 * 1024,
    timeout: options.timeout || 120_000,
  });
  if (result.status === 0 && !result.error) {
    return;
  }
  const reason = result.error ? result.error.message : `exit ${result.status}`;
  const diagnostic = tail(`${result.stdout || ''}\n${result.stderr || ''}`);
  throw new Error(`${label} failed: ${reason}${diagnostic.trim() ? `\n${diagnostic}` : ''}`);
}

function copyFixtures(runtimeDir) {
  const dataDir = path.join(runtimeDir, 'fixture-data');
  const indexDir = path.join(runtimeDir, 'fixture-index');
  const mainRoot = path.join(ROOT, 'tests', 'fixtures', 'session_hifi_fixture');
  fs.cpSync(mainRoot, dataDir, { recursive: true });
  generateSessionFixtures(dataDir);
  fs.mkdirSync(indexDir, { recursive: true });
  return { dataDir, indexDir };
}

async function waitUntilReady(baseURL, server) {
  const paths = [
    '/dashboard',
    `/sessions/claude_code/${MAIN_SESSION_ID}`,
    `/sessions/claude_code/${LONG_SESSION_ID}`,
  ];
  for (let attempt = 0; attempt < 30; attempt += 1) {
    if (server.exitCode !== null) return false;
    try {
      const responses = await Promise.all(paths.map((item) => fetch(`${baseURL}${item}`, {
        signal: AbortSignal.timeout(2_000),
      })));
      if (responses.every((response) => response.ok)) return true;
    } catch (_) {
      // 进程启动期间连接失败属于预期重试条件。
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  return false;
}

async function startServer() {
  const baseURL = process.env.BASE_URL || 'http://127.0.0.1:19099';
  const parsed = new URL(baseURL);
  const port = Number(parsed.port || 80);
  const innerPort = await allocatePort();
  const launcher = path.join(ROOT, 'java', 'app-cli', 'build', 'install', 'app-cli', 'bin', 'app-cli');
  if (!fs.existsSync(launcher)) {
    runChecked(
      path.join(ROOT, 'gradlew'),
      [':java:app-cli:installDist', '--console=plain'],
      'Gradle installDist',
      { timeout: 300_000 },
    );
  }

  const runId = process.env.FEIPI_RUN_ID || process.env.FEIPI_SESSION_ID || 'playwright';
  const runtimeBase = process.env.FEIPI_AGENT_RUNTIME_ROOT
    ? path.join(process.env.FEIPI_AGENT_RUNTIME_ROOT, 'runs', runId, 'tmp')
    : os.tmpdir();
  fs.mkdirSync(runtimeBase, { recursive: true });
  const runtimeDir = fs.mkdtempSync(path.join(runtimeBase, 'playwright-java-fixture-'));
  let dataDir;
  let indexDir;
  let javaEnv;
  try {
    ({ dataDir, indexDir } = copyFixtures(runtimeDir));
    javaEnv = {
      CLAUDE_DATA_DIR: dataDir,
      INDEX_DIR: indexDir,
      SESSION_BROWSER_LOG_LEVEL: 'WARN',
    };
    runChecked(
      launcher,
      ['scan', '--full', '--index-dir', indexDir],
      'fixture scan',
      { env: javaEnv, timeout: 120_000 },
    );
  } catch (error) {
    fs.rmSync(runtimeDir, { recursive: true, force: true });
    throw error;
  }

  const server = spawn(
    launcher,
    ['serve', '--host', '127.0.0.1', '--port', String(innerPort), '--allow-empty', '--no-scan'],
    { cwd: ROOT, env: { ...process.env, ...javaEnv }, stdio: ['ignore', 'pipe', 'pipe'] },
  );
  let diagnostics = '';
  for (const stream of [server.stdout, server.stderr]) {
    stream.on('data', (chunk) => {
      diagnostics = tail(diagnostics + chunk.toString());
    });
  }

  let stopping = false;
  let proxy = null;
  const cleanup = () => fs.rmSync(runtimeDir, { recursive: true, force: true });
  const stop = (signal) => {
    if (stopping) return;
    stopping = true;
    if (proxy) proxy.close();
    if (!server.killed) server.kill(signal);
    cleanup();
  };
  process.on('SIGINT', () => stop('SIGINT'));
  process.on('SIGTERM', () => stop('SIGTERM'));
  process.on('exit', cleanup);
  server.on('error', (error) => {
    console.error(`[playwright-fixture] Java server launch failed: ${error.message}`);
    cleanup();
    process.exit(1);
  });
  server.on('exit', (code, signal) => {
    cleanup();
    if (!stopping) {
      console.error(`[playwright-fixture] Java server exited (${code ?? signal ?? 'unknown'}).`);
      if (diagnostics.trim()) console.error(diagnostics);
      process.exit(code || 1);
    }
    process.exit(0);
  });

  const innerURL = `http://127.0.0.1:${innerPort}`;
  if (!await waitUntilReady(innerURL, server)) {
    console.error(`[playwright-fixture] readiness timeout for synthetic Java server on ${innerURL}.`);
    if (diagnostics.trim()) console.error(diagnostics);
    stop('SIGTERM');
    process.exit(1);
  }
  proxy = await startIdentityProxy(port, innerPort);
  console.log(`[playwright-fixture] ready with identity ${JSON.stringify(FIXTURE_IDENTITY)} on ${baseURL}`);
}

if (process.argv.includes('--find-port')) {
  findPort();
} else {
  startServer().catch((error) => {
    console.error(`[playwright-fixture] setup failed: ${error.stack || error.message}`);
    process.exit(1);
  });
}
