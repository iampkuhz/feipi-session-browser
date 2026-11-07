const { test, expect } = require('@playwright/test');

const SESSION_PATH = '/sessions/claude_code/hifi-viz-session-001';
const LONG_SESSION_PATH = '/sessions/claude_code/long-session-001';
const ATTRIBUTION_VIEWPORTS = [
  { width: 1440, height: 900 },
  { width: 2560, height: 1440 },
];
const BROWSER_WARNINGS = new WeakMap();

// Mock the payload, not its index identity: all sibling resources retain the live snapshot stamp.
async function fulfillIndexedJson(route, json) {
  const response = await route.fetch();
  return route.fulfill({ response, json });
}


test.describe('unbound legacy generation consistency regressions', () => {
  // These synthetic G1/G2 tests intentionally exercise the pre-SSR, unbound batch protocol.
  // The separate real-page SSR boundary cases retain the document stamp without alteration.
  test.beforeEach(async ({ page }) => {
    await page.route('**/*', async route => {
      if (!route.request().isNavigationRequest() || route.request().resourceType() !== 'document') return route.continue();
      const response = await route.fetch();
      const body = (await response.text()).replace(/(<body\b[^>]*?)\sdata-index-generation=(['"])[^'"]*\2/i, '$1');
      return route.fulfill({ response, body });
    });
  });
  async function openSnapshotProbe(page) {
    await page.goto(SESSION_PATH);
    await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
    await page.evaluate(() => {
      document.body.replaceChildren();
      // This probe deliberately exercises unbound synthetic G1/G2 batches.
      document.body.removeAttribute('data-index-generation');
      const main = document.createElement('main');
      for (const key of ['a', 'b']) {
        const node = document.createElement('p');
        node.id = `probe-${key}`;
        main.appendChild(node);
      }
      document.body.appendChild(main);
      window.probeSnapshot = window.IndexSnapshot.create();
      window.probeLoad = () => window.probeSnapshot.load(['a', 'b'].map((key) => ({
        key: `probe/${key}`, url: `/api/snapshot-probe/${key}`,
        apply(data) {
          if (key === 'b' && window.probeThrow) { window.probeThrow = false; throw new Error('fixture DOM failure'); }
          document.getElementById(`probe-${key}`).textContent = `${key}-${data.value}`;
        },
      })));
    });
  }

  test('a named snapshot cannot downgrade to a partial headerless batch', async ({ page }) => {
    let phase = 'G1';
    await page.route('**/api/snapshot-probe/*', async (route) => {
      const failed = phase === 'missing' && route.request().url().endsWith('/b');
      await route.fulfill({ status: failed ? 500 : 200, headers: phase === 'missing' ? {} : { 'x-session-index-generation': phase }, json: { value: phase } });
    });
    await openSnapshotProbe(page);
    await page.evaluate(() => window.probeLoad());
    phase = 'missing';
    await page.evaluate(() => window.probeLoad());
    await expect(page.locator('#probe-a')).toHaveText('a-G1');
    await expect(page.locator('#probe-b')).toHaveText('b-G1');
    await expect(page.locator('body')).toHaveAttribute('data-index-generation', 'G1');
    await expect(page.locator('[data-snapshot-error]').first()).toBeVisible();
    phase = 'G2';
    await page.locator('[data-snapshot-error] button').first().click();
    await expect(page.locator('#probe-a')).toHaveText('a-G2');
    await expect(page.locator('#probe-b')).toHaveText('b-G2');
  });

  test('an apply failure hides the whole batch until a successful full retry', async ({ page }) => {
    let phase = 'G1';
    let failRequest = false;
    await page.route('**/api/snapshot-probe/*', (route) => route.fulfill({ status: failRequest && route.request().url().endsWith('/b') ? 500 : 200, headers: { 'x-session-index-generation': phase }, json: { value: phase } }));
    await openSnapshotProbe(page);
    await page.evaluate(() => window.probeLoad());
    await page.evaluate(() => {
      window.probeMain = document.querySelector('main');
      window.probeClicks = 0;
      window.probeRestores = 0;
      window.probeMain.addEventListener('click', () => { window.probeClicks += 1; });
      window.addEventListener('index-snapshot-restored', () => { window.probeRestores += 1; });
    });
    phase = 'G2';
    await page.evaluate(() => { window.probeThrow = true; return window.probeLoad().catch((error) => { window.probeUnhandled = error.message; }); });
    await expect(page.locator('main')).toBeHidden();
    await expect(page.locator('[data-snapshot-batch-error]')).toContainText('fixture DOM failure');
    await expect(page.locator('body')).not.toHaveAttribute('data-index-generation', 'G2');
    expect(await page.evaluate(() => window.probeUnhandled)).toBeUndefined();
    failRequest = true;
    await page.locator('[data-snapshot-batch-error] button').click();
    await expect(page.locator('[data-snapshot-batch-error]')).toContainText('Snapshot recovery requires every resource');
    await expect(page.locator('main')).toBeHidden();
    failRequest = false;
    await page.locator('[data-snapshot-batch-error] button').click();
    await expect(page.locator('main')).toBeVisible();
    await expect(page.locator('#probe-a')).toHaveText('a-G2');
    await expect(page.locator('#probe-b')).toHaveText('b-G2');
    await expect(page.locator('body')).toHaveAttribute('data-index-generation', 'G2');
    expect(await page.evaluate(() => window.probeMain === document.querySelector('main'))).toBe(true);
    await page.locator('#probe-a').click();
    expect(await page.evaluate(() => window.probeClicks)).toBe(1);
    await expect.poll(() => page.evaluate(() => window.probeRestores)).toBe(1);
  });

  const cases = [
    { path: '/', prefix: '/api/dashboard/', primary: '/summary', delayed: '/trends/tokens', field: 'sessionCount' },
    { path: '/projects', prefix: '/api/projects/', primary: '/summary', delayed: '/active-filters', field: 'projectCount' },
    { path: '/projects/test-hifi-project', prefix: '/api/projects/test-hifi-project/', primary: '/summary', delayed: '/sessions/rows', field: 'totalSessions' },
    { path: '/sessions', prefix: '/api/sessions/', primary: '/summary', delayed: '/options', field: 'totalCount' },
    { path: SESSION_PATH, prefix: '/api/sessions/claude_code/hifi-viz-session-001/', primary: '/meta', delayed: '/diagnostics', field: 'title' },
  ];
  for (const item of cases) {
    test(`stages and retries a mixed generation batch on ${item.path}`, async ({ page }) => {
      const calls = new Map();
      let release;
      let primaryReady;
      const barrier = new Promise((resolve) => { release = resolve; });
      const primary = new Promise((resolve) => { primaryReady = resolve; });
      await page.route('**/api/**', async (route) => {
        const pathname = new URL(route.request().url()).pathname;
        if (!pathname.startsWith(item.prefix)) return route.continue();
        const count = (calls.get(pathname) || 0) + 1;
        calls.set(pathname, count);
        const response = await route.fetch();
        const data = await response.json();
        const isPrimary = pathname === item.prefix.replace(/\/$/, '') + item.primary;
        if (isPrimary) data[item.field] = item.field === 'title' ? `generation-marker-${count}` : 987653 + count;
        const delayed = count === 1 && pathname.endsWith(item.delayed);
        if (delayed) await barrier;
        await route.fulfill({ response, headers: { ...response.headers(), 'x-session-index-generation': count === 1 && !delayed ? 'G1' : 'G2' }, json: data });
        if (isPrimary && count === 1) primaryReady();
      });
      await page.goto(item.path, { waitUntil: 'domcontentloaded' });
      await primary;
      await expect(page.locator('body')).not.toContainText(item.field === 'title' ? 'generation-marker-1' : /987,?654/);
      release();
      await expect(page.locator('body')).toHaveAttribute('data-index-generation', 'G2');
      await expect(page.locator('body')).toContainText(item.field === 'title' ? 'generation-marker-2' : /987,?655/);
      expect([...calls.values()].every((count) => count === 2)).toBe(true);
    });
  }

  test('bounds automatic retries and exposes a manual full-batch retry', async ({ page }) => {
    let calls = 0;
    let stable = false;
    await page.route('**/api/sessions/claude_code/hifi-viz-session-001/*', async (route) => {
      calls += 1;
      const stamp = stable ? 'stable' : `G${calls}`;
      const response = await route.fetch();
      await route.fulfill({ response, headers: { ...response.headers(), 'x-session-index-generation': stamp } });
    });
    await page.goto(SESSION_PATH);
    await expect(page.locator('[data-resource-error]').first()).toBeVisible();
    expect(calls).toBe(12);
    await expect(page.locator('body')).not.toHaveAttribute('data-session-api-hydrated', 'true');
    stable = true;
    await page.locator('[data-resource-error] button').first().click();
    await expect(page.locator('body')).toHaveAttribute('data-index-generation', 'stable');
    await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
    expect(calls).toBe(16);
  });

  test('project pagination refreshes all six resources when the index changes', async ({ page }) => {
    const calls = new Map();
    await page.route('**/api/projects/test-hifi-project/**', async (route) => {
      const url = new URL(route.request().url());
      calls.set(url.pathname, (calls.get(url.pathname) || 0) + 1);
      const response = await route.fetch();
      await route.fulfill({ response, headers: { ...response.headers(), 'x-session-index-generation': url.searchParams.get('page') === '2' ? 'G2' : 'G1' } });
    });
    await page.goto('/projects/test-hifi-project?page_size=1');
    await expect(page.locator('body')).toHaveAttribute('data-index-generation', 'G1');
    await page.locator('[data-action="next-page"]').click();
    await expect(page.locator('body')).toHaveAttribute('data-index-generation', 'G2');
    await expect(page).toHaveURL(/page=2/);
    expect(calls.size).toBe(6);
    expect([...calls.values()]).toEqual([2, 2, 2, 2, 2, 2]);
  });

  test('same-generation resource retries are pinned and a 409 refreshes the full batch', async ({ page }) => {
    const calls = new Map();
    let changed = false;
    let expectedHeader = '';
    await page.route('**/api/sessions/claude_code/hifi-viz-session-001/*', async (route) => {
      const pathname = new URL(route.request().url()).pathname;
      const count = (calls.get(pathname) || 0) + 1;
      calls.set(pathname, count);
      if (pathname.endsWith('/metrics') && count === 1) return route.fulfill({ status: 500, headers: { 'x-session-index-generation': 'G1' }, json: { error: 'fixture failure' } });
      if (pathname.endsWith('/metrics') && count === 2) {
        expectedHeader = route.request().headers()['x-session-index-generation'];
        changed = true;
        return route.fulfill({ status: 409, headers: { 'x-session-index-generation': 'G2' }, json: { code: 'index_generation_changed' } });
      }
      const response = await route.fetch();
      await route.fulfill({ response, headers: { ...response.headers(), 'x-session-index-generation': changed ? 'G2' : 'G1' } });
    });
    await page.goto(SESSION_PATH);
    await expect(page.locator('[data-resource-error="metrics"]')).toContainText('HTTP 500');
    await expect(page.locator('[data-trace-round-row]').first()).toBeVisible();
    await page.locator('[data-resource-error="metrics"] button').click();
    await expect(page.locator('body')).toHaveAttribute('data-index-generation', 'G2');
    await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
    expect(expectedHeader).toBe('G1');
    expect([...calls.entries()].filter(([path]) => !path.endsWith('/metrics')).every(([, count]) => count === 2)).toBe(true);
  });
});

test.describe('real detail evidence regressions', () => {
  for (const hasContent of [false, true]) {
    test(`health does not infer success from ${hasContent ? 'issue-free content' : 'missing content'}`, async ({ page }) => {
      await page.route('**/api/sessions/**/metrics', async (route) => {
        const response = await route.fetch();
        const data = await response.json();
        if (!hasContent) Object.assign(data, { roundCount: 0, userMessages: 0, assistantMessages: 0, toolCalls: 0, subagents: 0, parity: {} });
        await route.fulfill({ response, json: data });
      });
      await page.route('**/api/sessions/**/diagnostics', async (route) => {
        const response = await route.fetch();
        const data = await response.json();
        Object.assign(data, { anomalyCount: 0, parity: { runHealth: 'Completed', issueRounds: 0, attributionGaps: 0, payloadGaps: 0, failedTools: 0, toolCalls: 0 } });
        await route.fulfill({ response, json: data });
      });
      if (!hasContent) await page.route('**/api/sessions/**/rounds', async (route) => {
        const response = await route.fetch();
        await route.fulfill({ response, json: { ...(await response.json()), roundCount: 0, rounds: [] } });
      });
      await page.goto(SESSION_PATH);
      await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
      const health = page.locator('.sd-kpi[aria-label="Run Health"]');
      await expect(health).not.toContainText('Completed');
      await expect(health.locator('.sd-kpi__value')).toHaveText(hasContent ? 'No issue signals detected' : 'Unknown');
      await expect(health).toContainText('Attribution Gaps N/A');
      await expect(page.locator('[data-issue-strip]')).not.toContainText('All rounds completed successfully');
      if (hasContent) {
        await expect(health).toContainText('Failed Tools 0');
        await expect(health).toContainText('Payload Gaps 0');
        await expect(page.locator('.sd-kpi[aria-label="Workload"] .sd-kpi__value')).not.toHaveText('N/A');
      }
      if (!hasContent) {
        await expect(page.locator('.sd-kpi[aria-label="Workload"] .sd-kpi__value')).toHaveText('N/A');
        await expect(health).toContainText('Failed Tools N/A');
        await expect(health).toContainText('Payload Gaps N/A');
      }
    });
  }
});

test.beforeEach(async ({ page }) => {
  const warnings = [];
  BROWSER_WARNINGS.set(page, warnings);
  page.on('console', (message) => {
    if (message.type() === 'warning') warnings.push(message.text());
  });
});

test.afterEach(async ({ page }) => {
  expect(BROWSER_WARNINGS.get(page) || [], 'browser console warnings must be empty').toEqual([]);
});

async function openHydratedSession(page, path = SESSION_PATH) {
  const response = await page.goto(path, { waitUntil: 'domcontentloaded', timeout: 30_000 });
  expect(response && response.ok(), `fixture URL must return HTTP success: ${path}`).toBe(true);
  await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true', { timeout: 10_000 });
  await expect(page.locator('[data-trace-round-row]').first()).toBeVisible({ timeout: 10_000 });
}

for (const scenario of ['subagent-only', 'mixed', 'unowned-fallback']) {
  test(`round member pages render tool ownership exactly once: ${scenario}`, async ({ page }) => {
    const child = { callId: 'fixture-child', scope: 'subagent', subagentId: 'fixture-agent', responseToolCallIds: ['fixture-response-tool'] };
    const main = { callId: 'fixture-main', scope: 'main' };
    const tools = [
      { toolCallId: 'fixture-declared-tool', declaredByCallId: child.callId, name: 'Read', inputPreview: 'synthetic child declaration' },
      { toolCallId: 'fixture-response-tool', name: 'Read', inputPreview: 'synthetic response edge' },
    ];
    const calls = [child];
    if (scenario === 'mixed') {
      calls.unshift(main);
      tools.push({ toolCallId: 'fixture-main-tool', declaredByCallId: main.callId, name: 'Read', inputPreview: 'synthetic main declaration' });
    }
    if (scenario === 'unowned-fallback') {
      tools.push({ toolCallId: 'fixture-unowned-tool', name: 'Read', inputPreview: 'synthetic ownerless fallback' });
    }
    await openHydratedSession(page);
    const generation = await page.locator('body').getAttribute('data-index-generation');
    expect(generation).toBeTruthy();
    await page.route('**/api/sessions/*/*/round/*', async (route) => {
      const url = new URL(route.request().url());
      const next = url.searchParams.get('cursor') === 'fixture-members';
      // The body and cursor are synthetic; only the current document's generation is inherited.
      await route.fulfill({ headers: { 'x-session-index-generation': generation }, json: {
        round: next
          ? { calls, tools, toolCallIds: tools.map((tool) => tool.toolCallId) }
          : { calls: [{ callId: 'fixture-first-page', scope: 'main' }], tools: [], toolCallIds: [] },
        membersPaged: true, total: calls.length + 1,
        nextCursor: next ? null : 'fixture-members', toolsComplete: true,
      } });
    });
    const row = page.locator('[data-trace-round-row]').first();
    await row.locator('[data-action="toggle-round"]').click();
    await expect(row).toHaveAttribute('data-detail-loaded', 'true');
    const detail = page.locator('[data-trace-detail]').first();
    await detail.locator('[data-content-pagination="round-members"] button').click();
    await expect(detail.locator('[data-content-pagination="round-members"]')).toContainText(`${calls.length + 1} / ${calls.length + 1} loaded`);
    const expectedIds = tools.map((tool) => tool.toolCallId).sort();
    await expect.poll(() => detail.locator('[data-tool-call-id]').evaluateAll((nodes) =>
      nodes.map((node) => node.getAttribute('data-tool-call-id')).sort())).toEqual(expectedIds);
    for (const tool of tools) {
      await expect(detail.locator(`[data-tool-call-id="${tool.toolCallId}"]`)).toHaveCount(1);
    }
    await expect(detail.locator('[data-subagent-block] [data-tool-call-id]')).toHaveCount(2);
    if (scenario === 'unowned-fallback') {
      await expect(detail.locator('[data-tool-call-id="fixture-unowned-tool"]')).toBeVisible();
    }
  });
}

async function openAttribution(page, kind) {
  const button = page.locator(`[data-attribution-path*="/${kind}"]:visible`).first();
  await expect(button).toHaveText(kind === 'request' ? 'Request' : 'Response');
  const path = await button.getAttribute('data-attribution-path');
  const pending = page.waitForResponse((response) => response.url().endsWith(path));
  await button.click();
  const response = await pending;
  expect(response.ok()).toBe(true);
  const payload = await response.json();
  const explicitId = new URL(response.url()).searchParams.get('call_id');
  const callId = payload.data.callId;
  expect(callId).toBeTruthy();
  if (explicitId) expect(callId).toBe(explicitId);
  expect(payload.kind).toBe(`llm.${kind}_attribution`);
  const modal = page.locator('dialog.payload-modal');
  await expect(modal).toBeVisible();
  const disclosure = modal.locator(`[data-payload-attribution="${kind}"]`);
  await expect(disclosure).toHaveAttribute('data-attribution-call', callId);
  await expect(disclosure.locator('summary')).toHaveText(kind === 'request' ? '输入归因' : '输出归因');
  await expect(disclosure.locator('.sd-kv').first()).toBeHidden();
  await disclosure.locator('summary').press('Enter');
  await expect(disclosure.locator('.sd-kv').first()).toBeVisible();
  return { modal, disclosure, payload };
}

async function installDetailedAttributionRoute(page) {
  await page.route(/\/api\/sessions\/[^/]+\/[^/]+\/attribution\/\d+\/\d+\/(request|response)(?:\?|$)/, async (route) => {
    const url = new URL(route.request().url());
    const kind = url.pathname.split('/').at(-1);
    const response = await route.fetch();
    expect(response.ok()).toBe(true);
    const actual = await response.json();
    await route.fulfill({ response, json: {
      kind: `llm.${kind}_attribution`,
      data: {
        callId: actual.data.callId,
        callKey: 'fixture-attribution-key',
        scope: 'main',
        freshInputTokens: 120,
        outputTokens: 90,
        cacheReadTokens: 30,
        cacheWriteTokens: 0,
        requestToolResultCount: 3,
        responseToolCallCount: 2,
        provenance: {
          freshInput: 'provider_reported', output: 'provider_reported',
          cacheRead: 'provider_reported', cacheWrite: 'provider_reported',
        },
      },
    } });
  });
}

test('[UI-SD-036] real Java attribution API returns the current call identity and usage', async ({ page }) => {
  await openHydratedSession(page);
  const callIds = [];
  for (const kind of ['request', 'response']) {
    const { modal, disclosure, payload } = await openAttribution(page, kind);
    callIds.push(payload.data.callId);
    expect(payload.data.model).toBeTruthy();
    for (const field of [
      'totalTokens', 'freshInputTokens', 'outputTokens', 'cacheReadTokens', 'cacheWriteTokens',
      'requestToolResultCount', 'responseToolCallCount',
    ]) {
      expect(typeof payload.data[field], `Java API field ${field} must be numeric`).toBe('number');
    }
    await expect(disclosure).toHaveAttribute('data-attribution-scope', payload.data.scope);
    await expect(disclosure.locator('.sd-kv').first()).toContainText(payload.data.callKey || payload.data.callId);
    await expect(modal.locator('[data-payload-attribution]')).toHaveCount(1);
    await page.keyboard.press('Escape');
    await expect(modal).toBeHidden();
  }
  expect(callIds[0]).toBe(callIds[1]);
});

for (const viewport of ATTRIBUTION_VIEWPORTS) {
  for (const kind of ['request', 'response']) {
    const contractId = kind === 'request' ? 'UI-SD-037' : 'UI-SD-038';
    test(`[${contractId}] ${kind} attribution shows only its exact counters @ ${viewport.width}x${viewport.height}`, async ({ page }) => {
      await installDetailedAttributionRoute(page);
      await page.setViewportSize(viewport);
      await openHydratedSession(page);
      const { modal, disclosure } = await openAttribution(page, kind);
      const tokens = kind === 'request'
        ? [['新鲜输入', '120'], ['缓存读取', '30'], ['缓存写入', '0']]
        : [['输出', '90']];
      await expect(disclosure.locator('.sd-kv > span:first-child')).toHaveText([
        '调用', ...tokens.map(([label]) => label), '计量依据',
        kind === 'request' ? '已记录工具结果' : '已记录工具指令',
      ]);
      await expect(disclosure.locator('.sd-kv > span:last-child')).toHaveText([
        'fixture-attribution-key · 主会话', ...tokens.map(([, value]) => value),
        '提供方报告', kind === 'request' ? '3' : '2',
      ]);
      const bounds = await modal.boundingBox();
      const grid = await disclosure.locator('.sd-attribution-summary-grid').boundingBox();
      expect(grid.x).toBeGreaterThanOrEqual(bounds.x - 2);
      expect(grid.x + grid.width).toBeLessThanOrEqual(bounds.x + bounds.width + 2);
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(viewport.width + 2);
      await page.keyboard.press('Escape');
      await expect(modal).toBeHidden();
    });
  }
}

async function toggleAlignment(page, visibleOnly = false) {
  return page.locator(
    visibleOnly
      ? '[data-trace-round-row]:not(.is-filtered-out) [data-action="toggle-round"]'
      : '[data-trace-round-row] [data-action="toggle-round"]',
  ).evaluateAll((toggles) => {
    const positions = toggles.slice(0, 50).map((toggle) => Math.round(toggle.getBoundingClientRect().left));
    return {
      count: positions.length,
      spread: positions.length ? Math.max(...positions) - Math.min(...positions) : 0,
    };
  });
}

async function expectNoAlignmentRegression(page, baseline, label, visibleOnly = false) {
  const current = await toggleAlignment(page, visibleOnly);
  expect(current.count, `${label}: fixture must expose round toggles`).toBeGreaterThan(0);
  expect(current.spread - baseline, `${label}: alignment regression must be <=2px`).toBeLessThanOrEqual(2);
}

test('[UI-SD-040] trace toggles remain aligned through interactions', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1100 });
  await openHydratedSession(page);

  const baseline = await toggleAlignment(page);
  expect(baseline.count, 'fixture must expose round toggles').toBeGreaterThan(0);
  expect(baseline.spread, 'initial toggle spread must be <=20px').toBeLessThanOrEqual(20);

  const toggles = page.locator('[data-trace-round-row] [data-action="toggle-round"]');
  const toggleCount = await toggles.count();
  for (const index of [0, 1, 7, 23].filter((item) => item < toggleCount)) {
    await toggles.nth(index).click();
    await expect(toggles.nth(index)).toHaveAttribute('aria-expanded', 'true', { timeout: 10_000 });
    await toggles.nth(index).click();
    await expect(toggles.nth(index)).toHaveAttribute('aria-expanded', 'false', { timeout: 5_000 });
  }
  await expectNoAlignmentRegression(page, baseline.spread, 'round clicks');

  const failedFilter = page.locator('[data-action="status-failed"]').first();
  const allFilter = page.locator('[data-action="status-all"]').first();
  await expect(failedFilter).toBeVisible();
  await failedFilter.click();
  await expectNoAlignmentRegression(page, baseline.spread, 'failed filter', true);
  await allFilter.click();
  await expectNoAlignmentRegression(page, baseline.spread, 'all filter', true);

  const toggleAll = page.locator('[data-action="toggle-all"]').first();
  await expect(toggleAll).toBeVisible();
  await toggleAll.click();
  await expect.poll(
    () => page.locator('[data-trace-round-row].is-open').count(),
    { message: 'expand-all must open trace rounds', timeout: 25_000 },
  ).toBeGreaterThan(0);
  await toggleAll.click();
  await expect.poll(
    () => page.locator('[data-trace-round-row].is-open').count(),
    { message: 'collapse-all must close trace rounds', timeout: 5_000 },
  ).toBe(0);
  await expectNoAlignmentRegression(page, baseline.spread, 'expand/collapse all');
});

