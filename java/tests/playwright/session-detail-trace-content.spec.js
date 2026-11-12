const { test, expect } = require('@playwright/test');
const path = require('path');
const { runPlaywrightRoot } = require('./runtime-paths');

const SESSION = '/sessions/claude_code/hifi-viz-session-001';
const API = '/api/sessions/claude_code/hifi-viz-session-001';
const COMMAND = 'printf "<script>window.traceInjected = true</script> & synthetic"; ' + 'echo fixture-only; '.repeat(100) + 'echo COMMAND_END';
const INPUTS = {
  'tool-a': JSON.stringify({ file_path: '/synthetic/alpha.txt' }),
  'tool-b': JSON.stringify({ command: COMMAND }),
};
const RESPONSE = '可见 assistant 文本\nRead tool-a\n' + INPUTS['tool-a'] + '\nBash tool-b\n' + INPUTS['tool-b'];
const REQUEST = '合成 user 输入\ntool_result previous-tool: synthetic previous result';

// Keep the real fixture snapshot identity when replacing only synthetic content.
async function fulfillIndexedJson(route, json) {
  const response = await route.fetch();
  await route.fulfill({ response, status: 200, json });
}

async function installTraceFixture(page) {
  const calls = [
    { callId: 'synthetic-call-7', callKey: 'C7', scope: 'main', model: 'fixture-model', usage: { total: 200 }, responseToolCallIds: ['tool-a'] },
    { callId: 'synthetic-call-8', callKey: 'C8', scope: 'main', model: 'fixture-model', usage: {}, requestToolResultIds: ['tool-a'], responseToolCallIds: ['tool-b', 'tool-missing'] },
  ];
  const tools = [
    { toolCallId: 'tool-a', name: 'Read', declaredByCallId: calls[0].callId, inputPreview: '/synthetic/alpha.txt', durationMs: 24, status: 'success', resultObserved: true, executionKind: 'tool' },
    { toolCallId: 'tool-b', name: 'Bash', declaredByCallId: calls[1].callId, inputPreview: COMMAND, durationMs: 0, exitCode: 7, resultObserved: true, executionKind: 'shell' },
    { toolCallId: 'tool-missing', name: 'Read', declaredByCallId: calls[1].callId, status: 'running', resultObserved: false, executionKind: 'tool' },
  ];
  await page.route(`**${API}/rounds`, (route) => fulfillIndexedJson(route, { rounds: [{ roundIndex: 1, callCount: 2, toolCallCount: 3, tokens: { total: 200 }, status: 'ok', parity: { summary: 'Read × 2 · Bash × 1' } }] }));
  await page.route(`**${API}/round/1`, (route) => fulfillIndexedJson(route, { round: { calls, tools, toolCallIds: tools.map((tool) => tool.toolCallId), callAssistantTexts: { 'synthetic-call-7': '可见 assistant 文本' } } }));
  await page.route(`**${API}/attribution/1/1/*`, (route) => {
    const url = new URL(route.request().url());
    const side = url.pathname.split('/').at(-1);
    const callId = url.searchParams.get('call_id');
    return fulfillIndexedJson(route, { kind: 'llm.' + side + '_attribution', data: {
      callId, callKey: 'C8', scope: 'main', freshInputTokens: 4567, outputTokens: 890,
      cacheReadTokens: 12000, cacheWriteTokens: 0, requestToolResultCount: 1, responseToolCallCount: 1,
      provenance: { freshInput: 'provider_reported', cacheRead: 'provider_reported', cacheWrite: 'unavailable', output: 'provider_reported' },
      responseTools: side === 'response' ? [{ id: 'tool-b', name: 'Bash', preview: 'printf synthetic' }] : [],
    } });
  });
  await page.route(`**${API}/payload/*`, (route) => {
    const id = decodeURIComponent(route.request().url().split('/payload/')[1]);
    let kind;
    let content;
    if (id.startsWith('tool:')) {
      const [, side, toolId] = id.split(':');
      kind = side === 'input' ? 'tool_input' : 'tool_result';
      content = side === 'input' ? INPUTS[toolId] : `synthetic result for ${toolId}`;
    } else {
      const side = id.split(':')[1];
      kind = side === 'req' ? 'llm_request' : 'llm_response';
      content = side === 'req' ? REQUEST : id === 'main:resp:synthetic-call-8' ? '' : RESPONSE;
      if (id === 'main:resp:synthetic-call-8') return fulfillIndexedJson(route, { kind, content, reading: [], status: 'missing' });
    }
    return fulfillIndexedJson(route, { kind, content: content || '', status: content ? 'available' : 'missing', truncated: false });
  });
  await page.goto(SESSION);
  await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  await page.locator('[data-evidence-analysis] > summary').click();
  return page.locator('[data-trace-round-row][data-round="1"]');
}

