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
    { toolCallId: 'tool-a', name: 'Read', declaredByCallId: calls[0].callId, inputPreview: '/synthetic/alpha.txt', durationMs: 24, status: 'success' },
    { toolCallId: 'tool-b', name: 'Bash', declaredByCallId: calls[1].callId, inputPreview: COMMAND, durationMs: 0, status: 'success' },
    { toolCallId: 'tool-missing', name: 'Read', declaredByCallId: calls[1].callId, status: 'unknown' },
  ];
  await page.route(`**${API}/rounds`, (route) => fulfillIndexedJson(route, { rounds: [{ roundIndex: 1, callCount: 2, toolCallCount: 3, tokens: { total: 200 }, status: 'ok', parity: { summary: 'Read × 2 · Bash × 1' } }] }));
  await page.route(`**${API}/round/1`, (route) => fulfillIndexedJson(route, { round: { calls, tools, toolCallIds: tools.map((tool) => tool.toolCallId), callAssistantTexts: { 'synthetic-call-7': '可见 assistant 文本' } } }));
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
      content = side === 'req' ? REQUEST : RESPONSE;
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
  const modal = await openContent(page, row.getByRole('button', { name: 'Response', exact: true }), 'Response', RESPONSE);
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
});

test('[UI-SD-044] Trace Round Request/Response 展示聚合内容，Token 归因独立', async ({ page }) => {
  const attributionRequests = [];
  page.on('request', (request) => { if (request.url().includes('/attribution/')) attributionRequests.push(request.url()); });
  const row = await installTraceFixture(page);
  await expect(row.getByRole('button', { name: '输入归因', exact: true })).toHaveAttribute('data-payload-kind', 'llm.request_attribution');
  await expect(row.getByRole('button', { name: '输出归因', exact: true })).toHaveAttribute('data-payload-kind', 'llm.response_attribution');
  const request = await openContent(page, row.getByRole('button', { name: 'Request', exact: true }), 'Request', REQUEST);
  await expect(request).toContainText('本地可见记录');
  await closeContent(request);
  const response = await openContent(page, row.getByRole('button', { name: 'Response', exact: true }), 'Response', RESPONSE);
  await expect(response).toContainText(INPUTS['tool-a']);
  await expect(response).toContainText('COMMAND_END');
  await expect(response.locator('script')).toHaveCount(0);
  expect(await page.evaluate(() => window.traceInjected)).toBeUndefined();
  expect(attributionRequests).toEqual([]);
  await closeContent(response);
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
  await expect(calls.nth(1).locator('.sd-tool-kind')).toHaveText('RESPONSE');
  await expect(calls.nth(1)).toContainText('2 个工具指令');
  await expect(calls.nth(1).locator('.sd-tool-time')).toHaveText('未记录');
  await expect(calls.nth(1).getByRole('button', { name: 'Request', exact: true })).toHaveAttribute('data-payload-id', 'main:req:synthetic-call-8');
  await expect(calls.nth(1).getByRole('button', { name: 'Response', exact: true })).toHaveAttribute('data-payload-id', 'main:resp:synthetic-call-8');
  for (const id of ['tool-a', 'tool-b']) {
    const tool = detail.locator(`[data-tool-call-id="${id}"]`);
    await expect(tool.locator('.sd-tool-tokens')).toHaveText('无独立 token');
    await closeContent(await openContent(page, tool.getByRole('button', { name: 'Input', exact: true }), 'Input', INPUTS[id]));
    await closeContent(await openContent(page, tool.getByRole('button', { name: 'Result', exact: true }), 'Result', `synthetic result for ${id}`));
  }
  await expect(detail.locator('[data-tool-call-id="tool-a"] .sd-tool-time')).toHaveText('24 ms');
  await expect(detail.locator('[data-tool-call-id="tool-b"] .sd-tool-time')).toHaveText('0 ms');
  const missing = detail.locator('[data-tool-call-id="tool-missing"]');
  await expect(missing.locator('.sd-tool-cmd')).toHaveText('输入未记录');
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
