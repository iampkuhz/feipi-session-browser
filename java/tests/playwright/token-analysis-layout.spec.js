const { test, expect } = require('@playwright/test');

const detail = '/sessions/claude_code/hifi-viz-session-001';
const all = state => ({ freshInput: state, cacheRead: state, cacheWrite: state, output: state });
const measured = { fresh: 30, cacheRead: 60, cacheWrite: 0, output: 10, total: 100, provenance: all('provider_reported') };

async function assertPanel(page) {
  const panel = page.locator('#token-bar-popover');
  await expect(panel).toBeVisible();
  await expect(panel.locator('[data-token-part]')).toHaveCount(5);
  await expect(panel.locator('.token-component')).toHaveText(['Fresh', 'Cache Read', 'Cache Write', 'Output', 'Total']);
  const bounds = await panel.evaluate(element => {
    const box = element.getBoundingClientRect();
    return { left: box.left, right: box.right, top: box.top, bottom: box.bottom,
      width: innerWidth, height: innerHeight, overflow: element.scrollWidth > element.clientWidth + 1 };
  });
  expect(bounds.left).toBeGreaterThanOrEqual(0);
  expect(bounds.top).toBeGreaterThanOrEqual(0);
  expect(bounds.right).toBeLessThanOrEqual(bounds.width);
  expect(bounds.bottom).toBeLessThanOrEqual(bounds.height);
  expect(bounds.overflow).toBe(false);
  return panel;
}

test('Token 构成常显，桌面 Agent 对照保持左表右图', async ({ page }) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(detail);
  await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  const analysis = page.locator('#session-analysis');
  await expect(analysis.locator('[data-session-diagnostics]')).toBeVisible();
  const workbench = analysis.locator('[data-subagent-workbench]');
  const table = workbench.getByRole('table');
  const plot = workbench.locator('[data-subagent-timeline-panel]:visible .sd-token-round-chart');
  await expect(table).toBeVisible();
  await expect(plot).toBeVisible();
  await expect(plot.locator('.sd-token-round').first()).toBeVisible();
  const legend = workbench.locator('[data-subagent-timeline-panel]:visible small').filter({ hasText: 'Token 总量' });
  await expect(legend).toHaveText('柱：Token 总量　线：输入缓存命中率');
  await expect(workbench.locator('[data-subagent-timeline-panel]:visible small')).toHaveCount(1);
  const [tableBounds, plotBounds] = await Promise.all([
    workbench.locator('.sd-subagent-table-scroll').boundingBox(),
    workbench.locator('.sd-subagent-timeline-area').boundingBox(),
  ]);
  expect(tableBounds.x + tableBounds.width).toBeLessThanOrEqual(plotBounds.x + 1);
  expect(Math.abs(tableBounds.y - plotBounds.y)).toBeLessThanOrEqual(1);
  await page.evaluate(() => scrollTo(0, 0));
  const overview = test.info().outputPath('task57-overview-1440.png');
  await page.screenshot({ path: overview, mask: [page.locator('[data-session-file-text]')] });
  await test.info().attach('overview-synthetic-http', { path: overview, contentType: 'image/png' });
  const context = page.locator('.sd-token-composition');
  await expect(context.getByRole('heading', { name: 'Token 构成' })).toBeVisible();
  await expect(context.getByLabel('Token 构成用量')).toBeVisible();
  for (const width of [1440, 1024]) {
    await page.setViewportSize({ width, height: 1100 });
    await context.scrollIntoViewIfNeeded();
    const layout = await context.locator('.sd-context-budget').evaluate(element => {
      const items = [...element.children];
      return { columns: new Set(items.map(item => Math.round(item.getBoundingClientRect().left))).size,
        overflow: items.some(item => item.scrollWidth > item.clientWidth + 1),
        pageOverflow: document.documentElement.scrollWidth > innerWidth + 1,
        clipped: items.some(item => [...item.querySelectorAll('span,b')].some(label =>
          getComputedStyle(label).textOverflow === 'ellipsis')) };
    });
    expect(layout.columns).toBeGreaterThan(1);
    expect(layout.overflow).toBe(false);
    expect(layout.pageOverflow).toBe(false);
    expect(layout.clipped).toBe(false);
    const shot = test.info().outputPath(`task57-context-${width}.png`);
    await page.screenshot({ path: shot, mask: [page.locator('[data-session-file-text]')] });
    await test.info().attach(`context-${width}-synthetic-http`, { path: shot, contentType: 'image/png' });
  }
  expect(errors).toEqual([]);
});

test('shared popover covers Agent, Round and Trace without stealing desktop navigation', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(detail);
  await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  for (const selector of ['[data-subagent-row] [data-token-breakdown]', '.sd-token-round', '.tokenbar-wrap']) {
    const trigger = page.locator(selector).first();
    await trigger.scrollIntoViewIfNeeded();
    await trigger.hover();
    await assertPanel(page);
    await page.mouse.move(0, 0);
    await page.keyboard.press('Escape');
    await page.keyboard.press('Tab');
    await trigger.focus();
    await assertPanel(page);
    if (selector === '.sd-token-round') {
      const shot = test.info().outputPath('task57-round-tooltip.png');
      await page.locator('#token-bar-popover').screenshot({ path: shot });
      await test.info().attach('round-tooltip-synthetic-http', { path: shot, contentType: 'image/png' });
    }
    await page.keyboard.press('Escape');
    await expect(trigger).toHaveAttribute('aria-expanded', 'false');
  }
});

