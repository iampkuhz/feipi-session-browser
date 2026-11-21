const { test: baseTest, expect } = require('@playwright/test');
const { captureDiagnosticScreenshot, waitForPublishedScan } = require('./start-java-fixture-server');

// 只读场景共享本 worker 内已完整发布的合成索引；每个用例仍有独立页面。
const test = baseTest.extend({
  readLongOperationNormal: [async ({}, use) => {
    const servers = new Map();
    try {
      await use(async (request, partial, read, inputForChild08) => {
        if (inputForChild08 && inputForChild08 !== hotspotInput) {
          throw new Error('Custom synthetic input must use an isolated long-operation server');
        }
        const key = (partial ? 'partial' : 'full') + (inputForChild08 ? '-hotspot' : '');
        if (!servers.has(key)) {
          servers.set(key, await startLongOperationNormal(request, partial, inputForChild08));
        }
        const server = servers.get(key);
        try {
          if (!server.running()) throw new Error('Shared synthetic long-operation server stopped: ' + key);
          await read(structuredClone(server.snapshot));
        } catch (error) {
          server.failed = true;
          throw error;
        }
      });
    } finally {
      await Promise.all([...servers.values()].map(server => server.close(server.failed === true)));
    }
  }, { scope: 'worker' }],
});

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

for (const width of [1440, 390]) {
  for (const nested of [false, true]) {
    test(`raw collaboration ${nested ? 'nested' : 'siblings'} at ${width}px`, async ({ page, request, baseURL }) => {
      const imported = await upload(request, baseURL, 'claude_code', claudeSource(nested));
      const api = '/api/imports/' + imported.import_id;
      try {
        await page.setViewportSize({ width, height: 1100 });
        const requests = [];
        page.on('request', r => { if (r.url().includes('/api/')) requests.push(new URL(r.url()).pathname); });
        await page.goto(imported.detail_url);
        const host = page.locator('[data-collaboration]');
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
        expect(requests.filter(p => /\/execution$/.test(p))).toHaveLength(1);
        expect(requests.filter(p => /\/api\/sessions\//.test(p))).toHaveLength(0);
        // continuation preserves the relation direction rather than guessing from tool name.
        while (!(await host.innerText()).includes('Verify synthetic UI')) {
          await host.locator('[data-content-pagination="collaboration"] button').click();
        }
        await host.evaluate(n => n.scrollIntoView({ block: 'start' }));
        await captureDiagnosticScreenshot(page, { path: test.info().outputPath(`default-${nested ? 'nested' : 'siblings'}-${width}.png`) });
        const relation = host.locator('[data-collaboration-relation]').filter({ hasText: 'Verify synthetic UI' }).last();
        await relation.getByRole('button', { includeHidden: true, name: /查看 .* 的过程与耗时/ }).click();
        await expect(page.locator('[data-execution-agent-context]')).toContainText('所选过程');
        await expect(page.locator('[data-execution-group]')).toHaveCount(1);
        await expect(page.locator('[data-execution-items]')).toContainText('Synthetic child B answer');
        await expect(page.locator('[data-execution-judgment]')).toContainText('此范围未观察到工具调用');
        await expect(page.locator('[data-execution-judgment]')).toBeFocused();
        await expect(page.getByRole('link', { name: '直接查看所选过程' })).toBeInViewport();
        await page.getByRole('link', { name: '直接查看所选过程' }).click();
        await expect(page.locator('[data-execution-agent-context]')).toBeInViewport();
        await captureDiagnosticScreenshot(page, { path: test.info().outputPath(`selected-agent-${width}.png`) });
        await page.getByRole('button', { includeHidden: true, name: '返回协作位置', exact: true }).click();
        await expect(relation.getByRole('button', { includeHidden: true, name: /查看 .* 的过程与耗时/ })).toBeFocused();
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
        await expect(page.locator('[data-execution-tool]:focus')).toHaveCount(1);
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await page.getByRole('button', { includeHidden: true, name: '返回全部过程', exact: true }).click();
        await expect(page.locator('[data-execution-agent-context]')).toContainText('全部上下文');
        await openEvidence(relation.getByRole('button', { includeHidden: true, name: '查看此 Agent 发起的委派', exact: true }));
        await relation.getByRole('button', { includeHidden: true, name: '查看此 Agent 发起的委派', exact: true }).click();
        await assertSelectedContextIdentity(page, 'subagent:worker-same-prefix-002');
        await expect(host).toContainText('未记录该上下文发起的明确委派');
        await captureDiagnosticScreenshot(page, { path: test.info().outputPath(`branch-${width}.png`) });
      } finally { expect((await request.delete(api)).status()).toBe(204); }
    });
  }
}

for (const width of [1440, 390]) {
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
      const host = page.locator('[data-collaboration]');
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
    const host = page.locator('[data-collaboration]');
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
    const host = page.locator('[data-collaboration]');
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
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: 1100 });
      await page.goto(base + '/sessions/codex/' + rootId);
      const host = page.locator('[data-collaboration]');
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
      await expect(page.locator('[data-execution-tool]:focus')).toHaveAttribute('data-execution-tool', b.toolId);
      expect(calls.at(-1).searchParams.get('target')).toBe(b.toolId);
      await relation.getByRole('button', { includeHidden: true, name: /查看 .* 的过程与耗时/ }).click();
      await expect(page.locator('[data-execution-items]')).toContainText('Synthetic B final answer');
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
        await assertRecordedResult(page, request, importApi, page.locator('[data-collaboration]').getByRole('button', { includeHidden: true, name: '委派返回 Result', exact: true }).first(), JSON.stringify({ agent_id: 'worker-same-prefix-001' }));
        await openRelatedExchanges(page.locator('[data-collaboration]'));
        await assertRecordedResult(page, request, importApi, page.locator('[data-collaboration]').getByRole('button', { includeHidden: true, name: '报告 Result', exact: true }).last(),
          JSON.stringify({ status: { 'worker-same-prefix-001': { completed: 'Synthetic tail report' } } }));
      } finally { expect((await request.delete(importApi)).status()).toBe(204); }
    }
    await page.goto(base + '/sessions/codex/' + rootId);
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
    await expect(page.locator('[data-collaboration]')).toContainText('当前记录未提供可确认的协作关联');
    await expect(page.locator('[data-collaboration]')).toContainText('Qoder / 裸名 send_input');
    await expect(page.locator('[data-collaboration-relation]')).toHaveCount(0);
    await expect(page.locator('[data-execution-collaboration-return]')).not.toBeVisible();
  } finally { expect((await request.delete('/api/imports/' + unsupported.import_id)).status()).toBe(204); }
});

test('Agent execution selection scopes diagnostics and ignores stale responses after return to all', async ({ page, request, baseURL }) => {
  const imported = await upload(request, baseURL, 'claude_code', claudeSource(true));
  const api = '/api/imports/' + imported.import_id;
  try {
    await page.goto(imported.detail_url);
    const host = page.locator('[data-collaboration]');
    const selected = host.locator('[data-collaboration-relation]').filter({ hasText: 'Review synthetic parser' }).getByRole('button', { includeHidden: true, name: /查看 .* 的过程与耗时/ });
    await expect(selected).toBeVisible();
    for (const status of [200, 409, 500]) {
      let release, arrived, handled;
      const gate = new Promise(resolve => { release = resolve; });
      const arrival = new Promise(resolve => { arrived = resolve; });
      const completed = new Promise(resolve => { handled = resolve; });
      await page.route('**/execution?status=all&agent_context=subagent%3Aworker-same-prefix-001', async route => {
        const response = await route.fetch();
        arrived();
        await gate;
        await route.fulfill({ response, status });
        handled();
      });
      await selected.click();
      await arrival;
      await expect(page.locator('[data-execution-judgment]')).toContainText('正在读取所选上下文');
      await expect(page.locator('[data-execution-tool]')).toHaveCount(0);
      await page.getByRole('button', { includeHidden: true, name: '返回全部过程', exact: true }).click();
      await expect(page.locator('[data-execution-tool]')).toHaveCount(8);
      release();
      await completed;
      await page.unroute('**/execution?status=all&agent_context=subagent%3Aworker-same-prefix-001');
      await expect(page.locator('[data-execution-agent-context]')).toContainText('全部上下文');
      await expect(page.locator('[data-execution-status]')).toBeEmpty();
      await expect(page.locator('[data-execution-tool]')).toHaveCount(8);
    }
  } finally { expect((await request.delete(api)).status()).toBe(204); }
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
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: 1100 });
      await page.goto(imported.detail_url);
      const host = page.locator('[data-collaboration]');
      await expect(host.locator('[data-collaboration-relation]')).toHaveCount(5);
      const b = host.locator('[data-collaboration-relation]').filter({ hasText: 'Verify synthetic UI' });
      await openEvidence(b.getByRole('button', { includeHidden: true, name: '查看此 Agent 发起的委派', exact: true }));
      await b.getByRole('button', { includeHidden: true, name: '查看此 Agent 发起的委派', exact: true }).click();
      await expect(host).toContainText('Synthetic deeper review');
      await expect(host.locator('[data-collaboration-relation]')).toHaveCount(1);
      await host.evaluate(n => n.scrollIntoView({ block: 'start' }));
      await captureDiagnosticScreenshot(page, { path: test.info().outputPath(`deep-branch-${width}.png`) });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await host.getByRole('button', { includeHidden: true, name: /查看 .* 的过程与耗时/ }).click();
      await expect(page.locator('[data-execution-items]')).toContainText('Synthetic C answer');
    }
  } finally { expect((await request.delete(api)).status()).toBe(204); }
});

test('actual available empty Result differs from missing Result without guessing output shape', async ({ page, request, baseURL }) => {
  const records = [{ type: 'session_meta', timestamp: '2026-11-13T10:00:00Z', payload: { id: 'synthetic-empty-result', timestamp: '2026-11-13T10:00:00Z', cwd: '/synthetic/empty', source: 'cli' } }];
  for (const [i, value] of ['', null, undefined, 'missing'].entries()) {
    records.push({ type: 'response_item', payload: { type: 'function_call', call_id: 'empty-' + i, name: 'exec_command', arguments: JSON.stringify({ cmd: 'printf synthetic-empty-' + i }) } });
    records.push({ type: 'token_usage_record', timestamp: '2026-11-13T10:00:01Z', payload: { response_id: 'empty-response-' + i, usage: { input_tokens: 10, output_tokens: 2 } } });
    if (value !== 'missing') records.push({ type: 'response_item', payload: { type: 'function_call_output', call_id: 'empty-' + i, ...(value === undefined ? {} : { output: value }) } });
  }
  const fs = require('fs'), path = require('path'), { spawn } = require('child_process');
  const { runTmpRoot } = require('./runtime-paths');
  const { copyDistribution, resolveJavaEnvironment } = require('./start-java-fixture-server');
  fs.mkdirSync(runTmpRoot, { recursive: true });
  const directory = fs.mkdtempSync(path.join(runTmpRoot, 'empty-result-normal-')), home = path.join(directory, 'home');
  fs.mkdirSync(path.join(home, '.codex', 'sessions', 'synthetic-empty-result'), { recursive: true });
  fs.writeFileSync(path.join(home, '.codex', 'session_index.jsonl'), JSON.stringify({ id: 'synthetic-empty-result', thread_name: 'Synthetic empty', updated_at: '2026-11-13T10:00:01Z' }) + '\n');
  fs.writeFileSync(path.join(home, '.codex', 'sessions', 'synthetic-empty-result', 'rollout-synthetic-empty-result.jsonl'), records.map(JSON.stringify).join('\n') + '\n');
  const child = spawn(copyDistribution(directory), ['serve', '--host', '127.0.0.1', '--port', '0'], {
    env: { ...process.env, ...resolveJavaEnvironment(), HOME: home, INDEX_DIR: path.join(directory, 'index'),
      JAVA_OPTS: `"-Duser.home=${home}"`, APP_CLI_OPTS: '', JAVA_TOOL_OPTIONS: '', JDK_JAVA_OPTIONS: '', _JAVA_OPTIONS: '' }, stdio: ['ignore', 'pipe', 'pipe'] });
  let logs = '';
  const base = await new Promise((resolve, reject) => {
    child.once('error', reject); child.once('exit', code => reject(new Error('server exit ' + code + logs)));
    for (const stream of [child.stdout, child.stderr]) stream.on('data', data => {
      logs += data; const match = logs.match(/serve 已就绪: (http:\/\/127\.0\.0\.1:\d+)/); if (match) resolve(match[1]);
    });
  });
  const api = base + '/api/sessions/codex/synthetic-empty-result';
  try {
    await expect.poll(async () => (await request.get(api + '/execution')).status()).toBe(200);
    await page.goto(base + '/sessions/codex/synthetic-empty-result');
    const execution = await (await request.get(api + '/execution')).json();
    const tools = execution.items.filter(item => item.tool).map(item => item.tool);
    await test.info().attach('empty-execution.json', { body: JSON.stringify(execution), contentType: 'application/json' });
    expect(tools).toHaveLength(4);
    for (const [i, tool] of tools.entries()) {
      const payload = await (await request.get(api + '/payload/' + encodeURIComponent('tool:result:' + tool.toolCallId))).json();
      expect(payload.status).toBe(i < 3 ? 'available' : 'missing');
      const row = page.locator('[data-execution-tool]').filter({ hasText: 'printf synthetic-empty-' + i });
      await row.locator('.se-tool-evidence > summary').click();
      await row.getByRole('button', { name: '执行结果', exact: true }).click();
      const modal = page.locator('dialog.payload-modal');
      if (i < 3) {
        await expect(modal).toContainText('已记录工具返回，暂无可展示的非空正文');
        await expect(modal).not.toContainText('Result 内容未记录');
      } else {
        await expect(modal).toContainText('未记录');
        await expect(modal).not.toContainText('已记录工具返回');
      }
      await page.keyboard.press('Escape');
    }
  } finally {
    child.kill('SIGTERM'); await new Promise(resolve => child.once('exit', resolve));
    fs.writeFileSync(path.join(directory, 'service.log'), logs);
  }
});

test('协作导航 记录身份 说明层级 联合扫读 normal full-key labels preserve delayed collaboration identity across diagnostics and process', async ({ page, request }) => {
  const fs = require('fs'), path = require('path'), { spawn } = require('child_process');
  const { runTmpRoot } = require('./runtime-paths');
  const { copyDistribution, resolveJavaEnvironment } = require('./start-java-fixture-server');
  fs.mkdirSync(runTmpRoot, { recursive: true });
  const directory = fs.mkdtempSync(path.join(runTmpRoot, 'labels-normal-')), home = path.join(directory, 'home');
  const ids = ['synthetic-label-root', 'synthetic-label-worker-prefix-A', 'synthetic-label-worker-prefix-B', 'synthetic-label-worker-prefix-C'];
  const source = path.join(home, '.codex', 'sessions', 'synthetic'); fs.mkdirSync(source, { recursive: true });
  const usage = id => ({ type: 'token_usage_record', timestamp: '2026-11-14T06:00:01Z', payload: { response_id: id, usage: { input_tokens: 10, output_tokens: 2 } } });
  const meta = (id, parent) => ({ type: 'session_meta', timestamp: '2026-11-14T06:00:00Z', payload: { id, timestamp: '2026-11-14T06:00:00Z', cwd: '/synthetic/labels', source: parent ? { subagent: { thread_spawn: { parent_thread_id: parent } } } : 'cli' } });
  const call = (id, name, args) => ({ type: 'response_item', payload: { type: 'function_call', call_id: id, name, arguments: JSON.stringify(args) } });
  const result = (id, output) => ({ type: 'response_item', payload: { type: 'function_call_output', call_id: id, output } });
  const delegate = (id, target) => [call(id, 'spawn_agent', { message: 'Synthetic label task ' + target }), result(id, { agent_id: target })];
  const action = (id, secs, nanos = 0) => [call(id, 'exec_command', { cmd: 'node synthetic-' + id + '.js' }), usage(id), result(id, 'Synthetic recorded output'), { type: 'event_msg', payload: { type: 'exec_command_end', call_id: id, duration: { secs, nanos }, exit_code: 0, status: 'completed' } }];
  const root = [meta(ids[0]), ...action('root-build', 40), ...delegate('spawn-A', ids[1]), ...delegate('spawn-B', ids[2]), usage('root-delegates'),
    call('root-wait', 'wait_agent', { targets: [ids[1]] }), usage('root-wait-response'), result('root-wait', { status: { [ids[1]]: { completed: 'Synthetic wait report only, not task success' } } }),
    { type: 'event_msg', payload: { type: 'exec_command_end', call_id: 'root-wait', duration: { secs: 2, nanos: 0 }, exit_code: 0, status: 'completed' } }];
  const a = [meta(ids[1], ids[0])]; for (let i = 0; i < 23; i++) a.push(...action('A-' + i, 0, 500000000));
  a.push(...delegate('spawn-C', ids[3]), usage('A-child'));
  for (const records of [root, a, [meta(ids[2], ids[0]), ...action('B', 35)], [meta(ids[3], ids[1]), ...action('C', 3)]]) fs.writeFileSync(path.join(source, 'rollout-' + records[0].payload.id + '.jsonl'), records.map(JSON.stringify).join('\n') + '\n');
  fs.writeFileSync(path.join(home, '.codex', 'session_index.jsonl'), ids.map(id => JSON.stringify({ id, thread_name: 'Synthetic label ' + id, updated_at: '2026-11-14T06:00:02Z' })).join('\n') + '\n');
  const child = spawn(copyDistribution(directory), ['serve', '--host', '127.0.0.1', '--port', '0'], { env: { ...process.env, ...resolveJavaEnvironment(), HOME: home, INDEX_DIR: path.join(directory, 'index'), JAVA_OPTS: `"-Duser.home=${home}"`, APP_CLI_OPTS: '', JAVA_TOOL_OPTIONS: '', JDK_JAVA_OPTIONS: '', _JAVA_OPTIONS: '' }, stdio: ['ignore', 'pipe', 'pipe'] });
  let logs = '';
  const base = await new Promise((resolve, reject) => { child.once('error', reject); child.once('exit', code => reject(new Error('server exit ' + code + logs))); for (const stream of [child.stdout, child.stderr]) stream.on('data', data => { logs += data; const m = logs.match(/serve 已就绪: (http:\/\/127\.0\.0\.1:\d+)/); if (m) resolve(m[1]); }); });
  try {
    const api = base + '/api/sessions/codex/' + ids[0];
    await waitForPublishedScan(base);
    const response = await request.get(api + '/collaboration');
    expect(response.status()).toBe(200);
    const facts = await response.json();
    const label = id => facts.items.find(row => row.target === 'subagent:' + id).targetLabel;
    expect(label(ids[2])).not.toBe(label(ids[3]));
    await test.info().attach('labels-source-api.json', { body: JSON.stringify({ facts, directory, ids }), contentType: 'application/json' });
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: 1000 });
      let release, arrived; const gate = new Promise(resolve => { release = resolve; }); const arrival = new Promise(resolve => { arrived = resolve; });
      await page.route('**/collaboration?*', async route => { const response = await route.fetch(); arrived(); await gate; await route.fulfill({ response, status: width === 390 ? 500 : 200 }); });
      await page.goto(base + '/sessions/codex/' + ids[0]); await arrival;
      await expect(page.locator('[data-execution-workload-details]')).toHaveCount(1);
      await page.locator('[data-execution-workload-details] > summary').click(); // Original per-context evidence is now one explicit disclosure away.
      const workload = seconds => page.locator('[data-execution-workloads]').filter({ has: page.locator('h3').filter({ hasText: '已测累计 ' + seconds }) });
      await expect(workload('35s')).toBeVisible();
      await expect(workload('35s').locator('[data-execution-delegation-sources]')).toContainText('读取中');
      // 同快照execution已有权威hint，迟到/失败协作不能让已确认标签退回raw。
      await expect(workload('35s').locator('.se-basis').first()).not.toContainText('子 Agent 2');
      const retainedWork = await workload('35s').elementHandle();
      await workload('11.5s').locator('[data-execution-slowest]').evaluate(node => { node.open = true; });
      const retained = page.locator('[data-execution-tool]').first();
      await retained.locator('.se-tool-evidence > summary').click(); await retained.focus();
      const retainedNode = await retained.elementHandle();
      release();
      if (width === 390) {
        await expect(page.locator('[data-collaboration-status]')).toContainText('HTTP 500');
        await expect(workload('35s').locator('[data-execution-delegation-sources]')).toContainText('读取失败');
        await expect(workload('35s').locator('.se-basis').first()).toContainText(label(ids[2]) + ' · 独立上下文');
        await page.unroute('**/collaboration?*');
        await page.locator('[data-collaboration-status]').getByRole('button', { name: 'Retry' }).click();
      }
      await expect(page.locator('[data-collaboration-relation]')).toHaveCount(3);
      await expect(page.locator('[data-execution-delegation-sources]')).toHaveCount(3);
      expect((await page.locator('[data-execution-judgment]').innerText()).match(/慢不等于异常/g)).toHaveLength(1);
      await expect(page.locator('[data-execution-signal-content] > p').first()).toContainText('非完整瓶颈');
      await expect(page.locator('[data-collaboration-response-group]')).toHaveCount(2);
      await expect(page.locator('[data-collaboration-response-group]').first()).toContainText('主 Agent · 发起记录 #2 · 此处显示 2 项委派');
      await expect(page.locator('[data-collaboration-response-group]').last()).toContainText('Agent 1 · 发起记录 #27 · 此处显示 1 项委派');
      await captureDiagnosticScreenshot(page.locator('[data-collaboration]'), { path: test.info().outputPath('grouping-normal-' + width + '.png') });
      expect(await retainedNode.evaluate(node => node.isConnected)).toBe(true);
      expect(await retainedWork.evaluate(node => node.isConnected)).toBe(true);
      await expect(workload('11.5s').locator('[data-execution-slowest]')).toHaveAttribute('open');
      // Retry 本身会移动焦点；纯迟到身份更新不得移动已有动作焦点。
      if (width === 1440) await expect(retained).toBeFocused();
      await expect(retained.locator('.se-tool-evidence')).toHaveAttribute('open');
      for (const [id, seconds] of [[ids[1], '11.5s'], [ids[2], '35s'], [ids[3], '3s']]) await expect(workload(seconds).locator('.se-basis').first()).toContainText(label(id) + ' · 独立上下文');
      await page.locator('[data-execution-judgment]').scrollIntoViewIfNeeded(); await captureDiagnosticScreenshot(page, { path: test.info().outputPath('labels-' + width + '.png') });
      const row = page.locator('[data-collaboration-relation]').filter({ hasText: 'Synthetic label task ' + ids[2] });
      const bridge = workload('35s').locator('[data-execution-delegation-sources]');
      await expect(bridge).toContainText('已加载委派来源'); await expect(bridge).toContainText('主 Agent · 发起记录 #2');
      await bridge.getByRole('button', { name: /定位任务关系/ }).click(); await expect(row).toBeFocused();
      await expect(workload('35s').locator('.se-workload-line')).toBeVisible();
      await workload('11.5s').locator('[data-execution-slowest]').evaluate(node => { node.open = false; });
      const overview = page.getByRole('button', { name: '查看 Agent 协作', exact: true });
      const navigationRequests = []; const observeNavigation = r => navigationRequests.push(r.url());
      page.on('request', observeNavigation);
      await overview.focus(); await page.keyboard.press('Enter');
      await expect(page.locator('[data-collaboration-context]')).toBeFocused();
      page.off('request', observeNavigation); expect(navigationRequests).toEqual([]);
      await captureDiagnosticScreenshot(page.locator('[data-execution-judgment]'), { path: test.info().outputPath('scan-normal-' + width + '.png') });
      const commandStyles = await page.locator('[data-execution-workloads] .se-representative > .se-diagnosis-command').evaluateAll(nodes => nodes.map(node => {
        const style = getComputedStyle(node), article = getComputedStyle(node.closest('article'));
        return { text: node.textContent, color: style.color, articleColor: article.color, fontSize: style.fontSize,
          fontWeight: style.fontWeight, metadataColor: getComputedStyle(node.parentElement).color,
          background: getComputedStyle(document.body).backgroundColor };
      }));
      await test.info().attach('representative-command-styles-' + width + '.json', { body: JSON.stringify(commandStyles), contentType: 'application/json' });
      expect(commandStyles).toHaveLength(5);
      for (const command of commandStyles) {
        expect(command.color).toBe(command.articleColor);
        expect(command.color).not.toBe(command.metadataColor);
        expect(command.fontSize).toBe('14px'); expect(command.fontWeight).toBe('400');
      }

      await test.info().attach('scan-normal-geometry-' + width + '.json', { body: JSON.stringify(await page.evaluate(() => Object.fromEntries(['[data-execution-judgment]', '[data-collaboration]', '[data-execution-items]'].map(selector => { const node = document.querySelector(selector), rect = node.getBoundingClientRect(); return [selector, { y: rect.top + scrollY, height: rect.height }]; })))), contentType: 'application/json' });
      if (width === 1440) {
        // UI模拟guard：使用真实API行作为底稿，明确不冒充额外原始来源。
        const state = await page.evaluate(facts => {
          const diagnosis = document.querySelector('[data-execution-workloads]:has(h3)');
          const slow = document.querySelector('[data-execution-slowest]'); slow.open = true; slow.querySelector('summary').focus();
          const b = facts.items.find(row => row.target.endsWith('-B'));
          const rows = Array.from({ length: 6 }, (_, i) => ({ ...b, toolId: 'ui-source-tool-' + i, callId: 'ui-response-' + i, task: 'UI source guard ' + i }));
          applyCollaborationPage({ ...facts, items: rows.slice(0, 5), offset: 0, total: 6, nextCursor: null }, false);
          applyCollaborationPage({ ...facts, items: rows.slice(5), offset: 5, total: 6, nextCursor: null }, true);
          const host = [...document.querySelectorAll('[data-execution-delegation-sources]')].find(n => n.dataset.executionDelegationSources === b.target);
          const text = host.textContent, buttons = host.querySelectorAll('button').length;
          const first = host.querySelector('button'); first.focus(); syncExecutionDelegationSources();
          const stableButton = document.activeElement === first;
          collaborationView.sourceStatus = 'loading'; syncExecutionDelegationSources(); const loadingLinks = host.querySelectorAll('button').length;
          collaborationView.sourceStatus = 'failed'; syncExecutionDelegationSources(); const failure = host.textContent;
          applyCollaborationPage({ ...facts, view: 'exchanges' }, false); const exchangeSource = host.textContent, exchangeButtons = host.querySelectorAll('button').length;
          applyCollaborationPage({ ...facts, view: 'participants', items: [] }, false); const unavailable = host.textContent;
          applyCollaborationPage(facts, false);
          return { text, buttons, stableButton, loadingLinks, failure, exchangeSource, exchangeButtons, unavailable, retained: diagnosis.isConnected, expanded: slow.open };
        }, facts);
        expect(state.text).toContain('6 条'); expect(state.text).toContain('另 3 条'); expect(state.buttons).toBe(3);
        expect(state.stableButton).toBe(true); expect(state.loadingLinks).toBe(0); expect(state.failure).toContain('读取失败');
        expect(state.exchangeSource).toContain('已加载委派来源 1 条'); expect(state.exchangeButtons).toBe(1);
        expect(state.unavailable).toContain('当前视图不提供'); expect(state.retained).toBe(true); expect(state.expanded).toBe(true);
        await test.info().attach('scan-ui-guard.json', { body: JSON.stringify(state), contentType: 'application/json' });
        let arrived, release, finished;
        const arrival = new Promise(resolve => { arrived = resolve; });
        const gate = new Promise(resolve => { release = resolve; });
        const completed = new Promise(resolve => { finished = resolve; });
        await page.route('**/collaboration?view=exchanges&selection=', async route => {
          const response = await route.fetch(); arrived(); await gate; await route.fulfill({ response }); finished();
        });
        await page.locator('[data-collaboration-all-exchanges]').click(); await arrival;
        await expect(bridge).toContainText('读取中'); await expect(bridge.locator('button')).toHaveCount(0);
        await page.locator('[data-collaboration-root]').click(); await expect(bridge).toContainText('主 Agent · 发起记录 #2');
        release(); await completed;
        await expect(bridge).toContainText('主 Agent · 发起记录 #2');
        await expect(page.locator('[data-collaboration-relation]')).toHaveCount(3);
        await page.unroute('**/collaboration?view=exchanges&selection=');

      }

      await row.getByRole('button', { name: '查看 ' + label(ids[2]) + ' 的过程与耗时', exact: true }).click();
      await expect(page.locator('[data-execution-judgment]')).toContainText('35s'); await expect(page.locator('.se-group-context')).toContainText(label(ids[2]));
      await page.getByRole('button', { name: '返回协作位置', exact: true }).click(); await expect(row.getByRole('button', { name: /过程与耗时/ })).toBeFocused();
      await row.locator('[data-collaboration-evidence] > summary').focus(); await page.keyboard.press('Enter');
      await row.getByRole('button', { name: '任务 Input', exact: true }).click();
      await expect(page.locator('dialog.payload-modal')).toContainText('Synthetic label task ' + ids[2]); await page.keyboard.press('Escape');
      await assertRecordedResult(page, request, api, row.getByRole('button', { name: '委派返回 Result', exact: true }), JSON.stringify({ agent_id: ids[2] }));
      // 真实参与者入口与视图替换：不把参与者称支路，也不保留脱离 DOM 的来源。
      await page.locator('[data-collaboration-participants]').click();
      await expect(page.getByRole('button', { name: '查看 Agent 协作', exact: true })).toBeVisible();
      const participant = page.locator('.sc-participant').filter({ hasText: label(ids[2]) });
      const participantEntry = participant.getByRole('button', { name: '查看过程与耗时', exact: true });
      await participantEntry.click();
      await expect(page.locator('[data-execution-judgment]')).toBeFocused();
      await page.getByRole('button', { name: '返回协作位置', exact: true }).focus(); await page.keyboard.press('Enter');
      await expect(participantEntry).toBeFocused();
      // 局部同步/追加保持同一真实入口；明确断开则降级（UI guard，不冒充原始来源）。
      const navigation = await page.evaluate(() => {
        const original = collaborationView.returnFocus;
        applyCollaborationPage({ ...collaborationView.page, items: [], nextCursor: null }, true);
        syncExecutionDelegationSources(); syncExecutionContextLabels(); syncExecutionCollaborationNavigation();
        const retained = collaborationView.returnFocus === original;
        original.remove(); syncExecutionCollaborationNavigation();
        return { retained, cleared: collaborationView.returnFocus === null };
      });
      expect(navigation).toEqual({ retained: true, cleared: true });
      await expect(page.getByRole('button', { name: '查看 Agent 协作', exact: true })).toBeVisible();
      await page.locator('[data-collaboration-root]').click();
      await expect(page.getByRole('button', { name: '查看 Agent 协作', exact: true })).toBeVisible();
      await captureDiagnosticScreenshot(page.locator('[data-collaboration]'), { path: test.info().outputPath('navigation-normal-' + width + '.png') });
      await page.unroute('**/collaboration?*');
      if (width === 390) {
        // 使用真实资源，替换已发布的测试快照stamp；旧200不得把旧scope编号贴回。
        await page.evaluate(() => { document.body.setAttribute('data-index-generation', 'synthetic-label-new-generation'); window.dispatchEvent(new Event('index-snapshot-restored')); });
        await expect(page.locator('[data-execution-judgment] h2')).toContainText(ids[2]);
        await expect(page.locator('[data-execution-agent-context]')).toContainText(ids[2]);
        await expect(page.locator('.se-group-context')).toContainText(ids[2]);
        await expect(page.locator('[data-collaboration-status]')).toContainText('Refresh');
        await expect(page.locator('[data-execution-collaboration-return]')).toBeHidden();
        await expect(page.locator('[data-execution-delegation-sources] button')).toHaveCount(0);
        await expect(page.locator('[data-execution-judgment] h2')).not.toContainText(label(ids[2]));
      }
    }
  } finally { child.kill('SIGTERM'); await new Promise(resolve => child.once('exit', resolve)); fs.writeFileSync(path.join(directory, 'service.log'), logs); }
});

