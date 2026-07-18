const { defineConfig } = require('@playwright/test');
const { execFileSync } = require('child_process');
const path = require('path');
const {
  repoRoot,
  runPlaywrightRoot,
} = require('./runtime-paths');

delete process.env.NO_COLOR;

function resolveWorkers() {
  const raw = process.env.SESSION_BROWSER_PLAYWRIGHT_WORKERS || process.env.PLAYWRIGHT_WORKERS || '';
  const parsed = Number.parseInt(raw, 10);
  if (Number.isFinite(parsed)) return Math.max(8, parsed);
  return 8;
}

const runOutputRoot = process.env.PLAYWRIGHT_OUTPUT_ROOT
  ? path.resolve(process.env.PLAYWRIGHT_OUTPUT_ROOT)
  : runPlaywrightRoot;
const serverScript = path.join(__dirname, 'start-java-fixture-server.js');
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
  testDir: '.',
  testMatch: ['**/*.spec.{js,ts}'],
  fullyParallel: true,
  workers: resolveWorkers(),
  forbidOnly: true,
  retries: 0,
  timeout: 30_000,
  reporter: [
    ['./no-skip-reporter.js'],
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
    cwd: repoRoot,
    url: `${baseURL}/sessions/claude_code/hifi-viz-session-001`,
    reuseExistingServer: reuseFixtureServer,
    timeout: 120_000,
  },
});
