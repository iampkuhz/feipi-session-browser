const { test, expect } = require('@playwright/test');

const { executionSourceRecords } = require('../fixtures/generate-session-fixtures');
const { createHash } = require('crypto');
let detail;
let api;
test.beforeEach(async ({ request, baseURL }) => {
  api = undefined;
  const response = await request.post('/api/imports', {
    headers: { Origin: new URL(baseURL).origin },
    multipart: { source: 'codex', file: { name: 'synthetic-execution.jsonl', mimeType: 'application/x-ndjson',
      buffer: Buffer.from(executionSourceRecords().map(JSON.stringify).join('\n') + '\n') } },
  });
  expect(response.status()).toBe(201);
  const result = await response.json();
  detail = result.detail_url;
  api = '/api/imports/' + result.import_id;
});
test.afterEach(async ({ request, baseURL }) => {
  if (api) expect((await request.delete(api, { headers: { Origin: new URL(baseURL).origin } })).status()).toBe(204);
});

// TASK-75 唯一原始合成源，固定字节以复用只读审查原点。
function sameToolSlowSource() {
  const tools = [{ id: 'same-exec-build', cmd: 'node synthetic-build.js --mode production', nanos: 40e9 }];
  for (let i = 1; i <= 20; i++) tools.push({ id: 'same-exec-short-' + String(i).padStart(2, '0'), cmd: 'printf "synthetic-short-' + String(i).padStart(2, '0') + '"', nanos: 5e7 });
  tools.push({ id: 'same-exec-test', cmd: 'node synthetic-test.js --suite integration', nanos: 35e9 });
  const records = [];
  const add = (type, payload) => records.push({ synthetic: true, type, timestamp: new Date(Date.parse('2026-04-24T10:00:00Z') + records.length * 1000).toISOString(), payload });
  add('session_meta', { id: '424ef7c5-0c60-49a7-bb9c-f7a9330c2264', cwd: '/synthetic/same-exec', source: 'cli' });
  add('turn_context', { turn_id: 'synthetic-same-exec-turn', model: 'synthetic-codex' });
  add('response_item', { type: 'message', role: 'user', content: [{ type: 'input_text', text: '合成：同一 exec 工具的 build 和 test 不同脚本；仅阅读记录，不实际执行。' }] });
  tools.forEach((t, i) => {
    add('response_item', { type: 'function_call', call_id: t.id, name: 'exec_command', arguments: JSON.stringify({ cmd: t.cmd }) });
    add('token_usage_record', { response_id: 'synthetic-same-exec-response-' + (i + 1), turn_id: 'synthetic-same-exec-turn', usage: { input_tokens: 100, output_tokens: 20 } });
    add('response_item', { type: 'function_call_output', call_id: t.id, output: 'SYNTHETIC_RESULT:' + t.id + '; recorded output only, not timing evidence.' });
    add('event_msg', { type: 'exec_command_end', call_id: t.id, process_id: 'synthetic-process-' + (i + 1), duration: { secs: Math.floor(t.nanos / 1e9), nanos: t.nanos % 1e9 }, status: 'completed', exit_code: 0 });
  });
  const raw = Buffer.from(records.map(JSON.stringify).join('\n') + '\n');
  expect(createHash('sha256').update(raw).digest('hex')).toBe('447ccfe8d5566a3b0b62f2d4e662658c90332c848b3e2fc198bb933c7e8d10b4');
  return raw;
}