test('shared popover preserves the single-call parent and lazily loaded child navigation', async ({ page }) => {
  await page.goto(detail);
  await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  await page.locator('.sd-token-round').first().click();
  await expect(page).toHaveURL(/[?&]round=1(?:&|$)/);
  expect(new URL(page.url()).searchParams.has('tab')).toBe(false);
  await expect(page.locator('[data-trace-detail]').first()).toBeVisible();
  await expect(page.locator('#round-1-detail [data-timeline-item="assistant_text"] [data-token-breakdown]')).toHaveCount(0);
  const mainCall = page.locator('#round-1 .tokenbar-wrap[data-token-breakdown]');
  await page.keyboard.press('Tab');
  await mainCall.focus();
  await assertPanel(page);
  await page.keyboard.press('Escape');
  // The generic HTTP fixture has no child call. Inject only a synthetic child DTO, retaining the server snapshot identity.
  await page.route('**/round/4', async route => {
    const response = await route.fetch();
    const data = await response.json();
    data.round.calls.push({ callId: 'synthetic-token-child', scope: 'subagent', subagentId: 'synthetic-child', usage: measured });
    await route.fulfill({ response, json: data });
  });
  const analysis = page.locator('#session-analysis');
  await analysis.locator('.sd-token-round[data-round="4"]').click();
  await page.locator('#round-4-detail [data-action="toggle-subagent-rounds"]').click();
  const call = page.locator('#round-4-detail .sd-sub-tokenbar').first();
  await call.scrollIntoViewIfNeeded();
  await page.keyboard.press('Tab');
  await call.focus();
  await assertPanel(page);
});

for (const url of ['/sessions', '/projects', '/projects/test-hifi-project', '/dashboard']) {
  test(`shared breakdown entry at ${url}`, async ({ page }) => {
    if (url === '/dashboard') {
      // Keep a measured bucket in the visible UTC window regardless of the host date.
      await page.clock.setFixedTime(new Date('2026-01-01T12:00:00Z'));
      await page.route('**/api/dashboard/trends/tokens?*', async route => {
        const response = await route.fetch();
        await route.fulfill({ response, json: { points: [{ date: '2026-01-01', tokens: measured }] } });
      });
    }
    await page.goto(url);
    const trigger = page.locator(url === '/dashboard' ? '#token-trend-chart [data-token-breakdown]' :
      url === '/sessions' ? '.token-bar-trigger' : 'td.token-cell .tokenbar').first();
    await page.setViewportSize({ width: 1440, height: 900 });
    await trigger.scrollIntoViewIfNeeded();
    await trigger.hover();
    await assertPanel(page);
    await page.mouse.move(0, 0);
    await page.keyboard.press('Escape');
    await page.keyboard.press('Tab');
    await trigger.focus();
    await assertPanel(page);
    await page.keyboard.press('Escape');
  });
}

test('shared renderer distinguishes known, zero, unknown, unavailable, Partial and Estimated with long labels', async ({ page }) => {
  await page.goto(detail);
  await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  for (const [state, value, share] of [
    ['provider_reported', '0', '0%'],
    ['unknown', 'N/A', 'N/A'],
    ['unavailable', 'N/A', 'N/A'],
    ['mixed', 'N/A', 'N/A'],
    ['estimated', '≈0', '≈0%'],
  ]) {
    await page.evaluate(({ measured, state }) => {
      const tokens = { ...measured, cacheWrite: 0, provenance: { ...measured.provenance, cacheWrite: state } };
      const host = document.createElement('button');
      host.textContent = 'Synthetic measurement';
      host.dataset.tokenBreakdown = JSON.stringify({ tokens, ratio: true });
      document.querySelector('#synthetic-measurement')?.remove();
      host.id = 'synthetic-measurement';
      document.querySelector('main').prepend(host);
      TokenProvenance.bindTooltips(document);
    }, { measured, state });
    await page.locator('#synthetic-measurement').focus();
    const panel = await assertPanel(page);
    const row = panel.locator('[data-token-part="cacheWrite"]');
    await expect(row.locator('strong')).toHaveText(value);
    await expect(row.locator('.token-breakdown__share')).toHaveText(share);
    await expect(panel).toContainText(state === 'provider_reported' ? 'Cache Read / Input：66.7%' : 'Cache Read / Input：N/A');
    await panel.locator('.token-component').first().evaluate(element => {
      element.textContent = 'Synthetic long token category / 很长的分类名称与来源说明';
    });
    expect(await panel.evaluate(element => element.scrollWidth <= element.clientWidth + 1)).toBe(true);
    await page.keyboard.press('Escape');
  }
});
