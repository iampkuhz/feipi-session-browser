/**
 * macbook-smoke.spec.js — MacBook viewport smoke matrix (1280x800, 1440x900)
 *
 * Verifies that all major pages render correctly at MacBook viewport sizes.
 * This spec requires a running session-browser server and Playwright browser binaries.
 * If Playwright environment is unavailable, use tests/pages/test_macbook_smoke.py instead.
 */
import { test, expect } from '@playwright/test';

const VIEWPORTS = {
  'macbook-13': { width: 1280, height: 800 },
  'macbook-14': { width: 1440, height: 900 },
};

const PAGES = [
  { name: 'Dashboard', path: '/dashboard', heading: 'Dashboard' },
  { name: 'Sessions List', path: '/sessions', heading: 'Sessions' },
  { name: 'Session Detail', path: '/sessions/claude_code/test', heading: 'Session Detail' },
  { name: 'Agents', path: '/agents', heading: 'Agents' },
  { name: 'Projects', path: '/projects', heading: 'Projects' },
];

for (const [viewportName, size] of Object.entries(VIEWPORTS)) {
  test.describe(`MacBook ${viewportName} (${size.width}x${size.height})`, () => {
    test.use({ viewport: size });

    for (const pageSpec of PAGES) {
      test(`${pageSpec.name} page loads`, async ({ page }) => {
        await page.goto(pageSpec.path);
        // Verify page body is visible
        await expect(page.locator('body')).toBeVisible();
        // Verify page title contains expected heading
        const title = await page.title();
        expect(title.toLowerCase()).toContain(pageSpec.name.toLowerCase());
      });
    }

    test('Dashboard has metric cards', async ({ page }) => {
      await page.goto('/dashboard');
      const cards = page.locator('.metric-card');
      await expect(cards).toHaveCount(4);
    });

    test('Sessions List has data table', async ({ page }) => {
      await page.goto('/sessions');
      const table = page.locator('table[aria-label="Sessions table"]');
      await expect(table).toBeVisible();
    });

    test('Agents page renders agent list', async ({ page }) => {
      await page.goto('/agents');
      const agentList = page.locator('.agent-list, .data-table');
      await expect(agentList.first()).toBeVisible();
    });

    test('Projects page renders project list', async ({ page }) => {
      await page.goto('/projects');
      const projectList = page.locator('.project-list, .data-table');
      await expect(projectList.first()).toBeVisible();
    });
  });
}
