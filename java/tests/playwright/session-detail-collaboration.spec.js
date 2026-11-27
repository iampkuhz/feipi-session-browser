const { test, expect } = require('@playwright/test');
const { captureDiagnosticScreenshot, waitForPublishedScan } = require('./start-java-fixture-server');

async function openCollaboration(page) {
  const disclosure = page.locator('[data-collaboration-disclosure]');
  await expect(disclosure.locator(':scope > summary')).toBeVisible();
  await expect(disclosure).not.toHaveAttribute('open');
  await disclosure.locator(':scope > summary').press('Enter');
  await expect(disclosure).toHaveAttribute('open');
  return disclosure.locator('[data-collaboration]');
}

// 合成原始记录进入真实 single-file import；没有替换 collaboration/execution DTO。
function claudeSource(nested) {
  const assistant = (uuid, content, extra = {}) => ({ type: 'assistant', uuid, sessionId: 'synthetic-collaboration',
    message: { id: uuid, role: 'assistant', content }, ...extra });
  const tool = (id, prompt) => ({ type: 'tool_use', id, name: 'Agent', input: { prompt } });
  return [
    { type: 'user', uuid: 'user', sessionId: 'synthetic-collaboration', message: { role: 'user', content: 'Synthetic collaboration evidence only' } },
    assistant('root', [tool('shared', 'Review synthetic parser'), ...(!nested ? [tool('second', 'Verify synthetic UI')] : []),
      ...Array.from({ length: 6 }, (_, i) => tool('extra-' + i, 'Synthetic independent task ' + i))]),
    assistant('a', [tool('nested-delegate', 'Verify synthetic UI')], { agentId: 'worker-same-prefix-001', isSidechain: true, parent_tool_use_id: 'shared' }),
    assistant('b', [{ type: 'text', text: 'Synthetic child B answer, not delivery confirmation' }],
      { agentId: 'worker-same-prefix-002', isSidechain: true, parent_tool_use_id: nested ? 'nested-delegate' : 'second' }),
    assistant('anonymous', [{ type: 'text', text: 'Synthetic anonymous context' }], { isSidechain: true }),
  ];
}

function codexSource(waitCount = 25, laterError = false) {
  const records = [{ type: 'session_meta', payload: { id: 'synthetic-wait' } }];
  for (let i = 0; i < 8; i++) {
    records.push({ type: 'response_item', payload: { type: 'function_call', call_id: 'spawn-' + i, name: 'spawn_agent', arguments: JSON.stringify({ message: 'Synthetic task ' + i }) } });
    records.push({ type: 'response_item', payload: { type: 'function_call_output', call_id: 'spawn-' + i, output: { agent_id: 'worker-' + i } } });
  }
  records.push({ type: 'token_usage_record', payload: { response_id: 'spawn-response', usage: { input_tokens: 10, output_tokens: 2 } } });
  for (let i = 0; i < waitCount; i++) {
    records.push({ type: 'response_item', payload: { type: 'function_call', call_id: 'wait-' + i, name: 'wait_agent', arguments: { targets: ['worker-0'] } } });
    records.push({ type: 'token_usage_record', payload: { response_id: 'wait-response-' + i, usage: { input_tokens: 10, output_tokens: 2 } } });
    const report = laterError && i === waitCount - 1
      ? { errored: 'Synthetic later error report' }
      : { completed: 'Synthetic report, not permanent status' };
    records.push({ type: 'response_item', payload: { type: 'function_call_output', call_id: 'wait-' + i, output: { status: { 'worker-0': report } } } });
  }
  return records;
}

async function upload(request, baseURL, source, records) {
  const response = await request.post('/api/imports', { headers: { Origin: new URL(baseURL).origin },
    multipart: { source, file: { name: 'synthetic-collaboration.jsonl', mimeType: 'application/x-ndjson',
      buffer: Buffer.from(records.map(JSON.stringify).join('\n') + '\n') } } });
  expect(response.status()).toBe(201);
  return response.json();
}

// 证据默认折叠；通过原生 summary 展开后保持原有原文/定位断言。
async function openEvidence(button) {
  await expect(button).toBeAttached();
  if (!await button.isVisible()) await button.locator('xpath=ancestor::details[1]').locator('summary').click();
}

async function openRelatedExchanges(host) {
  const entry = host.locator('[data-collaboration-exchanges]').first();
  await openEvidence(entry);
  await entry.click();
  // 旧视图的 Result 已可见也不能提前打开；新往来窗口会替换并折叠它。
  await expect(host.locator('[data-collaboration-context]')).toHaveText(/ · 协作往来$/);
}

// 完整 Result 经真实 HTTP、modal 与复制核对；仅替换浏览器剪贴板权限边界。
async function assertRecordedResult(page, request, api, button, expected) {
  await openEvidence(button);
  const id = await button.getAttribute('data-payload-id');
  const response = await request.get(api + '/payload/' + encodeURIComponent(id));
  expect(response.ok()).toBe(true);
  const payload = await response.json();
  expect(payload.status).toBe('available');
  expect(payload.text || payload.content).toBe(expected);
  await test.info().attach('recorded-result.json', { body: JSON.stringify({ api, id, payload, expected }), contentType: 'application/json' });
  await page.evaluate(() => {
    window.syntheticResultCopies = [];
    Object.defineProperty(navigator, 'clipboard', { configurable: true,
      value: { writeText: async text => window.syntheticResultCopies.push(text) } });
  });
  await button.click();
  const modal = page.locator('dialog.payload-modal');
  await expect(modal).toBeVisible();
  await expect(modal).not.toContainText('Result 内容未记录');
  await expect(modal.locator('pre').last()).toHaveText(expected);
  const originalResult = modal.locator('[data-tool-result-original] > summary').first();
  if (await originalResult.count()) await originalResult.click();
  await modal.getByRole('button', { name: 'Copy', exact: true }).click();
  expect(await page.evaluate(() => window.syntheticResultCopies)).toEqual([expected]);
  await page.keyboard.press('Escape');
}