for (const width of [1440, 390]) {
  test(`raw import same-response grouping preserves 5+1 relation windows at ${width}px`, async ({ page, request, baseURL }) => {
    const records = [{ type: 'user', uuid: 'grouping-user', sessionId: 'synthetic-grouping', message: { role: 'user', content: 'Synthetic response grouping only' } },
      { type: 'assistant', uuid: 'grouping-root', sessionId: 'synthetic-grouping', message: { id: 'grouping-root', role: 'assistant', content: Array.from({ length: 6 }, (_, i) => ({ type: 'tool_use', id: 'group-tool-' + i, name: 'Agent', input: { prompt: '合成分组任务 ' + i } })) } }];
    const imported = await upload(request, baseURL, 'claude_code', records), api = '/api/imports/' + imported.import_id;
    try {
      await page.setViewportSize({ width, height: 1000 }); const paths = [];
      page.on('request', r => { if (r.url().includes('/api/')) paths.push(r.url()); });
      await page.goto(imported.detail_url); const host = page.locator('[data-collaboration]');
      await expect(host.locator('[data-collaboration-relation]')).toHaveCount(5);
      const facts = await (await request.get(api + '/collaboration?limit=100')).json();
      expect(facts.items).toHaveLength(6); expect(new Set(facts.items.map(row => row.actor + '/' + row.callId)).size).toBe(1);
      await test.info().attach('grouping-import-source-api.json', { body: JSON.stringify({ records, facts }), contentType: 'application/json' });
      await expect(host.locator('[data-collaboration-response-group]')).toHaveCount(1);
      await expect(host.locator('[data-collaboration-response-group] > h3')).toContainText('此处显示 5 项委派');
      await expect(host).toContainText('仅当前已载'); await expect(host).toContainText('不表示并行');
      await captureDiagnosticScreenshot(host, { path: test.info().outputPath('grouping-import-default-' + width + '.png') });
      const first = host.locator('[data-collaboration-relation]').first(), node = await first.elementHandle();
      await expect(first).toContainText('目标身份未确认'); await expect(first.locator('.sc-origin')).not.toContainText('#');
      await first.locator('[data-collaboration-evidence] > summary').focus(); await page.keyboard.press('Enter');
      await first.getByRole('button', { name: '任务 Input', exact: true }).click(); await expect(page.locator('dialog.payload-modal')).toContainText('合成分组任务 0'); await page.keyboard.press('Escape');
      await host.locator('[data-content-pagination="collaboration"] button').click();
      await expect(host.locator('[data-collaboration-relation]')).toHaveCount(6); await expect(host.locator('[data-collaboration-response-group]')).toHaveCount(2);
      await expect(host.locator('[data-collaboration-response-group] > h3')).toHaveText([/此处显示 5 项委派/, /此处显示 1 项委派/]);
      expect(await node.evaluate(n => n.isConnected)).toBe(true); await expect(first.locator('[data-collaboration-evidence]')).toHaveAttribute('open');
      await expect(host.locator('.sc-task')).toHaveText(Array.from({ length: 6 }, (_, i) => '任务：合成分组任务 ' + i));
      await expect(host.locator('[data-collaboration-pagination]')).toContainText('6 / 6');
      expect(paths.filter(p => /\/collaboration\?/.test(p))).toHaveLength(2); // API request above uses request context, not browser.
      await captureDiagnosticScreenshot(host, { path: test.info().outputPath('grouping-import-' + width + '.png') });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await host.getByRole('button', { name: '全部协作往来', exact: true }).click(); await expect(host.locator('[data-collaboration-relation]')).toHaveCount(6); await expect(host.locator('[data-collaboration-response-group]')).toHaveCount(0);
      // 明确模拟UI身份保护（不冒充原始parser证据）：同显示#不等于同完整call。
      const guard = await page.evaluate(source => {
        const base = { ...source, actor: 'main', actorIdentityReason: 'main_context', callId: 'call-A', callIndex: 7 };
        const variants = [{}, { callId: 'call-B' }, {}, { actor: 'subagent:other-full-key', actorIdentityReason: 'explicit_instance' },
          { actor: 'unknown:context', actorIdentityReason: 'anonymous_sidechain' },
          { actor: 'subagent:unknown-sidechain:explicit-origin', actorIdentityReason: 'anonymous_sidechain' }, { callId: '' }];
        const template = document.createElement('template');
        template.innerHTML = collaborationDelegations(variants.map((extra, i) => ({ ...base, ...extra, task: 'UI identity guard ' + i })));
        return { groups: template.content.querySelectorAll('[data-collaboration-response-group]').length,
          members: [...template.content.querySelectorAll('[data-collaboration-response-group]')].map(n => n.querySelectorAll('article').length),
          tasks: [...template.content.querySelectorAll('.sc-task')].map(n => n.textContent), articles: template.content.querySelectorAll('article').length };
      }, facts.items[0]);
      expect(guard).toEqual({ groups: 4, members: [1, 1, 1, 1], tasks: Array.from({ length: 7 }, (_, i) => '任务：UI identity guard ' + i), articles: 7 });
      await test.info().attach('grouping-ui-identity-guard.json', { body: JSON.stringify(guard), contentType: 'application/json' });
    } finally { expect((await request.delete(api)).status()).toBe(204); }
  });
}

for (const width of [1440, 390]) {
  test(`协作导航 说明层级 联合扫读 raw single-file import keeps measured scan and honest unavailable child at ${width}px`, async ({ page, request, baseURL }) => {
    const records = [{ type: 'session_meta', payload: { id: 'synthetic-scan-import' } },
      { type: 'response_item', payload: { type: 'function_call', call_id: 'scan-build', name: 'exec_command', arguments: JSON.stringify({ cmd: 'node synthetic-scan.js --demo-only' }) } },
      { type: 'token_usage_record', payload: { response_id: 'scan-first', usage: { input_tokens: 10, output_tokens: 2 } } },
      { type: 'response_item', payload: { type: 'function_call_output', call_id: 'scan-build', output: 'Synthetic recorded result' } },
      { type: 'event_msg', payload: { type: 'exec_command_end', call_id: 'scan-build', duration: { secs: 35, nanos: 0 }, status: 'completed', exit_code: 0 } },
      { type: 'response_item', payload: { type: 'function_call', call_id: 'scan-spawn', name: 'spawn_agent', arguments: JSON.stringify({ message: '合成单文件任务：不读取相邻child' }) } },
      { type: 'response_item', payload: { type: 'function_call_output', call_id: 'scan-spawn', output: { agent_id: 'synthetic-scan-missing-child' } } },
      { type: 'token_usage_record', payload: { response_id: 'scan-second', usage: { input_tokens: 10, output_tokens: 2 } } }];
    const imported = await upload(request, baseURL, 'codex', records), api = '/api/imports/' + imported.import_id;
    try {
      const urls = []; page.on('request', r => { if (r.url().includes('/api/')) urls.push(r.url()); });
      await page.setViewportSize({ width, height: 1000 }); await page.goto(imported.detail_url);
      const diagnosis = page.locator('[data-execution-judgment]');
      await expect(diagnosis.locator('h3')).toContainText('exec_command · 已测累计 35s');
      await expect(diagnosis.locator('.se-workload-line')).toContainText('单次已测最长 35s · 已测 1/1 次');
      await expect(diagnosis.locator('[data-execution-delegation-sources]')).toHaveCount(0);
      await expect(diagnosis.locator('.se-source-note')).toHaveCount(0);
      await expect(diagnosis.locator('[data-execution-workloads] > .se-basis')).toContainText('仅已测，非完整瓶颈，慢不等于异常。');
      await expect(page.locator('[data-collaboration-relation]')).toContainText('合成单文件任务');
      await expect(page.locator('[data-collaboration-relation]')).toContainText('单文件导入未包含 child');
      await expect(page.locator('[data-collaboration-agent]')).toHaveCount(0);
      const overview = page.getByRole('button', { name: '查看 Agent 协作', exact: true });
      const navigationRequests = []; const observeNavigation = r => navigationRequests.push(r.url());
      page.on('request', observeNavigation);
      await overview.focus(); await page.keyboard.press('Enter');
      await expect(page.locator('[data-collaboration-context]')).toBeFocused();
      page.off('request', observeNavigation); expect(navigationRequests).toEqual([]);
      await captureDiagnosticScreenshot(page.locator('[data-collaboration]'), { path: test.info().outputPath('navigation-import-' + width + '.png') });
      expect(urls.every(u => u.includes(api + '/'))).toBe(true); expect(urls.some(u => u.includes('/payload/'))).toBe(false);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await captureDiagnosticScreenshot(diagnosis, { path: test.info().outputPath('scan-import-' + width + '.png') });
      await test.info().attach('scan-import-source.json', { body: JSON.stringify({ records, execution: await (await request.get(api + '/execution')).json(), collaboration: await (await request.get(api + '/collaboration')).json() }), contentType: 'application/json' });
    } finally { expect((await request.delete(api)).status()).toBe(204); }
  });
}

// 两类真实normal源；原始字节自包含，不从tmp导入运行fixture。
const recordIdentityLocalRecords = [
  {
    "type": "session_meta",
    "timestamp": "2026-11-14T06:00:00Z",
    "payload": {
      "id": "synthetic-concept-local",
      "timestamp": "2026-11-14T06:00:00Z",
      "cwd": "/synthetic/concept-review",
      "source": "cli"
    }
  },
  {
    "type": "response_item",
    "payload": {
      "type": "message",
      "role": "user",
      "content": [
        {
          "type": "input_text",
          "text": "合成审阅：打印标记后委派复核；不执行任何真实命令。"
        }
      ]
    }
  },
  {
    "type": "response_item",
    "payload": {
      "type": "message",
      "role": "assistant",
      "content": [
        {
          "type": "output_text",
          "text": "合成：准备打印标记。"
        }
      ]
    }
  },
  {
    "type": "response_item",
    "payload": {
      "type": "function_call",
      "call_id": "review-cmd",
      "name": "exec_command",
      "arguments": "{\"cmd\":\"echo SYNTHETIC_REVIEW_NOT_EXECUTED\"}"
    }
  },
  {
    "type": "response_item",
    "payload": {
      "type": "function_call",
      "call_id": "review-cmd-2",
      "name": "exec_command",
      "arguments": "{\"cmd\": \"echo SYNTHETIC_SECOND_NOT_EXECUTED\"}"
    }
  },
  {
    "type": "response_item",
    "payload": {
      "type": "function_call_output",
      "call_id": "review-cmd",
      "output": "SYNTHETIC_REVIEW_NOT_EXECUTED（仅合成载荷，未运行）"
    }
  },
  {
    "type": "response_item",
    "payload": {
      "type": "function_call_output",
      "call_id": "review-cmd-2",
      "output": "ONLY_TOOL_RESULT_SECOND"
    }
  },
  {
    "type": "response_item",
    "payload": {
      "type": "message",
      "role": "assistant",
      "content": [
        {
          "type": "output_text",
          "text": "合成：现在委派复核。"
        }
      ]
    }
  },
  {
    "type": "response_item",
    "payload": {
      "type": "function_call",
      "call_id": "review-spawn",
      "name": "spawn_agent",
      "arguments": "{\"message\":\"合成复核任务：仅审阅标记，不执行命令。\"}"
    }
  },
  {
    "type": "response_item",
    "payload": {
      "type": "function_call_output",
      "call_id": "review-spawn",
      "output": {
        "agent_id": "synthetic-review-child",
        "nickname": "合成审阅child"
      }
    }
  },
  {
    "type": "response_item",
    "payload": {
      "type": "message",
      "role": "assistant",
      "content": [
        {
          "type": "output_text",
          "text": "仅确认工具返回了目标ID，不代表child回答或任务完成。"
        }
      ]
    }
  }
];

for (const boundary of ['explicit', 'local']) {
  test(`记录身份 raw normal ${boundary} keeps visible type, shared model entries and independent tool results`, async ({ page, request }) => {
    const fs = require('fs'), path = require('path'), { spawn } = require('child_process');
    const { runTmpRoot } = require('./runtime-paths'), { copyDistribution, resolveJavaEnvironment } = require('./start-java-fixture-server');
    fs.mkdirSync(runTmpRoot, { recursive: true }); const directory = fs.mkdtempSync(path.join(runTmpRoot, 'record-identity-')), home = path.join(directory, 'home');
    const id = 'synthetic-record-identity-' + boundary, records = structuredClone(recordIdentityLocalRecords); records[0].payload.id = id;
    if (boundary === 'explicit') {
      for (const [tool, response] of [['review-cmd-2', 'identity-command-response'], ['review-spawn', 'identity-spawn-response']]) {
        const index = records.findIndex(row => row.payload?.type === 'function_call_output' && row.payload.call_id === tool);
        records.splice(index, 0, { type: 'token_usage_record', payload: { response_id: response, usage: { input_tokens: 10, output_tokens: 2 } } });
      }
    }
    const source = path.join(home, '.codex/sessions/synthetic-record-identity'); fs.mkdirSync(source, { recursive: true });
    fs.writeFileSync(path.join(source, 'rollout-' + id + '.jsonl'), records.map(JSON.stringify).join('\n') + '\n');
    fs.writeFileSync(path.join(home, '.codex/session_index.jsonl'), JSON.stringify({ id, thread_name: '合成记录身份 ' + boundary, updated_at: '2026-11-14T06:00:03Z' }) + '\n');
    const child = spawn(copyDistribution(directory), ['serve', '--host', '127.0.0.1', '--port', '0'], { cwd: directory,
      env: { ...process.env, ...resolveJavaEnvironment(), HOME: home, INDEX_DIR: path.join(directory, 'index'), JAVA_OPTS: `"-Duser.home=${home}"`, APP_CLI_OPTS: '', JAVA_TOOL_OPTIONS: '', JDK_JAVA_OPTIONS: '', _JAVA_OPTIONS: '' }, stdio: ['ignore', 'pipe', 'pipe'] });
    let logs = ''; const base = await new Promise((resolve, reject) => { child.once('error', reject); child.once('exit', code => reject(new Error('server exit ' + code + logs))); for (const stream of [child.stdout, child.stderr]) stream.on('data', data => { logs += data; const m = logs.match(/serve 已就绪: (http:\/\/127\.0\.0\.1:\d+)/); if (m) resolve(m[1]); }); });
    try {
      const api = base + '/api/sessions/codex/' + id;
      await expect.poll(async () => (await request.get(api + '/execution')).status()).toBe(200);
      const response = await request.get(api + '/execution'); expect(response.status()).toBe(200);
      const data = await response.json(), label = boundary === 'explicit' ? '模型响应记录' : '本地响应记录';
      const first = data.items.filter(item => item.group.index === 1); expect(first.map(item => item.tool.toolCallId)).toEqual(['review-cmd', 'review-cmd-2']);
      expect(first.every(item => item.group.label === label && item.group.toolCount === 2)).toBe(true);
      await test.info().attach('record-identity-source-api.json', { body: JSON.stringify({ boundary, records, data, directory }), contentType: 'application/json' });
      for (const width of [1440, 390]) {
        const paths = []; const collect = r => { if (r.url().includes('/api/')) paths.push(r.url()); }; page.on('request', collect);
        await page.setViewportSize({ width, height: 900 }); await page.goto(base + '/sessions/codex/' + id);
        await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
        const groups = page.locator('[data-execution-group]'), group = groups.first();
        await expect(group.locator('header > h3')).toHaveText(label + ' #1'); await expect(group.locator('header > h3')).toBeVisible();
        await expect(group.locator('[data-execution-response-actions]').getByRole('button', { name: '模型输入', exact: true })).toHaveCount(1);
        await expect(group.locator('[data-execution-response-actions]').getByRole('button', { name: '模型输出', exact: true })).toHaveCount(1);
        await expect(group.locator('[data-execution-tool]')).toHaveCount(2);
        await expect(page.locator('.se-process__head')).toContainText('#编号用于本地记录定位，不等同独立LLM请求次数');
        await expect(page.locator('.se-process__head')).toContainText('模型输入/输出仅限本地可见材料');
        await expect(page.locator('[data-collaboration-response-group] > h3')).toContainText('发起记录 #2');
        if (boundary === 'local') { await expect(groups.last().locator('header > h3')).toHaveText('本地响应记录 #3'); await expect(groups.last()).toContainText('仅确认工具返回了目标ID'); }
        expect(paths.some(url => url.includes('/payload/'))).toBe(false); expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await captureDiagnosticScreenshot(page.locator('[data-execution-items]'), { path: test.info().outputPath('record-identity-' + boundary + '-' + width + '.png') });
        await test.info().attach('record-identity-geometry-' + width + '.json', { body: JSON.stringify(await group.boundingBox()), contentType: 'application/json' });
        await group.getByRole('button', { name: '模型输出', exact: true }).click(); const modal = page.locator('dialog.payload-modal');
        await expect(modal).toBeVisible(); await expect(modal).toContainText('合成：准备打印标记。'); await expect(modal).toContainText('SYNTHETIC_SECOND_NOT_EXECUTED'); await expect(modal).not.toContainText('ONLY_TOOL_RESULT_SECOND');
        if (width === 1440) await captureDiagnosticScreenshot(modal, { path: test.info().outputPath('record-identity-' + boundary + '-model-output.png') });
        await page.keyboard.press('Escape');
        for (const [toolId, expected] of [['review-cmd', 'SYNTHETIC_REVIEW_NOT_EXECUTED（仅合成载荷，未运行）'], ['review-cmd-2', 'ONLY_TOOL_RESULT_SECOND']]) {
          const tool = group.locator('[data-execution-tool="' + toolId + '"]'); await tool.locator('.se-tool-evidence > summary').click();
          await tool.getByRole('button', { name: '命令或参数', exact: true }).click(); await expect(modal).toContainText(toolId === 'review-cmd' ? 'SYNTHETIC_REVIEW_NOT_EXECUTED' : 'SYNTHETIC_SECOND_NOT_EXECUTED'); await page.keyboard.press('Escape');
          await assertRecordedResult(page, request, api, tool.getByRole('button', { name: '执行结果', exact: true }), expected);
        }
        page.off('request', collect);
      }
    } finally { child.kill('SIGTERM'); await new Promise(resolve => child.once('exit', resolve)); fs.writeFileSync(path.join(directory, 'service.log'), logs); }
  });
}

 test('协作导航 no collaboration hides navigation without inventing a branch', async ({ page, request, baseURL }) => {
  const imported = await upload(request, baseURL, 'codex', [{ type: 'session_meta', payload: { id: 'synthetic-no-collaboration-navigation' } }, { type: 'response_item', payload: { type: 'message', role: 'assistant', content: [{ type: 'output_text', text: 'Synthetic plain answer' }] } }]);
  try {
    await page.goto(imported.detail_url);
    await expect(page.locator('[data-collaboration]')).toContainText('当前记录未提供可确认的协作关联');
    await expect(page.locator('[data-execution-collaboration-return]')).toBeHidden();
  } finally { expect((await request.delete('/api/imports/' + imported.import_id)).status()).toBe(204); }
});

test('协作导航 pending selection must not override an immediate real return', async ({ page, request, baseURL }) => {
  const imported = await upload(request, baseURL, 'claude_code', claudeSource(false));
  try {
    await page.goto(imported.detail_url);
    const relation = page.locator('[data-collaboration-relation]').filter({ hasText: 'Review synthetic parser' });
    const entry = relation.getByRole('button', { name: /查看 .* 的过程与耗时/ });
    await expect(entry).toBeVisible();
    let release, arrived;
    const gate = new Promise(resolve => { release = resolve; }), arrival = new Promise(resolve => { arrived = resolve; });
    // UI时序guard：延迟真实原生execution响应，不修改parser/DTO。
    await page.route('**/execution?*', async route => { const response = await route.fetch(); arrived(); await gate; await route.fulfill({ response }); });
    await entry.click(); await arrival;
    const back = page.getByRole('button', { name: '返回协作位置', exact: true });
    await expect(back).toBeVisible(); await back.focus(); await page.keyboard.press('Enter');
    await expect(entry).toBeFocused();
    release();
    await expect(page.locator('[data-execution-items]')).toContainText('Verify synthetic UI');
    await expect(entry).toBeFocused();
  } finally { expect((await request.delete('/api/imports/' + imported.import_id)).status()).toBe(204); }
});

test('失败归属 real normal child exit7 remains distinct from completed parent wait and local label guards', async ({ page, request }) => {
  const fs = require('fs'), path = require('path'), { spawn } = require('child_process');
  const { runTmpRoot } = require('./runtime-paths'), { copyDistribution, resolveJavaEnvironment } = require('./start-java-fixture-server');
  fs.mkdirSync(runTmpRoot, { recursive: true });
  const directory = fs.mkdtempSync(path.join(runTmpRoot, 'failure-context-')), home = path.join(directory, 'home');
  const source = path.join(home, '.codex/sessions/synthetic'); fs.mkdirSync(source, { recursive: true });
  const rootId = 'synthetic-failure-context-root', childId = 'synthetic-failure-context-child';
  const meta = (id, parent) => ({ type: 'session_meta', payload: { id, source: parent ? { subagent: { thread_spawn: { parent_thread_id: parent } } } : 'cli' } });
  const call = (id, name, args) => ({ type: 'response_item', payload: { type: 'function_call', call_id: id, name, arguments: JSON.stringify(args) } });
  const output = (id, value) => ({ type: 'response_item', payload: { type: 'function_call_output', call_id: id, output: value } });
  const usage = id => ({ type: 'token_usage_record', payload: { response_id: id, usage: { input_tokens: 10, output_tokens: 2 } } });
  const root = [meta(rootId), call('failure-spawn', 'spawn_agent', { message: 'Synthetic failed child, parent wait not success proof' }), output('failure-spawn', { agent_id: childId }), usage('root-spawn'), call('failure-wait', 'wait_agent', { targets: [childId] }), usage('root-wait'), output('failure-wait', { status: { [childId]: { completed: 'Synthetic parent wait report only' } } })];
  const childRaw = [meta(childId, rootId), call('failure-command', 'exec_command', { cmd: 'node synthetic-failure-check.js --case 23' }), usage('child-failure'), output('failure-command', 'Synthetic recorded error, command not executed'), { type: 'event_msg', payload: { type: 'exec_command_end', call_id: 'failure-command', duration: { secs: 0, nanos: 500000000 }, exit_code: 7, status: 'completed' } }];
  for (const [id, records] of [[rootId, root], [childId, childRaw]]) fs.writeFileSync(path.join(source, 'rollout-' + id + '.jsonl'), records.map(JSON.stringify).join('\n') + '\n');
  fs.writeFileSync(path.join(home, '.codex/session_index.jsonl'), [rootId, childId].map(id => JSON.stringify({ id, thread_name: 'Synthetic failure context ' + id })).join('\n') + '\n');
  const child = spawn(copyDistribution(directory), ['serve', '--host', '127.0.0.1', '--port', '0'], { env: { ...process.env, ...resolveJavaEnvironment(), HOME: home, INDEX_DIR: path.join(directory, 'index'), JAVA_OPTS: `"-Duser.home=${home}"`, APP_CLI_OPTS: '', JAVA_TOOL_OPTIONS: '', JDK_JAVA_OPTIONS: '', _JAVA_OPTIONS: '' }, stdio: ['ignore', 'pipe', 'pipe'] });
  let logs = '';
  const base = await new Promise((resolve, reject) => { child.once('error', reject); child.once('exit', c => reject(new Error('early ' + c + logs))); for (const stream of [child.stdout, child.stderr]) stream.on('data', d => { logs += d; const m = logs.match(/serve 已就绪: (http:\/\/127\.0\.0\.1:\d+)/); if (m) resolve(m[1]); }); });
  try {
    const api = base + '/api/sessions/codex/' + rootId;
    await expect.poll(async () => (await request.get(api + '/execution')).status()).toBe(200);
    const data = await (await request.get(api + '/execution')).json(), facts = await (await request.get(api + '/collaboration')).json();
    const label = facts.items.find(row => row.target === 'subagent:' + childId).targetLabel;
    expect(data.diagnostics.firstFailureTool).toMatchObject({ scope: 'subagent', subagentId: childId, exitCode: 7, toolCallId: 'failure-command' });
    expect(data.diagnostics.firstFailure).toBe('failure-command');
    expect(facts.items.flatMap(row => row.reports || []).some(report => report.phase === 'result_report' && report.reportedStatus === 'completed')).toBe(true);
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: 1000 }); await page.goto(base + '/sessions/codex/' + rootId);
      const card = page.locator('.se-judgments article').first();
      await expect(card).toContainText('1 个工具有失败信号'); await expect(card).toContainText('执行归属：' + label + ' · 独立上下文');
      await expect(card).toContainText('node synthetic-failure-check.js --case 23');
      await expect(card.locator('p').first()).toHaveText('首个依据：退出码 7；不等同整个任务失败。');
      const locate = card.getByRole('button', { name: '定位首个失败', exact: true }); const target = await locate.getAttribute('data-execution-locate'); expect(target).toBe(data.diagnostics.firstFailure);
      await locate.focus();
      const guarded = await page.evaluate(() => {
        const card = document.querySelector('.se-judgments article'), span = card.querySelector('[data-execution-context-key]'), key = span.dataset.executionContextKey, target = card.querySelector('button');
        collaborationView.labels.delete(key); syncExecutionContextLabels(); const fallback = span.textContent, explanation = card.querySelector('p'), measurement = document.querySelector('.se-measurement'), basis = document.querySelector('[data-execution-judgment] > p.se-basis'); measurement.open = true;
        collaborationView.labels.set(key, 'Synthetic authoritative label'); syncExecutionContextLabels();
        return { measurementSame: measurement === document.querySelector('.se-measurement'), measurementOpen: measurement.open, basisSame: basis === document.querySelector('[data-execution-judgment] > p.se-basis'), fallback, text: span.textContent, sameExplanation: explanation === card.querySelector('p'), explanation: explanation.textContent, sameCard: card === document.querySelector('.se-judgments article'), sameSpan: span === card.querySelector('[data-execution-context-key]'), focused: document.activeElement === target };
      });
      expect(guarded).toEqual({ measurementSame: true, measurementOpen: true, basisSame: true, fallback: '子上下文 ' + childId + ' · 独立上下文', text: 'Synthetic authoritative label · 独立上下文', sameExplanation: true, explanation: '首个依据：退出码 7；不等同整个任务失败。', sameCard: true, sameSpan: true, focused: true });
      await expect(locate).toHaveAttribute('data-execution-locate', target); await locate.click(); await expect(page.locator('[data-execution-tool]:focus')).toHaveCount(1);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    }
    // UI guards only: missing/unknown scopes cannot be inferred as main; anonymous child keeps honest identity.
    const guards = await page.evaluate(original => {
      return [{ scope: 'main' }, { scope: 'subagent', subagentId: null }, { scope: 'unknown' }, {}, null].map(identity => {
        applyExecutionPage({ ...original, diagnostics: { ...original.diagnostics, firstFailureTool: identity ? { ...original.diagnostics.firstFailureTool, ...identity, subagentId: identity.subagentId || null } : null } }, false);
        return document.querySelector('.se-judgments article').textContent;
      });
    }, data);
    expect(guards[0]).toContain('执行归属：主会话');
    expect(guards[1]).toContain('执行归属：子 Agent · 身份未记录 · 独立上下文');
    expect(guards[2]).toContain('执行归属：归属未记录'); expect(guards[2]).not.toContain('主会话');
    // Missing scope must actually omit the source value, rather than inherit the real child scope.
    const missing = await page.evaluate(original => { const tool = { ...original.diagnostics.firstFailureTool }; delete tool.scope; applyExecutionPage({ ...original, diagnostics: { ...original.diagnostics, firstFailureTool: tool } }, false); return document.querySelector('.se-judgments article').textContent; }, data);
    expect(missing).toContain('执行归属：归属未记录'); expect(missing).not.toContain('主会话');
    expect(guards[4]).not.toContain('执行归属：');
    await test.info().attach('failure-context-source-api.json', { body: JSON.stringify({ root, childRaw, data, facts }), contentType: 'application/json' });
  } finally { child.kill('SIGTERM'); await new Promise(resolve => child.once('exit', resolve)); fs.writeFileSync(path.join(directory, 'service.log'), logs); }
});

// 会改变来源形状、观测停机日志或验证独立代际的测试继续用全新的 HOME 和索引。
async function withLongOperationNormal(request, partial, read, inputForChild08, childIdentities) {
  const server = await startLongOperationNormal(request, partial, inputForChild08, childIdentities);
  try {
    await read(server.snapshot);
  } finally {
    await server.close();
  }
}

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
  const child = spawn(copyDistribution(directory), ['serve', '--host', '127.0.0.1', '--port', '0'], { env: { ...process.env, ...resolveJavaEnvironment(), HOME: home, INDEX_DIR: path.join(directory, 'index'), JAVA_OPTS: `"-Duser.home=${home}"`, APP_CLI_OPTS: '', JAVA_TOOL_OPTIONS: '', JDK_JAVA_OPTIONS: '', _JAVA_OPTIONS: '' }, stdio: ['ignore', 'pipe', 'pipe'] });
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
        if (/后台扫描失败结果:|启动扫描失败|后台扫描获取锁失败|(?:warm|hot) 层级扫描失败/.test(logs)) reject(new Error('initial synthetic scan failed: ' + logs));
        else if (ready && /后台扫描完成: tier=full window=all updated=\d+ perSource=/.test(logs)) resolve(ready[1]);
      });
    });
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

