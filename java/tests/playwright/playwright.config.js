const { defineConfig } = require('@playwright/test');
const { execFileSync } = require('child_process');
const path = require('path');
const {
  repoRoot,
  runPlaywrightRoot,
} = require('./runtime-paths');

delete process.env.NO_COLOR;

const serverScript = path.join(__dirname, 'start-java-fixture-server.js');
// worker 继承父进程的地址，不重新预约端口或启动服务。
const inheritedBaseURL = process.env.FEIPI_PLAYWRIGHT_MANAGED_BASE_URL;
const portClaim = inheritedBaseURL ? null : JSON.parse(execFileSync(
  process.execPath,
  [serverScript, '--reserve-port'],
  { encoding: 'utf8' },
));
const baseURL = inheritedBaseURL || `http://127.0.0.1:${portClaim.port}`;
if (portClaim) process.env.FEIPI_PLAYWRIGHT_MANAGED_BASE_URL = baseURL;

module.exports = defineConfig({
  testDir: '.',
  testMatch: ['**/*.spec.{js,ts}'],
  fullyParallel: true,
  // 托管 runner 同时还运行 Web JVM/扫描 JVM；避免浏览器和冷扫描抢同一组核心。
  // 本机共享导入不超过 8 份；每个 worker 的典型用例可能同时保留 2 份。
  workers: process.env.GITHUB_ACTIONS === 'true' ? 2 : 4,
  forbidOnly: true,
  retries: 0,
  timeout: 30_000,
  reporter: [
    ['./no-skip-reporter.js'],
    ['html', { outputFolder: path.join(runPlaywrightRoot, 'report') }],
    ['list'],
  ],
  expect: {
    timeout: 5_000,
  },
  use: {
    baseURL,
    headless: true,
    viewport: { width: 1440, height: 1100 },
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  outputDir: path.join(runPlaywrightRoot, 'test-results'),
  webServer: portClaim ? {
    command: `node "${serverScript}" --claim-token ${portClaim.token}`,
    cwd: repoRoot,
    url: `${baseURL}/sessions/claude_code/hifi-viz-session-001`,
    reuseExistingServer: false,
    timeout: 120_000,
    stdout: 'pipe',
  } : undefined,
});
