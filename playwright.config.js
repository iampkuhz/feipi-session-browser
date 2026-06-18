// @ts-check
const { defineConfig } = require('@playwright/test');

function resolveWorkers() {
  const raw = process.env.SESSION_BROWSER_PLAYWRIGHT_WORKERS || process.env.PLAYWRIGHT_WORKERS || '';
  const parsed = Number.parseInt(raw, 10);
  if (Number.isFinite(parsed)) return Math.max(8, parsed);
  return 8;
}

const fixtureBaseURL = process.env.BASE_URL || 'http://127.0.0.1:19099';
const reuseFixtureServer = process.env.SESSION_BROWSER_REUSE_PLAYWRIGHT_SERVER === '1';
process.env.BASE_URL = fixtureBaseURL;
process.env.PW_SESSION_URL = process.env.PW_SESSION_URL || `${fixtureBaseURL}/sessions/claude_code/hifi-viz-session-001`;
process.env.PW_LONG_SESSION_URL = process.env.PW_LONG_SESSION_URL || `${fixtureBaseURL}/sessions/claude_code/long-session-001`;

/**
 * Playwright 视觉/冒烟质量门禁配置
 *
 * 用法：
 *   npx playwright test                          # 运行全部测试（需先启动服务）
 *   npx playwright test --headed                 # 带浏览器可见性运行
 *   npx playwright test session-detail           # 仅运行会话详情测试
 *   npx playwright test --update-snapshots       # 更新截图基线
 *
 * 服务需提前启动：
 *   ./scripts/session-browser.sh serve
 * 或设置 SB_TEST_DB 指向有效的 SQLite 索引并运行测试工具
 */
module.exports = defineConfig({
  testDir: './tests/playwright',
  testMatch: ['**/*.spec.{js,ts}'],
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: resolveWorkers(),
  reporter: [
    ['./tests/playwright/no-skip-reporter.js'],
    ['html', { outputFolder: 'reports/playwright-report' }],
    ['list'],
  ],
  webServer: {
    command: 'python scripts/start_fixture_server.py',
    url: `${fixtureBaseURL}/dashboard`,
    reuseExistingServer: reuseFixtureServer,
    timeout: 30_000,
  },

  use: {
    baseURL: fixtureBaseURL,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    viewport: { width: 1280, height: 900 },
    actionTimeout: 10_000,
    navigationTimeout: 15_000,
  },

  projects: [
    {
      name: 'chromium',
      use: { browserName: 'chromium' },
    },
  ],

  outputDir: 'test-results/',
});