test('[UI-SD-021][UI-SD-041] payload typed content remains accessible in the current single-view modal', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1100 });
  await openHydratedSession(page);

  const firstToggle = page.locator('[data-action="toggle-round"]').first();
  await firstToggle.click();
  await expect(firstToggle).toHaveAttribute('aria-expanded', 'true', { timeout: 10_000 });
  const payloadButton = page.locator('[data-trace-round-row]').first()
    .getByRole('button', { name: 'Request', exact: true });
  await expect(payloadButton, 'expanded round must expose a payload action').toBeVisible({ timeout: 10_000 });
  await payloadButton.click();

  const modal = page.locator('dialog.payload-modal');
  await expect.poll(
    () => modal.evaluate((dialog) => dialog.open).catch(() => false),
    { message: 'payload modal must open', timeout: 5_000 },
  ).toBe(true);
  await expect(modal).toHaveAccessibleName(/.+/);
  await expect(modal.getByRole('button', { name: /close/i })).toBeVisible();

  const rendered = modal.locator('[data-payload-body]');
  await expect.poll(
    async () => (await rendered.innerText()).trim(),
    { message: 'typed payload content must be non-empty', timeout: 10_000 },
  ).not.toBe('');
  expect((await rendered.innerText()).trim()).not.toBe('(No rendered content)');
  await expect(modal.locator('.sd-conversation-payload')).toBeVisible();
  await expect(modal.locator('.sd-content-block .sd-card-title').first()).toContainText('Request');
  await expect(modal.locator('.sd-payload-meta')).toHaveCount(0);
  await expect(modal.locator('.sd-payload-empty')).toHaveCount(0);

  await page.keyboard.press('Escape');
  await expect(modal).toBeHidden({ timeout: 5_000 });
  const overflow = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    viewportWidth: window.innerWidth,
  }));
  expect(overflow.scrollWidth).toBeLessThanOrEqual(overflow.viewportWidth + 2);
});

