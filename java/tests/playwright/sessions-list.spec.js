/**
 * sessions-list.spec.js — 会话列表页 Playwright 截图与交互检查
 */
import { test, expect } from '@playwright/test';

test.describe('会话列表页', () => {
  test('retains a valid URL page size outside the presets and uses compact billion units', async ({ page }) => {
    await page.route('**/api/sessions/summary?*', async (route) => {
      const response = await route.fetch();
      const data = await response.json();
      const provenance = Object.fromEntries(['freshInput', 'cacheRead', 'cacheWrite', 'output']
        .map((key) => [key, 'provider_reported']));
      data.tokens = { fresh: 4_200_000_000, cacheRead: 0, cacheWrite: 0, output: 0,
        total: 4_200_000_000, provenance };
      await route.fulfill({ response, json: data });
    });
    await page.goto('/sessions?page_size=1&sort=tokens&dir=desc');
    const first = page.locator('.sessions-row').first();
    await expect(first).toBeVisible();
    const firstId = await first.getAttribute('data-session-id');
    await expect(page.locator('[data-action="page-size"]')).toHaveValue('1', { timeout: 2000 });
    await page.getByRole('button', { name: 'Next page' }).click();
    await expect(page).toHaveURL(/page_size=1/);
    await expect(first).not.toHaveAttribute('data-session-id', firstId);
    await expect(page.locator('.page-head__stats')).toContainText('4.2B');
    await expect(page.locator('.pagination')).toContainText(/of \d+ · \d+ sessions/);
  });

  test('rounds separate legacy groups, observed calls, partial and unknown boundaries', async ({ page }) => {
    const cases = [
      ['legacy', 2, 70, null, '2 groups', /Legacy index/],
      ['observed', 70, 70, 70, '70', /^Observed model call boundaries$/],
      ['partial', 7, 9, 5, '5+', /unconfirmed boundaries/],
      ['unknown', 4, 4, 0, '—', /boundaries unknown/],
    ];
    await page.route('**/api/sessions/rows**', async route => {
      const response = await route.fetch();
      const body = await response.json();
      const sample = body.rows[0];
      body.rows = cases.map(([name, rounds, llmCalls, modelCallCount]) => ({
        ...sample, sessionKey: 'codex:' + name, sessionId: name, agent: 'codex',
        rounds, llmCalls, modelCallCount,
      }));
      await route.fulfill({ response, json: body });
    });
    await page.goto('/sessions');
    for (const [name, , , , value, evidence] of cases) {
      const cell = page.locator(`.sessions-row[data-session-id="${name}"] .col-rounds`);
      await expect(cell).toHaveText(value);
      await expect(cell).toHaveAttribute('title', evidence);
    }
  });

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
    const rowsResponsePromise = page.waitForResponse((response) => new URL(response.url()).pathname === '/api/sessions/rows');
    await page.goto('/sessions');
    await expect(page.locator('body')).toBeVisible();
    await expect(page.getByText('Loading sessions')).toHaveCount(0, { timeout: 10000 });
    await expect(page.locator('.sessions-table-card')).toBeVisible();
    await expect(page.locator('[data-api-rows="/api/sessions/rows"]')).toBeVisible();
    const firstDataRow = page.locator('.data-table tbody tr[data-action="row"]').first();
    await expect(firstDataRow).toBeVisible({ timeout: 10000 });
    await expect(firstDataRow.locator(':scope > td')).toHaveCount(11);
    const disclosure = firstDataRow.locator('.token-total__status');
    await expect(disclosure).toBeVisible();
    await expect(disclosure).toContainText(/Partial|Unknown/);
    const clipping = await firstDataRow.evaluate((row) => {
      const cell = row.querySelector('.token-cell');
      const inside = (inner, outer) => inner.top >= outer.top - 1 && inner.bottom <= outer.bottom + 1
        && inner.left >= outer.left - 1 && inner.right <= outer.right + 1;
      return Array.from(cell.querySelectorAll('.token-total__value, .token-total__status')).some((element) => {
        const range = document.createRange();
        range.selectNodeContents(element);
        return element.scrollWidth > element.clientWidth + 1 || element.scrollHeight > element.clientHeight + 1
          || Array.from(range.getClientRects()).some((rect) => !inside(rect, cell.getBoundingClientRect()) || !inside(rect, row.getBoundingClientRect()));
      });
    });
    expect(clipping, 'Partial/Unknown 来源说明与 token 值必须完整保留在单元格和行边界内').toBe(false);
    const rowsResponse = await rowsResponsePromise;
    expect(rowsResponse.ok()).toBe(true);
    const rowsApi = await rowsResponse.json();
    const reported = rowsApi.rows.find((row) => ['freshInput', 'cacheRead', 'cacheWrite', 'output']
      .every((key) => row.tokens?.provenance?.[key] === 'provider_reported'));
    expect(reported, 'Synthetic fixture 必须提供显式四段 provider_reported 的 compact 正例').toBeDefined();
    const compactRow = page.locator('.data-table tbody tr[data-action="row"]').filter({ has: page.locator(`[data-session-link][href="${reported.detailUrl}"]`) });
    await expect(compactRow.locator(':scope > td')).toHaveCount(11);
    const compactRowHeight = await compactRow.evaluate((row) => row.getBoundingClientRect().height);
    expect(compactRowHeight, '完整 reported 的 API 行应保持 compact table row 结构，不能因 <td> 被剥离而撑高').toBeLessThanOrEqual(70);
    await test.info().attach('session-row-layout', { contentType: 'application/json', body: JSON.stringify({
      disclosureRowHeight: await firstDataRow.evaluate((row) => row.getBoundingClientRect().height),
      compactSessionId: reported.sessionId, compactRowHeight, compactProvenance: reported.tokens.provenance, clipping,
    }) });
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
    expect(headerTexts.map(text => text.trim())).toEqual([
      'Session', 'Project', 'Agent', 'Model', 'Tokens', 'Rounds', 'Tools', 'Subagents', 'Task Active', 'Created', 'Updated',
    ]);
    await expect(page.locator('[data-sort-key="duration"], [data-sort-key="failure"]')).toHaveCount(0);
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

  test('[UI-SESSIONS-003][UI-SESSIONS-016][DATA-PRESENTER-013] Token 分项可查，色条不伪造缺失分项', async ({ page }) => {
    await page.goto('/sessions');
    const cell = page.locator('.sessions-row .token-cell').first();
    await expect(cell.locator('.token-total__value')).toBeVisible();
    await expect(cell.locator('details')).toHaveCount(0);
    const trigger = cell.getByRole('button', { name: 'Token breakdown' });
    const panel = page.locator('#token-bar-popover');
    await trigger.hover();
    await expect(panel.locator('.token-breakdown__row .token-component')).toHaveText(['Fresh', 'Cache Read', 'Cache Write', 'Output', 'Total']);
    await expect(panel.locator('.token-composition > .tokenbar')).toHaveCount(0);
    await expect(panel.locator('[data-token-part]')).toHaveCount(5);
    await page.keyboard.press('Escape');
    await expect(panel).toBeHidden();
    await trigger.press('Enter');
    await expect(trigger).toHaveAttribute('aria-expanded', 'true');
    await expect(panel.locator('.token-composition')).toContainText('占比以当前总量为分母');
    await page.keyboard.press('Escape');
    await expect(trigger).toHaveAttribute('aria-expanded', 'false');
    await page.locator('#session-search').focus();
    await trigger.focus();
    await expect(panel).toBeVisible();
    await page.keyboard.press('Escape');
    expect(await cell.locator('.tokenbar-seg').evaluateAll(nodes =>
      nodes.every(node => parseFloat(node.style.getPropertyValue('--segment-width')) > 0))).toBe(true);
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
      await expect(page.locator('.sessions-loading-cell')).toHaveAttribute('colspan', '11');
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

  test('[UI-SESSIONS-017] 非常用 page_size 翻页与跳页保留实际大小和筛选，显式改大小回第一页', async ({ page }) => {
    const filters = { q: 'Synthetic', agent: 'claude_code', sort: 'tokens', dir: 'desc' };
    const expectedResponse = await page.request.get(`/api/sessions/rows?${new URLSearchParams({ ...filters, page_size: '100' })}`);
    expect(expectedResponse.ok()).toBe(true);
    const expectedRows = (await expectedResponse.json()).rows;
    expect(expectedRows.length, '真实 synthetic fixture 必须提供至少三条匹配会话').toBeGreaterThanOrEqual(3);
    const rows = page.locator('.data-table tbody tr[data-action="row"]');
    const hiddenSize = page.locator('#session-filter-form input[name="page_size"]');
    const pageInput = page.locator('.pagination [data-action="page-input"]');

    /** 验证真实 rows API、地址栏及页面都使用相同分页、排序和筛选状态。 */
    async function assertPage(response, expectedPage, expectedSize) {
      expect(response.ok()).toBe(true);
      const requested = new URL(response.url());
      const body = await response.json();
      await test.info().attach(`paging-${expectedPage}-${expectedSize}`, {
        contentType: 'application/json',
        body: JSON.stringify({ query: requested.search, pagination: body.pagination, sessionIds: body.rows.map((row) => row.sessionId) }),
      });
      expect(requested.searchParams.get('page_size')).toBe(String(expectedSize));
      expect(Number(requested.searchParams.get('page') || 1)).toBe(expectedPage);
      for (const [key, value] of Object.entries(filters)) expect(requested.searchParams.get(key)).toBe(value);
      expect(body.pagination.page).toBe(expectedPage);
      expect(body.pagination.pageSize).toBe(expectedSize);
      const expectedIds = expectedRows.slice((expectedPage - 1) * expectedSize, expectedPage * expectedSize).map((row) => row.sessionId);
      expect(body.rows.map((row) => row.sessionId)).toEqual(expectedIds);
      await expect(rows).toHaveCount(expectedIds.length);
      for (let index = 0; index < expectedIds.length; index += 1) {
        await expect(rows.nth(index)).toHaveAttribute('data-session-id', expectedIds[index]);
      }
      await expect(hiddenSize).toHaveValue(String(expectedSize));
      await expect(page.locator('.pagination [data-action="page-size"]')).toHaveValue(String(expectedSize));
      await expect(pageInput).toHaveValue(String(expectedPage));
      await expect.poll(() => {
        const current = new URL(page.url()).searchParams;
        return ['page_size', 'page', ...Object.keys(filters)].map((key) => current.get(key) || (key === 'page' ? '1' : ''));
      }).toEqual([String(expectedSize), String(expectedPage), ...Object.values(filters)]);
    }

    /** 只等待真实分页响应，不用 page_size 约束等待条件掩盖丢参错误。 */
    function rowsResponse() {
      return page.waitForResponse((response) => new URL(response.url()).pathname === '/api/sessions/rows');
    }

    let responsePromise = rowsResponse();
    await page.goto(`/sessions?${new URLSearchParams({ ...filters, page_size: '1' })}`);
    await assertPage(await responsePromise, 1, 1);

    responsePromise = rowsResponse();
    await page.locator('.pagination [data-action="next-page"]').click();
    await assertPage(await responsePromise, 2, 1);
    expect(expectedRows[1].sessionId).not.toBe(expectedRows[0].sessionId);

    responsePromise = rowsResponse();
    await page.locator('.pagination [data-action="prev-page"]').click();
    await assertPage(await responsePromise, 1, 1);

    responsePromise = rowsResponse();
    await pageInput.fill('3');
    await pageInput.press('Enter');
    await assertPage(await responsePromise, 3, 1);

    responsePromise = rowsResponse();
    await page.locator('.pagination [data-action="page-size"]').selectOption('50');
    await assertPage(await responsePromise, 1, 50);
  });

  test('[UI-SESSIONS-006] 筛选表单提交并改变 URL', async ({ page }) => {
    await page.goto('/sessions');
    const searchInput = page.locator('#session-search');
    await expect(page.locator('.sessions-row').first()).toBeVisible();
    await searchInput.fill('test-query-t082-no-match');
    await expect(page).toHaveURL(/q=test-query-t082-no-match/);
    await expect(page.locator('.empty-state')).toContainText('No sessions match');
    await expect(page.locator('.empty-state').locator('..')).toHaveAttribute('colspan', '11');
    await page.locator('.empty-state [data-action="clear"]').click();
    await expect(page.locator('.sessions-row').first()).toBeVisible();
    await expect(searchInput).toHaveValue('');
  });
});
