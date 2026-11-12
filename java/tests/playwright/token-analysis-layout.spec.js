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

test('Context grid and progressive diagnostics retain all capabilities on real HTTP synthetic pages', async ({ page }) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(detail);
  await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  await expect(page.locator('[data-evidence-analysis]')).not.toHaveAttribute('open');
  await page.locator('[data-evidence-analysis] > summary').click();
  await expect(page.locator('.sd-kpis > .sd-kpi')).toHaveCount(3);
  const more = page.locator('[data-secondary-metrics]');
  await expect(more).not.toHaveAttribute('open');
  await more.locator(':scope > summary').focus();
  await page.keyboard.press('Enter');
  await expect(more.locator('[aria-label="Run Health"]')).toBeVisible();
  await expect(more.locator('[aria-label="Source Task Active"]')).toBeVisible();
  await more.locator(':scope > summary').click();
  const tools = page.locator('[data-tool-impact]');
  await expect(tools).not.toHaveAttribute('open');
  await tools.locator('summary').click();
  await expect(tools.locator('table')).toBeVisible();
  await expect(tools.locator('thead')).toContainText('本地估算');
  await tools.locator('summary').click();
  const issues = page.locator('[data-issue-details]');
  if (await issues.locator('[data-action="jump-round"]').count()) {
    await expect(issues).toHaveAttribute('open', '');
    await expect(issues.locator('[data-action="copy"]').first()).toBeVisible();
  }
  await page.evaluate(() => scrollTo(0, 0));
  const overview = test.info().outputPath('task57-overview-1440.png');
  await page.screenshot({ path: overview, mask: [page.locator('[data-session-file-text]')] });
  await test.info().attach('overview-synthetic-http', { path: overview, contentType: 'image/png' });
  const context = page.locator('.sd-diagnostic-card--context');
  await expect(context).toContainText('仅明确纳入且占比可用');
  await expect(context).toContainText('并非服务商精确统计');
  await expect(context).toContainText('Tool Results 是构成之外的本地估算');
  const columns = [];
  for (const width of [1440, 800, 390]) {
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
    columns.push(layout.columns);
    expect(layout.overflow).toBe(false);
    expect(layout.pageOverflow).toBe(false);
    expect(layout.clipped).toBe(false);
    if (width !== 800) {
      const shot = test.info().outputPath(`task57-context-${width}.png`);
      await page.screenshot({ path: shot, mask: [page.locator('[data-session-file-text]')] });
      await test.info().attach(`context-${width}-synthetic-http`, { path: shot, contentType: 'image/png' });
    }
  }
  expect(columns[0]).toBeGreaterThan(1);
  expect(columns[2]).toBe(1);
  expect(errors).toEqual([]);
});

for (const width of [1440, 390]) {
 test(`shared popover covers Agent, Round and Trace without stealing navigation at ${width}px`, async ({ page }) => {
  await page.setViewportSize({ width, height: 900 });
  await page.goto(detail);
  await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  await page.locator('[data-evidence-analysis] > summary').click();
  {
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
      if (selector === '.sd-token-round' && width === 1440) {
        const shot = test.info().outputPath('task57-round-tooltip.png');
        await page.locator('#token-bar-popover').screenshot({ path: shot });
        await test.info().attach('round-tooltip-synthetic-http', { path: shot, contentType: 'image/png' });
      }
      await page.keyboard.press('Escape');
      await expect(trigger).toHaveAttribute('aria-expanded', 'false');
    }
  }
 });
}

test('shared popover preserves main call and lazily loaded child navigation', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 900 });
  await page.goto(detail);
  await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  await page.locator('[data-evidence-analysis] > summary').click();
  await page.locator('.sd-token-round').first().click();
  await expect(page).toHaveURL(/tab=trace.*round=1/);
  await expect(page.locator('[data-trace-detail]').first()).toBeVisible();
  const mainCall = page.locator('#round-1-detail [data-timeline-item="assistant_text"] [data-token-breakdown]').first();
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
  await page.locator('.sd-token-round[data-round="4"]').click();
  await page.locator('#round-4-detail [data-action="toggle-subagent-rounds"]').click();
  const call = page.locator('#round-4-detail .sd-sub-tokenbar').first();
  await call.scrollIntoViewIfNeeded();
  await page.keyboard.press('Tab');
  await call.focus();
  await assertPanel(page);
});

for (const url of ['/sessions', '/projects', '/projects/test-hifi-project', '/dashboard']) {
  test(`shared breakdown entry at ${url}`, async ({ page }) => {
    await page.goto(url);
    const trigger = page.locator(url === '/dashboard' ? '#token-trend-chart [data-token-breakdown]' :
      url === '/sessions' ? '.token-bar-trigger' : 'td.token-cell .tokenbar').first();
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: 900 });
      await trigger.scrollIntoViewIfNeeded();
      await trigger.hover();
      await assertPanel(page);
      await page.mouse.move(0, 0);
      await page.keyboard.press('Escape');
      await page.keyboard.press('Tab');
      await trigger.focus();
      await assertPanel(page);
      await page.keyboard.press('Escape');
    }
  });
}

test('shared renderer distinguishes known, zero, unknown, unavailable, Partial and Estimated with long labels', async ({ page }) => {
  await page.goto(detail);
  await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  for (const [state, value, share] of [
    ['provider_reported', '0 · 服务商上报', '0.0%'],
    ['unknown', 'N/A · 来源未知', 'N/A'],
    ['unavailable', 'N/A · 未上报', 'N/A'],
    ['mixed', 'N/A · 部分数据', 'N/A'],
    ['estimated', '≈0 · 本地估算', '≈0.0%'],
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
    await page.setViewportSize({ width: 390, height: 500 });
    await page.locator('#synthetic-measurement').focus();
    await panel.locator('.token-component').first().evaluate(element => {
      element.textContent = 'Synthetic long token category / 很长的分类名称与来源说明';
    });
    expect(await panel.evaluate(element => element.scrollWidth <= element.clientWidth + 1)).toBe(true);
    await page.keyboard.press('Escape');
  }
});