test('[UI-SD-042][UI-VISUAL-010] long session remains vertically scrollable without horizontal overflow', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1100 });
  await openHydratedSession(page, LONG_SESSION_PATH);
  await expect(page.locator('[data-trace-round-row]')).toHaveCount(100);

  const before = await page.evaluate(() => ({
    scrollHeight: document.documentElement.scrollHeight,
    viewportHeight: window.innerHeight,
    scrollWidth: document.documentElement.scrollWidth,
    viewportWidth: window.innerWidth,
  }));
  expect(before.scrollHeight).toBeGreaterThan(before.viewportHeight);
  expect(before.scrollWidth).toBeLessThanOrEqual(before.viewportWidth + 2);
  await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
  await expect.poll(() => page.evaluate(() => window.scrollY), { timeout: 5_000 }).toBeGreaterThan(0);
});

// 资源失败与逆序响应也必须由既有 browserBehaviorTests required Gate 持续验证。
test.describe('会话资源独立失败与恢复', () => {
  const detail = '/sessions/claude_code/hifi-viz-session-001';
  async function failResource(page, pattern) {
    let failing = true;
    await page.route(pattern, (route) => failing
      ? route.fulfill({ status: 500, contentType: 'application/json', body: '{}' })
      : route.continue());
    return () => { failing = false; };
  }

  test('diagnostics failure preserves expandable rounds and retry restores hydration', async ({ page }) => {
    const recover = await failResource(page, '**/diagnostics');
    await page.goto(detail);
    const round = page.locator('[data-trace-round-row]').first();
    await expect(round).toBeVisible();
    await round.locator('[data-action="toggle-round"]').click();
    await expect(round).toHaveAttribute('data-detail-loaded', 'true');
    await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'false');
    await expect(page.locator('[data-resource-error="diagnostics"]')).toContainText('HTTP 500');
    recover();
    await page.locator('[data-resource-error="diagnostics"] button').click();
    await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
    await expect(page.locator('[data-resource-error]')).toHaveCount(0);
  });

  test('round failure replaces loading with retryable error', async ({ page }) => {
    const recover = await failResource(page, '**/rounds');
    await page.goto(detail);
    const table = page.locator('.trace-table[data-trace-list] tbody');
    await expect(table).toContainText('Unable to load rounds');
    await expect(table).not.toContainText('Loading');
    await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'false');
    recover();
    await table.getByRole('button', { name: 'Retry' }).click();
    await expect(page.locator('[data-trace-round-row]').first()).toBeVisible();
    await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  });

  test('list auxiliary failure preserves rows and supports retry', async ({ page }) => {
    const recover = await failResource(page, '**/api/sessions/options*');
    await page.goto('/sessions');
    await expect(page.locator('.sessions-row').first()).toBeVisible();
    await expect(page.locator('[data-resource-error="options"]')).toContainText('HTTP 500');
    recover();
    await page.locator('[data-resource-error="options"] button').click();
    await expect(page.locator('[data-resource-error]')).toHaveCount(0);
    await expect(page.locator('.sessions-row').first()).toBeVisible();
  });

  test('list rows failure stays on page and recovers without reload loop', async ({ page }) => {
    let navigations = 0;
    page.on('request', (request) => {
      if (request.isNavigationRequest() && request.resourceType() === 'document'
        && request.frame() === page.mainFrame()) navigations += 1;
    });
    const recover = await failResource(page, '**/api/sessions/rows*');
    await page.goto('/sessions');
    const table = page.locator('.data-table tbody');
    await expect(table).toContainText('Unable to load rows');
    await expect(table).not.toContainText('Loading');
    await page.waitForTimeout(500);
    expect(navigations).toBe(1);
    recover();
    await table.getByRole('button', { name: 'Retry' }).click();
    await expect(page.locator('.sessions-row').first()).toBeVisible();
    expect(navigations).toBe(1);
  });

  async function querySessions(page, query) {
    await page.locator('#session-filter-form').evaluate((form, value) => {
      form.querySelector('[name="q"]').value = value;
      form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    }, query);
  }

  function queryResource(route, query) {
    const name = new URL(route.request().url()).pathname.split('/').pop();
    const filters = { q: query };
    const bodies = {
      rows: { rows: [{ sessionKey: query, sessionId: query, title: `Query ${query}`, agent: 'claude_code', detailUrl: detail }], filters },
      summary: { totalCount: query === 'B' ? 2 : 1, projectCount: 1, tokens: {} },
      options: { models: [{ value: query, label: `Model ${query}` }] },
      'active-filters': { chips: [{ key: 'q', label: 'Query', value: query }] },
    };
    return fulfillIndexedJson(route, bodies[name]);
  }

  test('new query survives older delayed rows, auxiliary success and failure', async ({ page }) => {
    let release;
    const delayed = new Promise((resolve) => { release = resolve; });
    let pending = 0;
    let completed = 0;
    await page.route('**/api/sessions/*', async (route) => {
      const url = new URL(route.request().url());
      const query = url.searchParams.get('q');
      if (query !== 'A' && query !== 'B') return route.continue();
      if (query === 'A') {
        pending += 1;
        await delayed;
        if (url.pathname.endsWith('/active-filters')) {
          await route.fulfill({ status: 500, body: '{}' });
        } else await queryResource(route, query);
        completed += 1;
        return;
      }
      return queryResource(route, query);
    });
    await page.goto('/sessions');
    await expect(page.locator('.sessions-row').first()).toBeVisible();
    await querySessions(page, 'A');
    await expect.poll(() => pending).toBe(4);
    await querySessions(page, 'B');
    await expect(page.locator('.sessions-row')).toContainText('Query B');
    await expect(page.locator('#filter-model option')).toContainText(['All Models', 'Model B']);
    release();
    await expect.poll(() => completed).toBe(4);
    // Wait until the browser has consumed the released fetch bodies, not just the route fulfill calls.
    await page.waitForTimeout(300);
    await expect(page.locator('.sessions-row')).toContainText('Query B');
    await expect(page).toHaveURL(/q=B/);
    await expect(page.locator('#filter-model option')).toContainText(['All Models', 'Model B']);
    await expect(page.locator('.page-head__stats')).toContainText('2 sessions');
    await expect(page.locator('.active-filters')).toContainText('B');
    await expect(page.locator('[data-resource-error]')).toHaveCount(0);
  });

  test('old query retry cannot overwrite a newer successful query', async ({ page }) => {
    let attempts = 0;
    let retryStarted = false;
    let release;
    const delayed = new Promise((resolve) => { release = resolve; });
    let completed = false;
    await page.route('**/api/sessions/*', async (route) => {
      const url = new URL(route.request().url());
      const query = url.searchParams.get('q');
      if (query !== 'A' && query !== 'B') return route.continue();
      if (query === 'A' && url.pathname.endsWith('/rows')) {
        attempts += 1;
        if (attempts === 1) return route.fulfill({ status: 500, body: '{}' });
        retryStarted = true;
        await delayed;
        await queryResource(route, query);
        completed = true;
        return;
      }
      return queryResource(route, query);
    });
    await page.goto('/sessions');
    await expect(page.locator('.sessions-row').first()).toBeVisible();
    await querySessions(page, 'A');
    await page.locator('[data-resource-error="rows"] button').click();
    await expect.poll(() => retryStarted).toBe(true);
    await querySessions(page, 'B');
    await expect(page.locator('.sessions-row')).toContainText('Query B');
    release();
    await expect.poll(() => completed).toBe(true);
    await page.waitForTimeout(300);
    await expect(page.locator('.sessions-row')).toContainText('Query B');
    await expect(page).toHaveURL(/q=B/);
    await expect(page.locator('[data-resource-error]')).toHaveCount(0);
  });
});

// 使用真实上传解析，而非 mock round/payload；这些场景必须留在 Gate 已选择的 spec 中。
for (const shape of ['event-only', 'event-usage', 'dual', 'anonymous-dual', 'multiturn', 'response-only']) {
  test(`Codex ${shape} renders original request and assistant text`, async ({ page, request, baseURL }) => {
    const prompt = `Synthetic Codex ${shape} original request`;
    const answer = `Synthetic Codex ${shape} original assistant answer`;
    const messages = [[prompt, answer]];
    const events = [
      { type: 'session_meta', payload: { id: 'synthetic-codex-content', cwd: '/synthetic' } },
      { type: 'turn_context', payload: { model: 'synthetic-model' } },
    ];
    if (shape !== 'response-only') events.push(
      { type: 'event_msg', payload: { type: 'user_message', message: prompt } },
      { type: 'event_msg', payload: { type: 'agent_message', message: answer } },
    );
    if (shape === 'event-usage' || shape === 'multiturn') events.push({
      type: 'event_msg', payload: { type: 'token_count', info: {
        total_token_usage: { input_tokens: 10, output_tokens: 5, total_tokens: 15 },
      } },
    });
    if (shape === 'dual' || shape === 'anonymous-dual' || shape === 'response-only') events.push(
      { type: 'response_item', payload: { type: 'message', role: 'user', content: [{ type: 'input_text', text: prompt }] } },
      { type: 'response_item', payload: { type: 'message', role: 'assistant', content: [{ type: 'output_text', text: answer }] } },
    );
    // A shared explicit turn identifies mirrored observations; text equality alone does not.
    if (shape === 'dual') {
      for (const event of events) {
        if (event.type === 'event_msg' || event.type === 'response_item') {
          event.payload.turn_id = 'synthetic-dual-turn';
        }
      }
    }
    // Without identity the two source observations must remain visible, even with identical text.
    if (shape === 'anonymous-dual') messages.push([prompt, answer]);
    if (shape === 'multiturn') {
      messages.push([prompt + ' second', answer + ' second']);
      events.push(
        { type: 'event_msg', payload: { type: 'user_message', message: messages[1][0] } },
        { type: 'event_msg', payload: { type: 'agent_message', message: messages[1][1] } },
      );
    }
    let importId;
    try {
      await page.goto('/imports');
      await page.getByLabel('会话来源', { exact: true }).selectOption('codex');
      const chooser = page.waitForEvent('filechooser');
      await page.getByLabel('JSONL 文件', { exact: true }).click();
      await (await chooser).setFiles({
        name: `synthetic-codex-${shape}.jsonl`, mimeType: 'application/x-ndjson',
        buffer: Buffer.from(events.map(JSON.stringify).join('\n') + '\n'),
      });
      const uploaded = page.waitForResponse((response) =>
        new URL(response.url()).pathname === '/api/imports' && response.request().method() === 'POST');
      await page.getByRole('button', { name: '导入并分析', exact: true }).click();
      expect((await uploaded).status()).toBe(201);
      await expect(page).toHaveURL(/\/imports\/[0-9a-f-]{36}$/);
      importId = new URL(page.url()).pathname.split('/').pop();
      await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
      await expect(page.locator('[data-trace-round-row]')).toHaveCount(messages.length);
      await expect(page.locator('[aria-label="Total Tokens"] .sd-kpi__value')).toHaveText(
        shape === 'event-usage' || shape === 'multiturn' ? '15 · Partial' : 'N/A · Unknown',
      );
      for (const [index, [userText, assistantText]] of messages.entries()) {
        const round = page.locator('[data-trace-round-row]').nth(index);
        await round.locator('[data-action="toggle-round"]').click();
        for (const [title, original] of [['Request', userText], ['Response', assistantText]]) {
          await round.getByRole('button', { name: title, exact: true }).click();
          const modal = page.locator('dialog.payload-modal');
          const block = modal.locator('.sd-content-block').filter({ has: page.getByText(title, { exact: true }) });
          await expect(block.locator('pre')).toBeVisible();
          await expect(block.locator('pre')).toContainText(original);
          await modal.getByRole('button', { name: 'Close', exact: true }).click();
        }
      }
    } finally {
      if (importId) {
        const deleted = await request.delete(`/api/imports/${importId}`, { headers: { Origin: new URL(baseURL).origin } });
        expect([204, 404]).toContain(deleted.status());
      }
    }
  });
}

