const { test, expect } = require('@playwright/test');

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
  const call = page.locator('#round-1-detail [data-timeline-item="assistant_text"]').last();
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
  await expect(detail.locator('.sd-exit').filter({ hasText: '记录 C8' })).toHaveAttribute('title', /callId: synthetic-call-8/);
  const calls = detail.locator('[data-timeline-item="assistant_text"]');
  await expect(calls.nth(0).locator('.sd-tool-kind')).toHaveText('TEXT');
  await expect(calls.nth(1).locator('.sd-tool-kind')).toHaveText('TOOLS');
  await expect(calls.nth(1)).toContainText('Bash、Read');
  await expect(calls.nth(1).locator('.sd-tool-time')).toHaveText('未记录');
  await expect(calls.nth(1).getByRole('button', { name: 'Request', exact: true })).toHaveAttribute('data-payload-id', 'main:req:synthetic-call-8');
  await expect(calls.nth(1).getByRole('button', { name: 'Response', exact: true })).toHaveAttribute('data-payload-id', 'main:resp:synthetic-call-8');
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