async function openContent(page, button, label, content) {
  await button.click();
  const modal = page.locator('dialog.payload-modal');
  await expect(modal).toBeVisible();
  await expect(modal.locator('.sd-card-title')).toHaveText(label);
  await expect(modal.locator('pre')).toHaveText(content);
  return modal;
}

async function closeContent(modal) {
  await modal.locator('[data-action="close-payload"]').click();
  await expect(modal).toBeHidden();
}

for (const scenario of [
  { name: 'Request raw-only', title: 'Request', raw: true, empty: '未单列输入正文；仍有本地记录，请展开“原始记录”查证。' },
  { name: 'Request no raw', title: 'Request', raw: false, empty: 'Request 正文未记录' },
  { name: 'Request unconfirmed context', title: 'Request', raw: true, unconfirmedContext: true, empty: '未确认可单列的正文，请查看原始记录。' },
  { name: 'Response raw-only', title: 'Response', raw: true, empty: 'Response 正文未记录' },
  { name: 'Response no raw', title: 'Response', raw: false, empty: 'Response 正文未记录' },
  { name: 'Request reading present', title: 'Request', raw: true, reading: [{ text: 'Synthetic request prose' }] },
]) {
  test(`conversation empty guidance guard: ${scenario.name}`, async ({ page }) => {
    const row = await installTraceFixture(page);
    const raw = scenario.raw ? 'Tool result [synthetic-previous]\nSynthetic stored evidence' : '';
    await page.route(`**${API}/payload/*`, route => fulfillIndexedJson(route, {
      kind: scenario.title === 'Request' ? 'llm_request' : 'llm_response', content: raw,
      reading: scenario.reading || [], unconfirmedContext: !!scenario.unconfirmedContext,
    }));
    await page.route(`**${API}/attribution/1/1/*`, route => {
      const url = new URL(route.request().url());
      return fulfillIndexedJson(route, { kind: 'llm.' + url.pathname.split('/').at(-1) + '_attribution',
        data: { callId: url.searchParams.get('call_id'), scope: 'main', responseTools: [] } });
    });
    await row.getByRole('button', { name: scenario.title, exact: true }).click();
    const modal = page.locator('dialog.payload-modal');
    await expect(modal).toBeVisible();
    await expect(modal).toContainText('仅展示本地可见记录，不代表完整 provider context。');
    if (scenario.empty) await expect(modal.locator('.sd-payload-empty')).toHaveText(scenario.empty);
    else {
      await expect(modal.locator('.sd-payload-empty')).toHaveCount(0);
      await expect(modal).toContainText('Synthetic request prose');
    }
    const original = modal.locator('[data-payload-raw]');
    await expect(original).toHaveCount(scenario.raw ? 1 : 0);
    if (scenario.raw) {
      await expect(original).not.toHaveAttribute('open');
      if (scenario.unconfirmedContext) await expect(original.locator('summary')).toHaveText('原始记录（含项目说明或上下文，归属无法确认）');
      await original.locator('summary').click();
      await expect(original.locator('pre')).toHaveText(raw);
    }
  });
}