for (const partial of [false, true]) for (const width of [1440, 390]) test('分层耗时线索 defaults precision and scope ' + (partial ? 'partial199of200' : 'full200of200') + ' at ' + width + 'px', async ({ page, request, readLongOperationNormal }) => {
  await readLongOperationNormal(request, partial, async ({ base, rootId, children, raws, api, data, signals }) => {
    const requests = []; page.on('request', r => { if (r.url().includes('/api/')) requests.push(r.url()); });
    await page.setViewportSize({ width, height: 1000 }); await page.goto(base + '/sessions/codex/' + rootId);
    const section = page.locator('[data-execution-long-operations]'); await expect(section).toBeVisible();
    await expect(section).toContainText('exec_command · 可信已测 ' + (partial ? '231' : '232') + '/232 次'); await expect(section).toContainText(partial ? '已测累计 99.5s' : '已测累计 100s'); await expect(section).toContainText(partial ? '已测 199/200 次' : '已测 200/200 次'); await expect(section).toContainText('单次最大值 35s'); await expect(section.locator('[data-execution-long-operation]')).toHaveCount(3);
    await expect(section.locator('[data-execution-signal-other] [data-execution-context-key="subagent:' + children[8] + '"]')).toHaveText(data.contextLabels['subagent:' + children[8]] + ' · 独立上下文');
    for (const row of await section.locator('[data-execution-long-operation]').all()) {
      await expect(row.getByRole('button')).toHaveText(['查看上下文过程', '定位代表调用', '查看任务与往来']);
    }
    const cumulativeActions = section.locator('[data-execution-long-operation]').first().getByRole('button');
    await cumulativeActions.nth(0).focus(); await page.keyboard.press('Tab'); await expect(cumulativeActions.nth(1)).toBeFocused();
    await page.keyboard.press('Tab'); await expect(cumulativeActions.nth(2)).toBeFocused();
    const summaryLabelGuard = await page.evaluate(() => {
      const section = document.querySelector('[data-execution-long-operations]'), row = section.querySelector('[data-execution-long-operation]'), span = section.querySelector('[data-execution-signal-other] [data-execution-context-key]'), button = section.querySelector('[data-execution-signal-metric]');
      button.focus(); collaborationView.labels.set(span.dataset.executionContextKey, 'Synthetic ninth summary label'); syncExecutionContextLabels();
      return { sameRow: row === section.querySelector('[data-execution-long-operation]'), sameSpan: span === section.querySelector('[data-execution-signal-other] [data-execution-context-key]'), text: span.textContent, focus: document.activeElement === button };
    });
    expect(summaryLabelGuard).toEqual({ sameRow: true, sameSpan: true, text: 'Synthetic ninth summary label · 独立上下文', focus: true });
    const beforeSwitch = requests.length, metric = section.getByRole('button', { name: '单次耗时', exact: true });
    await metric.focus(); await page.keyboard.press('Enter'); await expect(metric).toBeFocused();
    await expect(section.locator('[data-execution-long-operation]')).toHaveCount(3);
    await expect(section.locator('[data-execution-signal-other]')).toContainText(partial ? '已测累计最大值 99.5s' : '已测累计最大值 100s');
    expect(requests.length).toBe(beforeSwitch); await expect(section).toContainText('单次 35s'); await expect(section).toContainText('Synthetic ninth summary label');
    for (const row of await section.locator('[data-execution-long-operation]').all()) {
      await expect(row.getByRole('button')).toHaveText(['定位此动作', '查看任务与往来']);
    }
    const singleActions = section.locator('[data-execution-long-operation]').first().getByRole('button');
    await singleActions.nth(0).focus(); await page.keyboard.press('Tab'); await expect(singleActions.nth(1)).toBeFocused();
    await expect(section).toContainText('SYNTHETIC_LONG_CHILD_09_NOT_EXECUTED'); await expect(section.locator('[data-execution-long-operation]')).toHaveCount(3);
    await expect(page.locator('[data-execution-workload]').first()).toContainText('wait_agent · 已测累计 2s');
    await expect(page.locator('[data-execution-workload]').nth(1)).toContainText('exec_command · 已测累计 12s');
    await expect(page.locator('[data-execution-workload]').nth(1)).toContainText('已测 24/24 次');
    expect(requests.some(u => u.includes('/payload/'))).toBe(false);
    const first = section.locator('[data-execution-long-operation]').first(); const button = first.getByRole('button', { name: '定位此动作', exact: true });
    const stable = await page.evaluate(() => { const row = document.querySelector('[data-execution-long-operation]'), span = row.querySelector('[data-execution-context-key]'), key = span.dataset.executionContextKey, button = row.querySelector('button'); button.focus(); collaborationView.labels.set(key, 'Synthetic ninth authoritative label'); syncExecutionContextLabels(); return { same: row === document.querySelector('[data-execution-long-operation]'), text: span.textContent, focus: document.activeElement === button }; });
    expect(stable).toEqual({ same: true, text: 'Synthetic ninth authoritative label · 独立上下文', focus: true });
    await expect(button).toHaveAttribute('data-execution-locate', 'long-check-09-0'); await expect(page.locator('[data-execution-tool="long-check-09-0"]')).toHaveCount(0); await button.click();
    await expect(section.getByRole('button', { name: '单次耗时', exact: true })).toHaveAttribute('aria-pressed', 'true');
    const tool = page.locator('[data-execution-tool="long-check-09-0"]'); await expect(tool).toBeFocused(); await expect(tool).toContainText('35s');
    await tool.locator('.se-tool-evidence > summary').click(); await tool.getByRole('button', { name: '执行结果', exact: true }).click(); await expect(page.locator('dialog.payload-modal pre').last()).toHaveText('Synthetic complete Result long-check-09-0'); await page.keyboard.press('Escape');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    // UI guards, not parser claims: C2 keeps exact returned order/precision and separate family coverage.
    const cumulativeGuard = await page.evaluate(original => {
      const diag = original.diagnostics, signal = diag.workloadSignals, sample = signal.candidates[0];
      const guarded = { ...original, diagnostics: { ...diag, longOperations: { ...diag.longOperations, candidates: [] }, workloadSignals: { ...signal, totalTools: signal.measuredTools + 9, unknownTools: 2, otherKindTools: 3, excludedIdentityTools: 4, eligibleGroups: 7,
        candidates: ['0', '1', '9007199254740993'].map((measuredWorkNanos, i) => ({ ...sample, measuredWorkNanos, longest: { ...sample.longest, durationNanos: measuredWorkNanos, tool: { ...sample.longest.tool, toolCallId: 'ui-cumulative-' + i } } })) } } };
      applyExecutionPage(guarded, false);
      const text = document.querySelector('[data-execution-long-operations]').textContent;
      const controls = document.querySelectorAll('[data-execution-signal-metric]').length;
      applyExecutionPage(original, false);
      document.querySelector('[data-execution-signal-metric="single"]').focus();
      document.querySelector('[data-execution-signal-metric="single"]').click();
      applyExecutionPage(original, true);
      const appendRetained = document.querySelector('[data-execution-signal-metric="single"]').getAttribute('aria-pressed');
      applyExecutionPage(original);
      const snapshotReset = document.querySelector('[data-execution-signal-metric="cumulative"]').getAttribute('aria-pressed');
      const snapshotNoFocus = !document.activeElement.hasAttribute('data-execution-signal-metric');
      const old = document.body.getAttribute('data-index-generation');
      document.querySelector('[data-execution-signal-metric="single"]').focus();
      document.querySelector('[data-execution-signal-metric="single"]').click();
      document.body.setAttribute('data-index-generation', 'ui-guard-next-generation'); applyExecutionPage(original, false);
      const generationReset = document.querySelector('[data-execution-signal-metric="cumulative"]').getAttribute('aria-pressed');
      const generationNoFocus = !document.activeElement.hasAttribute('data-execution-signal-metric');
      if (old === null) document.body.removeAttribute('data-index-generation'); else document.body.setAttribute('data-index-generation', old);
      return { text, controls, appendRetained, snapshotReset, generationReset, snapshotNoFocus, generationNoFocus };
    }, data);
    expect(cumulativeGuard.text).toContain('已测累计 0ms'); expect(cumulativeGuard.text).toContain('已测累计 <1ms'); expect(cumulativeGuard.text).toContain('已测累计 9007199.254740993s');
    expect(cumulativeGuard.text.indexOf('已测累计 0ms')).toBeLessThan(cumulativeGuard.text.indexOf('已测累计 <1ms'));
    expect(cumulativeGuard.text).toContain('累计线索 3/7 组（按执行上下文分组）'); expect(cumulativeGuard.text).toContain('归属边界未确认而排除 4 次');
    expect(cumulativeGuard.text).toContain('缺少本口径的执行器原始时长 2 次'); expect(cumulativeGuard.text).toContain('其他计时口径 3 次');
    expect(cumulativeGuard).toMatchObject({ controls: 0, appendRetained: 'true', snapshotReset: 'true', generationReset: 'true', snapshotNoFocus: true, generationNoFocus: true });
    // Bounded UI guards: precision/order/coverage and visibility use the real page as a base, not parser claims.
    const guard = await page.evaluate(original => {
      const diag = original.diagnostics, signal = diag.longOperations, sample = signal.candidates[0];
      function render(extra) { applyExecutionPage({ ...original, diagnostics: { ...diag, workloadSignals: { ...diag.workloadSignals, candidates: [] }, ...extra } }, false); return document.querySelector('[data-execution-long-operations]')?.textContent || ''; }
      const precise = render({ longOperations: { ...signal, unknownTools: 2, otherKindTools: 3, unconfirmedIdentityTools: 4, totalTools: signal.measuredTools + 9, candidates: ['0', '1', '9007199254740993'].map((durationNanos, i) => ({ durationNanos, tool: { ...sample.tool, toolCallId: 'ui-precise-' + i } })) } });
      const noCap = render({ workloadGroups: diag.workloads.length }); const noCandidate = render({ longOperations: { ...signal, candidates: [] }, workloadSignals: { ...diag.workloadSignals, candidates: [] } });
      render({ failures: 1, firstFailure: sample.tool.toolCallId, firstFailureTool: sample.tool });
      const failureFirst = document.querySelector('.se-judgments article').compareDocumentPosition(document.querySelector('[data-execution-long-operations]')) & Node.DOCUMENT_POSITION_FOLLOWING;
      return { precise, noCap, noCandidate, failureFirst: !!failureFirst };
    }, data);
    expect(guard.precise).toContain('单次 0ms'); expect(guard.precise).toContain('单次 <1ms'); expect(guard.precise).toContain('单次 9007199.254740993s');
    expect(guard.precise.indexOf('单次 0ms')).toBeLessThan(guard.precise.indexOf('单次 <1ms')); expect(guard.precise.indexOf('单次 <1ms')).toBeLessThan(guard.precise.indexOf('单次 9007199.254740993s'));
    expect(guard.precise).toContain('缺少本口径的执行器原始时长 2 次'); expect(guard.precise).toContain('其他计时口径 3 次'); expect(guard.precise).toContain('身份依据不足 4 次');
    expect(guard.noCap).toContain('单次 35s'); // Untruncated, but actual candidates span confirmed contexts.
    expect(guard.noCandidate).toBe(''); expect(guard.failureFirst).toBe(true);
    const selected = await (await request.get(api + '/execution?agent_context=' + encodeURIComponent('subagent:' + children[8]))).json();
    await page.evaluate(original => applyExecutionPage(original, false), data);
    await page.locator('[data-collaboration-participants]').click();
    const ninth = page.locator('[data-collaboration-agent="subagent:' + children[8] + '"]');
    while (!await ninth.count()) await page.locator('[data-collaboration-pagination] button').click();
    await ninth.click(); await expect(page.locator('[data-execution-judgment]')).toBeFocused();
    await expect(page.locator('[data-execution-long-operations]')).toHaveCount(0);
    await expect(page.locator('[data-execution-judgment]')).toContainText('已测累计 35s');
    expect(await page.evaluate(() => executionView.agent)).toBe('subagent:' + children[8]);
    await test.info().attach('long-operations-normal-source-api.json', { body: JSON.stringify({ raws, data, selected }), contentType: 'application/json' });
  });
});

for (const width of [1440, 390]) test('证据分层 分层耗时线索 task08/task09 native navigation chain at ' + width + 'px', async ({ page, request, readLongOperationNormal }) => {
  await readLongOperationNormal(request, false, async ({ base, rootId, children, raws, api, data, signals }) => {
    const requests = []; page.on('request', r => { if (r.url().includes('/api/')) requests.push(r.url()); });
    await page.setViewportSize({ width, height: 1000 }); await page.goto(base + '/sessions/codex/' + rootId);
    const section = page.locator('[data-execution-long-operations]'); await expect(section).toBeVisible();
      await captureDiagnosticScreenshot(section, { path: test.info().outputPath('signals-default-' + width + '.png') });
      const taskEntry = section.locator('[data-execution-long-operation]').first().getByRole('button', { name: '查看任务与往来', exact: true });
      expect(await taskEntry.count()).toBe(1); // Missing entry is a fast original red, not a locator timeout.
      await expect(page.locator('[data-collaboration-relation]')).toHaveCount(5);
      const initiallyLoaded = await page.locator('[data-collaboration-source]').evaluateAll(nodes => nodes.map(node => JSON.parse(node.dataset.collaborationSource)[0]));
      expect(initiallyLoaded).not.toContain('subagent:' + children[7]); expect(initiallyLoaded).not.toContain('subagent:' + children[8]);
      {
      const response = page.waitForResponse(r => r.url().includes('/collaboration?') && new URL(r.url()).searchParams.get('selection') === 'subagent:' + children[7]);
      const start = requests.length; await taskEntry.click();
      const exchanges = await (await response).json(); expect(exchanges.items.length).toBeLessThanOrEqual(20);
      await test.info().attach('exchanges-08-' + width + '.json', { body: JSON.stringify({ initiallyLoaded, exchanges }), contentType: 'application/json' });
      const context = page.locator('[data-collaboration-context]'); await expect(context).toBeFocused();
      await assertSelectedContextIdentity(page, 'subagent:' + children[7]); await expect(page.locator('[data-collaboration-items]')).toContainText('Synthetic independent task 08');
      const calls = requests.slice(start).filter(url => url.includes('/collaboration?'));
      expect(calls).toHaveLength(1); expect(new URL(calls[0]).searchParams.get('view')).toBe('exchanges'); expect(new URL(calls[0]).searchParams.get('selection')).toBe('subagent:' + children[7]);
      expect(await page.locator('[data-collaboration-relation]').count()).toBe(1); // Real normal original red: two typed facts, one task card.
      await expect(page.locator('[data-collaboration-pagination]')).toContainText('2 / 2 条事实');
      await expect(page.locator('[data-collaboration-pagination]')).toContainText('1 张主卡');
      await captureDiagnosticScreenshot(page.locator('[data-collaboration]'), { path: test.info().outputPath('task08-' + width + '.png') });
      const declaration = page.locator('[data-collaboration-relation]').filter({ hasText: 'Synthetic independent task 08' });
      const evidence = declaration.locator('[data-collaboration-evidence] > summary'); await evidence.click();
      const receiptEvidence = declaration.locator('[data-collaboration-creation-evidence]');
      await expect(receiptEvidence).toContainText('delegate / result_report');
      await expect(receiptEvidence).toContainText(exchanges.items[1].sourceLocator);
      expect(requests.slice(start).some(url => url.includes('/payload/'))).toBe(false);
      await receiptEvidence.getByRole('button', { name: '创建回执 Result', exact: true }).click();
      await expect(page.locator('dialog.payload-modal pre').last()).toHaveText(JSON.stringify({ agent_id: children[7] })); await page.keyboard.press('Escape');
      const locate = declaration.getByRole('button', { name: '定位发起记录', exact: true }); await expect(locate).toHaveAttribute('data-collaboration-locate', 'token_usage_record:long-delegations'); await locate.click();
      await expect(page.locator('[data-execution-group="token_usage_record:long-delegations"]')).toBeFocused();
      }
    await section.getByRole('button', { name: '单次耗时', exact: true }).click();
    await expect(section).toContainText('单次 35s');
      const response = page.waitForResponse(r => r.url().includes('/collaboration?') && new URL(r.url()).searchParams.get('selection') === 'subagent:' + children[8]);
      const start = requests.length;
      await section.locator('[data-execution-long-operation]').first().getByRole('button', { name: '查看任务与往来', exact: true }).click();
      const exchanges = await (await response).json(); expect(exchanges.items.length).toBeLessThanOrEqual(20);
      await test.info().attach('exchanges-09-' + width + '.json', { body: JSON.stringify(exchanges), contentType: 'application/json' });
      expect(requests.slice(start).filter(url => url.includes('/collaboration?'))).toHaveLength(1);
      await expect(page.locator('[data-collaboration-context]')).toBeFocused(); await assertSelectedContextIdentity(page, 'subagent:' + children[8]);
      await expect(page.locator('[data-collaboration-items]')).toContainText('Synthetic independent task 09');
      await expect(page.locator('[data-collaboration-relation]')).toHaveCount(1);
      await expect(page.locator('[data-collaboration-creation-evidence]')).toHaveCount(1);
      await captureDiagnosticScreenshot(page.locator('[data-collaboration]'), { path: test.info().outputPath('task09-' + width + '.png') });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
});

for (const kind of ['metric', 'other', 'append', 'lastTarget', 'task']) test('分层耗时线索 pending native response respects ' + kind + ' reading', async ({ page, request, readLongOperationNormal }) => {
  await readLongOperationNormal(request, false, async ({ base, rootId, children, raws, api, data, signals }) => {
      // Actual normal HTTP passthrough delayed only for timing; no DTO/parser facts replaced.
      await page.setViewportSize({ width: 1440, height: 900 });
      async function delayedReading(kind) {
        await page.goto(base + '/sessions/codex/' + rootId);
        const section = page.locator('[data-execution-long-operations]');
        await section.getByRole('button', { name: '单次耗时', exact: true }).click();
        let release, arrived;
        const gate = new Promise(resolve => { release = resolve; }), arrival = new Promise(resolve => { arrived = resolve; });
        const matches = url => url.href.includes('/execution?') && url.href.includes(kind === 'append' ? 'cursor=' : 'target=long-check-09-0');
        const handler = async route => { const response = await route.fetch(); arrived(); await gate; await route.fulfill({ response }); };
        await page.route(matches, handler);
        try {
          await page.evaluate(() => {
            window.focusRepairBeforePage = executionView.page; window.focusRepairTargetScrolls = 0;
            const original = Element.prototype.scrollIntoView;
            Element.prototype.scrollIntoView = function (...args) { if (this.dataset.executionTool === 'long-check-09-0') window.focusRepairTargetScrolls++; return original.apply(this, args); };
          });
          if (kind === 'append') await page.locator('[data-execution-pagination] button').click();
          else await section.getByRole('button', { name: '定位此动作', exact: true }).first().click();
          await arrival;
          if (kind === 'task') {
            await section.locator('[data-execution-long-operation]').first().getByRole('button', { name: '查看任务与往来', exact: true }).click();
            await expect(page.locator('[data-collaboration-context]')).toBeFocused(); release();
            await expect.poll(() => page.evaluate(() => executionView.page !== window.focusRepairBeforePage)).toBe(true);
            await expect(page.locator('[data-collaboration-context]')).toBeFocused();
            expect(await page.evaluate(() => window.focusRepairTargetScrolls)).toBe(0);
            return;
          }
          if (kind === 'lastTarget') {
            release(); await expect(page.locator('[data-execution-tool="long-check-09-0"]')).toBeFocused();
            expect(await page.evaluate(() => window.focusRepairTargetScrolls)).toBe(1);
            return;
          }
          const metric = section.getByRole('button', { name: '已测累计', exact: true });
          await metric.focus(); await page.keyboard.press('Enter'); await expect(metric).toBeFocused();
          const other = page.locator('[data-execution-filter="failed"]');
          if (kind === 'other') await other.focus();
          const scroll = await page.evaluate(() => scrollY);
          release();
          await expect.poll(() => page.evaluate(() => executionView.page !== window.focusRepairBeforePage)).toBe(true);
          await expect(section.getByRole('button', { name: '已测累计', exact: true })).toHaveAttribute('aria-pressed', 'true');
          if (kind === 'other') await expect(other).toBeFocused();
          else await expect(section.getByRole('button', { name: '已测累计', exact: true })).toBeFocused();
          // DOM replacement can adjust browser scroll anchoring by a few pixels; assert the actual old target scroll action is absent.
          expect(await page.evaluate(() => window.focusRepairTargetScrolls)).toBe(0);
          await test.info().attach('pending-' + kind + '-focus.json', { body: JSON.stringify(await page.evaluate(before => ({ beforeScroll: before, afterScroll: scrollY, mode: executionView.signalMetric, activeMetric: document.activeElement.dataset.executionSignalMetric || null, activeFilter: document.activeElement.dataset.executionFilter || null, targetScrolls: window.focusRepairTargetScrolls, dataApplied: executionView.page !== window.focusRepairBeforePage }), scroll)), contentType: 'application/json' });
          if (kind !== 'append') await expect(page.locator('[data-execution-tool="long-check-09-0"]')).toHaveCount(1);
        } finally { release(); await page.unroute(matches, handler); }
      }
      await delayedReading(kind);
  });
});

test('任务与往来 real import transport isolation and explicit UI-only candidate lifecycle guards', async ({ page, request, baseURL }) => {
  const imported = await upload(request, baseURL, 'codex', codexSource(25));
  const paths = []; page.on('request', r => { if (r.url().includes('/api/')) paths.push(r.url()); });
  let release = () => {};
  try {
    await page.goto(imported.detail_url); await expect(page.locator('[data-collaboration-context]')).toBeVisible();
    // Import does not collect neighbouring child files and has no trustworthy C/C2 candidates.
    // This is only a UI consumer guard; actual task records below still come from native imported raw.
    await expect(page.locator('[data-execution-task-context]')).toHaveCount(0);
    await page.evaluate(() => {
      const page = executionView.page;
      const candidates = [0, 1].map(i => {
        const tool = { scope: 'subagent', subagentId: 'worker-' + i, name: 'exec_command', toolCallId: 'ui-only-' + i, inputPreview: 'UI candidate guard, not a parsed execution' };
        return { scope: tool.scope, subagentId: tool.subagentId, name: tool.name, kind: 'executor_reported', measuredWorkNanos: '1', totalTools: 1, measuredTools: 1, unknownTools: 0, otherKindTools: 0, longest: { durationNanos: '1', tool } };
      });
      applyExecutionPage({ ...page, diagnostics: { ...page.diagnostics, workloadGroups: 9, workloads: [], workloadSignals: { totalTools: 2, measuredTools: 2, unknownTools: 0, otherKindTools: 0, excludedIdentityTools: 0, eligibleGroups: 2, candidates }, longOperations: { totalTools: 2, measuredTools: 2, unknownTools: 0, otherKindTools: 0, unconfirmedIdentityTools: 0, candidates: [{ durationNanos: '1', tool: candidates[0].longest.tool }] } } }, false);
    });
    let mode = 'fail', arrived, delivered0 = 0; const nativePages = [];
    const entry = key => page.locator('[data-execution-task-context][data-collaboration-exchanges="subagent:worker-' + key + '"]');
    let arrival;
    function delay() { mode = 'delay'; arrival = new Promise(r => { arrived = r; }); return new Promise(r => { release = r; }); }
    let gate;
    await page.route('**/collaboration?*', async route => {
      const url = new URL(route.request().url());
      if (url.searchParams.get('selection') !== 'subagent:worker-0') return route.continue();
      const response = await route.fetch(); const data = await response.json(); nativePages.push({ selection: data.selection, items: data.items.length, nextCursor: !!data.nextCursor });
      if (mode === 'fail') { await route.fulfill({ response, status: 500, body: JSON.stringify({ error: 'Synthetic transport failure, not parser data' }) }); delivered0++; return; }
      if (mode === 'delay') { arrived(); await gate; }
      await route.fulfill({ response }); delivered0++;
    });
    const host = page.locator('[data-collaboration]'), status = page.locator('[data-collaboration-status]');
    await entry(0).click(); await expect(host).toContainText('读取失败：协作往来 · 所选上下文：subagent:worker-0'); await expect(host).not.toContainText('Synthetic task 1');
    await page.evaluate(() => { window.oldTaskRetry = document.querySelector('[data-collaboration-status] button'); });
    mode = 'normal'; await status.getByRole('button', { name: 'Retry', exact: true }).click();
    await expect(page.locator('[data-collaboration-context]')).toBeFocused(); await assertSelectedContextIdentity(page, 'subagent:worker-0');
    mode = 'fail'; await entry(0).click(); await expect(host).toContainText('读取失败：');
    gate = delay(); await status.getByRole('button', { name: 'Retry', exact: true }).click(); await arrival;
    await expect(host).toContainText('正在读取协作往来 · 所选上下文：subagent:worker-0');
    const single = page.getByRole('button', { name: '单次耗时', exact: true }); await single.focus(); await page.keyboard.press('Enter'); release();
    await expect(status).toHaveText(''); await expect(host).toContainText('Synthetic task 0'); await expect(single).toBeFocused();
    await page.getByRole('button', { name: '已测累计', exact: true }).click();
    gate = delay(); await entry(0).click(); await arrival; await entry(1).click();
    await expect(page.locator('[data-collaboration-context]')).toBeFocused(); await assertSelectedContextIdentity(page, 'subagent:worker-1'); release(); await expect.poll(() => delivered0).toBe(5);
    await expect(host).toContainText('Synthetic task 1'); await expect(host).not.toContainText('Synthetic task 0');
    const beforeStaleRetry = paths.length; await page.evaluate(() => window.oldTaskRetry.click()); expect(paths.length).toBe(beforeStaleRetry);
    gate = delay(); await entry(0).click(); await arrival; const other = page.locator('[data-execution-filter="failed"]'); await other.focus(); release();
    await expect(host).toContainText('Synthetic task 0'); await expect(other).toBeFocused();
    const calls = paths.filter(url => url.includes('/collaboration?') && new URL(url).searchParams.get('selection'));
    expect(calls.length).toBe(7); expect(calls.every(url => new URL(url).pathname === '/api/imports/' + imported.import_id + '/collaboration')).toBe(true);
    expect(nativePages.every(data => data.items <= 20)).toBe(true); expect(nativePages[0].items).toBe(20);
    await page.locator('[data-collaboration-pagination] button').click(); await expect.poll(() => paths.filter(url => url.includes('/collaboration?') && new URL(url).searchParams.has('cursor')).length).toBe(1);
    await assertSelectedContextIdentity(page, 'subagent:worker-0');
    await expect(host.locator('[data-collaboration-relation]')).toHaveCount(40);
    // Frozen-scope epoch guard only, not a parser or actual reindex simulation: a prior real HTTP response cannot restore an old scope.
    gate = delay(); await entry(0).click(); await arrival;
    await page.evaluate(() => { collaborationView.epoch++; document.querySelector('[data-collaboration]').textContent = 'UI guard: newer frozen scope'; });
    const deliveredBefore = delivered0; release(); await expect.poll(() => delivered0).toBe(deliveredBefore + 1); await expect(host).toHaveText('UI guard: newer frozen scope');
    // UI identity guards only: main and anonymous contexts never receive a guessed task destination.
    const guessed = await page.evaluate(() => {
      const page = executionView.page, signal = page.diagnostics.workloadSignals, sample = signal.candidates[0];
      const candidates = [{ scope: 'main', subagentId: null }, { scope: 'subagent', subagentId: null }, { scope: 'subagent', subagentId: 'unknown-sidechain:synthetic' }].map(identity => ({ ...sample, ...identity }));
      applyExecutionPage({ ...page, diagnostics: { ...page.diagnostics, workloadSignals: { ...signal, candidates }, longOperations: { ...page.diagnostics.longOperations, candidates: [] } } }, false);
      return document.querySelectorAll('[data-execution-task-context]').length;
    });
    expect(guessed).toBe(0);
    expect(paths.some(url => url.includes('/payload/'))).toBe(false);
    await test.info().attach('task-import-url-isolation.json', { body: JSON.stringify({ calls, nativePages, scope: 'Real single-file import raw/API; injected UI candidates only, not imported C2/parser capability' }), contentType: 'application/json' });
  } finally { release(); await page.unroute('**/collaboration?*'); expect((await request.delete('/api/imports/' + imported.import_id)).status()).toBe(204); }
});

// 明确 UI guards：以真实 single-file API 行为基底，不把白名单/冲突注入称为解析事实。
test('证据分层 strict selected-page identity guards, native import evidence and append stability', async ({ page, request, baseURL }) => {
  const imported = await upload(request, baseURL, 'codex', codexSource(0));
  const api = '/api/imports/' + imported.import_id;
  const paths = []; page.on('request', r => { if (r.url().includes('/api/')) paths.push(r.url()); });
  try {
    const selected = await (await request.get(api + '/collaboration?view=exchanges&selection=subagent%3Aworker-0')).json();
    expect(selected.items).toHaveLength(2);
    expect(selected.items.every(row => row.reason === 'single_file_not_included' && !row.childIncluded)).toBe(true);
    await page.goto(imported.detail_url);
    await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
    await expect(page.locator('[data-collaboration-relation]')).toHaveCount(5);
    await page.evaluate(value => applyCollaborationPage(value, false), selected);
    await expect(page.locator('[data-collaboration-relation]')).toHaveCount(2); // Actual import has no confirmed included-child relation reason.
    await expect(page.locator('[data-collaboration-creation-evidence]')).toHaveCount(0);
    const guard = await page.evaluate(original => {
      const declaration = { ...original.items[0], reason: 'child_candidate_available', parentIssue: '' };
      const receipt = { ...original.items[1], reason: 'explicit_parent_tool', parentIssue: '' };
      function render(rows) { const host = document.createElement('div'); host.innerHTML = collaborationSelectedExchanges(rows); return { cards: host.querySelectorAll('[data-collaboration-relation]').length, receipts: host.querySelectorAll('[data-collaboration-creation-evidence]').length, text: host.textContent }; }
      const valid = render([declaration, receipt]);
      const variants = [];
      function reject(name, rows) { const result = render(rows); variants.push({ name, cards: result.cards, facts: rows.length, receipts: result.receipts }); }
      for (const field of ['actor', 'callId', 'toolId', 'target']) {
        reject('mismatch ' + field, [declaration, { ...receipt, [field]: field === 'actor' ? 'subagent:other' : receipt[field] + '-other' }]);
        for (const value of ['', null, undefined]) reject('missing ' + field + ' ' + value, [{ ...declaration, [field]: value }, { ...receipt, [field]: value }]);
      }
      for (const phase of ['declaration', 'result_report']) for (const reason of ['child_not_found', 'single_file_not_included', 'conflicting_tool_identity', 'explicit_target', 'explicit_report', 'anonymous_sidechain', 'facts_truncated', 'brand_new_reason']) {
        reject(phase + ' reason ' + reason, [{ ...declaration, ...(phase === 'declaration' ? { reason } : {}) }, { ...receipt, ...(phase === 'result_report' ? { reason } : {}) }]);
      }
      for (const extra of [
        { actor: 'main', actorIdentityReason: 'explicit_instance' }, { actor: 'subagent:worker', actorIdentityReason: 'actor_unknown' },
        { actor: 'subagent:unknown-sidechain:1', actorIdentityReason: 'explicit_instance' }, { target: 'subagent:unknown-sidechain:1' }, { target: 'subagent:' },
        { callId: 'unknown:call' }, { callId: 'observed-input:call' }, { parentIssue: 'SUBAGENT_CYCLE' }
      ]) reject('unconfirmed ' + JSON.stringify(extra), [{ ...declaration, ...extra }, { ...receipt, ...extra }]);
      reject('duplicate declaration', [declaration, receipt, declaration]); reject('duplicate receipt', [declaration, receipt, receipt]);
      const other = { ...declaration, toolId: 'another-tool' }, otherReceipt = { ...receipt, toolId: 'another-tool' };
      reject('interleaved', [declaration, other, receipt, otherReceipt]); reject('reverse', [receipt, declaration]); reject('receipt only', [receipt]);
      const multiple = render([declaration, receipt, { ...declaration, actor: 'subagent:another-parent', actorIdentityReason: 'explicit_instance' }, { ...receipt, actor: 'subagent:another-parent', actorIdentityReason: 'explicit_instance' }]);
      const wait = { ...declaration, kind: 'wait' }, completed = { ...receipt, kind: 'wait', reportedStatus: 'completed' };
      const withWait = render([declaration, receipt, wait, completed]);
      applyCollaborationPage({ ...original, items: [declaration, receipt], selection: '' }, false);
      const unselectedCards = document.querySelectorAll('[data-collaboration-relation]').length;
      applyCollaborationPage({ ...original, items: [declaration], total: 2, offset: 0 }, false);
      const old = document.querySelector('[data-collaboration-relation]'), details = old.querySelector('details'); details.open = true; const focus = old.querySelector('button'); focus.focus();
      applyCollaborationPage({ ...original, items: [receipt], total: 2, offset: 1 }, true);
      const append = { sameNode: old === document.querySelector('[data-collaboration-relation]'), open: details.open, focus: document.activeElement === focus, cards: document.querySelectorAll('[data-collaboration-relation]').length, receipts: document.querySelectorAll('[data-collaboration-creation-evidence]').length, pager: document.querySelector('[data-collaboration-pagination]').textContent };
      applyCollaborationPage({ ...original, items: [declaration, receipt] }, false);
      return { valid, variants, multiple, withWait, unselectedCards, append };
    }, selected);
    expect(guard.valid).toMatchObject({ cards: 1, receipts: 1 });
    for (const item of guard.variants) expect(item, item.name).toMatchObject({ cards: item.facts, receipts: 0 });
    expect(guard.multiple).toMatchObject({ cards: 2, receipts: 2 });
    expect(guard.withWait).toMatchObject({ cards: 3, receipts: 1 }); expect(guard.withWait.text).toContain('completed'); expect(guard.withWait.text).toContain('不是整个任务的永久状态');
    expect(guard.unselectedCards).toBe(2); expect(guard.append).toMatchObject({ sameNode: true, open: true, focus: true, cards: 2, receipts: 0 }); expect(guard.append.pager).toContain('2 / 2 条事实');
    expect(paths.some(url => url.includes('/payload/'))).toBe(false);
    const card = page.locator('[data-collaboration-relation]');
    await expect(card.locator('[data-collaboration-evidence] details')).toHaveCount(0);
    await expect(card).toContainText('创建 ID 仅为归属证据，不是 child 回答或任务完成');
    await expect(card.getByRole('button', { name: '查看过程与耗时', exact: true })).toHaveCount(0);
    await card.locator('[data-collaboration-evidence] > summary').click();
    const receipt = card.locator('[data-collaboration-creation-evidence]');
    await expect(receipt).toContainText('delegate / result_report'); await expect(receipt).toContainText(selected.items[1].sourceLocator);
    await expect(receipt).toContainText(selected.items[1].callId); await expect(receipt).toContainText(selected.items[1].toolId);
    await card.getByRole('button', { name: '任务 Input', exact: true }).click();
    await expect(page.locator('dialog.payload-modal pre').last()).toContainText('Synthetic task 0'); await page.keyboard.press('Escape');
    await receipt.getByRole('button', { name: '创建回执 Result', exact: true }).click();
    await expect(page.locator('dialog.payload-modal pre').last()).toContainText('worker-0'); await page.keyboard.press('Escape');
    expect(paths.filter(url => url.includes('/payload/')).every(url => url.includes(api + '/payload/'))).toBe(true);
    await test.info().attach('selected-exchange-layer-ui-guards.json', { body: JSON.stringify({ selected, guard }), contentType: 'application/json' });
  } finally { expect((await request.delete('/api/imports/' + imported.import_id, { headers: { Origin: new URL(baseURL).origin } })).status()).toBe(204); }
});

test('统一线索计量分层 real normal details retain scope nodes and explicit sources', async ({ page, request, readLongOperationNormal }) => {
  await readLongOperationNormal(request, false, async ({ base, rootId, data }) => {
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: 900 }); await page.goto(base + '/sessions/codex/' + rootId);
      const detail = page.locator('[data-execution-workload-details]'), judgment = page.locator('[data-execution-judgment]');
      await expect(page.locator('[data-execution-long-operations]')).toContainText('已测累计 100s');
      await expect(detail).toHaveCount(1); await expect(detail).not.toHaveAttribute('open', '');
      await expect(detail.locator(':scope > summary')).toContainText('已载 8/11 组（前缀，非排名）');
      await expect(judgment.locator(':scope > .se-basis').last()).toContainText('已测工具 233 / 243');
      await expect(detail.locator('[data-execution-workload]')).toHaveCount(8);
      const requests = []; page.on('request', r => requests.push(r.url()));
      await detail.locator(':scope > summary').focus(); await page.keyboard.press('Enter');
      await expect(detail.locator('[data-execution-workload]').first()).toBeVisible(); expect(requests).toEqual([]);
      const bodyColor = await detail.locator('[data-execution-workload] h3').first().evaluate(n => ({ actual: getComputedStyle(n).color, expected: getComputedStyle(document.querySelector('[data-execution-judgment]')).color }));
      expect(bodyColor.actual).toBe(bodyColor.expected);
      const stability = await page.evaluate(original => {
        const detail = document.querySelector('[data-execution-workload-details]'), node = detail.querySelector('[data-execution-locate]'); node.focus();
        const measurement = document.querySelector('.se-measurement:not([data-execution-workload-details])'); measurement.open = true;
        applyExecutionPage(original, true);
        const result = { same: detail === document.querySelector('[data-execution-workload-details]'), node: node === document.activeElement, open: detail.open, measurement: measurement.open };
        document.querySelector('[data-execution-signal-metric="single"]').click(); syncExecutionContextLabels(); syncExecutionDelegationSources();
        return { ...result, afterMetric: detail === document.querySelector('[data-execution-workload-details]') && detail.open };
      }, data);
      expect(stability).toEqual({ same: true, node: true, open: true, measurement: true, afterMetric: true });
      await detail.locator(':scope > summary').click(); await expect(detail).not.toHaveAttribute('open', '');
      // Consumer-only qualification guards, not parser claims.
      const guards = await page.evaluate(original => {
        const diag = original.diagnostics;
        const apply = extra => { applyExecutionPage({ ...original, diagnostics: { ...diag, ...extra } }); return !!document.querySelector('[data-execution-workload-details]'); };
        const noCandidate = apply({ workloadSignals: { ...diag.workloadSignals, candidates: [] }, longOperations: { ...diag.longOperations, candidates: [] } });
        const failed = apply({ failures: 1 });
        const unknown = apply({ workloads: [{ ...diag.workloads[0], scope: 'subagent', subagentId: null }, ...diag.workloads.slice(1)] });
        const conflictingMain = apply({ workloads: [{ ...diag.workloads[0], scope: 'main', subagentId: 'synthetic-conflicting-main' }, ...diag.workloads.slice(1)] });
        const one = apply({ workloads: [diag.workloads[0]] });
        const gap = { ...diag.workloads[1], unknownTools: 2, otherKindTools: 3 };
        apply({ workloads: [diag.workloads[0], gap, ...diag.workloads.slice(2)] });
        const gapText = document.querySelector('[data-execution-workload-gaps]').textContent;
        applyExecutionPage(original); const detail = document.querySelector('[data-execution-workload-details]'); detail.open = true;
        document.body.setAttribute('data-index-generation', 'ui-disclosure-next'); applyExecutionPage(original, false);
        return { noCandidate, failed, unknown, conflictingMain, one, gapText, generationReset: !document.querySelector('[data-execution-workload-details]').open };
      }, data);
      expect(guards).toMatchObject({ noCandidate: false, failed: false, unknown: false, conflictingMain: false, one: false, generationReset: true });
      const revealed = await page.evaluate(() => {
        const host = document.querySelector('[data-collaboration]'), source = host.querySelector('[data-collaboration-agent]');
        const details = document.createElement('details'), summary = document.createElement('summary'); summary.textContent = 'UI-only nested source'; details.append(summary); source.before(details); details.append(source);
        collaborationView.returnFocus = source; syncExecutionCollaborationNavigation();
        const noBackgroundOpen = !details.open; document.querySelector('[data-execution-collaboration-return]').click();
        const result = { noBackgroundOpen, opened: details.open, focus: document.activeElement === source, same: source.isConnected };
        details.before(source); details.remove(); return result;
      });
      expect(revealed).toEqual({ noBackgroundOpen: true, opened: true, focus: true, same: true });
      expect(guards.gapText).toContain('独立上下文'); expect(guards.gapText).toContain('exec_command'); expect(guards.gapText).toContain('未知 2 次'); expect(guards.gapText).toContain('其他/未确认口径 3 次');
      expect(guards.gapText).toContain('执行器观测'); expect(guards.gapText).not.toContain('executor_reported');
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    }
  });
});