// Regression evidence from the real-data audit; all payloads below are synthetic.
const projectMeasuredProvenance = { freshInput: 'provider_reported', cacheRead: 'provider_reported', cacheWrite: 'provider_reported', output: 'provider_reported' };
test('project agent mix coverage labels fit the card at desktop and narrow widths', async ({ page }) => {
  await page.route('**/api/projects/*/agent-mix*', route => fulfillIndexedJson(route, {
    rows: [
      { agent: 'claude_code', label: 'Claude Code', sessions: 12345, sessionShare: 60,
        tokens: { total: 1234567, provenance: { ...projectMeasuredProvenance, output: 'unknown' } },
        failedTools: 1234, contentSampleCount: 123 },
      { agent: 'codex', label: 'Codex', sessions: 9876, sessionShare: 40,
        tokens: { total: 0, provenance: {} }, failedTools: null, contentSampleCount: 0 },
    ],
  }));
  await page.goto('/projects/test-hifi-project');
  const rows = page.locator('.agent-mix-row');
  await expect(rows).toHaveCount(2);
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 900 });
    await expect(rows.nth(0)).toContainText('Partial');
    await expect(rows.nth(0)).toContainText('Observed (123/12345)');
    await expect(rows.nth(1)).toContainText('Unknown');
    for (const row of await rows.all()) {
      for (const child of await row.locator(':scope > span').all()) await expect(child).toBeVisible();
      expect(await row.evaluate(node => {
        const card = node.closest('.project-analysis-card').getBoundingClientRect();
        return [...node.children].every(child => {
          const rect = child.getBoundingClientRect();
          const style = getComputedStyle(child);
          return rect.left >= card.left && rect.right <= card.right
            && child.scrollWidth <= child.clientWidth + 1
            && style.textOverflow !== 'ellipsis' && style.whiteSpace !== 'nowrap';
        });
      }), `Agent Mix content fits at ${width}px without truncation`).toBe(true);
    }
  }
});

test('real audit: project API token points draw the stacked SVG instead of an empty canvas', async ({ page }) => {
  await page.route('**/api/projects/*/token-trend*', route => fulfillIndexedJson(route, {
    points: [
      { label: '2026-11-01', tokens: { fresh: 10, cacheRead: 20, cacheWrite: 5, output: 15, total: 50, provenance: projectMeasuredProvenance } },
      { label: '2026-11-02', tokens: { fresh: 20, cacheRead: 30, cacheWrite: 10, output: 40, total: 100, provenance: projectMeasuredProvenance } },
    ],
  }));
  await page.goto('/projects/test-hifi-project');
  const chart = page.locator('.project-token-area-chart');
  await expect(chart.locator('path')).toHaveCount(4);
  await expect(chart.locator('.project-area--output')).toHaveAttribute('d', /M.*L.*Z/);
  await expect(page.locator('.project-trend-point')).toHaveCount(2);
});

test('real audit: Prompt Activity uses the API summary and null failure efficiency stays unknown', async ({ page }) => {
  await page.route('**/api/dashboard/summary*', async route => {
    const response = await route.fetch();
    const body = await response.json();
    await route.fulfill({ response, json: { ...body, userMessages: 123456 } });
  });
  await page.route('**/api/dashboard/agents/efficiency*', route => fulfillIndexedJson(route, {
    rows: [{ agent: 'codex', model: 'synthetic-null-failure', sessionCount: 1,
      avgTokensPerSession: 1, avgWallSeconds: 1, avgToolsPerSession: 0, failedPerSession: null }],
  }));
  await page.goto('/dashboard');
  const card = page.locator('.metric-card--kpi').filter({ has: page.locator('.metric-card__label', { hasText: /^Prompt Activity$/ }) });
  await expect(card.locator('.metric-card__value')).toHaveText('123,456');
  const row = page.locator('#dashboard-agent-model-efficiency-table tbody tr').filter({ hasText: 'synthetic-null-failure' });
  await expect(row.locator('td').last()).toHaveText('N/A');
});

test('real audit: an empty rounds response resolves the diagnostic timeline empty state', async ({ page }) => {
  await page.route('**/api/sessions/*/*/rounds*', route => fulfillIndexedJson(route, {
    rounds: [], state: { title: 'No readable log', message: 'Source transcript is missing.' },
  }));
  await page.goto(SESSION_PATH);
  await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  await expect(page.locator('.trace-table')).toContainText('No readable log');
  const diagnostics = page.locator('[data-session-diagnostics]');
  await expect(diagnostics.getByRole('heading', { name: 'Content evidence unavailable', exact: true })).toBeVisible();
  await expect(diagnostics).toContainText('Agent, tool and failure counts are N/A, not measured zero.');
  await expect(diagnostics).not.toContainText('is loading');
  await expect(diagnostics.locator('.sd-subagent-timeline')).toHaveCount(0);
});

test('real audit: visible version matches the launcher build version', async ({ page }) => {
  const fs = require('fs');
  const path = require('path');
  const version = fs.readFileSync(path.resolve(__dirname, '../../gradle/VERSION'), 'utf8').trim();
  await page.goto('/dashboard');
  await expect(page.locator('.brand-meta > span').first()).toHaveText('v' + version);
});

for (const [measurement, total, pathCount] of [['unknown', 5, 8], ['unavailable', 0, 8], ['provider_reported', 0, 4]]) {
  test(`real audit: project trend respects ${measurement} points without fabricating zero`, async ({ page }) => {
    const point = (label, total, state) => ({ label, tokens: { fresh: total, cacheRead: 0, cacheWrite: 0, output: 0, total,
      provenance: { freshInput: state, cacheRead: state, cacheWrite: state, output: state } } });
    await page.route('**/api/projects/*/token-trend*', route => fulfillIndexedJson(route, {
      points: [point('2026-11-01', 10, 'provider_reported'), point('2026-11-02', total, measurement), point('2026-11-03', 20, 'provider_reported')],
    }));
    await page.goto('/projects/test-hifi-project');
    await expect(page.locator('.project-token-area-chart path')).toHaveCount(pathCount);
  });
}

test.describe('real trend bucket regressions', () => {
  test.use({ timezoneId: 'America/Los_Angeles' });
  const measured = { freshInput: 'provider_reported', cacheRead: 'provider_reported', cacheWrite: 'provider_reported', output: 'provider_reported' };
  const observations = [
    ['2025-01-01', 999, 1], ['2026-10-01', 7, 9], ['2026-10-29', 3, 2],
    ['2026-11-03', 2, 5], ['2026-11-05', 10, 8],
    ['2026-11-05T01:30:00Z', 999, 10], ['2026-11-06', 1000, 10],
  ];
  const badge = (page, label) => page.locator('.metric-card--kpi').filter({ has: page.locator('.metric-card__label', { hasText: new RegExp('^' + label + '$') }) }).locator('.metric-card__badge');

  test.beforeEach(async ({ page }) => {
    const path = require('path');
    await page.clock.setFixedTime(new Date('2026-11-05T00:30:00Z'));
    await page.route('**/static/js/*.js*', route => route.fulfill({
      path: path.resolve(__dirname, '../../web/src/main/resources/static/js', path.basename(new URL(route.request().url()).pathname)),
      contentType: 'text/javascript',
    }));
    await page.route('**/api/dashboard/trends/*', route => {
      const resource = new URL(route.request().url()).pathname.split('/').pop();
      const points = observations.map(([date, count, read]) => {
        const tokens = { fresh: 10 - read, cacheRead: read, cacheWrite: 0, output: 0, total: 10, provenance: measured };
        if (resource === 'sessions') return { date, totalCount: count, codexCount: count, failedTools: count };
        if (resource === 'tokens') return { date, tokens, codexTokens: 10 };
        if (resource === 'prompts') return { date, totalPrompts: count, codexPrompts: count };
        const tuple = { ...tokens, ratio: { value: read / 10, provenance: measured } };
        return { date, average: tuple, codex: tuple };
      });
      return fulfillIndexedJson(route, { points, latestRatio: { value: 1, provenance: measured }, lowestRatio: { value: 0.01, provenance: measured } });
    });
  });

  for (const [grain, count, delta, ratio, ratioDelta, buckets, lowest] of [
    ['day', 10, '+10', '80.0%', 'N/A', 30, '20.0%'],
    ['week', 12, '+9', '65.0%', '+45.0pp', 20, '20.0%'],
    // October's weighted monthly ratio is (9+2)/(10+10), not its lowest daily ratio.
    ['month', 12, '+2', '65.0%', '+10.0pp', 12, '55.0%'],
  ]) {
    test(`${grain}: adjacent UTC buckets, matching cache summary and no future cohort`, async ({ page }) => {
      await page.goto('/dashboard?grain=' + grain);
      await expect(page.locator('[data-stat="latest-sessions"]')).toHaveText('Latest: ' + count);
      await expect(badge(page, 'Sessions')).toHaveText(delta);
      await expect(badge(page, 'Prompt Activity')).toHaveText(delta);
      await expect(badge(page, 'Cache Read Ratio')).toHaveText(ratioDelta);
      await expect(badge(page, 'Sessions')).toHaveAttribute('data-tooltip-def', /UTC.*session-start cohort.*未完成/);
      await expect(page.locator('[data-stat="latest-ratio"]')).toHaveText('Latest ratio: ' + ratio);
      await expect(page.locator('[data-stat="lowest-ratio"]')).toHaveText('Lowest ratio: ' + lowest);
      await expect(page.locator('#trend-chart .bar')).toHaveCount(buckets);
      await expect(page.locator('[data-stat="range-total-tokens"]')).toHaveText('Range total: ' + (grain === 'day' ? 30 : 40));
      if (grain === 'day') await expect(page.locator('[data-stat="range-total-sessions"]')).toHaveText('Range total: 15');
    });
  }

  test('an empty current day is zero sessions but unknown cache, not the last measured day', async ({ page }) => {
    await page.route('**/api/dashboard/trends/sessions*', route => fulfillIndexedJson(route, {
      points: [{ date: '2026-11-03', totalCount: 2, codexCount: 2 }],
    }));
    await page.route('**/api/dashboard/trends/cache-health*', route => fulfillIndexedJson(route, {
      points: [{ date: '2026-11-03', average: { fresh: 5, cacheRead: 5, cacheWrite: 0,
        provenance: measured, ratio: { value: 0.5, provenance: measured } } }],
      latestRatio: { value: 0.5, provenance: measured },
    }));
    await page.goto('/dashboard?grain=day');
    await expect(page.locator('[data-stat="latest-sessions"]')).toHaveText('Latest: 0');
    await expect(badge(page, 'Sessions')).toHaveText('0');
    await expect(page.locator('[data-stat="latest-ratio"]')).toHaveText('Latest ratio: N/A');
    await expect(badge(page, 'Cache Read Ratio')).toHaveText('N/A');
  });
});

test('real generation: quarantine hides the actual styled main and safely restores it', async ({ page }) => {
  const path = require('path');
  await page.addInitScript({ path: path.resolve(__dirname, '../../web/src/main/resources/static/js/index-snapshot.js') });
  await page.route('**/static/css/shell.css*', route => route.fulfill({
    path: path.resolve(__dirname, '../../web/src/main/resources/static/css/shell.css'), contentType: 'text/css',
  }));
  await page.goto(SESSION_PATH);
  await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  await expect(page.locator('main')).toHaveClass(/main/);
  await page.route('**/api/qa-real-main/*', route => route.fulfill({
    headers: { 'X-Session-Index-Generation': 'synthetic-main-G2' }, json: {},
  }));
  await page.evaluate(async () => {
    // Isolate apply-failure recovery from the separate immutable SSR-document boundary.
    document.body.removeAttribute('data-index-generation');
    window.snapshotApplyFails = true;
    window.snapshotBindingClicks = 0;
    const binding = document.createElement('button');
    binding.id = 'snapshot-preserved-binding';
    binding.textContent = 'Synthetic preserved control';
    binding.addEventListener('click', () => { window.snapshotBindingClicks += 1; });
    document.querySelector('main').append(binding);
    await window.IndexSnapshot.create().load([
      { key: 'synthetic-main-a', url: '/api/qa-real-main/a', apply() { document.querySelector('main h1').textContent = 'Synthetic new snapshot'; } },
      { key: 'synthetic-main-b', url: '/api/qa-real-main/b', apply() { if (window.snapshotApplyFails) throw new Error('Synthetic render failure'); } },
    ]);
  });
  await expect(page.locator('main')).toBeHidden();
  await expect(page.getByRole('heading', { name: 'Synthetic new snapshot', exact: true })).toBeHidden();
  await expect(page.locator('body')).not.toHaveAttribute('data-index-generation', 'synthetic-main-G2');
  await expect(page.locator('[data-snapshot-batch-error]')).toBeVisible();
  await page.evaluate(() => { window.snapshotApplyFails = false; });
  await page.getByRole('button', { name: 'Retry entire page', exact: true }).click();
  await expect(page.locator('main')).toBeVisible();
  await expect(page.locator('body')).toHaveAttribute('data-index-generation', 'synthetic-main-G2');
  await page.locator('#snapshot-preserved-binding').click();
  expect(await page.evaluate(() => window.snapshotBindingClicks)).toBe(1);
});