test('[UI-SD-043] Payload metadata 键值不重叠，窄屏保留完整正文', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const row = await installTraceFixture(page);
  const response = await openContent(page, row.getByRole('button', { name: 'Response', exact: true }), 'Response', RESPONSE);
  await expect(response.locator('pre')).toContainText('COMMAND_END');
  expect(await response.locator('[data-payload-body]').evaluate(body => body.scrollWidth - body.clientWidth)).toBeLessThanOrEqual(1);
  await closeContent(response);
  await row.locator('[data-action="toggle-round"]').click();
  const toolInput = page.locator('#round-1-detail [data-tool-call-id="tool-b"]').getByRole('button', { name: 'Input', exact: true });
  const modal = await openContent(page, toolInput, 'Input', INPUTS['tool-b']);
  const boxes = await modal.locator('.sd-kv').evaluateAll((rows) => rows.map((row) => {
    const [key, value] = Array.from(row.children).map((child) => child.getBoundingClientRect());
    return { keyRight: key.right, valueLeft: value.left, valueRight: value.right };
  }));
  expect(boxes.length).toBeGreaterThan(0);
  for (const box of boxes) {
    expect(box.keyRight).toBeLessThanOrEqual(box.valueLeft);
    expect(box.valueRight).toBeLessThanOrEqual(390);
  }
  await expect(modal.locator('pre')).toContainText('COMMAND_END');
  await closeContent(modal);
});

test('[UI-SD-044] side-specific attribution is linked to the expanded record; tool-only response exposes Input', async ({ page }) => {
  const attributionRequests = [];
  page.on('request', (request) => {
    if (request.url().includes('/attribution/')) attributionRequests.push(new URL(request.url()).searchParams.get('call_id'));
  });
  const row = await installTraceFixture(page);
  await expect(row.locator('.attribution-col button')).toHaveText(['Request', 'Response']);
  await row.locator('[data-action="toggle-round"]').click();
  const call = page.locator('#round-1-detail [data-tool-call-id="tool-b"]');
  const request = await openContent(page, call.getByRole('button', { name: 'Request', exact: true }), 'Request', REQUEST);
  const input = request.locator('[data-payload-attribution="request"]');
  await input.locator('summary').press('Enter');
  await expect(input).toHaveAttribute('data-attribution-call', 'synthetic-call-8');
  await expect(input).toContainText('4,567');
  await expect(input).toContainText('12,000');
  await expect(input).toContainText('Not reported');
  await expect(input).not.toContainText('890');
  await closeContent(request);

  await call.getByRole('button', { name: 'Response', exact: true }).click();
  const response = page.locator('dialog.payload-modal');
  const output = response.locator('[data-payload-attribution="response"]');
  await output.locator('summary').press('Enter');
  await expect(output).toHaveAttribute('data-attribution-call', 'synthetic-call-8');
  await expect(output).toContainText('890');
  await expect(output).not.toContainText('4,567');
  await expect(response.locator('.sd-payload-empty')).toHaveCount(0);
  await expect(response.locator('.sd-payload-tool-link')).toContainText('Bash · printf synthetic');
  await openContent(page, response.getByRole('button', { name: 'Input', exact: true }), 'Input', INPUTS['tool-b']);
  expect(attributionRequests).toEqual(['synthetic-call-8', 'synthetic-call-8']);
});