async function withLowFanoutNormal(request, read) {
  const fs = require('fs'), path = require('path'), { spawn } = require('child_process');
  const { runTmpRoot } = require('./runtime-paths'), { copyDistribution, resolveJavaEnvironment } = require('./start-java-fixture-server');
  fs.mkdirSync(runTmpRoot, { recursive: true }); const directory = fs.mkdtempSync(path.join(runTmpRoot, 'low-fanout-')), home = path.join(directory, 'home'), source = path.join(home, '.codex/sessions/synthetic'); fs.mkdirSync(source, { recursive: true });
  const rootId = 'synthetic-low-fanout', ids = ['synthetic-low-A', 'synthetic-low-B', 'synthetic-low-C'];
  const meta = (id, parent) => ({ type: 'session_meta', payload: { id, source: parent ? { subagent: { thread_spawn: { parent_thread_id: parent } } } : 'cli' } });
  const call = (id, name, args) => ({ type: 'response_item', payload: { type: 'function_call', call_id: id, name, arguments: JSON.stringify(args) } });
  const output = (id, value) => ({ type: 'response_item', payload: { type: 'function_call_output', call_id: id, output: value } });
  const usage = id => ({ type: 'token_usage_record', payload: { response_id: id, usage: { input_tokens: 10, output_tokens: 2 } } });
  const end = (id, ms) => ({ type: 'event_msg', payload: { type: 'exec_command_end', call_id: id, duration: { secs: Math.floor(ms / 1000), nanos: ms % 1000 * 1000000 }, exit_code: 0, status: 'completed' } });
  const spawnRows = (id, target) => [call(id, 'spawn_agent', { message: 'Synthetic task for ' + target }), output(id, { agent_id: target })];
  const action = (id, ms) => [call(id, 'exec_command', { cmd: 'echo SYNTHETIC_NOT_EXECUTED_' + id }), usage(id), output(id, 'Synthetic Result ' + id), end(id, ms)];
  const root = [meta(rootId), ...spawnRows('spawn-A', ids[0]), ...spawnRows('spawn-B', ids[1]), usage('root-spawns'), ...action('root-short', 500), call('parent-wait', 'wait_agent', { targets: [ids[0]] }), usage('wait'), output('parent-wait', { status: { [ids[0]]: { completed: 'Report, not whole task completion' } } }), end('parent-wait', 2000)];
  const a = [meta(ids[0], rootId), ...spawnRows('spawn-C', ids[2]), usage('A-spawn')]; for (let n = 0; n < 23; n++) a.push(...action('A-' + n, 500));
  const raws = [[rootId, root], [ids[0], a], [ids[1], [meta(ids[1], rootId), ...action('B-long', 35000)]], [ids[2], [meta(ids[2], ids[0]), ...action('C-medium', 3000)]]];
  for (const [id, rows] of raws) fs.writeFileSync(path.join(source, 'rollout-' + id + '.jsonl'), rows.map(JSON.stringify).join('\n') + '\n');
  fs.writeFileSync(path.join(home, '.codex/session_index.jsonl'), raws.map(([id]) => JSON.stringify({ id, thread_name: 'Synthetic low fanout ' + id })).join('\n') + '\n');
  const child = spawn(copyDistribution(directory), ['serve', '--host', '127.0.0.1', '--port', '0'], { env: { ...process.env, ...resolveJavaEnvironment(), HOME: home, INDEX_DIR: path.join(directory, 'index'), JAVA_OPTS: `"-Duser.home=${home}"`, APP_CLI_OPTS: '', JAVA_TOOL_OPTIONS: '', JDK_JAVA_OPTIONS: '', _JAVA_OPTIONS: '', SESSION_BROWSER_LOG_LEVEL: 'INFO' }, stdio: ['ignore', 'pipe', 'pipe'] }); let logs = '';
  try {
    const base = await new Promise((resolve, reject) => {
      child.once('error', reject); child.once('exit', code => reject(new Error('early ' + code + logs)));
      for (const stream of [child.stdout, child.stderr]) stream.on('data', data => { logs += data; const ready = logs.match(/serve 已就绪: (http:\/\/127\.0\.0\.1:\d+)/); if (/后台扫描失败结果:|启动扫描失败|后台扫描获取锁失败|(?:warm|hot) 层级扫描失败/.test(logs)) reject(new Error(logs)); else if (ready && /后台扫描完成: tier=full window=all updated=\d+ perSource=/.test(logs)) resolve(ready[1]); });
    });
    const api = base + '/api/sessions/codex/' + rootId; expect((await request.get(api + '/execution')).status()).toBe(200); const data = await (await request.get(api + '/execution')).json();
    expect(data.diagnostics).toMatchObject({ totalTools: 30, measuredTools: 27, workloadGroups: 5 }); expect(data.diagnostics.workloads).toHaveLength(5);
    expect(data.diagnostics.workloadSignals.candidates.map(x => x.measuredWorkNanos)).toEqual(['35000000000', '11500000000', '3000000000']);
    await read({ base, rootId, ids, api, data, raws });
  } finally { if (child.exitCode === null && child.signalCode === null) { child.kill('SIGTERM'); await new Promise(resolve => child.once('exit', resolve)); } fs.writeFileSync(path.join(directory, 'service.log'), logs); }
}

for (const width of [1440, 390]) {
  test('loaded exchange delegation source follows the selected agent ' + width, async ({ page, request }) => {
    await withLowFanoutNormal(request, async ({ base, rootId, ids }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.goto(base + '/sessions/codex/' + rootId);
      const key = 'subagent:' + ids[1], collaboration = page.locator('[data-collaboration]');
      await page.locator('[data-execution-long-operation]').first().getByRole('button', { name: '查看任务与往来', exact: true }).click();
      await expect(collaboration.locator('[data-collaboration-context]')).toBeFocused();
      const relation = collaboration.locator('[data-collaboration-source-confirmed="true"]');
      await expect(relation).toHaveCount(1);
      const tuple = await relation.getAttribute('data-collaboration-source');
      expect(JSON.parse(tuple)).toEqual([key, 'main', 'token_usage_record:root-spawns', 'spawn-B']);
      await relation.locator('[data-collaboration-evidence] > summary').click();
      const original = await relation.elementHandle();
      await relation.locator('[data-collaboration-agent]').click();
      const judgment = page.locator('[data-execution-judgment]');
      await expect(judgment).toBeFocused(); await expect(judgment).toContainText('35s');
      const bridge = judgment.locator('[data-execution-delegation-sources]');
      await expect(bridge).toHaveAttribute('data-execution-delegation-sources', key);
      await expect(bridge).toContainText('已加载委派来源 1 条');
      await expect(bridge.locator('button')).toHaveCount(1);
      await expect(bridge.locator('button')).toHaveAttribute('data-execution-delegation-source', tuple);
      const requests = [], observe = r => { if (new URL(r.url()).pathname.startsWith('/api/')) requests.push(r.url()); };
      await page.waitForLoadState('networkidle'); page.on('request', observe);
      await bridge.locator('button').focus(); await page.keyboard.press('Enter');
      expect(await original.evaluate(node => node === document.activeElement && node.isConnected)).toBe(true);
      await expect(relation.locator('[data-collaboration-evidence]')).toHaveAttribute('open');
      page.off('request', observe); expect(requests).toEqual([]);
      await judgment.scrollIntoViewIfNeeded();
      await captureDiagnosticScreenshot(page, { path: test.info().outputPath('loaded-exchange-source-' + width + '.png') });
      await collaboration.locator('[data-collaboration-participants]').click();
      await expect(bridge).toContainText('当前视图不提供'); await expect(bridge.locator('button')).toHaveCount(0);
      await collaboration.locator('[data-collaboration-all-exchanges]').click();
      await expect(bridge).toContainText('已加载委派来源 1 条');
      await expect(bridge.locator('button')).toHaveAttribute('data-execution-delegation-source', tuple);
      await expect(page.locator('[data-execution-tool]')).toHaveCount(1);
      await expect(page.locator('[data-execution-tool]')).toContainText('35s');
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    });
  });
}

test('少量多Agent重点 real normal keeps other measured family and exact sources', async ({ page, request }) => {
  await withLowFanoutNormal(request, async ({ base, rootId, ids, data, raws }) => {
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: 900 }); await page.goto(base + '/sessions/codex/' + rootId);
      const section = page.locator('[data-execution-long-operations]'), detail = page.locator('[data-execution-workload-details]');
      await expect(section).toBeVisible(); await expect(section).toContainText('已测累计 35s'); await expect(section).toContainText('已测累计 11.5s'); await expect(section).toContainText('已测累计 3s');
      await expect(detail).not.toHaveAttribute('open', ''); await expect(detail.locator(':scope > summary')).toHaveText('上下文计量明细 · 已载 5/5 组（非排名）');
      const secondary = page.locator('[data-execution-secondary-work]'); await expect(secondary).toContainText('主会话'); await expect(secondary).toContainText('wait_agent · 已测累计 2s'); await expect(secondary).toContainText('已测 1/1 次');
      await expect(page.locator('[data-execution-judgment] > .se-basis').last()).toContainText('已测工具 27 / 30');
      const requests = []; page.on('request', r => requests.push(r.url())); await detail.locator(':scope > summary').click(); await expect(detail.locator('[data-execution-workload]')).toHaveCount(5); expect(requests).toEqual([]);
      const source = detail.locator('[data-execution-delegation-sources="subagent:' + ids[1] + '"] button'); await expect(source).toHaveCount(1); const tuple = JSON.parse(await source.getAttribute('data-execution-delegation-source')); expect(tuple[0]).toBe('subagent:' + ids[1]); expect(tuple[1]).toBe('main'); expect(tuple[3]).toBe('spawn-B'); await source.focus(); await page.keyboard.press('Enter'); const target = page.locator('[data-collaboration-source]').filter({ has: page.locator('[data-collaboration-agent="subagent:' + ids[1] + '"]') }); await expect(target).toBeFocused();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    }
    // UI-only qualification/family guards on a real native page, not parser facts.
    const guard = await page.evaluate(original => {
      const diag = original.diagnostics, cumulative = diag.workloadSignals, single = diag.longOperations;
      function render(extra, agent = '') { executionView.agent = agent; applyExecutionPage({ ...original, diagnostics: { ...diag, ...extra } }); return { signal: !!document.querySelector('[data-execution-long-operations]'), detail: !!document.querySelector('[data-execution-workload-details]') }; }
      const same = render({ workloadSignals: { ...cumulative, candidates: cumulative.candidates.map(x => ({ ...x, scope: 'main', subagentId: null })) }, longOperations: { ...single, candidates: single.candidates.map(x => ({ ...x, tool: { ...x.tool, scope: 'main', subagentId: null } })) } });
      const oneContext = render({ workloads: diag.workloads.map(x => ({ ...x, scope: 'main', subagentId: null })) });
      const selected = render({}, 'subagent:synthetic-low-B'), failed = render({ failures: 1 });
      const unknown = render({ workloads: [{ ...diag.workloads[0], scope: 'subagent', subagentId: null }, ...diag.workloads.slice(1)] });
      const noCandidate = render({ workloadSignals: { ...cumulative, candidates: [] }, longOperations: { ...single, candidates: [] } });
      const noTime = render({ measuredTools: 0, workloads: [], workloadSignals: { ...cumulative, candidates: [] }, longOperations: { ...single, candidates: [] } });
      const secondaryWorks = diag.workloads.map(work => work.name === 'wait_agent' ? { ...work, measuredWorkNanos: '100000000000', unknownTools: 2, otherKindTools: 3 } : work.scope === 'main' ? { ...work, kind: 'ui-other-clock' } : work);
      render({ workloads: secondaryWorks });
      const secondary = Array.from(document.querySelectorAll('[data-execution-secondary-work]')).map(n => n.textContent);
      const gaps = document.querySelector('[data-execution-workload-gaps]')?.textContent || '';
      render({}); const detail = document.querySelector('[data-execution-workload-details]'); detail.open = true;
      const button = detail.querySelector('[data-execution-locate]'); button.focus(); applyExecutionPage(original, true);
      document.querySelector('[data-execution-signal-metric="single"]').click(); syncExecutionContextLabels(); syncExecutionDelegationSources();
      return { same, oneContext, selected, failed, unknown, noCandidate, noTime, secondary, gaps, stable: detail === document.querySelector('[data-execution-workload-details]') && detail.open && document.activeElement === button };
    }, data);
    for (const key of ['same', 'oneContext', 'selected', 'failed', 'unknown', 'noCandidate', 'noTime']) expect(guard[key]).toEqual({ signal: false, detail: false });
    expect(guard.secondary).toHaveLength(2); expect(guard.secondary.join(' ')).toContain('wait_agent · 已测累计 100s'); expect(guard.secondary.join(' ')).toContain('未知 2 次'); expect(guard.secondary.join(' ')).toContain('其他/未确认口径 3 次'); expect(guard.secondary.join(' ')).toContain('其他计时口径，单独累计'); expect(guard.gaps).not.toContain('未知 2 次'); expect(guard.stable).toBe(true);
    await test.info().attach('low-normal-source-api.json', { body: JSON.stringify({ raws, data }), contentType: 'application/json' });
  });
});

// Namespaced Codex input facts enter the real normal scanner/import parser, never a DTO route.
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

async function withFollowupNormal(read) {
  const fs = require('fs'), path = require('path'), { spawn } = require('child_process');
  const { runTmpRoot } = require('./runtime-paths'), { copyDistribution, resolveJavaEnvironment } = require('./start-java-fixture-server');
  fs.mkdirSync(runTmpRoot, { recursive: true }); const directory = fs.mkdtempSync(path.join(runTmpRoot, 'followup-')), home = path.join(directory, 'home'), source = path.join(home, '.codex/sessions/synthetic'); fs.mkdirSync(source, { recursive: true });
  const fixture = followupSource();
  for (const [id, records] of [[fixture.rootId, fixture.root], [fixture.ids[0], fixture.child]]) fs.writeFileSync(path.join(source, 'rollout-' + id + '.jsonl'), records.map(JSON.stringify).join('\n') + '\n');
  fs.writeFileSync(path.join(home, '.codex/session_index.jsonl'), [fixture.rootId, fixture.ids[0]].map(id => JSON.stringify({ id, thread_name: 'Synthetic followup ' + id })).join('\n') + '\n');
  const child = spawn(copyDistribution(directory), ['serve', '--host', '127.0.0.1', '--port', '0'], { env: { ...process.env, ...resolveJavaEnvironment(), HOME: home, INDEX_DIR: path.join(directory, 'index'), JAVA_OPTS: `"-Duser.home=${home}"`, APP_CLI_OPTS: '', JAVA_TOOL_OPTIONS: '', JDK_JAVA_OPTIONS: '', _JAVA_OPTIONS: '', SESSION_BROWSER_LOG_LEVEL: 'INFO' }, stdio: ['ignore', 'pipe', 'pipe'] }); let logs = '';
  try {
    const base = await new Promise((resolve, reject) => {
      child.once('error', reject); child.once('exit', code => reject(new Error('early ' + code + logs)));
      for (const stream of [child.stdout, child.stderr]) stream.on('data', data => { logs += data; const ready = logs.match(/serve 已就绪: (http:\/\/127\.0\.0\.1:\d+)/); if (/后台扫描失败结果:|启动扫描失败|后台扫描获取锁失败|(?:warm|hot) 层级扫描失败/.test(logs)) reject(new Error(logs)); else if (ready && /后台扫描完成: tier=full window=all updated=\d+ perSource=/.test(logs)) resolve(ready[1]); });
    });
    await test.info().attach('followup-normal-raw.json', { body: JSON.stringify(fixture), contentType: 'application/json' });
    await read({ base, fixture, directory });
  } finally { if (child.exitCode === null && child.signalCode === null) { child.kill('SIGTERM'); await new Promise(resolve => child.once('exit', resolve)); } fs.writeFileSync(path.join(directory, 'service.log'), logs); await test.info().attach('followup-service.log', { body: logs, contentType: 'text/plain' }); }
}

async function checkFollowupPage(page, request, url, api, width, included) {
  const facts = await (await request.get(api + '/collaboration?view=exchanges')).json();
  expect(facts.inputDeclarationTotal).toBe(3); expect(facts.items.every(row => row.kind !== 'input')).toBe(true);
  await test.info().attach('followup-first-page.json', { body: JSON.stringify(facts), contentType: 'application/json' });
  const full = await (await request.get(api + '/collaboration?view=exchanges&limit=100')).json();
  expect(full.inputDeclarationTotal).toBe(3); expect(full.items.filter(row => row.kind === 'input')).toHaveLength(6);
  expect(full.items.filter(row => row.kind === 'input' && row.phase === 'result_report').map(row => row.reportedStatus)).toEqual(['queued', 'queued', '']);
  await test.info().attach('followup-full-api.json', { body: JSON.stringify(full), contentType: 'application/json' });
  const execution = await (await request.get(api + '/execution?limit=100')).json();
  expect(execution.items.find(row => row.tool?.toolCallId === 'create-0').tool.inputPreview).toBe('委派任务：Initial synthetic task 0');
  expect(execution.items.find(row => row.tool?.toolCallId === 'follow-message').tool.inputPreview).toBe('追加输入：Synthetic followup <b>message</b>');
  expect(execution.items.find(row => row.tool?.toolCallId === 'follow-items').tool.inputPreview).toBe('追加输入：Synthetic items followup');
  expect(execution.items.find(row => row.tool?.toolCallId === 'follow-unknown').tool.inputPreview).toContain('image');
  const errors = []; page.on('pageerror', error => errors.push(error.message));
  await page.setViewportSize({ width, height: 900 }); const payloads = []; page.on('request', r => { if (r.url().includes('/payload/')) payloads.push(r.url()); });
  await page.goto(url); const host = page.locator('[data-collaboration]'), all = host.locator('[data-collaboration-all-exchanges]');
  await expect(all).toHaveText('全部协作往来（含追加输入声明3条）'); expect(payloads).toEqual([]);
  await captureDiagnosticScreenshot(page, { path: test.info().outputPath('followup-default-' + width + '.png'), fullPage: true });
  await captureDiagnosticScreenshot(host, { path: test.info().outputPath('followup-default-panel-' + width + '.png') });
  await all.click(); await expect(host.locator('[data-collaboration-relation]')).toHaveCount(20);
  await host.locator('[data-collaboration-pagination] button').click();
  const message = host.locator('[data-collaboration-relation]').filter({ hasText: '追加内容：Synthetic followup <b>message</b>' });
  await expect(message).toHaveCount(1); await expect(message.locator('h3')).toContainText('追加输入'); await expect(message.locator('b')).toHaveCount(0);
  const items = host.locator('[data-collaboration-relation]').filter({ hasText: '追加内容：Synthetic items followup' }); await expect(items).toHaveCount(1);
  const receipt = host.locator('[data-collaboration-relation]').filter({ hasText: '工具报告已排队接受' }); await expect(receipt).toHaveCount(2);
  await expect(receipt.locator('[data-collaboration-creation-evidence]')).toHaveCount(0);
  await expect(host.locator('[data-collaboration-relation]').filter({ hasText: '工具报告提交错误' })).toHaveCount(1);
  await expect(message.locator('[data-collaboration-agent]')).toHaveCount(included ? 1 : 0);
  const unknown = host.locator('[data-collaboration-relation]').filter({ hasText: '追加内容摘要未安全解析' }); await expect(unknown).toHaveCount(1);
  await expect(unknown.locator('[data-collaboration-agent], [data-collaboration-branch], [data-collaboration-exchanges]')).toHaveCount(0);
  await expect(all).toHaveText('全部协作往来（含追加输入声明3条）'); expect(payloads).toEqual([]);
  await message.locator('summary').click(); const input = message.getByRole('button', { name: '追加输入 Input', exact: true }); await input.click();
  const modal = page.locator('dialog.payload-modal'); await expect(modal).toContainText('Synthetic followup <b>message</b>'); await expect(modal).toContainText('interrupt'); await page.keyboard.press('Escape');
  await assertRecordedResult(page, request, api, input, JSON.stringify({ target: '11111111-1111-4111-8111-000000000001', message: 'Synthetic followup <b>message</b>', interrupt: true }));
  const locate = message.getByRole('button', { name: '定位发起工具', exact: true }); await locate.focus(); await page.keyboard.press('Enter'); await expect(page.locator('[data-execution-tool]:focus')).toHaveCount(1);
  await expect(page.locator('[data-execution-tool]:focus .se-action__main code')).toHaveText('追加输入：Synthetic followup <b>message</b>');
  await expect(page.locator('[data-execution-tool]:focus .se-action__main b')).toHaveCount(0);
  await captureDiagnosticScreenshot(page.locator('[data-execution-tool]:focus'), { path: test.info().outputPath('followup-focused-operation-' + width + '.png') });
  const firstReceipt = receipt.first(); await assertRecordedResult(page, request, api, firstReceipt.getByRole('button', { name: '提交回执 Result', exact: true, includeHidden: true }), JSON.stringify({ submission_id: 'synthetic-submission-message' }));
  await captureDiagnosticScreenshot(page, { path: test.info().outputPath('followup-exchanges-' + width + '.png'), fullPage: true });
  await captureDiagnosticScreenshot(message, { path: test.info().outputPath('followup-message-' + width + '.png') });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await host.locator('[data-collaboration-participants]').click(); await expect(host.locator('[data-collaboration-all-exchanges]')).toHaveText('全部协作往来（含追加输入声明3条）');
  await host.locator('[data-collaboration-exchanges]').first().click(); await expect(host.locator('[data-collaboration-all-exchanges]')).toHaveText('全部协作往来（含追加输入声明3条）');
  expect(errors).toEqual([]);
}

for (const width of [1440, 390]) {
  test('followup collaboration normal ' + width, async ({ page, request }) => {
    await withFollowupNormal(async ({ base, fixture }) => {
      await checkFollowupPage(page, request, base + '/sessions/codex/' + fixture.rootId, base + '/api/sessions/codex/' + fixture.rootId, width, true);
    });
  });
  test('followup collaboration import ' + width, async ({ page, request, baseURL }) => {
    const fixture = followupSource(), imported = await upload(request, baseURL, 'codex', fixture.root), api = '/api/imports/' + imported.import_id;
    try { await checkFollowupPage(page, request, imported.detail_url, api, width, false); }
    finally { expect((await request.delete(api, { headers: { Origin: new URL(baseURL).origin } })).status()).toBe(204); }
  });
}

