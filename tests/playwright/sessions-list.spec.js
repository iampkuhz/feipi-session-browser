/**
 * sessions-list.spec.js — 会话列表页 Playwright 截图与交互检查
 */
import { test, expect } from '@playwright/test';

test.describe('会话列表页', () => {
  test('[UI-SESSIONS-001] 核心页面加载与结构', async ({ page }) => {
    await page.goto('/sessions');
    await expect(page.locator('body')).toBeVisible();

    // 页面标题
    await expect(page.locator('.page-head h1')).toHaveText('Sessions');

    // 筛选栏
    await expect(page.locator('#session-search')).toBeVisible();
    await expect(page.locator('#filter-agent')).toBeVisible();
    await expect(page.locator('#filter-model')).toBeVisible();
    await expect(page.locator('#filter-project')).toBeVisible();

    // 数据表格
    await expect(page.locator('.data-table')).toBeVisible();

    // 分页（仅在有数据时显示）
    const totalCount = await page.locator('.page-status').first().textContent();
    if (totalCount && /\d+ sessions?/.test(totalCount)) {
      const pagination = page.locator('.pagination');
      await expect(pagination).toBeVisible();
    }
  });

  test('[UI-SESSIONS-015] 1440x900 API-first 列表布局 smoke', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/sessions');
    await expect(page.locator('body')).toBeVisible();
    await expect(page.getByText('Loading sessions')).toHaveCount(0, { timeout: 10000 });
    await expect(page.locator('.sessions-table-card')).toBeVisible();
    await expect(page.locator('[data-api-rows="/api/sessions/rows"]')).toBeVisible();
    const firstDataRow = page.locator('.data-table tbody tr[data-action="row"]').first();
    await expect(firstDataRow).toBeVisible({ timeout: 10000 });
    await expect(firstDataRow.locator(':scope > td')).toHaveCount(13);
    const firstRowHeight = await firstDataRow.evaluate((row) => row.getBoundingClientRect().height);
    expect(firstRowHeight, 'API 渲染出的表格行应保持 table row 结构，不能因 <td> 被剥离而撑高').toBeLessThanOrEqual(70);
    const viewportWidth = await page.evaluate(() => document.documentElement.clientWidth);
    const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    expect(scrollWidth, 'API 渲染后不应产生横向页面滚动').toBeLessThanOrEqual(viewportWidth + 2);
  });

  test('[UI-SESSIONS-002] 数据表格包含全部列头', async ({ page }) => {
    await page.goto('/sessions');
    const headers = page.locator('.data-table th');
    const count = await headers.count();
    expect(count).toBeGreaterThanOrEqual(8);

    const headerTexts = await headers.allTextContents();
    const combined = headerTexts.join(' ').toLowerCase();
    expect(combined).toContain('session');
    expect(combined).toContain('project');
    expect(combined).toContain('agent');
    expect(combined).toContain('model');
    expect(combined).toContain('tokens');
    expect(combined).toContain('rounds');
    expect(combined).toContain('tools');
    expect(combined).toContain('duration');
    expect(combined).toContain('updated');
  });

  test('[UI-SESSIONS-005] 排序按钮可点击且生效', async ({ page }) => {
    await page.goto('/sessions');
    const sortButtons = page.locator('.c-data-table__sort[data-action="sort"]');
    const count = await sortButtons.count();
    expect(count).toBeGreaterThanOrEqual(4);

    // 点击 tokens 排序按钮，验证 URL 变化
    const tokensSort = page.locator('.c-data-table__sort[data-sort-key="tokens"]');
    if (await tokensSort.isVisible()) {
      const currentUrl = page.url();
      await tokensSort.click();
      await page.waitForURL(/sort=/);
      expect(page.url()).toContain('sort=tokens');
    }
  });

  test('[UI-SESSIONS-008] 会话行包含 data 属性', async ({ page }) => {
    await page.goto('/sessions');
    const rows = page.locator('tr[data-action="row"]');
    const count = await rows.count();
    if (count > 0) {
      const firstRow = rows.first();
      await expect(firstRow).toHaveAttribute('data-agent');
      await expect(firstRow).toHaveAttribute('data-model');
      await expect(firstRow).toHaveAttribute('data-session-id');
    }
  });

  test('[UI-SESSIONS-004] agent 徽章渲染正确', async ({ page }) => {
    await page.goto('/sessions');
    const badges = page.locator('.data-table .badge');
    const count = await badges.count();
    if (count > 0) {
      // 至少一个徽章应有 cc、cx 或 qd 类
      const firstBadge = badges.first();
      const className = await firstBadge.getAttribute('class');
      expect(className).toMatch(/(cc|cx|qd)/);
    }
  });

  test('[UI-SESSIONS-003][UI-SESSIONS-016][DATA-PRESENTER-013] token 条包含四段', async ({ page }) => {
    await page.goto('/sessions');
    const tokenbars = page.locator('.tokenbar');
    const count = await tokenbars.count();
    if (count > 0) {
      const segments = tokenbars.first().locator('.tokenbar-seg');
      const segCount = await segments.count();
      expect(segCount).toBe(4);
    }
  });

  test('[UI-SESSIONS-007][UI-SESSIONS-011][UI-INTERACTION-002] next 一次到 page 2 且使用 JSON rows API', async ({ page }) => {
    // 暂停首屏 rows 请求，确定性覆盖加载期间的禁用态，仍由真实 API 返回分页数据。
    let releaseInitialRows;
    const initialRowsReleased = new Promise((resolve) => { releaseInitialRows = resolve; });
    await page.route('**/api/sessions/rows**', async (route) => {
      const requestedPage = new URL(route.request().url()).searchParams.get('page') || '1';
      if (requestedPage === '1') await initialRowsReleased;
      await route.continue();
    });
    const nextBtn = page.locator('.pagination [data-action="next-page"]');
    try {
      await page.goto('/sessions?page=1');
      await expect(nextBtn).toBeVisible();
      await expect(nextBtn).toBeDisabled();
    } finally {
      releaseInitialRows();
    }
    await expect(nextBtn, 'fixture must contain enough sessions for pagination').toBeEnabled();

    const pageInput = page.locator('.page-input');
    await expect(pageInput).toHaveValue('1');

    // 单击必须仅前进一页，JSON 分页同步更新 DOM 和 history.pushState。
    const page2Response = page.waitForResponse((response) => {
      const url = new URL(response.url());
      return url.pathname === '/api/sessions/rows'
        && url.searchParams.get('page') === '2'
        && (response.request().headers().accept || '').includes('application/json');
    }, { timeout: 10000 });
    await Promise.all([
      page2Response,
      nextBtn.click(),
    ]);

    await expect(pageInput).toHaveValue('2', { timeout: 10000 });
    await expect.poll(() => new URL(page.url()).searchParams.get('page'), {
      message: 'one next click must settle on page=2',
      timeout: 10000,
    }).toBe('2');
    expect(new URL(page.url()).searchParams.get('page')).not.toBe('3');

    // Assert session rows are non-empty (data loaded)
    const rows = page.locator('tr[data-action="row"], .sessions-row');
    await expect(rows.first()).toBeVisible({ timeout: 10000 });

    // Assert prev button is enabled (we are not on page 1)
    const prevBtn = page.locator('.pagination [data-action="prev-page"]');
    await expect(prevBtn).toBeEnabled();
  });

  test('[UI-SESSIONS-006] 筛选表单提交并改变 URL', async ({ page }) => {
    await page.goto('/sessions');
    const searchInput = page.locator('#session-search');
    if (await searchInput.isVisible()) {
      await searchInput.fill('test-query-t082');
      // 点击应用
      const applyBtn = page.locator('button[data-action="apply"], input[type="submit"]');
      if (await applyBtn.count() > 0) {
        await applyBtn.first().click();
        await page.waitForURL(/q=/);
        expect(page.url()).toContain('q=test-query-t082');
      }
    }
  });
});