test('[UI-SD-045] Trace 本地记录编号、工具预览与 Input/Result 对应，缺失值明确', async ({ page }) => {
  const row = await installTraceFixture(page);
  await row.locator('[data-action="toggle-round"]').click();
  const detail = page.locator('#round-1-detail');
  await expect(detail.locator('[data-tool-call-id="tool-a"]')).toHaveCount(1);
  await expect(detail.locator('.sd-exit').filter({ hasText: '记录 C7' })).toHaveAttribute('title', /callId: synthetic-call-7.*不代表独立 provider 请求/);
  await expect(detail.locator('[data-tool-call-id="tool-b"] .sd-exit')).toHaveAttribute('title', /声明调用: synthetic-call-8/);
  const calls = detail.locator('[data-timeline-item="assistant_text"]');
  await expect(calls.nth(0).locator('.sd-tool-kind')).toHaveText('TEXT');
  await expect(calls).toHaveCount(1);
  const toolOnlyCall = detail.locator('[data-tool-call-id="tool-b"]');
  await expect(toolOnlyCall.getByRole('button', { name: 'Request', exact: true })).toHaveAttribute('data-payload-id', 'main:req:synthetic-call-8');
  await expect(toolOnlyCall.getByRole('button', { name: 'Response', exact: true })).toHaveAttribute('data-payload-id', 'main:resp:synthetic-call-8');
  for (const id of ['tool-a', 'tool-b']) {
    const tool = detail.locator(`[data-tool-call-id="${id}"]`);
    await expect(tool.locator('.sd-tool-tokens')).toHaveAttribute('aria-label', '无独立 token 计量');
    await closeContent(await openContent(page, tool.getByRole('button', { name: 'Input', exact: true }), 'Input', INPUTS[id]));
    await closeContent(await openContent(page, tool.getByRole('button', { name: 'Result', exact: true }), 'Result', `synthetic result for ${id}`));
  }
  await expect(detail.locator('[data-tool-call-id="tool-a"] .sd-tool-time')).toHaveText('24 ms');
  await expect(detail.locator('[data-tool-call-id="tool-b"] .sd-tool-time')).toHaveText('0 ms');
  const missing = detail.locator('[data-tool-call-id="tool-missing"]');
  await expect(missing.locator('.sd-tool-cmd')).toHaveText('Read');
  await expect(missing.locator('.sd-tool-result')).toHaveText('running');
  await expect(missing.getByRole('button', { name: 'Result', exact: true })).toHaveCount(0);
  await expect(detail.locator('[data-tool-call-id="tool-b"] .sd-tool-result')).toHaveText('exit 7');
  await detail.locator('[data-tool-kind-filter]').selectOption('shell');
  await expect(detail.locator('[data-tool-call-id="tool-a"]')).toBeHidden();
  await expect(detail.locator('[data-tool-call-id="tool-b"]')).toBeVisible();
  await detail.locator('[data-tool-kind-filter]').selectOption('');
  await expect(missing.locator('.sd-tool-time')).toHaveText('未记录');
  await missing.getByRole('button', { name: 'Input', exact: true }).click();
  await expect(page.locator('dialog.payload-modal .sd-payload-empty')).toHaveText('Input 内容未记录');
});

test('tool-only member uses one timeline operation, paired bodies are lazy and responsive', async ({ page }) => {
  let bodyReads = 0;
  page.on('request', (request) => { if (request.url().includes('/payload/')) bodyReads++; });
  const row = await installTraceFixture(page);
  await row.locator('[data-action="toggle-round"]').click();
  const detail = page.locator('#round-1-detail');
  await expect(detail.locator('[data-timeline-item="assistant_text"]')).toHaveCount(1);
  await expect(detail.locator('[data-timeline-item="tool-call"]')).toHaveCount(3);
  await expect(detail.locator('[data-content-pagination="round-members"]')).toHaveCount(0);
  await expect(detail.locator('[data-tool-kind-filter]')).toHaveClass('ui-select__control');
  expect(bodyReads).toBe(0);
  const pair = detail.locator('[data-tool-id="tool-b"]');
  await pair.locator('summary').click();
  await expect(pair.locator('pre').first()).toHaveText(INPUTS['tool-b']);
  await expect(pair.locator('pre').last()).toHaveText('synthetic result for tool-b');
  await detail.screenshot({ path: path.join(runPlaywrightRoot, 'task56-trace-pair-desktop.png') });
  const boxes = await pair.locator('.sd-tool-payload-grid > section').evaluateAll(nodes => nodes.map(node => {
    const b = node.getBoundingClientRect(); return { top: b.top, left: b.left, right: b.right, bottom: b.bottom };
  }));
  expect(boxes[0].top).toEqual(boxes[1].top);
  expect(boxes[0].right).toBeLessThan(boxes[1].left);
  await page.setViewportSize({ width: 390, height: 844 });
  const narrow = await pair.locator('.sd-tool-payload-grid > section').evaluateAll(nodes => nodes.map(node => {
    const b = node.getBoundingClientRect(); return { top: b.top, bottom: b.bottom, right: b.right };
  }));
  await detail.screenshot({ path: path.join(runPlaywrightRoot, 'task56-trace-pair-narrow.png') });
  expect(narrow[0].bottom).toBeLessThan(narrow[1].top);
  expect(narrow[1].right).toBeLessThanOrEqual(390);
  expect(await detail.locator('[data-tool-call-id="tool-b"] .sd-tool-cmd').evaluate(node => node.getBoundingClientRect().height)).toBeLessThanOrEqual(70);
  expect(bodyReads).toBe(2);
});