test('followup collaboration input-only and neutral consumer guard', async ({ page, request, baseURL }) => {
  const fixture = followupSource(true), imported = await upload(request, baseURL, 'codex', fixture.root), api = '/api/imports/' + imported.import_id;
  try {
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: 900 }); await page.goto(imported.detail_url);
      const host = page.locator('[data-collaboration]'); await expect(host).toContainText('未记录创建委派；已记录的追加输入请从全部协作往来查看');
      await expect(host.getByText('明确操作目标：3', { exact: true })).toHaveCount(1);
      await expect(host).not.toContainText('明确等待目标');
      await host.locator('[data-collaboration-all-exchanges]').click(); await expect(host.locator('[data-collaboration-relation]')).toHaveCount(6);
      await expect(host.locator('[data-collaboration-agent], [data-collaboration-branch], [data-collaboration-exchanges]')).toHaveCount(0);
      await captureDiagnosticScreenshot(page, { path: test.info().outputPath('followup-only-' + width + '.png'), fullPage: true });
      // UI-only unknown protocol kind guard, not parser evidence.
      const neutral = await page.evaluate(() => { const row = { ...collaborationView.page.items[0], kind: 'future_kind', phase: 'declaration' }; return { declaration: collaborationRelation(row, false), report: collaborationRelation({ ...row, phase: 'result_report' }, false), inputUnknown: collaborationRelation({ ...row, kind: 'input', phase: 'result_report', reportedStatus: '', reason: 'report_status_unknown' }, false) }; });
      expect(neutral.declaration).toContain('协作操作'); expect(neutral.declaration).not.toContain('等待 →');
      expect(neutral.report).toContain('协作工具本次报告'); expect(neutral.report).not.toContain('等待工具本次目标报告');
      expect(neutral.inputUnknown).toContain('提交状态未确认'); expect(neutral.inputUnknown).not.toContain('工具报告已排队接受');
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    }
  } finally { expect((await request.delete(api, { headers: { Origin: new URL(baseURL).origin } })).status()).toBe(204); }
});

for (const family of ['main', 'fanout']) for (const width of [1440, 390]) {
  test('measurement copy real normal ' + family + ' ' + width, async ({ page, request, readLongOperationNormal }) => {
    const run = async ({ base, rootId, data }) => {
      await page.setViewportSize({ width, height: 900 }); const requests = [], errors = []; page.on('request', r => requests.push(r.url())); page.on('pageerror', e => errors.push(e.message));
      await page.goto(base + '/sessions/codex/' + rootId); const d = page.locator('[data-execution-judgment]'), signal = d.locator('[data-execution-long-operations]'), detail = d.locator('[data-execution-workload-details]'); await expect(signal).toBeVisible();
      expect(requests.filter(u => u.includes('/payload/'))).toEqual([]);
      const readings = [];
      for (const metric of ['cumulative', 'single']) {
        const button = signal.locator('[data-execution-signal-metric="' + metric + '"]'), count = requests.length;
        await button.focus(); await page.keyboard.press('Enter'); await expect(button).toBeFocused(); expect(requests).toHaveLength(count);
        const text = await d.innerText(), preface = signal.locator('[data-execution-signal-content] > p').first();
        await expect(preface).toContainText('非任务用时、效率、墙钟或关键路径');
        if (metric === 'cumulative') { await expect(preface).toContainText('仅比较已测部分'); await expect(preface).toContainText('未测记录可能改变累计高低'); for (const time of family === 'main' ? ['35s', '11.5s', '3s'] : ['100s', '35s', '12s']) await expect(signal).toContainText('已测累计 ' + time); }
        else { await expect(preface).toContainText('同类执行器'); await expect(preface).toContainText('非累计'); for (const time of ['35s', '500ms']) await expect(signal).toContainText('单次 ' + time); if (family === 'fanout') await expect(signal).toContainText('单次 750ms'); }
        const footer = d.locator(':scope > .se-basis').last(); await expect(footer).toContainText('已测工具 ' + data.diagnostics.measuredTools + ' / ' + data.diagnostics.totalTools); await expect(footer).toContainText('未参与可信累计比较'); await expect(footer).toContainText('模型耗时未测量'); await expect(footer).toContainText('— 未知，不是零'); await expect(footer).toContainText('工具返回不证明整个任务完成'); readings.push({ metric, text, preface: await preface.innerText(), footer: await footer.innerText() });
        await expect(d).toContainText('未观察到工具失败；不证明任务成功或记录完整'); await expect(d.locator('.se-source-note')).toContainText('不代表唯一父级');
        await expect(d.locator('[data-execution-secondary-work]')).toContainText('wait_agent · 已测累计 2s');
        await captureDiagnosticScreenshot(d, { path: test.info().outputPath('measurement-' + family + '-' + metric + '-' + width + '.png') });
      }
      await test.info().attach('measurement-copy-readings.json', { body: JSON.stringify(readings), contentType: 'application/json' });
      for (const reading of readings) { expect(reading.text.match(/非完整瓶颈/g) || []).toHaveLength(1); expect(reading.text.match(/慢不等于异常/g) || []).toHaveLength(1); expect(reading.preface).toContain('非完整瓶颈'); if (reading.metric === 'single') expect(reading.preface).toContain('仅已测'); expect(reading.footer).not.toContain('累计非墙钟'); }
      const same = await page.evaluate(original => { const detail = document.querySelector('[data-execution-workload-details]'); detail.open = true; const button = document.querySelector('[data-execution-signal-metric="single"]'); button.focus(); applyExecutionPage(original, true); syncExecutionContextLabels(); syncExecutionDelegationSources(); return detail === document.querySelector('[data-execution-workload-details]') && detail.open && document.activeElement === button; }, data); expect(same).toBe(true);
      // UI-only branch guards on real source data; not parser evidence.
      const guards = await page.evaluate(original => { const diag = original.diagnostics; function read(extra, agent = '') { executionView.agent = agent; applyExecutionPage({ ...original, diagnostics: { ...diag, ...extra } }); return { top: !!document.querySelector('[data-execution-shared-work-basis]'), bottom: document.querySelector('[data-execution-judgment]').innerText.includes('累计非墙钟或关键路径'), disclosure: !!document.querySelector('[data-execution-workload-details]') }; }
        return { selected: read({}, 'subagent:synthetic-guard'), absent: read({ longOperations: { ...diag.longOperations, candidates: [] }, workloadSignals: { ...diag.workloadSignals, candidates: [] } }), unknown: read({ workloads: [{ ...diag.workloads[0], scope: 'subagent', subagentId: null }, ...diag.workloads.slice(1)] }), single: read({ workloads: [diag.workloads[0]], workloadGroups: 1 }), failure: read({ failures: 1 }) }; }, data);
      for (const key of ['selected', 'absent', 'unknown']) expect(guards[key]).toEqual({ top: true, bottom: true, disclosure: false }); expect(guards.single).toEqual({ top: false, bottom: true, disclosure: false }); expect(guards.failure.disclosure).toBe(false);
      expect(errors).toEqual([]); expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    };
    if (family === 'main') await withLowFanoutNormal(request, run); else await readLongOperationNormal(request, false, run);
  });
}

const hotspotInput = n => ({ cmd: n < 20 ? 'synthetic-alpha' : 'synthetic-beta' });
for (const width of [1440, 390]) test('same input hotspot real normal child08 ' + width, async ({ page, request, readLongOperationNormal }) => {
  await readLongOperationNormal(request, false, async ({ base, rootId, data, api }) => {
    const candidate = data.diagnostics.workloadSignals.candidates[0];
    expect(candidate.sameInputMaximum).toMatchObject({ measuredWorkNanos: '90000000000', totalTools: 180, measuredTools: 180, unknownTools: 0, otherKindTools: 0, distinctInputs: 2, identifiedInputs: 200, totalInputs: 200, tool: { inputPreview: 'synthetic-beta', subagentId: 'synthetic-long-child-08' } });
    expect(candidate.longest.tool.inputPreview).toBe('synthetic-alpha'); expect(candidate.longest.durationNanos).toBe('500000000');
    await test.info().attach('same-input-native-api.json', { body: JSON.stringify(data), contentType: 'application/json' });
    await page.setViewportSize({ width, height: 900 }); const requests = [], errors = []; page.on('request', r => requests.push(r.url())); page.on('pageerror', e => errors.push(e.message));
    await page.goto(base + '/sessions/codex/' + rootId); const d = page.locator('[data-execution-judgment]'), section = d.locator('[data-execution-long-operations]'), row = section.locator('[data-execution-long-operation]').filter({ hasText: '已测累计 100s' });
    const hotspot = row.locator('[data-execution-same-input]'); await expect(hotspot).toContainText('其中已测 90s'); await expect(hotspot).toContainText('已测 180/180 次'); await expect(hotspot).toContainText('本组 2 种参数记录'); await expect(hotspot).toContainText('synthetic-beta'); await expect(row.locator('.se-representative')).toContainText('synthetic-alpha'); await expect(row.getByRole('button', { name: '定位代表调用', exact: true })).toHaveAttribute('data-execution-locate', 'long-check-08-0');
    await expect(section).toContainText('单次最大值 35s'); expect(requests.filter(u => u.includes('/payload/'))).toEqual([]); await captureDiagnosticScreenshot(d, { path: test.info().outputPath('hotspot-default-' + width + '.png') });
    const count = requests.length; await section.getByRole('button', { name: '单次耗时', exact: true }).click(); await expect(section.locator('[data-execution-same-input]')).toHaveCount(0); await expect(section).toContainText('单次 35s'); await section.getByRole('button', { name: '已测累计', exact: true }).click(); expect(requests).toHaveLength(count); await expect(hotspot).toBeVisible();
    await row.getByRole('button', { name: '查看任务与往来', exact: true }).click(); const relation = page.locator('[data-collaboration-relation]'); await expect(relation).toHaveCount(1); const tuple = JSON.parse(await relation.getAttribute('data-collaboration-source')); expect(tuple).toEqual(['subagent:synthetic-long-child-08', 'main', 'token_usage_record:long-delegations', 'long-spawn-7']);
    const entry = relation.getByRole('button', { name: /过程与耗时/ }); await entry.click(); await expect(d).toBeFocused(); const selected = d.locator('[data-execution-workload]').filter({ hasText: '已测累计 100s' }); await expect(selected.locator('[data-execution-same-input]')).toContainText('其中已测 90s'); await expect(selected.locator('.se-representative')).toContainText('synthetic-alpha');
    await d.locator('.se-measurement > summary').click(); await expect(d.locator('.se-measurement')).toContainText('输入识别 200/200'); await expect(d.locator('.se-measurement')).toContainText('不证明业务操作或环境相同'); await d.locator('.se-measurement > summary').click();
    const old = await selected.locator('[data-execution-same-input]').elementHandle(); await expect(page.locator('[data-execution-pagination]')).toContainText('1–20 / 200'); await page.locator('[data-execution-pagination] button').click(); await expect(page.locator('[data-execution-pagination]')).toContainText('1–40 / 200'); expect(await old.evaluate(n => n.isConnected)).toBe(true); await expect(selected.locator('[data-execution-same-input]')).toContainText('已测 180/180 次');
    await captureDiagnosticScreenshot(d, { path: test.info().outputPath('hotspot-selected-' + width + '.png') });
    const tool = page.locator('[data-execution-tool="long-check-08-0"]'); await assertRecordedResult(page, request, api, tool.getByRole('button', { name: '命令或参数', exact: true, includeHidden: true }), JSON.stringify(hotspotInput(0))); await assertRecordedResult(page, request, api, tool.getByRole('button', { name: '执行结果', exact: true, includeHidden: true }), 'Synthetic complete Result long-check-08-0');
    await page.getByRole('button', { name: '返回协作位置', exact: true }).click(); await expect(entry).toBeFocused(); expect(errors).toEqual([]); expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }, hotspotInput);
});

function hotspotImportSource(partial = false, input = hotspotInput) {
  // Explicit main source is deliberately not the parent-dependent normal child source.
  const call = (i, args) => ({ type: 'response_item', payload: { type: 'function_call', call_id: 'hotspot-' + i, name: 'exec_command', arguments: JSON.stringify(args) } });
  const rows = [{ type: 'session_meta', payload: { id: 'synthetic-hotspot-main', source: 'cli' } }];
  for (let i = 0; i < 200; i++) rows.push(call(i, input(i)), { type: 'token_usage_record', payload: { response_id: 'hotspot-' + i, usage: { input_tokens: 1, output_tokens: 1 } } }, { type: 'response_item', payload: { type: 'function_call_output', call_id: 'hotspot-' + i, output: 'Synthetic hotspot result ' + i } }, { type: 'event_msg', payload: { type: 'exec_command_end', call_id: 'hotspot-' + i, exit_code: 0, status: 'completed', ...(!partial || i !== 199 ? { duration: { secs: 0, nanos: 500000000 } } : {}) } });
  return rows;
}

async function assertHotspotResponse(page, request, api, tool, target, preview, width) {
  const response = await request.get(api + '/execution?target=' + encodeURIComponent(target)); expect(response.status()).toBe(200);
  const data = await response.json(), item = data.items.find(item => item.tool?.toolCallId === target);
  expect(item.tool).toMatchObject({ scope: 'main', subagentId: '' }); expect(item.group.toolCount).toBe(1); expect(data.total).toBe(200);
  const group = tool.locator('xpath=ancestor::*[@data-execution-group][1]'); await expect(group.locator('[data-execution-tool]')).toHaveCount(1);
  await expect(group.locator('header > h3')).toContainText('模型响应记录');
  await group.locator('[data-execution-response-actions]').getByRole('button', { name: '模型输出', exact: true }).click();
  const modal = page.locator('dialog.payload-modal'); await expect(modal).toBeVisible(); await expect(modal).toContainText(preview); await expect(modal).toContainText(target);
  await expect(modal.locator('.sd-payload-tool-link')).toHaveCount(1); await expect(modal.locator('.sd-payload-tool-link')).toBeVisible(); await expect(modal.locator('.sd-payload-tool-link')).toContainText(preview);
  await captureDiagnosticScreenshot(modal, { path: test.info().outputPath('hotspot-sample-response-' + width + '.png') });
  await test.info().attach('sample-response.txt', { body: await modal.innerText(), contentType: 'text/plain' }); await page.keyboard.press('Escape');
}

for (const partial of [false, true]) for (const width of [1440, 390]) test('same input hotspot real import ' + (partial ? 'partial' : 'full') + ' ' + width, async ({ page, request, baseURL }) => {
  const rows = hotspotImportSource(partial);
  const imported = await upload(request, baseURL, 'codex', rows), api = '/api/imports/' + imported.import_id;
  try {
    const raw = Buffer.from(rows.map(JSON.stringify).join('\n') + '\n');
    await test.info().attach('hotspot-source.jsonl', { body: raw, contentType: 'application/x-ndjson' });
    await test.info().attach('hotspot-source-sha256.txt', { body: require('crypto').createHash('sha256').update(raw).digest('hex'), contentType: 'text/plain' });
    const response = await request.get(api + '/execution'); expect(response.status()).toBe(200);
    const data = await response.json(), workload = data.diagnostics.workloads[0], max = workload.sameInputMaximum;
    await test.info().attach('hotspot-import-api.json', { body: JSON.stringify(data, null, 2), contentType: 'application/json' });
    expect(data.total).toBe(200); expect(workload).toMatchObject({ measuredWorkNanos: partial ? '99500000000' : '100000000000', measuredTools: partial ? 199 : 200, totalTools: 200 });
    expect(workload.longest.inputPreview).toBe('synthetic-alpha');
    await page.setViewportSize({ width, height: 900 }); await page.goto(imported.detail_url);
    const group = page.locator('[data-execution-workload]');
    await expect(group).toContainText(partial ? '已测累计 99.5s' : '已测累计 100s'); await expect(group).toContainText('synthetic-alpha');
    await captureDiagnosticScreenshot(page.locator('[data-execution-judgment]'), { path: test.info().outputPath('hotspot-import-before-assert-' + width + '.png') });
    expect(max).toMatchObject({ measuredWorkNanos: partial ? '89500000000' : '90000000000', measuredTools: partial ? 179 : 180, totalTools: 180, unknownTools: partial ? 1 : 0, distinctInputs: 2, identifiedInputs: 200, totalInputs: 200, tool: { inputPreview: 'synthetic-beta' } });
    const line = group.locator('[data-execution-same-input]'); await expect(line).toContainText(partial ? '其中已测 89.5s' : '其中已测 90s'); await expect(line).toContainText(partial ? '已测 179/180 次' : '已测 180/180 次'); await expect(line).toContainText('本组 2 种参数记录');
    if (partial) await expect(line).toContainText('缺测 1 次');
    const target = max.tool.toolCallId;
    expect(max.tool.subagentId || '').toBe('');
    const declaration = rows.find(row => row.payload?.type === 'function_call' && row.payload.call_id === target), result = rows.find(row => row.payload?.type === 'function_call_output' && row.payload.call_id === target);
    expect(JSON.parse(declaration.payload.arguments)).toEqual({ cmd: 'synthetic-beta' });
    const sample = line.getByRole('button', { name: '定位此参数的一次调用', exact: true }); await expect(sample).toHaveAttribute('data-execution-locate', target); await sample.click();
    const tool = page.locator('[data-execution-tool="' + target + '"]'); await expect(tool).toBeFocused(); await expect(tool).toContainText('synthetic-beta');
    await assertHotspotResponse(page, request, api, tool, target, 'synthetic-beta', width);
    await assertRecordedResult(page, request, api, tool.getByRole('button', { name: '命令或参数', exact: true, includeHidden: true }), declaration.payload.arguments);
    await assertRecordedResult(page, request, api, tool.getByRole('button', { name: '执行结果', exact: true, includeHidden: true }), result.payload.output);
    const isolated = await request.get(api + '/execution?agent_context=' + encodeURIComponent('subagent:synthetic-long-child-08')); expect(isolated.status()).toBe(200); const empty = await isolated.json(); expect(empty.items).toEqual([]); expect(empty.total).toBe(0); expect(empty.diagnostics.totalTools).toBe(0);

  } finally { expect((await request.delete(api, { headers: { Origin: new URL(baseURL).origin } })).status()).toBe(204); }
});

for (const variant of ['independent-nested', 'secret']) for (const width of [1440, 390]) test('same input hotspot real import guard ' + variant + ' ' + width, async ({ page, request, baseURL }) => {
  const secrets = ['synthetic-private-one', 'synthetic-private-two'];
  const rows = hotspotImportSource(false, variant === 'secret' ? n => ({ cmd: 'synthetic-safe', api_key: secrets[n < 20 ? 0 : 1] }) : hotspotInput);
  if (variant === 'independent-nested') {
    const independent = { type: 'tool_use', id: 'hotspot-0', name: 'exec_command', input: { cmd: 'synthetic-independent' } };
    rows[1].payload.content = [independent, { ...independent }];
  }
  const imported = await upload(request, baseURL, 'codex', rows), api = '/api/imports/' + imported.import_id;
  const paths = [], errors = [], consoleErrors = []; page.on('request', r => paths.push(r.url())); page.on('pageerror', e => errors.push(e.message)); page.on('console', m => { if (m.type() === 'error') consoleErrors.push(m.text()); });
  try {
    const response = await request.get(api + '/execution'); expect(response.status()).toBe(200); const data = await response.json(), workload = data.diagnostics.workloads[0], max = workload.sameInputMaximum;
    expect(data.total).toBe(200); expect(workload).toMatchObject({ totalTools: 200, measuredTools: 200, measuredWorkNanos: '100000000000' });
    expect(workload.longest).toMatchObject({ inputPreview: variant === 'secret' ? 'synthetic-safe' : 'synthetic-alpha', durationMs: 500 });
    await test.info().attach('guard-api.json', { body: JSON.stringify(data, null, 2), contentType: 'application/json' });
    await page.setViewportSize({ width, height: 900 }); await page.goto(imported.detail_url); const group = page.locator('[data-execution-workload]'); await expect(group).toContainText('已测累计 100s');
    expect(paths.filter(url => url.includes('/payload/'))).toEqual([]); expect(paths.filter(url => /\/execution$/.test(url))).toHaveLength(1);
    if (variant === 'independent-nested') {
      expect(max).toBeNull(); await expect(group.locator('[data-execution-same-input]')).toHaveCount(0); await expect(group).toContainText('synthetic-alpha');
      const tool = page.locator('[data-execution-tool="hotspot-0"]');
      await assertHotspotResponse(page, request, api, tool, 'hotspot-0', 'synthetic-alpha', width);
      await assertRecordedResult(page, request, api, tool.getByRole('button', { name: '命令或参数', exact: true, includeHidden: true }), JSON.stringify(hotspotInput(0)));
      await assertRecordedResult(page, request, api, tool.getByRole('button', { name: '执行结果', exact: true, includeHidden: true }), 'Synthetic hotspot result 0');
    } else {
      expect(max).toMatchObject({ measuredWorkNanos: '90000000000', measuredTools: 180, totalTools: 180, distinctInputs: 2, identifiedInputs: 200, totalInputs: 200, tool: { inputPreview: 'synthetic-safe', scope: 'main', subagentId: '' } });
      const line = group.locator('[data-execution-same-input]'); await expect(line).toContainText('其中已测 90s'); await expect(line).toContainText('本组 2 种参数记录');
      const target = max.tool.toolCallId; await line.getByRole('button', { name: '定位此参数的一次调用', exact: true }).click(); const tool = page.locator('[data-execution-tool="' + target + '"]'); await expect(tool).toBeFocused();
      await assertHotspotResponse(page, request, api, tool, target, 'synthetic-safe', width);
      const input = tool.getByRole('button', { name: '命令或参数', exact: true, includeHidden: true }); await openEvidence(input);
      const payloadResponse = await request.get(api + '/payload/' + encodeURIComponent(await input.getAttribute('data-payload-id'))); expect(payloadResponse.status()).toBe(200); const payload = await payloadResponse.json();
      const safe = payload.text || payload.content; expect(safe).toContain('synthetic-safe'); expect(safe).toContain('api_key'); expect(safe).toContain('[REDACTED]');
      await input.click(); await expect(page.locator('dialog.payload-modal')).toContainText('[REDACTED]'); await page.keyboard.press('Escape');
      const exposed = JSON.stringify({ data, payload, errors, consoleErrors }) + await page.locator('body').innerText();
      for (const secret of secrets) { expect(exposed).not.toContain(secret); expect(exposed).not.toContain(require('crypto').createHash('sha256').update(secret).digest('hex')); }
      expect(exposed).not.toContain(process.cwd()); expect(exposed).not.toContain('sameInputFingerprint');
    }
    expect(errors).toEqual([]); expect(consoleErrors).toEqual([]); expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await captureDiagnosticScreenshot(page.locator('[data-execution-judgment]'), { path: test.info().outputPath('hotspot-guard-' + variant + '-' + width + '.png') });
  } finally { expect((await request.delete(api, { headers: { Origin: new URL(baseURL).origin } })).status()).toBe(204); }
});

// 全同和全异参数计数归 SessionExecutionInputsTest；浏览器保留缺值和可见安全边界。
for (const variant of ['missing', 'same-preview', 'secret']) test('same input hotspot qualified normal input shape ' + variant, async ({ page, request }) => {
  let directory;
  const args = n => variant === 'missing' ? (n === 199 ? undefined : hotspotInput(n)) : variant === 'same-preview' ? { cmd: 'synthetic-shared-preview', mode: n < 20 ? 'alpha' : 'beta' } : { cmd: 'synthetic-safe', api_key: n < 20 ? 'synthetic-private-one' : 'synthetic-private-two' };
  await withLongOperationNormal(request, false, async ({ base, rootId, data, directory: runtime }) => {
    directory = runtime; const candidate = data.diagnostics.workloadSignals.candidates.find(x => x.subagentId === 'synthetic-long-child-08'), max = candidate.sameInputMaximum;
    if (variant === 'missing') expect(max).toBeNull();
    else if (variant === 'same-preview') expect(max).toMatchObject({ distinctInputs: 2, measuredWorkNanos: '90000000000', tool: { inputPreview: 'synthetic-shared-preview' } });
    else if (variant === 'secret') expect(max).toMatchObject({ distinctInputs: 2, measuredWorkNanos: '90000000000', measuredTools: 180, tool: { inputPreview: 'synthetic-safe' } });
    await page.goto(base + '/sessions/codex/' + rootId); await expect(page.locator('[data-execution-long-operations]')).toBeVisible(); const row = page.locator('[data-execution-long-operation]').filter({ hasText: '已测累计 100s' }); await expect(row.locator('[data-execution-same-input]')).toHaveCount(max ? 1 : 0); await expect(row.getByRole('button', { name: '定位此参数的一次调用', exact: true })).toHaveCount(max ? 1 : 0);
    const text = JSON.stringify(data) + await page.locator('body').innerText(); expect(text).not.toContain('synthetic-private-one'); expect(text).not.toContain('synthetic-private-two'); expect(text).not.toContain('fingerprint');
    if (variant === 'same-preview') await expect(row.locator('[data-execution-same-input]')).toContainText('本组 2 种参数记录');
    await test.info().attach('normal-input-shape-' + variant + '.json', { body: JSON.stringify({ variant, sameInputMaximum: max, totalTools: candidate.totalTools, measuredWorkNanos: candidate.measuredWorkNanos }), contentType: 'application/json' });
  }, args);
  const log = require('fs').readFileSync(require('path').join(directory, 'service.log'), 'utf8'); expect(log).not.toContain('synthetic-private-one'); expect(log).not.toContain('synthetic-private-two'); expect(log).not.toContain('fingerprint');
});

test('same input hotspot real normal partial keeps unknown coverage', async ({ page, request, readLongOperationNormal }) => {
  await readLongOperationNormal(request, true, async ({ base, rootId, data }) => {
    expect(data.diagnostics.workloadSignals.candidates[0].sameInputMaximum).toMatchObject({ measuredWorkNanos: '89500000000', measuredTools: 179, totalTools: 180, unknownTools: 1, distinctInputs: 2, identifiedInputs: 200, totalInputs: 200 });
    for (const width of [1440, 390]) { await page.setViewportSize({ width, height: 900 }); await page.goto(base + '/sessions/codex/' + rootId); const row = page.locator('[data-execution-long-operation]').filter({ hasText: '已测累计 99.5s' }); await expect(row.locator('[data-execution-same-input]')).toContainText('其中已测 89.5s · 已测 179/180 次 · 缺测 1 次'); await expect(row.locator('.se-representative')).toContainText('synthetic-alpha'); await captureDiagnosticScreenshot(page.locator('[data-execution-judgment]'), { path: test.info().outputPath('hotspot-partial-' + width + '.png') }); }
  }, hotspotInput);
});

for (const width of [1440, 390]) test('same input sample locate real normal across unloaded prefix ' + width, async ({ page, request, readLongOperationNormal }) => {
  await readLongOperationNormal(request, false, async ({ base, rootId, children, raws, api, data }) => {
    const maximum = data.diagnostics.workloadSignals.candidates[0].sameInputMaximum, target = maximum.tool.toolCallId;
    const raw = raws.find(([id]) => id === maximum.tool.subagentId)[1], declaration = raw.find(r => r.payload?.type === 'function_call' && r.payload.call_id === target), result = raw.find(r => r.payload?.type === 'function_call_output' && r.payload.call_id === target);
    expect(maximum.tool.subagentId).toBe(children[7]); expect(JSON.parse(declaration.payload.arguments)).toEqual({ cmd: 'synthetic-beta' });
    await test.info().attach('sample-source-target.json', { body: JSON.stringify({ maximum, declaration, result }), contentType: 'application/json' });
    const requests = [], errors = []; page.on('request', r => requests.push(r.url())); page.on('pageerror', e => errors.push(e.message));
    await page.setViewportSize({ width, height: 900 }); await page.goto(base + '/sessions/codex/' + rootId);
    const d = page.locator('[data-execution-judgment]'), section = d.locator('[data-execution-long-operations]'), row = section.locator('[data-execution-long-operation]').filter({ hasText: '已测累计 100s' }), sample = row.locator('[data-execution-same-input]').getByRole('button', { name: '定位此参数的一次调用', exact: true });
    await expect(sample).toHaveCount(1); await expect(sample).toHaveAttribute('data-execution-locate', target); await expect(sample).not.toHaveAttribute('data-collaboration-agent', /./);
    await expect(row.locator('.se-workload-line').getByRole('button')).toHaveText(['查看上下文过程', '定位代表调用', '查看任务与往来']);
    await expect(row.locator('.se-representative')).toContainText('synthetic-alpha'); await expect(row.getByRole('button', { name: '定位代表调用', exact: true })).toHaveAttribute('data-execution-locate', 'long-check-08-0');
    await expect(page.locator('[data-execution-tool="' + target + '"]')).toHaveCount(0); expect(requests.filter(u => u.includes('/payload/'))).toEqual([]);
    await captureDiagnosticScreenshot(d, { path: test.info().outputPath('sample-default-' + width + '.png') });
    const before = requests.length; await section.getByRole('button', { name: '单次耗时', exact: true }).click(); await expect(section.getByRole('button', { name: '定位此参数的一次调用' })).toHaveCount(0); await section.getByRole('button', { name: '已测累计', exact: true }).click(); expect(requests).toHaveLength(before);
    const node = await d.elementHandle(), start = requests.length; await sample.focus(); await page.keyboard.press('Enter'); const tool = page.locator('[data-execution-tool="' + target + '"]'); await expect(tool).toBeFocused(); await expect(tool).toContainText('synthetic-beta');
    const added = requests.slice(start); expect(added).toHaveLength(1); expect(added[0]).toContain('/execution?'); expect(new URL(added[0]).searchParams.get('target')).toBe(target); expect(new URL(added[0]).searchParams.get('agent_context')).toBe(''); expect(added.some(u => u.includes('/payload/'))).toBe(false);
    expect(await node.evaluate(n => n.isConnected)).toBe(true); await expect(section.getByRole('button', { name: '已测累计', exact: true })).toHaveAttribute('aria-pressed', 'true'); await expect(tool.locator('.se-tool-evidence')).not.toHaveAttribute('open', '');
    await captureDiagnosticScreenshot(tool, { path: test.info().outputPath('sample-tool-' + width + '.png') });
    await assertRecordedResult(page, request, api, tool.getByRole('button', { name: '命令或参数', exact: true, includeHidden: true }), declaration.payload.arguments);
    await assertRecordedResult(page, request, api, tool.getByRole('button', { name: '执行结果', exact: true, includeHidden: true }), result.payload.output);
    await row.getByRole('button', { name: '查看任务与往来', exact: true }).click(); const relation = page.locator('[data-collaboration-relation]'); await expect(relation).toHaveCount(1); expect(JSON.parse(await relation.getAttribute('data-collaboration-source'))).toEqual(['subagent:' + children[7], 'main', 'token_usage_record:long-delegations', 'long-spawn-7']); const entry = relation.getByRole('button', { name: /过程与耗时/ }); await entry.click(); await expect(d).toBeFocused();
    const selected = d.locator('[data-execution-workload]').filter({ hasText: '已测累计 100s' }), selectedSample = selected.getByRole('button', { name: '定位此参数的一次调用', exact: true }); await expect(selectedSample).toHaveCount(1); await captureDiagnosticScreenshot(d, { path: test.info().outputPath('sample-selected-' + width + '.png') });
    const begin = requests.length; await selectedSample.focus(); await page.keyboard.press('Enter'); await expect(tool).toBeFocused(); const selectedRequests = requests.slice(begin); expect(selectedRequests).toHaveLength(1); expect(new URL(selectedRequests[0]).searchParams.get('agent_context')).toBe('subagent:' + children[7]); expect(new URL(selectedRequests[0]).searchParams.get('target')).toBe(target); await expect(d).toContainText('已测累计 100s');
    await page.getByRole('button', { name: '返回协作位置', exact: true }).click(); await expect(entry).toBeFocused(); expect(errors).toEqual([]); expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  }, hotspotInput);
});

