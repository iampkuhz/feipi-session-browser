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

// ─── Session detail viewport contract tests (T096) ───
// Required viewports: 1440x900, 1280x800, 1180x800
// Requires a running server with indexed session data.
// Set PW_SESSION_URL to a valid session detail URL, otherwise tests skip.

function resolveSessionUrl(): string | null {
  const direct = process.env.PW_SESSION_URL;
  if (direct) return direct;
  return null;
}

for (const vp of dashboardViewports) {
  test(`session-detail @ ${vp.label} — screenshot + visibility`, async ({ page }) => {
    const sessionUrl = resolveSessionUrl();
    if (!sessionUrl) {
      console.log('No PW_SESSION_URL set; skipping session-detail viewport test.');
      return;
    }

    await page.setViewportSize({ width: vp.width, height: vp.height });
    await page.goto(sessionUrl);

    // Core structure visibility: hero, tabs, trace table
    await expect(page.locator('.hero').first()).toBeVisible();
    await expect(page.locator('.sd-tabs')).toBeVisible();
    await expect(page.locator('[data-trace-panel]')).toBeVisible();

    // Full-page screenshot for visual regression
    await expect(page).toHaveScreenshot(`session-detail-${vp.label.replace('x', '-')}.png`, {
      fullPage: true,
      maxDiffPixelRatio: 0.05,
    });
  });
}

// ─── Projects viewport contract tests (T110) ───
// Required viewports: 1440x900, 1280x800, 1180x800

for (const vp of dashboardViewports) {
  test(`projects @ ${vp.label} — screenshot + visibility`, async ({ page }) => {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await page.goto('/projects');

    // Core structure visibility
    await expect(page.locator('.page-head')).toBeVisible();
    await expect(page.locator('.metric-grid')).toBeVisible();
    await expect(page.locator('.data-table')).toBeVisible();

    // Full-page screenshot for visual regression
    await expect(page).toHaveScreenshot(`projects-${vp.label.replace('x', '-')}.png`, {
      fullPage: true,
      maxDiffPixelRatio: 0.05,
    });
  });
}

// ─── Project detail viewport contract tests (T124) ───
// Required viewports: 1440x900, 1280x800, 1180x800
// Requires a running server with indexed project data.
// Set PW_PROJECT_URL to a valid project detail URL, otherwise tests skip.

function resolveProjectUrl(): string | null {
  const direct = process.env.PW_PROJECT_URL;
  if (direct) return direct;
  return null;
}

for (const vp of dashboardViewports) {
  test(`project-detail @ ${vp.label} — screenshot + visibility`, async ({ page }) => {
    const projectUrl = resolveProjectUrl();
    if (!projectUrl) {
      console.log('No PW_PROJECT_URL set; skipping project-detail viewport test.');
      return;
    }

    await page.setViewportSize({ width: vp.width, height: vp.height });
    await page.goto(projectUrl);

    // Core structure visibility
    await expect(page.locator('.page-head')).toBeVisible();
    await expect(page.locator('.metric-grid')).toBeVisible();
    await expect(page.locator('.data-table')).toBeVisible();

    // Full-page screenshot for visual regression
    await expect(page).toHaveScreenshot(`project-detail-${vp.label.replace('x', '-')}.png`, {
      fullPage: true,
      maxDiffPixelRatio: 0.05,
    });
  });
}

// ─── Agents list viewport contract tests (T138) ───
// Required viewports: 1440x900, 1280x800, 1180x800

for (const vp of dashboardViewports) {
  test(`agents @ ${vp.label} — screenshot + visibility`, async ({ page }) => {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await page.goto('/agents');

    // Core structure visibility
    await expect(page.locator('.page-head')).toBeVisible();
    await expect(page.locator('.metric-grid')).toBeVisible();
    await expect(page.locator('.data-table')).toBeVisible();

    // Full-page screenshot for visual regression
    await expect(page).toHaveScreenshot(`agents-${vp.label.replace('x', '-')}.png`, {
      fullPage: true,
      maxDiffPixelRatio: 0.05,
    });
  });
}

// ─── Glossary viewport contract tests (T166) ───
// Required viewports: 1440x900, 1280x800, 1180x800

for (const vp of dashboardViewports) {
  test(`glossary @ ${vp.label} — screenshot + visibility`, async ({ page }) => {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await page.goto('/glossary');

    // Core structure visibility
    await expect(page.locator('.page-head')).toBeVisible();
    await expect(page.locator('.metric-grid')).toBeVisible();
    await expect(page.locator('.filter-card')).toBeVisible();
    await expect(page.locator('.card.section').first()).toBeVisible();
    await expect(page.locator('.data-table').first()).toBeVisible();

    // Full-page screenshot for visual regression
    await expect(page).toHaveScreenshot(`glossary-${vp.label.replace('x', '-')}.png`, {
      fullPage: true,
      maxDiffPixelRatio: 0.05,
    });
  });
}

// ─── Agent detail viewport contract tests (T152) ───
// Required viewports: 1440x900, 1280x800, 1180x800
// Requires a running server with indexed agent data.
// Set PW_AGENT_URL to a valid agent detail URL (e.g. /agents/claude_code), otherwise tests skip.

function resolveAgentUrl(): string | null {
  const direct = process.env.PW_AGENT_URL;
  if (direct) return direct;
  return null;
}

for (const vp of dashboardViewports) {
  test(`agent-detail @ ${vp.label} — screenshot + visibility`, async ({ page }) => {
    const agentUrl = resolveAgentUrl();
    if (!agentUrl) {
      console.log('No PW_AGENT_URL set; skipping agent-detail viewport test.');
      return;
    }

    await page.setViewportSize({ width: vp.width, height: vp.height });
    await page.goto(agentUrl);

    // Core structure visibility
    await expect(page.locator('.header')).toBeVisible();
    await expect(page.locator('.metric-grid')).toBeVisible();
    await expect(page.locator('.data-table')).toBeVisible();

    // Full-page screenshot for visual regression
    await expect(page).toHaveScreenshot(`agent-detail-${vp.label.replace('x', '-')}.png`, {
      fullPage: true,
      maxDiffPixelRatio: 0.05,
    });
  });
}