test('round HTTP failure without generation is retryable, real generation change requires refresh', async ({ page }) => {
  let failed = true;
  const row = await installTraceFixture(page);
  await page.route(`**${API}/round/1`, async route => {
    if (failed) return route.fulfill({ status: 500, contentType: 'application/json', json: { message: 'synthetic temporary failure' } });
    return fulfillIndexedJson(route, { round: { calls: [], tools: [] }, total: 0, membersPaged: true });
  });
  await row.locator('[data-action="toggle-round"]').click();
  const error = page.locator('[data-loading-for="1"]');
  await expect(error).toContainText('HTTP 500: synthetic temporary failure');
  await expect(error).not.toContainText('Index changed');
  failed = false;
  await error.getByRole('button', { name: 'Retry', exact: true }).click();
  await expect(page.locator('#round-1-detail')).toBeVisible();
  await expect(page.locator('[data-content-pagination="round-members"]')).toHaveCount(0);

  await page.reload();
  await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  await page.locator('[data-evidence-analysis] > summary').click();
  await page.route(`**${API}/round/1`, route => route.fulfill({ status: 409, contentType: 'application/json', json: { error: 'index_generation_changed' } }));
  await page.locator('[data-trace-round-row]').first().locator('[data-action="toggle-round"]').click();
  await expect(page.locator('[data-loading-for="1"]')).toContainText('Index changed');
  await expect(page.locator('[data-loading-for="1"]').getByRole('button', { name: 'Refresh page' })).toBeVisible();
  await expect(page.locator('#round-1-detail')).toHaveCount(0);
});

test('unavailable diagnostics and file provenance are not measured empty values', async ({ page }) => {
  await page.route(`**${API}/meta`, async route => {
    const response = await route.fetch();
    const data = await response.json();
    data.parity = { ...data.parity, sessionFilePath: '' };
    await route.fulfill({ response, json: data });
  });
  await page.route(`**${API}/diagnostics`, route => fulfillIndexedJson(route, { parity: {
    contentMeasured: true, agents: [], contextSegmentsAvailable: false, toolImpactAvailable: false, issuesAvailable: false,
  } }));
  await installTraceFixture(page);
  await page.locator('[data-session-info] > summary').click();
  await expect(page.locator('[data-session-file-text]')).toHaveText('来源未提供可展示的会话文件路径');
  await expect(page.locator('[data-session-file-path] [data-action="copy"]')).toBeHidden();
  const cards = page.locator('[data-session-diagnostics]');
  await expect(cards.locator('[data-evidence-state="unavailable"]')).toHaveCount(3);
  await expect(cards).toContainText('未提供可验证的上下文预算');
  await expect(cards).not.toContainText('0 calls');
  await expect(cards).not.toContainText('0 issues');
});