// Canonical authority is an explicit test-side bounded directory read, never a page mock.
async function assertHotspotLabelAssets(request, base, directory) {
  const fs = require('fs'), path = require('path'), { execFileSync } = require('child_process'), crypto = require('crypto');
  const jar = path.join(directory, 'app-cli/lib', fs.readdirSync(path.join(directory, 'app-cli/lib')).find(name => /^web-.*\.jar$/.test(name)));
  const proof = [];
  for (const name of ['execution', 'collaboration', 'init']) {
    const asset = 'static/js/session-detail/' + name + '.js', source = fs.readFileSync(path.resolve(__dirname, '../../web/src/main/resources', asset));
    const packaged = execFileSync('/usr/bin/unzip', ['-p', jar, asset]), response = await request.get(base + '/' + asset); expect(response.status()).toBe(200);
    expect(packaged.equals(source)).toBe(true); expect((await response.body()).equals(source)).toBe(true);
    proof.push({ asset, sourceJarHttpEqual: true, sha256: crypto.createHash('sha256').update(source).digest('hex') });
  }
  await test.info().attach('label-assets.json', { body: JSON.stringify(proof), contentType: 'application/json' });
}

for (const variant of ['original', 'non-numeric-shuffled']) for (const width of [1440, 390]) test('hotspot context labels normal ' + variant + ' ' + width, async ({ page, request }) => {
  const identities = variant === 'original' ? undefined : ['worker-zulu', 'worker-copper', 'worker-mint', 'worker-amber', 'worker-willow', 'worker-indigo', 'worker-slate', 'worker-yarrow', 'worker-violet', 'worker-maple'];
  await withLongOperationNormal(request, false, async ({ base, rootId, children, raws, api, data, signals, directory }) => {
    const candidate = data.diagnostics.workloadSignals.candidates[0], single = signals.candidates[0], keys = ['subagent:' + candidate.subagentId, 'subagent:' + single.tool.subagentId];
    expect(candidate).toMatchObject({ subagentId: children[7], measuredWorkNanos: '100000000000', measuredTools: 200, totalTools: 200, longest: { durationNanos: '500000000', tool: { inputPreview: 'synthetic-alpha' } }, sameInputMaximum: { measuredWorkNanos: '90000000000', measuredTools: 180, totalTools: 180, distinctInputs: 2, identifiedInputs: 200, totalInputs: 200 } });
    expect(single).toMatchObject({ durationNanos: '35000000000', tool: { subagentId: children[8] } });
    const authorityResponse = await request.get(api + '/collaboration?view=participants&limit=100'); expect(authorityResponse.status()).toBe(200); const authority = await authorityResponse.json(); expect(authority.items).toHaveLength(11);
    const labels = keys.map(key => authority.items.find(item => item.key === key)); expect(labels.every(Boolean)).toBe(true);
    for (const item of labels) expect(data.contextLabels[item.key]).toBe(item.label);
    expect(Object.keys(data.contextLabels).length).toBeLessThanOrEqual(2 * data.items.length + 69);
    await assertHotspotLabelAssets(request, base, directory);
    const crypto = require('crypto'); await test.info().attach('label-source-shas.json', { body: JSON.stringify(raws.map(([id, rows]) => ({ id, sha256: crypto.createHash('sha256').update(rows.map(JSON.stringify).join('\n') + '\n').digest('hex') }))), contentType: 'application/json' });
    await test.info().attach('label-authority-and-execution.json', { body: JSON.stringify({ variant, keys, labels, authority, execution: data }), contentType: 'application/json' });
    const requests = [], errors = []; page.on('request', r => { if (r.url().includes('/api/')) requests.push(r.url()); }); page.on('pageerror', e => errors.push(e.message));
    await page.setViewportSize({ width, height: 950 });
    const collaborationResponse = page.waitForResponse(r => new URL(r.url()).pathname.endsWith('/collaboration'));
    await page.goto(base + '/sessions/codex/' + rootId); const collaboration = await (await collaborationResponse).json(); await page.waitForFunction(() => collaborationView.sourceStatus === 'ready');
    expect(collaboration.participants).toHaveLength(5); expect(collaboration.items).toHaveLength(5); expect(collaboration.participants.some(item => keys.includes(item.key))).toBe(false);
    const judgment = page.locator('[data-execution-judgment]'), section = judgment.locator('[data-execution-long-operations]'), row = section.locator('[data-execution-long-operation]').filter({ hasText: '已测累计 100s' });
    await expect(row.locator('[data-execution-same-input]')).toContainText('其中已测 90s'); await expect(row).toContainText('已测 180/180 次'); await expect(row.locator('.se-representative')).toContainText('synthetic-alpha'); await expect(section).toContainText('单次最大值 35s');
    const contextRows = [row, section.locator('[data-execution-long-operation]').filter({ hasText: '已测累计 35s' })], readings = [];
    for (let i = 0; i < keys.length; i++) {
      const node = contextRows[i].locator('[data-execution-context-key="' + keys[i] + '"]'); await expect(node).toHaveCount(1); await expect(node).toBeVisible(); await expect(node).toContainText('独立上下文'); readings.push({ key: keys[i], canonical: labels[i].label, visibleText: await node.innerText() });
    }
    expect(requests).toHaveLength(7); expect(requests.some(url => /view=participants|\/payload\/|cursor=/.test(url))).toBe(false); expect(errors).toEqual([]); expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await test.info().attach('label-default-reading.json', { body: JSON.stringify({ readings, requests, collaboration, errors, directory }), contentType: 'application/json' });
    await captureDiagnosticScreenshot(judgment, { path: test.info().outputPath('label-default-' + variant + '-' + width + '.png') });
    for (let i = 0; i < keys.length; i++) { const node = contextRows[i].locator('[data-execution-context-key="' + keys[i] + '"]'); await expect.soft(node).toContainText(labels[i].label); }
  }, hotspotInput, identities);
});

for (const partial of [false, true]) for (const width of [1440, 390]) test('hotspot context labels import control ' + (partial ? 'partial' : 'full') + ' ' + width, async ({ page, request, baseURL }) => {
  const rows = hotspotImportSource(partial), raw = Buffer.from(rows.map(JSON.stringify).join('\n') + '\n'), sha = require('crypto').createHash('sha256').update(raw).digest('hex');
  expect(sha).toBe(partial ? '4e6caaa33b8baf5201e8101fce2f56ecadfbf26561de4a0413d9338ee4601008' : 'edd2a9a7227c8061e7d61e072c4b8abdcf9247c28d3ca706b0771e1a56652b34');
  const imported = await upload(request, baseURL, 'codex', rows), api = '/api/imports/' + imported.import_id;
  try {
    const response = await request.get(api + '/execution'); expect(response.status()).toBe(200); const data = await response.json(), workload = data.diagnostics.workloads[0];
    expect(workload).toMatchObject({ scope: 'main', subagentId: '', measuredWorkNanos: partial ? '99500000000' : '100000000000', measuredTools: partial ? 199 : 200, totalTools: 200, sameInputMaximum: { measuredWorkNanos: partial ? '89500000000' : '90000000000', measuredTools: partial ? 179 : 180, totalTools: 180, unknownTools: partial ? 1 : 0, identifiedInputs: 200, totalInputs: 200 } });
    const requests = [], errors = []; page.on('request', r => { if (r.url().includes('/api/')) requests.push(r.url()); }); page.on('pageerror', e => errors.push(e.message)); await page.setViewportSize({ width, height: 950 });
    const ready = page.waitForResponse(r => new URL(r.url()).pathname.endsWith('/collaboration')); await page.goto(imported.detail_url); await ready; await page.waitForFunction(() => collaborationView.sourceStatus === 'ready');
    const judgment = page.locator('[data-execution-judgment]'), row = judgment.locator('[data-execution-workload]'); await expect(row).toContainText(partial ? '已测累计 99.5s' : '已测累计 100s'); await expect(row.locator('[data-execution-same-input]')).toContainText(partial ? '其中已测 89.5s' : '其中已测 90s'); await expect(judgment).toContainText('主会话');
    await test.info().attach('label-import-default-requests.json', { body: JSON.stringify(requests), contentType: 'application/json' });
    await expect(judgment.locator('[data-execution-context-key^="subagent:"]')).toHaveCount(0); expect(requests.some(url => /view=participants|\/payload\/|cursor=/.test(url))).toBe(false); expect(requests).toHaveLength(6); expect(errors).toEqual([]); expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    const isolated = await (await request.get(api + '/execution?agent_context=' + encodeURIComponent('subagent:synthetic-long-child-08'))).json(); expect(isolated.total).toBe(0); expect(isolated.items).toEqual([]);
    await test.info().attach('label-import-control.json', { body: JSON.stringify({ sourceSha256: sha, execution: data, requests, errors, isolated }), contentType: 'application/json' }); await captureDiagnosticScreenshot(judgment, { path: test.info().outputPath('label-import-' + partial + '-' + width + '.png') });
  } finally { expect((await request.delete(api, { headers: { Origin: new URL(baseURL).origin } })).status()).toBe(204); }
});

for (const width of [1440, 390]) test('hotspot context label lifetime pending collaboration append and fallback ' + width, async ({ page, request, readLongOperationNormal }) => {
  await readLongOperationNormal(request, false, async ({ base, rootId, api, data }) => {
    const key = 'subagent:' + data.diagnostics.workloadSignals.candidates[0].subagentId;
    const authority = await (await request.get(api + '/collaboration?view=participants&limit=100')).json(), label = authority.items.find(item => item.key === key).label;
    let release, arrived; const gate = new Promise(resolve => { release = resolve; }), arrival = new Promise(resolve => { arrived = resolve; });
    await page.route('**/collaboration?*', async route => { const response = await route.fetch(); arrived(); await gate; await route.fulfill({ response, status: width === 390 ? 500 : 200 }); });
    await page.setViewportSize({ width, height: 950 }); await page.goto(base + '/sessions/codex/' + rootId); await arrival;
    const row = page.locator('[data-execution-long-operation]').filter({ hasText: '已测累计 100s' }), span = row.locator('[data-execution-context-key="' + key + '"]');
    await expect(span).toHaveText(label + ' · 独立上下文'); await expect(span).toBeVisible();
    const rowNode = await row.elementHandle(), spanNode = await span.elementHandle(), first = page.locator('[data-execution-tool]').first(), firstNode = await first.elementHandle();
    await first.locator('.se-tool-evidence > summary').click(); const metric = page.getByRole('button', { name: '已测累计', exact: true }); await metric.focus();
    const initial = await page.evaluate(({ key, data }) => {
      const metric = document.activeElement, pageBefore = executionView.page, before = collaborationView.labels.get(key); let writes = 0;
      const set = collaborationView.labels.set; collaborationView.labels.set = function (k, value) { if (k === key) writes++; return set.call(this, k, value); };
      seedExecutionContextLabels(data.contextLabels); collaborationView.labels.set = set;
      collaborationView.labels.delete(key); syncExecutionContextLabels();
      return { before, writes, fallback: document.querySelector('[data-execution-long-operation] [data-execution-context-key="' + key + '"]').textContent, cursor: pageBefore.nextCursor, focused: document.activeElement === metric };
    }, { key, data });
    expect(initial).toMatchObject({ before: label, writes: 0, fallback: '子上下文 ' + key.slice(9) + ' · 独立上下文', focused: true }); expect(initial.cursor).toBeTruthy();
    // Real continuation hints restore a missing cache entry before the diagnostics reuse early return.
    await page.evaluate(cursor => loadExecutionPage({ cursor }, true), initial.cursor);
    await expect(page.locator('[data-execution-pagination]')).toContainText('1–40'); await expect(span).toHaveText(label + ' · 独立上下文');
    expect(await rowNode.evaluate(node => node.isConnected)).toBe(true); expect(await spanNode.evaluate(node => node.isConnected)).toBe(true); expect(await firstNode.evaluate(node => node.isConnected)).toBe(true); await expect(first.locator('.se-tool-evidence')).toHaveAttribute('open'); await expect(metric).toBeFocused();
    release();
    if (width === 390) {
      await expect(page.locator('[data-collaboration-status]')).toContainText('HTTP 500'); await expect(span).toHaveText(label + ' · 独立上下文');
      await page.unroute('**/collaboration?*'); await page.locator('[data-collaboration-status]').getByRole('button', { name: 'Retry' }).click();
    }
    await expect(page.locator('[data-collaboration-relation]')).toHaveCount(5); await expect(span).toHaveText(label + ' · 独立上下文'); expect(await rowNode.evaluate(node => node.isConnected)).toBe(true); expect(await spanNode.evaluate(node => node.isConnected)).toBe(true);
    if (width === 1440) await expect(metric).toBeFocused();
    await captureDiagnosticScreenshot(page.locator('[data-execution-judgment]'), { path: test.info().outputPath('hint-lifetime-' + width + '.png') }); await page.unroute('**/collaboration?*');
    await test.info().attach('hint-lifetime.json', { body: JSON.stringify({ key, label, initial, authority }), contentType: 'application/json' });
  }, hotspotInput);
});

