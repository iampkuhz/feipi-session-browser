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

test('first question and identity-bound originals are lazy in the sole execution view', async ({ page }) => {
  const bodyRequests = [];
  const indexRequests = [];
  page.on('request', req => {
    if (req.url().includes(API + '/payload/')) bodyRequests.push(req.url());
    if (req.url().startsWith(new URL(API + '/payloads', req.url()).href)) indexRequests.push(req.url());
  });
  await page.goto(SESSION);
  await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  const trace = page.locator('section[data-trace-panel]');
  await expect(trace.getByRole('heading', { name: '执行过程', exact: true })).toBeVisible();
  await expect(page.getByRole('tab')).toHaveCount(0);
  expect(bodyRequests).toHaveLength(0);
  expect(indexRequests).toHaveLength(0);

  await page.getByRole('button', { name: '查看首问', exact: true }).click();
  const modal = page.locator('dialog[open]');
  await expect(modal).toContainText('create the implementation plan.');
  await closeContent(modal);

  await expect(trace.locator('[data-round-sources], [data-payload-index]')).toHaveCount(0);
  const round = trace.locator('[data-trace-round-row]').first();
  await round.locator('[data-action="toggle-round"]').click();
  await expect(trace.locator('#round-1-detail [data-payload-kind="llm_request"]')).toHaveCount(0);
  const request = round.getByRole('button', { name: 'Request', exact: true });
  await expect(request).toBeVisible();
  expect(indexRequests).toHaveLength(0);
  expect(bodyRequests).toHaveLength(1);
  await request.click();
  await expect(modal).toContainText('create the implementation plan.');
  await expect(modal.locator('[data-payload-attribution="request"]')).toHaveAttribute('data-attribution-call', 'C1');
  expect(indexRequests).toHaveLength(0);
});