test('paired tool bodies distinguish a failed read from missing content and reject changed generation', async ({ page }) => {
  const row = await installTraceFixture(page);
  let mode = 'error';
  await page.route(`**${API}/payload/${encodeURIComponent('tool:input:tool-b')}`, route => {
    if (mode === 'ok') return fulfillIndexedJson(route, { kind: 'tool_input', content: INPUTS['tool-b'] });
    return route.fulfill({ status: mode === 'changed' ? 409 : 500, contentType: 'application/json',
      json: { error: mode === 'changed' ? 'index_generation_changed' : 'synthetic_read_failure' } });
  });
  await row.locator('[data-action="toggle-round"]').click();
  const pair = page.locator('#round-1-detail [data-tool-payload-pair][data-tool-id="tool-b"]');
  await pair.locator('summary').click();
  const input = pair.locator('.sd-tool-payload-grid > section').first();
  await expect(input).toContainText('HTTP 500');
  await expect(input).not.toContainText('未记录');
  await expect(pair.locator('.sd-tool-payload-grid > section').last()).toContainText('synthetic result for tool-b');
  mode = 'ok';
  await input.getByRole('button', { name: 'Retry', exact: true }).click();
  await expect(input.locator('pre')).toHaveText(INPUTS['tool-b']);
  mode = 'changed';
  await page.reload();
  await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  await page.locator('[data-evidence-analysis] > summary').click();
  await page.locator('[data-trace-round-row] [data-action="toggle-round"]').click();
  await pair.locator('summary').click();
  await expect(input).toContainText('Index changed');
  await expect(input.getByRole('button', { name: 'Refresh page', exact: true })).toBeVisible();
  await expect(input).not.toContainText('COMMAND_END');
});

test('[UI-SD-046] Trace 长命令安全转义且窄屏内容与操作可访问', async ({ page }) => {
  await page.setViewportSize({ width: 768, height: 1000 });
  const row = await installTraceFixture(page);
  await row.locator('[data-action="toggle-round"]').click();
  const tool = page.locator('#round-1-detail [data-tool-call-id="tool-b"]');
  await expect(tool.locator('.sd-tool-cmd')).toHaveText(COMMAND);
  await expect(tool.locator('.sd-tool-cmd')).toHaveAttribute('title', `Bash: ${COMMAND}`);
  await expect(tool.locator('script')).toHaveCount(0);
  expect(await tool.evaluate((element) => element.scrollWidth <= element.clientWidth + 1)).toBe(true);
  const modal = await openContent(page, tool.getByRole('button', { name: 'Input', exact: true }), 'Input', INPUTS['tool-b']);
  await expect(modal).toContainText('COMMAND_END');
  expect(await page.evaluate(() => window.traceInjected)).toBeUndefined();
});

