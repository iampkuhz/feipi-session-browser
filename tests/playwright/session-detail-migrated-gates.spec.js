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
  const request = kind === 'request';
  return {
    kind: `llm.${kind}_attribution`,
    data: {
      model: 'fixture-detailed-model',
      source_label: 'local fixture logs',
      call_id: 'fixture-call-1',
      call_identity: {
        agent_runtime: 'claude_code',
        api_family: 'Messages',
        provider_or_broker: 'fixture-provider',
        model: 'fixture-detailed-model',
        billing_units: ['tokens'],
        mapping_confidence: 1,
      },
      timing: { request_at: '10:00:00', response_at: '10:00:01', duration: '1s' },
      usage: request
        ? {
            fresh: { value: 120, precision: 'exact' },
            cache_read: { value: 30, precision: 'provider_reported' },
            cache_write: { value: 10, precision: 'provider_reported' },
            coverage: { value: 1, precision: 'exact' },
            unknown: { value: 0, precision: 'exact' },
          }
        : {
            total_output: { value: 90, precision: 'exact' },
            visible_text: { value: 70, precision: 'exact' },
            tool_call: { value: 20, precision: 'exact' },
            metadata: { value: 0, precision: 'exact' },
            coverage: { value: 1, precision: 'exact' },
            unknown: { value: 0, precision: 'exact' },
          },
      coverage: request
        ? {
            provider_request_input: 160,
            input_side_component_total: 160,
            request_content_denominator: 120,
            reconstructed_total: 120,
            coverage_ratio: 1,
            residual_tokens: 0,
          }
        : null,
      buckets: [
        {
          key: request ? 'current_user_input' : 'tool_call',
          canonical_key: request ? 'current_user_input' : 'tool_call',
          color_key: request ? 'current_user_input' : 'tool_call',
          label: request ? '当前用户输入' : '工具调用',
          tokens: request ? 120 : 90,
          percent: 100,
          precision: 'exact',
          contributes_to_total: true,
          count_label: '1 item',
          details: {
            explanation: ['本地日志中的可见内容用于归因展示。'],
            items: [
              {
                label: request ? '用户消息' : '工具调用 block',
                role: request ? 'user' : 'assistant',
                content_type: request ? 'text' : 'tool_use',
                tokens: request ? 120 : 90,
                summary: '稳定的可见内容摘要',
                full_content: request ? '请分析当前会话。' : '{"name":"Read","input":{"path":"fixture.md"}}',
              },
            ],
          },
        },
      ],
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
    '用量分布',
    '贡献来源',
    kind === 'request' ? '请求摘要' : '响应摘要',
    kind === 'request' ? '当前用户输入' : '工具调用',
  ];
  for (const copy of requiredCopy) {
    expect(visibleText, `${kind} attribution modal must contain ${copy}`).toContain(copy);
  }
  const lowerText = visibleText.toLowerCase();
  for (const copy of FORBIDDEN_ATTRIBUTION_COPY) {
    expect(lowerText, `${kind} attribution modal must not expose ${copy}`).not.toContain(copy);
  }

  const bucketToggle = modal.locator('[data-bucket-toggle]').first();
  await expect(bucketToggle).toHaveAttribute('aria-expanded', 'false');
  await bucketToggle.click();
  await expect(bucketToggle).toHaveAttribute('aria-expanded', 'true');
  const leafToggle = modal.locator('[data-bucket-leaf-toggle]').first();
  await expect(leafToggle).toBeVisible();
  await leafToggle.click();
  await expect(leafToggle).toHaveAttribute('aria-expanded', 'true');
  await expect(modal.locator('.sd-bucket-detail-preview').first()).toBeVisible();

  const geometry = await page.evaluate(() => {
    const dialog = document.querySelector('dialog.payload-modal');
    const rect = (selector) => {
      const element = document.querySelector(selector);
      if (!element) return null;
      const bounds = element.getBoundingClientRect();
      return { left: bounds.left, right: bounds.right };
    };
    const bounds = dialog.getBoundingClientRect();
    return {
      viewportWidth: window.innerWidth,
      scrollWidth: document.documentElement.scrollWidth,
      modal: { left: bounds.left, right: bounds.right },
      distribution: rect('.sd-attribution-distribution__bar'),
      summaryGrid: rect('.sd-attribution-summary-grid'),
      bucketList: rect('.sd-attribution-bucket-list'),
      preview: rect('.sd-bucket-detail-preview'),
    };
  });
  expect(geometry.scrollWidth).toBeLessThanOrEqual(geometry.viewportWidth + 2);
  expect(geometry.modal.left).toBeGreaterThanOrEqual(-2);
  expect(geometry.modal.right).toBeLessThanOrEqual(geometry.viewportWidth + 2);
  for (const key of ['distribution', 'summaryGrid', 'bucketList', 'preview']) {
    expect(geometry[key], `${key} must exist in the current detailed renderer`).not.toBeNull();
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
  await expect(modal.locator('.sd-payload-empty')).toHaveText('No content');

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
