const { test, expect } = require('@playwright/test');

// 全部为合成记录；故意复用个人 fixture 的来源 ID，证明不能串读或覆盖。
const PERSONAL_SESSION_ID = 'hifi-viz-session-001';
const SYNTHETIC_COMMAND = 'echo synthetic-import-tool-input';
const SYNTHETIC_TOOL_RESULT = 'Synthetic tool result: complete original output\nsynthetic-tool-result-end';
const importsByPage = new WeakMap();
const IMPORT_DETAIL_PATH = /^\/imports\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$/i;

test.beforeEach(async ({ page, baseURL }) => {
  const imports = new Set();
  importsByPage.set(page, imports);
  page.on('framenavigated', (frame) => {
    if (frame !== page.mainFrame()) return;
    const url = new URL(frame.url());
    const match = url.pathname.match(IMPORT_DETAIL_PATH);
    if (url.origin === new URL(baseURL).origin && match) imports.add(match[1]);
  });
});

test.afterEach(async ({ page, request, baseURL }) => {
  const imports = importsByPage.get(page);
  for (const importId of imports) {
    const response = await request.delete(`/api/imports/${encodeURIComponent(importId)}`, {
      headers: { Origin: new URL(baseURL).origin },
    });
    expect([204, 404], `clean up import ${importId}`).toContain(response.status());
  }
});

function claudeJsonl(marker, inputTokens = 11, outputTokens = 7) {
  return [
    {
      type: 'user', sessionId: PERSONAL_SESSION_ID, uuid: 'synthetic-import-user',
      timestamp: '2026-06-01T10:00:00Z', cwd: '/synthetic/import-project',
      message: { role: 'user', content: `Synthetic import request: ${marker}` },
    },
    {
      type: 'assistant', sessionId: PERSONAL_SESSION_ID, uuid: 'synthetic-import-assistant',
      timestamp: '2026-06-01T10:00:01Z',
      message: {
        id: 'synthetic-import-message', role: 'assistant', model: 'claude-sonnet-4.5',
        content: [{ type: 'text', text: `Synthetic import response: ${marker}` }],
        usage: {
          input_tokens: inputTokens, output_tokens: outputTokens,
          cache_read_input_tokens: 3, cache_creation_input_tokens: 2,
        },
      },
    },
  ].map((record) => JSON.stringify(record)).join('\n') + '\n';
}

function qoderRoleJsonl() {
  return [
    {
      role: 'user', sessionId: PERSONAL_SESSION_ID, uuid: 'synthetic-qoder-user',
      timestamp: '2026-06-01T10:00:00Z', cwd: '/synthetic/import-project',
      content: [{ type: 'text', text: 'Synthetic import request: qoder' }],
    },
    {
      role: 'assistant', sessionId: PERSONAL_SESSION_ID, uuid: 'synthetic-qoder-assistant',
      id: 'synthetic-qoder-message', timestamp: '2026-06-01T10:00:01Z', model: 'synthetic-qoder-model',
      content: [
        { type: 'text', text: 'Synthetic import response: qoder' },
        { type: 'tool_use', id: 'synthetic-tool', name: 'Bash', input: { command: SYNTHETIC_COMMAND } },
      ],
      usage: {
        input_tokens: 11, cache_read_input_tokens: 3, cache_creation_input_tokens: 2, output_tokens: 7,
      },
    },
    {
      role: 'user', sessionId: PERSONAL_SESSION_ID, uuid: 'synthetic-qoder-tool-result',
      timestamp: '2026-06-01T10:00:02Z',
      content: [{ type: 'tool_result', tool_use_id: 'synthetic-tool', content: SYNTHETIC_TOOL_RESULT }],
    },
  ].map((record) => JSON.stringify(record)).join('\n') + '\n';
}

function codexJsonl() {
  return [
    { type: 'session_meta', timestamp: '2026-06-01T10:00:00Z', payload: {
      id: PERSONAL_SESSION_ID, cwd: '/synthetic/import-project',
    } },
    { type: 'turn_context', payload: { model: 'synthetic-model' } },
    { type: 'response_item', payload: { type: 'message', role: 'user', content: [
      { type: 'input_text', text: 'Synthetic import request: codex' },
    ] } },
    { type: 'response_item', payload: { type: 'function_call', call_id: 'synthetic-tool',
      name: 'shell', arguments: JSON.stringify({ command: SYNTHETIC_COMMAND }),
    } },
    { type: 'response_item', payload: { type: 'function_call_output',
      call_id: 'synthetic-tool', output: SYNTHETIC_TOOL_RESULT,
    } },
    { type: 'response_item', payload: { type: 'message', role: 'assistant', content: [
      { type: 'output_text', text: 'Synthetic import response: codex' },
    ] } },
    { type: 'event_msg', timestamp: '2026-06-01T10:00:03Z', payload: {
      type: 'token_count', info: { total_token_usage: {
        input_tokens: 100, cached_input_tokens: 40, cache_creation_input_tokens: 3,
        output_tokens: 20, total_tokens: 123,
      } },
    } },
  ].map((record) => JSON.stringify(record)).join('\n') + '\n';
}