test('failed scan status keeps published content and exposes distinct candidate and diagnostic counts', async ({ page }) => {
  let statusRequests = 0;
  let scanWrites = 0;
  page.on('request', request => {
    if (/\/api\/scan(?:\?|$)/.test(request.url()) && request.method() !== 'GET') scanWrites += 1;
  });
  await page.route('**/api/scan-status', route => {
    statusRequests += 1;
    return route.fulfill({ json: {
      status: 'failure', processedCount: 2, publishedProcessedCount: 0, errorCount: 1,
      publishedDataAvailable: true,
      message: 'Latest scan failed. Previous successfully published data is still displayed; this failed scan published no partial results.',
      reasons: [
        { source: 'codex', phase: 'PARSE', code: 'BUFFER_OVERFLOW', line: 42, explanation: 'Source parsing reached its bounded buffer limit.' },
        { source: 'codex', phase: 'PARSE', code: 'BAD_JSON', line: 43, explanation: 'The source could not be parsed.' },
      ],
      retryCommand: './scripts/session-browser.sh scan --incremental --index-dir <same-index-directory>',
    } });
  });
  await page.goto('/dashboard');
  const banner = page.locator('[data-scan-status-banner]');
  await expect(banner).toContainText('最新扫描失败');
  await expect(banner).toContainText('Processed: 2 · Published from this scan: 0 · Errors: 1');
  await expect(banner).toContainText('codex · PARSE · BUFFER_OVERFLOW · line 42');
  await expect(banner).toContainText('codex · PARSE · BAD_JSON · line 43');
  await expect(banner).toContainText('Previous successfully published data');
  await expect(page.locator('.kpi-grid')).toBeVisible();
  expect(await banner.locator('.state-panel').count()).toBe(0);
  const beforeRefresh = statusRequests;
  await banner.getByRole('button', { name: '刷新状态', exact: true }).click();
  await expect.poll(() => statusRequests).toBeGreaterThan(beforeRefresh);
  await expect(page).toHaveURL(/\/dashboard$/);
  expect(scanWrites).toBe(0);
});

test('unavailable scan status is unknown rather than silently successful', async ({ page }) => {
  await page.route('**/api/scan-status', route => route.fulfill({ status: 503, json: { error: 'synthetic unavailable' } }));
  await page.goto('/sessions');
  const banner = page.locator('[data-scan-status-banner]');
  await expect(banner).toContainText('扫描状态读取失败');
  await expect(banner).toContainText('当前页面数据是否最新尚未确认');
  await expect(banner).not.toContainText('最新扫描失败');
  await expect(page.locator('.data-table')).toBeVisible();
});

// Server-free synthetic probes exercise the shared helper in a real browser.
test.describe('event optional snapshot:', () => {
  async function openOptionalProbe(page) {
    const path = require('path');
    await page.route('http://snapshot.test/', route => route.fulfill({
      contentType: 'text/html',
      // Match the product's hidden-state rule; the probe isolates snapshot logic, not CSS ownership.
      body: '<!doctype html><html><head><style>[hidden]{display:none!important}main{display:block;padding:16px}p{min-height:24px}</style></head><body><main><p id="required">initial</p><p id="optional">initial</p></main></body></html>',
    }));
    await page.goto('http://snapshot.test/');
    await page.addScriptTag({ path: path.resolve(__dirname, '../../web/src/main/resources/static/js/index-snapshot.js') });
    await page.evaluate(() => {
      window.optionalProbe = { generation: 'A', optionalGeneration: 'A', status: 501, failure: '', throwApply: false, optionalApplies: 0, errors: [] };
      // A local synthetic origin and explicit resource URLs prevent real-source requests.
      window.fetch = async url => {
        const state = window.optionalProbe;
        if (url === 'http://snapshot.test/required') {
          return new Response(JSON.stringify({ value: state.generation }), { status: 200, headers: { 'X-Session-Index-Generation': state.generation } });
        }
        if (url !== 'http://snapshot.test/optional') throw new Error('unexpected synthetic URL');
        if (state.failure === 'network') throw new Error('synthetic network failure');
        return new Response(state.failure === 'json' ? '{invalid' : JSON.stringify({ value: state.optionalGeneration }), {
          status: state.status, headers: { 'X-Session-Index-Generation': state.optionalGeneration },
        });
      };
      window.optionalSnapshot = window.IndexSnapshot.create();
      window.loadOptionalProbe = () => window.optionalSnapshot.load([
        { key: 'event-probe-required', url: 'http://snapshot.test/required', apply(data) {
          if (window.optionalProbe.throwApply) throw new Error('synthetic required apply failure');
          document.querySelector('#required').textContent = data.value;
        } },
        { key: 'event-probe-optional', url: 'http://snapshot.test/optional', unavailableStatus: 501,
          apply(data) { window.optionalProbe.optionalApplies += 1; document.querySelector('#optional').textContent = data.value; },
          error(error) { window.optionalProbe.errors.push(error.message); document.querySelector('#optional').textContent = 'Unknown ' + error.message; },
        },
      ]);
      return window.loadOptionalProbe();
    });
  }

  test('event optional snapshot: matching 501 settles a new generation without applying error data', async ({ page }) => {
    await openOptionalProbe(page);
    await expect(page.locator('main')).toBeVisible();
    await expect(page.locator('#required')).toHaveText('A');
    await expect(page.locator('#optional')).toHaveText('Unknown HTTP 501');
    await expect(page.locator('body')).toHaveAttribute('data-index-generation', 'A');
    await page.evaluate(async () => {
      Object.assign(window.optionalProbe, { generation: 'B', optionalGeneration: 'B' });
      await window.loadOptionalProbe();
    });
    await expect(page.locator('main')).toBeVisible();
    await expect(page.locator('#required')).toHaveText('B');
    await expect(page.locator('#optional')).toHaveText('Unknown HTTP 501');
    await expect(page.locator('body')).toHaveAttribute('data-index-generation', 'B');
    expect(await page.evaluate(() => window.optionalProbe.optionalApplies)).toBe(0);
    expect(await page.evaluate(() => window.optionalProbe.errors)).toEqual(['HTTP 501', 'HTTP 501']);
    await expect(page.locator('[data-snapshot-error], [data-snapshot-batch-error]')).toHaveCount(0);
  });

  test('event optional snapshot: quarantined recovery permits only the declared 501 status', async ({ page }) => {
    await openOptionalProbe(page);
    await page.evaluate(async () => {
      Object.assign(window.optionalProbe, { generation: 'B', optionalGeneration: 'B', status: 200, throwApply: true });
      await window.loadOptionalProbe();
    });
    await expect(page.locator('main')).toBeHidden();
    await expect(page.locator('[data-snapshot-batch-error]')).toContainText('synthetic required apply failure');
    for (const failure of ['500', 'network', 'json', '409']) {
      await page.evaluate(async failure => {
        Object.assign(window.optionalProbe, { generation: 'C', optionalGeneration: 'C', throwApply: false,
          status: failure === '500' ? 500 : failure === '409' ? 409 : 200,
          failure: failure === 'network' || failure === 'json' ? failure : '' });
        await window.loadOptionalProbe();
      }, failure);
      await expect(page.locator('main')).toBeHidden();
      await expect(page.locator('[data-snapshot-batch-error]')).toBeVisible();
      await expect(page.locator('#required')).toHaveText('A');
    }
    await page.evaluate(async () => {
      Object.assign(window.optionalProbe, { status: 501, failure: '' });
      await window.loadOptionalProbe();
    });
    await expect(page.locator('main')).toBeVisible();
    await expect(page.locator('#required')).toHaveText('C');
    await expect(page.locator('#optional')).toHaveText('Unknown HTTP 501');
    await expect(page.locator('body')).toHaveAttribute('data-index-generation', 'C');
    await expect(page.locator('[data-snapshot-batch-error]')).toHaveCount(0);
    expect(await page.evaluate(() => window.optionalProbe.optionalApplies)).toBe(0);
  });

  test('event optional snapshot: a 501 with a different generation never permits mixed rendering', async ({ page }) => {
    await openOptionalProbe(page);
    await page.evaluate(async () => {
      Object.assign(window.optionalProbe, { generation: 'B', optionalGeneration: 'A' });
      await window.loadOptionalProbe();
    });
    await expect(page.locator('#required')).toHaveText('A');
    await expect(page.locator('body')).toHaveAttribute('data-index-generation', 'A');
    await expect(page.locator('[data-snapshot-error]').first()).toContainText('Index changed repeatedly');
    expect(await page.evaluate(() => window.optionalProbe.optionalApplies)).toBe(0);
  });
});

test.describe('event dashboard:', () => {
  test.use({ timezoneId: 'America/Los_Angeles' });
  const eventRows = page => page.locator('[data-event-activity-days] tr');
  function eventTokens() {
    const component = (reportedTokens, reportedSamples, estimatedSamples, unavailableSamples, unknownSamples, mixedSamples) =>
      ({ reportedTokens, reportedSamples, estimatedSamples, unavailableSamples, unknownSamples, mixedSamples });
    return { fresh: component(null, 0, 1, 2, 3, 4), cacheRead: component(0, 1, 0, 0, 0, 0),
      cacheWrite: component(11, 2, 3, 4, 5, 6), output: component(13, 1, 0, 0, 0, 0) };
  }
  function eventResponse(params, empty = false) {
    const factor = params.get('agent') === 'codex' ? 2 : 1;
    return { basis: 'source_event_utc', tokenBasis: 'codex_modern_usage_report_day', coverage: empty ? 'unknown' : 'partial',
      windowDays: Number(params.get('days')), coverageCounts: { summarizedSessions: empty ? 0 : 2,
        unknownSessions: 4, undatedUserMessages: 7, undatedUsageEvents: 5, unsupportedUsageEvents: 6,
        futureExcludedDayBuckets: 2, futureExcludedObservedUserMessages: 9 }, undatedTokens: eventTokens(),
      days: empty ? [] : [['2025-01-01', 999], ['2026-10-29', 2], ['2026-11-03', 3], ['2026-11-05', 5], ['2026-11-06', 999]]
        .map(([date, count]) => ({ date, observedUserMessages: count * factor, tokens: eventTokens() })) };
  }
  async function interceptEvents(page, state = {}) {
    await page.clock.setFixedTime(new Date('2026-11-05T00:30:00Z'));
    state.requests = [];
    await page.route('**/api/dashboard/event-activity?*', async route => {
      const params = new URL(route.request().url()).searchParams;
      state.requests.push(Object.fromEntries(params));
      if (state.unavailable) {
        const response = await route.fetch();
        return route.fulfill({ response, status: 501, json: { error: 'EVENT_ACTIVITY_UNAVAILABLE' } });
      }
      return fulfillIndexedJson(route, eventResponse(params, state.empty));
    });
    return state;
  }
  async function expectHealthyCohort(page) {
    await expect(page.locator('main')).toBeVisible();
    await expect(page.locator('.metric-card--kpi')).toHaveCount(6);
    await expect(page.locator('[data-stat="latest-sessions"]')).not.toContainText('Loading');
    await expect(page.locator('[data-chart-card="sessions"]')).toBeVisible();
    await expect(page.locator('[data-chart-card="tokens"]')).toBeVisible();
    await expect(page.locator('[data-snapshot-batch-error]')).toHaveCount(0);
  }

  for (const [grain, expected] of [
    ['day', [['2026-10-29', '2', 'N/A', '0', '11', '13'], ['2026-11-03', '3', 'N/A', '0', '11', '13'], ['2026-11-05', '5', 'N/A', '0', '11', '13']]],
    ['week', [['2026-W44', '2', 'N/A', '0', '11', '13'], ['2026-W45', '8', 'N/A', '0', '22', '26']]],
    ['month', [['2026-10', '2', 'N/A', '0', '11', '13'], ['2026-11', '8', 'N/A', '0', '22', '26']]],
  ]) {
    test(`event dashboard: ${grain} aggregates only actual UTC observations with nullable precision evidence`, async ({ page }) => {
      const state = await interceptEvents(page);
      await page.goto('/dashboard?grain=' + grain);
      await expect(page.locator('[data-event-activity-state]')).toContainText('Partial');
      await expect(eventRows(page)).toHaveCount(expected.length);
      for (let index = 0; index < expected.length; index += 1) {
        await expect(eventRows(page).nth(index).locator('td')).toHaveText(expected[expected.length - index - 1]);
      }
      const latest = eventRows(page).first();
      const multiplier = grain === 'day' ? 1 : 2;
      await expect(latest.locator('td').nth(2)).toHaveAttribute('title', new RegExp(`provider reported=0, estimated=${multiplier}, unavailable=${2 * multiplier}, unknown=${3 * multiplier}, mixed=${4 * multiplier}`));
      await expect(latest.locator('td').nth(4)).toHaveAttribute('title', new RegExp(`provider reported=${2 * multiplier}, estimated=${3 * multiplier}, unavailable=${4 * multiplier}, unknown=${5 * multiplier}, mixed=${6 * multiplier}`));
      await expect(page.locator('[data-event-activity-summary]')).toContainText('across the selected sources');
      await page.locator('[data-event-activity-disclosure] summary').click();
      await expect(page.locator('[data-event-activity-coverage]')).toContainText('(7 undated)');
      await expect(page.locator('[data-event-activity-usage]')).toContainText('6 unsupported usage events');
      await expect(page.locator('[data-event-activity-future]')).toContainText('2 excluded day buckets · 9 observed user messages');
      await expect(page.locator('[data-event-activity-future]')).toContainText('Entire mixed day buckets');
      await expect(page.locator('[data-event-activity-undated]')).toContainText('never assigned to a date');
      await expect(page.locator('[data-event-activity-undated]')).toContainText('Fresh: N/A');
      await expect(page.locator('[data-event-activity-undated]')).toContainText('Cache read: 0');
      expect(state.requests.at(-1)).toMatchObject({ agent: 'all', grain, days: grain === 'day' ? '30' : grain === 'week' ? '140' : '366' });
      await expectHealthyCohort(page);
    });
  }

  test('event dashboard: real grain and agent controls reload filters and observation rows', async ({ page }) => {
    const state = await interceptEvents(page);
    await page.goto('/dashboard?grain=day');
    await expect(eventRows(page)).toHaveCount(3);
    await page.locator('[data-action="grain"][data-grain="week"]').click();
    await expect(page).toHaveURL(/grain=week/);
    await expect(eventRows(page)).toHaveCount(2);
    await expect(eventRows(page).first().locator('td').nth(1)).toHaveText('8');
    await page.locator('[data-action="agent-scope"][data-scope="codex"]').click();
    await expect(page).toHaveURL(/agent=codex/);
    await expect(eventRows(page).first().locator('td').nth(1)).toHaveText('16');
    expect(state.requests.at(-1)).toMatchObject({ agent: 'codex', grain: 'week', days: '140' });
    await expectHealthyCohort(page);
  });

  test('event dashboard: empty unknown and 501 retry recover without blocking cohort KPIs', async ({ page }) => {
    const state = await interceptEvents(page, { empty: true });
    await page.goto('/dashboard');
    await expect(page.locator('[data-event-activity-state]')).toContainText('Unknown');
    await expect(eventRows(page)).toHaveCount(0);
    const empty = page.locator('[data-event-activity-empty]');
    await expect(empty).toBeVisible();
    await expect(empty).toContainText('No observed event dates');
    await expect(empty).toContainText('not measured zero');
    await expectHealthyCohort(page);
    state.unavailable = true;
    await page.reload();
    await expect(page.locator('[data-event-activity-state]')).toContainText('HTTP 501');
    await expect(page.locator('[data-event-activity-state]')).toHaveAttribute('role', 'status');
    await expect(eventRows(page)).toHaveCount(0);
    await expectHealthyCohort(page);
    const before = state.requests.length;
    state.unavailable = false;
    state.empty = false;
    await page.getByRole('button', { name: 'Retry event activity', exact: true }).click();
    await expect(page.locator('[data-event-activity-state]')).toContainText('Partial');
    await expect(eventRows(page)).toHaveCount(3);
    expect(state.requests.length).toBeGreaterThan(before);
    await expectHealthyCohort(page);
  });

  test('event dashboard: narrow viewport keeps table scrolling local without document overflow', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await interceptEvents(page);
    await page.goto('/dashboard');
    await expect(eventRows(page)).toHaveCount(3);
    const geometry = await page.locator('.event-activity-scroll').evaluate(node => ({
      client: node.clientWidth, content: node.scrollWidth, overflow: getComputedStyle(node).overflowX,
      documentWidth: document.documentElement.scrollWidth, viewport: window.innerWidth,
    }));
    expect(geometry.overflow).toBe('auto');
    expect(geometry.content).toBeGreaterThan(geometry.client);
    expect(geometry.documentWidth).toBeLessThanOrEqual(geometry.viewport + 1);
    await page.locator('.event-activity-scroll').evaluate(node => { node.scrollLeft = node.scrollWidth; });
    expect(await page.locator('.event-activity-scroll').evaluate(node => node.scrollLeft)).toBeGreaterThan(0);
    await expectHealthyCohort(page);
  });
});

