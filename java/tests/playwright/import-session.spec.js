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
  await page.locator('[data-evidence-analysis] > summary').click();
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

test('renders local Markdown as readable content with a separate verbatim view', async ({ page }) => {
  const markdown = [
    '[$fixture](/synthetic/skills/fixture/SKILL.md)',
    '',
    '| Metric | Value |', '| --- | --- |', '| Fresh | 7 |', '',
    '- Measured', '', '```json', '{"literal":"[syntax](https://example.invalid)"}', '```', '',
    '[related](http://127.0.0.1:18999/sessions/claude_code/hifi-viz-session-001)',
    '[unsafe](javascript:alert(1))',
    '![figure](https://example.invalid/pixel.png)',
    '<img src=x onerror=alert(1)>',
  ].join('\n');
  const external = [];
  const { import_id: importId } = await uploadAndOpen(page, 'claude_code', claudeJsonl(markdown));
  await page.route('https://example.invalid/**', (route) => {
    external.push(route.request().url());
    return route.abort();
  });
  const button = page.locator('[data-trace-round-row]').first().getByRole('button', { name: 'Response', exact: true });
  const response = page.waitForResponse((r) => new URL(r.url()).pathname.startsWith(`/api/imports/${importId}/payload/`));
  await button.click();
  expect((await response).ok()).toBe(true);
  const modal = page.locator('dialog.payload-modal');
  await expect(modal.getByRole('cell', { name: '7', exact: true })).toBeVisible({ timeout: 2500 });
  await expect(modal.getByRole('columnheader').first()).toHaveCSS('border-bottom-width', '1px');
  await expect(modal.locator('[data-payload-subtitle]')).toBeHidden();
  await expect(modal.getByRole('listitem')).toHaveText('Measured');
  await expect(modal.locator('pre code')).toContainText('[syntax]');
  await expect(modal.getByRole('link', { name: 'related' })).toHaveAttribute('href', '/sessions/claude_code/hifi-viz-session-001');
  await expect(modal.locator('img, [href^="javascript:"], [href*="SKILL.md"]')).toHaveCount(0);
  expect(external).toEqual([]);
  const raw = modal.locator('details[data-payload-raw]');
  await expect(raw.locator('pre')).toBeHidden();
  await raw.locator('summary').click();
  await expect(raw.locator('pre')).toContainText('| Fresh | 7 |');
  await expect(raw.locator('pre')).toContainText('<img src=x onerror=alert(1)>');
});

test('request reading view excludes typed injected context and tool results but preserves the raw record', async ({ page }) => {
  const records = claudeJsonl('synthetic-reader').trim().split('\n').map(JSON.parse);
  const injected = { ...records[0], uuid: 'synthetic-injection', isMeta: true,
    message: { role: 'user', content: 'SYNTHETIC INJECTED CONTEXT' } };
  const tool = { ...records[0], uuid: 'synthetic-tool-result',
    message: { role: 'user', content: [
      { type: 'tool_result', tool_use_id: 'synthetic-tool', content: 'SYNTHETIC TOOL RESULT' },
    ] } };
  const jsonl = [records[0], injected, tool, records[1]].map(JSON.stringify).join('\n') + '\n';
  await uploadAndOpen(page, 'claude_code', jsonl);
  await page.locator('[data-trace-round-row]').first().getByRole('button', { name: 'Request', exact: true }).click();
  const modal = page.locator('dialog.payload-modal');
  const reading = modal.locator('.sd-content-block');
  await expect(reading).toContainText('Synthetic import request: synthetic-reader', { timeout: 2500 });
  await expect(reading).not.toContainText(/SYNTHETIC INJECTED CONTEXT|SYNTHETIC TOOL RESULT/);
  await modal.locator('details[data-payload-raw] summary').click();
  await expect(modal.locator('details[data-payload-raw] pre')).toContainText('SYNTHETIC INJECTED CONTEXT');
  await expect(modal.locator('details[data-payload-raw] pre')).toContainText('SYNTHETIC TOOL RESULT');
});

