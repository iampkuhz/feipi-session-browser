/**
 * ui-contract.spec.ts — 页面视觉契约测试（截图 + 可见性）
 *
 * 覆盖所有主要页面的多视口截图和核心结构验证。
 * 视口：1440x900, 1280x800, 1180x800, 2560x1440
 */
import { test, expect } from '@playwright/test';

// ─── 核心页面截图 ───────────────────────────────────────────────────

const pages = [
  ['/dashboard', 'dashboard'],
  ['/sessions', 'sessions'],
  ['/projects', 'projects'],
  ['/glossary', 'glossary'],
];

for (const [url, name] of pages) {
  test(`${name} 核心截图`, async ({ page }) => {
    await page.goto(url);
    await expect(page.locator('body')).toBeVisible();
    await expect(page).toHaveScreenshot(`${name}-1440.png`, { fullPage: true, maxDiffPixelRatio: 0.05 });
  });
}

// ─── 视口配置 ────────────────────────────────────────────────────────
// 必需视口：1440x900, 1280x800, 1180x800, 2560x1440

const viewports = [
  { width: 1440, height: 900, label: '1440x900' },
  { width: 1280, height: 800, label: '1280x800' },
  { width: 1180, height: 800, label: '1180x800' },
  { width: 2560, height: 1440, label: '2560x1440' },
] as const;

for (const vp of viewports) {
  test(`[UI-VISUAL-009] 仪表板 @ ${vp.label} — 截图 + 可见性`, async ({ page }) => {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await page.goto('/dashboard');

    // 核心结构可见
    await expect(page.locator('.page-head')).toBeVisible();
    await expect(page.locator('.metric-grid')).toBeVisible();
    await expect(page.locator('.chart-card').first()).toBeVisible();

    // 范围切换必须存在
    await expect(page.locator('.scope-switch')).toBeVisible();

    // 全屏截图用于视觉回归
    await expect(page).toHaveScreenshot(`dashboard-${vp.label.replace('x', '-')}.png`, {
      fullPage: true,
      maxDiffPixelRatio: 0.05,
    });
  });
}

// ─── 会话详情视口契约测试（T096） ────────────────────────────────────
// 必需视口：1440x900, 1280x800, 1180x800, 2560x1440
// 使用 fixture session URL，不再依赖 PW_SESSION_URL 环境变量。

const FIXTURE_SESSION_URL = '/sessions/claude_code/hifi-viz-session-001';

for (const vp of viewports) {
  test(`[UI-SD-015] 会话详情 @ ${vp.label} — 截图 + 可见性`, async ({ page }) => {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await page.goto(FIXTURE_SESSION_URL, { waitUntil: 'domcontentloaded', timeout: 15000 });

    // 核心结构可见：hero、标签页、trace 表格
    await expect(page.locator('.sd-hero').first()).toBeVisible({ timeout: 10000 });
    await expect(page.locator('.sd-tabs')).toBeVisible();
    await expect(page.locator('[data-trace-panel]')).toBeVisible();

    // 全屏截图用于视觉回归
    await expect(page).toHaveScreenshot(`session-detail-${vp.label.replace('x', '-')}.png`, {
      fullPage: true,
      maxDiffPixelRatio: 0.05,
    });
  });
}

// ─── 项目页视口契约测试（T110） ──────────────────────────────────────
// 必需视口：1440x900, 1280x800, 1180x800, 2560x1440

for (const vp of viewports) {
  test(`项目页 @ ${vp.label} — 截图 + 可见性`, async ({ page }) => {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await page.goto('/projects');

    // 核心结构可见
    await expect(page.locator('.page-head')).toBeVisible();
    await expect(page.locator('.metric-grid')).toBeVisible();
    await expect(page.locator('.data-table')).toBeVisible();

    // 全屏截图用于视觉回归
    await expect(page).toHaveScreenshot(`projects-${vp.label.replace('x', '-')}.png`, {
      fullPage: true,
      maxDiffPixelRatio: 0.05,
    });
  });
}

// ─── 项目详情页视口契约测试（T124） ──────────────────────────────────
// 必需视口：1440x900, 1280x800, 1180x800, 2560x1440
// 使用 fixture project URL，不再依赖 PW_PROJECT_URL 环境变量。

const FIXTURE_PROJECT_URL = '/projects/test-hifi-project';

for (const vp of viewports) {
  test(`项目详情 @ ${vp.label} — 截图 + 可见性`, async ({ page }) => {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await page.goto(FIXTURE_PROJECT_URL, { waitUntil: 'domcontentloaded', timeout: 15000 });

    // 核心结构可见
    await expect(page.locator('.page-head')).toBeVisible();
    await expect(page.locator('.metric-grid')).toBeVisible();
    await expect(page.locator('.data-table')).toBeVisible();

    // 全屏截图用于视觉回归
    await expect(page).toHaveScreenshot(`project-detail-${vp.label.replace('x', '-')}.png`, {
      fullPage: true,
      maxDiffPixelRatio: 0.05,
    });
  });
}

// ─── 术语表视口契约测试（T166） ──────────────────────────────────────
// 必需视口：1440x900, 1280x800, 1180x800, 2560x1440

for (const vp of viewports) {
  test(`术语表 @ ${vp.label} — 截图 + 可见性`, async ({ page }) => {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await page.goto('/glossary');

    // 核心结构可见
    await expect(page.locator('.page-head')).toBeVisible();
    await expect(page.locator('.metric-grid')).toBeVisible();
    await expect(page.locator('.filter-card')).toBeVisible();
    await expect(page.locator('.card.section').first()).toBeVisible();
    await expect(page.locator('.data-table').first()).toBeVisible();

    // 全屏截图用于视觉回归
    await expect(page).toHaveScreenshot(`glossary-${vp.label.replace('x', '-')}.png`, {
      fullPage: true,
      maxDiffPixelRatio: 0.05,
    });
  });
}

// ─── 状态页视口契约测试（T180） ──────────────────────────────────────
// 必需视口：1440x900, 1280x800, 1180x800, 2560x1440
// 404 页可通过任意未映射 URL 触发。
// error.html 是服务端 500 模板，无法通过普通 URL 触发（会引发真实服务错误），
// 因此排除在 Playwright 截图检查之外。404 页已覆盖共享的 states.css 样式。

for (const vp of viewports) {
  test(`[UI-VISUAL-007] 404 页 @ ${vp.label} — 截图 + 可见性`, async ({ page }) => {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    // 导航到未映射 URL 触发 404
    await page.goto('/__test-404-not-found__');

    // 核心结构可见
    await expect(page.locator('.state-panel')).toBeVisible();
    await expect(page.locator('.state-panel__title')).toHaveText('Page Not Found');
    await expect(page.locator('.state-panel__links')).toBeVisible();

    // 全屏截图用于视觉回归
    await expect(page).toHaveScreenshot(`404-${vp.label.replace('x', '-')}.png`, {
      fullPage: true,
      maxDiffPixelRatio: 0.05,
    });
  });
}