// C14: SSR-only values cannot be silently retained while another generation hydrates.
test.describe('SSR document generation hydration boundary:', () => {
  async function openSsrGenerationProbe(page, apiGeneration, options = {}) {
    const fs = require('fs');
    const path = require('path');
    const runtime = fs.readFileSync(path.resolve(__dirname,
      '../../web/src/main/resources/static/js/index-snapshot.js'), 'utf8');
    const state = { documents: 0, apiRequests: [], applies: [], errors: [] };
    await page.exposeFunction('recordC14Apply', value => { state.applies.push(value); });
    await page.exposeFunction('recordC14Error', value => { state.errors.push(value); });
    await page.route('**/c14-snapshot-runtime.js', route => route.fulfill({
      contentType: 'application/javascript', body: runtime,
    }));
    await page.route('**/api/c14-ssr-probe/*', route => {
      const key = new URL(route.request().url()).pathname.split('/').at(-1);
      state.apiRequests.push({ key, expected: route.request().headers()['x-session-index-generation'] || '' });
      if (options.networkFailure && key === 'chart') return route.abort('failed');
      const chart = key === 'chart';
      const generation = chart && options.chartGeneration !== undefined ? options.chartGeneration : apiGeneration;
      const headers = { 'Content-Type': 'application/json',
        ...((options.headerless || (chart && options.chartHeaderless)) ? {} : { 'X-Session-Index-Generation': generation }) };
      const status = chart && options.optional501 ? 501 : chart && options.chartStatus ? options.chartStatus : options.status || 200;
      if (chart && options.malformedChart) return route.fulfill({ status, headers, body: '{invalid' });
      return route.fulfill({ status, headers, json: { generation, key } });
    });
    await page.route('**/c14-ssr-probe', route => {
      state.documents += 1;
      // A full document recovery obtains the newly published document, not another A shell.
      const generation = state.documents === 1 ? 'A' : apiGeneration;
      return route.fulfill({ headers: { 'Content-Type': 'text/html',
        'X-Session-Index-Generation': generation }, body: `<!doctype html>
        <html><head><title>Synthetic SSR generation boundary</title></head>
        <body data-index-generation="${generation}"><main>
          <p id="c14-primary">SSR-${generation}</p>
          <p id="c14-ssr-only-aux">aux-${generation}</p>
          <p id="c14-chart">SSR-chart-${generation}</p>
        </main><script src="/c14-snapshot-runtime.js"></script><script>
          const documentGeneration = document.body.dataset.indexGeneration;
          const optionalChart = ${!!options.optional501};
          window.c14ApplyHistory = [];
          window.c14LoadComplete = false;
          window.IndexSnapshot.create().load(['primary', 'chart'].map(key => ({
            key: 'c14/' + key, url: '/api/c14-ssr-probe/' + key,
            unavailableStatus: optionalChart && key === 'chart' ? 501 : undefined,
            error: optionalChart && key === 'chart' ? function(error) {
              window.recordC14Error(error.message);
              document.getElementById('c14-chart').textContent = 'Unknown ' + error.message;
            } : undefined,
            apply(data) {
              const evidence = { key, documentGeneration, apiGeneration: data.generation };
              window.c14ApplyHistory.push(evidence);
              window.recordC14Apply(evidence);
              document.getElementById('c14-' + key).textContent = 'API-' + data.generation;
            }
          }))).finally(() => { window.c14LoadComplete = true; });
        </script></body></html>` });
    });
    await page.goto('/c14-ssr-probe');
    return state;
  }

  test('SSR A plus API B blocks before every apply or recovers the entire document', async ({ page }) => {
    const state = await openSsrGenerationProbe(page, 'B');
    await expect.poll(async () => page.evaluate(() => {
      const main = document.querySelector('main');
      const primary = document.getElementById('c14-primary')?.textContent;
      const auxiliary = document.getElementById('c14-ssr-only-aux')?.textContent;
      const alert = document.querySelector('[role="alert"]');
      if (main?.hidden && alert?.textContent.trim()) return 'blocked';
      if (document.body.dataset.indexGeneration === 'B'
          && primary === 'API-B' && auxiliary === 'aux-B') return 'recovered';
      return 'unsettled';
    })).toMatch(/^(blocked|recovered)$/);
    // This history survives document reloads. Even a transient B apply into A is forbidden.
    expect(state.applies.filter(row => row.documentGeneration !== row.apiGeneration)).toEqual([]);
    expect(state.apiRequests.length).toBeGreaterThanOrEqual(2);
    expect(state.documents).toBeLessThanOrEqual(2);
    const blocked = await page.locator('main').isHidden();
    if (blocked) {
      await expect(page.locator('[role="alert"]').first()).toBeVisible();
      await expect(page.locator('[role="alert"]').first()).toContainText(/snapshot|generation|index|reload|refresh/i);
      expect(state.applies).toEqual([]);
      await expect(page.locator('#c14-primary')).toHaveText('SSR-A');
      await expect(page.locator('#c14-ssr-only-aux')).toHaveText('aux-A');
      // The recovery control must reload the document, not retry only API hydration.
      await page.getByRole('button', { name: 'Reload entire page', exact: true }).click();
    }
    await expect(page.locator('main')).toBeVisible();
    await expect(page.locator('#c14-primary')).toHaveText('API-B');
    await expect(page.locator('#c14-chart')).toHaveText('API-B');
    await expect(page.locator('#c14-ssr-only-aux')).toHaveText('aux-B');
    await expect(page.locator('body')).toHaveAttribute('data-index-generation', 'B');
    await expect(page.locator('[data-snapshot-error], [data-snapshot-batch-error]')).toHaveCount(0);
    await expect.poll(() => state.applies.filter(row => row.documentGeneration === 'B').length).toBe(2);
    expect(state.applies.filter(row => row.documentGeneration !== row.apiGeneration)).toEqual([]);
    expect(state.documents).toBe(2);
  });

  test('SSR A plus API A applies the full batch and preserves same-generation auxiliary values', async ({ page }) => {
    const state = await openSsrGenerationProbe(page, 'A');
    await expect(page.locator('#c14-primary')).toHaveText('API-A');
    await expect(page.locator('#c14-chart')).toHaveText('API-A');
    await expect(page.locator('#c14-ssr-only-aux')).toHaveText('aux-A');
    await expect(page.locator('body')).toHaveAttribute('data-index-generation', 'A');
    await expect(page.locator('main')).toBeVisible();
    await expect(page.locator('[data-snapshot-error], [data-snapshot-batch-error]')).toHaveCount(0);
    await expect.poll(() => state.applies.length).toBe(2);
    expect(state.applies.map(row => [row.documentGeneration, row.apiGeneration])).toEqual([['A', 'A'], ['A', 'A']]);
    expect(state.apiRequests).toHaveLength(2);
    expect(state.documents).toBe(1);
  });

  for (const [scenario, options] of [['headerless', { headerless: true }], ['HTTP 409', { status: 409 }]]) {
    test(`SSR A cannot downgrade through ${scenario} API responses`, async ({ page }) => {
      const state = await openSsrGenerationProbe(page, 'A', options);
      await expect(page.locator('main')).toBeHidden();
      await expect(page.locator('[data-snapshot-batch-error]')).toContainText(/generation.*document/i);
      await expect(page.getByRole('button', { name: 'Reload entire page', exact: true })).toBeVisible();
      await expect(page.locator('#c14-primary')).toHaveText('SSR-A');
      await expect(page.locator('#c14-chart')).toHaveText('SSR-chart-A');
      await expect(page.locator('#c14-ssr-only-aux')).toHaveText('aux-A');
      expect(state.applies).toEqual([]);
      expect(state.documents).toBe(1);
      expect(state.apiRequests).toHaveLength(2);
      expect(state.apiRequests.map(request => request.expected)).toEqual(['A', 'A']);
    });
  }


  test('SSR-bound optional 501 with stamp A permits only the required same-generation apply', async ({ page }) => {
    const state = await openSsrGenerationProbe(page, 'A', { optional501: true });
    await expect(page.locator('#c14-primary')).toHaveText('API-A');
    await expect(page.locator('#c14-chart')).toHaveText('Unknown HTTP 501');
    await expect(page.locator('#c14-ssr-only-aux')).toHaveText('aux-A');
    await expect(page.locator('main')).toBeVisible();
    await expect(page.locator('body')).toHaveAttribute('data-index-generation', 'A');
    await expect(page.locator('[data-snapshot-error], [data-snapshot-batch-error]')).toHaveCount(0);
    await expect.poll(() => state.applies.length).toBe(1);
    expect(state.applies).toEqual([{ key: 'primary', documentGeneration: 'A', apiGeneration: 'A' }]);
    await expect.poll(() => state.errors).toEqual(['HTTP 501']);
    expect(state.documents).toBe(1);
    expect(state.apiRequests).toHaveLength(2);
  });

  for (const [scenario, options] of [['stamp B', { chartGeneration: 'B' }], ['missing stamp', { chartHeaderless: true }]]) {
    test(`SSR-bound optional 501 with ${scenario} blocks the entire batch before callbacks`, async ({ page }) => {
      const state = await openSsrGenerationProbe(page, 'A', { optional501: true, ...options });
      await expect(page.locator('main')).toBeHidden();
      await expect(page.locator('[data-snapshot-batch-error]')).toContainText(/generation.*document/i);
      await expect(page.getByRole('button', { name: 'Reload entire page', exact: true })).toBeVisible();
      await expect(page.locator('#c14-primary')).toHaveText('SSR-A');
      await expect(page.locator('#c14-chart')).toHaveText('SSR-chart-A');
      await expect(page.locator('#c14-ssr-only-aux')).toHaveText('aux-A');
      await expect(page.locator('body')).toHaveAttribute('data-index-generation', 'A');
      expect(state.applies).toEqual([]);
      expect(state.errors).toEqual([]);
      expect(state.documents).toBe(1);
      expect(state.apiRequests).toHaveLength(2);
    });
  }

  for (const [scenario, initial] of [['network failure', { networkFailure: true }], ['malformed JSON', { malformedChart: true }], ['HTTP 500', { chartStatus: 500 }]]) {
    test(`SSR-bound same-generation ${scenario} preserves independent resources and pins retry to the document`, async ({ page }) => {
      const options = { ...initial };
      const state = await openSsrGenerationProbe(page, 'A', options);
      const error = page.locator('[data-snapshot-error="c14/chart"]');
      await expect(page.locator('main')).toBeVisible();
      await expect(page.locator('#c14-primary')).toHaveText('API-A');
      await expect(page.locator('#c14-chart')).toHaveText('SSR-chart-A');
      await expect(page.locator('#c14-ssr-only-aux')).toHaveText('aux-A');
      await expect(error).toBeVisible();
      if (scenario === 'HTTP 500') await expect(error).toContainText('HTTP 500');
      await expect(page.locator('[data-snapshot-batch-error]')).toHaveCount(0);
      await expect(page.locator('body')).toHaveAttribute('data-index-generation', 'A');
      await expect.poll(() => state.applies.length).toBe(1);
      expect(state.applies).toEqual([{ key: 'primary', documentGeneration: 'A', apiGeneration: 'A' }]);
      Object.assign(options, { networkFailure: false, malformedChart: false, chartStatus: 200 });
      await error.getByRole('button', { name: 'Retry', exact: true }).click();
      await expect(page.locator('#c14-chart')).toHaveText('API-A');
      await expect(error).toHaveCount(0);
      await expect.poll(() => state.applies.length).toBe(2);
      expect(state.applies.map(row => [row.documentGeneration, row.apiGeneration])).toEqual([['A', 'A'], ['A', 'A']]);
      expect(state.documents).toBe(1);
      expect(state.apiRequests.map(request => request.expected)).toEqual(['A', 'A', 'A']);
    });
  }

});