for (const width of [1440, 1024]) {
  for (const nested of [false, true]) {
    test(`raw collaboration ${nested ? 'nested' : 'siblings'} at ${width}px`, async ({ page, request, baseURL }) => {
      const imported = await upload(request, baseURL, 'claude_code', claudeSource(nested));
      const api = '/api/imports/' + imported.import_id;
      try {
        await page.setViewportSize({ width, height: 1100 });
        const requests = [];
        page.on('request', r => { if (r.url().includes('/api/')) requests.push(new URL(r.url()).pathname); });
        await page.goto(imported.detail_url);
        const host = await openCollaboration(page);
        await expect(host.locator('[data-collaboration-relation]')).toHaveCount(5);
        await expect(host).toContainText('Review synthetic parser');
        await expect(host.locator('[data-collaboration-evidence][open]')).toHaveCount(0);
        expect(await host.getByRole('button').count()).toBeLessThan(12);
        const facts = await (await request.get(api + '/collaboration?limit=100')).json();
        await test.info().attach('collaboration-api.json', { body: JSON.stringify(facts, null, 2), contentType: 'application/json' });
        const b = facts.items.find(row => row.target === 'subagent:worker-same-prefix-002');
        expect(b).toBeTruthy();
        expect(b.actor).toBe(nested ? 'subagent:worker-same-prefix-001' : 'main');
        expect(b.childIncluded).toBe(true);
        expect(facts.participantTotal).toBeGreaterThanOrEqual(4);
        expect(requests.filter(p => /\/payload\//.test(p))).toHaveLength(0);
        expect(requests.filter(p => p.endsWith('/execution'))).toHaveLength(1);
        expect(requests.filter(p => /\/api\/sessions\//.test(p))).toHaveLength(0);
        // continuation preserves the relation direction rather than guessing from tool name.
        const relation = host.locator('[data-collaboration-relation]').filter({ hasText: 'Verify synthetic UI' });
        if (await relation.count() === 0) {
          await host.locator('[data-content-pagination="collaboration"] button').click();
        }
        await expect(relation).toHaveCount(1);
        await host.evaluate(n => n.scrollIntoView({ block: 'start' }));
        await captureDiagnosticScreenshot(page, { path: test.info().outputPath(`default-${nested ? 'nested' : 'siblings'}-${width}.png`) });
        await relation.getByRole('button', { includeHidden: true, name: /查看 .* 首条执行记录/ }).click();
        await expect(page.locator('[data-trace-panel]')).toContainText('Synthetic child B answer');
        expect(requests.filter(p => /\/payload\//.test(p))).toHaveLength(0);
        await expect(page.locator('[data-trace-panel]')).toHaveCount(1);
        await page.locator('[data-execution-collaboration-return]').click();
        await expect(relation.locator('[data-collaboration-agent]')).toBeFocused();
        await relation.locator('[data-collaboration-evidence] > summary').focus();
        await page.keyboard.press('Enter');
        await expect(relation.locator('[data-collaboration-evidence]')).toHaveAttribute('open');
        await openEvidence(relation.getByRole('button', { includeHidden: true, name: '任务 Input', exact: true }));
        await relation.getByRole('button', { includeHidden: true, name: '任务 Input', exact: true }).click();
        await expect(page.locator('dialog.payload-modal')).toContainText('Verify synthetic UI');
        await captureDiagnosticScreenshot(page, { path: test.info().outputPath(`task-input-${width}.png`) });
        await page.keyboard.press('Escape');
        await openEvidence(relation.getByRole('button', { includeHidden: true, name: '定位发起工具', exact: true }));
        await relation.getByRole('button', { includeHidden: true, name: '定位发起工具', exact: true }).click();
        const origin = page.locator('[data-tool-payload-pair][data-tool-id="' + b.toolId + '"]');
        await expect(origin.locator('summary')).toBeFocused();
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await openEvidence(relation.getByRole('button', { includeHidden: true, name: '查看此 Agent 发起的委派', exact: true }));
        await relation.getByRole('button', { includeHidden: true, name: '查看此 Agent 发起的委派', exact: true }).click();
        await expect(host.locator('[data-collaboration-context]')).toContainText('该上下文发起的委派');
        await expect(host).toContainText('所选上下文完整身份：subagent:worker-same-prefix-002');
        await expect(host).toContainText('未记录该上下文发起的明确委派');
        await captureDiagnosticScreenshot(page, { path: test.info().outputPath(`branch-${width}.png`) });
      } finally { expect((await request.delete(api)).status()).toBe(204); }
    });
  }
}

for (const width of [1440, 1024]) {
  test(`raw report preview discloses its bounded sample at ${width}px`, async ({ page, request, baseURL }) => {
    const imported = await upload(request, baseURL, 'codex', codexSource(2, true));
    const api = '/api/imports/' + imported.import_id;
    try {
      await page.setViewportSize({ width, height: 1000 });
      const facts = await (await request.get(api + '/collaboration')).json();
      const relation = facts.items.find(row => row.target === 'subagent:worker-0');
      expect(relation.reportTotal).toBe(5);
      expect(relation.reports).toHaveLength(3);
      expect(relation.reports.at(-1).reportedStatus).toBe('completed');
      const exchanges = await (await request.get(api + '/collaboration?view=exchanges&selection=subagent%3Aworker-0')).json();
      expect(exchanges.items.some(row => row.reportedStatus === 'errored')).toBe(true);
      await page.goto(imported.detail_url);
      const host = await openCollaboration(page);
      const row = host.locator('[data-collaboration-relation]').filter({ hasText: 'Synthetic task 0' });
      await expect(row.locator(':scope > .se-basis')).toContainText('仅预览前 3 / 5 条');
      await expect(row.locator(':scope > .se-basis')).toBeVisible();
      await expect(row.locator('[data-collaboration-evidence]')).not.toHaveAttribute('open');
      await host.getByRole('button', { name: '全部协作往来', exact: true }).click();
      await expect(host.locator('[data-collaboration-relation]').filter({ hasText: '等待工具本次目标报告：errored' })).toBeVisible();
    } finally { expect((await request.delete(api)).status()).toBe(204); }
  });
}

test('raw Codex tail report, bounded exchanges, isolated imports and cursor selection', async ({ page, request, baseURL }) => {
  const a = await upload(request, baseURL, 'codex', codexSource());
  const b = await upload(request, baseURL, 'codex', codexSource());
  const apiA = '/api/imports/' + a.import_id, apiB = '/api/imports/' + b.import_id;
  try {
    const first = await (await request.get(apiA + '/collaboration')).json();
    expect(first.items).toHaveLength(5);
    expect(first.delegationTotal).toBe(8);
    expect(first.items[0].reason).toBe('single_file_not_included');
    expect(first.items[0].reportTotal).toBe(51);
    expect(first.items[0].reports).toHaveLength(3);
    expect((await request.get(apiB + '/collaboration?cursor=' + encodeURIComponent(first.nextCursor))).status()).toBe(400);
    const exchanges = await (await request.get(apiA + '/collaboration?view=exchanges&selection=subagent%3Aworker-0')).json();
    expect(exchanges.total).toBe(52);
    expect(exchanges.items).toHaveLength(20);
    expect((await request.get(apiA + '/collaboration?view=exchanges&selection=subagent%3Aworker-1&cursor=' + encodeURIComponent(exchanges.nextCursor))).status()).toBe(400);
    const all = await (await request.get(apiA + '/collaboration?view=exchanges&selection=subagent%3Aworker-0&limit=100')).json();
    const tail = all.items.at(-1);
    expect(tail.phase).toBe('result_report');
    expect(tail.consumer).toBe('');
    expect(tail.reportedStatus).toBe('completed');
    await page.goto(a.detail_url);
    const host = await openCollaboration(page);
    await expect(host).toContainText('单文件导入未包含 child');
    await expect(host).toContainText('委派工具返回（目标 ID 证据）');
    await openEvidence(host.getByRole('button', { includeHidden: true, name: '委派返回 Result', exact: true }).first());
    await expect(host.getByRole('button', { includeHidden: true, name: '委派返回 Result', exact: true }).first()).toBeVisible();
    await openEvidence(host.locator('[data-collaboration-exchanges]').first());
    await host.locator('[data-collaboration-exchanges]').first().click();
    await expect(host.locator('[data-collaboration-relation]')).toHaveCount(20);
    await host.locator('[data-content-pagination="collaboration"] button').click();
    await expect(host.locator('[data-collaboration-relation]')).toHaveCount(40);
    await host.locator('[data-content-pagination="collaboration"] button').click();
    await expect(host.locator('[data-collaboration-relation]')).toHaveCount(52);
    const last = host.locator('[data-collaboration-relation]').last();
    await expect(last).toContainText('等待工具本次目标报告');
    await expect(last).toContainText('不是整个任务的永久状态');
    await expect(last).toContainText('回传接收方未确认');
    await assertRecordedResult(page, request, apiA, last.getByRole('button', { includeHidden: true, name: '报告 Result', exact: true }),
      JSON.stringify({ status: { 'worker-0': { completed: 'Synthetic report, not permanent status' } } }));
  } finally {
    expect((await request.delete(apiA)).status()).toBe(204);
    expect((await request.delete(apiB)).status()).toBe(204);
  }
});

test('collaboration selection ignores obsolete 200/409/500 and current failures offer recovery', async ({ page, request, baseURL }) => {
  const imported = await upload(request, baseURL, 'codex', codexSource());
  const api = '/api/imports/' + imported.import_id;
  try {
    await page.goto(imported.detail_url);
    const host = await openCollaboration(page);
    await expect(host.locator('[data-collaboration-relation]')).toHaveCount(5);
    for (const status of [200, 409, 500]) {
      let release;
      const gate = new Promise(resolve => { release = resolve; });
      let arrived;
      const arrival = new Promise(resolve => { arrived = resolve; });
      let handled;
      const completed = new Promise(resolve => { handled = resolve; });
      await page.route('**/collaboration?view=exchanges&selection=subagent%3Aworker-0', async route => {
        const response = await route.fetch();
        arrived();
        await gate;
        await route.fulfill({ response, status });
        handled();
      });
      await openEvidence(host.locator('[data-collaboration-exchanges]').first());
      await host.locator('[data-collaboration-exchanges]').first().click();
      await arrival;
      await host.getByRole('button', { includeHidden: true, name: '参与者与深层入口', exact: true }).click();
      await expect(host.locator('[data-collaboration-context]')).toHaveText('参与上下文');
      release();
      await completed;
      await expect(host.locator('[data-collaboration-context]')).toHaveText('参与上下文');
      await page.unroute('**/collaboration?view=exchanges&selection=subagent%3Aworker-0');
      await expect(page.locator('[data-collaboration-status]')).toBeEmpty();
      await host.getByRole('button', { includeHidden: true, name: '全部委派（默认两层）', exact: true }).click();
      await expect(host.locator('[data-collaboration-relation]')).toHaveCount(5);
    }
    await page.route('**/collaboration?view=exchanges&selection=subagent%3Aworker-0', route => route.fulfill({ status: 500, body: '{}' }));
    await openEvidence(host.locator('[data-collaboration-exchanges]').first());
    await host.locator('[data-collaboration-exchanges]').first().click();
    await expect(page.locator('[data-collaboration-status]')).toContainText('HTTP 500');
    await expect(page.locator('[data-collaboration-status]').getByRole('button', { includeHidden: true, name: 'Retry' })).toBeVisible();
    await page.unroute('**/collaboration?view=exchanges&selection=subagent%3Aworker-0');
    await page.locator('[data-collaboration-status]').getByRole('button', { includeHidden: true, name: 'Retry' }).click();
    await expect(host.locator('[data-collaboration-relation]')).toHaveCount(20);
    await host.getByRole('button', { includeHidden: true, name: '全部委派（默认两层）', exact: true }).click();
    await expect(host.locator('[data-collaboration-relation]')).toHaveCount(5);
    await page.route('**/collaboration?view=exchanges&selection=subagent%3Aworker-0', route => route.fulfill({ status: 409, body: '{}' }));
    await openEvidence(host.locator('[data-collaboration-exchanges]').first());
    await host.locator('[data-collaboration-exchanges]').first().click();
    await expect(page.locator('[data-collaboration-status]').getByRole('button', { includeHidden: true, name: 'Refresh page' })).toBeVisible();
    await page.unroute('**/collaboration?view=exchanges&selection=subagent%3Aworker-0');
    await page.locator('[data-collaboration-status]').getByRole('button', { includeHidden: true, name: 'Refresh page' }).click();
    await expect(host.locator('[data-collaboration-relation]')).toHaveCount(5);
  } finally { expect((await request.delete(api)).status()).toBe(204); }
});

// Run each real-scan topology independently; both retain their browser and single-file import assertions.
for (const topology of ['siblings', 'nested']) test(`normal raw Codex ${topology} locates off-page tools without prefix fetches`, async ({ page, request }) => {
  const nested = topology === 'nested';
  const rootId = 'normal-' + topology;
  const fs = require('fs');
  const path = require('path');
  const { spawn } = require('child_process');
  const { runTmpRoot, repoRoot } = require('./runtime-paths');
  const { copyDistribution, resolveJavaEnvironment } = require('./start-java-fixture-server');
  fs.mkdirSync(runTmpRoot, { recursive: true });
  const directory = fs.mkdtempSync(path.join(runTmpRoot, 'collaboration-normal-'));
  const home = path.join(directory, 'home');
  const files = [];
  const meta = (id, parent = '') => ({ type: 'session_meta', timestamp: '2026-11-13T10:00:00Z', payload: {
    id, timestamp: '2026-11-13T10:00:00Z', cwd: '/synthetic/collaboration',
    ...(parent ? { source: { subagent: { thread_spawn: { parent_thread_id: parent } } } } : { source: 'cli' }),
  } });
  const usage = id => ({ type: 'token_usage_record', timestamp: '2026-11-13T10:00:01Z', payload: { response_id: id, usage: { input_tokens: 10, output_tokens: 2 } } });
  const spawnRecords = (id, target, task) => [
    { type: 'response_item', payload: { type: 'function_call', call_id: id, name: 'spawn_agent', arguments: JSON.stringify({ message: task }) } },
    { type: 'response_item', payload: { type: 'function_call_output', call_id: id, output: { agent_id: target } } },
  ];
  const sourceRoot = path.join(home, '.codex', 'sessions', rootId);
  fs.mkdirSync(sourceRoot, { recursive: true });
  const root = [meta(rootId)];
  for (let i = 0; i < 24; i++) root.push(
    { type: 'response_item', payload: { type: 'function_call', call_id: 'earlier-' + i, name: 'exec_command', arguments: JSON.stringify({ cmd: 'printf synthetic-' + i }) } }, usage('earlier-response-' + i));
  root.push(...spawnRecords('shared-tool', 'worker-same-prefix-001', 'Review synthetic parser'));
  if (!nested) root.push(...spawnRecords('second-spawn', 'worker-same-prefix-002', 'Verify synthetic UI'));
  root.push(usage('root-response'));
  root.push({ type: 'response_item', payload: { type: 'function_call', call_id: 'root-wait', name: 'wait_agent', arguments: { targets: ['worker-same-prefix-001'] } } },
    usage('wait-response'), { type: 'response_item', payload: { type: 'function_call_output', call_id: 'root-wait', output: { status: { 'worker-same-prefix-001': { completed: 'Synthetic tail report' } } } } });
  const a = [meta('worker-same-prefix-001', rootId)];
  if (nested) a.push(...spawnRecords('shared-tool', 'worker-same-prefix-002', 'Verify synthetic UI'));
  a.push(usage('a-response'));
  const b = [meta('worker-same-prefix-002', nested ? 'worker-same-prefix-001' : rootId),
    { type: 'response_item', payload: { type: 'message', role: 'assistant', content: [{ type: 'output_text', text: 'Synthetic B final answer' }] } }, usage('b-response')];
  for (const [name, records] of [['root', root], ['a', a], ['b', b]]) {
    const file = path.join(sourceRoot, `rollout-${name === 'root' ? rootId : name}.jsonl`);
    fs.writeFileSync(file, records.map(JSON.stringify).join('\n') + '\n');
    files.push(file);
  }
  fs.writeFileSync(path.join(home, '.codex', 'session_index.jsonl'), JSON.stringify({ id: rootId, thread_name: rootId, updated_at: '2026-11-13T10:00:01Z' }) + '\n');
  fs.mkdirSync(path.join(directory, 'index'), { recursive: true });
  const launcher = copyDistribution(directory);
  const child = spawn(launcher, ['serve', '--host', '127.0.0.1', '--port', '0'], { cwd: repoRoot,
    env: { ...process.env, ...resolveJavaEnvironment(), HOME: home, INDEX_DIR: path.join(directory, 'index'),
      JAVA_OPTS: `"-Duser.home=${home}"`, APP_CLI_OPTS: '', JAVA_TOOL_OPTIONS: '', JDK_JAVA_OPTIONS: '', _JAVA_OPTIONS: '', SESSION_BROWSER_LOG_LEVEL: 'WARN' },
    stdio: ['ignore', 'pipe', 'pipe'] });
  let logs = '';
  const closed = new Promise(resolve => child.once('close', resolve));
  const ready = new Promise((resolve, reject) => {
    child.once('error', reject);
    child.once('exit', code => reject(new Error('Synthetic server exited ' + code + ': ' + logs)));
    for (const stream of [child.stdout, child.stderr]) stream.on('data', data => {
      logs += data;
      const match = logs.match(/serve 已就绪: (http:\/\/127\.0\.0\.1:\d+)/);
      if (match) resolve(match[1]);
    });
  });
  try {
    const base = await ready;
    await waitForPublishedScan(base);
    const api = base + '/api/sessions/codex/' + rootId;
    const facts = await (await request.get(api + '/collaboration')).json();
    expect(facts.items).toHaveLength(2);
    const b = facts.items.find(row => row.target === 'subagent:worker-same-prefix-002');
    expect(b.actor).toBe(nested ? 'subagent:worker-same-prefix-001' : 'main');
    expect(b.childIncluded).toBe(true);
    const a = facts.items.find(row => row.target === 'subagent:worker-same-prefix-001');
    if (nested) expect(a.toolId).not.toBe(b.toolId); // 同一裸 shared-tool 在不同 scope 保持 occurrence。
    const first = await (await request.get(api + '/execution')).json();
    expect(first.items.some(item => item.tool?.toolCallId === b.toolId)).toBe(false);
    const selected = await (await request.get(api + '/execution?agent_context=subagent%3Aworker-same-prefix-002')).json();
    expect(selected.items.every(item => item.group.subagentId === 'worker-same-prefix-002')).toBe(true);
    expect(selected.diagnostics.totalTools).toBe(0);
    for (const width of [1440, 1024]) {
      await page.setViewportSize({ width, height: 1100 });
      await page.goto(base + '/sessions/codex/' + rootId);
      const host = await openCollaboration(page);
      await assertRecordedResult(page, request, api,
        host.getByRole('button', { includeHidden: true, name: '委派返回 Result', exact: true }).first(),
        JSON.stringify({ agent_id: 'worker-same-prefix-001' }));
      await expect(host.locator('[data-collaboration-relation]')).toHaveCount(2);
      await host.evaluate(n => n.scrollIntoView({ block: 'start' }));
      await captureDiagnosticScreenshot(page, { path: test.info().outputPath(`normal-${topology}-${width}.png`) });
      const relation = host.locator('[data-collaboration-relation]').filter({ hasText: 'Verify synthetic UI' });
      const calls = [];
      page.on('request', r => { if (r.url().includes('/execution?')) calls.push(new URL(r.url())); });
      await openEvidence(relation.getByRole('button', { includeHidden: true, name: '定位发起工具', exact: true }));
      await relation.getByRole('button', { includeHidden: true, name: '定位发起工具', exact: true }).click();
      await expect(page.locator('[data-tool-payload-pair][data-tool-id="' + b.toolId + '"] summary')).toBeFocused();
      expect(calls.at(-1).searchParams.get('target')).toBe(b.toolId);
      const inspectChild = relation.locator('[data-collaboration-agent]');
      await inspectChild.click();
      await expect(page.locator('[data-trace-panel]')).toContainText('Synthetic B final answer');
      await page.locator('[data-execution-collaboration-return]').click();
      await expect(inspectChild).toBeFocused();

      // Use actual selection data but hold its response across a second explicit return.
      if (width === 1440) {
        let reached, release;
        const arrived = new Promise(resolve => { reached = resolve; });
        const pending = new Promise(resolve => { release = resolve; });
        const routePattern = '**/execution?agent_context=*&limit=1';
        await page.route(routePattern, async route => {
          const response = await route.fetch();
          expect(response.ok()).toBe(true);
          reached();
          await pending;
          await route.fulfill({ response });
        });
        try {
          const url = page.url();
          await inspectChild.click();
          await arrived;
          await page.locator('[data-execution-collaboration-return]').click();
          await expect(inspectChild).toBeFocused();
          const completed = page.waitForResponse(r => new URL(r.url()).searchParams.has('agent_context'));
          release();
          await completed;
          await expect(inspectChild).toBeFocused();
          await expect(page).toHaveURL(url);
        } finally {
          release();
          await page.unroute(routePattern);
        }
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    }
    // 同一原文件的 object 与 JSON string output，normal/import 对照均完整。
    const raw = fs.readFileSync(path.join(sourceRoot, 'rollout-' + rootId + '.jsonl'), 'utf8').trim().split('\n').map(JSON.parse);
    for (const asString of [false, true]) {
      const records = structuredClone(raw);
      if (asString) for (const event of records) if (event.payload?.type === 'function_call_output') event.payload.output = JSON.stringify(event.payload.output);
      const importedResponse = await request.post(base + '/api/imports', { headers: { Origin: base }, multipart: { source: 'codex', file: {
        name: 'same-source.jsonl', mimeType: 'application/x-ndjson', buffer: Buffer.from(records.map(JSON.stringify).join('\n') + '\n') } } });
      expect(importedResponse.status()).toBe(201);
      const imported = await importedResponse.json();
      const importApi = base + '/api/imports/' + imported.import_id;
      try {
        await page.goto(base + imported.detail_url);
        await openCollaboration(page);
        await assertRecordedResult(page, request, importApi, page.locator('[data-collaboration]').getByRole('button', { includeHidden: true, name: '委派返回 Result', exact: true }).first(), JSON.stringify({ agent_id: 'worker-same-prefix-001' }));
        const importHost = page.locator('[data-collaboration]');
        await expect(importHost.locator('[data-collaboration-agent]')).toHaveCount(0);
        await expect(page.locator('[data-execution-collaboration-return]')).toBeHidden();
        const importedFacts = await (await request.get(importApi + '/collaboration?limit=100')).json();
        expect(importedFacts.items.some(row => row.target === 'subagent:worker-same-prefix-001' && !row.childIncluded)).toBe(true);
        await openRelatedExchanges(page.locator('[data-collaboration]'));
        await assertRecordedResult(page, request, importApi, page.locator('[data-collaboration]').getByRole('button', { includeHidden: true, name: '报告 Result', exact: true }).last(),
          JSON.stringify({ status: { 'worker-same-prefix-001': { completed: 'Synthetic tail report' } } }));
      } finally { expect((await request.delete(importApi)).status()).toBe(204); }
    }
    await page.goto(base + '/sessions/codex/' + rootId);
    await openCollaboration(page);
    await openRelatedExchanges(page.locator('[data-collaboration]'));
    await assertRecordedResult(page, request, api, page.locator('[data-collaboration]').getByRole('button', { includeHidden: true, name: '报告 Result', exact: true }).last(),
      JSON.stringify({ status: { 'worker-same-prefix-001': { completed: 'Synthetic tail report' } } }));
    await test.info().attach(`normal-${topology}-facts.json`, { body: JSON.stringify(facts, null, 2), contentType: 'application/json' });
    await test.info().attach('normal-service-identity.json', { body: JSON.stringify({ pid: child.pid, base, home, files, index: path.join(directory, 'index') }), contentType: 'application/json' });
  } finally {
    if (child.exitCode === null && child.signalCode === null) child.kill('SIGTERM');
    await closed;
    fs.writeFileSync(path.join(directory, 'service.log'), logs);
    // 身份/合成源保留为交付证据；服务已按本次 child handle 精确停止。
  }
});

test('large raw task bodies keep compact response and parsing bounded; unsupported association stays honest', async ({ page, request, baseURL }) => {
  const records = [{ type: 'session_meta', payload: { id: 'synthetic-large-collaboration' } }];
  for (let i = 0; i < 150; i++) {
    records.push({ type: 'response_item', payload: { type: 'function_call', call_id: 'large-' + i, name: 'spawn_agent', arguments: JSON.stringify({ message: 'Synthetic task ' + i + ' ' + 'x'.repeat(9000) }) } });
    records.push({ type: 'response_item', payload: { type: 'function_call_output', call_id: 'large-' + i, output: { agent_id: 'large-worker-' + i } } });
  }
  records.push({ type: 'token_usage_record', payload: { response_id: 'large-response', usage: { input_tokens: 10, output_tokens: 2 } } });
  const imported = await upload(request, baseURL, 'codex', records);
  const api = '/api/imports/' + imported.import_id;
  try {
    const started = performance.now();
    const response = await request.get(api + '/collaboration');
    const text = await response.text();
    const body = JSON.parse(text);
    expect(body.items).toHaveLength(5);
    expect(body.participants).toHaveLength(5);
    expect(body.delegationTotal).toBe(150);
    expect(body.participantTotal).toBe(151);
    expect(text.length).toBeLessThan(20000);
    expect(body.items.every(row => row.task.length <= 180)).toBe(true);
    await test.info().attach('bounded-source-cost.json', { body: JSON.stringify({ sourceBytes: Buffer.byteLength(records.map(JSON.stringify).join('\n')),
      responseBytes: Buffer.byteLength(text), elapsedMs: performance.now() - started,
      facts: body.exchangeTotal, participantTotal: body.participantTotal, pageItems: body.items.length,
      parsingBudgetChars: 262144, argumentLimitChars: 65536, taskPreviewChars: 180,
      note: 'Full frozen content units are streamed for compact joins; response pagination does not claim constant source IO.' }), contentType: 'application/json' });
  } finally { expect((await request.delete(api)).status()).toBe(204); }
  const unsupported = await upload(request, baseURL, 'codex', [
    { type: 'session_meta', payload: { id: 'synthetic-unknown-message' } },
    { type: 'response_item', payload: { type: 'function_call', name: 'send_input', call_id: 'unknown-message', arguments: JSON.stringify({ id: 'imagined-target', message: 'Do not infer a delivery edge' }) } },
    { type: 'token_usage_record', payload: { response_id: 'unknown-response', usage: { input_tokens: 10, output_tokens: 2 } } },
  ]);
  try {
    await page.goto(unsupported.detail_url);
    await openCollaboration(page);
    await expect(page.locator('[data-collaboration]')).toContainText('当前记录未提供可确认的协作关联');
    await expect(page.locator('[data-collaboration]')).toContainText('Qoder / 裸名 send_input');
    await expect(page.locator('[data-collaboration-relation]')).toHaveCount(0);
    await expect(page.locator('[data-execution-collaboration-return]')).not.toBeVisible();
  } finally { expect((await request.delete('/api/imports/' + unsupported.import_id)).status()).toBe(204); }
});

test('explicit third-level branch is reachable without recursively indenting or merging anonymous contexts', async ({ page, request, baseURL }) => {
  const records = claudeSource(true);
  records.find(r => r.uuid === 'b').message.content.push({ type: 'tool_use', id: 'deep-delegate', name: 'Agent', input: { prompt: 'Synthetic deeper review' } });
  records.push({ type: 'assistant', uuid: 'deep', sessionId: 'synthetic-collaboration', agentId: 'worker-same-prefix-003', isSidechain: true,
    parent_tool_use_id: 'deep-delegate', message: { id: 'deep', role: 'assistant', content: [{ type: 'text', text: 'Synthetic C answer' }] } });
  records.push({ type: 'assistant', uuid: 'anonymous-two', sessionId: 'synthetic-collaboration', isSidechain: true,
    message: { id: 'anonymous-two', role: 'assistant', content: [{ type: 'text', text: 'Separate anonymous context, not main' }] } });
  const imported = await upload(request, baseURL, 'claude_code', records);
  const api = '/api/imports/' + imported.import_id;
  try {
    const overview = await (await request.get(api + '/collaboration?limit=100')).json();
    expect(overview.items.some(row => row.target === 'subagent:worker-same-prefix-003')).toBe(false);
    expect(overview.delegationTotal).toBe(9);
    const branch = await (await request.get(api + '/collaboration?selection=subagent%3Aworker-same-prefix-002')).json();
    expect(branch.items).toHaveLength(1);
    expect(branch.items[0]).toMatchObject({ actor: 'subagent:worker-same-prefix-002', target: 'subagent:worker-same-prefix-003', childIncluded: true });
    const participants = await (await request.get(api + '/collaboration?view=participants&limit=100')).json();
    expect(participants.items.filter(p => p.key.includes('unknown-sidechain:'))).toHaveLength(2);
    for (const width of [1440, 1024]) {
      await page.setViewportSize({ width, height: 1100 });
      await page.goto(imported.detail_url);
      const host = await openCollaboration(page);
      await expect(host.locator('[data-collaboration-relation]')).toHaveCount(5);
      const b = host.locator('[data-collaboration-relation]').filter({ hasText: 'Verify synthetic UI' });
      await openEvidence(b.getByRole('button', { includeHidden: true, name: '查看此 Agent 发起的委派', exact: true }));
      await b.getByRole('button', { includeHidden: true, name: '查看此 Agent 发起的委派', exact: true }).click();
      await expect(host).toContainText('Synthetic deeper review');
      await expect(host.locator('[data-collaboration-relation]')).toHaveCount(1);
      await host.evaluate(n => n.scrollIntoView({ block: 'start' }));
      await captureDiagnosticScreenshot(page, { path: test.info().outputPath(`deep-branch-${width}.png`) });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await host.getByRole('button', { includeHidden: true, name: /查看 .* 首条执行记录/ }).click();
      await expect(page.locator('[data-trace-panel]')).toContainText('Synthetic C answer');
    }
  } finally { expect((await request.delete(api)).status()).toBe(204); }
});

function followupSource(inputOnly = false) {
  const rootId = inputOnly ? 'synthetic-followup-only' : 'synthetic-followup';
  const ids = Array.from({ length: 11 }, (_, n) => '11111111-1111-4111-8111-' + String(n + 1).padStart(12, '0'));
  const unknown = '22222222-2222-4222-8222-222222222222';
  const meta = (id, parent) => ({ type: 'session_meta', payload: { id, source: parent ? { subagent: { thread_spawn: { parent_thread_id: parent } } } : 'cli' } });
  const call = (id, name, args, namespace) => ({ type: 'response_item', payload: { type: 'function_call', call_id: id, name, ...(namespace ? { namespace } : {}), arguments: JSON.stringify(args) } });
  const output = (id, value) => ({ type: 'response_item', payload: { type: 'function_call_output', call_id: id, output: value } });
  const usage = id => ({ type: 'token_usage_record', payload: { response_id: id, usage: { input_tokens: 10, output_tokens: 2 } } });
  const root = [meta(rootId)];
  if (!inputOnly) for (const [n, id] of ids.entries()) root.push(call('create-' + n, 'spawn_agent', { message: 'Initial synthetic task ' + n }), output('create-' + n, { agent_id: id }), usage('create-' + n));
  root.push(call('follow-message', 'send_input', { target: inputOnly ? unknown : ids[0], message: 'Synthetic followup <b>message</b>', interrupt: true }, 'multi_agent_v1'), output('follow-message', { submission_id: 'synthetic-submission-message' }), usage('follow-message'));
  root.push(call('follow-items', 'send_input', { target: inputOnly ? unknown : ids[0], items: [{ type: 'text', text: 'Synthetic items followup' }] }, 'multi_agent_v1'), output('follow-items', { submission_id: 'synthetic-submission-items' }), usage('follow-items'));
  root.push(call('follow-unknown', 'send_input', { target: unknown, items: [{ type: 'image', image_url: 'synthetic-image' }] }, 'multi_agent_v1'), output('follow-unknown', { error: 'Synthetic rejected input' }), usage('follow-unknown'));
  const child = [meta(ids[0], rootId), { type: 'response_item', payload: { type: 'message', role: 'assistant', content: [{ type: 'output_text', text: 'Synthetic child answer, not input receipt' }] } }, usage('child')];
  return { rootId, ids, unknown, root, child };
}

for (const invalid of ['marker', 'offset', 'first']) test('collaboration attention rejects wrong ' + invalid, async ({ page, request, baseURL }) => {
  const fixture = followupSource(), imported = await upload(request, baseURL, 'codex', fixture.root), api = '/api/imports/' + imported.import_id;
  try {
    await page.goto(imported.detail_url); await expect(page.locator('[data-collaboration-attention-open]')).toBeVisible();
    await page.route('**' + api + '/collaboration?**', async route => {
      if (!new URL(route.request().url()).searchParams.has('evidence_window')) return route.continue();
      const response = await route.fetch(), body = await response.json();
      if (invalid === 'marker') delete body.evidenceWindow;
      if (invalid === 'offset') body.offset++;
      if (invalid === 'first') body.items[0].reason = 'queued';
      await route.fulfill({ response, json: body });
    });
    const payloads = []; page.on('request', r => { if (r.url().includes('/payload/')) payloads.push(r.url()); });
    await page.locator('[data-collaboration-attention-open]').click();
    await expect(page.locator('[data-collaboration-status]')).toContainText('无法确认提交错误证据窗口');
    await expect(page.locator('[data-collaboration] [data-payload-id], [data-collaboration-relation]')).toHaveCount(0); expect(payloads).toEqual([]);
  } finally { expect((await request.delete(api, { headers: { Origin: new URL(baseURL).origin } })).status()).toBe(204); }
});

test('collaboration attention actual continuation retains protected start and scope', async ({ page, request, baseURL }) => {
  const fixture = followupSource();
  for (let n = 0; n < 15; n++) fixture.root.push(
    { type: 'response_item', payload: { type: 'function_call', call_id: 'later-' + n, namespace: 'multi_agent_v1', name: 'send_input', arguments: JSON.stringify({ target: fixture.unknown, message: 'Synthetic later input ' + n }) } },
    { type: 'response_item', payload: { type: 'function_call_output', call_id: 'later-' + n, output: { submission_id: 'later-submission-' + n } } },
    { type: 'token_usage_record', payload: { response_id: 'later-' + n, usage: { input_tokens: 1, output_tokens: 1 } } });
  const imported = await upload(request, baseURL, 'codex', fixture.root), api = '/api/imports/' + imported.import_id;
  try {
    await page.goto(imported.detail_url); await page.locator('[data-collaboration-attention-open]').click();
    await expect(page.locator('[data-collaboration-relation]')).toHaveCount(20);
    const start = await page.evaluate(() => collaborationView.evidence.start);
    const pending = page.waitForResponse(r => r.url().includes(api + '/collaboration?') && new URL(r.url()).searchParams.has('evidence_window'));
    await page.locator('[data-collaboration-pagination] button').click(); const next = await (await pending).json();
    expect(next.evidenceWindow).toBe('input_submission_error'); expect(next.offset).toBe(start + 20);
    await expect(page.locator('[data-collaboration-relation]')).toHaveCount(31);
    await expect(page.locator('[data-collaboration-pagination]')).toContainText('已载事实 ' + (start + 1) + '–' + (start + 31));
    await expect(page.locator('[data-collaboration-locate]')).toHaveCount(0);
    await page.locator('[data-collaboration-participants]').click(); await expect(page.locator('[data-collaboration-context]')).toHaveText('参与上下文');
    expect(await page.evaluate(() => collaborationView.evidence)).toBeNull();
    await expect(page.locator('[data-collaboration-attention]')).toContainText('全冻结范围已记录1条');
  } finally { expect((await request.delete(api, { headers: { Origin: new URL(baseURL).origin } })).status()).toBe(204); }
});

test('collaboration attention Retry preserves source and 409 requires refresh', async ({ page, request, baseURL }) => {
  const fixture = followupSource(), imported = await upload(request, baseURL, 'codex', fixture.root), api = '/api/imports/' + imported.import_id;
  try {
    await page.goto(imported.detail_url); const entry = page.locator('[data-collaboration-attention-open]'); await expect(entry).toBeVisible();
    let failure = 500;
    await page.route('**' + api + '/collaboration?**', async route => {
      if (new URL(route.request().url()).searchParams.has('evidence_window') && failure) { const status = failure; failure = 0; return route.fulfill({ status, json: { message: 'Synthetic response failure without generation header' } }); }
      return route.continue();
    });
    await entry.click(); await expect(page.locator('[data-collaboration-status] button')).toHaveText('Retry');
    await page.locator('[data-collaboration-status] button').click(); await expect(page.locator('[data-collaboration-relation]').first()).toBeFocused();
    await page.locator('[data-collaboration-attention-return]').click(); await expect(entry).toBeFocused();
    failure = 409; await entry.click(); await expect(page.locator('[data-collaboration-status] button')).toHaveText('Refresh page');
    await expect(page.locator('[data-collaboration-attention]')).toContainText('全冻结范围已记录1条');
  } finally { expect((await request.delete(api, { headers: { Origin: new URL(baseURL).origin } })).status()).toBe(204); }
});

test('collaboration attention later interaction and epoch cancel stale focus not valid data', async ({ page, request, baseURL }) => {
  const fixture = followupSource(), imported = await upload(request, baseURL, 'codex', fixture.root), api = '/api/imports/' + imported.import_id;
  try {
    await page.goto(imported.detail_url); await expect(page.locator('[data-collaboration-attention-open]')).toBeVisible();
    let release, entered; const gate = new Promise(resolve => { release = resolve; }), started = new Promise(resolve => { entered = resolve; });
    await page.route('**' + api + '/collaboration?**', async route => {
      if (!new URL(route.request().url()).searchParams.has('evidence_window')) return route.continue();
      const response = await route.fetch(); entered(); await gate; await route.fulfill({ response });
    });
    await page.locator('[data-collaboration-attention-open]').click(); await started;
    const diagnosis = page.locator('[data-trace-panel] [data-action="status-all"]'); await diagnosis.focus(); release();
    await expect(page.locator('[data-collaboration-relation]').first()).toContainText('工具报告提交错误'); await expect(diagnosis).toBeFocused();
    await page.unroute('**' + api + '/collaboration?**');
    let finish, seen; const hold = new Promise(resolve => { finish = resolve; }), ready = new Promise(resolve => { seen = resolve; });
    await page.route('**' + api + '/collaboration?**', async route => {
      if (!new URL(route.request().url()).searchParams.has('evidence_window')) return route.continue();
      const response = await route.fetch(); seen(); await hold; await route.fulfill({ response });
    });
    await page.locator('[data-collaboration-attention-open]').click(); await ready;
    await page.evaluate(() => { collaborationView.view = 'participants'; collaborationView.selection = ''; return loadCollaborationPage(); });
    finish(); await page.unrouteAll({ behavior: 'wait' });
    await expect(page.locator('[data-collaboration-context]')).toHaveText('参与上下文'); expect(await page.evaluate(() => collaborationView.evidence)).toBeNull();
    // Same-generation participant failure cannot revoke the accepted all-scope summary.
    await page.route('**' + api + '/collaboration?**', route => route.fulfill({ status: 503, json: { message: 'Synthetic temporary failure' } }));
    await page.locator('[data-collaboration-participants]').click(); await expect(page.locator('[data-collaboration-status] button')).toHaveText('Retry');
    await expect(page.locator('[data-collaboration-attention]')).toContainText('全冻结范围已记录1条');
    // UI-only generation event exercises init's central invalidation, not a real server index replacement.
    expect(await page.evaluate(() => { const source = collaborationView.attentionReturn?.source; document.body.setAttribute('data-index-generation', 'synthetic-ui-only-generation'); window.dispatchEvent(new Event('index-snapshot-restored')); return { summary: collaborationView.attention, evidence: collaborationView.evidence, back: validCollaborationAttentionReturn(), connected: !!source?.isConnected }; })).toMatchObject({ summary: null, evidence: null, back: null });
    await expect(page.locator('[data-collaboration-attention]')).toBeHidden();
  } finally { expect((await request.delete(api, { headers: { Origin: new URL(baseURL).origin } })).status()).toBe(204); }
});

test('collaboration attention queued unknown and missing authority never assert success or zero', async ({ page, request, baseURL }) => {
  const fixture = followupSource(true);
  fixture.root.find(row => row.payload?.type === 'function_call_output' && row.payload.call_id === 'follow-unknown').payload.output = { submission_id: 'synthetic-queued' };
  const imported = await upload(request, baseURL, 'codex', fixture.root), api = '/api/imports/' + imported.import_id;
  try {
    await page.goto(imported.detail_url); await openCollaboration(page); await expect(page.locator('[data-collaboration-all-exchanges]')).toBeVisible();
    expect(await page.evaluate(() => collaborationView.attention.count)).toBe(0); await expect(page.locator('[data-collaboration-attention]')).toBeHidden();
    await page.route('**' + api + '/collaboration?**', async route => { const response = await route.fetch(), body = await response.json(); delete body.inputSubmissionErrorReportTotal; delete body.firstInputSubmissionError; await route.fulfill({ response, json: body }); });
    await page.reload(); await openCollaboration(page); await expect(page.locator('[data-collaboration-all-exchanges]')).toBeVisible(); expect(await page.evaluate(() => collaborationView.attention)).toBeNull();
    await expect(page.locator('[data-collaboration-attention]')).toBeHidden();
    await page.unrouteAll({ behavior: 'wait' }); await page.route('**' + api + '/collaboration?**', route => route.fulfill({ status: 500, json: { message: 'Synthetic unavailable' } }));
    await page.reload(); await openCollaboration(page); await expect(page.locator('[data-collaboration-status] button')).toHaveText('Retry');
    expect(await page.evaluate(() => collaborationView.attention)).toBeNull(); await expect(page.locator('[data-collaboration-attention]')).toBeHidden();
  } finally { expect((await request.delete(api, { headers: { Origin: new URL(baseURL).origin } })).status()).toBe(204); }
});

test('collaboration attention UI-only whole window qualification matrix includes reports and creation', async ({ page, request, baseURL }) => {
  const fixture = followupSource(), imported = await upload(request, baseURL, 'codex', fixture.root), api = '/api/imports/' + imported.import_id;
  try {
    await page.goto(imported.detail_url); await page.locator('[data-collaboration-attention-open]').click(); await expect(page.locator('[data-collaboration-relation]')).toHaveCount(1);
    const matrix = await page.evaluate(() => {
      const original = collaborationView.page, error = original.items[0], delegate = { ...error, kind: 'delegate', phase: 'declaration', task: 'Synthetic matrix', reports: [], reportTotal: 0 };
      const checks = ['unique', 'ambiguous', 'unconfirmed', undefined].map(state => {
        const row = { ...error, actor: 'unknown', actorIdentityReason: 'actor_unknown', toolPayloadState: state }, report = { ...row, kind: 'delegate' };
        const task = { ...delegate, toolPayloadState: state, reports: [report], reportTotal: 1 };
        const html = collaborationRelation(row, false) + collaborationRelation(task, false, report) + collaborationReport(report);
        const block = document.createElement('div'); block.innerHTML = html;
        return { state: state || 'missing', raw: block.querySelectorAll('[data-payload-id]').length, locate: block.querySelectorAll('[data-collaboration-locate]').length, text: block.textContent };
      });
      acceptCollaborationAttention({ ...original, reasons: { facts_truncated: 1 } });
      const limitation = document.querySelector('[data-collaboration-attention]').textContent;
      return { checks, limitation };
    });
    expect(matrix.checks[0].raw).toBeGreaterThan(4); expect(matrix.checks.every(row => row.locate === 0)).toBe(true);
    for (const row of matrix.checks.slice(1)) { expect(row.raw).toBe(0); expect(row.text).toMatch(/原文无法唯一定位|发起记录未确认/); }
    expect(matrix.limitation).toContain('范围存在截断/解析或身份限制');
    await test.info().attach('attention-ui-only-matrix.json', { body: JSON.stringify(matrix), contentType: 'application/json' });
  } finally { expect((await request.delete(api, { headers: { Origin: new URL(baseURL).origin } })).status()).toBe(204); }
});

test('collaboration attention actual unique tool multiple recorded results', async ({ page, request, baseURL }) => {
  const fixture = followupSource();
  fixture.root.splice(fixture.root.length - 1, 0,
    { type: 'response_item', payload: { type: 'function_call_output', call_id: 'follow-unknown', output: { error: 'Synthetic second recorded result' } } });
  const imported = await upload(request, baseURL, 'codex', fixture.root), api = '/api/imports/' + imported.import_id;
  try {
    const traffic = []; page.on('request', r => { if (r.url().includes('/payload/')) traffic.push(r.url()); });
    await page.goto(imported.detail_url); await page.locator('[data-collaboration-attention-open]').click();
    const first = page.locator('[data-collaboration-relation]').first(); await expect(first).toContainText('工具报告提交错误');
    const actual = await page.evaluate(() => collaborationView.page);
    expect(actual.evidenceWindow).toBe('input_submission_error'); expect(actual.items[0].toolPayloadState).toBe('unique');
    await first.locator('summary').click(); await first.getByRole('button', { name: '工具全部已记录 Result', exact: true }).click();
    const modal = page.locator('dialog.payload-modal'); await expect(modal).toContainText('Synthetic rejected input'); await expect(modal).toContainText('Synthetic second recorded result');
    await page.keyboard.press('Escape');
    expect(traffic.map(url => [decodeURIComponent(new URL(url).pathname).split('/payload/').at(-1), new URL(url).searchParams.get('view')])).toEqual([
      ['tool:result:follow-unknown', 'local_results'],
    ]);
    await test.info().attach('attention-qualification-multi-result.json', { body: JSON.stringify({ actual, traffic }), contentType: 'application/json' });
  } finally { expect((await request.delete(api, { headers: { Origin: new URL(baseURL).origin } })).status()).toBe(204); }
});


test('local result inclusion keeps unitemized wait report first-visible without inventing relations', async ({ page, request, baseURL }) => {
  const imported = await upload(request, baseURL, 'codex', codexSource(1));
  const api = '/api/imports/' + imported.import_id;
  const expected = JSON.stringify({ status: { 'worker-0': { completed: 'Synthetic report, not permanent status' } } });
  try {
    const response = await request.get(api + '/payload/tool:result:wait-0?view=local_results');
    expect(response.ok()).toBe(true);
    const body = await response.json();
    expect(body.payload.status).toBe('available');
    expect(body.payload.text).toBe(expected);
    expect(body.localResults.items).toEqual([]);
    await page.goto(imported.detail_url);
    await page.evaluate(() => {
      window.syntheticResultCopies = [];
      Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText: async text => window.syntheticResultCopies.push(text) } });
    });
    const host = await openCollaboration(page);
    await openRelatedExchanges(host);
    const report = host.locator('[data-collaboration-relation]').filter({ hasText: '等待工具本次目标报告：completed' }).last();
    const result = report.getByRole('button', { includeHidden: true, name: '报告 Result', exact: true });
    await openEvidence(result);
    await result.click();
    const modal = page.locator('dialog.payload-modal');
    const unitemized = modal.locator('[data-unitemized-tool-output]');
    await expect(unitemized).toBeVisible();
    await expect(unitemized).toContainText('包含关系未确认');
    await expect(unitemized.locator('pre')).toHaveText(expected);
    await expect(unitemized.locator('[data-local-reference], [data-local-result], button')).toHaveCount(0);
    const original = modal.locator('[data-tool-result-original]').first();
    await expect(original).not.toHaveAttribute('open');
    await original.locator(':scope > summary').click();
    await modal.getByRole('button', { name: 'Copy', exact: true }).click();
    expect(await page.evaluate(() => window.syntheticResultCopies)).toEqual([expected]);
    await page.keyboard.press('Escape');
    // 截断包装只能展示当前安全原文，不能当成完整 output 解包。
    const partial = JSON.stringify({ output: 'synthetic recorded partial', note: 'synthetic truncation marker' });
    await page.route('**/payload/tool%3Aresult%3Await-0?view=local_results', async route => {
      const originalResponse = await route.fetch();
      const projected = await originalResponse.json();
      projected.payload.text = partial;
      projected.payload.truncated = true;
      await route.fulfill({ response: originalResponse, json: projected });
    });
    await result.click();
    await expect(unitemized).toContainText('已截断；包含关系未确认');
    await expect(unitemized.locator('pre')).toHaveText(partial);
    await expect(original).not.toHaveAttribute('open');
    await original.locator(':scope > summary').click();
    await original.getByRole('button', { name: 'Copy', exact: true }).click();
    expect(await page.evaluate(() => window.syntheticResultCopies)).toEqual([expected, partial]);
  } finally {
    expect((await request.delete(api)).status()).toBe(204);
  }
});

test('identical raw tool IDs stay scoped per import; recorded empty does not create missing Result', async ({ page, request, baseURL }) => {
  function source(label) {
    const records = [{ type: 'session_meta', payload: { id: 'synthetic-tool-scope' } }];
    for (const [id, output] of [['shared-tool', label], ['empty-tool', ''], ['missing-tool', undefined]]) {
      records.push({ type: 'response_item', payload: { type: 'function_call', call_id: id, name: 'exec_command',
        arguments: JSON.stringify({ cmd: 'printf synthetic-' + id }) } });
      records.push({ type: 'token_usage_record', payload: { response_id: 'synthetic-response-' + id, usage: { input_tokens: 1, output_tokens: 1 } } });
      if (output !== undefined) records.push({ type: 'response_item', payload: { type: 'function_call_output', call_id: id, output } });
    }
    return records;
  }
  const traffic = [];
  page.on('request', request => {
    const url = new URL(request.url());
    if (url.pathname.includes('/payload/')) traffic.push(url);
  });
  const uploads = [];
  try {
    for (const label of ['Synthetic left import only', 'Synthetic right import only']) {
      uploads.push(await upload(request, baseURL, 'codex', source(label)));
    }
    for (const [i, imported] of uploads.entries()) {
      const api = '/api/imports/' + imported.import_id;
      const ownText = i ? 'Synthetic right import only' : 'Synthetic left import only';
      const otherText = i ? 'Synthetic left import only' : 'Synthetic right import only';
      await page.goto(imported.detail_url);
      await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
      await page.getByRole('button', { name: 'Expand all', exact: true }).click();
      const trace = page.locator('[data-trace-panel]');
      const result = id => trace.locator('[data-tool-call-id="' + id + '"] [data-payload-kind="tool_result"]');
      const start = traffic.length;
      await result('shared-tool').click();
      const modal = page.locator('dialog.payload-modal[open]');
      await expect(modal.locator('[data-reading-category="result"]')).toContainText(ownText);
      await expect(modal).not.toContainText(otherText);
      expect(traffic.slice(start).map(url => [decodeURIComponent(url.pathname), url.searchParams.get('view')]))
        .toEqual([[api + '/payload/tool:result:shared-tool', 'local_results']]);
      await page.keyboard.press('Escape');

      const empty = await (await request.get(api + '/payload/' + encodeURIComponent('tool:result:empty-tool') + '?view=local_results')).json();
      const missing = await (await request.get(api + '/payload/' + encodeURIComponent('tool:result:missing-tool'))).json();
      expect(empty.payload.status).toBe('available');
      expect(missing.status).toBe('missing');
      await result('empty-tool').click();
      await expect(modal).toContainText(/已记录空结果|已记录工具返回/);
      await page.keyboard.press('Escape');
      await expect(result('missing-tool')).toHaveCount(0);
      const pair = trace.locator('[data-tool-payload-pair][data-tool-id="missing-tool"]');
      await pair.locator('summary').click();
      await expect(pair).toContainText('结果未记录');
    }
  } finally {
    for (const imported of uploads) {
      expect((await request.delete('/api/imports/' + imported.import_id)).status()).toBe(204);
    }
  }
});

async function startLongOperationNormal(request, partial, inputForChild08, childIdentities) {
  const fs = require('fs'), path = require('path'), { spawn } = require('child_process');
  const { runTmpRoot } = require('./runtime-paths'), { copyDistribution, resolveJavaEnvironment } = require('./start-java-fixture-server');
  fs.mkdirSync(runTmpRoot, { recursive: true }); const directory = fs.mkdtempSync(path.join(runTmpRoot, 'long-operation-')), home = path.join(directory, 'home');
  const source = path.join(home, '.codex/sessions/synthetic'); fs.mkdirSync(source, { recursive: true });
  const rootId = 'synthetic-long-operation-root', children = childIdentities || Array.from({ length: 10 }, (_, i) => 'synthetic-long-child-' + String(i + 1).padStart(2, '0'));
  const meta = (id, parent) => ({ type: 'session_meta', payload: { id, source: parent ? { subagent: { thread_spawn: { parent_thread_id: parent } } } : 'cli' } });
  const call = (id, name, args) => ({ type: 'response_item', payload: { type: 'function_call', call_id: id, name, arguments: JSON.stringify(args) } });
  const output = (id, value) => ({ type: 'response_item', payload: { type: 'function_call_output', call_id: id, output: value } });
  const usage = id => ({ type: 'token_usage_record', payload: { response_id: id, usage: { input_tokens: 10, output_tokens: 2 } } });
  const end = (id, ms) => ({ type: 'event_msg', payload: { type: 'exec_command_end', call_id: id, duration: { secs: Math.floor(ms / 1000), nanos: ms % 1000 * 1000000 }, exit_code: 0, status: 'completed' } });
  const root = [meta(rootId)]; children.forEach((id, i) => root.push(call('long-spawn-' + i, 'spawn_agent', { message: 'Synthetic independent task ' + String(i + 1).padStart(2, '0') }), output('long-spawn-' + i, { agent_id: id })));
  root.push(usage('long-delegations'), call('long-parent-wait', 'wait_agent', { targets: [children[0]] }), usage('long-parent-wait'), output('long-parent-wait', { status: { [children[0]]: { completed: 'Synthetic wait report only' } } }), end('long-parent-wait', 2000));
  const raws = [[rootId, root]];
  children.forEach((id, i) => { const rows = [meta(id, rootId)]; for (let n = 0; n < (i === 0 ? 24 : i === 7 ? 200 : 1); n++) { const tool = 'long-check-' + String(i + 1).padStart(2, '0') + '-' + n; rows.push(call(tool, 'exec_command', i === 7 && inputForChild08 ? inputForChild08(n) : { cmd: 'echo SYNTHETIC_LONG_CHILD_' + String(i + 1).padStart(2, '0') + '_NOT_EXECUTED' }), usage(tool), output(tool, 'Synthetic complete Result ' + tool), partial && i === 7 && n === 199 ? { type: 'event_msg', payload: { type: 'exec_command_end', call_id: tool, exit_code: 0, status: 'completed' } } : end(tool, i === 8 ? 35000 : i === 9 ? 750 : 500)); } raws.push([id, rows]); });
  for (const [id, rows] of raws) fs.writeFileSync(path.join(source, 'rollout-' + id + '.jsonl'), rows.map(JSON.stringify).join('\n') + '\n');
  fs.writeFileSync(path.join(home, '.codex/session_index.jsonl'), [rootId, ...children].map(id => JSON.stringify({ id, thread_name: 'Synthetic long operations ' + id })).join('\n') + '\n');
  const child = spawn(copyDistribution(directory), ['serve', '--host', '127.0.0.1', '--port', '0'], { env: { ...process.env, ...resolveJavaEnvironment(), HOME: home, INDEX_DIR: path.join(directory, 'index'), SESSION_BROWSER_LOG_LEVEL: 'WARN', JAVA_OPTS: `"-Duser.home=${home}"`, APP_CLI_OPTS: '', JAVA_TOOL_OPTIONS: '', JDK_JAVA_OPTIONS: '', _JAVA_OPTIONS: '' }, stdio: ['ignore', 'pipe', 'pipe'] });
  let logs = '';
  const running = () => child.exitCode === null && child.signalCode === null;
  const close = async (retainRuntime = true) => {
    if (running()) { child.kill('SIGTERM'); await new Promise(resolve => child.once('exit', resolve)); }
    fs.writeFileSync(path.join(directory, 'service.log'), logs);
    if (!retainRuntime) {
      for (const name of ['app-cli', 'index']) fs.rmSync(path.join(directory, name), { force: true, recursive: true });
    }
  };
  try {
    // HTTP readiness precedes the first automatic scan; wait for source readiness, not a longer assertion timeout.
    const base = await new Promise((resolve, reject) => {
      child.once('error', reject); child.once('exit', c => reject(new Error('early ' + c + logs)));
      for (const stream of [child.stdout, child.stderr]) stream.on('data', d => {
        logs += d; const ready = logs.match(/serve 已就绪: (http:\/\/127\.0\.0\.1:\d+)/);
        if (ready) resolve(ready[1]);
      });
    });
    await waitForPublishedScan(base);
    const api = base + '/api/sessions/codex/' + rootId; await expect.poll(async () => (await request.get(api + '/execution')).status()).toBe(200);
    const data = await (await request.get(api + '/execution')).json(), signals = data.diagnostics.longOperations;
    expect(signals).toMatchObject({ totalTools: 232, measuredTools: partial ? 231 : 232, unknownTools: partial ? 1 : 0, otherKindTools: 0, unconfirmedIdentityTools: 0 });
    expect(data.diagnostics.workloadSignals.candidates[0]).toMatchObject({ subagentId: children[7], measuredWorkNanos: partial ? '99500000000' : '100000000000', measuredTools: partial ? 199 : 200, totalTools: 200, longest: { durationNanos: '500000000' } });
    expect(signals.candidates[0]).toMatchObject({ durationNanos: '35000000000', tool: { toolCallId: 'long-check-09-0', subagentId: children[8] } });
    return { snapshot: { base, rootId, children, raws, api, data, signals, directory }, close, running };
  } catch (error) {
    await close();
    throw error;
  }
}


const hotspotInput = n => ({ cmd: n < 20 ? 'synthetic-alpha' : 'synthetic-beta' });
function hotspotImportSource(partial = false, input = hotspotInput) {
  // Explicit main source is deliberately not the parent-dependent normal child source.
  const call = (i, args) => ({ type: 'response_item', payload: { type: 'function_call', call_id: 'hotspot-' + i, name: 'exec_command', arguments: JSON.stringify(args) } });
  const rows = [{ type: 'session_meta', payload: { id: 'synthetic-hotspot-main', source: 'cli' } }];
  for (let i = 0; i < 200; i++) rows.push(call(i, input(i)), { type: 'token_usage_record', payload: { response_id: 'hotspot-' + i, usage: { input_tokens: 1, output_tokens: 1 } } }, { type: 'response_item', payload: { type: 'function_call_output', call_id: 'hotspot-' + i, output: 'Synthetic hotspot result ' + i } }, { type: 'event_msg', payload: { type: 'exec_command_end', call_id: 'hotspot-' + i, exit_code: 0, status: 'completed', ...(!partial || i !== 199 ? { duration: { secs: 0, nanos: 500000000 } } : {}) } });
  return rows;
}

async function assertHotspotTrace(page, url, api, maximum, measured, hasChild) {
  const calls = [];
  page.on('request', request => {
    if (request.url().includes('/api/')) calls.push(new URL(request.url()));
  });
  await page.setViewportSize({ width: 1024, height: 900 });
  await page.goto(url);
  await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  const judgment = page.locator('[data-execution-judgment]');
  const disclosure = hasChild ? judgment.locator('[data-execution-long-operations]')
    : judgment.locator('details').filter({ has: page.getByText('工具耗时证据', { exact: true }) });
  await expect(disclosure).not.toHaveAttribute('open');
  await disclosure.locator(':scope > summary').press('Enter');
  const panel = hasChild ? disclosure.locator('[data-execution-signal-metric="cumulative"]') : disclosure;
  if (hasChild) await panel.locator(':scope > summary').press('Enter');
  const hotspot = panel.locator('[data-execution-same-input]').filter({ hasText: 'synthetic-beta' });
  await expect(hotspot).toContainText('synthetic-beta');
  await expect(hotspot).toContainText(`已测 ${measured}/180 次`);
  if (hasChild) {
    const selection = 'subagent:' + maximum.tool.subagentId;
    const context = panel.locator('[data-execution-long-operation]').filter({ has: page.locator('[data-execution-same-input]').filter({ hasText: 'synthetic-beta' }) })
      .locator('[data-execution-task-context]');
    await expect(context).toHaveAttribute('data-collaboration-exchanges', selection);
    const exchanges = page.waitForResponse(response => {
      const url = new URL(response.url());
      return url.pathname.endsWith('/collaboration') && url.searchParams.get('view') === 'exchanges'
        && url.searchParams.get('selection') === selection;
    });
    await context.click();
    const response = await exchanges;
    expect(response.ok()).toBe(true);
    expect((await response.json()).selection).toBe(selection);
    const collaboration = page.locator('[data-collaboration-disclosure]');
    await expect(collaboration).toHaveAttribute('open');
    await expect(collaboration.locator('[data-collaboration-context]')).toBeFocused();
    await collaboration.locator('[data-collaboration-hotspot-return]').click();
    await expect(context).toBeFocused();
    await expect(hotspot).toBeVisible();
    const failExchanges = url => url.pathname.endsWith('/collaboration')
      && url.searchParams.get('view') === 'exchanges' && url.searchParams.get('selection') === selection;
    await page.route(failExchanges, route => route.fulfill({ status: 500, json: { error: 'synthetic' } }));
    await context.click();
    await expect(collaboration.locator('[data-collaboration-status]').getByRole('button', { name: 'Retry' })).toBeVisible();
    await collaboration.locator('[data-collaboration-hotspot-return]').click();
    await expect(context).toBeFocused();
    await page.unroute(failExchanges);
  }
  expect(calls.filter(u => u.pathname.includes('/payload/'))).toHaveLength(0);
  const entry = hotspot.locator('[data-execution-locate]');
  const id = maximum.tool.toolCallId;
  await expect(entry).toHaveAttribute('data-execution-locate', id);
  const posted = page.waitForRequest(r => {
    const u = new URL(r.url());
    return u.pathname === new URL(api, url).pathname + '/execution' && u.searchParams.get('target') === id;
  });
  await entry.click();
  await posted;
  const pair = page.locator('[data-tool-payload-pair][data-tool-id="' + id + '"]');
  await expect(pair.locator('summary')).toBeFocused();
  await expect(pair.locator('.sd-tool-payload-grid pre').first()).toContainText('synthetic-beta');
  const result = hasChild ? 'Synthetic complete Result ' + id : 'Synthetic hotspot result ' + id.split('-').at(-1);
  await expect(pair.locator('.sd-tool-payload-grid pre').last()).toContainText(result);
  const row = page.locator('[data-tool-call-id="' + id + '"]');
  await expect(row).toHaveAttribute('data-declaring-call-scope', hasChild ? 'subagent' : 'main');
  expect(calls.filter(u => u.pathname.endsWith('/execution') && u.searchParams.has('cursor'))).toHaveLength(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
}

test('normal same-input hotspot finds the exact child action in Trace', async ({ page, request }) => {
  const server = await startLongOperationNormal(request, false, hotspotInput);
  try {
    const { base, rootId, api, data } = server.snapshot;
    const maximum = data.diagnostics.workloadSignals.candidates[0].sameInputMaximum;
    expect(maximum).toMatchObject({ measuredWorkNanos: '90000000000', measuredTools: 180, totalTools: 180,
      distinctInputs: 2, identifiedInputs: 200, totalInputs: 200, tool: { inputPreview: 'synthetic-beta' } });
    await assertHotspotTrace(page, base + '/sessions/codex/' + rootId, api, maximum, 180, true);
  } finally {
    await server.close(false);
  }
});

test('import same-input hotspot preserves partial measurement and targets its original action', async ({ page, request, baseURL }) => {
  const imported = await upload(request, baseURL, 'codex', hotspotImportSource(true));
  const api = baseURL + '/api/imports/' + imported.import_id;
  try {
    const response = await request.get(api + '/execution');
    expect(response.ok()).toBe(true);
    const data = await response.json();
    const maximum = data.diagnostics.workloads[0].sameInputMaximum;
    expect(maximum).toMatchObject({ measuredWorkNanos: '89500000000', measuredTools: 179, totalTools: 180,
      unknownTools: 1, distinctInputs: 2, identifiedInputs: 200, totalInputs: 200, tool: { inputPreview: 'synthetic-beta' } });
    await assertHotspotTrace(page, new URL(imported.detail_url, baseURL).href, api, maximum, 179, false);
  } finally {
    expect((await request.delete(api)).status()).toBe(204);
  }
});
