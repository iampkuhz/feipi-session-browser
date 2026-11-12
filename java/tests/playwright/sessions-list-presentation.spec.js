import { test, expect } from '@playwright/test';

const now = new Date('2026-06-06T12:00:00Z');
const provenance = Object.fromEntries(['freshInput', 'cacheRead', 'cacheWrite', 'output']
  .map(key => [key, 'provider_reported']));
const tokens = { fresh: 2500, cacheRead: 5000, cacheWrite: 1000, output: 1500, total: 10000, provenance };
const partial = { activeTaskSeconds: 582, activeTaskPrecision: 'partial', activeTaskBasis: 'main_task_windows',
  completedTaskCount: 2, incompleteTaskCount: 1 };
const longTitle = '修复合成订单服务的缓存失效与重复扣款，并补充并发回归测试 — Synthetic checkout cache invalidation and concurrent payment regression';

async function syntheticRows(page, overrides) {
  await page.clock.setFixedTime(now);
  await page.route('**/api/sessions/rows**', async route => {
    const response = await route.fetch();
    const body = await response.json();
    body.rows = overrides.map((row, index) => ({
      ...body.rows[0], tokens, title: `Synthetic task ${index}`, displayTitle: `Synthetic task ${index}`,
      sessionId: `synthetic-${index}`, sessionKey: `codex:synthetic-${index}`, agent: 'codex',
      tools: 100, failedTools: 0, timing: { activeTaskPrecision: 'unknown' },
      updatedAt: new Date(now.getTime() - 150000).toISOString(), ...row,
    }));
    body.pagination = { ...body.pagination, totalItems: body.rows.length, totalPages: body.rows.length ? 1 : 0,
      hasNext: false, hasPrevious: false };
    body.state = body.rows.length ? { kind: 'ready' }
      : { kind: 'empty', title: 'No indexed sessions yet', message: 'Scan a synthetic source to get started.' };
    await route.fulfill({ response, json: body });
  });
}

