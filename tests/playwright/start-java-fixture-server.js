#!/usr/bin/env node

const fs = require('fs');
const http = require('http');
const net = require('net');
const path = require('path');
const crypto = require('crypto');
const { spawn, spawnSync } = require('child_process');
const {
  checkoutScope,
  repoRoot: ROOT,
  runTmpRoot,
  runtimeRoot,
} = require('./runtime-paths');

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

function portClaimPath(port) {
  return path.join(portClaimRoot(), `${port}.json`);
}

function portClaimRoot() {
  if (process.env.FEIPI_AGENT_RUNTIME_ROOT) {
    return path.join(runtimeRoot, 'playwright-port-claims');
  }
  const commonDir = spawnSync('git', ['rev-parse', '--git-common-dir'], {
    cwd: ROOT,
    encoding: 'utf8',
  });
  const repositoryIdentity = commonDir.status === 0
    ? path.resolve(ROOT, commonDir.stdout.trim())
    : ROOT;
  const repositoryScope = crypto
    .createHash('sha256')
    .update(repositoryIdentity)
    .digest('hex')
    .slice(0, 16);
  return path.join(process.env.TMPDIR || '/tmp', 'feipi-playwright-port-claims', repositoryScope);
}

/**
 * 在真实 socket 仍被持有时原子写入端口 claim，然后才释放探测 socket。
 * claim 是跨 checkout 的端口选择协议；starter 绑定前必须持有匹配 token，
 * 因而两个本仓库 invocation 不会经历“查找后无所有权地等待绑定”的窗口。
 */
async function reservePortClaim(requestedPort = 0) {
  const claimRoot = portClaimRoot();
  fs.mkdirSync(claimRoot, { recursive: true });
  for (let attempt = 0; attempt < 20; attempt += 1) {
    const server = net.createServer();
    await new Promise((resolve, reject) => {
      server.once('error', reject);
      server.listen(requestedPort, '127.0.0.1', resolve);
    });
    const port = server.address().port;
    const token = crypto.randomUUID();
    const claimPath = portClaimPath(port);
    try {
      fs.writeFileSync(claimPath, JSON.stringify({ checkoutScope, token }), {
        encoding: 'utf8',
        flag: 'wx',
        mode: 0o600,
      });
      await new Promise((resolve) => server.close(resolve));
      return { port, token };
    } catch (error) {
      await new Promise((resolve) => server.close(resolve));
      if (error.code !== 'EEXIST' || requestedPort) throw error;
    }
  }
  throw new Error('unable to claim a unique Playwright proxy port');
}

function consumePortClaim(port, token) {
  const claimPath = portClaimPath(port);
  const claim = JSON.parse(fs.readFileSync(claimPath, 'utf8'));
  if (claim.checkoutScope !== checkoutScope || claim.token !== token) {
    throw new Error(`invalid Playwright proxy port claim for ${port}`);
  }
  // token 只消费一次；claim 文件继续代表该 checkout 对端口的临时所有权。
  fs.writeFileSync(claimPath, JSON.stringify({ checkoutScope }), { encoding: 'utf8', mode: 0o600 });
  return claimPath;
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
  // fixture 数据只在启动 Java 服务前生成，避免端口与进程管理代码掺入数据准备细节。
  const { generateSessionFixtures } = require('../fixtures/generate-session-fixtures');
  const dataDir = path.join(runtimeDir, 'fixture-data');
  const indexDir = path.join(runtimeDir, 'fixture-index');
  const mainRoot = path.join(ROOT, 'tests', 'fixtures', 'session_hifi_fixture');
  fs.cpSync(mainRoot, dataDir, { recursive: true });
  generateSessionFixtures(dataDir);
  fs.mkdirSync(indexDir, { recursive: true });
  return { dataDir, indexDir };
}

async function fetchFixtureJson(baseURL, pathname) {
  const response = await fetch(`${baseURL}${pathname}`, {
    headers: { accept: 'application/json' },
    signal: AbortSignal.timeout(5_000),
  });
  if (!response.ok) {
    throw new Error(`fixture isolation check ${pathname} returned HTTP ${response.status}`);
  }
  return response.json();
}