async function personalSnapshot(request) {
  const snapshot = {};
  for (const endpoint of ['/api/dashboard/summary', '/api/sessions/summary', '/api/sessions/rows']) {
    const response = await request.get(endpoint);
    expect(response.ok(), endpoint).toBe(true);
    snapshot[endpoint] = await response.json();
  }
  return snapshot;
}

async function chooseJsonl(page, contents, filename = 'synthetic-import.jsonl') {
  const chooserPromise = page.waitForEvent('filechooser');
  await page.getByLabel('JSONL 文件', { exact: true }).click();
  const chooser = await chooserPromise;
  await chooser.setFiles({
    name: filename,
    mimeType: 'application/x-ndjson',
    buffer: Buffer.from(contents, 'utf8'),
  });
}

function uploadResponse(page) {
  return page.waitForResponse((response) =>
    new URL(response.url()).pathname === '/api/imports'
    && response.request().method() === 'POST');
}

async function readImportedPage(page, source, origin) {
  await expect(page).toHaveURL((url) => url.origin === origin
    && IMPORT_DETAIL_PATH.test(url.pathname) && !url.search && !url.hash);
  const importId = new URL(page.url()).pathname.match(IMPORT_DETAIL_PATH)[1];
  // 使用独立请求验证导航目标，避免立即导航清除 Chrome 的 POST response body。
  const metaResponse = await page.request.get(`/api/imports/${importId}/meta`);
  expect(metaResponse.ok(), 'imported metadata must be available').toBe(true);
  const meta = await metaResponse.json();
  expect(meta.filters.agent).toBe(source);
  expect(meta.sessionKey).toBe(`import:${importId}`);
  await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  await expect(page.locator('[data-import-scope]')).toContainText('不计入个人统计');
  await expect(page.locator('[data-trace-round-row]').first()).toBeVisible();
  return { import_id: importId, source: meta.filters.agent };
}

async function uploadAndOpen(page, source, contents, filename) {
  await page.goto('/imports');
  await page.getByLabel('会话来源', { exact: true }).selectOption(source);
  await chooseJsonl(page, contents, filename);
  const responsePromise = uploadResponse(page);
  await page.getByRole('button', { name: '导入并分析', exact: true }).click();
  const response = await responsePromise;
  expect(response.ok(), 'real JSONL upload must succeed').toBe(true);
  expect(response.status()).toBe(201);
  return readImportedPage(page, source, new URL(response.url()).origin);
}

async function expandFirstRound(page) {
  const toggle = page.locator('[data-trace-round-row] [data-action="toggle-round"]').first();
  await expect(toggle).toBeVisible();
  if (await toggle.getAttribute('aria-expanded') !== 'true') await toggle.click();
}

async function openRealPayload(page, button, importId, title) {
  await expect(button).toBeVisible();
  const payloadId = await button.getAttribute('data-payload-id');
  expect(payloadId).toBeTruthy();
  const endpoint = `/api/imports/${importId}/payload/${encodeURIComponent(payloadId)}`;
  const responsePromise = page.waitForResponse((response) => new URL(response.url()).pathname === endpoint);
  await button.click();
  const response = await responsePromise;
  expect(response.ok(), endpoint).toBe(true);
  const payload = await response.json();
  const modal = page.locator('dialog.payload-modal');
  await expect(modal).toBeVisible();
  const block = modal.locator('.sd-content-block').filter({ has: page.getByText(title, { exact: true }) });
  await expect(block.locator('pre')).toBeVisible();
  return { modal, block, payload };
}

async function closeRealPayload(modal) {
  await modal.getByRole('button', { name: 'Close', exact: true }).click();
  await expect(modal).toBeHidden();
}