test('Codex request keeps quoted context tags and separates a standalone environment envelope with unconfirmed origin', async ({ page }) => {
  const records = codexJsonl().trim().split('\n').map(JSON.parse);
  const message = (text) => ({ type: 'response_item', payload: { type: 'message', role: 'user',
    content: [{ type: 'input_text', text }] } });
  const envelope = '<environment_context>\nSYNTHETIC ENVIRONMENT ONLY\n</environment_context>';
  const userText = [
    'Synthetic user discussion of <environment_context>.',
    '', '```xml', '<environment_context>', 'SYNTHETIC FENCED EXAMPLE', '</environment_context>', '```',
    '', '<environment_context>', 'SYNTHETIC QUOTED EXAMPLE', '</environment_context>', 'Synthetic user text outside the tag.',
  ].join('\n');
  records.splice(2, 1, message(envelope), message(userText));
  await uploadAndOpen(page, 'codex', records.map(JSON.stringify).join('\n') + '\n');
  await page.locator('[data-trace-round-row]').first().getByRole('button', { name: 'Request', exact: true }).click();
  const modal = page.locator('dialog.payload-modal');
  const reading = modal.locator('.sd-content-block');
  await expect(reading).toContainText('Synthetic user discussion');
  await expect(reading).toContainText('SYNTHETIC FENCED EXAMPLE');
  await expect(reading).toContainText('SYNTHETIC QUOTED EXAMPLE');
  await expect(reading).toContainText('Synthetic user text outside the tag.');
  await expect(reading).not.toContainText('SYNTHETIC ENVIRONMENT ONLY');
  const raw = modal.locator('details[data-payload-raw]');
  await expect(raw.locator('summary')).toContainText('归属无法确认');
  await expect(raw.locator('pre')).toBeHidden();
  await raw.locator('summary').click();
  await expect(raw.locator('pre')).toContainText(envelope);
});

test('Codex unclosed project wrapper keeps the fence and user question in reading view', async ({ page }) => {
  const records = codexJsonl().trim().split('\n').map(JSON.parse);
  const text = '# AGENTS.md instructions for synthetic\n<INSTRUCTIONS>\n```xml\n</INSTRUCTIONS>\n```\n请解释上面的标签。';
  records[2].payload.content[0].text = text;
  await uploadAndOpen(page, 'codex', records.map(JSON.stringify).join('\n') + '\n');
  await page.locator('[data-trace-round-row]').first().getByRole('button', { name: 'Request', exact: true }).click();
  const body = page.locator('dialog.payload-modal .sd-reading-markdown');
  await expect(body.locator('h1')).toHaveText('AGENTS.md instructions for synthetic');
  await expect(body.locator('pre code')).toHaveText('</INSTRUCTIONS>');
  await expect(body.locator('p').last()).toHaveText('请解释上面的标签。');
});

test('Codex mixed project instructions preserve user text and use local Markdown typography', async ({ page }) => {
  const records = codexJsonl().trim().split('\n').map(JSON.parse);
  const project = '# AGENTS.md instructions for /synthetic/project\n\n<INSTRUCTIONS>\n## Synthetic project rules\n- Synthetic context, not a task.\n\n```xml\n</INSTRUCTIONS>\n```\n</INSTRUCTIONS>';
  const user = '# Synthetic request\n\nPlease review the fixture below.\n\n- Keep this item\n- Keep this long inline path: `/synthetic/' + 'pathsegment'.repeat(16) + '`';
  const environment = '<environment_context>\nSynthetic environment\n</environment_context>';
  records[2].payload.content[0].text = project + environment + '\n\n' + user;
  await page.setViewportSize({ width: 390, height: 850 });
  await uploadAndOpen(page, 'codex', records.map(JSON.stringify).join('\n') + '\n');
  await page.locator('[data-trace-round-row]').first().getByRole('button', { name: 'Request', exact: true }).click();
  const modal = page.locator('dialog.payload-modal');
  // 阅读正文与折叠保留的 raw 是两种视图；等待 raw 后检查，避免命中初始摘要的时序。
  const raw = modal.locator('[data-payload-raw]');
  await expect(raw.locator('summary')).toContainText('项目说明');
  await expect(raw.locator('pre')).toBeHidden();
  const body = modal.locator('.sd-reading-markdown');
  await expect(body.locator('h1')).toHaveText('Synthetic request');
  await expect(body.locator('li')).toHaveCount(2);
  await expect(body).not.toContainText(/Synthetic project rules|Synthetic environment/);
  expect(await body.locator('h1').evaluate(e => parseFloat(getComputedStyle(e).fontSize))).toBeLessThanOrEqual(21);
  expect(await body.evaluate(e => e.scrollWidth <= e.clientWidth + 1 && parseFloat(getComputedStyle(e.querySelector('ul')).paddingInlineStart) >= 18)).toBe(true);
  await raw.locator('summary').click();
  await expect(raw.locator('pre')).toContainText(project + environment);
  await expect(raw.locator('pre')).toContainText(user);
});

