// @ts-check
const { defineConfig } = require('@playwright/test');

/**
 * Playwright config for session-browser visual/smoke quality gate.
 *
 * Usage:
 *   npx playwright test                          # run all tests (server must be running)
 *   npx playwright test --headed                 # run with visible browser
 *   npx playwright test session-detail           # run session-detail tests only
 *   npx playwright test --update-snapshots       # update screenshot baselines
 *
 * Server must be started separately before running tests:
 *   ./scripts/session-browser.sh serve
 * (or point SB_TEST_DB to a valid SQLite index and run the test harness)
 */
module.exports = defineConfig({
  testDir: './',
  testMatch: ['e2e/**/*.spec.{js,ts}', 'tests/playwright/**/*.spec.{js,ts}'],
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: [['html', { outputFolder: 'playwright-report' }], ['list']],

  use: {
    baseURL: process.env.BASE_URL || 'http://127.0.0.1:18999',
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