test('真实上传独立分析，重复同名/同来源 ID 不影响个人或已有导入', async ({ page, request }, testInfo) => {
  const before = await personalSnapshot(request);
  const requested = [];
  page.on('request', (req) => {
    const pathname = new URL(req.url()).pathname;
    if (pathname.startsWith('/api/')) requested.push(pathname);
  });

  await page.goto('/imports');
  await expect(page.getByRole('heading', { name: '导入单个会话文件', exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath('import-upload-desktop.png'), fullPage: true });
  const first = await uploadAndOpen(page, 'claude_code', claudeJsonl('first'), 'shared-synthetic.jsonl');
  const firstPath = new URL(page.url()).pathname;
  await expect(page.locator('[aria-label="Total Tokens"] .sd-kpi__value')).toHaveText('23');
  await expect(page.locator('[data-import-scope]')).toContainText('仅本文件分析');
  await page.screenshot({ path: testInfo.outputPath('import-detail-desktop.png'), fullPage: true });
  await expandFirstRound(page);

  const modal = page.locator('dialog.payload-modal');
  for (const kind of ['request', 'response']) {
    const attribution = page.locator(
      `button[data-action="open-payload"][data-payload-kind="llm.${kind}_attribution"]:visible`,
    ).first();
    await expect(attribution).toBeVisible();
    const attributionResponse = page.waitForResponse((response) => {
      const path = new URL(response.url()).pathname;
      return path.startsWith(`/api/imports/${first.import_id}/attribution/`) && path.endsWith(`/${kind}`);
    });
    await attribution.click();
    expect((await attributionResponse).ok()).toBe(true);
    await expect(modal).toHaveAttribute('data-attribution-state', 'success');
    await expect(modal.locator('[data-attribution-card="advanced"]')).toContainText(
      'Timing、coverage、bucket 分布与 credit 归因在当前数据源中未记录。',
    );
    await page.keyboard.press('Escape');
  }

  const round = page.locator('[data-trace-round-row]').first();
  for (const sample of [
    { title: 'Request', kind: 'llm_request', text: 'Synthetic import request: first' },
    { title: 'Response', kind: 'llm_response', text: 'Synthetic import response: first' },
  ]) {
    const opened = await openRealPayload(
      page, round.getByRole('button', { name: sample.title, exact: true }), first.import_id, sample.title,
    );
    expect(opened.payload.kind).toBe(sample.kind);
    expect(opened.payload.text || opened.payload.content).toContain(sample.text);
    await expect(opened.block.locator('pre')).toContainText(sample.text);
    await closeRealPayload(opened.modal);
  }

  const second = await uploadAndOpen(page, 'claude_code', claudeJsonl('second', 31, 9), 'shared-synthetic.jsonl');
  expect(second.import_id).not.toBe(first.import_id);
  await expect(page.locator('[aria-label="Total Tokens"] .sd-kpi__value')).toHaveText('45');
  await page.goto(firstPath);
  await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  await expect(page.locator('[aria-label="Total Tokens"] .sd-kpi__value')).toHaveText('23');
  await expect(page.locator('[data-import-scope]')).toContainText('不计入个人统计');
  expect(requested.some((url) => url.startsWith('/api/sessions/'))).toBe(false);
  expect(requested.some((url) => url.startsWith(`/api/imports/${first.import_id}/round/`))).toBe(true);
  expect(await personalSnapshot(request)).toEqual(before);

  await page.getByRole('link', { name: '返回个人 Sessions', exact: true }).click();
  await expect(page).toHaveURL(/\/sessions$/);
});

for (const sample of [
  { source: 'codex', contents: codexJsonl(), tokens: '123' },
  { source: 'qoder', contents: qoderRoleJsonl(), tokens: '23' },
]) {
  test(`真实上传 ${sample.source}，显式来源和 token 投影保持一致`, async ({ page }) => {
    const requested = [];
    page.on('request', (request) => {
      const path = new URL(request.url()).pathname;
      if (path.startsWith('/api/')) requested.push(path);
    });
    const result = await uploadAndOpen(page, sample.source, sample.contents, 'shared-synthetic.jsonl');
    expect(result.source).toBe(sample.source);
    await expect(page.locator('[aria-label="Total Tokens"] .sd-kpi__value')).toHaveText(sample.tokens);
    await expect(page.locator('[data-import-scope]')).toContainText('仅本文件分析');
    await expandFirstRound(page);
    await expect(page.locator('[data-import-scope]')).toBeVisible();
    const tool = page.locator('[data-tool-call-id="synthetic-tool"]');
    await expect(tool).toHaveCount(1);
    const input = await openRealPayload(
      page, tool.getByRole('button', { name: 'Input', exact: true }), result.import_id, 'Input',
    );
    expect(input.payload.kind).toBe('tool_input');
    expect(JSON.parse(input.payload.text || input.payload.content)).toEqual({ command: SYNTHETIC_COMMAND });
    expect(JSON.parse(await input.block.locator('pre').innerText())).toEqual({ command: SYNTHETIC_COMMAND });
    await closeRealPayload(input.modal);

    const output = await openRealPayload(
      page, tool.getByRole('button', { name: 'Result', exact: true }), result.import_id, 'Result',
    );
    expect(output.payload.kind).toBe('tool_result');
    expect(output.payload.text || output.payload.content).toBe(SYNTHETIC_TOOL_RESULT);
    await expect(output.block.locator('pre')).toHaveText(SYNTHETIC_TOOL_RESULT);
    await closeRealPayload(output.modal);

    const round = page.locator('[data-trace-round-row]').first();
    for (const payloadSample of [
      { title: 'Request', kind: 'llm_request', text: `Synthetic import request: ${sample.source}` },
      { title: 'Response', kind: 'llm_response', text: `Synthetic import response: ${sample.source}` },
    ]) {
      const opened = await openRealPayload(
        page, round.getByRole('button', { name: payloadSample.title, exact: true }), result.import_id, payloadSample.title,
      );
      expect(opened.payload.kind).toBe(payloadSample.kind);
      expect(opened.payload.text || opened.payload.content).toContain(payloadSample.text);
      await expect(opened.block.locator('pre')).toContainText(payloadSample.text);
      await closeRealPayload(opened.modal);
    }
    expect(requested.some((url) => url.startsWith('/api/sessions/'))).toBe(false);
    expect(requested.some((url) => url.startsWith(`/api/imports/${result.import_id}/round/`))).toBe(true);
  });
}

test('解析失败可以重试，换成有效文件后恢复真实分析', async ({ page }) => {
  await page.goto('/imports');
  await page.getByLabel('会话来源', { exact: true }).selectOption('claude_code');
  await chooseJsonl(page, '{invalid synthetic JSONL}\n');
  const failed = uploadResponse(page);
  await page.getByRole('button', { name: '导入并分析', exact: true }).click();
  expect((await failed).ok()).toBe(false);
  await expect(page.locator('[data-import-error]')).toBeVisible();
  await expect(page.locator('[data-import-error]')).not.toContainText('{invalid synthetic JSONL}');
  await expect(page.getByRole('button', { name: '导入并分析', exact: true })).toBeEnabled();

  const retried = uploadResponse(page);
  await page.getByRole('button', { name: '重新尝试', exact: true }).click();
  expect((await retried).ok()).toBe(false);
  await expect(page.locator('[data-import-error]')).toBeVisible();

  await chooseJsonl(page, claudeJsonl('recovered'));
  const recovered = uploadResponse(page);
  await page.getByRole('button', { name: '导入并分析', exact: true }).click();
  const response = await recovered;
  expect(response.ok()).toBe(true);
  expect(response.status()).toBe(201);
  await readImportedPage(page, 'claude_code', new URL(response.url()).origin);
});

test('恶意文件名和正文保持文本显示，窄宽范围提示不溢出', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 850, height: 900 });
  await page.goto('/imports');
  await expect(page.getByRole('heading', { name: '导入单个会话文件', exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath('import-upload-narrow.png'), fullPage: true });
  const filename = 'synthetic-<img src=x onerror=window.importXss=true>.jsonl';
  const attack = '<img src=x onerror=window.importBodyXss=true><script>window.importBodyXss=true</script>';
  const imported = await uploadAndOpen(page, 'claude_code', claudeJsonl(attack), filename);
  await expect(page.locator('[data-import-scope]')).toContainText(filename);
  expect(await page.evaluate(() => window.importXss)).toBeUndefined();
  expect(await page.locator('[data-import-scope] img').count()).toBe(0);
  const geometry = await page.locator('[data-import-scope]').evaluate((element) => {
    const rect = element.getBoundingClientRect();
    return { left: rect.left, right: rect.right, viewport: window.innerWidth };
  });
  expect(geometry.left).toBeGreaterThanOrEqual(0);
  expect(geometry.right).toBeLessThanOrEqual(geometry.viewport);
  await page.screenshot({ path: testInfo.outputPath('import-detail-narrow.png'), fullPage: true });
  await expandFirstRound(page);
  const round = page.locator('[data-trace-round-row]').first();
  for (const title of ['Request', 'Response']) {
    const opened = await openRealPayload(
      page, round.getByRole('button', { name: title, exact: true }), imported.import_id, title,
    );
    await expect(opened.block.locator('pre')).toContainText(attack);
    await expect(opened.block.locator('script, img')).toHaveCount(0);
    expect(await page.evaluate(() => window.importBodyXss)).toBeUndefined();
    await closeRealPayload(opened.modal);
  }
  expect(await page.evaluate(() => window.importXss)).toBeUndefined();
  await expect(page.locator('img[src="x"]')).toHaveCount(0);
});

test('拒绝服务响应中的外部详情 URL，不离开导入页', async ({ page }) => {
  await page.route('**/api/imports', (route) => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ import_id: 'synthetic-id', detail_url: 'https://example.invalid/imports/synthetic-id' }),
  }));
  await page.goto('/imports');
  await page.getByLabel('会话来源', { exact: true }).selectOption('claude_code');
  await chooseJsonl(page, claudeJsonl('unsafe-redirect'));
  await page.getByRole('button', { name: '导入并分析', exact: true }).click();
  await expect(page.locator('[data-import-error]')).toContainText('无效的导入链接');
  await expect(page).toHaveURL(/\/imports$/);
  await expect(page.getByRole('button', { name: '导入并分析', exact: true })).toBeEnabled();
});