// Actual personal page job wiring, with its real SSR stamp and unmodified fixture business data.
test.describe('real page SSR generation boundary integration:', () => {
  for (const item of [
    { path: '/', prefix: '/api/dashboard/' },
    { path: '/projects', prefix: '/api/projects/' },
    { path: '/projects/test-hifi-project', prefix: '/api/projects/test-hifi-project/' },
    { path: '/sessions', prefix: '/api/sessions/' },
    { path: SESSION_PATH, prefix: '/api/sessions/claude_code/hifi-viz-session-001/' },
  ]) {
    test(`real SSR page ${item.path} rejects another API generation before apply and recovers by full reload`, async ({ page }) => {
      const state = { recover: false, documents: 0, stamps: [] };
      page.on('request', request => {
        if (request.isNavigationRequest() && request.resourceType() === 'document') state.documents += 1;
      });
      // Observe the actual page's jobs, rather than substituting a synthetic dashboard loader.
      await page.addInitScript(() => {
        window.c14RealPageApplyCount = 0;
        let implementation;
        Object.defineProperty(window, 'IndexSnapshot', {
          configurable: true,
          get() { return implementation; },
          set(value) {
            const create = value.create;
            value.create = function (...args) {
              const snapshot = create.apply(this, args);
              const load = snapshot.load;
              snapshot.load = function (jobs) {
                return load.call(snapshot, jobs.map(job => ({ ...job,
                  apply(data) {
                    window.c14RealPageApplyCount += 1;
                    return job.apply(data);
                  },
                })));
              };
              return snapshot;
            };
            implementation = value;
          },
        });
      });
      await page.route('**/api/**', async route => {
        const pathname = new URL(route.request().url()).pathname;
        if (!pathname.startsWith(item.prefix)) return route.continue();
        // Fetch with the real SSR stamp; never forward the invented response stamp to the guard.
        const response = await route.fetch();
        const realStamp = response.headers()['x-session-index-generation'];
        state.stamps.push(realStamp);
        if (state.recover) return route.fulfill({ response });
        return route.fulfill({ response, headers: { ...response.headers(),
          'x-session-index-generation': realStamp + '-synthetic-other-generation' } });
      });
      await page.goto(item.path);
      await expect(page.locator('main')).toBeHidden();
      await expect(page.locator('[data-snapshot-batch-error]')).toContainText(/generation.*document/i);
      const initialStamp = await page.locator('body').getAttribute('data-index-generation');
      expect(initialStamp).toBeTruthy();
      expect(state.stamps.length).toBeGreaterThan(0);
      expect(state.stamps.every(stamp => stamp === initialStamp)).toBe(true);
      expect(await page.evaluate(() => window.c14RealPageApplyCount)).toBe(0);
      expect(state.documents).toBe(1);
      state.recover = true;
      const navigation = page.waitForEvent('load');
      await page.getByRole('button', { name: 'Reload entire page', exact: true }).click();
      await navigation;
      await expect.poll(() => page.evaluate(() => window.c14RealPageApplyCount)).toBeGreaterThan(0);
      await expect(page.locator('main')).toBeVisible();
      await expect(page.locator('body')).toHaveAttribute('data-index-generation', initialStamp);
      await expect(page.locator('[data-snapshot-error], [data-snapshot-batch-error], [data-resource-error]')).toHaveCount(0);
      expect(state.documents).toBe(2);
      expect(state.stamps.every(stamp => stamp === initialStamp)).toBe(true);
      if (item.path === SESSION_PATH) await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
    });
  }
});

// Exercise the exact fixture proxy without importing its server-starting CLI entrypoint.
test.describe('fixture identity proxy transport lifecycle regressions', () => {
  const http = require('node:http');
  const fs = require('node:fs');
  const path = require('node:path');
  const vm = require('node:vm');

  async function withIdentityProxy(upstreamHandler, exercise) {
    const ownedSockets = new Set();
    const ownedServers = [];
    function ownSocket(socket) {
      ownedSockets.add(socket);
      socket.on('error', () => {});
      socket.once('close', () => ownedSockets.delete(socket));
    }
    function ownServer(server) {
      ownedServers.push(server);
      server.on('connection', ownSocket);
      return server;
    }
    // Observe errors so an old proxy's missing error handler cannot escape the test.
    // These observers never forward, end, destroy, or otherwise repair either stream.
    const observedHttp = {
      createServer: (...args) => ownServer(http.createServer(...args)),
      request: (...args) => {
        const request = http.request(...args);
        request.on('socket', ownSocket);
        request.on('error', () => {});
        request.on('response', response => response.on('error', () => {}));
        return request;
      },
    };
    const source = fs.readFileSync(path.join(__dirname, 'start-java-fixture-server.js'), 'utf8');
    const start = source.indexOf('function startIdentityProxy(');
    const end = source.indexOf('\nfunction runChecked(', start);
    expect(start).toBeGreaterThanOrEqual(0);
    expect(end).toBeGreaterThan(start);
    const startIdentityProxy = vm.runInNewContext(
      `(${source.slice(start, end).trim()})`,
      { http: observedHttp, FIXTURE_IDENTITY: Object.freeze({ synthetic: true }), console },
    );
    try {
      const upstream = ownServer(http.createServer(upstreamHandler));
      await new Promise((resolve, reject) => {
        upstream.once('error', reject);
        upstream.listen(0, '127.0.0.1', resolve);
      });
      const proxy = await startIdentityProxy(0, upstream.address().port);
      const request = (callback, pathname = '/synthetic-transport-probe', agent = false) => {
        const client = http.get({ host: '127.0.0.1', port: proxy.address().port,
          path: pathname, agent }, callback);
        client.on('socket', ownSocket);
        client.on('error', () => {});
        return client;
      };
      await exercise(request);
    } finally {
      // Failed old implementations leave streams open: cleanup must not await their cooperation.
      for (const socket of ownedSockets) socket.destroy();
      await Promise.all(ownedServers.map(server => new Promise(resolve => {
        if (!server.listening) return resolve();
        server.close(resolve);
        server.closeAllConnections();
      })));
    }
  }

  test('upstream mid-body abort explicitly fails the downstream response', async () => {
    let upstreamResponse;
    let outcome = 'pending';
    await withIdentityProxy((request, response) => {
      upstreamResponse = response;
      response.writeHead(200, { 'content-type': 'text/plain', 'content-length': '100' });
      response.write('x');
    }, async request => {
      const client = request(response => {
        response.on('aborted', () => { outcome = 'failed'; });
        response.on('error', () => { outcome = 'failed'; });
        response.on('end', () => { outcome = response.complete ? 'success' : 'failed'; });
        response.on('close', () => { if (!response.complete) outcome = 'failed'; });
        // Abort only after the first byte reached the downstream, not before headers.
        response.once('data', () => upstreamResponse.socket.destroy());
        response.resume();
      });
      client.on('error', () => { outcome = 'failed'; });
      await expect.poll(() => outcome).toBe('failed');
    });
  });

  test('downstream client abort releases the unfinished upstream response', async () => {
    let upstreamClosed = false;
    let upstreamFinished = false;
    let downstreamReceivedBody = false;
    await withIdentityProxy((request, response) => {
      response.on('close', () => { upstreamClosed = true; });
      response.on('finish', () => { upstreamFinished = true; });
      response.writeHead(200, { 'content-type': 'text/plain', 'content-length': '100' });
      response.write('x');
    }, async request => {
      const client = request(response => {
        response.on('error', () => {});
        response.once('data', () => {
          downstreamReceivedBody = true;
          client.destroy();
        });
        response.resume();
      });
      await expect.poll(() => downstreamReceivedBody).toBe(true);
      await expect.poll(() => upstreamClosed).toBe(true);
      expect(upstreamFinished).toBe(false);
    });
  });

  test('complete bodies and identity never pool the fixture downstream socket', async () => {
    let upstreamRequests = 0;
    await withIdentityProxy((request, response) => {
      upstreamRequests += 1;
      response.writeHead(200, { 'content-type': 'text/plain', 'content-length': '4',
        'connection': 'keep-alive', 'keep-alive': 'timeout=30',
        'x-synthetic-passthrough': 'yes' });
      response.end('done');
    }, async request => {
      const agent = new http.Agent({ keepAlive: true });
      function read(pathname) {
        return new Promise((resolve, reject) => {
          const client = request(response => {
            let body = '';
            response.setEncoding('utf8');
            response.on('data', chunk => { body += chunk; });
            response.on('error', reject);
            response.on('aborted', () => reject(new Error('complete response aborted')));
            response.on('end', () => resolve({ status: response.statusCode,
              headers: response.headers, complete: response.complete, body, reused: client.reusedSocket }));
          }, pathname, agent);
          client.on('error', reject);
        });
      }
      try {
        const normal = await read('/synthetic-transport-probe');
        expect(normal).toMatchObject({ status: 200, complete: true, body: 'done' });
        expect(normal.headers['x-synthetic-passthrough']).toBe('yes');
        expect(normal.headers.connection).toBe('close');
        expect(normal.headers['keep-alive']).toBeUndefined();
        const next = await read('/synthetic-transport-probe');
        expect(next).toMatchObject({ status: 200, complete: true, body: 'done', reused: false });
        const identity = await read('/__feipi_fixture_identity');
        expect(identity).toMatchObject({ status: 200, complete: true });
        expect(identity.headers.connection).toBe('close');
        expect(JSON.parse(identity.body)).toEqual({ synthetic: true });
        expect(upstreamRequests).toBe(2);
      } finally {
        agent.destroy();
      }
    });
  });

  test('upstream error before headers returns an explicit complete 502', async () => {
    await withIdentityProxy(request => request.socket.destroy(), async request => {
      const result = await new Promise((resolve, reject) => {
        const client = request(response => {
          let body = '';
          response.setEncoding('utf8');
          response.on('data', chunk => { body += chunk; });
          response.on('error', reject);
          response.on('aborted', () => reject(new Error('502 response aborted')));
          response.on('end', () => resolve({ status: response.statusCode,
            complete: response.complete, body }));
        });
        client.on('error', reject);
      });
      expect(result.status).toBe(502);
      expect(result.complete).toBe(true);
      expect(result.body).toBe('fixture upstream unavailable');
    });
  });

});