test('hotspot context label lifetime checked generation rejects failed and stale batches', async ({ page, request, readLongOperationNormal }) => {
  // The first index is read-only here; only the changed generation needs a new server.
  await readLongOperationNormal(request, false, async first => {
    const changed = ['changed-zulu', 'changed-copper', 'changed-mint', 'changed-amber', 'changed-willow', 'changed-indigo', 'changed-slate', first.children[7], 'changed-violet', 'changed-maple'];
    await withLongOperationNormal(request, false, async second => {
      const key = 'subagent:' + first.children[7], batches = {};
      for (const [name, fixture] of [['first', first], ['second', second]]) {
        const resources = Object.fromEntries(await Promise.all(['meta', 'metrics', 'diagnostics', 'rounds', 'execution'].map(async resource => {
          const response = await request.get(fixture.api + '/' + resource); expect(response.status()).toBe(200);
          return [resource, { body: await response.body(), headers: response.headers() }];
        })));
        const authority = await (await request.get(fixture.api + '/collaboration?view=participants&limit=100')).json();
        const label = authority.items.find(item => item.key === key).label, generation = resources.execution.headers['x-session-index-generation'];
        expect(generation).toBeTruthy(); for (const resource of Object.values(resources)) expect(resource.headers['x-session-index-generation']).toBe(generation);
        batches[name] = { fixture, resources, authority, label, generation };
      }
      expect(batches.first.label).not.toBe(batches.second.label); expect(batches.first.generation).not.toBe(batches.second.generation);
      const sha = rows => require('crypto').createHash('sha256').update(rows.map(JSON.stringify).join('\n') + '\n').digest('hex');
      await test.info().attach('generation-real-authorities.json', { body: JSON.stringify(Object.fromEntries(Object.entries(batches).map(([name, b]) => [name, { generation: b.generation, label: b.label, authority: b.authority, sources: b.fixture.raws.map(([id, rows]) => ({ id, sha256: sha(rows) })), batch: Object.fromEntries(Object.entries(b.resources).map(([resource, value]) => [resource, { headers: value.headers, sha256: require('crypto').createHash('sha256').update(value.body).digest('hex') }])) }]))), contentType: 'application/json' });
      // Transport-only fixture: retain real response bytes/headers, but allow the existing coordinator's
      // unbound-document path to publish successive real generations in one document.
      await page.route(first.base + '/sessions/codex/' + first.rootId, async route => { const response = await route.fetch(); await route.fulfill({ response, body: (await response.text()).replace(/\sdata-index-generation="[^"]*"/g, '') }); });
      await page.addInitScript(() => {
        let api;
        Object.defineProperty(window, 'IndexSnapshot', { configurable: true, get: () => api, set: value => {
          api = value; const create = value.create;
          value.create = function () { const snapshot = create(), load = snapshot.load; snapshot.load = function (jobs) { window.labelSnapshot = snapshot; window.labelJobs = jobs; return load(jobs); }; return snapshot; };
        } });
      });
      let phase = 'first', release, arrived; const gate = new Promise(resolve => { release = resolve; }), arrival = new Promise(resolve => { arrived = resolve; });
      await page.route(first.api + '/*', async route => {
        const resource = new URL(route.request().url()).pathname.split('/').at(-1), selectedPhase = phase;
        if (!['meta', 'metrics', 'diagnostics', 'rounds', 'execution'].includes(resource)) {
          if (selectedPhase !== 'first') { const response = await route.fetch({ url: route.request().url().replace(first.base, second.base) }); await route.fulfill({ response }); }
          else await route.continue();
          return;
        }
        const batch = selectedPhase === 'first' ? batches.first : batches.second, response = batch.resources[resource];
        if (selectedPhase === 'stale' && resource === 'execution') { arrived(); await gate; }
        await route.fulfill({ status: selectedPhase === 'failed' && resource === 'metrics' ? 500 : 200, headers: response.headers, body: response.body });
      });
      await page.goto(first.base + '/sessions/codex/' + first.rootId); await page.waitForFunction(() => collaborationView.sourceStatus === 'ready');
      const context = () => page.locator('[data-execution-long-operation]').filter({ hasText: '已测累计 100s' }).locator('[data-execution-context-key="' + key + '"]');
      await expect(context()).toHaveText(batches.first.label + ' · 独立上下文');
      phase = 'failed'; await page.evaluate(() => labelSnapshot.load(labelJobs));
      expect(await page.evaluate(key => collaborationView.labels.get(key), key)).toBe(batches.first.label); expect(await page.locator('body').getAttribute('data-index-generation')).toBe(batches.first.generation);
      phase = 'first'; await page.evaluate(async () => { await labelSnapshot.load(labelJobs); window.dispatchEvent(new Event('index-snapshot-restored')); }); await expect(context()).toHaveText(batches.first.label + ' · 独立上下文');
      phase = 'stale'; await page.evaluate(() => { window.labelStaleLoad = labelSnapshot.load(labelJobs); }); await arrival;
      phase = 'first'; await page.evaluate(async () => { await labelSnapshot.load(labelJobs); window.dispatchEvent(new Event('index-snapshot-restored')); }); release(); await page.evaluate(() => labelStaleLoad);
      await expect(context()).toHaveText(batches.first.label + ' · 独立上下文');
      phase = 'second'; await page.evaluate(async () => {
        const execution = labelJobs.find(job => job.key === 'execution'), apply = execution.apply;
        execution.apply = function (part) { apply(part); throw new Error('synthetic post-apply quarantine'); };
        try { await labelSnapshot.load(labelJobs); } finally { execution.apply = apply; }
        window.dispatchEvent(new Event('index-snapshot-restored'));
      });
      expect(await page.locator('[data-snapshot-batch-error]').count()).toBe(1);
      expect(await page.evaluate(key => collaborationView.labels.get(key), key)).toBe(batches.first.label);
      phase = 'first'; await page.evaluate(async () => { await labelSnapshot.load(labelJobs); window.dispatchEvent(new Event('index-snapshot-restored')); });
      await expect(context()).toHaveText(batches.first.label + ' · 独立上下文');
      phase = 'second'; await page.evaluate(async () => { await labelSnapshot.load(labelJobs); window.dispatchEvent(new Event('index-snapshot-restored')); });
      await expect(context()).toHaveText(batches.second.label + ' · 独立上下文'); await expect(context()).toBeVisible(); expect(await page.locator('body').getAttribute('data-index-generation')).toBe(batches.second.generation);
      expect(await page.evaluate(key => collaborationView.labels.has(key), 'subagent:' + first.children[0])).toBe(false);
      await captureDiagnosticScreenshot(page.locator('[data-execution-judgment]'), { path: test.info().outputPath('hint-real-generation.png') });
      await test.info().attach('generation-ui-result.json', { body: JSON.stringify({ key, first: batches.first.label, second: batches.second.label, failedAndStalePreservedFirst: true, oldUnreferencedKeyRemoved: true, transportFixtureNotProductScan: true }), contentType: 'application/json' });
    }, hotspotInput, changed);
  }, hotspotInput);
});

test('hotspot context label lifetime same raw tool IDs remain isolated across real imports', async ({ page, request, baseURL }) => {
  const imports = [];
  try {
    for (const partial of [false, true]) {
      const imported = await upload(request, baseURL, 'codex', hotspotImportSource(partial)), api = '/api/imports/' + imported.import_id; imports.push(api);
      const data = await (await request.get(api + '/execution')).json(); expect(data.contextLabels).toEqual({ main: '主 Agent' });
      await page.goto(imported.detail_url); await page.waitForFunction(() => collaborationView.sourceStatus === 'ready'); await expect(page.locator('[data-execution-judgment]')).toContainText(partial ? '99.5s' : '100s');
      expect(await page.evaluate(() => [...collaborationView.labels.keys()])).toEqual(['main']); await expect(page.locator('[data-execution-context-key^="subagent:"]')).toHaveCount(0);
    }
    expect(new Set(imports).size).toBe(2);
  } finally { for (const api of imports) expect((await request.delete(api, { headers: { Origin: new URL(baseURL).origin } })).status()).toBe(204); }
});

test('hotspot context label lifetime accepted partial snapshot retains hints through metrics Retry', async ({ page, request, readLongOperationNormal }) => {
  await readLongOperationNormal(request, false, async ({ base, rootId, children, api, data }) => {
    const key = 'subagent:' + children[7], requests = [];
    const authority = await (await request.get(api + '/collaboration?view=participants&limit=100')).json();
    const label = authority.items.find(item => item.key === key).label;
    expect(data.contextLabels[key]).toBe(label);
    let fail = true;
    await page.route(api + '/metrics', async route => {
      const response = await route.fetch();
      await route.fulfill(fail ? { response, status: 500 } : { response });
    });
    page.on('request', request => { if (request.url().startsWith(api)) requests.push(request.url()); });
    await page.goto(base + '/sessions/codex/' + rootId);
    await expect(page.locator('[data-resource-error="metrics"]')).toContainText('HTTP 500');
    await expect(page.locator('body')).toHaveAttribute('data-session-api-execution-state', 'true');
    const executionRequests = requests.filter(url => new URL(url).pathname.endsWith('/execution')).length;
    fail = false;
    await page.locator('[data-resource-error="metrics"] button').click();
    await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
    await page.waitForFunction(() => collaborationView.sourceStatus === 'ready');
    const context = page.locator('[data-execution-long-operation]').filter({ hasText: '已测累计 100s' }).locator('[data-execution-context-key="' + key + '"]');
    await expect(context).toHaveText(label + ' · 独立上下文'); await expect(context).toBeVisible();
    expect(requests.filter(url => new URL(url).pathname.endsWith('/execution')).length).toBe(executionRequests);
    await test.info().attach('accepted-partial-authority.json', { body: JSON.stringify({ key, label, authority, executionRequests, singleResourceRetry: true }), contentType: 'application/json' });
  }, hotspotInput);
});

// Four immutable raw sources traverse both native scan and single-file import; never execute cmd.
function failureEvidenceSource(kind) {
  const id = 'synthetic-failure-evidence-' + kind, call = 'failure-evidence-command';
  const status = kind === 'cancelled' ? 'cancelled' : kind === 'executor-failed' ? 'failed' : 'completed';
  const observation = { type: 'exec_command_end', call_id: call, duration: { secs: 0, nanos: 500000000 }, status };
  if (kind !== 'cancelled') observation.exit_code = kind === 'exit7' ? 7 : 0;
  const output = { type: 'function_call_output', call_id: call, output: 'Synthetic recorded result only; command not executed' };
  if (kind === 'result-signal') output.error = 'Synthetic result signal <failure-evidence-sentinel>';
  const command = 'node synthetic-failure-evidence.js --scenario ' + kind;
  const rows = [
    { timestamp: '2026-01-01T00:00:00Z', type: 'session_meta', payload: { id, source: 'cli' } },
    { timestamp: '2026-01-01T00:00:01Z', type: 'response_item', payload: { type: 'function_call', call_id: call, name: 'exec_command', arguments: JSON.stringify({ cmd: command }) } },
    { timestamp: '2026-01-01T00:00:02Z', type: 'token_usage_record', payload: { response_id: 'failure-evidence-response', usage: { input_tokens: 10, output_tokens: 2 } } },
    { timestamp: '2026-01-01T00:00:03Z', type: 'response_item', payload: output },
    { timestamp: '2026-01-01T00:00:04Z', type: 'event_msg', payload: observation },
  ];
  return { id, call, command, rows, observation, resultSignal: output.error || '', bytes: Buffer.from(rows.map(JSON.stringify).join('\n') + '\n') };
}

async function withFailureEvidenceNormal(request, source, read) {
  const fs = require('fs'), path = require('path'), { spawn } = require('child_process');
  const { runTmpRoot } = require('./runtime-paths'), { copyDistribution, resolveJavaEnvironment } = require('./start-java-fixture-server');
  fs.mkdirSync(runTmpRoot, { recursive: true });
  const directory = fs.mkdtempSync(path.join(runTmpRoot, 'failure-evidence-')), home = path.join(directory, 'home'), temp = path.join(directory, 'temp');
  fs.mkdirSync(path.join(home, '.codex/sessions/synthetic'), { recursive: true }); fs.mkdirSync(temp);
  const sources = [source, ...(source.siblings || [])];
  for (const entry of sources) fs.writeFileSync(path.join(home, '.codex/sessions/synthetic/rollout-' + entry.id + '.jsonl'), entry.bytes);
  fs.writeFileSync(path.join(home, '.codex/session_index.jsonl'), sources.map(entry => JSON.stringify({ id: entry.id, thread_name: 'Synthetic failure evidence' })).join('\n') + '\n');
  const java = resolveJavaEnvironment();
  const child = spawn(copyDistribution(directory), ['serve', '--host', '127.0.0.1', '--port', '0'], { cwd: directory,
    env: { JAVA_HOME: java.JAVA_HOME, PATH: java.JAVA_HOME + '/bin:/usr/bin:/bin:/usr/sbin:/sbin', HOME: home, INDEX_DIR: path.join(directory, 'index'), TMPDIR: temp, JAVA_OPTS: `"-Duser.home=${home}" "-Djava.io.tmpdir=${temp}"`, APP_CLI_OPTS: '', LANG: 'en_US.UTF-8' }, stdio: ['ignore', 'pipe', 'pipe'] });
  let logs = '';
  try {
    const base = await new Promise((resolve, reject) => { child.once('error', reject); child.once('exit', code => reject(new Error('early exit ' + code + logs))); for (const stream of [child.stdout, child.stderr]) stream.on('data', value => { logs += value; const match = logs.match(/serve 已就绪: (http:\/\/127\.0\.0\.1:\d+)/); if (match) resolve(match[1]); }); });
    await expect.poll(() => /后台扫描完成: tier=full window=all/.test(logs)).toBe(true);
    const api = base + '/api/sessions/codex/' + source.id;
    await expect.poll(async () => (await request.get(api + '/execution')).status()).toBe(200);
    await assertHotspotLabelAssets(request, base, directory);
    await read({ api, url: base + '/sessions/codex/' + source.id, directory });
  } finally {
    if (child.exitCode === null) { child.kill('SIGTERM'); await new Promise(resolve => child.once('exit', resolve)); }
    fs.writeFileSync(path.join(directory, 'service.log'), logs);
    await test.info().attach('failure-evidence-service.json', { body: JSON.stringify({ directory, pid: child.pid, exited: child.exitCode !== null || child.signalCode !== null, signal: child.signalCode }), contentType: 'application/json' });
  }
}

for (const kind of ['exit7', 'cancelled', 'executor-failed', 'result-signal']) for (const mode of ['normal', 'import']) for (const width of [1440, 390]) {
  test('failure evidence ' + kind + ' ' + mode + ' ' + width, async ({ page, request, baseURL }) => {
    const fs = require('fs'), path = require('path'), crypto = require('crypto'), source = failureEvidenceSource(kind);
    fs.writeFileSync(test.info().outputPath('source.jsonl'), source.bytes);
    const sourceSHA = crypto.createHash('sha256').update(source.bytes).digest('hex');
    const read = async ({ api, url }) => {
      const response = await request.get(api + '/execution'); expect(response.status()).toBe(200);
      const data = await response.json(), diag = data.diagnostics, tool = diag.firstFailureTool;
      await test.info().attach('failure-evidence-api-before-assert.json', { body: JSON.stringify({ data, source: source.rows }), contentType: 'application/json' });
      expect(diag.failures).toBe(1); expect(diag.firstFailure).toBe(source.call);
      const evidence = { exit7: { kind: 'nonzero_exit', exitCode: 7, executorStatus: null }, cancelled: { kind: 'executor_status', exitCode: null, executorStatus: 'cancelled' }, 'executor-failed': { kind: 'executor_status', exitCode: null, executorStatus: 'failed' }, 'result-signal': { kind: 'result_signal', exitCode: null, executorStatus: null } };
      expect(diag.firstFailureEvidence).toEqual(evidence[kind]);
      expect(Object.keys(diag.firstFailureEvidence).sort()).toEqual(['executorStatus', 'exitCode', 'kind']);
      expect(JSON.stringify(diag.firstFailureEvidence)).not.toContain('Synthetic');

      expect(tool).toMatchObject({ toolCallId: source.call, scope: 'main', subagentId: '', inputPreview: source.command });
      expect(tool.observation.status).toBe(source.observation.status);
      expect(tool.observation.exitCode).toBe(source.observation.exit_code === undefined ? null : source.observation.exit_code);
      expect(tool.exitCode).toBe(source.observation.exit_code === undefined ? null : source.observation.exit_code);
      if (source.resultSignal) expect(tool.status).toBe(source.resultSignal); else expect(tool.status).toBe('');
      expect(tool.resultObserved).toBe(true);
      const item = data.items.find(item => item.tool?.toolCallId === source.call); expect(item).toBeTruthy();
      expect(item.tool.declaredByCallId).toBe(tool.declaredByCallId); expect(item.group.id).toBe(tool.declaredByCallId); expect(item.group.toolCount).toBe(1);
      const network = []; page.on('request', r => { if (new URL(r.url()).pathname.startsWith('/api/')) network.push(r.url()); });
      await page.setViewportSize({ width, height: 1000 }); await page.goto(url);
      await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
      await page.waitForFunction(() => collaborationView.sourceStatus === 'ready');
      const card = page.locator('.se-judgments article').filter({ has: page.getByRole('heading', { name: '1 个工具有失败信号', exact: true }) }); await expect(card).toHaveCount(1); await expect(card).toBeVisible();
      await expect(card.locator('h3')).toHaveText('1 个工具有失败信号'); await expect(card.locator('.se-basis')).toHaveText('执行归属：主会话');
      await expect(card.locator('.se-diagnosis-command')).toHaveText(source.command);
      await expect(card.getByRole('button', { name: '定位首个失败', exact: true })).toHaveAttribute('data-execution-locate', source.call);
      const explanation = card.locator('p').first(); await expect(explanation).toHaveCount(1); await expect(explanation).toBeVisible(); await expect(explanation).toContainText('不等同整个任务失败');
      expect(network.length).toBe(mode === 'normal' ? 7 : 6); expect(network.some(url => /\/payload|cursor=|view=participants/.test(url))).toBe(false);
      await captureDiagnosticScreenshot(card, { path: test.info().outputPath('failure-card-' + width + '.png') });
      await test.info().attach('failure-evidence-positive.json', { body: JSON.stringify({ kind, mode, width, sourceSHA, raw: source.rows, api, data, firstFailureEvidencePresent: Object.hasOwn(diag, 'firstFailureEvidence'), visibleExplanation: await explanation.textContent(), network, target: source.call, commandsExecuted: false }), contentType: 'application/json' });
      const expected = { exit7: '退出码 7', cancelled: '执行器状态 cancelled（取消）', 'executor-failed': '执行器状态 failed（失败）', 'result-signal': '工具结果记录含失败线索' };
      await expect(explanation).toContainText(expected[kind]);
    };
    if (mode === 'normal') await withFailureEvidenceNormal(request, source, read);
    else {
      const imported = await upload(request, baseURL, 'codex', source.rows), api = baseURL + '/api/imports/' + imported.import_id;
      try { await read({ api, url: new URL(imported.detail_url, baseURL).href }); }
      finally { const response = await request.delete(api, { headers: { Origin: new URL(baseURL).origin } }); expect(response.status()).toBe(204); await test.info().attach('failure-evidence-import-cleanup.json', { body: JSON.stringify({ importId: imported.import_id, deletedStatus: response.status() }), contentType: 'application/json' }); }
    }
  });
}

test('failure evidence DTO guards and frozen diagnostic node lifetime are UI-only', async ({ page, request, baseURL }) => {
  const source = failureEvidenceSource('exit7'), imported = await upload(request, baseURL, 'codex', source.rows), api = '/api/imports/' + imported.import_id;
  try {
    const original = await (await request.get(api + '/execution')).json();
    await page.goto(imported.detail_url); await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
    await page.waitForFunction(() => collaborationView.sourceStatus === 'ready');
    const guards = await page.evaluate(original => {
      const sentinel = '<img src=x onerror="failureEvidenceInjected=1">', fallback = '首个工具已记录信号，具体依据请定位查看；不等同整个任务失败。';
      const cases = [undefined, null, { kind: 'unknown', exitCode: 7 }, { kind: sentinel },
        { kind: 'executor_status', executorStatus: sentinel }, { kind: 'executor_status', executorStatus: 'toString' }, { kind: 'executor_status', executorStatus: ['failed'] },
        ...[null, '7', 7.5, 0, 2147483648, -2147483649].map(exitCode => ({ kind: 'nonzero_exit', exitCode }))];
      const readings = cases.map(evidence => {
        const diag = { ...original.diagnostics, firstFailureEvidence: evidence };
        if (evidence === undefined) delete diag.firstFailureEvidence;
        applyExecutionPage({ ...original, diagnostics: diag }, false);
        return document.querySelector('.se-judgments article p').textContent;
      });
      applyExecutionPage({ ...original, diagnostics: { ...original.diagnostics, firstFailureTool: null } }, false);
      readings.push(document.querySelector('.se-judgments article p').textContent);
      const safe = [];
      for (const evidence of [{ kind: 'executor_status', executorStatus: 'error' }, { kind: 'nonzero_exit', exitCode: -2147483648 }, { kind: 'nonzero_exit', exitCode: 2147483647 }]) {
        applyExecutionPage({ ...original, diagnostics: { ...original.diagnostics, firstFailureEvidence: evidence } }, false);
        safe.push(document.querySelector('.se-judgments article p').textContent);
      }
      const noSentinelDom = !document.querySelector('.se-judgments img') && !window.failureEvidenceInjected;
      applyExecutionPage(original, false);
      const card = document.querySelector('.se-judgments article'), explanation = card.querySelector('p'), button = card.querySelector('button'), tool = document.querySelector('[data-execution-tool]'), details = tool.querySelector('.se-tool-evidence');
      details.open = true; button.focus();
      // UI-only transport simulation retains the exact actual frozen diagnostics; it is not a source/API fixture.
      applyExecutionPage({ ...original, items: [], offset: original.items.length }, true);
      const appendToolPreserved = tool === document.querySelector('[data-execution-tool]') && details.open;
      applyExecutionPage(original, false);
      collaborationView.labels.set('main', 'Synthetic late label must not replace 主会话'); syncExecutionContextLabels();
      return { fallback, readings, safe, noSentinelDom, sameCard: card === document.querySelector('.se-judgments article'), sameExplanation: explanation === card.querySelector('p'), appendToolPreserved, detailsOpen: details.open, focused: document.activeElement === button, text: explanation.textContent, owner: card.querySelector('.se-basis').textContent, command: card.querySelector('code').textContent, target: button.dataset.executionLocate };
    }, original);
    expect(guards.readings.every(text => text === guards.fallback)).toBe(true);
    expect(guards.safe).toEqual(['首个依据：执行器状态 error（错误）；不等同整个任务失败。', '首个依据：退出码 -2147483648；不等同整个任务失败。', '首个依据：退出码 2147483647；不等同整个任务失败。']);
    expect(guards).toMatchObject({ noSentinelDom: true, sameCard: true, sameExplanation: true, appendToolPreserved: true, detailsOpen: true, focused: true, text: '首个依据：退出码 7；不等同整个任务失败。', owner: '执行归属：主会话', command: source.command, target: source.call });
    await test.info().attach('failure-evidence-dto-guards.json', { body: JSON.stringify({ uiOnly: true, guards }), contentType: 'application/json' });
  } finally { expect((await request.delete(api, { headers: { Origin: new URL(baseURL).origin } })).status()).toBe(204); }
});

// The exact root/child records used by the original failure attribution case above.
function failureMeasurementChildSource() {
  const rootId = 'synthetic-failure-context-root', childId = 'synthetic-failure-context-child';
  const meta = (id, parent) => ({ type: 'session_meta', payload: { id, source: parent ? { subagent: { thread_spawn: { parent_thread_id: parent } } } : 'cli' } });
  const call = (id, name, args) => ({ type: 'response_item', payload: { type: 'function_call', call_id: id, name, arguments: JSON.stringify(args) } });
  const output = (id, value) => ({ type: 'response_item', payload: { type: 'function_call_output', call_id: id, output: value } });
  const usage = id => ({ type: 'token_usage_record', payload: { response_id: id, usage: { input_tokens: 10, output_tokens: 2 } } });
  const root = [meta(rootId), call('failure-spawn', 'spawn_agent', { message: 'Synthetic failed child, parent wait not success proof' }), output('failure-spawn', { agent_id: childId }), usage('root-spawn'), call('failure-wait', 'wait_agent', { targets: [childId] }), usage('root-wait'), output('failure-wait', { status: { [childId]: { completed: 'Synthetic parent wait report only' } } })];
  const childRaw = [meta(childId, rootId), call('failure-command', 'exec_command', { cmd: 'node synthetic-failure-check.js --case 23' }), usage('child-failure'), output('failure-command', 'Synthetic recorded error, command not executed'), { type: 'event_msg', payload: { type: 'exec_command_end', call_id: 'failure-command', duration: { secs: 0, nanos: 500000000 }, exit_code: 7, status: 'completed' } }];
  const bytes = rows => Buffer.from(rows.map(JSON.stringify).join('\n') + '\n');
  return { id: rootId, bytes: bytes(root), siblings: [{ id: childId, bytes: bytes(childRaw) }], childId, call: 'failure-command', command: 'node synthetic-failure-check.js --case 23' };
}

for (const mode of ['normal-child', 'cancelled-import']) for (const width of [1440, 390]) {
  test('failure measurement density ' + mode + ' ' + width, async ({ page, request, baseURL }) => {
    const fs = require('fs'), crypto = require('crypto'), normal = mode === 'normal-child';
    const source = normal ? failureMeasurementChildSource() : failureEvidenceSource('cancelled');
    const sourceSHAs = [source, ...(source.siblings || [])].map((entry, index) => {
      fs.writeFileSync(test.info().outputPath('source-' + index + '.jsonl'), entry.bytes);
      return { id: entry.id, sha256: crypto.createHash('sha256').update(entry.bytes).digest('hex') };
    });
    if (!normal) expect(sourceSHAs[0].sha256).toBe('c395fceba3ba6c7ab6fb00aef6cf561ebf3e3e367184f1cf08442874a4411a1f');
    const read = async ({ api, url }) => {
      const response = await request.get(api + '/execution'); expect(response.status()).toBe(200);
      const data = await response.json(), diag = data.diagnostics, tool = diag.firstFailureTool;
      expect(diag).toMatchObject({ failures: 1, measuredTools: 1, totalTools: normal ? 3 : 1, unrankedTools: normal ? 2 : 0, measuredWorkMs: 500, firstFailure: source.call });
      expect(diag.workloads.length).toBeGreaterThan(0);
      expect(tool).toMatchObject({ toolCallId: source.call, inputPreview: source.command, scope: normal ? 'subagent' : 'main', subagentId: normal ? source.childId : '', exitCode: normal ? 7 : null });
      expect(tool.observation.status).toBe(normal ? 'completed' : 'cancelled');
      expect(diag.firstFailureEvidence).toEqual(normal ? { kind: 'nonzero_exit', exitCode: 7, executorStatus: null } : { kind: 'executor_status', exitCode: null, executorStatus: 'cancelled' });
      let owner = '主会话', facts;
      if (normal) {
        const participants = await (await request.get(api + '/collaboration?view=participants&limit=100')).json();
        owner = participants.items.find(item => item.key === 'subagent:' + source.childId).label + ' · 独立上下文';
        facts = await (await request.get(api + '/collaboration')).json();
        expect(facts.items.flatMap(item => item.reports || []).some(report => report.reportedStatus === 'completed')).toBe(true);
      }
      const network = []; page.on('request', r => { if (new URL(r.url()).pathname.startsWith('/api/')) network.push(r.url()); });
      await page.setViewportSize({ width, height: 1000 }); await page.goto(url);
      await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true'); await page.waitForFunction(() => collaborationView.sourceStatus === 'ready');
      const judgment = page.locator('[data-execution-judgment]'), card = judgment.locator('.se-judgments article').filter({ has: page.getByRole('heading', { name: '1 个工具有失败信号', exact: true }) });
      await expect(card).toHaveCount(1); await expect(card).toBeVisible();
      await expect(card.locator('p').first()).toHaveText(normal ? '首个依据：退出码 7；不等同整个任务失败。' : '首个依据：执行器状态 cancelled（取消）；不等同整个任务失败。');
      await expect(card.locator('.se-basis')).toHaveText('执行归属：' + owner); await expect(card.locator('code')).toHaveText(source.command);
      await expect(card.getByRole('button', { name: '定位首个失败', exact: true })).toHaveAttribute('data-execution-locate', source.call);
      const workload = judgment.locator('[data-execution-workload]'); await expect(workload).toHaveCount(1); await expect(workload).toBeVisible(); await expect(workload).toContainText('已测累计 500ms');
      const basis = judgment.locator(':scope > p.se-basis'); await expect(basis).toHaveCount(1); await expect(basis).toBeVisible();
      await expect(basis).toContainText('已测工具 1 / ' + (normal ? 3 : 1)); await expect(basis).toContainText('未参与可信累计比较 ' + (normal ? 2 : 0) + ' 次');
      for (const boundary of ['模型耗时未测量', '累计非墙钟或关键路径', '— 表示来源未知，不是零', '工具返回不证明整个任务完成', '日志未明确记录时，异步任务状态未知']) await expect(basis).toContainText(boundary);
      const measurement = judgment.locator('details.se-measurement'); await expect(measurement).not.toHaveAttribute('open', '');
      expect(network.length).toBe(normal ? 7 : 6); expect(network.some(url => /\/payload|cursor=|view=participants/.test(url))).toBe(false);
      await captureDiagnosticScreenshot(judgment, { path: test.info().outputPath('measurement-judgment-' + width + '.png') }); await captureDiagnosticScreenshot(page, { path: test.info().outputPath('measurement-viewport-' + width + '.png'), fullPage: false });
      const beforeDisclosure = network.length;
      await measurement.locator('summary').focus(); await page.keyboard.press(width === 1440 ? 'Enter' : 'Space'); await expect(measurement).toHaveAttribute('open', '');
      const fullMeasurement = measurement.locator(':scope > p').first(); await expect(fullMeasurement).toBeVisible();
      for (const boundary of ['已测工作量之和 500 ms', '全范围可含不同上下文/口径，不据此混榜', '不是墙钟时间或关键路径', '模型耗时未测量', '— 表示来源未知，不是零', '工具结果、wait/poll 返回或子任务完成均不证明整个任务完成', '日志未明确记录时，异步任务状态未知', '不能据工具或轮询结果判断其仍在运行或已结束']) await expect(fullMeasurement).toContainText(boundary);
      expect(network.length).toBe(beforeDisclosure);
      await captureDiagnosticScreenshot(measurement, { path: test.info().outputPath('measurement-expanded-' + width + '.png') });
      await test.info().attach('failure-measurement-positive.json', { body: JSON.stringify({ mode, width, sourceSHAs, data, facts, owner, target: source.call, basis: await basis.textContent(), fullMeasurement: await fullMeasurement.textContent(), network, commandsExecuted: false }), contentType: 'application/json' });
      await expect(basis).not.toContainText('已测工作量之和');
    };
    if (normal) await withFailureEvidenceNormal(request, source, read);
    else {
      const imported = await upload(request, baseURL, 'codex', source.rows), api = baseURL + '/api/imports/' + imported.import_id;
      try { await read({ api, url: new URL(imported.detail_url, baseURL).href }); }
      finally { const response = await request.delete(api, { headers: { Origin: new URL(baseURL).origin } }); expect(response.status()).toBe(204); await test.info().attach('measurement-import-cleanup.json', { body: JSON.stringify({ importId: imported.import_id, status: response.status() }), contentType: 'application/json' }); }
    }
  });
}

test('failure measurement density UI-only AND boundary and frozen diagnosis lifetime', async ({ page, request, baseURL }) => {
  const source = failureEvidenceSource('cancelled'), imported = await upload(request, baseURL, 'codex', source.rows), api = '/api/imports/' + imported.import_id;
  try {
    const original = await (await request.get(api + '/execution')).json(); await page.goto(imported.detail_url);
    await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true'); await page.waitForFunction(() => collaborationView.sourceStatus === 'ready');
    const results = await page.evaluate(original => {
      const diag = original.diagnostics, work = diag.workloads[0];
      const scenarios = {
        qualified: {},
        noWorkloads: { workloads: [] },
        noMeasurements: { measuredTools: 0, workloads: [] },
        zeroMeasurementsDespiteWorkload: { measuredTools: 0 },
        measuredZero: { measuredWorkMs: 0, workloads: [{ ...work, measuredWorkNanos: '0', longest: { ...work.longest, durationMs: 0, observation: { ...work.longest.observation, durationNanos: 0 } } }] },
        unknownScopeWithoutTrustedWork: { workloads: [], firstFailureTool: { ...diag.firstFailureTool, scope: 'unknown', subagentId: '' } }
      };
      const readings = Object.entries(scenarios).map(([scenario, fields]) => {
        applyExecutionPage({ ...original, diagnostics: { ...diag, ...fields } }, false);
        const host = document.querySelector('[data-execution-judgment]');
        return { scenario, basis: host.querySelector(':scope > p.se-basis').textContent, details: host.querySelector('.se-measurement').textContent, owner: host.querySelector('.se-judgments .se-basis').textContent };
      });
      applyExecutionPage(original, false);
      const host = document.querySelector('[data-execution-judgment]'), card = host.querySelector('.se-judgments article'), explanation = card.querySelector('p'), basis = host.querySelector(':scope > p.se-basis'), measurement = host.querySelector('.se-measurement'), button = card.querySelector('button'); measurement.open = true; button.focus();
      applyExecutionPage({ ...original, items: [], offset: original.items.length }, true); applyExecutionPage(original, false);
      return { readings, nodes: { card: card === host.querySelector('.se-judgments article'), explanation: explanation === card.querySelector('p'), basis: basis === host.querySelector(':scope > p.se-basis'), measurement: measurement === host.querySelector('.se-measurement'), open: measurement.open, focus: document.activeElement === button, target: button.dataset.executionLocate } };
    }, original);
    for (const row of results.readings) {
      const shortened = ['qualified', 'measuredZero'].includes(row.scenario);
      expect(row.basis.includes('已测工作量之和'), row.scenario).toBe(!shortened);
      if (shortened) { expect(row.basis).toContain('日志未明确记录时，异步任务状态未知'); expect(row.details).toContain('已测工作量之和 ' + (row.scenario === 'measuredZero' ? '0 ms' : '500 ms')); }
      else { expect(row.basis).toContain('不能据工具或轮询结果判断其仍在运行或已结束'); expect(row.basis).toContain('工具结果、wait/poll 返回或子任务完成均不证明整个任务完成'); }
    }
    expect(results.readings.find(row => row.scenario === 'unknownScopeWithoutTrustedWork').owner).toBe('执行归属：归属未记录');
    expect(results.nodes).toEqual({ card: true, explanation: true, basis: true, measurement: true, open: true, focus: true, target: source.call });
    await test.info().attach('measurement-ui-only-guards.json', { body: JSON.stringify({ uiOnly: true, ...results }), contentType: 'application/json' });
  } finally { const response = await request.delete(api, { headers: { Origin: new URL(baseURL).origin } }); expect(response.status()).toBe(204); }
});

// Immutable normal parent/child source: no fabricated child model owner and no command execution.
for (const width of [1440, 390]) test('orphan tool input normal source ' + width, async ({ page, request }, testInfo) => {
  const fs = require('fs'), path = require('path'), crypto = require('crypto');
  const parentBytes = Buffer.from("{\"type\":\"session_meta\",\"payload\":{\"id\":\"synthetic-orphan-parent-v52\"}}\n{\"type\":\"response_item\",\"payload\":{\"type\":\"function_call\",\"call_id\":\"orphan-parent-spawn-v54\",\"name\":\"spawn_agent\",\"arguments\":\"{\\\"message\\\":\\\"Synthetic interrupted child task: inspect recorded command failure; do not execute a real script.\\\"}\"}}\n{\"type\":\"response_item\",\"payload\":{\"type\":\"function_call_output\",\"call_id\":\"orphan-parent-spawn-v54\",\"output\":\"{\\\"agent_id\\\":\\\"synthetic-orphan-child-v52\\\"}\"}}\n{\"type\":\"token_usage_record\",\"payload\":{\"response_id\":\"orphan-parent-response-v54\",\"usage\":{\"input_tokens\":1,\"output_tokens\":1}}}\n"), childBytes = Buffer.from("{\"type\":\"session_meta\",\"payload\":{\"id\":\"synthetic-orphan-child-v52\",\"source\":{\"subagent\":{\"thread_spawn\":{\"parent_thread_id\":\"synthetic-orphan-parent-v52\"}}}}}\n{\"type\":\"response_item\",\"payload\":{\"type\":\"function_call\",\"call_id\":\"orphan-command-v52\",\"name\":\"exec_command\",\"arguments\":\"{\\\"cmd\\\":\\\"node synthetic-orphan-check.js --case no-owner\\\"}\"}}\n{\"type\":\"response_item\",\"payload\":{\"type\":\"function_call_output\",\"call_id\":\"orphan-command-v52\",\"output\":\"Synthetic recorded error, command not executed\"}}\n{\"type\":\"event_msg\",\"payload\":{\"type\":\"exec_command_end\",\"call_id\":\"orphan-command-v52\",\"duration\":{\"secs\":0,\"nanos\":500000000},\"exit_code\":7,\"status\":\"completed\"}}\n");
  expect(crypto.createHash('sha256').update(parentBytes).digest('hex')).toBe('9a91aecab70d4979c098507a443cbed720d70bdc70471e843c11ab3a5cfa55fc');
  expect(crypto.createHash('sha256').update(childBytes).digest('hex')).toBe('61349a6822530652ff636826a8b579d84a2fa27774291bf59867e45255cc969e');
  const source = { id: 'synthetic-orphan-parent-v52', bytes: parentBytes, siblings: [{ id: 'synthetic-orphan-child-v52', bytes: childBytes }] };
  const out = testInfo.outputPath('orphan-tool-input'); fs.mkdirSync(out, { recursive: true });
  const errors = [], network = []; page.on('pageerror', e => errors.push(e.message)); page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('request', r => { if (new URL(r.url()).pathname.startsWith('/api/')) network.push(r.url()); });
  await withFailureEvidenceNormal(request, source, async ({ api, url }) => {
    const data = await (await request.get(api + '/execution')).json(), diag = data.diagnostics;
    expect(data.total).toBe(2); expect(data.items.filter(x => x.group.response).length).toBe(1);
    expect(diag).toMatchObject({ failures: 1, measuredTools: 1, measuredWorkMs: 500, firstFailure: 'orphan-command-v52' });
    expect(diag.firstFailureTool).toMatchObject({ declaredByCallId: 'unknown', scope: 'subagent', subagentId: 'synthetic-orphan-child-v52', exitCode: 7, durationMs: 500 });
    const orphan = data.items.find(x => x.tool.toolCallId === diag.firstFailure); expect(orphan.group).toMatchObject({ response: false, inputAvailable: false, outputAvailable: false });
    const authority = await (await request.get(api + '/collaboration?view=participants&limit=100')).json();
    const label = authority.items.find(x => x.key === 'subagent:synthetic-orphan-child-v52').label; expect(label).toBe('Agent 1');
    expect(authority.items.map(x => x.key)).toEqual(['main', 'subagent:synthetic-orphan-child-v52']);
    await page.setViewportSize({ width, height: 900 }); await page.goto(url); await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true'); await page.waitForFunction(() => collaborationView.sourceStatus === 'ready');
    const judgment = page.locator('[data-execution-judgment]'), card = judgment.locator('.se-judgments article').filter({ has: page.getByRole('heading', { name: '1 个工具有失败信号', exact: true }) });
    await expect(card.locator('.se-basis')).toHaveText('执行归属：' + label + ' · 独立上下文'); await expect(card).toContainText('首个依据：退出码 7；不等同整个任务失败。'); await expect(judgment).toContainText('已测累计 500ms');
    expect(network.length).toBe(7); expect(network.some(u => /\/payload|cursor=|view=participants/.test(u))).toBe(false);
    await captureDiagnosticScreenshot(page, { path: path.join(out, width + '-viewport.png'), fullPage: false });
    await expect(card.locator('code')).toBeVisible();
    await expect.soft(card.locator('code'), 'default visible command from raw').toHaveText('node synthetic-orphan-check.js --case no-owner');
    const located = page.waitForResponse(r => new URL(r.url()).searchParams.get('target') === diag.firstFailure); await card.getByRole('button', { name: '定位首个失败', exact: true }).click(); await located;
    const tool = page.locator('[data-execution-tool="orphan-command-v52"]'); await expect(tool).toBeFocused(); await expect(tool).toContainText('退出码 7'); await expect(tool).toContainText('500ms');
    const group = tool.locator('xpath=ancestor::*[@data-execution-group][1]'); await expect(group).toContainText('来源未确认'); await expect(group).toContainText('未观察到模型输出'); await captureDiagnosticScreenshot(group, { path: path.join(out, width + '-group.png') }); await captureDiagnosticScreenshot(judgment, { path: path.join(out, width + '-judgment.png') });
    await tool.locator('.se-tool-evidence > summary').click();
    const payloads = [];
    for (const name of ['命令或参数', '执行结果']) {
      await tool.getByRole('button', { name, exact: true }).click(); const modal = page.locator('dialog.payload-modal[open]'); await expect(modal).toBeVisible(); await expect(modal).not.toContainText('Loading payload...'); await expect(modal).toContainText('available'); payloads.push({ name, text: await modal.innerText() });
      if (name === '执行结果') await expect(modal).toContainText('Synthetic recorded error, command not executed');
      else await expect.soft(modal, 'raw standalone input must remain readable').toContainText('{"cmd":"node synthetic-orphan-check.js --case no-owner"}');
      await captureDiagnosticScreenshot(modal, { path: path.join(out, width + '-' + (name === '执行结果' ? 'result' : 'input') + '.png') }); await page.keyboard.press('Escape');
    }
    expect(errors).toEqual([]); expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
    fs.writeFileSync(path.join(out, width + '-actual.json'), JSON.stringify({ data, authority, payloads, network, errors, stableTargetFocus: true, commandsExecuted: false }, null, 2));
    // Explicit selection is separate from the frozen seven-request default budget.
    const key = 'subagent:synthetic-orphan-child-v52';
    const selectedResponse = await request.get(api + '/execution?agent_context=' + encodeURIComponent(key)); expect(selectedResponse.status()).toBe(200);
    const selected = await selectedResponse.json(); fs.writeFileSync(path.join(out, width + '-selected-api.json'), JSON.stringify(selected, null, 2));
    expect.soft(selected.total, 'full-key selected process retains the orphan tool').toBe(1);
    expect.soft(selected.diagnostics.totalTools, 'selected diagnostics have the same child scope').toBe(1);
    const navigation = [];
    const verifyEntry = async (entry, origin) => {
      await expect.soft(entry, origin + ' has a native full-key process entry').toHaveCount(1);
      if (await entry.count() !== 1) { navigation.push({ origin, missingEntry: true }); return; }
      const loaded = page.waitForResponse(r => new URL(r.url()).pathname.endsWith('/execution') && new URL(r.url()).searchParams.get('agent_context') === key);
      await entry.click(); const actual = await (await loaded).json(); expect(actual.total).toBe(1); expect(actual.diagnostics.totalTools).toBe(1);
      expect(actual.items.map(x => x.tool.toolCallId)).toEqual(['orphan-command-v52']); expect(actual.items[0].tool.declaredByCallId).toBe('unknown'); expect(actual.items[0].group.response).toBe(false);
      await expect(judgment).toContainText('已测累计 500ms'); await expect(judgment).toContainText('退出码 7'); await expect(judgment.locator('code').first()).toHaveText('node synthetic-orphan-check.js --case no-owner');
      await captureDiagnosticScreenshot(judgment, { path: path.join(out, width + '-' + origin + '-selected-judgment.png') }); await captureDiagnosticScreenshot(page, { path: path.join(out, width + '-' + origin + '-selected-viewport.png'), fullPage: false });
      await judgment.getByText('直接查看所选过程', { exact: true }).click();
      const selectedTool = page.locator('[data-execution-tool="orphan-command-v52"]'); await expect(selectedTool).toBeVisible();
      await judgment.getByRole('button', { name: '定位首个失败', exact: true }).click(); await expect(selectedTool).toBeFocused();
      await captureDiagnosticScreenshot(selectedTool.locator('xpath=ancestor::*[@data-execution-group][1]'), { path: path.join(out, width + '-' + origin + '-selected-group.png') });
      await selectedTool.locator('.se-tool-evidence > summary').click();
      for (const name of ['命令或参数', '执行结果']) {
        await selectedTool.getByRole('button', { name, exact: true }).click(); const modal = page.locator('dialog.payload-modal[open]'); await expect(modal).toContainText('available'); await expect(modal).toContainText(name === '命令或参数' ? '{"cmd":"node synthetic-orphan-check.js --case no-owner"}' : 'Synthetic recorded error, command not executed'); await captureDiagnosticScreenshot(modal, { path: path.join(out, width + '-' + origin + '-selected-' + (name === '命令或参数' ? 'input' : 'result') + '.png') }); await page.keyboard.press('Escape');
      }
      await page.getByRole('button', { name: '返回协作位置', exact: true }).click(); await expect(entry).toBeFocused(); await captureDiagnosticScreenshot(page, { path: path.join(out, width + '-' + origin + '-returned-viewport.png'), fullPage: false }); navigation.push({ origin, actual, stableFocus: true, inputResult: true, returnFocus: true });
    };
    await page.goto(url); await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true'); await page.waitForFunction(() => collaborationView.sourceStatus === 'ready');
    const collaboration = page.locator('[data-collaboration]');
    await captureDiagnosticScreenshot(collaboration, { path: path.join(out, width + '-relations.png') });
    await verifyEntry(collaboration.locator('[data-collaboration-relation] [data-collaboration-agent="' + key + '"]'), 'relation');
    await collaboration.getByRole('button', { name: '参与者与深层入口', exact: true }).click();
    await expect(collaboration).toContainText('参与上下文');
    const participantText = await collaboration.innerText();
    await captureDiagnosticScreenshot(collaboration, { path: path.join(out, width + '-participants.png') });
    await expect.soft(collaboration, 'participant must not deny an existing tool process').not.toContainText('冻结内容未包含过程');
    await verifyEntry(collaboration.locator('[data-collaboration-agent="' + key + '"]'), 'participant');
    expect(errors).toEqual([]); expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
    fs.writeFileSync(path.join(out, width + '-navigation.json'), JSON.stringify({ key, selected, participantText, navigation, explicitPageNetwork: network.slice(7), errors }, null, 2));

  });
});

for (const width of [1440, 390]) test('hotspot return native task context at ' + width + 'px', async ({ page, request, readLongOperationNormal }) => {
  await readLongOperationNormal(request, false, async ({ base, rootId, children }) => {
    const paths = []; page.on('request', r => { if (r.url().includes('/api/')) paths.push(r.url()); });
    await page.setViewportSize({ width, height: 900 });
    await page.goto(base + '/sessions/codex/' + rootId);
    const section = page.locator('[data-execution-long-operations]');
    await expect(section).toContainText('已测累计 100s');
    await expect(page.locator('[data-collaboration-relation]')).toHaveCount(5);
    const loaded = await page.locator('[data-collaboration-source]').evaluateAll(ns => ns.map(n => JSON.parse(n.dataset.collaborationSource)[0]));
    for (const index of [7, 8]) expect(loaded).not.toContain('subagent:' + children[index]);
    for (const [metric, index, seconds] of [['已测累计', 7, '100s'], ['单次耗时', 8, '35s']]) {
      await section.getByRole('button', { name: metric, exact: true }).click();
      await expect(section).toContainText(seconds);
      const entry = section.locator('[data-execution-long-operation]').first().getByRole('button', { name: '查看任务与往来', exact: true });
      const original = await entry.elementHandle(), before = paths.length;
      await entry.focus(); await page.keyboard.press('Enter');
      await expect(page.locator('[data-collaboration-context]')).toBeFocused();
      await assertSelectedContextIdentity(page, 'subagent:' + children[index]);
      await expect(page.locator('[data-collaboration-items]')).toContainText('Synthetic independent task ' + String(index + 1).padStart(2, '0'));
      const back = page.getByRole('button', { name: '返回耗时位置', exact: true });
      expect(await back.count()).toBe(1);
      await captureDiagnosticScreenshot(page.locator('[data-collaboration]'), { path: test.info().outputPath('hotspot-task-return-' + index + '-' + width + '.png') });
      await back.focus(); await page.keyboard.press('Space');
      await expect(entry).toBeFocused();
      expect(await original.evaluate(n => n === document.activeElement && n.isConnected)).toBe(true);
      expect(paths.slice(before).filter(p => p.includes('/collaboration?'))).toHaveLength(1);
      expect(paths.slice(before)).toHaveLength(1);
      await captureDiagnosticScreenshot(page, { path: test.info().outputPath('hotspot-return-' + index + '-' + width + '.png') });
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await test.info().attach('hotspot-return-network.json', { body: JSON.stringify(paths), contentType: 'application/json' });
  });
});

test('wide collaboration reading keeps independent scopes and command width', async ({ page, request, readLongOperationNormal }) => {
  await readLongOperationNormal(request, false, async ({ base, rootId, children }) => {
    const errors = []; page.on('pageerror', error => errors.push(error.message));
    for (const width of [1920, 1600, 1599, 1440, 390]) {
      await page.setViewportSize({ width, height: 900 });
      await page.goto(base + '/sessions/codex/' + rootId);
      const trace = page.locator('[data-trace-panel]'), host = page.locator('[data-collaboration]');
      await expect(host.locator('[data-collaboration-relation]')).toHaveCount(5);
      await expect(page.locator('[data-execution-long-operations]')).toContainText('已测累计 100s');
      await expect(host.locator('.se-collaboration-layout-note')).toHaveText('独立展示当前协作范围，不与左侧逐行对应；范围见下方导航。');
      expect(await trace.evaluate(node => getComputedStyle(node).display)).toBe(width >= 1600 ? 'grid' : 'block');
      expect(await host.locator('.se-collaboration-layout-note').isVisible()).toBe(width >= 1600);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      if (width >= 1600) {
        const hot = page.locator('[data-execution-long-operation]').first().getByRole('button', { name: '查看任务与往来', exact: true });
        const originalHot = await hot.elementHandle();
        await hot.click(); await expect(host.locator('[data-collaboration-context]')).toBeFocused();
        await assertSelectedContextIdentity(page, 'subagent:' + children[7]);
        await page.getByRole('button', { name: '返回耗时位置', exact: true }).click();
        expect(await originalHot.evaluate(node => node === document.activeElement && node.isConnected)).toBe(true);
        await host.getByRole('button', { name: '全部委派（默认两层）', exact: true }).click();
        const entry = host.locator('[data-collaboration-agent="subagent:' + children[2] + '"]');
        const original = await entry.elementHandle(); await entry.click();
        await expect(page.locator('[data-execution-judgment]')).toBeFocused();
        await expect(page.locator('[data-execution-tool]')).toHaveCount(1);
        const geometry = await page.evaluate(() => {
          const box = selector => { const r = document.querySelector(selector).getBoundingClientRect(); return { top: r.top, bottom: r.bottom, width: r.width }; };
          return { judgment: box('[data-execution-judgment]'), process: box('.se-process'), command: box('.se-action__main code'), collaboration: box('[data-collaboration]'), analysis: box('[data-evidence-analysis]') };
        });
        expect(geometry.process.top - geometry.judgment.bottom).toBeLessThan(70);
        expect(geometry.command.width).toBeGreaterThan(250);
        expect(geometry.analysis.top).toBeGreaterThanOrEqual(Math.max(geometry.process.bottom, geometry.collaboration.bottom));
        const summary = page.locator('[data-execution-tool] details > summary').first();
        await summary.click(); await summary.focus(); const originalSummary = await summary.elementHandle();
        for (const boundary of [1599, 1600]) {
          await page.setViewportSize({ width: boundary, height: 900 });
          expect(await originalSummary.evaluate(node => node === document.activeElement && node.parentElement.open)).toBe(true);
          expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        }
        await page.setViewportSize({ width, height: 900 });
        await captureDiagnosticScreenshot(page, { path: test.info().outputPath('wide-selected-' + width + '.png') });
        await page.getByRole('button', { name: '返回协作位置', exact: true }).click();
        expect(await original.evaluate(node => node === document.activeElement && node.isConnected)).toBe(true);
      }
      await page.getByRole('tab', { name: 'Payload · 原文', exact: true }).click();
      await expect(trace).toBeHidden();
      await page.getByRole('tab', { name: 'Trace', exact: true }).click(); await expect(trace).toBeVisible();
    }
    expect(errors).toEqual([]);
  });
});

test('wide collaboration reading leaves unconfirmed associations full width', async ({ page, request, baseURL }) => {
  const records = [{ type: 'session_meta', payload: { id: 'synthetic-no-collaboration' } },
    { type: 'response_item', payload: { type: 'function_call', call_id: 'only', name: 'exec_command', arguments: '{"cmd":"echo SYNTHETIC_NOT_EXECUTED"}' } },
    { type: 'token_usage_record', payload: { response_id: 'only', usage: { input_tokens: 10, output_tokens: 2 } } },
    { type: 'response_item', payload: { type: 'function_call_output', call_id: 'only', output: 'Synthetic result' } }];
  const imported = await upload(request, baseURL, 'codex', records), api = '/api/imports/' + imported.import_id;
  try {
    await page.setViewportSize({ width: 1920, height: 900 }); await page.goto(imported.detail_url);
    await expect(page.locator('[data-collaboration]')).toContainText('未提供可确认的协作关联');
    await expect(page.locator('[data-execution-tool]')).toHaveCount(1);
    expect(await page.locator('[data-trace-panel]').evaluate(node => getComputedStyle(node).display)).toBe('block');
    const widths = await page.evaluate(() => ['[data-execution-judgment]', '.se-process', '[data-trace-panel]'].map(selector => document.querySelector(selector).getBoundingClientRect().width));
    expect(widths[0]).toBe(widths[2]); expect(widths[1]).toBe(widths[2]);
    expect(await page.locator('.se-collaboration-rail').count()).toBe(1);
  } finally { const response = await request.delete(api, { headers: { Origin: new URL(baseURL).origin } }); expect(response.status()).toBe(204); }
});

test('wide collaboration reading retains late fact reading and native disclosures', async ({ page, request, readLongOperationNormal }) => {
  await readLongOperationNormal(request, false, async ({ base, rootId, api }) => {
    let release, arrived; const gate = new Promise(resolve => { release = resolve; }), arrival = new Promise(resolve => { arrived = resolve; });
    await page.route(api + '/collaboration?**', async route => { const response = await route.fetch(); arrived(); await gate; await route.fulfill({ response }); });
    try {
      await page.setViewportSize({ width: 1600, height: 900 }); await page.goto(base + '/sessions/codex/' + rootId); await arrival;
      const group = page.locator('[data-execution-group]').first(), tool = page.locator('[data-execution-tool]').first();
      await expect(tool).toBeAttached();
      expect(await page.locator('[data-trace-panel]').evaluate(node => getComputedStyle(node).display)).toBe('block');
      const summary = tool.locator('details > summary').first(); await summary.click(); await summary.focus();
      await group.evaluate(node => node.scrollIntoView({ block: 'start' }));
      const original = await summary.elementHandle(), top = await group.evaluate(node => node.getBoundingClientRect().top);
      release(); await expect(page.locator('[data-collaboration].sc-panel')).toBeAttached();
      await expect(page.locator('[data-collaboration-relation]')).toHaveCount(5);
      expect(await page.locator('[data-trace-panel]').evaluate(node => getComputedStyle(node).display)).toBe('grid');
      expect(await original.evaluate(node => node === document.activeElement && node.isConnected && node.parentElement.open)).toBe(true);
      expect(Math.abs(await group.evaluate(node => node.getBoundingClientRect().top) - top)).toBeLessThan(4);
      await captureDiagnosticScreenshot(page, { path: test.info().outputPath('wide-late-reading.png') });
    } finally { release(); await page.unroute(api + '/collaboration?**'); }
  });
});

test('wide collaboration reading retains a partial tool with no later visible anchor', async ({ page, request }) => {
  await withLowFanoutNormal(request, async ({ base, rootId, api }) => {
    let release, arrived; const gate = new Promise(resolve => { release = resolve; }), arrival = new Promise(resolve => { arrived = resolve; });
    await page.route(api + '/collaboration?**', async route => { const response = await route.fetch(); arrived(); await gate; await route.fulfill({ response }); });
    try {
      await page.setViewportSize({ width: 1600, height: 260 }); await page.goto(base + '/sessions/codex/' + rootId); await arrival;
      const tool = page.locator('[data-execution-tool="root-short"]'), group = tool.locator('xpath=ancestor::article[1]');
      await expect(tool).toBeAttached(); await tool.locator('details > summary').click(); await group.locator('.se-group-evidence > summary').click();
      const target = tool.getByRole('button', { name: '命令或参数', exact: true }), original = await target.elementHandle();
      await target.focus(); await tool.evaluate(node => scrollTo(0, node.getBoundingClientRect().top + scrollY + 60));
      const before = await target.evaluate(node => {
        const row = node.closest('[data-execution-tool]').getBoundingClientRect(), rect = node.getBoundingClientRect();
        return { toolTop: row.top, toolBottom: row.bottom, targetTop: rect.top, targetBottom: rect.bottom,
          laterAnchors: Array.from(document.querySelectorAll('[data-execution-tool]')).filter(node => { const r = node.getBoundingClientRect(); return r.top >= 0 && r.top < innerHeight; }).length };
      });
      expect(before.toolTop).toBeLessThan(0); expect(before.toolBottom).toBeGreaterThan(0);
      expect(before.targetTop).toBeGreaterThanOrEqual(0); expect(before.targetBottom).toBeLessThan(260); expect(before.laterAnchors).toBe(0);
      release(); await expect(page.locator('[data-collaboration].sc-panel')).toBeAttached();
      expect(await original.evaluate(node => node === document.activeElement && node.isConnected && node.closest('details').open)).toBe(true);
      await expect(group.locator('.se-group-evidence')).toHaveAttribute('open', '');
      const after = await target.evaluate(node => node.getBoundingClientRect().top);
      await test.info().attach('partial-row-position.json', { body: JSON.stringify({ before, after, delta: after - before.targetTop }), contentType: 'application/json' });
      expect(Math.abs(after - before.targetTop)).toBeLessThan(4);
      await captureDiagnosticScreenshot(page, { path: test.info().outputPath('wide-partial-row.png') });
    } finally { release(); await page.unroute(api + '/collaboration?**'); }
  });
});

for (const boundary of ['metric', 'replacement', 'late', 'retry']) test('hotspot return boundary ' + boundary, async ({ page, request, readLongOperationNormal }) => {
  await readLongOperationNormal(request, false, async ({ base, rootId, children }) => {
    await page.goto(base + '/sessions/codex/' + rootId);
    const section = page.locator('[data-execution-long-operations]');
    const entry = section.locator('[data-execution-long-operation]').first().getByRole('button', { name: '查看任务与往来', exact: true });
    await expect(entry).toBeVisible(); const original = await entry.elementHandle();
    const match = url => url.pathname.endsWith('/collaboration') && url.searchParams.get('selection') === 'subagent:' + children[7];
    let release, arrived, failed = false;
    const gate = new Promise(r => { release = r; }), arrival = new Promise(r => { arrived = r; });
    await page.route(match, async route => {
      const response = await route.fetch();
      if (boundary === 'retry' && !failed) { failed = true; await route.fulfill({ status: 503, body: 'Synthetic transport failure' }); return; }
      arrived(); await gate; await route.fulfill({ response });
    });
    try {
      await entry.click();
      if (boundary === 'retry') {
        const retry = page.locator('[data-collaboration-status]').getByRole('button', { name: 'Retry', exact: true });
        await expect(retry).toBeVisible();
        const back = page.getByRole('button', { name: '返回耗时位置', exact: true });
        await expect(back).toBeVisible(); await retry.click();
      }
      await arrival;
      const elsewhere = page.locator('[data-execution-filter="failed"]');
      if (boundary === 'metric') await section.getByRole('button', { name: '单次耗时', exact: true }).click();
      if (boundary === 'replacement') await original.evaluate(n => n.replaceWith(n.cloneNode(true)));
      if (boundary === 'late' || boundary === 'replacement') await elsewhere.focus();
      release();
      await assertSelectedContextIdentity(page, 'subagent:' + children[7]);
      if (boundary === 'retry') await expect(page.locator('[data-collaboration-context]')).toBeFocused();
      const back = page.getByRole('button', { name: '返回耗时位置', exact: true });
      if (boundary === 'metric' || boundary === 'replacement') {
        await expect(back).toHaveCount(0);
        expect(await original.evaluate(n => n.isConnected)).toBe(false);
      } else {
        await expect(back).toBeVisible();
        if (boundary === 'late') await expect(elsewhere).toBeFocused();
        await back.focus(); await page.keyboard.press('Enter');
        expect(await original.evaluate(n => n === document.activeElement)).toBe(true);
      }
      await captureDiagnosticScreenshot(page, { path: test.info().outputPath('hotspot-return-' + boundary + '.png') });
    } finally { release(); await page.unroute(match); }
  });
});

for (const width of [1440, 390]) for (const mode of ['normal', 'import']) {
  test('selected context authoritative breadcrumb ' + mode + ' ' + width, async ({ page, request, baseURL }) => {
    const read = async ({ base, fixture, url, api }) => {
      const full = await (await request.get(api + '/collaboration?view=exchanges&limit=100')).json();
      const key = 'subagent:' + fixture.ids[0], participant = full.participants.find(row => row.key === key);
      expect(participant.label).toBeTruthy(); expect(participant.label).not.toBe(key);
      await test.info().attach('selected-context-authority.json', { body: JSON.stringify({ key, participant, full }), contentType: 'application/json' });
      const requests = [], errors = []; page.on('request', r => requests.push(r.url())); page.on('pageerror', e => errors.push(e.message));
      await page.setViewportSize({ width, height: 900 }); await page.goto(url);
      const host = page.locator('[data-collaboration]');
      await host.locator('[data-collaboration-participants]').click();
      await host.locator('[data-collaboration-branch="' + key + '"]').click();
      const context = host.locator('[data-collaboration-context]');
      await expect(context).toContainText('所选上下文');
      await captureDiagnosticScreenshot(context, { path: test.info().outputPath('breadcrumb-before-' + mode + '-' + width + '.png') });
      await expect(context.locator('[data-execution-context-short]')).toHaveText(participant.label);
      await expect(context).not.toContainText(key);
      const evidence = host.locator(':scope > details').filter({ has: page.getByText('采集与关联原因', { exact: true }) });
      const beforeEvidence = requests.length;
      await evidence.locator('summary').focus(); await page.keyboard.press('Enter');
      await expect(evidence).toHaveAttribute('open', ''); await expect(evidence.locator('.se-evidence__body')).toContainText(key);
      await evidence.locator('summary').click(); await evidence.locator('summary').click();
      await expect(evidence.locator('.se-evidence__body')).toBeVisible();
      expect(requests.length).toBe(beforeEvidence);
      // UI-only cache/late-label guard: the actual parser authority above is not replaced.
      const stable = await page.evaluate(({ key, label }) => {
        const node = document.querySelector('[data-collaboration-context]'), span = node.querySelector('[data-execution-context-short]');
        const detail = document.querySelector('[data-collaboration] > details'), pageBefore = collaborationView.page, execution = executionView.page;
        const selection = collaborationView.selection, cursor = collaborationView.page.nextCursor, count = document.querySelectorAll('[data-collaboration-relation]').length;
        node.focus(); collaborationView.labels.delete(key); syncExecutionContextLabels(); const fallback = span.textContent;
        collaborationView.labels.set(key, 'Synthetic late authoritative label'); syncExecutionContextLabels(); const late = span.textContent;
        collaborationView.labels.set(key, label); syncExecutionContextLabels();
        return { fallback, late, same: node === document.querySelector('[data-collaboration-context]'), spanSame: span === node.querySelector('[data-execution-context-short]'), focused: document.activeElement === node, open: detail.open, selected: collaborationView.selection === selection, page: collaborationView.page === pageBefore, cursor: collaborationView.page.nextCursor === cursor, execution: executionView.page === execution, count: document.querySelectorAll('[data-collaboration-relation]').length === count, main: executionAgentMarkup('main'), unknown: executionAgentMarkup('subagent:synthetic-unknown-full-key-987654321') };
      }, { key, label: participant.label });
      expect(stable).toMatchObject({ fallback: key, late: 'Synthetic late authoritative label', same: true, spanSame: true, focused: true, open: true, selected: true, page: true, cursor: true, execution: true, count: true });
      expect(stable.main).toContain(full.participants.find(p => p.key === 'main').label);
      expect(stable.unknown).toContain('subagent:synthetic-unknown-full-key-987654321');
      expect(requests.length).toBe(beforeEvidence); expect(errors).toEqual([]);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await captureDiagnosticScreenshot(host, { path: test.info().outputPath('selected-context-' + mode + '-' + width + '.png') });
      await captureDiagnosticScreenshot(page, { path: test.info().outputPath('selected-viewport-' + mode + '-' + width + '.png'), fullPage: false });
      await test.info().attach('selected-context-guard.json', { body: JSON.stringify({ stable, requests, errors }), contentType: 'application/json' });
    };
    if (mode === 'normal') await withFollowupNormal(async ({ base, fixture }) => read({ base, fixture, url: base + '/sessions/codex/' + fixture.rootId, api: base + '/api/sessions/codex/' + fixture.rootId }));
    else {
      const fixture = followupSource(), imported = await upload(request, baseURL, 'codex', fixture.root), api = baseURL + '/api/imports/' + imported.import_id;
      try { await read({ base: baseURL, fixture, url: imported.detail_url, api }); }
      finally { expect((await request.delete(api, { headers: { Origin: new URL(baseURL).origin } })).status()).toBe(204); }
    }
  });
}

// O14: identity remains full-key; only its primary presentation follows actual accepted API authority.
async function assertSelectedContextIdentity(page, key) {
  const context = page.locator('[data-collaboration-context]'), span = context.locator('[data-execution-context-short]');
  await expect(span).toHaveAttribute('data-execution-context-key', key);
  const authority = await page.evaluate(key => {
    const data = collaborationView.page, participant = data.participants.find(row => row.key === key);
    if (participant) return participant.label;
    const row = data.items.find(row => row.target === key || row.actor === key || row.key === key);
    return row?.target === key ? row.targetLabel : row?.actor === key ? row.actorLabel : row?.label;
  }, key);
  expect(authority).toBeTruthy();
  await expect(span).toHaveText(authority);
  await expect(page.locator('[data-collaboration] > details .se-evidence__body')).toContainText(key);
}

for (const width of [1440, 390]) for (const mode of ['normal', 'import']) {
  test('branch direction native outgoing ' + mode + ' ' + width, async ({ page, request, baseURL }) => {
    const read = async ({ fixture, url, api }) => {
      const key = 'subagent:' + fixture.ids[0];
      const get = async selection => { const response = await request.get(api + '/collaboration?view=delegations&selection=' + encodeURIComponent(selection) + '&limit=100'); expect(response.status()).toBe(200); return response.json(); };
      const child = await get(key), main = await get('main');
      expect(child.items).toHaveLength(0); expect(child.inputDeclarationTotal).toBe(3);
      expect(main.items).toHaveLength(11); expect(main.items.every(row => row.actor === 'main')).toBe(true); expect(main.items.some(row => row.target === key)).toBe(true);
      await test.info().attach('branch-direction-actual.json', { body: JSON.stringify({ key, child, main }), contentType: 'application/json' });
      const requests = [], errors = []; page.on('request', r => requests.push(r.url())); page.on('pageerror', e => errors.push(e.message));
      await page.setViewportSize({ width, height: 900 }); await page.goto(url); const host = page.locator('[data-collaboration]');
      const relationBranch = host.locator('[data-collaboration-branch]').first();
      await expect(relationBranch).toHaveText('查看此 Agent 发起的委派');
      await host.locator('[data-collaboration-participants]').click();
      const branch = host.locator('[data-collaboration-branch="' + key + '"]'); await expect(branch).toHaveText('发起的委派');
      const pending = page.waitForResponse(r => r.url().includes('/collaboration?') && new URL(r.url()).searchParams.get('selection') === key);
      await branch.focus(); await page.keyboard.press('Enter'); const actual = await (await pending).json(); expect(actual.items).toEqual(child.items);
      await assertSelectedContextIdentity(page, key);
      await expect(host.locator('[data-collaboration-context]')).toContainText('该上下文发起的委派');
      await expect(host).toContainText('未记录该上下文发起的明确委派，不代表没有工作。可从全部协作往来核对任务、输入或报告。');
      await expect(host).not.toContainText('已记录的追加输入');
      await captureDiagnosticScreenshot(host, { path: test.info().outputPath('branch-empty-' + mode + '-' + width + '.png') });
      await captureDiagnosticScreenshot(page, { path: test.info().outputPath('branch-viewport-' + mode + '-' + width + '.png'), fullPage: false });
      await host.locator('[data-collaboration-participants]').click();
      const response = page.waitForResponse(r => r.url().includes('/collaboration?') && new URL(r.url()).searchParams.get('selection') === 'main');
      await host.locator('[data-collaboration-branch="main"]').click(); const outgoing = await (await response).json();
      const tuples = [...outgoing.items]; expect(tuples).toEqual(main.items.slice(0, tuples.length));
      let nextCursor = outgoing.nextCursor;
      while (nextCursor) {
        const next = page.waitForResponse(r => r.url().includes('/collaboration?') && new URL(r.url()).searchParams.get('cursor') === nextCursor);
        await host.locator('[data-collaboration-pagination] button').click(); const batch = await (await next).json();
        tuples.push(...batch.items); nextCursor = batch.nextCursor; await expect(host.locator('[data-collaboration-relation]')).toHaveCount(tuples.length);
      }
      expect(tuples).toEqual(main.items); await assertSelectedContextIdentity(page, 'main');
      await expect(host.locator('[data-collaboration-context]')).toContainText('该上下文发起的委派');
      await expect(host.locator('[data-collaboration-relation]')).toHaveCount(11);
      await captureDiagnosticScreenshot(host, { path: test.info().outputPath('branch-positive-' + mode + '-' + width + '.png') });
      await host.locator('[data-collaboration-root]').click(); await expect(host.locator('[data-collaboration-context]')).toHaveText('全部委派');
      // UI-only selected empty control: global counts cannot assert selected input facts, even without a hint.
      const before = requests.length;
      const control = await page.evaluate(() => {
        const original = collaborationView.page, key = 'subagent:synthetic-unknown-outgoing-full-key';
        const texts = [0, 9].map(count => { applyCollaborationPage({ ...original, selection: key, items: [], inputDeclarationTotal: count }, false); return document.querySelector('[data-collaboration-items]').textContent; });
        const fallback = document.querySelector('[data-collaboration-context] [data-execution-context-short]').textContent;
        applyCollaborationPage(original, false); return { texts, fallback };
      });
      expect(control.texts[0]).toBe(control.texts[1]); expect(control.texts[0]).toContain('未记录该上下文发起的明确委派'); expect(control.texts[0]).not.toContain('已记录的追加输入'); expect(control.fallback).toBe('subagent:synthetic-unknown-outgoing-full-key');
      expect(requests.length).toBe(before); expect(errors).toEqual([]); expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await test.info().attach('branch-direction-network.json', { body: JSON.stringify({ requests, errors, control }), contentType: 'application/json' });
    };
    if (mode === 'normal') await withFollowupNormal(async ({ base, fixture }) => read({ fixture, url: base + '/sessions/codex/' + fixture.rootId, api: base + '/api/sessions/codex/' + fixture.rootId }));
    else { const fixture = followupSource(), imported = await upload(request, baseURL, 'codex', fixture.root), api = baseURL + '/api/imports/' + imported.import_id;
      try { await read({ fixture, url: imported.detail_url, api }); } finally { expect((await request.delete(api, { headers: { Origin: new URL(baseURL).origin } })).status()).toBe(204); }
    }
  });
}

// O22 主链仍由真实 normal/import parser 生成；不替换成功 DTO。
for (const mode of ['normal', 'import']) for (const width of [390, 1440]) {
  test('collaboration attention precise recorded error ' + mode + ' ' + width, async ({ page, request, baseURL }) => {
    const read = async ({ fixture, url, api }) => {
      const traffic = [], errors = []; page.on('request', r => { if (r.url().startsWith(api + '/')) traffic.push(r.url()); }); page.on('pageerror', e => errors.push(e.message));
      await page.setViewportSize({ width, height: 900 }); await page.goto(url);
      const entry = page.locator('[data-collaboration-attention-open]'), slot = page.locator('[data-collaboration-attention]');
      await expect(entry).toBeVisible(); await expect(slot).toContainText('全冻结范围已记录1条明确追加输入提交错误');
      await expect(page.locator('[data-collaboration-all-exchanges]')).toContainText('声明3条');
      expect(traffic.filter(u => u.includes('/collaboration?'))).toHaveLength(1); expect(traffic.filter(u => u.includes('/payload/'))).toEqual([]);
      const metrics = await page.evaluate(() => ({ tools: executionView.page.diagnostics.totalTools, failures: executionView.page.diagnostics.failures, measured: executionView.page.diagnostics.measuredTools }));
      expect(metrics.tools).toBe(14); expect(metrics.failures).toBe(0); expect(metrics.measured).toBe(0);
      await captureDiagnosticScreenshot(page, { path: test.info().outputPath('attention-default-' + mode + '-' + width + '.png'), fullPage: false });
      const before = traffic.length, response = page.waitForResponse(r => r.url().startsWith(api + '/collaboration?') && new URL(r.url()).searchParams.has('evidence_window'));
      await entry.click(); const result = await (await response).json();
      expect(result.evidenceWindow).toBe('input_submission_error'); expect(result.offset).toBeGreaterThan(20);
      expect(result.items[0]).toMatchObject({ kind: 'input', phase: 'result_report', reason: 'explicit_error', toolId: 'follow-unknown', toolPayloadState: 'unique' });
      const sent = traffic.slice(before).filter(u => u.includes('/collaboration?')); expect(sent).toHaveLength(1);
      const query = new URL(sent[0]).searchParams; expect(Object.fromEntries(query)).toEqual({ view: 'exchanges', selection: '', limit: '20', evidence_window: 'input_submission_error', cursor: result.firstInputSubmissionError.cursor });
      const first = page.locator('[data-collaboration-relation]').first(); await expect(first).toBeFocused(); await expect(first).toContainText('工具报告提交错误');
      expect(await page.locator('[data-collaboration] [data-collaboration-locate]').count()).toBe(0);
      await expect(page.locator('[data-collaboration-pagination]')).toContainText('未载前段');
      await first.locator('summary').click(); await first.getByRole('button', { name: '工具全部已记录 Result', exact: true }).click();
      await expect(page.locator('dialog.payload-modal pre').last()).toContainText('Synthetic rejected input');
      await page.keyboard.press('Escape');
      expect(traffic.filter(u => u.includes('/payload/'))).toHaveLength(1);
      await captureDiagnosticScreenshot(page, { path: test.info().outputPath('attention-error-' + mode + '-' + width + '.png'), fullPage: false });
      await page.locator('[data-collaboration-attention-return]').click(); await expect(entry).toBeFocused();
      await test.info().attach('attention-chain.json', { body: JSON.stringify({ result, metrics, traffic, errors }), contentType: 'application/json' }); expect(errors).toEqual([]);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    };
    if (mode === 'normal') await withFollowupNormal(async ({ base, fixture }) => read({ fixture, url: base + '/sessions/codex/' + fixture.rootId, api: base + '/api/sessions/codex/' + fixture.rootId }));
    else { const fixture = followupSource(), imported = await upload(request, baseURL, 'codex', fixture.root), api = baseURL + '/api/imports/' + imported.import_id;
      try { await read({ fixture, url: imported.detail_url, api }); } finally { expect((await request.delete(api, { headers: { Origin: new URL(baseURL).origin } })).status()).toBe(204); }
    }
  });
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
    const diagnosis = page.locator('[data-execution-judgment]'); await diagnosis.focus(); release();
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
    await page.goto(imported.detail_url); await expect(page.locator('[data-collaboration-all-exchanges]')).toBeVisible();
    expect(await page.evaluate(() => collaborationView.attention.count)).toBe(0); await expect(page.locator('[data-collaboration-attention]')).toBeHidden();
    await page.route('**' + api + '/collaboration?**', async route => { const response = await route.fetch(), body = await response.json(); delete body.inputSubmissionErrorReportTotal; delete body.firstInputSubmissionError; await route.fulfill({ response, json: body }); });
    await page.reload(); await expect(page.locator('[data-collaboration-all-exchanges]')).toBeVisible(); expect(await page.evaluate(() => collaborationView.attention)).toBeNull();
    await expect(page.locator('[data-collaboration-attention]')).toBeHidden();
    await page.unrouteAll({ behavior: 'wait' }); await page.route('**' + api + '/collaboration?**', route => route.fulfill({ status: 500, json: { message: 'Synthetic unavailable' } }));
    await page.reload(); await expect(page.locator('[data-collaboration-status] button')).toHaveText('Retry');
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

test('collaboration attention 1920 late summary preserves half visible tool and diagnosis nodes', async ({ page, request, baseURL }) => {
  const fixture = followupSource(), imported = await upload(request, baseURL, 'codex', fixture.root), api = '/api/imports/' + imported.import_id;
  let release;
  try {
    let seen; const pending = new Promise(resolve => { seen = resolve; }), gate = new Promise(resolve => { release = resolve; });
    let failFirst = true;
    await page.route('**' + api + '/collaboration?**', async route => {
      if (failFirst) { failFirst = false; return route.fulfill({ status: 503, json: { message: 'Synthetic initial collaboration failure' } }); }
      const response = await route.fetch(); seen(); await gate; await route.fulfill({ response });
    });
    await page.setViewportSize({ width: 1920, height: 900 }); await page.goto(imported.detail_url);
    await expect(page.locator('[data-collaboration-status] button')).toHaveText('Retry');
    await page.locator('[data-collaboration-status] button').click(); await pending;
    await expect(page.locator('[data-execution-judgment]')).toContainText('无可用工具时长');
    await page.evaluate(() => {
      const tool = document.querySelector('[data-execution-tool]'); window.attentionTool = tool; window.attentionDiagnosis = document.querySelector('.se-measurement');
      tool.focus(); const rect = tool.getBoundingClientRect(); window.scrollBy(0, rect.top + rect.height / 2); window.attentionTop = tool.getBoundingClientRect().top;
    });
    release(); await expect(page.locator('[data-collaboration-attention-open]')).toBeAttached();
    const stable = await page.evaluate(() => ({ tool: attentionTool === document.querySelector('[data-execution-tool]'), diagnosis: attentionDiagnosis === document.querySelector('.se-measurement'), focused: document.activeElement === attentionTool, delta: attentionTool.getBoundingClientRect().top - attentionTop }));
    expect(stable).toMatchObject({ tool: true, diagnosis: true, focused: true }); expect(Math.abs(stable.delta)).toBeLessThan(2);
    await page.evaluate(() => window.scrollTo(0, 0)); await expect(page.locator('[data-collaboration-attention-open]')).toBeInViewport();
    await captureDiagnosticScreenshot(page, { path: test.info().outputPath('attention-default-1920.png'), fullPage: false });
    const nodes = await page.evaluate(() => {
      const slot = document.querySelector('[data-collaboration-attention]'), entry = slot.querySelector('button'), pageBefore = executionView.page;
      applyExecutionPage(pageBefore, true);
      return { slot: slot === document.querySelector('[data-collaboration-attention]'), entry: entry === document.querySelector('[data-collaboration-attention-open]') };
    }); expect(nodes).toEqual({ slot: true, entry: true });
    await test.info().attach('attention-wide-stability.json', { body: JSON.stringify({ stable, nodes }), contentType: 'application/json' });
  } finally { if (release) release(); await page.unrouteAll({ behavior: 'wait' }); expect((await request.delete(api, { headers: { Origin: new URL(baseURL).origin } })).status()).toBe(204); }
});

// Duplicate/unknown-owner parser attempts are retained in qualification-first/second logs;
// those qualification boundaries are asserted in the explicitly UI-only matrix above, not mislabeled actual.
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
    await page.keyboard.press('Escape'); expect(traffic).toHaveLength(1);
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
    const row = page.locator('[data-execution-tool="wait-0"]');
    await row.locator('.se-tool-evidence > summary').click();
    await row.getByRole('button', { name: '执行结果', exact: true }).click();
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
    await row.getByRole('button', { name: '执行结果', exact: true }).click();
    await expect(unitemized).toContainText('已截断；包含关系未确认');
    await expect(unitemized.locator('pre')).toHaveText(partial);
    await expect(original).not.toHaveAttribute('open');
    await original.locator(':scope > summary').click();
    await original.locator('[data-tool-result-original] > summary').click();
    await modal.getByRole('button', { name: '复制原始载荷', exact: true }).click();
    expect(await page.evaluate(() => window.syntheticResultCopies)).toEqual([expected, partial]);
  } finally {
    expect((await request.delete(api)).status()).toBe(204);
  }
});
