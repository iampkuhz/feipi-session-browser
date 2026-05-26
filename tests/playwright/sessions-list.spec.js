/**
 * sessions-list.spec.js — 会话列表页 Playwright 截图与交互检查
 */
import { test, expect } from '@playwright/test';

test.describe('会话列表页', () => {
  test('核心页面加载与结构', async ({ page }) => {
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

  test('1440x900 截图', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/sessions');
    await expect(page.locator('body')).toBeVisible();
    await expect(page).toHaveScreenshot('sessions-1440x900.png', {
      fullPage: true,
      maxDiffPixelRatio: 0.05,
    });
  });

  test('数据表格包含全部列头', async ({ page }) => {
    await page.goto('/sessions');
    const headers = page.locator('.data-table th');
    const count = await headers.count();
    expect(count).toBeGreaterThanOrEqual(8);

    const headerTexts = await headers.allTextContents();
    const combined = headerTexts.join(' ').toLowerCase();
    expect(combined).toContain('title');
    expect(combined).toContain('project');
    expect(combined).toContain('agent');
    expect(combined).toContain('model');
    expect(combined).toContain('tokens');
    expect(combined).toContain('rounds');
    expect(combined).toContain('tools');
    expect(combined).toContain('duration');
    expect(combined).toContain('updated');
  });

  test('排序按钮可点击且生效', async ({ page }) => {
    await page.goto('/sessions');
    const sortButtons = page.locator('.sort-button[data-action="sort"]');
    const count = await sortButtons.count();
    expect(count).toBeGreaterThanOrEqual(4);

    // 点击 tokens 排序按钮，验证 URL 变化
    const tokensSort = page.locator('.sort-button[data-sort-key="tokens"]');
    if (await tokensSort.isVisible()) {
      const currentUrl = page.url();
      await tokensSort.click();
      await page.waitForURL(/sort=/);
      expect(page.url()).toContain('sort=tokens');
    }
  });

  test('会话行包含 data 属性', async ({ page }) => {
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

  test('agent 徽章渲染正确', async ({ page }) => {
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

  test('token 条包含四段', async ({ page }) => {
    await page.goto('/sessions');
    const tokenbars = page.locator('.tokenbar');
    const count = await tokenbars.count();
    if (count > 0) {
      const segments = tokenbars.first().locator('.tokenbar-seg');
      const segCount = await segments.count();
      expect(segCount).toBe(4);
    }
  });

  test('next 一次到 page 2', async ({ page }) => {
    // Regression test for S-09: duplicate JS listeners caused next click
    // to jump from page 1 to page 3 instead of page 2.
    await page.goto('/sessions?page=1');
    await expect(page.locator('body')).toBeVisible();

    const nextBtn = page.locator('.pagination [data-action="next-page"]');
    await expect(nextBtn).toBeVisible();

    // Skip gracefully when fixture is too small for pagination
    const isDisabled = await nextBtn.isDisabled();
    if (isDisabled) {
      console.log('[skip] next-page button is disabled — fixture too small for pagination.');
      test.skip();
    }

    // Click next once
    await nextBtn.click();

    // Wait for URL to reflect page=2 (not page=3)
    await page.waitForURL(/page=2/, { timeout: 10000 });

    // Assert page=2 in URL
    expect(page.url()).toMatch(/page=2/);

    // Assert page input value is 2
    await expect(page.locator('.page-input')).toHaveValue('2');

    // Assert session rows are non-empty (data loaded)
    const rows = page.locator('tr[data-action="row"], .sessions-row');
    await expect(rows.first()).toBeVisible({ timeout: 10000 });

    // Assert prev button is enabled (we are not on page 1)
    const prevBtn = page.locator('.pagination [data-action="prev-page"]');
    await expect(prevBtn).toBeEnabled();
  });

  test('筛选表单提交并改变 URL', async ({ page }) => {
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
