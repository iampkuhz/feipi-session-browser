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
async function reservePortClaim() {
  const claimRoot = portClaimRoot();
  fs.mkdirSync(claimRoot, { recursive: true });
  for (let attempt = 0; attempt < 20; attempt += 1) {
    const server = net.createServer();
    await new Promise((resolve, reject) => {
      server.once('error', reject);
      server.listen(0, '127.0.0.1', resolve);
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
      if (error.code !== 'EEXIST') throw error;
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
    // Playwright 的请求池可能在代理空闲关闭时复用旧连接；每个下游响应显式结束该连接。
    response.setHeader('connection', 'close');
    if (request.url === '/__feipi_fixture_identity') {
      response.writeHead(200, { 'content-type': 'application/json; charset=utf-8' });
      response.end(JSON.stringify(FIXTURE_IDENTITY));
      return;
    }
    let upstreamResponse;
    let failed = false;
    let cancelled = false;
    function diagnose(phase, error) {
      const code = error && typeof error.code === 'string' && /^[A-Z0-9_]{1,40}$/.test(error.code)
        ? error.code : 'UNKNOWN';
      console.warn('[playwright-fixture-transport] ' + JSON.stringify({
        phase, code, reusedSocket: upstream.reusedSocket === true,
        complete: upstreamResponse ? upstreamResponse.complete === true : false,
      }));
    }
    function releaseUpstream() {
      if (upstreamResponse && !upstreamResponse.destroyed) upstreamResponse.destroy();
      if (!upstream.destroyed) upstream.destroy();
    }
    function fail(phase, error) {
      if (failed || cancelled) return;
      failed = true;
      diagnose(phase, error);
      if (!response.destroyed && !response.writableEnded) {
        if (!response.headersSent) {
          response.writeHead(502, { 'content-type': 'text/plain; charset=utf-8' });
          response.end('fixture upstream unavailable');
        } else {
          // A partial body is never a successful response, even after headers were sent.
          response.destroy();
        }
      }
      releaseUpstream();
    }
    function cancel(phase, error) {
      if (cancelled || failed) return;
      cancelled = true;
      diagnose(phase, error);
      releaseUpstream();
    }
    const upstream = http.request({
      headers: request.headers,
      host: '127.0.0.1',
      method: request.method,
      path: request.url,
      port: innerPort,
    }, (incoming) => {
      upstreamResponse = incoming;
      incoming.on('aborted', () => fail('upstream_response_aborted', { code: 'UPSTREAM_ABORTED' }));
      incoming.on('error', error => fail('upstream_response_error', error));
      incoming.on('close', () => {
        if (!incoming.complete) fail('upstream_response_incomplete_close', { code: 'UPSTREAM_INCOMPLETE' });
      });
      if (cancelled || failed || response.destroyed) {
        releaseUpstream();
        return;
      }
      const { connection: _connection, 'keep-alive': _keepAlive, ...headers } = incoming.headers;
      response.writeHead(incoming.statusCode || 502, headers);
      incoming.pipe(response);
    });
    upstream.on('error', error => fail('upstream_request_error', error));
    request.on('aborted', () => cancel('downstream_request_aborted', { code: 'DOWNSTREAM_ABORTED' }));
    request.on('error', error => cancel('downstream_request_error', error));
    response.on('error', error => cancel('downstream_response_error', error));
    response.on('close', () => {
      if (!response.writableFinished) cancel('downstream_response_incomplete_close', { code: 'DOWNSTREAM_CLOSED' });
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

function resolveJavaEnvironment() {
  // npm 直跑也复用构建入口的 JDK 25 发现；必须先于合成 HOME 的隔离。
  const result = spawnSync('bash', [path.join(ROOT, 'scripts/harness/java_env.sh')], {
    cwd: ROOT,
    env: process.env,
    encoding: 'utf8',
    timeout: 30_000,
  });
  if (result.status !== 0 || result.error) {
    throw new Error(`fixture JDK discovery failed: ${tail(result.error?.message || result.stderr)}`);
  }
  const home = result.stdout.trim();
  if (!home || home.includes('\n')) throw new Error('fixture JDK discovery returned an invalid home');
  return { JAVA_HOME: home, PATH: `${home}/bin:${process.env.PATH || ''}` };
}

function copyFixtures(runtimeDir) {
  // fixture 数据只在启动 Java 服务前生成，避免端口与进程管理代码掺入数据准备细节。
  const { generateSessionFixtures } = require('../fixtures/generate-session-fixtures');
  const homeDir = path.join(runtimeDir, 'fixture home');
  const dataDir = path.join(homeDir, '.claude');
  const indexDir = path.join(runtimeDir, 'fixture-index');
  const mainRoot = path.join(ROOT, 'java', 'tests', 'fixtures', 'session_hifi_fixture');
  fs.cpSync(mainRoot, dataDir, { recursive: true });
  generateSessionFixtures(dataDir);
  fs.mkdirSync(indexDir, { recursive: true });
  return { homeDir, indexDir };
}

function copyDistribution(runtimeDir, source = path.join(ROOT, 'java', 'app-cli', 'build', 'install', 'app-cli')) {
  const distribution = path.join(runtimeDir, 'app-cli');
  fs.cpSync(source, distribution, {
    recursive: true,
    dereference: true,
    // Enforce per-entry traversal: the macOS native fast path may retain symlinks.
    filter: () => true,
  });
  return path.join(distribution, 'bin', 'app-cli');
}

async function validateStaticResources(pages) {
  const resources = new Map();
  for (const page of pages) {
    const html = await page.text();
    let count = 0;
    for (const tag of html.matchAll(/<(script|link)\b[^>]*>/gi)) {
      const attributes = Object.fromEntries([...tag[0].matchAll(/([\w-]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))/g)]
        .map((attribute) => [attribute[1].toLowerCase(), attribute[2] ?? attribute[3] ?? attribute[4]]));
      const script = tag[1].toLowerCase() === 'script';
      if (!script && !attributes.rel?.toLowerCase().split(/\s+/).includes('stylesheet')) continue;
      const reference = script ? attributes.src : attributes.href;
      if (!reference) continue;
      const url = new URL(reference.replace(/&amp;/g, '&'), page.url);
      if (url.origin !== new URL(page.url).origin) continue;
      resources.set(url.href, script ? 'javascript' : 'css');
      count += 1;
    }
    if (!count) throw new Error(`fixture static readiness: no same-origin JS/CSS in ${page.url}`);
  }
  for (const [url, kind] of resources) {
    let response;
    try {
      response = await fetch(url, { signal: AbortSignal.timeout(5_000), redirect: 'manual' });
      const contentType = (response.headers.get('content-type') || '').split(';')[0].trim().toLowerCase();
      const validType = kind === 'css' ? contentType === 'text/css'
        : ['text/javascript', 'application/javascript', 'application/ecmascript', 'text/ecmascript'].includes(contentType);
      const body = await response.text();
      const content = body.replace(/^(?:\s|<!--[\s\S]*?-->|\/\*[\s\S]*?\*\/)*/, '');
      if (response.status !== 200 || !validType || !content
          || /^(?:<!doctype\s+html|<html\b|<head\b|<body\b)/i.test(content)) {
        throw new Error(`HTTP ${response.status}, content-type=${contentType || '(missing)'}, expected ${kind}`);
      }
    } catch (error) {
      throw new Error(`fixture static readiness failed for ${url}: ${error.message}`);
    }
  }
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

async function waitForPublishedScan(baseURL, timeoutMs = 20_000) {
  const deadline = performance.now() + timeoutMs;
  do {
    const scan = await fetchFixtureJson(baseURL, '/api/scan-status');
    if (scan.status === 'failure' || scan.errorCount > 0) {
      throw new Error('fixture scan publication failed');
    }
    if (scan.status === 'success' && scan.publishedDataAvailable) return;
    await new Promise(resolve => setTimeout(resolve, 250));
  } while (performance.now() < deadline);
  throw new Error('fixture scan publication did not become ready');
}

async function captureDiagnosticScreenshot(target, options) {
  // 这些成功截图供本地阅读，不参与断言。托管 CI 的失败截图和 trace 由 Playwright 配置保留。
  if (process.env.GITHUB_ACTIONS === 'true') return false;
  await target.screenshot(options);
  return true;
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

async function validateImportReadiness(baseURL) {
  const rows = [
    { type: 'session_meta', payload: { id: 'synthetic-fixture-preflight', cwd: '/synthetic/preflight' } },
    { type: 'response_item', payload: { type: 'message', role: 'user',
      content: [{ type: 'input_text', text: 'Synthetic readiness only' }] } },
  ];
  const upload = new FormData();
  upload.set('source', 'codex');
  upload.set('file', new Blob([rows.map(row => JSON.stringify(row)).join('\n') + '\n'],
    { type: 'application/x-ndjson' }), 'synthetic-readiness.jsonl');
  const headers = { Origin: new URL(baseURL).origin };
  const response = await fetch(baseURL + '/api/imports',
    { method: 'POST', body: upload, headers, signal: AbortSignal.timeout(5_000) });
  if (response.status !== 201) throw new Error(`fixture import readiness: POST returned HTTP ${response.status}`);
  const { import_id: id } = await response.json();
  if (!/^[0-9a-f-]{36}$/i.test(id)) throw new Error('fixture import readiness: invalid import ID');
  const deleted = await fetch(baseURL + '/api/imports/' + id,
    { method: 'DELETE', headers, signal: AbortSignal.timeout(5_000) });
  if (deleted.status !== 204) throw new Error(`fixture import readiness: DELETE returned HTTP ${deleted.status}`);
}

async function checkBrowserRuntime() {
  const { chromium } = require('playwright');
  fs.mkdirSync(runTmpRoot, { recursive: true });
  const probe = fs.mkdtempSync(path.join(runTmpRoot, 'runtime-check-'));
  try {
    const volume = fs.statfsSync(probe);
    const freeMiB = Math.floor(volume.bavail * volume.bsize / 1024 / 1024);
    // 完整运行的临时产物曾达到 1.4 GiB；保留失败证据所需余量。
    if (freeMiB < 2048) throw new Error(`fixture temporary space: ${freeMiB} MiB available; need 2048 MiB`);
  } finally {
    fs.rmdirSync(probe);
  }
  const browser = await chromium.launch({ headless: true, timeout: 10_000 });
  await browser.close();
}

async function waitUntilReady(baseURL, server) {
  const paths = [
    '/dashboard',
    `/sessions/claude_code/${MAIN_SESSION_ID}`,
    `/sessions/claude_code/${LONG_SESSION_ID}`,
  ];
  for (let attempt = 0; attempt < 30; attempt += 1) {
    if (server.exitCode !== null) return false;
    let responses;
    let scan;
    try {
      responses = await Promise.all(paths.map((item) => fetch(`${baseURL}${item}`, {
        signal: AbortSignal.timeout(2_000),
      })));
      scan = await fetchFixtureJson(baseURL, '/api/scan-status');
    } catch (_) {
      // 进程启动期间连接失败属于预期重试条件。
    }
    if (scan?.status === 'failure') return false;
    if (scan?.status === 'success' && scan.errorCount === 0
        && scan.publishedDataAvailable && responses.every((response) => response.ok)) {
      // 已可用页面的静态资源失败不是启动瞬态；立即保留明确诊断，不重试掩盖。
      await validateStaticResources(responses);
      return true;
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  return false;
}

/**
 * 启动真实 Java fixture 的唯一生命周期：准备数据、正常启动并自动扫描、等待内容就绪，
 * 再挂载 identity proxy；端口 claim、信号处理和临时文件也在这里统一清理。
 */
async function startServer(claimToken) {
  const baseURL = process.env.FEIPI_PLAYWRIGHT_MANAGED_BASE_URL;
  const port = Number(new URL(baseURL).port);
  const outerClaimPath = consumePortClaim(port, claimToken);
  let innerClaimPath = null;
  let launcher;
  let innerPort;
  let runtimeDir = '';
  let javaEnv = {};
  const cleanup = () => {
    if (runtimeDir) fs.rmSync(runtimeDir, { recursive: true, force: true });
    fs.rmSync(outerClaimPath, { force: true });
    if (innerClaimPath) fs.rmSync(innerClaimPath, { force: true });
  };
  try {
    javaEnv = resolveJavaEnvironment();
    const innerClaim = await reservePortClaim();
    innerPort = innerClaim.port;
    innerClaimPath = consumePortClaim(innerPort, innerClaim.token);
    // 启动器存在不代表其 JAR/静态资源仍对应当前源码；由 Gradle 增量同步后再验页面。
    console.log('[playwright-fixture] build: one installDist');
    runChecked(
      path.join(ROOT, 'java', 'gradlew'),
      ['-p', path.join(ROOT, 'java'), ':java:app-cli:installDist', '--console=plain'],
      'Gradle installDist',
      { timeout: 300_000, env: javaEnv },
    );

    fs.mkdirSync(runTmpRoot, { recursive: true });
    runtimeDir = fs.mkdtempSync(path.join(runTmpRoot, 'playwright-java-fixture-'));
    launcher = copyDistribution(runtimeDir);
    const { homeDir, indexDir } = copyFixtures(runtimeDir);
    fs.mkdirSync(path.join(homeDir, '.codex'), { recursive: true });
    fs.mkdirSync(path.join(homeDir, '.qoder'), { recursive: true });
    javaEnv = {
      ...javaEnv,
      HOME: homeDir,
      // JVM 显式使用隔离主目录，不依赖宿主账户目录或 HOME 的平台行为。
      JAVA_OPTS: `"-Duser.home=${homeDir}"`,
      APP_CLI_OPTS: '',
      JAVA_TOOL_OPTIONS: '',
      JDK_JAVA_OPTIONS: '',
      _JAVA_OPTIONS: '',
      INDEX_DIR: indexDir,
      SESSION_BROWSER_LOG_LEVEL: 'WARN',
    };
  } catch (error) {
    cleanup();
    throw error;
  }

  console.log('[playwright-fixture] start: one normal serve with automatic scan');
  const server = spawn(
    launcher,
    ['serve', '--host', '127.0.0.1', '--port', String(innerPort)],
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
    // 先等 Java exit 再清理 DB/日志目录，避免 shutdown 写回后残留目录或丢诊断。
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
  try {
    if (!await waitUntilReady(innerURL, server)) {
      throw new Error(`readiness timeout for synthetic Java server on ${innerURL}`);
    }
    await validateFixtureIsolation(innerURL);
    await validateImportReadiness(innerURL);
  } catch (error) {
    console.error(`[playwright-fixture] ${error.message}`);
    if (diagnostics.trim()) console.error(diagnostics);
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

module.exports = { captureDiagnosticScreenshot, copyDistribution, resolveJavaEnvironment, validateImportReadiness, validateStaticResources, waitForPublishedScan, waitUntilReady };

if (require.main === module) {
  if (process.argv.includes('--check-runtime')) {
    checkBrowserRuntime().catch((error) => {
      console.error(`[playwright-fixture] runtime preflight: ${error.message}`);
      process.exitCode = 1;
    });
  } else if (process.argv.includes('--reserve-port')) {
    reservePortClaim().then((claim) => console.log(JSON.stringify(claim))).catch((error) => {
      console.error(`[playwright-fixture] port claim failed: ${error.stack || error.message}`);
      process.exit(1);
    });
  } else {
    startServer(argumentValue('--claim-token')).catch((error) => {
      console.error(`[playwright-fixture] setup failed: ${error.stack || error.message}`);
      process.exit(1);
    });
  }
}