test('long trace expands all 100 loaded rows without fetching individual payloads', async ({ page }) => {
  const scope = '/sessions/claude_code/long-session-001';
  const bodyRequests = [];
  page.on('request', req => { if (req.url().includes('/api' + scope + '/payload/')) bodyRequests.push(req.url()); });
  await page.goto(scope);
  await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  const rounds = page.locator('[data-trace-round-row]');
  await expect(rounds).toHaveCount(100);
  const toggle = page.locator('[data-action="toggle-all"]');
  await expect(toggle).toHaveText('Expand all');
  await toggle.click();
  const details = page.locator('[data-trace-detail]:visible');
  await expect(details).toHaveCount(100, { timeout: 20000 });
  const tool = details.locator('[data-timeline-item="tool-call"]').first();
  expect(await tool.evaluate(el => el.getBoundingClientRect().height)).toBeLessThanOrEqual(32);
  expect(bodyRequests).toHaveLength(0);
  await expect(tool.locator('[data-tool-payload-pair] > summary')).toBeVisible();
  await expect(tool.getByRole('button', { name: 'Result', exact: true })).toBeVisible();
  expect(bodyRequests).toHaveLength(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  await toggle.click();
  await expect(details).toHaveCount(0);
});

// Keep the real fixture snapshot identity when replacing only synthetic content.
async function fulfillIndexedJson(route, json) {
  const response = await route.fetch();
  await route.fulfill({ response, status: 200, json });
}

async function installTraceFixture(page, roundInfo) {
  const calls = [
    { callId: 'synthetic-call-7', callKey: 'C7', phaseLabel: '压缩前模型调用', scope: 'main', model: 'fixture-model', usage: { total: 200 }, responseToolCallIds: ['tool-a'] },
    { callId: 'synthetic-call-8', callKey: 'C8', scope: 'main', model: 'fixture-model', usage: {}, requestToolResultIds: ['tool-a'], responseToolCallIds: ['tool-b', 'tool-missing'] },
  ];
  const tools = [
    { toolCallId: 'tool-a', name: 'Read', declaredByCallId: calls[0].callId, inputPreview: '/synthetic/alpha.txt', durationMs: 25, observation: { durationNanos: 24123456 }, status: 'success', resultObserved: true, executionKind: 'read' },
    { toolCallId: 'tool-b', name: 'Bash', declaredByCallId: calls[1].callId, inputPreview: COMMAND, timestamp: '2026-01-01T01:02:03Z', durationMs: 0, exitCode: 7, resultObserved: true, executionKind: 'shell' },
    { toolCallId: 'tool-missing', name: 'Read', declaredByCallId: calls[1].callId, status: 'running', resultObserved: false, executionKind: 'read' },
  ];
  await page.route(`**${API}/rounds`, (route) => fulfillIndexedJson(route, { rounds: [{ roundIndex: 1, callCount: 2, toolCallCount: 3, tokens: { total: 200 }, status: 'ok', parity: { summary: '读取 × 2 · Shell', summaryRole: 'tool' }, ...roundInfo }] }));
  await page.route(`**${API}/round/1`, (route) => fulfillIndexedJson(route, { round: { calls, tools, toolCallIds: tools.map((tool) => tool.toolCallId), callAssistantTexts: { 'synthetic-call-7': '可见 assistant 文本' } } }));
  await page.route(`**${API}/attribution/1/1/*`, (route) => {
    const url = new URL(route.request().url());
    const side = url.pathname.split('/').at(-1);
    const callId = url.searchParams.get('call_id');
    return fulfillIndexedJson(route, { kind: 'llm.' + side + '_attribution', source: 'claude_code', data: {
      callId, callKey: 'C8', model: 'fixture-model', scope: 'main', freshInputTokens: 4567, outputTokens: 890,
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
    return fulfillIndexedJson(route, { kind, content: content || '', status: content ? 'available' : 'missing',
      truncated: false, ...(kind === 'tool_result' ? { reading: [] } : {}) });
  });
  await page.goto(SESSION);
  await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  return page.locator('[data-trace-round-row][data-round="1"]');
}

async function openToolPair(tool) {
  const pair = tool.locator('..').locator('[data-tool-payload-pair]');
  await pair.locator(':scope > summary').click();
  await expect(pair).toHaveAttribute('open');
  return pair;
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
    const row = await installTraceFixture(page, { callCount: 1 });
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
    await expect(modal).toContainText('仅展示本地记录；完整上下文与未公开推理范围未知。');
    if (scenario.empty) {
      await expect(modal.locator('.sd-payload-empty')).toHaveText(scenario.empty);
      await expect(modal.locator('.sd-reading-token-note')).toContainText('总 Token 未知，比例与余量未计算');
      await expect(modal.locator('.sd-reading-token-meter')).toHaveCount(0);
    } else {
      await expect(modal.locator('.sd-payload-empty')).toHaveCount(0);
      await expect(modal).toContainText('Synthetic request prose');
      await expect(modal.locator('.sd-reading-composition [data-token-part="current"] strong')).toHaveText('约 6 tokens');
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

test('Request and Response visible estimates exclude raw and do not invent shares without a measured total', async ({ page }) => {
  const row = await installTraceFixture(page, { callCount: 1 });
  await page.route(`**${API}/payload/*`, route => {
    const id = decodeURIComponent(route.request().url().split('/payload/')[1]);
    return fulfillIndexedJson(route, {
      kind: id.includes(':req:') ? 'llm_request' : 'llm_response',
      content: 'Repeated raw body that is not part of the denominator.',
      reading: [
        { label: 'Part A', html: '<p>中英正文</p>', text: '' },
        { label: 'Part B', text: 'abcdefghijklmnop' },
      ],
    });
  });
  for (const title of ['Request', 'Response']) {
    await row.getByRole('button', { name: title, exact: true }).click();
    const modal = page.locator('dialog.payload-modal');
    await expect(modal.locator('.sd-reading-composition .sd-reading-token-note')).toContainText('可见文本约 6 tokens');
    await expect(modal.locator('.sd-reading-composition .sd-reading-token-note')).toContainText('原始记录与本机参考不计入');
    const legend = modal.locator('.sd-reading-composition li strong');
    await expect(legend).toHaveText(['约 6 tokens']);
    await expect(modal.locator('.sd-reading-usage-band')).toHaveCount(0);
    await modal.locator('[data-payload-raw] summary').click();
    await expect(legend).toHaveText(['约 6 tokens']);
    await closeContent(modal);
  }
});

test('reading blocks show full character counts and scroll with the keyboard without an expand button', async ({ page }) => {
  const row = await installTraceFixture(page, { callCount: 1 });
  await page.route(`**${API}/payload/*`, route => fulfillIndexedJson(route, {
    kind: 'llm_request',
    reading: [
      { label: 'long', kind: 'instructions', html: '<p>synthetic line</p>'.repeat(25) + '<p>synthetic ending</p>' },
      { label: 'short', kind: 'conversation', text: '测试😀' },
    ],
  }));
  await row.getByRole('button', { name: 'Request', exact: true }).click();
  const modal = page.locator('dialog.payload-modal');
  const blocks = modal.locator('.sd-content-block');
  await expect(blocks).toHaveCount(2);
  await expect(blocks.first().locator('.sd-reading-block-measure')).toHaveText('366 字符 · 约 92 tokens');
  await expect(blocks.last().locator('.sd-reading-block-measure')).toHaveText('3 字符 · 约 2 tokens');
  const legend = modal.locator('li[data-token-part="instructions"]');
  await expect(legend.locator('small')).toHaveText('366 字符');
  await expect(legend.locator('strong')).toHaveText('约 92 tokens');
  await expect(modal.getByRole('button', { name: /展开全文|收起全文/ })).toHaveCount(0);
  const body = blocks.first().getByRole('region', { name: 'Request · long' });
  expect(await body.evaluate(el => el.scrollHeight - el.clientHeight)).toBeGreaterThan(100);
  expect(await body.evaluate(el => el.clientWidth - el.firstElementChild.clientWidth)).toBeLessThan(24);
  await body.focus();
  await body.press('End');
  await expect.poll(() => body.evaluate(el => el.scrollHeight - el.clientHeight - el.scrollTop)).toBeLessThanOrEqual(1);
  await expect(body).toBeFocused();
});

test('[UI-SD-043] Payload metadata 键值不重叠，桌面弹框保留完整正文', async ({ page }) => {
  await page.setViewportSize({ width: 1024, height: 900 });
  const row = await installTraceFixture(page, { callCount: 1 });
  const response = await openContent(page, row.getByRole('button', { name: 'Response', exact: true }), 'Response', RESPONSE);
  await expect(response.locator('pre')).toContainText('COMMAND_END');
  expect(await response.locator('[data-payload-body]').evaluate(body => body.scrollWidth - body.clientWidth)).toBeLessThanOrEqual(1);
  await closeContent(response);
  await row.locator('[data-action="toggle-round"]').click();
  const pair = await openToolPair(page.locator('#round-1-detail [data-tool-call-id="tool-b"]'));
  const toolInput = pair.getByRole('button', { name: 'Input', exact: true });
  const modal = await openContent(page, toolInput, 'Input', INPUTS['tool-b']);
  const boxes = await modal.locator('.sd-kv').evaluateAll((rows) => rows.map((row) => {
    const [key, value] = Array.from(row.children).map((child) => child.getBoundingClientRect());
    return { keyRight: key.right, valueLeft: value.left, valueRight: value.right };
  }));
  expect(boxes.length).toBeGreaterThan(0);
  for (const box of boxes) {
    expect(box.keyRight).toBeLessThanOrEqual(box.valueLeft);
    expect(box.valueRight).toBeLessThanOrEqual(1024);
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
  await expect(row.locator('.attribution-col button')).toHaveCount(0);
  await expect(row.locator('.attribution-col')).toHaveText('见调用明细');
  await row.locator('[data-action="toggle-round"]').click();
  const call = page.locator('#round-1-detail [data-call-tools="synthetic-call-8"]');
  const request = await openContent(page, call.getByRole('button', { name: 'Request', exact: true }), 'Request', REQUEST);
  const input = request.locator('[data-payload-attribution="request"]');
  await input.locator('summary').press('Enter');
  await expect(input).toHaveAttribute('data-attribution-call', 'synthetic-call-8');
  await expect(input.locator('summary')).toContainText('已报告 16,567 tokens，另有未知分项');
  await expect(input.locator('.sd-reading-usage-band')).toHaveCount(0);
  await expect(request.locator('.sd-payload-metadata')).toContainText('记录来源claude_code');
  await expect(request.locator('.sd-payload-metadata')).toContainText('模型fixture-model');
  await expect(input).toContainText('4,567');
  await expect(input).toContainText('12,000');
  await expect(input.locator('.sd-reading-usage-part').filter({ hasText: '缓存写入' })).toContainText('N/A');
  await expect(input).not.toContainText('890');
  await closeContent(request);

  await call.getByRole('button', { name: 'Response', exact: true }).click();
  const response = page.locator('dialog.payload-modal');
  const output = response.locator('[data-payload-attribution="response"]');
  await output.locator('summary').press('Enter');
  await expect(output).toHaveAttribute('data-attribution-call', 'synthetic-call-8');
  await expect(output.locator('summary')).toContainText('来源报告 890 tokens');
  await expect(output.locator('summary')).toContainText('推理等非正文用量未单列');
  await expect(output.locator('.sd-reading-usage-band')).toHaveCount(0);
  await expect(response.locator('.sd-reading-usage-band')).toHaveCount(1);
  await expect(output).not.toContainText('4,567');
  await expect(response.locator('.sd-payload-empty')).toHaveCount(0);
  const tool = response.locator('.sd-payload-tool-link');
  await expect(tool.locator('strong')).toHaveText('Bash');
  await expect(tool.locator('code')).toHaveText('printf synthetic');
  await expect(tool.getByRole('button', { name: 'Result', exact: true })).toHaveAttribute('data-payload-id', 'tool:result:tool-b');
  const result = await openContent(page, tool.getByRole('button', { name: 'Result', exact: true }), 'Result', 'synthetic result for tool-b');
  await expect(result.locator('.sd-reading-composition')).toContainText('工具结果不计为独立模型调用');
  await expect(result.locator('.sd-reading-usage-band')).toHaveCount(0);
  await expect(result.locator('.sd-reading-composition [data-token-part="result"]')).toContainText('tokens');
  await expect(result.locator('[data-payload-attribution]')).toHaveCount(0);
  await result.getByRole('button', { name: /^返回 .+ · C8 · Response$/ }).click();
  await expect(output).toHaveAttribute('data-attribution-call', 'synthetic-call-8');
  await openContent(page, response.getByRole('button', { name: 'Input', exact: true }), 'Input', INPUTS['tool-b']);
  expect(attributionRequests).toEqual(['synthetic-call-8', 'synthetic-call-8', 'synthetic-call-8']);
});

test('one Token bar per direction separates visible categories, reported reasoning, and residual', async ({ page }) => {
  const row = await installTraceFixture(page);
  let input = 320000;
  const kinds = ['skills', 'instructions', 'agents', 'tools', 'conversation', 'conversation'];
  const counts = [100, 200, 300, 400, 800, 4000];
  await page.route(`**${API}/payload/*`, route => {
    const response = decodeURIComponent(route.request().url()).includes(':resp:');
    return fulfillIndexedJson(route, {
      kind: response ? 'llm_response' : 'llm_request',
      content: 'duplicate raw evidence',
      tokens: response ? { output: 8000, total: input + 8000, reasoning: 50 } : { input, total: input + 8000, reasoning: 50 },
      reading: response ? [{ kind: 'conversation', label: 'assistant', text: 'x'.repeat(400) }]
        : [...kinds.map((kind, index) => ({
          kind, label: kind, source: [0, 4].includes(index) ? 'reconstructed' : 'current',
          text: 'x'.repeat(counts[index] * 4),
        })), { kind: 'configuration', label: '协作模式 Instructions（配置）',
          source: 'reconstructed', text: 'synthetic configuration' }],
    });
  });
  await page.route(`**${API}/attribution/1/1/request?*`, route => fulfillIndexedJson(route, {
    kind: 'llm.request_attribution', source: 'claude_code', data: {
      callId: 'synthetic-call-8', callKey: 'C8', source: 'fixture-entry', originator: 'fixture-cli', cliVersion: '1.2.3',
      freshInputTokens: input - 100, cacheReadTokens: 100, cacheWriteTokens: 0,
      outputTokens: 8000, totalTokens: input + 8000,
      provenance: { freshInput: 'provider_reported', cacheRead: 'provider_reported',
        cacheWrite: 'provider_reported', output: 'provider_reported' },
    },
  }));
  await row.locator('[data-action="toggle-round"]').click();
  const action = page.locator('#round-1-detail [data-call-tools="synthetic-call-8"]')
    .getByRole('button', { name: 'Request', exact: true });
  await action.click();
  const modal = page.locator('dialog.payload-modal');
  const composition = modal.locator('.sd-reading-composition');
  const legend = composition.locator('li');
  await expect(legend.locator('span')).toHaveText(['Skills 列表', 'Instructions', 'AGENTS.md', 'Tools', '历史上下文', '本次内容', '未识别']);
  await expect(modal.locator('[data-reading-category="skills"] .sd-card-title')).toHaveText('Skills 列表及使用说明');
  await expect(modal.locator('[data-reading-category="skills"] .sd-reading-block-measure')).toHaveText('400 字符 · 约 100 tokens');
  await expect(legend.locator('small')).toHaveText(['400 字符', '800 字符', '1,200 字符', '1,600 字符', '3,200 字符', '16,000 字符']);
  await expect(legend.last()).toContainText('约 314,200 tokens · 98.2%');
  await expect(composition.locator('p')).toContainText('可见文本约 5,800 tokens');
  const reference = modal.locator('details').filter({ hasText: '历史会话配置参考（未计入 Token）' });
  await expect(reference).not.toHaveAttribute('open');
  await reference.locator('summary').click();
  await expect(reference).toContainText('synthetic configuration');
  await expect(reference.locator('.sd-reading-block-measure')).toHaveText('23 字符');
  await expect(reference).toContainText('不是本机当前配置');
  await expect(legend.last()).toContainText('约 314,200 tokens · 98.2%');
  await expect(modal.locator('.sd-payload-metadata dt')).toHaveText(['记录来源', '记录入口类型', '客户端标识', 'CLI 版本']);
  await expect(modal.locator('.sd-payload-metadata dd')).toHaveText(['claude_code', 'fixture-entry', 'fixture-cli', '1.2.3']);
  const bar = modal.locator('.sd-reading-usage-band');
  await expect(bar).toHaveCount(1);
  await expect(bar).toBeVisible();
  const segments = bar.locator('rect');
  await expect(segments).toHaveCount(7);
  await expect(segments.first()).toHaveAttribute('width', '0.03125');
  await expect(segments.last()).toHaveAttribute('width', '98.1875');
  const legendColors = await legend.evaluateAll(nodes => nodes.map(el => getComputedStyle(el).borderInlineStartColor));
  expect(new Set(legendColors).size).toBe(7);
  expect(await segments.evaluateAll(nodes => nodes.map(el => getComputedStyle(el).fill))).toEqual(legendColors);
  await expect(modal.locator('meter')).toHaveCount(0);
  const raw = modal.locator('[data-payload-raw]');
  const navigation = modal.getByRole('navigation', { name: '载荷导航' }).getByRole('button', { name: / · C8 · Response$/ });
  await expect(navigation).toBeVisible();
  for (const property of ['backgroundColor', 'borderTopColor']) {
    const style = await navigation.evaluate((el, property) => getComputedStyle(el)[property], property);
    expect(await raw.evaluate((el, property) => getComputedStyle(el)[property], property)).not.toBe(style);
  }
  await navigation.click();
  await expect(composition.locator('p')).toContainText('本次Response来源报告总量：8,000 tokens');
  await expect(legend.filter({ hasText: '推理（来源报告）' })).toContainText('50 tokens');
  await expect(legend.last()).toContainText('约 7,850 tokens');
  await expect(bar).toHaveCount(1);
  await closeContent(modal);

  input = 500;
  await action.click();
  await expect(composition.locator('p')).toContainText('超过总量，不计算比例或负余量');
  await expect(bar).toHaveCount(0);
  await expect(legend.locator('span')).toHaveText(['Skills 列表', 'Instructions', 'AGENTS.md', 'Tools', '历史上下文', '本次内容']);
});

test('a round header uses scoped payload only when its sole member identity and scope are explicit', async ({ page }) => {
  const row = await installTraceFixture(page, { callCount: 1, calls: ['synthetic-call-8'],
    parity: { agentUsage: [{ owner: 'main' }] } });
  const request = row.getByRole('button', { name: 'Request', exact: true });
  await expect(request).toHaveAttribute('data-payload-id', 'main:req:synthetic-call-8');
  await expect(request).toHaveAttribute('data-attribution-path', '/attribution/1/1/request?call_id=synthetic-call-8');
  const modal = await openContent(page, request, 'Request', REQUEST);
  await expect(modal.locator('[data-payload-attribution="request"]')).toHaveAttribute('data-attribution-call', 'synthetic-call-8');
});

test('[UI-SD-045] Trace 本地记录编号、工具预览与 Input/Result 对应，缺失值明确', async ({ page }) => {
  const row = await installTraceFixture(page, { parity: { time: '12:34:56', taskDurationMs: 0, summary: '读取 × 2 · Shell', summaryRole: 'tool' } });
  await expect(row.locator('.round-id')).toHaveText('›R1');
  await expect(row.locator('.time-col .sd-time-point')).toHaveText('12:34:56');
  await expect(row.locator('.duration-col .sd-time-duration')).toHaveText('0 秒');
  await row.locator('[data-action="toggle-round"]').click();
  const detail = page.locator('#round-1-detail');
  await expect(detail.locator('[data-tool-call-id="tool-a"]')).toHaveCount(1);
  await expect(detail.locator('.sd-exit[title*="记录 C7"]')).toHaveAttribute('title', /callId: synthetic-call-7.*不代表独立 provider 请求/);
  await expect(detail.locator('[data-tool-call-id="tool-b"]')).toHaveAttribute('title', /声明调用: synthetic-call-8/);
  const calls = detail.locator('[data-timeline-item="assistant_text"]');
  await expect(calls.nth(0)).toContainText('压缩前模型调用');
  await expect(calls.nth(0).locator('.sd-tool-kind')).toHaveText('TEXT');
  await expect(calls).toHaveCount(1);
  const multiToolCall = detail.locator('[data-call-tools="synthetic-call-8"]');
  await expect(multiToolCall.locator('.sd-call-tools__label')).toHaveText('同一调用');
  await expect(multiToolCall.locator('[data-timeline-item="tool-call"]')).toHaveCount(2);
  await expect(row.locator('.summary-line')).toHaveText('工具读取 × 2 · Shell');
  const toolOnlyCall = multiToolCall.locator('.sd-call-sources');
  await expect(toolOnlyCall.getByRole('button', { name: 'Request', exact: true })).toHaveAttribute('data-payload-id', 'main:req:synthetic-call-8');
  await expect(toolOnlyCall.getByRole('button', { name: 'Response', exact: true })).toHaveAttribute('data-payload-id', 'main:resp:synthetic-call-8');
  for (const id of ['tool-a', 'tool-b']) {
    const tool = detail.locator(`[data-tool-call-id="${id}"]`);
    await expect(tool.locator('.sd-tool-tokens')).toBeEmpty();
    const result = tool.getByRole('button', { name: 'Result', exact: true });
    await expect(result).toHaveAttribute('data-payload-id', 'tool:result:' + id);
    await expect(tool.locator('..').locator('[data-tool-payload-pair]')).not.toHaveAttribute('open');
    await closeContent(await openContent(page, result, 'Result', `synthetic result for ${id}`));
    const pair = await openToolPair(tool);
    await closeContent(await openContent(page, pair.getByRole('button', { name: 'Input', exact: true }), 'Input', INPUTS[id]));
    await expect(pair.locator('section').filter({ has: page.getByRole('heading', { name: 'Tool Result', exact: true }) }).locator('pre'))
      .toHaveText(`synthetic result for ${id}`);
  }
  const timed = detail.locator('[data-tool-call-id="tool-a"]');
  const measuredZero = detail.locator('[data-tool-call-id="tool-b"]');
  await expect(timed.locator('.sd-time-point')).toHaveText('—');
  await expect(timed.locator('.sd-time-duration')).toHaveText('<0.1 秒');
  await expect(timed).toHaveAttribute('data-tool-observed-time', '<0.1 秒');
  await expect(timed).toHaveAttribute('data-tool-visible-name', 'Read');
  await expect(timed).not.toHaveAttribute('data-tool-observed-timestamp');
  await expect(measuredZero.locator('.sd-time-duration')).toHaveText('0 秒');
  await expect(measuredZero.locator('.sd-time-point')).toHaveText(/\d{2}:\d{2}:\d{2}/);
  await expect(measuredZero.locator('.sd-time-point')).toHaveAttribute('title', /非执行器启动时间/);
  await expect(measuredZero).toHaveAttribute('data-tool-observed-timestamp', /\d{2}:\d{2}:\d{2}/);
  await expect(measuredZero).toHaveAttribute('data-tool-observed-time', '0 秒');
  const colors = await Promise.all([timed, measuredZero].map(tool =>
    tool.locator('.sd-action-category').evaluate(el => getComputedStyle(el).backgroundColor)));
  expect(colors[0]).not.toBe(colors[1]);
  const missing = detail.locator('[data-tool-call-id="tool-missing"]');
  await expect(missing.locator('.sd-action-category')).toHaveText('读取');
  await expect(missing).toHaveAttribute('data-status', 'unknown');
  await expect(missing.getByRole('button', { name: 'Result', exact: true })).toHaveCount(0);
  await expect(detail.locator('[data-tool-call-id="tool-b"] .sd-tool-result')).toHaveText('退出码 7');
  await detail.locator('[data-tool-kind-filter]').selectOption('shell');
  await expect(detail.locator('[data-tool-call-id="tool-a"]')).toBeHidden();
  await expect(detail.locator('[data-tool-call-id="tool-b"]')).toBeVisible();
  await detail.locator('[data-tool-kind-filter]').selectOption('read');
  await expect(detail.locator('[data-tool-call-id="tool-b"]')).toBeHidden();
  await expect(toolOnlyCall.getByRole('button', { name: 'Response', exact: true })).toBeVisible();
  await detail.locator('[data-tool-kind-filter]').selectOption('');
  await expect(missing.locator('.sd-time-duration')).toHaveText('—');
  await expect(missing).not.toHaveAttribute('data-tool-observed-time');
  await expect(missing.locator('.sd-exit:empty')).toHaveCount(0);
  const missingPair = await openToolPair(missing);
  await expect(missingPair.locator('pre').first()).toHaveText('内容未记录');
  await expect(missingPair.locator('pre').last()).toHaveText('结果未记录');
  await expect(missingPair.getByRole('button', { name: 'Input', exact: true })).toHaveCount(0);
});

test('tool-only member uses one timeline operation and lazily loads paired bodies side by side', async ({ page }) => {
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
    contentMeasured: true, agents: [], contextSegmentsAvailable: false,
  } }));
  await installTraceFixture(page);
  await page.locator('[data-session-info] > summary').click();
  await expect(page.locator('[data-session-file-text]')).toHaveText('来源未提供可展示的会话文件路径');
  await expect(page.locator('[data-session-file-path] [data-action="copy"]')).toBeHidden();
  const cards = page.locator('[data-session-diagnostics]');
  await expect(cards).toContainText('未记录 Agent 运行');
  await expect(page.locator('[data-token-composition] [data-evidence-state="unavailable"]'))
    .toContainText('未提供可验证的 Token 构成');
  await expect(cards).not.toContainText('0 calls');
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
  await page.locator('[data-trace-round-row] [data-action="toggle-round"]').click();
  await pair.locator('summary').click();
  await expect(input).toContainText('Index changed');
  await expect(input.getByRole('button', { name: 'Refresh page', exact: true })).toBeVisible();
  await expect(input).not.toContainText('COMMAND_END');
});

test('[UI-SD-046] Trace 长命令安全转义且可打开完整正文', async ({ page }) => {
  await page.setViewportSize({ width: 1024, height: 1000 });
  const row = await installTraceFixture(page);
  await row.locator('[data-action="toggle-round"]').click();
  const tool = page.locator('#round-1-detail [data-tool-call-id="tool-b"]');
  await expect(tool.locator('.sd-action-category')).toHaveText('Shell');
  await expect(tool.locator('.sd-tool-cmd')).toContainText('printf');
  await expect(tool.locator('script')).toHaveCount(0);
  expect(await tool.evaluate((element) => element.scrollWidth <= element.clientWidth + 1)).toBe(true);
  const pair = await openToolPair(tool);
  const modal = await openContent(page, pair.getByRole('button', { name: 'Input', exact: true }), 'Input', INPUTS['tool-b']);
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
    await expect(page.getByRole('button', { name: '查看首问', exact: true })).toHaveAttribute('data-payload-id', /^main:req:/);
    const rows = page.locator('[data-trace-round-row]');
    await expect(rows).toHaveCount(2);
    for (const [index, marker, ids] of [[0, 'alpha', ['alpha', 'parallel']], [1, 'beta', ['beta', 'missing']]]) {
      const row = rows.nth(index);
      await expect(row.locator('.summary-col')).toContainText(`检查合成 ${marker}`);
      await expect(row.locator('.summary-col')).not.toContainText(index ? 'alpha' : 'beta');
      await expect(row.locator('.time-col .sd-time-point')).toHaveText(index ? '09:03:08' : '09:02:08');
      await expect(row.locator('.duration-col .sd-time-duration')).toHaveText('—');
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
        if (title === 'Request') {
          await expect(modal.locator('.sd-reading-usage-note').filter({ hasText: 'Tools：' }))
            .toContainText('完整工具清单及参数定义未记录');
        }
        await expect(modal.locator('[data-reading-category="current"]:not([data-reading-source="reconstructed"]) .sd-reading-preview').filter({
          hasText: title === 'Request' ? `检查合成 ${marker}` : `合成 ${marker}`,
        })).toContainText(
          title === 'Request' ? `检查合成 ${marker}` : `合成 ${marker}`,
        );
        if (title === 'Response') {
          await expect(modal.locator('[data-reading-category="toolCall"]')).toHaveCount(2);
          await expect(modal.locator('.sd-payload-tool-link')).toHaveCount(0);
          for (const id of ids) {
            const tool = modal.locator(`[data-reading-category="toolCall"][data-tool-call-id="${id}"]`);
            await expect(tool.locator('.sd-reading-preview')).toContainText(`printf synthetic-${id}`);
            await expect(tool.getByRole('button', { name: 'Input', exact: true })).toHaveAttribute('data-payload-id', 'tool:input:' + id);
            const resultAction = tool.getByRole('button', { name: 'Result', exact: true });
            if (id === 'missing') await expect(resultAction).toHaveCount(0);
            else await expect(resultAction).toHaveAttribute('data-payload-id', 'tool:result:' + id);
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
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
  } finally {
    expect((await request.delete(api, { headers })).status()).toBe(204);
  }
});

test('Side Chat bootstrap and post-compaction user text are kept on separate calls', async ({ page }) => {
  const row = await installTraceFixture(page);
  await page.route(`**${API}/payload/*`, route => {
    const first = decodeURIComponent(route.request().url()).endsWith('synthetic-call-7');
    const base = { kind: 'base_instructions', label: 'Base instructions', source: first ? 'current' : 'reconstructed', text: 'synthetic instructions' };
    const context = first ? [
      { kind: 'side_context', label: 'Side Chat 启动上下文', source: 'current', text: 'synthetic bootstrap' },
    ] : [
      { kind: 'context_snapshot', label: '上下文压缩', source: 'current', text: '源记录含 replacement_history 字段；替换快照未展开。' },
      { kind: 'conversation', label: 'User', source: 'current', text: 'synthetic first question' },
    ];
    return fulfillIndexedJson(route, { kind: 'llm_request', tokens: { input: first ? 300000 : 20000 }, reading: [base, ...context] });
  });
  await row.locator('[data-action="toggle-round"]').click();
  const members = page.locator('#round-1-detail [data-attribution-path*="/request"]');
  await expect(members).toHaveCount(2);
  const modal = page.locator('dialog.payload-modal');
  await members.first().click();
  await expect(modal.locator('li[data-token-part] > span')).toHaveText(['基础指令', 'Side Chat 启动上下文', '未识别']);
  await expect(modal.locator('[data-reading-category="side"] .sd-reading-block-measure')).toHaveText('19 字符 · 约 5 tokens');
  await expect(modal).toContainText('不是用户提问');
  await expect(modal.locator('.sd-reading-compression')).toHaveCount(0);
  await expect(modal).not.toContainText('synthetic first question');
  await closeContent(modal);
  await members.last().click();
  await expect(modal.locator('.sd-reading-compression')).toContainText('替换快照未展开');
  await expect(modal.locator('[data-reading-category="current"] .sd-card-title')).toHaveText('用户原话');
  await expect(modal.locator('li[data-token-part] > span')).toHaveText(['基础指令', '本次内容', '未识别']);
  await expect(modal).not.toContainText('synthetic bootstrap');
});

test('observed Side Chat response without assistant text still shows output evidence and exact task usage', async ({ page }) => {
  const row = await installTraceFixture(page);
  await page.route(`**${API}/payload/*`, route => {
    const path = decodeURIComponent(route.request().url());
    const request = path.includes(':req:');
    return fulfillIndexedJson(route, {
      kind: request ? 'llm_request' : 'llm_response',
      tokens: { input: 4000, output: 100, total: 4100, turnTotal: 6100, ...(request
        ? { fork_tool_result: 2500, fork_tool_result_chars: 10000, fork_tool_result_items: 29 }
        : { compactionOutput: 100, reasoning: 0 }) },
      reading: request ? [{kind: 'instructions', text: 'synthetic instructions'}] : [
        {kind: 'response_evidence', text: '来源记录了本次响应的用量；没有可见助手正文。'},
        {kind: 'response_compaction', text: '紧接着记录了上下文压缩，不是助手正文。'},
      ],
    });
  });
  await page.route(`**${API}/attribution/1/1/*`, route => {
    const url = new URL(route.request().url());
    return fulfillIndexedJson(route, {
      kind: 'llm.' + url.pathname.split('/').at(-1) + '_attribution',
      data: { callId: url.searchParams.get('call_id'), scope: 'main',
        cacheReadTokens: 1000, provenance: {cacheRead: 'provider_reported'}, responseTools: [] },
    });
  });
  await row.locator('[data-action="toggle-round"]').click();
  const round = page.locator('#round-1-detail');
  const modal = page.locator('dialog.payload-modal');
  await round.getByRole('button', {name:'Response',exact:true}).first().click();
  await expect(modal.locator('[data-response-evidence]')).toContainText('没有可见助手正文');
  await expect(modal.locator('[data-response-evidence]')).toContainText('上下文压缩');
  await expect(modal.locator('.sd-reading-turn dd')).toHaveText(['4,000 tokens', '100 tokens', '4,100 tokens', '6,100 tokens']);
  await expect(modal.locator('[data-reading-category]')).toHaveCount(0);
  await expect(modal.locator('[data-payload-raw]')).toHaveCount(0);
  await expect(modal.locator('.sd-reading-composition li strong')).toHaveText('100 tokens · 100%');
  await expect(modal.locator('li[data-token-part="compaction"]')).toContainText('压缩响应输出');
  await closeContent(modal);
  await round.getByRole('button', {name:'Request',exact:true}).first().click();
  await modal.locator('[data-payload-attribution] summary').click();
  await expect(modal.locator('.sd-reading-cache-ratio')).toHaveText('缓存命中 25% · 未命中 75%');
  await expect(modal.locator('.sd-reading-usage-band')).toHaveCount(1);
  await expect(modal.locator('li[data-token-part="fork_tool_result"]')).toContainText('约 2,500 tokens · 62.5%');
  await expect(modal.locator('.sd-reading-panel')).toContainText('不代表实际传输的逐项 Token');
  await expect(modal.locator('[data-reading-category^="fork_"]')).toHaveCount(0);
});
