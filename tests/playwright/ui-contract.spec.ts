/**
 * ui-contract.spec.ts — 页面结构契约测试（可见性 + 响应式布局）
 *
 * 覆盖所有主要页面的多视口核心结构验证。
 * 视口：1440x900, 1280x800, 1180x800, 2560x1440
 */
import { test, expect, type Page } from '@playwright/test';

type VisibleCheck = {
  selector: string;
  label: string;
  first?: boolean;
  minCount?: number;
  text?: string | RegExp;
};

type PageContract = {
  url: string;
  name: string;
  checks: VisibleCheck[];
};

async function expectVisible(page: Page, check: VisibleCheck) {
  const locator = check.first ? page.locator(check.selector).first() : page.locator(check.selector);

  if (check.minCount !== undefined) {
    await expect(locator, `${check.label} count`).toHaveCount(check.minCount);
  }

  await expect(locator, `${check.label} visible`).toBeVisible({ timeout: 10000 });

  if (check.text !== undefined) {
    await expect(locator, `${check.label} text`).toHaveText(check.text);
  }
}

async function expectPageStructure(page: Page, checks: VisibleCheck[]) {
  await expect(page.locator('body')).toBeVisible();

  for (const check of checks) {
    await expectVisible(page, check);
  }
}

async function expectViewportFits(page: Page) {
  const metrics = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));

  expect(metrics.scrollWidth, 'page should not create horizontal overflow').toBeLessThanOrEqual(
    metrics.clientWidth + 2,
  );
}

// ─── 核心页面结构 ───────────────────────────────────────────────────

const pageContracts: PageContract[] = [
  {
    url: '/dashboard',
    name: 'dashboard',
    checks: [
      { selector: '.page-head', label: 'dashboard page head' },
      { selector: 'main', label: 'dashboard main content' },
      { selector: '.chart-card', label: 'dashboard chart card', first: true },
    ],
  },
  {
    url: '/sessions',
    name: 'sessions',
    checks: [
      { selector: '.page-head', label: 'sessions page head' },
      { selector: 'main', label: 'sessions main content' },
      { selector: '.filter-card', label: 'sessions filters' },
      { selector: '.data-table', label: 'sessions table' },
    ],
  },
  {
    url: '/projects',
    name: 'projects',
    checks: [
      { selector: '.page-head', label: 'projects page head' },
      { selector: '.metric-grid', label: 'projects metric grid' },
      { selector: '.data-table', label: 'projects table' },
    ],
  },
  {
    url: '/glossary',
    name: 'glossary',
    checks: [
      { selector: '.page-head', label: 'glossary page head' },
      { selector: '.metric-grid', label: 'glossary metric grid' },
      { selector: '.filter-card', label: 'glossary filters' },
      { selector: '.card.section', label: 'glossary section card', first: true },
      { selector: '.data-table', label: 'glossary table', first: true },
    ],
  },
];

for (const contract of pageContracts) {
  test(`${contract.name} 核心结构`, async ({ page }) => {
    await page.goto(contract.url);
    await expectPageStructure(page, contract.checks);
    await expectViewportFits(page);
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

const dashboardChecks = pageContracts.find((contract) => contract.name === 'dashboard')!.checks;

for (const vp of viewports) {
  test(`[UI-VISUAL-009] 仪表板 @ ${vp.label} — 结构 + 可见性`, async ({ page }) => {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await page.goto('/dashboard');

    await expectPageStructure(page, dashboardChecks);
    await expectViewportFits(page);
  });
}

// ─── 会话详情视口契约测试（T096） ────────────────────────────────────
// 必需视口：1440x900, 1280x800, 1180x800, 2560x1440
// 使用 fixture session URL，不再依赖 PW_SESSION_URL 环境变量。

const FIXTURE_SESSION_URL = '/sessions/claude_code/hifi-viz-session-001';
const sessionDetailChecks: VisibleCheck[] = [
  { selector: '.sd-hero', label: 'session detail hero', first: true },
  { selector: '.sd-tabs', label: 'session detail tabs' },
  { selector: '[data-trace-panel]', label: 'session trace panel' },
];

for (const vp of viewports) {
  test(`[UI-SD-015] 会话详情 @ ${vp.label} — 结构 + 可见性`, async ({ page }) => {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await page.goto(FIXTURE_SESSION_URL, { waitUntil: 'domcontentloaded', timeout: 15000 });

    await expectPageStructure(page, sessionDetailChecks);
    await expectViewportFits(page);
  });
}

// ─── 项目页视口契约测试（T110） ──────────────────────────────────────
// 必需视口：1440x900, 1280x800, 1180x800, 2560x1440

const projectChecks = pageContracts.find((contract) => contract.name === 'projects')!.checks;

for (const vp of viewports) {
  test(`项目页 @ ${vp.label} — 结构 + 可见性`, async ({ page }) => {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await page.goto('/projects');

    await expectPageStructure(page, projectChecks);
    await expectViewportFits(page);
  });
}

// ─── 项目详情页视口契约测试（T124） ──────────────────────────────────
// 必需视口：1440x900, 1280x800, 1180x800, 2560x1440
// 使用 fixture project URL，不再依赖 PW_PROJECT_URL 环境变量。

const FIXTURE_PROJECT_URL = '/projects/test-hifi-project';
const projectDetailChecks: VisibleCheck[] = [
  { selector: '.page-head', label: 'project detail page head' },
  { selector: '.metric-grid', label: 'project detail metric grid' },
  { selector: '.data-table', label: 'project detail table' },
];

for (const vp of viewports) {
  test(`项目详情 @ ${vp.label} — 结构 + 可见性`, async ({ page }) => {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await page.goto(FIXTURE_PROJECT_URL, { waitUntil: 'domcontentloaded', timeout: 15000 });

    await expectPageStructure(page, projectDetailChecks);
    await expectViewportFits(page);
  });
}

// ─── 术语表视口契约测试（T166） ──────────────────────────────────────
// 必需视口：1440x900, 1280x800, 1180x800, 2560x1440

const glossaryChecks = pageContracts.find((contract) => contract.name === 'glossary')!.checks;

for (const vp of viewports) {
  test(`术语表 @ ${vp.label} — 结构 + 可见性`, async ({ page }) => {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await page.goto('/glossary');

    await expectPageStructure(page, glossaryChecks);
    await expectViewportFits(page);
  });
}

// ─── 状态页视口契约测试（T180） ──────────────────────────────────────
// 必需视口：1440x900, 1280x800, 1180x800, 2560x1440
// 404 页可通过任意未映射 URL 触发。
// error.html 是服务端 500 模板，无法通过普通 URL 触发（会引发真实服务错误），
// 因此排除在 Playwright 检查之外。404 页已覆盖共享的 states.css 样式。

const notFoundChecks: VisibleCheck[] = [
  { selector: '.state-panel', label: '404 panel' },
  { selector: '.state-panel__title', label: '404 title', text: 'Page Not Found' },
  { selector: '.state-panel__links', label: '404 links' },
];

for (const vp of viewports) {
  test(`[UI-VISUAL-007] 404 页 @ ${vp.label} — 结构 + 可见性`, async ({ page }) => {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    // 导航到未映射 URL 触发 404。
    await page.goto('/__test-404-not-found__');

    await expectPageStructure(page, notFoundChecks);
    await expectViewportFits(page);
  });
}
