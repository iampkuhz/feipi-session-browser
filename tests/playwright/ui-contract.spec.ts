import { test, expect } from '@playwright/test';

const pages = [
  ['/dashboard', 'dashboard'],
  ['/sessions', 'sessions'],
  ['/projects', 'projects'],
  ['/agents', 'agents'],
  ['/glossary', 'glossary'],
];

for (const [url, name] of pages) {
  test(`${name} core screenshot`, async ({ page }) => {
    await page.goto(url);
    await expect(page.locator('body')).toBeVisible();
    await expect(page).toHaveScreenshot(`${name}-1440.png`, { fullPage: true, maxDiffPixelRatio: 0.05 });
  });
}

// ─── Dashboard viewport contract tests (06-validation-contract) ───
// Required viewports: 1440x900, 1280x800, 1180x800

const dashboardViewports = [
  { width: 1440, height: 900, label: '1440x900' },
  { width: 1280, height: 800, label: '1280x800' },
  { width: 1180, height: 800, label: '1180x800' },
] as const;

for (const vp of dashboardViewports) {
  test(`dashboard @ ${vp.label} — screenshot + visibility`, async ({ page }) => {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await page.goto('/dashboard');

    // Core structure visibility
    await expect(page.locator('.page-head')).toBeVisible();
    await expect(page.locator('.metric-grid')).toBeVisible();
    await expect(page.locator('.chart-card').first()).toBeVisible();

    // Scope switch must be present on dashboard
    await expect(page.locator('.scope-switch')).toBeVisible();

    // Full-page screenshot for visual regression
    await expect(page).toHaveScreenshot(`dashboard-${vp.label.replace('x', '-')}.png`, {
      fullPage: true,
      maxDiffPixelRatio: 0.05,
    });
  });
}