test('Sessions titles, merged Tools and Partial explanation remain distinct and keyboard accessible', async ({ page }) => {
  await syntheticRows(page, [
    { displayTitle: longTitle, failedTools: 5, timing: partial, gitBranch: 'feature/synthetic-checkout-cache-regression' },
    { displayTitle: 'Add synthetic checkout validation', gitBranch: 'main' },
    { displayTitle: 'synthetic-2', failedTools: null },
    { displayTitle: '  ', tools: null, failedTools: null },
    { displayTitle: null, title: null, tools: null, failedTools: 5,
      timing: { activeTaskPrecision: 'partial', activeTaskSeconds: null } },
    { displayTitle: 'Synthetic measured zero', tools: 0, timing: { activeTaskPrecision: 'measured', activeTaskSeconds: 0 } },
  ]);
  await page.goto('/sessions');
  const rows = page.locator('.sessions-row');
  await expect(rows).toHaveCount(6);
  await expect(rows.locator('.col-tools')).toHaveText(['100(5)', '100', '100(?)', '—(?)', '—(5)', '0']);
  await expect(rows.nth(2).locator('.col-tools')).toHaveAttribute('aria-label', '100 tool calls; failures unknown');
  await expect(rows.locator('.session-link')).toHaveText([
    longTitle, 'Add synthetic checkout validation', 'Untitled session', 'Untitled session', 'Untitled session', 'Synthetic measured zero',
  ]);
  await expect(rows.first().locator('.session-link')).toHaveAttribute('title', longTitle);
  await expect(rows.first().locator('.title-sub .mono')).toHaveAttribute('title', 'synthetic-0');
  await expect(rows.locator('[data-task-active]')).toHaveText(['9m 42s Partial', 'N/A', 'N/A', 'N/A', 'N/A', '0s']);
  const badge = rows.first().getByRole('button', { name: 'Partial' });
  await badge.focus();
  await page.keyboard.press('Enter');
  const help = page.locator('#sessions-task-active-help');
  await expect(help).toBeVisible();
  await expect(help).toContainText('incomplete or cannot be paired');
  await expect(help).toContainText('overlaps counted once');
  await expect(help).toContainText('not the full session duration or model inference time');
  await expect(page).toHaveURL(/\/sessions$/);
  await page.keyboard.press('Escape');
  await expect(help).toBeHidden();
  for (const width of [1920, 1440, 800]) {
    await page.setViewportSize({ width, height: 1000 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
    const layout = await rows.first().evaluate(row => {
      const link = row.querySelector('.session-link');
      const sub = row.querySelector('.title-sub');
      return { titleBottom: link.getBoundingClientRect().bottom, metaTop: sub.getBoundingClientRect().top,
        font: parseFloat(getComputedStyle(link).fontSize), metaFont: parseFloat(getComputedStyle(sub).fontSize),
        titleHeight: link.getBoundingClientRect().height, lineHeight: parseFloat(getComputedStyle(link).lineHeight) };
    });
    expect(layout.titleBottom).toBeLessThanOrEqual(layout.metaTop + 1);
    expect(layout.font).toBeGreaterThan(layout.metaFont);
    expect(layout.titleHeight).toBeLessThanOrEqual(layout.lineHeight * 2 + 1);
    expect(layout.titleHeight).toBeGreaterThan(layout.lineHeight * 1.5);
  }
  await page.setViewportSize({ width: 1920, height: 1000 });
  const screenshot = test.info().outputPath('sessions-synthetic-after.png');
  await page.screenshot({ path: screenshot });
  await test.info().attach('sessions-synthetic-after', { path: screenshot, contentType: 'image/png' });
});

test('Tokens share aligned category/value-source/share rows and keep zero distinct from unknown', async ({ page }) => {
  await syntheticRows(page, [{}, { tokens: { ...tokens, fresh: 2000, cacheRead: 7000, cacheWrite: 0, output: 1000,
    provenance: { ...provenance, cacheRead: 'unknown' } } }]);
  await page.goto('/sessions');
  const triggers = page.getByRole('button', { name: 'Token breakdown', exact: true });
  const panel = page.locator('#token-bar-popover');
  for (const width of [1440, 800, 390]) {
    await page.mouse.move(0, 0);
    await page.setViewportSize({ width, height: 1000 });
    await triggers.first().scrollIntoViewIfNeeded();
    await triggers.first().hover();
    await expect(panel).toBeVisible();
    await expect(panel.locator('.token-breakdown__row .token-component')).toHaveText(['Fresh', 'Cache Read', 'Cache Write', 'Output', 'Total']);
    await expect(panel.locator('.token-breakdown__row')).toHaveText(['Fresh2,500 · 服务商上报25.0%', 'Cache Read5,000 · 服务商上报50.0%', 'Cache Write1,000 · 服务商上报10.0%', 'Output1,500 · 服务商上报15.0%', 'Total10,000 · 服务商上报100.0%']);
    await expect(panel).not.toContainText('Shown total');
    await expect(panel.locator('.tokenbar')).toHaveCount(0);
    await expect(panel).toContainText('服务商上报');
    const bounds = await panel.evaluate(element => {
      const box = element.getBoundingClientRect();
      const definitions = Array.from(element.querySelectorAll('.token-breakdown__row'));
      return { left: box.left, right: box.right, width: window.innerWidth,
        overflows: element.scrollWidth > element.clientWidth + 1,
        aligned: definitions.every(dd => {
          const children = Array.from(dd.children).map(child => child.getBoundingClientRect());
          return children.every(rect => Math.abs((rect.top + rect.bottom) / 2 - (children[0].top + children[0].bottom) / 2) <= 1);
        }) };
    });
    expect(bounds.left).toBeGreaterThanOrEqual(0);
    expect(bounds.right).toBeLessThanOrEqual(bounds.width);
    expect(bounds.overflows).toBe(false);
    expect(bounds.aligned).toBe(true);
    await page.keyboard.press('Escape');
  }
  // resize 会关闭弹框；先等真实事件送达，再建立本段键盘 focus 的交互前置条件。
  const resized = page.evaluate(() => new Promise(resolve => {
    window.addEventListener('resize', () => resolve(), { once: true });
  }));
  await page.setViewportSize({ width: 1440, height: 1000 });
  await resized;
  await triggers.nth(1).focus();
  await expect(panel).toBeVisible();
  await expect(panel.locator('.token-breakdown__row').nth(0)).toHaveText('Fresh2,000 · 服务商上报≈20.0%');
  await expect(panel.locator('.token-breakdown__row').nth(1)).toHaveText('Cache Read7,000 · 来源未知N/A');
  await expect(panel.locator('.token-breakdown__row').nth(2)).toHaveText('Cache Write0 · 服务商上报≈0.0%');
  await expect(panel.locator('.token-breakdown__row').nth(1).locator('.token-breakdown__share')).toHaveText('N/A');
  const screenshot = test.info().outputPath('tokens-synthetic-after.png');
  await panel.screenshot({ path: screenshot });
  await test.info().attach('tokens-synthetic-after', { path: screenshot, contentType: 'image/png' });
  await page.keyboard.press('Escape');
  await expect(triggers.nth(1)).toHaveAttribute('aria-expanded', 'false');
});

test('Updated uses one decimal in each unit and preserves exact timestamp as disclosure', async ({ page }) => {
  const ages = [12.5, 150, 4680, 216000];
  await syntheticRows(page, ages.map(age => ({ updatedAt: new Date(now.getTime() - age * 1000).toISOString() })));
  await page.goto('/sessions');
  await expect(page.locator('.sessions-row .col-updated')).toHaveText(['12.5s ago', '2.5m ago', '1.3h ago', '2.5d ago']);
  await expect(page.locator('.sessions-row .col-updated').nth(1)).toHaveAttribute('title', '2026-06-06T11:57:30.000Z');
});

test('Tools and Updated sorting follow raw API values, retaining search and page size', async ({ page }) => {
  for (const key of ['tools', 'updated']) {
    await page.goto(`/sessions?q=Synthetic&agent=claude_code&page_size=50&sort=${key}&dir=desc`);
    await expect(page.locator('.sessions-row').first()).toBeVisible();
    const responsePromise = page.waitForResponse(response => new URL(response.url()).pathname === '/api/sessions/rows');
    await page.locator(`a[data-sort-key="${key}"]`).click();
    const response = await responsePromise;
    const body = await response.json();
    const request = new URL(response.url()).searchParams;
    expect(request.get('sort')).toBe(key);
    expect(request.get('dir')).toBe('asc');
    expect(request.get('page_size')).toBe('50');
    expect(request.get('q')).toBe('Synthetic');
    expect(body.rows.length).toBeGreaterThan(1);
    const values = body.rows.map(row => key === 'tools' ? row.tools : Date.parse(row.updatedAt));
    expect(values).toEqual([...values].sort((a, b) => a - b));
    await expect(page.locator('.sessions-row')).toHaveCount(body.rows.length);
    expect(await page.locator('.sessions-row').evaluateAll(rows => rows.map(row => row.dataset.sessionId)))
      .toEqual(body.rows.map(row => row.sessionId));
  }
});

test('removed list sorts normalize to Updated and the empty table spans all remaining columns', async ({ page }) => {
  for (const sort of ['failure', 'duration']) {
    await page.goto(`/sessions?sort=${sort}&dir=asc`);
    await expect(page.locator('.sessions-row').first()).toBeVisible();
    await expect(page).toHaveURL(/\/sessions$/);
    await expect(page.locator('input[name="sort"]')).toHaveValue(/ended-at|updated/);
    await expect(page.locator('input[name="dir"]')).toHaveValue('desc');
  }
  await syntheticRows(page, []);
  await page.goto('/sessions');
  await expect(page.locator('.empty-state')).toContainText('No indexed sessions yet');
  await expect(page.locator('.empty-state').locator('..')).toHaveAttribute('colspan', '11');
});

test('session title and merged Tools cell both retain Session Detail navigation', async ({ page }) => {
  for (const target of ['.session-link', '.col-tools']) {
    await page.goto('/sessions');
    const row = page.locator('.sessions-row').first();
    await expect(row).toBeVisible();
    const detail = await row.getAttribute('data-detail-url');
    await row.locator(target).click();
    await expect(page).toHaveURL(url => url.pathname === detail);
    await expect(page.locator('.session-detail-page')).toBeVisible();
  }
});