test('real Codex import keeps R1/R2 summaries, times and same-name tool payloads bound to source identities', async ({ page, request, baseURL }) => {
  const event = (payload, timestamp) => ({ type: 'response_item', timestamp, payload });
  const user = text => ({ type: 'message', role: 'user', content: [{ type: 'input_text', text }] });
  const tool = id => ({ type: 'function_call', call_id: id, name: 'exec', arguments: JSON.stringify({ command: `printf synthetic-${id}` }) });
  const result = id => ({ type: 'function_call_output', call_id: id, output: `synthetic result ${id}` });
  const assistant = text => ({ type: 'message', role: 'assistant', content: [{ type: 'output_text', text }] });
  const records = [
    { type: 'session_meta', payload: { id: '11111111-1111-4111-8111-111111111156', cwd: '/synthetic' } },
    { type: 'turn_context', payload: { model: 'synthetic-model' } },
    event(user('检查合成 alpha'), '2026-01-01T01:02:03Z'),
    event(tool('alpha'), '2026-01-01T01:02:04Z'),
    event(tool('parallel'), '2026-01-01T01:02:05Z'),
    event(result('parallel'), '2026-01-01T01:02:06Z'),
    event(result('alpha'), '2026-01-01T01:02:07Z'),
    event(assistant('合成 alpha 完成'), '2026-01-01T01:02:08Z'),
    event(user('检查合成 beta'), '2026-01-01T01:03:04Z'),
    event(tool('beta'), '2026-01-01T01:03:05Z'),
    event(result('beta'), '2026-01-01T01:03:06Z'),
    event(tool('missing'), '2026-01-01T01:03:07Z'),
    event(assistant('合成 beta 等待结果'), '2026-01-01T01:03:08Z'),
  ];
  const headers = { Origin: new URL(baseURL).origin };
  const upload = await request.post('/api/imports', { headers, multipart: {
    source: 'codex', file: { name: 'synthetic-trace-evidence.jsonl', mimeType: 'application/x-ndjson', buffer: Buffer.from(records.map(JSON.stringify).join('\n') + '\n') },
  } });
  expect(upload.status(), await upload.text()).toBe(201);
  const { import_id: importId } = await upload.json();
  const api = `/api/imports/${importId}`;
  try {
    let bodyReads = 0;
    page.on('request', req => { if (req.url().includes(`${api}/payload/`)) bodyReads++; });
    await page.goto(`/imports/${importId}`);
    await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  await page.locator('[data-evidence-analysis] > summary').click();
    const rows = page.locator('[data-trace-round-row]');
    await expect(rows).toHaveCount(2);
    for (const [index, marker, ids] of [[0, 'alpha', ['alpha', 'parallel']], [1, 'beta', ['beta', 'missing']]]) {
      const row = rows.nth(index);
      await expect(row.locator('.summary-col')).toContainText(`检查合成 ${marker}`);
      await expect(row.locator('.summary-col')).not.toContainText(index ? 'alpha' : 'beta');
      await expect(row.locator('.time-col')).toHaveText(index ? '09:03:08' : '09:02:08');
      await row.locator('[data-action="toggle-round"]').click();
      const detail = page.locator(`#round-${index + 1}-detail`);
      await expect(detail).toBeVisible();
      await expect(detail.locator('[data-timeline-item="tool-call"]')).toHaveCount(2);
      await expect(detail.locator('[data-timeline-item="assistant_text"]')).toHaveCount(1);
      await expect(detail.locator('[data-content-pagination="round-members"]')).toHaveCount(0);
      if (!index) expect(bodyReads).toBe(0);
      for (const title of ['Request', 'Response']) {
        const pending = page.waitForResponse(r => r.url().includes(`${api}/payload/`));
        await row.getByRole('button', { name: title, exact: true }).click();
        const response = await pending;
        expect(response.status()).toBe(200);
        const payload = await response.json();
        expect(payload.content).toContain(title === 'Request' ? `检查合成 ${marker}` : `synthetic-${ids[0]}`);
        if (title === 'Response') {
          for (const id of ids) expect(payload.content).toContain(`synthetic-${id}`);
          expect(payload.content).not.toContain(index ? 'synthetic-alpha' : 'synthetic-beta');
          expect(payload.content).not.toContain('synthetic result');
        }
        const modal = page.locator('dialog.payload-modal');
        await expect(modal.locator('.sd-content-block').filter({ has: page.getByText(title, { exact: true }) }).locator('pre')).toContainText(
          title === 'Request' ? `检查合成 ${marker}` : `合成 ${marker}`,
        );
        if (title === 'Response') {
          await expect(modal.locator('.sd-payload-tool-link')).toHaveCount(2);
          for (const id of ids) {
            const link = modal.locator('.sd-payload-tool-link').filter({ has: page.locator(`[data-payload-id="tool:input:${id}"]`) });
            await expect(link).toContainText(`printf synthetic-${id}`);
          }
        }
        await closeContent(modal);
      }
      for (const id of ids) {
        const pair = detail.locator(`[data-tool-payload-pair][data-tool-id="${id}"]`);
        await pair.locator('summary').click();
        await expect(pair.locator('.sd-tool-payload-grid > section').first().locator('pre')).toContainText(`synthetic-${id}`);
        if (id === 'missing') {
          await expect(pair.locator('.sd-tool-payload-grid > section').last()).toContainText('结果未记录');
        } else {
          await expect(pair.locator('.sd-tool-payload-grid > section').last().locator('pre')).toHaveText(`synthetic result ${id}`);
        }
      }
    }
    await page.locator('#round-1-detail').screenshot({ path: path.join(runPlaywrightRoot, 'task56-real-trace-desktop.png') });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.locator('#round-2-detail').screenshot({ path: path.join(runPlaywrightRoot, 'task56-real-trace-narrow.png') });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  } finally {
    expect((await request.delete(api, { headers })).status()).toBe(204);
  }
});