// C15: finite cache observations separated by unknown buckets still need visible strokes.
test.describe('cache trend isolated known bucket regressions:', () => {
  const provider = { freshInput: 'provider_reported', cacheRead: 'provider_reported',
    cacheWrite: 'provider_reported', output: 'provider_reported' };
  const unknown = { freshInput: 'unknown', cacheRead: 'unknown', cacheWrite: 'unknown', output: 'unknown' };
  const scenarios = [
    { name: 'single measured zero baseline', days: [['2026-11-03', null], ['2026-11-04', 0], ['2026-11-05', null]] },
    { name: 'two isolated observations including measured zero', days: [['2026-11-03', 0], ['2026-11-04', null], ['2026-11-05', 50]] },
    { name: 'one island and a separate two-point segment', days: [['2026-11-01', 0], ['2026-11-02', null], ['2026-11-03', 25], ['2026-11-04', 75], ['2026-11-05', null]] },
  ];
  const indexForDate = date => Math.round((Date.parse(date + 'T00:00:00Z') - Date.parse('2026-10-07T00:00:00Z')) / 86400000);
  const xForDate = date => (indexForDate(date) + 0.5) / 30 * 100;
  const yForRatio = ratio => 95 - ratio * 0.9; // All scenarios include measured zero: domain 0..100, 5% inset.

  for (const scenario of scenarios) {
    test(`${scenario.name}: coordinates, visible strokes, gap topology and tooltip measurements`, async ({ page }) => {
      const path = require('path');
      await page.clock.setFixedTime(new Date('2026-11-05T12:00:00Z'));
      await page.route('**/static/js/dashboard.js*', route => route.fulfill({
        path: path.resolve(__dirname, '../../web/src/main/resources/static/js/dashboard.js'),
        contentType: 'application/javascript',
      }));
      await page.route('**/api/dashboard/trends/cache-health*', route => {
        const points = scenario.days.map(([date, value]) => {
          const tuple = value === null
            ? { fresh: null, cacheRead: null, cacheWrite: null, provenance: unknown,
              ratio: { value: null, provenance: unknown } }
            : { fresh: 100 - value, cacheRead: value, cacheWrite: 0, provenance: provider,
              ratio: { value: value / 100, provenance: provider } };
          return { date, average: tuple, codex: tuple };
        });
        // Keep the actual indexed fixture's generation; only replace synthetic business payload.
        return fulfillIndexedJson(route, { points });
      });
      await page.goto('/dashboard?grain=day');
      const chart = page.locator('#cache-health-chart');
      const line = chart.locator('path.line-series--average');
      const markers = chart.locator('line.line-isolated-marker.line-series--average');
      const finite = scenario.days.filter(([, value]) => value !== null);
      const islands = finite.filter(([date]) => {
        const index = indexForDate(date);
        return !finite.some(([other]) => Math.abs(indexForDate(other) - index) === 1);
      });
      await expect(chart.locator('.chart-hover-target')).toHaveCount(30);
      await expect(markers).toHaveCount(islands.length);
      await expect(chart.locator('svg.line-plot')).toBeVisible();
      let previousIndex = -2;
      const expectedCommands = finite.map(([date, value]) => {
        const index = indexForDate(date);
        const command = index === previousIndex + 1 ? 'L' : 'M';
        previousIndex = index;
        return `${command} ${xForDate(date).toFixed(2)},${yForRatio(value).toFixed(2)}`;
      });
      await expect(line).toHaveAttribute('d', expectedCommands.join(' '));
      // Only adjacent known buckets form L segments; unknown buckets never connect or become zero.
      expect(expectedCommands.filter(command => command.startsWith('L')).length)
        .toBe(scenario.name.includes('two-point segment') ? 1 : 0);
      for (let index = 0; index < islands.length; index += 1) {
        const [date, value] = islands[index];
        const marker = markers.nth(index);
        // A horizontal SVG line has zero geometric height; verify its painted stroke, not HTML visibility heuristics.
        await expect(marker).toHaveAttribute('x1', (xForDate(date) - 1.2).toFixed(2));
        await expect(marker).toHaveAttribute('x2', (xForDate(date) + 1.2).toFixed(2));
        await expect(marker).toHaveAttribute('y1', yForRatio(value).toFixed(2));
        await expect(marker).toHaveAttribute('y2', yForRatio(value).toFixed(2));
        const geometry = await marker.evaluate(node => {
          const box = node.getBBox();
          const screen = node.getBoundingClientRect();
          const style = getComputedStyle(node);
          return { length: node.getTotalLength(), width: box.width, screenWidth: screen.width,
            stroke: style.stroke, visibility: style.visibility, display: style.display, strokeWidth: parseFloat(style.strokeWidth), opacity: parseFloat(style.opacity) };
        });
        expect(geometry.length).toBeGreaterThan(0);
        expect(geometry.width).toBeGreaterThan(0);
        expect(geometry.screenWidth).toBeGreaterThan(0);
        expect(geometry.stroke).not.toBe('none');
        expect(geometry.visibility).toBe('visible');
        expect(geometry.display).not.toBe('none');
        expect(geometry.strokeWidth).toBeGreaterThan(0);
        expect(geometry.opacity).toBeGreaterThan(0);
      }
      for (const [date, value] of scenario.days) {
        const target = chart.locator('.chart-hover-target').nth(indexForDate(date));
        await expect(target.locator('.line-point')).toHaveCount(value === null ? 0 : 1);
        await target.hover();
        const tooltip = target.locator('.dashboard-tooltip');
        await expect(tooltip).toBeVisible();
        await expect(tooltip.locator('.tooltip-date')).toHaveText(date.slice(5));
        const average = tooltip.locator('.tooltip-row').filter({ has: page.locator('.tooltip-label', { hasText: /^Average$/ }) });
        await expect(average.locator('.tooltip-value')).toHaveText(value === null ? 'N/A' : value.toFixed(1) + '%');
        const input = tooltip.locator('.tooltip-row').filter({ has: page.locator('.tooltip-label', { hasText: /^Input-side Tokens$/ }) });
        await expect(input.locator('.tooltip-value')).toHaveText(value === null ? 'N/A' : '100');
      }
      await expect(page.locator('[data-snapshot-error], [data-snapshot-batch-error]')).toHaveCount(0);
    });
  }
});

// C16: zero consumption is still an inspectable date bucket, not a fabricated positive column.
test.describe('zero bar mouse hover regressions:', () => {
  const indexForDate = date => Math.round((Date.parse(date + 'T00:00:00Z') - Date.parse('2026-10-07T00:00:00Z')) / 86400000);
  async function prepareZeroBars(page) {
    const path = require('path');
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.clock.setFixedTime(new Date('2026-11-05T12:00:00Z'));
    await page.route('**/static/js/dashboard.js*', route => route.fulfill({
      path: path.resolve(__dirname, '../../web/src/main/resources/static/js/dashboard.js'), contentType: 'application/javascript',
    }));
    await page.route('**/api/dashboard/trends/sessions*', route => fulfillIndexedJson(route, {
      points: [['2026-11-01', 4], ['2026-11-02', 2], ['2026-11-03', 1], ['2026-11-05', 0]]
        .map(([date, count]) => ({ date, totalCount: count, codexCount: count, claudeCount: 0, qoderCount: 0, toolCalls: 0, failedTools: 0 })),
    }));
    await page.route('**/api/dashboard/trends/prompts*', route => fulfillIndexedJson(route, {
      points: [['2026-11-01', 8, 4], ['2026-11-02', 4, 2], ['2026-11-03', 0, 1], ['2026-11-05', 0, 0]]
        .map(([date, messages, samples]) => ({ date, totalPrompts: messages, codexPrompts: messages,
          claudePrompts: 0, qoderPrompts: 0, assistantTurns: 0, toolCalls: 0,
          measuredUserMessages: messages, userMessageSampleCount: samples,
          codexMeasuredUserMessages: messages, codexUserMessageSampleCount: samples,
          claudeMeasuredUserMessages: 0, claudeUserMessageSampleCount: 0,
          qoderMeasuredUserMessages: 0, qoderUserMessageSampleCount: 0 })),
    }));
    // Payload-only mocks preserve actual fixture SSR stamps and every API generation header.
    await page.goto('/dashboard?grain=day');
  }
  async function expectTruePositiveColumns(chart) {
    const stacks = await Promise.all(['2026-11-01', '2026-11-02'].map(date =>
      chart.locator('.bar').nth(indexForDate(date)).locator('.bar-stack').boundingBox()));
    expect(stacks.every(box => box && box.height > 0)).toBe(true);
    expect(stacks[1].height / stacks[0].height).toBeCloseTo(0.5, 2);
  }
  function row(tooltip, label, page) {
    return tooltip.locator('.tooltip-row').filter({ has: page.locator('.tooltip-label', { hasText: new RegExp('^' + label + '$') }) });
  }

  test('Sessions known zero and padded empty dates are real mouse targets with truthful zero stacks', async ({ page }) => {
    await prepareZeroBars(page);
    const chart = page.locator('#trend-chart');
    await expect(chart.locator('.bar')).toHaveCount(30);
    await expectTruePositiveColumns(chart);
    for (const date of ['2026-11-05', '2026-11-04']) {
      const bar = chart.locator('.bar').nth(indexForDate(date));
      await expect(bar.locator('.bar-stack > span')).toHaveCount(0);
      const stackHeight = await bar.locator('.bar-stack').evaluate(node => node.getBoundingClientRect().height);
      expect(stackHeight).toBe(0);
      // Genuine pointer motion only: no force, synthetic hover class, or style injection.
      await bar.hover();
      const tooltip = bar.locator('.dashboard-tooltip');
      await expect(tooltip).toBeVisible();
      await expect(tooltip.locator('.tooltip-date')).toHaveText(date.slice(5));
      await expect(row(tooltip, 'Total', page).locator('.tooltip-value')).toHaveText('0');
      for (const agent of ['Claude Code', 'Codex', 'Qoder']) {
        await expect(row(tooltip, agent, page).locator('.tooltip-value')).toHaveText('0');
      }
    }
    await expectTruePositiveColumns(chart);
    await expect(page.locator('[data-snapshot-error], [data-snapshot-batch-error]')).toHaveCount(0);
  });

  test('Prompts measured zero and empty dates expose distinct measured samples through genuine mouse hover', async ({ page }) => {
    await prepareZeroBars(page);
    const chart = page.locator('#prompt-activity-chart');
    await expect(chart.locator('.bar')).toHaveCount(30);
    await expectTruePositiveColumns(chart);
    for (const [date, average, samples] of [['2026-11-03', '0.0', '1 / 1'], ['2026-11-04', 'N/A', '0 / 0']]) {
      const bar = chart.locator('.bar').nth(indexForDate(date));
      await expect(bar.locator('.bar-stack > span')).toHaveCount(0);
      const stackHeight = await bar.locator('.bar-stack').evaluate(node => node.getBoundingClientRect().height);
      expect(stackHeight).toBe(0);
      await bar.hover();
      const tooltip = bar.locator('.dashboard-tooltip');
      await expect(tooltip).toBeVisible();
      await expect(tooltip.locator('.tooltip-date')).toHaveText(date.slice(5));
      await expect(row(tooltip, 'Total User Prompts', page).locator('.tooltip-value')).toHaveText('0');
      const overall = row(tooltip, 'Overall', page);
      await expect(overall.locator('.tooltip-value')).toHaveText(average);
      await expect(overall.locator('.tooltip-share')).toHaveText('/ measured session · samples ' + samples + ' cohort');
      await expect(row(tooltip, 'Assistant Messages', page).locator('.tooltip-value')).toHaveText('0');
      await expect(row(tooltip, 'Tool Calls', page).locator('.tooltip-value')).toHaveText('0');
    }
    await expectTruePositiveColumns(chart);
    await expect(page.locator('[data-snapshot-error], [data-snapshot-batch-error]')).toHaveCount(0);
  });
});
test('project detail explains missing tool breakdown without internal codes or API placeholders', async ({ page }) => {
  await page.goto('/projects/test-hifi-project');
  const hotspots = page.locator('[data-project-tool-hotspots]');
  await expect(hotspots).toHaveText('Tool hotspots unavailable: this project has no indexed per-tool breakdown.', { timeout: 2500 });
  await expect(page.locator('.project-detail-kpis')).not.toContainText(/\bSource\s*API\b/);
});

test('project pages show a custom page size and distinguish page count from result count', async ({ page }) => {
  for (const route of ['/projects', '/projects/test-hifi-project']) {
    await page.goto(route + '?page_size=1');
    const pagination = page.getByRole('navigation', { name: 'Pagination' });
    await expect(pagination.locator('[data-action="page-size"]')).toHaveValue('1');
    await expect(pagination).toContainText(route === '/projects' ? /of \d+ · [\d,]+ projects/ : /of \d+ · [\d,]+ sessions/);
  }
});

test('projects overview keeps implementation details out of hydrated cards and the table heading', async ({ page }) => {
  await page.goto('/projects');
  await expect(page.locator('#projects-table a.project-name-link').first()).toBeVisible();
  await expect(page.locator('[aria-label="Project overview metrics"]')).not.toContainText('/api/projects/');
  await expect(page.locator('#projects-table').locator('xpath=ancestor::section[contains(@class,"table-card")]')).not.toContainText('/api/projects/');
});
