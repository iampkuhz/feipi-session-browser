const { defineConfig } = require('@playwright/test');
const { execFileSync } = require('child_process');
const path = require('path');

delete process.env.NO_COLOR;

function resolveWorkers() {
  const raw = process.env.SESSION_BROWSER_PLAYWRIGHT_WORKERS || process.env.PLAYWRIGHT_WORKERS || '';
  const parsed = Number.parseInt(raw, 10);
  if (Number.isFinite(parsed)) return Math.max(8, parsed);
  return 8;
}

const runId = process.env.FEIPI_RUN_ID || process.env.FEIPI_SESSION_ID || `pid-${process.pid}`;
const runtimeRoot = process.env.FEIPI_AGENT_RUNTIME_ROOT || path.join(process.cwd(), 'tmp', 'agent-runtime');
const runOutputRoot = process.env.PLAYWRIGHT_OUTPUT_ROOT || path.join(runtimeRoot, 'runs', runId, 'playwright');
const serverScript = path.join(__dirname, 'tests', 'playwright', 'start-java-fixture-server.js');
const baseURL = process.env.BASE_URL || `http://127.0.0.1:${execFileSync(
  process.execPath,
  [serverScript, '--find-port'],
  { encoding: 'utf8' },
).trim()}`;
const reuseFixtureServer = process.env.SESSION_BROWSER_REUSE_PLAYWRIGHT_SERVER === '1';

process.env.BASE_URL = baseURL;
process.env.PW_SESSION_URL = process.env.PW_SESSION_URL || `${baseURL}/sessions/claude_code/hifi-viz-session-001`;
process.env.PW_LONG_SESSION_URL = process.env.PW_LONG_SESSION_URL || `${baseURL}/sessions/claude_code/long-session-001`;

/**
 * Playwright 会话详情质量门禁配置。
 *
 * 默认由 Node starter 在动态端口启动真实 Java fixture server。Gate executor 已启动
 * 外部服务时，需同时传入 BASE_URL 和 SESSION_BROWSER_REUSE_PLAYWRIGHT_SERVER=1。
 */
module.exports = defineConfig({
  testDir: './tests/playwright',
  testMatch: ['**/*.spec.{js,ts}'],
  fullyParallel: true,
  workers: resolveWorkers(),
  forbidOnly: true,
  retries: 0,
  timeout: 30_000,
  reporter: [
    ['./tests/playwright/no-skip-reporter.js'],
    ['html', { outputFolder: path.join(runOutputRoot, 'report') }],
    ['list'],
  ],
  expect: {
    timeout: 5_000,
  },
  use: {
    baseURL,
    headless: true,
    viewport: { width: 1440, height: 1100 },
    ignoreHTTPSErrors: true,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  outputDir: path.join(runOutputRoot, 'test-results'),
  webServer: {
    command: `node "${serverScript}"`,
    url: `${baseURL}/sessions/claude_code/hifi-viz-session-001`,
    reuseExistingServer: reuseFixtureServer,
    timeout: 120_000,
  },
});
