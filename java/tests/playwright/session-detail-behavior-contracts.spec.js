const { test, expect } = require('@playwright/test');

const SESSION_PATH = '/sessions/claude_code/hifi-viz-session-001';
const LONG_SESSION_PATH = '/sessions/claude_code/long-session-001';
const ATTRIBUTION_VIEWPORTS = [
  { width: 1440, height: 900 },
  { width: 2560, height: 1440 },
];
const FORBIDDEN_ATTRIBUTION_COPY = [
  'raw request',
  'raw response',
  'raw http request',
  'raw http response',
  '(no rendered content)',
  '(no raw content)',
];
const BROWSER_WARNINGS = new WeakMap();

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

async function openAttribution(page, kind) {
  const button = page
    .locator(`button[data-action="open-payload"][data-payload-kind="llm.${kind}_attribution"]:visible`)
    .first();
  await expect(button, `${kind} attribution trigger must be visible`).toBeVisible({ timeout: 10_000 });
  await button.click();
  const modal = page.locator('dialog.payload-modal');
  await expect.poll(
    () => modal.evaluate((dialog) => dialog.open).catch(() => false),
    { message: `${kind} attribution modal must open`, timeout: 5_000 },
  ).toBe(true);
  await expect(modal, `${kind} attribution API must complete successfully`).toHaveAttribute(
    'data-attribution-state',
    'success',
    { timeout: 10_000 },
  );
  return modal;
}

function detailedAttributionPayload(kind) {
  return {
    kind: `llm.${kind}_attribution`,
    data: {
      callId: 'fixture-call-id-001',
      callKey: 'C1',
      model: 'fixture-detailed-model',
      scope: 'main',
      timestamp: '2026-09-21T10:00:00Z',
      totalTokens: 210,
      freshInputTokens: 120,
      outputTokens: 90,
      cacheReadTokens: 30,
      cacheWriteTokens: 10,
      requestToolResultCount: 3,
      responseToolCallCount: 2,
    },
  };
}

async function installDetailedAttributionRoute(page) {
  await page.route(/\/api\/sessions\/[^/]+\/[^/]+\/attribution\/\d+\/\d+\/(request|response)$/, async (route) => {
    const kind = route.request().url().endsWith('/request') ? 'request' : 'response';
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(detailedAttributionPayload(kind)),
    });
  });
}

async function assertDetailedAttributionContract(page, modal, kind) {
  const visibleText = await modal.innerText();
  const requiredCopy = [
    '基于本地日志重建',
    '不等同于真实提供方',
    '调用身份',
    // h3 使用 text-transform: uppercase，innerText 返回大写形式
    kind === 'request' ? '请求 TOKEN' : '响应 TOKEN',
    '工具计数',
    'Request Tool Results',
    'Response Tool Calls',
  ];
  for (const copy of requiredCopy) {
    expect(visibleText, `${kind} attribution modal must contain ${copy}`).toContain(copy);
  }
  const lowerText = visibleText.toLowerCase();
  for (const copy of FORBIDDEN_ATTRIBUTION_COPY) {
    expect(lowerText, `${kind} attribution modal must not expose ${copy}`).not.toContain(copy);
  }

  // 中文说明：维护当前前端逻辑，原注释作为代码上下文保留：`Verify identity and token cards are present`
  await expect(modal.locator('[data-attribution-card="identity"]')).toBeVisible();
  await expect(modal.locator('[data-attribution-card="tokens"]')).toBeVisible();
  await expect(modal.locator('[data-attribution-card="tool-counts"]')).toBeVisible();

  const geometry = await page.evaluate(() => {
    const dialog = document.querySelector('dialog.payload-modal');
    const rect = (selector) => {
      const element = document.querySelector(selector);
      if (!element) return null;
      const bounds = element.getBoundingClientRect();
      return { left: bounds.left, right: bounds.right, width: bounds.width, height: bounds.height };
    };
    const bounds = dialog.getBoundingClientRect();
    return {
      viewportWidth: window.innerWidth,
      scrollWidth: document.documentElement.scrollWidth,
      modal: { left: bounds.left, right: bounds.right },
      identityGrid: rect('.sd-attribution-identity-grid'),
      summaryGrid: rect('.sd-attribution-summary-grid'),
      toolCountsCard: rect('[data-attribution-card="tool-counts"]'),
    };
  });
  expect(geometry.scrollWidth).toBeLessThanOrEqual(geometry.viewportWidth + 2);
  expect(geometry.modal.left).toBeGreaterThanOrEqual(-2);
  expect(geometry.modal.right).toBeLessThanOrEqual(geometry.viewportWidth + 2);
  for (const key of ['identityGrid', 'summaryGrid', 'toolCountsCard']) {
    expect(geometry[key], `${key} must exist in the current attribution renderer`).not.toBeNull();
    expect(geometry[key].right, `${key} must stay inside the modal`).toBeLessThanOrEqual(geometry.modal.right + 2);
  }
}

test('[UI-SD-036] real Java attribution API summary hydrates the modal', async ({ page }) => {
  await openHydratedSession(page);
  for (const kind of ['request', 'response']) {
    const apiResponse = page.waitForResponse((response) =>
      response.url().includes('/attribution/') && response.url().endsWith(`/${kind}`),
    );
    const modal = await openAttribution(page, kind);
    const response = await apiResponse;
    expect(response.ok()).toBe(true);
    const payload = await response.json();
    expect(payload.kind).toBe(`llm.${kind}_attribution`);
    expect(payload.data.model).toBeTruthy();
    for (const field of [
      'totalTokens',
      'freshInputTokens',
      'outputTokens',
      'cacheReadTokens',
      'cacheWriteTokens',
      'requestToolResultCount',
      'responseToolCallCount',
    ]) {
      expect(typeof payload.data[field], `Java API field ${field} must be numeric`).toBe('number');
    }
    await expect(modal).toContainText(payload.data.model);
    await expect(modal.locator('.sd-payload-error')).toHaveCount(0);
    await page.locator('[data-action="close-payload"], [data-action="close-modal"]').first().click();
    await expect(modal).toBeHidden({ timeout: 5_000 });
  }
});

for (const viewport of ATTRIBUTION_VIEWPORTS) {
  for (const kind of ['request', 'response']) {
    const contractId = kind === 'request' ? 'UI-SD-037' : 'UI-SD-038';
    test(`[${contractId}] ${kind} detailed renderer semantics and geometry @ ${viewport.width}x${viewport.height}`, async ({ page }) => {
      await installDetailedAttributionRoute(page);
      await page.setViewportSize(viewport);
      await openHydratedSession(page);
      const modal = await openAttribution(page, kind);
      await assertDetailedAttributionContract(page, modal, kind);
      await page.locator('[data-action="close-payload"], [data-action="close-modal"]').first().click();
      await expect(modal).toBeHidden({ timeout: 5_000 });
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
  const payloadButton = page
    .locator('button[data-action="open-payload"][data-payload-id]:not([data-payload-kind*="_attribution"]):visible')
    .first();
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
  await expect(modal.locator('.sd-payload-shell')).toBeVisible();
  await expect(modal.locator('.sd-payload-meta')).toContainText('Metadata');
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