test('Codex page-open marker and attachment path do not compete with the request heading', async ({ page }) => {
  const records = codexJsonl().trim().split('\n').map(JSON.parse);
  const input = (text) => ({ type: 'input_text', text });
  const marker = '<external_codex_apps_open_page>{"page_id":null}</external_codex_apps_open_page>';
  const path = '/synthetic/' + 'pathsegment/'.repeat(12) + 'synthetic-notes.md';
  const record = (text) => ({ ...records[2], payload: { ...records[2].payload, content: [input(text)] } });
  records.splice(2, 1, record(marker), record([
    '', '# Synthetic attachments', '', '## synthetic-notes.md: ' + path, '',
    '## Actual request', '', 'Read only this text.', '',
    'I am quoting ' + marker + ' in prose.',
  ].join('\n')));
  await page.setViewportSize({ width: 390, height: 850 });
  await uploadAndOpen(page, 'codex', records.map(JSON.stringify).join('\n') + '\n');
  await page.locator('[data-trace-round-row]').first().getByRole('button', { name: 'Request', exact: true }).click();
  const body = page.locator('dialog.payload-modal .sd-reading-markdown');
  const details = body.locator('details.sd-reading-page-marker');
  await expect(details.locator('summary')).toContainText('来源未确认');
  await expect(details.locator('pre')).toBeHidden();
  await details.locator('summary').press('Enter');
  await expect(details.locator('pre')).toHaveText(marker);
  await expect(body.locator('p').last()).toContainText(marker);
  const file = body.locator('.sd-reading-file-heading');
  const filename = file.locator('.sd-reading-file-name');
  const localPath = file.locator('.sd-reading-file-path');
  await expect(filename).toHaveText('synthetic-notes.md:');
  await expect(localPath).toHaveText(path);
  expect(await localPath.evaluate(e => e.scrollWidth > e.clientWidth && e.getBoundingClientRect().height <= 22)).toBe(true);
  await expect(body.getByRole('heading', { name: 'Actual request' })).toBeVisible();
});