async function validateFixtureIsolation(baseURL) {
  const { SPEC } = require('../fixtures/generate-session-fixtures');
  const expectedSessionCount = SPEC.mockCount + 2;
  const [summary, rowsResponse] = await Promise.all([
    fetchFixtureJson(baseURL, '/api/sessions/summary'),
    fetchFixtureJson(baseURL, '/api/sessions/rows?page_size=100'),
  ]);
  const rows = Array.isArray(rowsResponse.rows) ? rowsResponse.rows : [];
  const distinctProjects = new Set(rows.map((row) => row.projectKey));
  const expectedProjects = new Set([
    SPEC.project,
    'synthetic/workspace/projects/feipi-session-browser',
  ]);
  const isolated = summary.totalCount === expectedSessionCount
    && summary.projectCount === expectedProjects.size
    && rowsResponse.pagination?.totalItems === expectedSessionCount
    && rows.length === expectedSessionCount
    && rows.every((row) => row.agent === 'claude_code')
    && distinctProjects.size === expectedProjects.size
    && [...distinctProjects].every((project) => expectedProjects.has(project));
  if (!isolated) {
    throw new Error(
      'fixture isolation mismatch: '
        + `expected=${expectedSessionCount}, summaryTotal=${summary.totalCount}, `
        + `summaryProjects=${summary.projectCount}, rowsTotal=${rowsResponse.pagination?.totalItems}, `
        + `rows=${rows.length}, claudeOnly=${rows.every((row) => row.agent === 'claude_code')}, `
        + `distinctProjects=${distinctProjects.size}`,
    );
  }
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

/**
 * 启动真实 Java fixture 的唯一生命周期：准备数据、扫描、启动服务、等待就绪，
 * 再挂载 identity proxy；端口 claim、信号处理和临时文件也在这里统一清理。
 */
async function startServer({ claimToken = '' } = {}) {
  const baseURL = process.env.BASE_URL || 'http://127.0.0.1:19099';
  const parsed = new URL(baseURL);
  const port = Number(parsed.port || 80);
  const outerClaimPath = consumePortClaim(port, claimToken);
  let innerClaimPath = null;
  const launcher = path.join(ROOT, 'java', 'app-cli', 'build', 'install', 'app-cli', 'bin', 'app-cli');
  let innerPort;
  let runtimeDir = '';
  let javaEnv = {};
  const cleanup = () => {
    if (runtimeDir) fs.rmSync(runtimeDir, { recursive: true, force: true });
    fs.rmSync(outerClaimPath, { force: true });
    if (innerClaimPath) fs.rmSync(innerClaimPath, { force: true });
  };
  try {
    const innerClaim = await reservePortClaim();
    innerPort = innerClaim.port;
    innerClaimPath = consumePortClaim(innerPort, innerClaim.token);
    if (!fs.existsSync(launcher)) {
      runChecked(
        path.join(ROOT, 'gradlew'),
        [':java:app-cli:installDist', '--console=plain'],
        'Gradle installDist',
        { timeout: 300_000 },
      );
    }

    fs.mkdirSync(runTmpRoot, { recursive: true });
    runtimeDir = fs.mkdtempSync(path.join(runTmpRoot, 'playwright-java-fixture-'));
    const { dataDir, indexDir } = copyFixtures(runtimeDir);
    const codexDataDir = path.join(runtimeDir, 'empty-codex-data');
    const qoderDataDir = path.join(runtimeDir, 'empty-qoder-data');
    fs.mkdirSync(codexDataDir, { recursive: true });
    fs.mkdirSync(qoderDataDir, { recursive: true });
    javaEnv = {
      CLAUDE_DATA_DIR: dataDir,
      CODEX_DATA_DIR: codexDataDir,
      QODER_DATA_DIR: qoderDataDir,
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
    cleanup();
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
  let stopExitCode = 0;
  let proxy = null;
  const stop = (signal, exitCode = 0) => {
    if (stopping) return;
    stopping = true;
    stopExitCode = exitCode;
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
    process.exit(stopExitCode);
  });

  const innerURL = `http://127.0.0.1:${innerPort}`;
  if (!await waitUntilReady(innerURL, server)) {
    console.error(`[playwright-fixture] readiness timeout for synthetic Java server on ${innerURL}.`);
    if (diagnostics.trim()) console.error(diagnostics);
    stop('SIGTERM');
    process.exit(1);
  }
  try {
    await validateFixtureIsolation(innerURL);
  } catch (error) {
    console.error(`[playwright-fixture] ${error.message}`);
    stop('SIGTERM', 1);
    return;
  }
  try {
    proxy = await startIdentityProxy(port, innerPort);
  } catch (error) {
    console.error(`[playwright-fixture] identity proxy launch failed: ${error.message}`);
    stop('SIGTERM', 1);
    return;
  }
  console.log(`[playwright-fixture] ready with identity ${JSON.stringify(FIXTURE_IDENTITY)} on ${baseURL}`);
}

function argumentValue(name) {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : '';
}

if (process.argv.includes('--reserve-port')) {
  const requestedPort = Number(argumentValue('--port') || 0);
  reservePortClaim(requestedPort).then((claim) => console.log(JSON.stringify(claim))).catch((error) => {
    console.error(`[playwright-fixture] port claim failed: ${error.stack || error.message}`);
    process.exit(1);
  });
} else {
  startServer({
    claimToken: argumentValue('--claim-token'),
  }).catch((error) => {
    console.error(`[playwright-fixture] setup failed: ${error.stack || error.message}`);
    process.exit(1);
  });
}