for (const width of [1440, 390]) {
  test(`same tool slow calls reveal the off-page script at ${width}px`, async ({ page, request, baseURL }) => {
    const response = await request.post('/api/imports', { headers: { Origin: new URL(baseURL).origin }, multipart: { source: 'codex', file: { name: 'synthetic-same-exec.jsonl', mimeType: 'application/x-ndjson', buffer: sameToolSlowSource() } } });
    expect(response.status()).toBe(201);
    const imported = await response.json();
    const importedApi = '/api/imports/' + imported.import_id;
    try {
      const paths = [];
      page.on('request', r => { if (r.url().includes(importedApi)) paths.push(new URL(r.url())); });
      await page.setViewportSize({ width, height: width === 390 ? 900 : 1000 });
      await page.goto(imported.detail_url);
      await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
      const card = page.locator('[data-execution-workload]');
      await expect(card).toContainText('已测累计 76s');
      await expect(card).toContainText('单次已测最长 40s · 已测 22/22 次');
      const judgment = page.locator('[data-execution-judgment]');
      await page.evaluate(() => document.fonts.ready);
      const geometry = await judgment.evaluate(root => {
        const box = element => {
          const r = element.getBoundingClientRect();
          return { y: r.y + scrollY, height: r.height, text: element.textContent.trim() };
        };
        const card = root.querySelector('[data-execution-workload]');
        const title = card.querySelector('h3').firstChild;
        const range = document.createRange();
        const start = title.textContent.indexOf('76s');
        range.setStart(title, start);
        range.setEnd(title, start + 3);
        return { scrollY, first76sY: range.getBoundingClientRect().y + scrollY,
          representative: box(card.querySelector('code')), processTitle: box(document.querySelector('.se-process h2')),
          cardHeight: card.getBoundingClientRect().height,
          status: box(root.querySelector(':scope > .se-judgments article') || root.querySelector(':scope > .se-basis')),
          hints: [...root.querySelectorAll('.se-basis')].filter(n => n.getBoundingClientRect().height > 0).map(box) };
      });
      await test.info().attach(`first-glance-${width}.json`, { body: JSON.stringify(geometry, null, 2), contentType: 'application/json' });
      await page.screenshot({ path: test.info().outputPath(`first-glance-default-${width}.png`) });
      const first = await (await request.get(importedApi + '/execution')).json();
      const next = await (await request.get(importedApi + '/execution?cursor=' + encodeURIComponent(first.nextCursor))).json();
      await test.info().attach(`first-glance-execution-${width}.json`, { body: JSON.stringify({ first, next }), contentType: 'application/json' });
      await expect(judgment.locator(':scope > .se-judgments')).toHaveCount(0);
      await expect(judgment.locator(':scope > .se-basis').filter({ hasText: '未观察到工具失败；不证明任务成功或记录完整。' })).toBeVisible();
      const basis = judgment.locator(':scope > .se-basis').filter({ hasText: '模型耗时未测量' });
      await expect(basis).toBeVisible();
      await expect(basis).toHaveText('模型耗时未测量；累计非墙钟或关键路径；— 未知，不是零。');
      const measurement = judgment.locator('.se-measurement');
      await expect(measurement).not.toHaveAttribute('open');
      const complete = measurement.locator('p').filter({ hasText: '日志未明确记录时，异步任务状态未知' });
      await expect(complete).not.toBeVisible();
      await measurement.locator('summary').click();
      await expect(complete).toBeVisible();
      await expect(complete).toContainText('工具结果、wait/poll 返回或子任务完成均不证明整个任务完成');
      await measurement.locator('summary').click();
      await expect(page.locator('[data-execution-tool]')).toHaveCount(20);
      await expect(page.locator('[data-execution-tool="same-exec-test"]')).toHaveCount(0);
      const details = card.locator('[data-execution-slowest]');
      await page.screenshot({ path: test.info().outputPath(`same-tool-default-${width}.png`) });
      await expect(details).toHaveCount(1);
      await expect(details).not.toHaveAttribute('open');
      expect(await card.evaluate(n => n.getBoundingClientRect().height)).toBeLessThan(220);
      const slow = details.locator('[data-execution-slow-call="same-exec-test"]');
      await expect(slow).not.toBeVisible();
      expect(paths.filter(u => /\/execution$/.test(u.pathname))).toHaveLength(1);
      expect(paths.some(u => /\/payload\/|\/attribution\//.test(u.pathname))).toBe(false);
      await details.locator('summary').click();
      await expect(slow).toBeVisible();
      await expect(slow).toContainText('node synthetic-test.js --suite integration');
      await expect(slow).toContainText('35s');
      await expect(details).toContainText('前 3 项（含上方代表）');
      await expect(details).toContainText('非全部慢项');
      await expect(details.locator('[data-execution-slow-call]')).toHaveCount(2);
      await expect(details.locator('[data-execution-slow-call="same-exec-build"]')).toHaveCount(0);
      expect(paths.filter(u => /\/execution$/.test(u.pathname))).toHaveLength(1);
      expect(paths.some(u => /\/payload\/|\/attribution\//.test(u.pathname))).toBe(false);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await card.screenshot({ path: test.info().outputPath(`same-tool-expanded-${width}.png`) });
      await slow.getByRole('button', { name: '定位此动作', exact: true }).click();
      const row = page.locator('[data-execution-tool="same-exec-test"]');
      await expect(row).toBeFocused();
      await expect(row.locator('.se-duration')).toHaveText('35s');
      const executions = paths.filter(u => /\/execution$/.test(u.pathname));
      expect(executions).toHaveLength(2);
      expect(executions[1].searchParams.get('target')).toBe('same-exec-test');
      expect(executions.some(u => u.searchParams.has('cursor'))).toBe(false);
      await expect(page.locator('[data-execution-tool]')).toHaveCount(1);
      await row.locator('summary').click();
      for (const [label, kind, text] of [['命令或参数', 'input', 'node synthetic-test.js --suite integration'], ['执行结果', 'result', 'SYNTHETIC_RESULT:same-exec-test']]) {
        const pending = page.waitForResponse(r => decodeURIComponent(new URL(r.url()).pathname).endsWith('/payload/tool:' + kind + ':same-exec-test'));
        await row.getByRole('button', { name: label, exact: true }).click();
        const payload = await (await pending).json();
        expect(payload).toMatchObject({ callId: 'same-exec-test', status: 'available', truncated: false });
        await expect(page.locator('dialog.payload-modal')).toContainText(text);
        await page.keyboard.press('Escape');
      }
      await row.locator('..').getByRole('button', { name: '模型输出', exact: true }).click();
      await expect(page.locator('dialog.payload-modal')).toContainText('exec_command [same-exec-test]');
      await expect(page.locator('dialog.payload-modal')).toContainText('node synthetic-test.js --suite integration');
      await page.keyboard.press('Escape');
    } finally {
      expect((await request.delete(importedApi, { headers: { Origin: new URL(baseURL).origin } })).status()).toBe(204);
    }
  });
}

// 与 TASK-74 只读对照的两份 synthetic raw JSONL 字节相同，不依赖 ignored 文件。
test('diagnostic presentation keeps zero measurements, gaps and failure priority visible', async ({ page, request }) => {
  const data = await (await request.get(api + '/execution')).json();
  await page.setViewportSize({ width: 390, height: 900 });
  await page.goto(detail);
  await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  const judgment = page.locator('[data-execution-judgment]');
  const original = data.diagnostics;
  const work = { ...original.workloads[0], measuredWorkNanos: '0', measuredTools: 1, totalTools: 1,
    unknownTools: 0, otherKindTools: 0, slowest: [],
    longest: { ...original.workloads[0].longest, durationMs: 0, observation: { durationNanos: 0 } } };
  // 仅调用真实渲染器验证呈现分支；不替换HTTP，也不冒充原始源链验证。
  for (const scenario of ['zero', 'partial', 'unranked', 'truncated', 'unmeasured', 'untrusted', 'failure']) {
    const diag = { ...original, failures: 0, firstFailure: null, firstFailureTool: null,
      totalTools: 1, measuredTools: 1, measuredWorkMs: 0, unrankedTools: 0, workloadGroups: 1, workloads: [work] };
    if (scenario === 'partial') Object.assign(diag, { totalTools: 3, unrankedTools: 2,
      workloads: [{ ...work, totalTools: 3, unknownTools: 1, otherKindTools: 1 }] });
    if (scenario === 'unranked') Object.assign(diag, { totalTools: 2, measuredTools: 2, unrankedTools: 1 });
    if (scenario === 'truncated') Object.assign(diag, { totalTools: 9, measuredTools: 9, workloadGroups: 9,
      workloads: Array.from({ length: 8 }, (_, i) => ({ ...work, name: 'synthetic-tool-' + i })) });
    if (scenario === 'unmeasured') Object.assign(diag, { measuredTools: 0, unrankedTools: 1, workloadGroups: 0, workloads: [] });
    if (scenario === 'untrusted') Object.assign(diag, { unrankedTools: 1, workloadGroups: 0, workloads: [] });
    if (scenario === 'failure') Object.assign(diag, { failures: original.failures,
      firstFailure: original.firstFailure, firstFailureTool: original.firstFailureTool });
    await page.evaluate(diag => applyExecutionPage({ offset: 0, total: 0, items: [], diagnostics: diag }), diag);
    const basis = judgment.locator(':scope > .se-basis').filter({ hasText: '模型耗时未测量' });
    await expect(basis).toBeVisible();
    const firstCard = judgment.locator('[data-execution-workload]').first();
    if (['unmeasured', 'untrusted', 'failure'].includes(scenario)) {
      const status = judgment.locator(':scope > .se-judgments article');
      await expect(status).toBeVisible();
      await expect(basis).toContainText('— 表示来源未知，不是零');
      if (scenario === 'unmeasured') await expect(basis).toContainText('无可用时长');
      if (scenario === 'failure') {
        await expect(status.locator('.se-diagnosis-command')).toBeVisible();
        await expect(status.getByRole('button', { name: '定位首个失败' })).toHaveAttribute('data-execution-locate', original.firstFailure);
        expect(await status.evaluate((n, y) => n.getBoundingClientRect().top < y, (await firstCard.boundingBox()).y)).toBe(true);
      }
    } else {
      await expect(judgment.locator(':scope > .se-judgments')).toHaveCount(0);
      await expect(firstCard.locator('h3')).toContainText('已测累计 0ms');
      await expect(firstCard.locator('p').first()).toBeVisible();
      await expect(basis).toContainText('累计非墙钟或关键路径；— 未知，不是零');
      if (scenario === 'partial') {
        await expect(firstCard.locator('p').first()).toHaveText('单次已测最长 0ms · 已测 1/3 次 · 未知 1 次 · 其他/未确认口径 1 次');
        await expect(basis).toContainText('已测工具 1 / 3；未参与可信累计比较 2 次');
      }
      if (scenario === 'unranked') await expect(basis).toContainText('未参与可信累计比较 1 次');
      if (scenario === 'truncated') await expect(basis).toContainText('仅展示 9 组中的前 8 组（上下文分块，非全局榜）');
    }
    await expect(judgment.locator('.se-measurement')).not.toHaveAttribute('open');
    const visible = await judgment.evaluate(n => n.innerText);
    expect(visible).toContain('模型耗时未测量');
  }
});

function concentrationSource(partial) {
  const name = partial ? 'B-partial' : 'A-full';
  const tools = [{ id: name + '-long', name: 'exec_command', input: { cmd: 'node synthetic-long-task.js' }, nanos: 9e9, process: 'synthetic-long', status: 'completed', exit: 0 }];
  for (let i = 1; i <= 24; i++) tools.push({ id: name + '-wait-' + i, name: 'write_stdin', input: { session_id: 61001, chars: '', yield_time_ms: 500 }, nanos: 5e8, process: 'synthetic-wait-target', status: 'running' });
  if (partial) {
    tools.push({ id: name + '-zero', name: 'write_stdin', input: { session_id: 61001, chars: '', yield_time_ms: 500 }, nanos: 0, process: 'synthetic-wait-target', status: 'running' });
    for (let i = 1; i <= 25; i++) tools.push({ id: name + '-unknown-' + i, name: 'write_stdin', input: { session_id: 62000 + i, chars: '', yield_time_ms: 500 } });
  }
  const records = [];
  const add = (type, payload) => records.push({ synthetic: true, type, timestamp: new Date(Date.parse('2026-04-24T10:00:00Z') + records.length * 1000).toISOString(), payload });
  add('session_meta', { id: partial ? '5a54894a-476a-44e2-bb2f-19fe562e244b' : 'e3ab500b-3cae-4b1b-9ed1-2e237ed256a0', cwd: '/synthetic/concentration', source: 'cli' });
  add('turn_context', { turn_id: 'synthetic-concentration-turn', model: 'synthetic-codex' });
  add('response_item', { type: 'message', role: 'user', content: [{ type: 'input_text', text: '合成：定位已测调用工作量，不实际执行命令，不推断墙钟或模型时间。' }] });
  tools.forEach((t, i) => {
    add('response_item', { type: 'function_call', call_id: t.id, name: t.name, arguments: JSON.stringify(t.input) });
    add('token_usage_record', { response_id: 'synthetic-response-' + name + '-' + i, turn_id: 'synthetic-concentration-turn', usage: { input_tokens: 100, output_tokens: 20 } });
    add('response_item', { type: 'function_call_output', call_id: t.id, output: 'SYNTHETIC_RESULT:' + t.id + '; no timing inference from this text.' });
    if (t.nanos != null) add('event_msg', { type: 'exec_command_end', call_id: t.id, process_id: t.process, duration: { secs: Math.floor(t.nanos / 1e9), nanos: t.nanos % 1e9 }, status: t.status, ...(t.exit != null ? { exit_code: t.exit } : {}) });
  });
  const raw = Buffer.from(records.map(JSON.stringify).join('\n') + '\n');
  expect(createHash('sha256').update(raw).digest('hex')).toBe(partial ? '884438ddb26724cb507568c0f1ac1c0df2ca5bdbe72dee038c1577991e3a9b77' : '2f70664a88c2ad399f9ffc5a4a8160383cbe279329c13ad12a7e7d434fce1ad5');
  return { name, raw };
}

for (const partial of [false, true]) {
  for (const width of [1440, 390]) {
    test(`raw cumulative work concentration partial=${partial} at ${width}px`, async ({ page, request, baseURL }) => {
      const { name, raw } = concentrationSource(partial);
      const r = await request.post('/api/imports', { headers: { Origin: new URL(baseURL).origin }, multipart: { source: 'codex', file: { name: 'synthetic-' + name + '.jsonl', mimeType: 'application/x-ndjson', buffer: raw } } });
      expect(r.status()).toBe(201);
      const imported = await r.json();
      const importedApi = '/api/imports/' + imported.import_id;
      try {
        const data = await (await request.get(importedApi + '/execution')).json();
        expect(data.diagnostics.workloads).toHaveLength(2);
        expect(data.diagnostics.workloads[0]).toMatchObject({ name: 'write_stdin', measuredWorkNanos: '12000000000', measuredTools: partial ? 25 : 24, totalTools: partial ? 50 : 24, unknownTools: partial ? 25 : 0, otherKindTools: 0, longest: { toolCallId: name + '-wait-1', durationMs: 500 } });
        expect(data.diagnostics.workloads[1]).toMatchObject({ name: 'exec_command', measuredWorkNanos: '9000000000', measuredTools: 1, totalTools: 1, longest: { toolCallId: name + '-long', durationMs: 9000 } });
        const paths = [];
        page.on('request', r => { if (r.url().includes(importedApi)) paths.push(new URL(r.url())); });
        await page.setViewportSize({ width, height: width === 390 ? 900 : 1000 });
        await page.goto(imported.detail_url);
        await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
        const judgment = page.locator('[data-execution-judgment]');
        const cards = judgment.locator('[data-execution-workload]');
        await expect(cards).toHaveCount(2);
        await expect(cards.first()).toContainText('write_stdin · 已测累计 12s');
        await expect(cards.first()).toContainText('单次已测最长 500ms');
        await expect(cards.first()).toContainText(partial ? '已测 25/50 次 · 未知 25 次' : '已测 24/24 次');
        for (const card of await cards.all()) {
          await expect(card).not.toContainText('未知 0 次');
          await expect(card).not.toContainText('其他/未确认口径 0 次');
          await expect(card).toContainText('不代表同一命令');
        }
        const comparable = judgment.locator('[data-execution-workloads]');
        await expect(comparable).toHaveCount(1);
        await expect(comparable.locator(':scope > .se-basis')).toHaveText('主会话 · 执行器观测 · 仅本上下文、同口径比较；仅已测，非完整瓶颈，慢不等于异常。');
        await expect(cards.locator('p').filter({ hasText: /完整瓶颈|慢不等于异常/ })).toHaveCount(0);
        const basis = judgment.locator(':scope > .se-basis').filter({ hasText: '模型耗时未测量' });
        await expect(basis).toBeVisible();
        await expect(basis).toContainText('累计非墙钟或关键路径；— 未知，不是零');
        if (partial) {
          await expect(basis).toContainText('已测工具 26 / 51');
          await expect(basis).toContainText('未参与可信累计比较 25 次');
          await expect(cards.first().locator('p').first()).toBeVisible();
        }
        await expect(cards.nth(1)).toContainText('单次已测最长 9s');
        await expect(cards.nth(1).locator('[data-execution-slowest]')).toHaveCount(0);
        expect(paths.filter(url => /\/payload\//.test(url.pathname))).toHaveLength(0);
        expect(paths.filter(url => /\/execution$/.test(url.pathname))).toHaveLength(1);
        await expect(page.locator('[data-execution-tool]')).toHaveCount(20);
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await page.screenshot({ path: test.info().outputPath(`concentration-default-${partial}-${width}.png`) });
        await judgment.screenshot({ path: test.info().outputPath(`concentration-diagnosis-${partial}-${width}.png`) });
        await judgment.getByText('计量说明', { exact: true }).click();
        await expect(judgment.locator('.se-measurement')).toContainText('卡片已测次数仅计本口径，分母为本上下文同名全部调用；代表动作取本类单次最长');
        await judgment.getByText('计量说明', { exact: true }).click();
        for (const [card, id] of [[cards.first(), name + '-wait-1'], [cards.nth(1), name + '-long']]) {
          await card.getByRole('button', { name: '定位此动作', exact: true }).click();
          const row = page.locator('[data-execution-tool="' + id + '"]');
          await expect(row).toBeFocused();
          await row.locator('summary').click();
          await row.getByRole('button', { name: '执行结果', exact: true }).click();
          await expect(page.locator('dialog.payload-modal')).toContainText('SYNTHETIC_RESULT:' + id);
          await page.keyboard.press('Escape');
          await row.locator('..').getByRole('button', { name: '模型输出', exact: true }).click();
          await expect(page.locator('dialog.payload-modal')).toContainText(id);
          await page.keyboard.press('Escape');
        }
      } finally {
        expect((await request.delete(importedApi, { headers: { Origin: new URL(baseURL).origin } })).status()).toBe(204);
      }
    });
  }
}

function waitingActionSource(typed) {
  const tools = typed ? [
    { id: 'waiting-launch', name: 'exec_command', input: { cmd: 'node synthetic-task.js', yield_time_ms: 10 }, preview: 'node synthetic-task.js', status: '执行器：运行中', duration: '2ms', nanos: 2000000 },
    { id: 'waiting-poll', name: 'write_stdin', input: { session_id: 61001, chars: '', yield_time_ms: 1000 }, preview: '等待读取输出 · session 61001', status: '执行器：运行中', duration: '1s', nanos: 1000000000 },
    { id: 'waiting-exit', name: 'write_stdin', input: { session_id: 61001, chars: '', yield_time_ms: 1000 }, preview: '等待读取输出 · session 61001', status: '退出码 0', duration: '100ms', nanos: 100000000, exit: 0 },
  ] : [
    { id: 'waiting-cell-launch', name: 'exec', input: 'text(await tools.exec_command({cmd:"node synthetic-long-task.js"}));', preview: 'text(await tools.exec_command({cmd:"node synthetic-long-task.js"}));' },
    { id: 'waiting-cell-poll', name: 'wait', input: { cell_id: 'cell-A', yield_time_ms: 1000, terminate: false }, preview: '等待脚本返回 · cell-A' },
    { id: 'waiting-cell-stop', name: 'wait', input: { cell_id: 'cell-B', yield_time_ms: 1000, terminate: true }, preview: '{"cell_id":"cell-B","yield_time_ms":1000,"terminate":true}' },
  ];
  const records = executionSourceRecords().slice(0, 3);
  const add = (type, payload) => records.push({ synthetic: true, type, timestamp: new Date(Date.parse('2026-04-24T12:00:00Z') + records.length * 1000).toISOString(), payload });
  tools.forEach((tool, index) => {
    const freeform = typeof tool.input === 'string';
    tool.result = 'Synthetic result ' + tool.id + ': Script completed; exit 0; Wall time 5 seconds (text is not typed observation).';
    add('response_item', { type: freeform ? 'custom_tool_call' : 'function_call', call_id: tool.id, name: tool.name, ...(freeform ? { input: tool.input } : { arguments: JSON.stringify(tool.input) }) });
    add('token_usage_record', { response_id: 'synthetic-waiting-' + index, turn_id: 'synthetic-turn', usage: { input_tokens: 100, output_tokens: 20 } });
    add('response_item', { type: freeform ? 'custom_tool_call_output' : 'function_call_output', call_id: tool.id, output: tool.result });
    if (typed) add('event_msg', { type: 'exec_command_end', call_id: tool.id, process_id: 'synthetic-waiting-process', duration: { secs: Math.floor(tool.nanos / 1e9), nanos: tool.nanos % 1e9 }, status: tool.exit === 0 ? 'completed' : 'running', ...(tool.exit === 0 ? { exit_code: 0 } : {}) });
  });
  return { records, tools };
}

for (const typed of [true, false]) {
  for (const width of [1440, 390]) {
    test(`raw waiting action summaries preserve evidence and boundaries typed=${typed} at ${width}px`, async ({ page, request, baseURL }) => {
      const { records, tools } = waitingActionSource(typed);
      const response = await request.post('/api/imports', {
        headers: { Origin: new URL(baseURL).origin },
        multipart: { source: 'codex', file: { name: 'synthetic-waiting-actions.jsonl', mimeType: 'application/x-ndjson', buffer: Buffer.from(records.map(JSON.stringify).join('\n') + '\n') } },
      });
      expect(response.status()).toBe(201);
      const imported = await response.json();
      const importedApi = '/api/imports/' + imported.import_id;
      try {
        const data = await (await request.get(importedApi + '/execution')).json();
        expect(data.diagnostics.totalTools).toBe(3);
        expect(data.diagnostics.measuredTools).toBe(typed ? 3 : 0);
        expect(data.diagnostics.measuredWorkMs).toBe(typed ? 1102 : 0);
        expect(data.items.map(item => item.tool.toolCallId)).toEqual(tools.map(tool => tool.id));
        expect(new Set(data.items.map(item => item.group.id)).size).toBe(3);
        expect(data.items.map(item => item.tool.executionKind)).toEqual(['javascript', 'tool', 'tool']);
        if (typed) {
          expect(data.items.map(item => item.tool.durationMs)).toEqual([2, 1000, 100]);
          expect(data.items.map(item => item.tool.observation.status)).toEqual(['running', 'running', 'completed']);
          expect(data.items.map(item => item.tool.observation.exitCode)).toEqual([null, null, 0]);
          expect(new Set(data.items.map(item => item.tool.observation.processId)).size).toBe(1);
        } else {
          for (const { tool } of data.items) {
            expect(tool.durationMs).toBeNull(); expect(tool.exitCode).toBeNull(); expect(tool.observation).toBeNull();
          }
        }
        await page.setViewportSize({ width, height: width === 390 ? 900 : 1000 });
        const payloadRequests = [];
        page.on('request', r => { if (/\/payload\//.test(r.url())) payloadRequests.push(r.url()); });
        await page.goto(imported.detail_url);
        await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
        const rows = page.locator('[data-execution-tool]');
        await expect(rows).toHaveCount(3);
        await expect(page.locator('[data-execution-group]')).toHaveCount(3);
        await expect(page.locator('.se-tool-evidence[open]')).toHaveCount(0);
        expect(payloadRequests).toHaveLength(0);
        await page.locator('[data-execution-items]').evaluate(n => { n.scrollIntoView({ block: 'start' }); window.scrollBy(0, -64); });
        await page.screenshot({ path: test.info().outputPath(`raw-waiting-${typed}-${width}.png`) });
        await expect(rows.locator('.se-action__main code')).toHaveText(tools.map(tool => tool.preview));
        await expect(rows.locator('.se-kind')).toHaveText(tools.map(tool => tool.name));
        await expect(rows.locator('.se-status')).toHaveText(tools.map(tool => tool.status || '已记录结果 · 退出未知'));
        await expect(rows.locator('.se-duration')).toHaveText(tools.map(tool => tool.duration || '—'));
        await expect(page.locator('[data-execution-judgment]')).toContainText('不证明任务成功');
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        for (const tool of tools) {
          const row = page.locator('[data-execution-tool="' + tool.id + '"]');
          for (const [kind, label] of [['input', '命令或参数'], ['result', '执行结果']]) {
            await row.locator('summary').click();
            const button = row.getByRole('button', { name: label, exact: true });
            await expect(button).toHaveAttribute('data-payload-id', 'tool:' + kind + ':' + tool.id);
            const loaded = page.waitForResponse(r => decodeURIComponent(new URL(r.url()).pathname).endsWith('/payload/tool:' + kind + ':' + tool.id));
            await button.click();
            const payloadResponse = await loaded;
            expect(payloadResponse.status()).toBe(200);
            const payload = await payloadResponse.json();
            expect(payload.callId).toBe(tool.id); expect(payload.truncated).toBe(false); expect(payload.status).toBe('available');
            if (kind === 'input' && typeof tool.input === 'object') expect(JSON.parse(payload.content)).toEqual(tool.input);
            else expect(payload.content).toBe(kind === 'input' ? tool.input : tool.result);
            const modal = page.locator('dialog.payload-modal');
            await expect(modal).toBeVisible();
            await expect(modal.locator('.sd-payload-loading')).toHaveCount(0);
            await expect(modal).toContainText(kind === 'input' ? (typeof tool.input === 'object' ? Object.keys(tool.input)[0] : tool.input) : tool.result);
            await page.keyboard.press('Escape');
            await row.locator('summary').click();
          }
        }
      } finally {
        expect((await request.delete(importedApi, { headers: { Origin: new URL(baseURL).origin } })).status()).toBe(204);
      }
    });
  }
}

for (const inputRecorded of [true, false]) {
  test(`zero-tool guidance from raw Claude text with input recorded=${inputRecorded}`, async ({ page, request, baseURL }) => {
    const records = [];
    if (inputRecorded) records.push({ synthetic: true, type: 'user', message: { role: 'user', content: 'Synthetic text-only question' } });
    records.push({ synthetic: true, type: 'assistant', message: { role: 'assistant', model: 'synthetic-claude', content: [{ type: 'text', text: 'Synthetic text-only answer' }] } });
    const response = await request.post('/api/imports', {
      headers: { Origin: new URL(baseURL).origin },
      multipart: { source: 'claude_code', file: { name: 'synthetic-text-only.jsonl', mimeType: 'application/x-ndjson',
        buffer: Buffer.from(records.map(JSON.stringify).join('\n') + '\n') } },
    });
    expect(response.status()).toBe(201);
    const imported = await response.json();
    try {
      await page.goto(imported.detail_url);
      await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
      const judgment = page.locator('[data-execution-judgment]');
      await expect(judgment.locator('h3')).toHaveText('此范围未观察到工具调用');
      await expect(judgment.locator('.se-judgments')).toContainText('不证明任务成功');
      await expect(judgment.locator('.se-judgments')).toContainText('可用的模型输出与模型输入');
      await expect(judgment.locator('.se-judgments')).toContainText('未记录内容以页面标注为准');
      await expect(judgment.locator('.se-judgments')).not.toContainText('0 个工具有失败信号');
      await expect(judgment.locator('.se-basis')).toHaveText('模型耗时未测量。');
      await expect(judgment.locator('.se-basis')).toBeVisible();
      await expect(judgment.getByRole('heading', { name: '此范围未观察到工具调用' })).toBeVisible();
      const measurement = judgment.locator('.se-measurement');
      await expect(measurement).not.toHaveAttribute('open');
      const group = page.locator('[data-execution-group]');
      await expect(group).toContainText('Synthetic text-only answer');
      if (inputRecorded) {
        await group.getByRole('button', { name: '模型输入', exact: true }).click();
        await expect(page.locator('dialog.payload-modal')).toContainText('Synthetic text-only question');
        await page.keyboard.press('Escape');
      } else {
        await expect(group).toContainText('模型输入未记录');
        await expect(group.getByRole('button', { name: '模型输入', exact: true })).toHaveCount(0);
      }
      await group.getByRole('button', { name: '模型输出', exact: true }).click();
      await expect(page.locator('dialog.payload-modal')).toContainText('Synthetic text-only answer');
      await page.keyboard.press('Escape');
      await measurement.locator('summary').click();
      await expect(measurement).toContainText('已测工具 0 / 0');
      await expect(measurement).toContainText('wait/poll');
      await expect(measurement).toContainText('不代表完整 provider context');
    } finally {
      expect((await request.delete('/api/imports/' + imported.import_id, { headers: { Origin: new URL(baseURL).origin } })).status()).toBe(204);
    }
  });
}

test('raw Codex end survives actual import, execution API and page without DTO replacement', async ({ page, request }) => {
  await page.goto(detail);
  await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  const response = await request.get(api + '/execution?target=synthetic-action-24');
  const data = await response.json();
  await test.info().attach('raw-import-execution.json', { body: JSON.stringify(data, null, 2), contentType: 'application/json' });
  expect(data.items[0].tool.observation?.durationNanos).toBe(9e9);
  expect(data.diagnostics.measuredTools).toBe(26);
  await expect(page.locator('[data-execution-judgment]')).toContainText('已测工具 26 / 27');
  await expect(page.locator('[data-execution-judgment]')).toContainText('已测最长 9s');
});

for (const width of [1440, 1024, 390]) {
  test(`execution comprehension from raw Codex import at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1100 });
    const requests = [];
    page.on('request', request => requests.push(new URL(request.url()).pathname));
    await page.goto(detail);
    await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
    const judgment = page.locator('[data-execution-judgment]');
    await expect(judgment).toContainText('1 个工具有失败信号');
    await expect(judgment).toContainText('已测最长 9s');
    await expect(judgment).toContainText('已测工具 26 / 27');
    await expect(judgment).toContainText('模型耗时未测量');
    await expect(judgment.locator('.se-diagnosis-command')).toContainText(['node synthetic-failure.js', 'printf "synthetic action 24"']);
    expect((await judgment.locator('.se-judgments').allTextContents()).join('\n')).not.toContain('executor_reported');
    const info = page.locator('[data-session-info]');
    await expect(info).not.toHaveAttribute('open');
    await info.locator('summary').first().focus();
    await page.keyboard.press('Enter');
    await expect(info.getByRole('button', { name: 'Copy session ID', exact: true })).toBeVisible();
    await page.keyboard.press('Enter');
    await expect(info).not.toHaveAttribute('open');
    await info.locator('summary').first().evaluate(node => node.blur());
    await expect(page.locator('[data-execution-tool]')).toHaveCount(20);
    const groups = page.locator('[data-execution-group]');
    await expect(groups.first().locator('[data-execution-tool]')).toHaveCount(3);
    const sourceActions = groups.first().locator('header [data-execution-response-actions]');
    await expect(sourceActions.getByRole('button', { name: '模型输入', exact: true })).toBeVisible();
    await expect(sourceActions.getByRole('button', { name: '模型输出', exact: true })).toBeVisible();
    await expect(groups.first().locator('[data-execution-tool] button').filter({ hasText: /^模型输入$|^模型输出$/ })).toHaveCount(0);
    for (let i = 1; i <= 3; i += 1) {
      await expect(groups.nth(i).locator('[data-execution-tool]')).toHaveCount(1);
    }
    await expect(page.locator('[data-execution-tool="synthetic-action-1"] .se-duration')).toHaveText('0ms');
    await expect(page.locator('[data-execution-tool="synthetic-action-2"] .se-duration')).toHaveText('<1ms');
    await expect(page.locator('[data-execution-tool="synthetic-action-3"] .se-duration')).toHaveText('—');
    await expect(page.locator('[data-execution-tool="synthetic-action-1"] code')).toContainText('printf "first"; printf "second"; node --version');
    if (width >= 1024) expect(await page.locator('[data-execution-tool="synthetic-action-2"]').evaluate(node => node.getBoundingClientRect().height)).toBeLessThanOrEqual(64);
    await expect(page.locator('[data-evidence-analysis]')).not.toHaveAttribute('open');
    expect(requests.filter(url => /\/round\/|\/payload\//.test(url))).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    const overview = test.info().outputPath(`execution-${width}.png`);
    await page.screenshot({ path: overview });
    await test.info().attach(`execution-${width}-synthetic-http`, { path: overview, contentType: 'image/png' });
    await groups.first().evaluate(node => { node.scrollIntoView({ block: 'start' }); window.scrollBy(0, -64); });
    const process = test.info().outputPath(`process-${width}.png`);
    await page.screenshot({ path: process });
    await test.info().attach(`process-${width}-synthetic-http`, { path: process, contentType: 'image/png' });
  });
}

test('global diagnosis locates off-page tools once and exact upstream/output evidence remains lazy', async ({ page }) => {
  const executionRequests = [];
  page.on('request', request => { if (/\/api\/.*\/execution(?:\?|$)/.test(request.url())) executionRequests.push(request.url()); });
  await page.goto(detail);
  await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  await page.getByRole('button', { name: '定位首个失败' }).click();
  const failed = page.locator('[data-execution-tool="synthetic-action-27"]');
  await expect(failed).toBeFocused();
  await expect(failed).toContainText('退出码 7');
  expect(executionRequests).toHaveLength(2);
  expect(executionRequests[1]).toContain('target=synthetic-action-27');
  const source = failed.locator('..');
  const sourceActions = source.locator('header [data-execution-response-actions]');
  await expect(sourceActions.getByRole('button', { name: '模型输入', exact: true })).toBeVisible();
  await expect(sourceActions.getByRole('button', { name: '模型输出', exact: true })).toBeVisible();
  await expect(source.locator('header .se-group-evidence')).not.toHaveAttribute('open');
  await expect(failed.locator('details')).not.toHaveAttribute('open');
  await sourceActions.getByRole('button', { name: '模型输出', exact: true }).click();
  await expect(page.locator('dialog.payload-modal')).toContainText('合成模型输出 25');
  await page.keyboard.press('Escape');
  await sourceActions.getByRole('button', { name: '模型输入', exact: true }).click();
  const input = page.locator('dialog.payload-modal');
  await expect(input).toHaveAttribute('data-loading-payload-id', 'main:req:token_usage_record:synthetic-response-25');
  await expect(input).toContainText('Tool result [synthetic-action-26]');
  await expect(input).toContainText('Synthetic result 26');
  await expect(input).toContainText('不代表完整 provider context');
  await page.keyboard.press('Escape');
  await source.locator('header .se-group-evidence > summary').click();
  await failed.locator('summary').click();
  await expect(source).toContainText('token_usage_record:synthetic-response-25');
  await expect(failed).toContainText('executor_reported');
  const failureShot = test.info().outputPath('execution-failure-evidence-1440.png');
  await page.screenshot({ path: failureShot });
  await test.info().attach('failure-evidence-raw-synthetic-http', { path: failureShot, contentType: 'image/png' });
  await failed.getByRole('button', { name: '执行结果', exact: true }).click();
  await expect(page.locator('dialog.payload-modal')).toContainText('Synthetic failure: exit 7');
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: '定位此动作' }).click();
  await expect(page.locator('[data-execution-tool="synthetic-action-24"]')).toBeFocused();
  await expect(page).toHaveURL(/execution=synthetic-action-24/);
  await page.reload();
  await expect(page.locator('[data-execution-tool="synthetic-action-24"]')).toBeFocused();
});

// 只观察真实 handler 的 Promise；路由屏障控制乱序，不替换 loader 或依赖计时等待。
async function observeExecutionRequests(page) {
  await page.evaluate(() => {
    const load = window.loadExecutionPage;
    window.observedExecutionRequests = [];
    window.loadExecutionPage = function (...args) {
      const pending = load(...args);
      window.observedExecutionRequests.push(pending);
      return pending;
    };
  });
}

async function settleExecutionRequests(page) {
  await page.evaluate(async () => {
    await Promise.allSettled(window.observedExecutionRequests);
    // 包括调用方的 then/catch/finally，不能只等 HTTP response 事件。
    await new Promise(resolve => queueMicrotask(resolve));
  });
}

for (const origin of ['locate', 'continuation']) {
  for (const outcome of [200, 500, 409]) {
    test(`stale ${origin} ${outcome} cannot mutate a newer successful filter`, async ({ page }) => {
      await page.goto(detail);
      await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
      await observeExecutionRequests(page);
      // 已有定位链接也应在成功筛选后清除，不能留一个与列表不符的分享目标。
      await page.evaluate(() => history.replaceState({}, '', location.pathname + '?execution=synthetic-action-1'));
      let release;
      const held = new Promise(resolve => { release = resolve; });
      let started;
      const requested = new Promise(resolve => { started = resolve; });
      await page.route('**/execution?*', async route => {
        const query = new URL(route.request().url()).searchParams;
        if (!(origin === 'locate' ? query.has('target') : query.has('cursor'))) return route.fallback();
        const response = await route.fetch();
        started();
        await held;
        await route.fulfill({ response, status: outcome,
          ...(outcome === 200 ? {} : { json: { message: 'Synthetic obsolete request failure' } }) });
      });
      const pager = page.locator('[data-content-pagination="execution"]');
      if (origin === 'locate') await page.getByRole('button', { name: '定位此动作' }).click();
      else await pager.getByRole('button').click();
      await requested;
      const filter = page.getByRole('button', { name: '失败信号', exact: true });
      await filter.click();
      await expect(page.locator('[data-execution-tool]')).toHaveCount(1);
      await expect(page.locator('[data-execution-status]')).toBeEmpty();
      release();
      await settleExecutionRequests(page);
      await expect(filter).toHaveAttribute('aria-pressed', 'true');
      await expect(filter).toBeFocused();
      await expect(page.locator('[data-execution-tool]')).toHaveAttribute('data-execution-tool', 'synthetic-action-27');
      await expect(page).not.toHaveURL(/execution=/);
      await expect(page.locator('[data-execution-status]')).toBeEmpty();
      await expect(page.locator('[data-execution-pagination]')).toContainText('1–1 / 1');
      await expect(page.locator('[data-execution-pagination] [role="alert"]')).toHaveCount(0);
      await expect(page.locator('[data-execution-pagination] button')).toHaveCount(0);
    });
  }
}

test('stale locate completion cannot clear loading or restore an obsolete pager while the filter is pending', async ({ page }) => {
  await page.goto(detail);
  await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  await observeExecutionRequests(page);
  const releases = {};
  const starts = {};
  const started = Object.fromEntries(['locate', 'filter'].map(kind => [kind, new Promise(resolve => { starts[kind] = resolve; })]));
  const held = Object.fromEntries(['locate', 'filter'].map(kind => [kind, new Promise(resolve => { releases[kind] = resolve; })]));
  await page.route('**/execution?*', async route => {
    const kind = new URL(route.request().url()).searchParams.has('target') ? 'locate' : 'filter';
    const response = await route.fetch();
    starts[kind]();
    await held[kind];
    await route.fulfill({ response });
  });
  await page.getByRole('button', { name: '定位此动作' }).click();
  await started.locate;
  await page.getByRole('button', { name: '失败信号', exact: true }).click();
  await started.filter;
  releases.locate();
  await page.evaluate(async () => {
    await window.observedExecutionRequests[0];
    await new Promise(resolve => queueMicrotask(resolve));
  });
  await expect(page.locator('[data-execution-status]')).toHaveText('正在加载摘要…');
  await expect(page.locator('[data-execution-pagination] button')).toHaveCount(0);
  await expect(page).not.toHaveURL(/execution=/);
  releases.filter();
  await settleExecutionRequests(page);
  await expect(page.locator('[data-execution-tool]')).toHaveCount(1);
  await expect(page.locator('[data-execution-status]')).toBeEmpty();
});

for (const outcome of [500, 409]) {
  test(`current locate ${outcome} retains real Retry or Refresh recovery`, async ({ page }) => {
    await page.goto(detail);
    await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
    let fail = true;
    await page.route('**/execution?*', async route => {
      if (!fail || !new URL(route.request().url()).searchParams.has('target')) return route.fallback();
      await route.fulfill({ status: outcome, json: { message: 'Synthetic current locate failure' } });
    });
    await page.getByRole('button', { name: '定位此动作' }).click();
    const status = page.locator('[data-execution-status]');
    await expect(status).toContainText(outcome === 500 ? 'HTTP 500' : /refresh/i);
    await expect(status.getByRole('button')).toHaveText(outcome === 500 ? 'Retry' : 'Refresh page');
    await expect(page.locator('[data-execution-tool]')).toHaveCount(20);
    fail = false;
    if (outcome === 409) {
      await Promise.all([page.waitForEvent('load'), status.getByRole('button').click()]);
      await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
      await page.getByRole('button', { name: '定位此动作' }).click();
    } else await status.getByRole('button').click();
    await expect(page.locator('[data-execution-tool="synthetic-action-24"]')).toBeFocused();
    await expect(status).toBeEmpty();
    await expect(page).toHaveURL(/execution=synthetic-action-24/);
  });
}

for (const failure of ['server', 'stale', 'missing-generation']) {
  test(`execution continuation rejects ${failure} without merging a bad page`, async ({ page }) => {
    // 导入 UUID 本来是不可变、无 generation header 的范围。仅此故障注入建立有名快照前置条件。
    if (failure === 'missing-generation') {
      await page.route('**/api/imports/*/*', async route => {
        const response = await route.fetch();
        await route.fulfill({ response, headers: { ...response.headers(), 'x-session-index-generation': 'synthetic-named-snapshot' } });
      });
    }
    await page.goto(detail);
    await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
    if (failure === 'missing-generation') await expect(page.locator('body')).toHaveAttribute('data-index-generation', 'synthetic-named-snapshot');
    let recover = false;
    await page.route('**/execution?*', async route => {
      if (recover || !new URL(route.request().url()).searchParams.has('cursor')) return route.fallback();
      const response = await route.fetch();
      const headers = { ...response.headers() };
      delete headers['x-session-index-generation'];
      await route.fulfill({ response, headers, status: failure === 'server' ? 500 : failure === 'stale' ? 409 : 200,
        json: failure === 'missing-generation' ? await response.json() : { message: 'Synthetic page read failure' } });
    });
    const pager = page.locator('[data-content-pagination="execution"]');
    await pager.getByRole('button').click();
    await expect(pager.locator('[role="alert"]')).toContainText(failure === 'stale' ? /refresh/i : failure === 'server' ? /HTTP 500/ : '索引校验信息缺失');
    await expect(page.locator('[data-execution-tool]')).toHaveCount(20);
    await expect(pager.getByRole('button')).toHaveText(failure === 'stale' ? 'Refresh page' : 'Retry');
    if (failure !== 'stale') {
      recover = true;
      await pager.getByRole('button').click();
      await expect(page.locator('[data-execution-tool]')).toHaveCount(27);
    }
  });
}

test('presentation-only: a long single response continues with an explicit stable group boundary', async ({ page }) => {
  await page.route('**/execution*', async route => {
    const url = new URL(route.request().url());
    if (!url.pathname.startsWith('/api/')) return route.continue();
    const tail = url.searchParams.has('cursor');
    url.search = '';
    const response = await route.fetch({ url: url.toString() });
    const data = await response.json();
    const first = data.items[0];
    data.items = Array.from({ length: tail ? 10 : 20 }, (_, i) => ({ group: { ...first.group, toolCount: 30 },
      toolOrdinal: i + (tail ? 21 : 1), tool: { ...first.tool, exitCode: null,
        observation: { ...first.tool.observation, exitCode: null, status: 'completed' },
        toolCallId: 'synthetic-long-' + (i + (tail ? 21 : 1)) } }));
    data.offset = tail ? 20 : 0;
    data.total = 30;
    data.nextCursor = tail ? null : 'synthetic-tail';
    await route.fulfill({ response, json: data });
  });
  await page.goto(detail);
  await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  const groups = page.locator('[data-execution-group]');
  const owner = await groups.first().getAttribute('data-execution-group');
  const firstTool = page.locator('[data-execution-tool]').first();
  await expect(firstTool.locator('.se-status')).toHaveText('执行器：完成');
  await firstTool.locator('summary').click();
  await expect(firstTool).toContainText('状态原值 completed');
  await page.locator('[data-content-pagination="execution"] button').click();
  await expect(page.locator('[data-execution-tool]')).toHaveCount(30);
  await expect(groups).toHaveCount(2);
  await expect(groups.last()).toHaveAttribute('data-execution-group', owner);
  await expect(groups.last().locator('h3')).toContainText('续 · 工具 21 起');
  await expect(page.locator('[data-content-pagination="execution"]')).toContainText('1–30 / 30');
});

for (const width of [1440, 390]) {
  test(`presentation-only: wait/poll and same-name main/child tools remain distinct at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1100 });
    // 明确为 presentation fixture，不声称这些 DTO 来自源 parser 或 typed 异步生命周期。
    await page.route('**/execution', async route => {
      const response = await route.fetch();
      const data = await response.json();
      const sample = data.items[0];
      const group = (id, index, subagentId = '', scope = subagentId ? 'subagent' : 'main') => ({ ...sample.group, id, index,
        label: '本地响应记录', scope, subagentId,
        parentCallId: subagentId ? 'synthetic-main-declare' : '',
        preview: '合成展示场景 · 非原始来源链', inputAvailable: false, outputAvailable: false,
        toolCount: id === 'synthetic-main-declare' ? 2 : 1 });
      const item = (owner, id, name, inputPreview, ordinal = 1) => ({ group: owner, toolOrdinal: ordinal,
        tool: { toolCallId: id, name, inputPreview, durationMs: null,
          scope: owner.scope, subagentId: owner.subagentId, declaredByCallId: owner.id, executionKind: '',
          observation: null, exitCode: null, status: 'success', resultObserved: true } });
      const main = group('synthetic-main-declare', 1);
      data.items = [
        item(main, 'synthetic-main-exec', 'exec_command', 'node synthetic-check.js'),
        item(main, 'synthetic-spawn', 'spawn_agent', 'spawn_agent({"task":"synthetic child check"})', 2),
        item(group('synthetic-poll-response-1', 2), 'synthetic-poll-1', 'wait', 'wait({"ids":["synthetic-child-a"]})'),
        item(group('synthetic-child-response-a', 3, 'synthetic-child-a'), 'synthetic-child-exec-a', 'exec_command', 'node synthetic-check.js'),
        item(group('synthetic-child-response-b', 4, 'synthetic-child-b'), 'synthetic-child-exec-b', 'exec_command', 'node synthetic-check.js'),
        item(group('synthetic-child-response-a2', 5, 'synthetic-child-a'), 'synthetic-child-exec-a2', 'exec_command', 'node synthetic-check.js'),
        item(group('synthetic-child-response-unknown', 6, '', 'subagent'), 'synthetic-child-exec-unknown', 'exec_command', 'node synthetic-check.js'),
        item(group('synthetic-poll-response-2', 7), 'synthetic-poll-2', 'wait', 'wait({"ids":["synthetic-child-a"]})'),
      ];
      data.items[7].tool.status = '';
      data.total = 8;
      data.offset = 0;
      data.nextCursor = null;
      data.diagnostics = { failures: 0, measuredTools: 0, totalTools: 8, measuredKinds: 0,
        measuredWorkMs: 0, longestByName: [] };
      await test.info().attach('synthetic-presentation-only.json', { body: JSON.stringify(data, null, 2), contentType: 'application/json' });
      await route.fulfill({ response, json: data });
    });
    await page.goto(detail);
    await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
    const groups = page.locator('[data-execution-group]');
    // synthetic-child-a/b 共享前缀；默认 header 必须可区分，不能只靠折叠的完整 ID。
    const context = index => groups.nth(index).locator('header > span');
    await expect(context(2)).toHaveText('子 Agent 1 · 独立上下文 · 下发 1 个工具');
    await expect(context(3)).toHaveText('子 Agent 2 · 独立上下文 · 下发 1 个工具');
    await expect(context(4)).toHaveText(await context(2).textContent());
    await expect(context(5)).toHaveText('子 Agent · 身份未记录 · 独立上下文 · 下发 1 个工具');
    for (const index of [2, 3, 4, 5]) await expect(groups.nth(index).locator('header .se-group-evidence')).not.toHaveAttribute('open');
    const judgment = page.locator('[data-execution-judgment]');
    await expect(judgment).toContainText('不证明任务成功');
    await expect(judgment).toContainText('异步任务状态未知');
    await expect(judgment).toContainText('不能据工具或轮询结果判断其仍在运行或已结束');
    await expect(judgment).not.toContainText('typed');
    await expect(judgment).toContainText('wait/poll 返回或子任务完成均不证明整个任务完成');
    const rows = page.locator('[data-execution-tool]');
    await expect(rows).toHaveCount(8);
    await expect(groups).toHaveCount(7);
    expect(new Set(await rows.evaluateAll(nodes => nodes.map(node => node.dataset.executionTool))).size).toBe(8);
    await expect(rows.locator('.se-kind')).toHaveText(['exec_command', 'spawn_agent', 'wait', 'exec_command', 'exec_command', 'exec_command', 'exec_command', 'wait']);
    await expect(rows.locator('.se-duration')).toHaveText(Array(8).fill('—'));
    await expect(page.locator('[data-execution-tool="synthetic-poll-1"] .se-status')).toHaveText('结果信号：完成');
    await expect(page.locator('[data-execution-tool="synthetic-poll-2"] .se-status')).toHaveText('已记录结果 · 退出未知');
    await expect(groups.nth(0).locator('header > span')).toContainText('主会话');
    await expect(page.locator('[data-execution-items]')).not.toContainText(/并行|Parallel/);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    const screenshot = test.info().outputPath(`synthetic-wait-child-${width}.png`);
    await page.locator('[data-trace-panel]').screenshot({ path: screenshot });
    await test.info().attach(`synthetic-presentation-only-${width}`, { path: screenshot, contentType: 'image/png' });
    await groups.nth(0).locator('header .se-group-evidence > summary').click();
    await expect(groups.nth(0).locator('.se-group-evidence')).toContainText('主会话');
    await expect(groups.nth(0).locator('.se-group-evidence')).not.toContainText('synthetic-child-');
    for (const [index, child] of [[2, 'a'], [3, 'b'], [4, 'a']]) {
      await groups.nth(index).locator('header .se-group-evidence > summary').click();
      await expect(groups.nth(index)).toContainText('synthetic-child-' + child);
      await expect(groups.nth(index)).toContainText('父调用 synthetic-main-declare');
      await expect(groups.nth(index).locator('.se-group-evidence')).not.toContainText('synthetic-child-' + (child === 'a' ? 'b' : 'a'));
    }
    await groups.nth(5).locator('header .se-group-evidence > summary').click();
    await expect(groups.nth(5).locator('.se-group-evidence')).toContainText('子 Agent 身份未记录');
    await expect(groups.nth(5).locator('.se-group-evidence')).not.toContainText(/主会话|父调用/);
    await expect(groups.nth(1).locator('[data-execution-tool]')).toHaveAttribute('data-execution-tool', 'synthetic-poll-1');
    await expect(groups.nth(6).locator('[data-execution-tool]')).toHaveAttribute('data-execution-tool', 'synthetic-poll-2');
  });
}

test('execution pagination and filters preserve global coverage, Payload is a separate lazy entry', async ({ page, request }) => {
  const response = await request.get(api + '/execution');
  const first = await response.json();
  expect(first.total).toBe(27);
  expect(first.items).toHaveLength(20);
  expect(JSON.stringify(first)).not.toContain('Synthetic result');
  for (const query of ['limit=0', 'limit=101', 'limit=no', 'cursor=broken', 'status=other']) {
    expect((await request.get(api + '/execution?' + query)).status()).toBe(400);
  }
  expect((await request.get(api + '/execution?status=failed&cursor=' + first.nextCursor)).status()).toBe(400);
  await page.goto(detail);
  await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  await page.locator('[data-content-pagination="execution"] button').click();
  await expect(page.locator('[data-execution-tool]')).toHaveCount(27);
  await page.getByRole('button', { name: '失败信号', exact: true }).click();
  await expect(page.locator('[data-execution-tool]')).toHaveCount(1);
  await expect(page.locator('[data-execution-judgment]')).toContainText('26 / 27');
  await page.getByRole('tab', { name: 'Payload · 原文' }).click();
  await expect(page.locator('[data-payload-index] [data-payload-id]').first()).toBeVisible();
  await page.reload();
  await expect(page.getByRole('tab', { name: 'Payload · 原文' })).toHaveAttribute('aria-selected', 'true');
  await expect(page.locator('[data-payload-index] [data-payload-id]').first()).toBeVisible();
});