test('真实上传独立分析，重复同名/同来源 ID 不影响个人或已有导入', async ({ page, request }) => {
  const before = await personalSnapshot(request);
  const requested = [];
  page.on('request', (req) => {
    const pathname = new URL(req.url()).pathname;
    if (pathname.startsWith('/api/')) requested.push(pathname);
  });

  await page.goto('/imports');
  await expect(page.getByRole('heading', { name: '导入单个会话文件', exact: true })).toBeVisible();
  const first = await uploadAndOpen(page, 'claude_code', claudeJsonl('first'), 'shared-synthetic.jsonl');
  const firstPath = new URL(page.url()).pathname;
  await expect(page.locator('[aria-label="Total Tokens"] .sd-kpi__value')).toHaveText('23');
  await expect(page.locator('[data-import-scope]')).toContainText('仅本文件分析');
  await expandFirstRound(page);

  const round = page.locator('[data-trace-round-row]').first();
  for (const sample of [
    { title: 'Request', side: 'request', kind: 'llm_request', text: 'Synthetic import request: first' },
    { title: 'Response', side: 'response', kind: 'llm_response', text: 'Synthetic import response: first' },
  ]) {
    const button = round.getByRole('button', { name: sample.title, exact: true });
    const path = await button.getAttribute('data-attribution-path');
    expect(path).toBeTruthy();
    const attributionResponse = page.waitForResponse((response) =>
      response.url().endsWith(`/api/imports/${first.import_id}${path}`));
    const opened = await openRealPayload(page, button, first.import_id, sample.title);
    expect(opened.payload.kind).toBe(sample.kind);
    expect(opened.payload.text || opened.payload.content).toContain(sample.text);
    await expect(opened.block.locator('pre')).toContainText(sample.text);
    const response = await attributionResponse;
    expect(response.ok()).toBe(true);
    const attribution = await response.json();
    expect(attribution.kind).toBe(`llm.${sample.side}_attribution`);
    expect(attribution.data.callId).toBe('synthetic-import-assistant');
    const disclosure = opened.modal.locator(`[data-payload-attribution="${sample.side}"]`);
    await expect(disclosure).toHaveAttribute('data-attribution-call', attribution.data.callId);
    await disclosure.locator('summary').press('Enter');
    await expect(disclosure.locator('.sd-kv').first()).toBeVisible();
    await expect(disclosure).toContainText(sample.side === 'request' ? '新鲜输入' : '输出');
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

test('恶意文件名和正文保持文本显示，窄宽范围提示不溢出', async ({ page }) => {
  await page.setViewportSize({ width: 850, height: 900 });
  await page.goto('/imports');
  await expect(page.getByRole('heading', { name: '导入单个会话文件', exact: true })).toBeVisible();
  const filename = 'synthetic-<img src=x onerror=window.importXss=true>.jsonl';
  const attack = '<img src=x onerror=window.importBodyXss=true><script>window.importBodyXss=true</script>';
  const imported = await uploadAndOpen(page, 'claude_code', claudeJsonl(attack), filename);
  await expect(page.locator('[data-session-hero] h1')).toContainText(filename);
  expect(await page.evaluate(() => window.importXss)).toBeUndefined();
  expect(await page.locator('[data-import-scope] img, [data-session-hero] img').count()).toBe(0);
  const geometry = await page.locator('[data-import-scope]').evaluate((element) => {
    const rect = element.getBoundingClientRect();
    return { left: rect.left, right: rect.right, viewport: window.innerWidth };
  });
  expect(geometry.left).toBeGreaterThanOrEqual(0);
  expect(geometry.right).toBeLessThanOrEqual(geometry.viewport);
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

test('无模型调用的实际输入仍可从摘要和展开读取，不伪造调用或工具', async ({ page }) => {
  const input = 'Synthetic pending input\nsecond line remains readable';
  const contents = JSON.stringify({ type: 'message', message: { role: 'user', content: input } }) + '\n';
  const result = await uploadAndOpen(page, 'qoder', contents, 'synthetic-pending.jsonl');
  await expect(page.locator('[data-execution-group]')).toContainText('用户输入记录');
  await expect(page.locator('[data-execution-group]')).not.toContainText('响应记录');
  await expect(page.locator('[data-execution-tool]')).toHaveCount(0);
  const row = page.locator('[data-trace-round-row]').first();
  await expect(row.locator('.metric-calls-tools')).toHaveText('0 records0 tools');
  await expect(row).toHaveAttribute('data-is-user-input', 'true');
  await expect(row.locator('.summary-title')).toContainText('Synthetic pending input');
  const response = page.waitForResponse((r) => new URL(r.url()).pathname.startsWith(`/api/imports/${result.import_id}/payload/`));
  await row.getByRole('button', { name: 'Input', exact: true }).click();
  const actual = await response;
  expect(actual.ok()).toBe(true);
  expect((await actual.json()).content).toBe(input);
  const modal = page.locator('dialog.payload-modal');
  await expect(modal).toBeVisible();
  await expect(modal.locator('[data-payload-body]')).toContainText('second line remains readable');
  await closeRealPayload(modal);
  await expandFirstRound(page);
  const detail = page.locator('#round-1-detail');
  await expect(detail.locator('[data-tool-call-id]')).toHaveCount(0);
  await expect(detail.getByRole('button', { name: 'Input', exact: true })).toBeVisible();
});
