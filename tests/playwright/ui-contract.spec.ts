/**
 * ui-contract.spec.ts — 页面视觉契约测试（截图 + 可见性）
 *
 * 覆盖所有主要页面的多视口截图和核心结构验证。
 */
import { test, expect } from '@playwright/test';

// ─── 核心页面截图 ───────────────────────────────────────────────────

const pages = [
  ['/dashboard', 'dashboard'],
  ['/sessions', 'sessions'],
  ['/projects', 'projects'],
  ['/agents', 'agents'],
  ['/glossary', 'glossary'],
];

for (const [url, name] of pages) {
  test(`${name} 核心截图`, async ({ page }) => {
    await page.goto(url);
    await expect(page.locator('body')).toBeVisible();
    await expect(page).toHaveScreenshot(`${name}-1440.png`, { fullPage: true, maxDiffPixelRatio: 0.05 });
  });
}

// ─── 仪表板视口契约测试（06-validation-contract） ────────────────────
// 必需视口：1440x900, 1280x800, 1180x800

const viewports = [
  { width: 1440, height: 900, label: '1440x900' },
  { width: 1280, height: 800, label: '1280x800' },
  { width: 1180, height: 800, label: '1180x800' },
] as const;

for (const vp of viewports) {
  test(`仪表板 @ ${vp.label} — 截图 + 可见性`, async ({ page }) => {
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
// 必需视口：1440x900, 1280x800, 1180x800
// 需要运行服务并包含索引数据。设置 PW_SESSION_URL 指向有效会话 URL，否则跳过。

function resolveSessionUrl(): string | null {
  const direct = process.env.PW_SESSION_URL;
  if (direct) return direct;
  return null;
}

for (const vp of viewports) {
  test(`会话详情 @ ${vp.label} — 截图 + 可见性`, async ({ page }) => {
    const sessionUrl = resolveSessionUrl();
    if (!sessionUrl) {
      console.log('未设置 PW_SESSION_URL；跳过会话详情视口测试。');
      return;
    }

    await page.setViewportSize({ width: vp.width, height: vp.height });
    await page.goto(sessionUrl);

    // 核心结构可见：hero、标签页、trace 表格
    await expect(page.locator('.hero').first()).toBeVisible();
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
// 必需视口：1440x900, 1280x800, 1180x800

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
// 必需视口：1440x900, 1280x800, 1180x800
// 设置 PW_PROJECT_URL 指向有效项目 URL，否则跳过。

function resolveProjectUrl(): string | null {
  const direct = process.env.PW_PROJECT_URL;
  if (direct) return direct;
  return null;
}

for (const vp of viewports) {
  test(`项目详情 @ ${vp.label} — 截图 + 可见性`, async ({ page }) => {
    const projectUrl = resolveProjectUrl();
    if (!projectUrl) {
      console.log('未设置 PW_PROJECT_URL；跳过项目详情视口测试。');
      return;
    }

    await page.setViewportSize({ width: vp.width, height: vp.height });
    await page.goto(projectUrl);

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

// ─── Agent 列表页视口契约测试（T138） ────────────────────────────────
// 必需视口：1440x900, 1280x800, 1180x800

for (const vp of viewports) {
  test(`Agent 列表 @ ${vp.label} — 截图 + 可见性`, async ({ page }) => {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await page.goto('/agents');

    // 核心结构可见
    await expect(page.locator('.page-head')).toBeVisible();
    await expect(page.locator('.metric-grid')).toBeVisible();
    await expect(page.locator('#agents-table.data-table')).toBeVisible();

    // 全屏截图用于视觉回归
    await expect(page).toHaveScreenshot(`agents-${vp.label.replace('x', '-')}.png`, {
      fullPage: true,
      maxDiffPixelRatio: 0.05,
    });
  });
}

// ─── 术语表视口契约测试（T166） ──────────────────────────────────────
// 必需视口：1440x900, 1280x800, 1180x800

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

// ─── Agent 详情页视口契约测试（T152） ─────────────────────────────────
// 必需视口：1440x900, 1280x800, 1180x800
// 设置 PW_AGENT_URL 指向有效 Agent URL（如 /agents/claude_code），否则跳过。

function resolveAgentUrl(): string | null {
  const direct = process.env.PW_AGENT_URL;
  if (direct) return direct;
  return null;
}

for (const vp of viewports) {
  test(`Agent 详情 @ ${vp.label} — 截图 + 可见性`, async ({ page }) => {
    const agentUrl = resolveAgentUrl();
    if (!agentUrl) {
      console.log('未设置 PW_AGENT_URL；跳过 Agent 详情视口测试。');
      return;
    }

    await page.setViewportSize({ width: vp.width, height: vp.height });
    await page.goto(agentUrl);

    // 核心结构可见
    await expect(page.locator('.header')).toBeVisible();
    await expect(page.locator('.metric-grid')).toBeVisible();
    await expect(page.locator('.data-table').first()).toBeVisible();

    // 全屏截图用于视觉回归
    await expect(page).toHaveScreenshot(`agent-detail-${vp.label.replace('x', '-')}.png`, {
      fullPage: true,
      maxDiffPixelRatio: 0.05,
    });
  });
}

// ─── 状态页视口契约测试（T180） ──────────────────────────────────────
// 必需视口：1440x900, 1280x800, 1180x800
// 404 页可通过任意未映射 URL 触发。
// error.html 是服务端 500 模板，无法通过普通 URL 触发（会引发真实服务错误），
// 因此排除在 Playwright 截图检查之外。404 页已覆盖共享的 states.css 样式。

for (const vp of viewports) {
  test(`404 页 @ ${vp.label} — 截图 + 可见性`, async ({ page }) => {
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
