const { test: base, expect } = require('@playwright/test');
const { captureDiagnosticScreenshot } = require('./start-java-fixture-server');

const { executionSourceRecords } = require('../fixtures/generate-session-fixtures');
const { createHash } = require('crypto');
// 只为显式消费默认会话的测试保留一个导入槽；自带数据的测试不上传无关会话。
const test = base.extend({
  executionSession: async ({ request, baseURL }, use) => {
    const headers = { Origin: new URL(baseURL).origin };
    const response = await request.post('/api/imports', {
      headers,
      multipart: { source: 'codex', file: { name: 'synthetic-execution.jsonl', mimeType: 'application/x-ndjson',
        buffer: Buffer.from(executionSourceRecords().map(JSON.stringify).join('\n') + '\n') } },
    });
    expect(response.status()).toBe(201);
    const result = await response.json();
    const api = '/api/imports/' + result.import_id;
    try {
      await use({ detail: result.detail_url, api });
    } finally {
      expect((await request.delete(api, { headers })).status()).toBe(204);
    }
  },
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
      await captureDiagnosticScreenshot(page, { path: test.info().outputPath(`first-glance-default-${width}.png`) });
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
      await captureDiagnosticScreenshot(page, { path: test.info().outputPath(`same-tool-default-${width}.png`) });
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
      await captureDiagnosticScreenshot(card, { path: test.info().outputPath(`same-tool-expanded-${width}.png`) });
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
        const data = await (await pending).json();
        const payload = kind === 'result' ? data.payload : data;
        if (kind === 'result') { expect(data.localResults).not.toBeNull(); expect(data.relations).toBeNull(); }
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
test('diagnostic presentation keeps zero measurements, gaps and failure priority visible', async ({ page, request, executionSession: { api, detail } }) => {
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
      if (scenario === 'unmeasured') {
        await expect(basis).toContainText('无可用工具时长，不能按耗时判断慢项');
        await expect(judgment.locator('.se-measurement')).toContainText('已测工作量之和 无可用时长');
      }
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
        await captureDiagnosticScreenshot(page, { path: test.info().outputPath(`concentration-default-${partial}-${width}.png`) });
        await captureDiagnosticScreenshot(judgment, { path: test.info().outputPath(`concentration-diagnosis-${partial}-${width}.png`) });
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
        await captureDiagnosticScreenshot(page, { path: test.info().outputPath(`raw-waiting-${typed}-${width}.png`) });
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
            const data = await payloadResponse.json();
            const payload = kind === 'result' ? data.payload : data;
            if (kind === 'result') { expect(data.localResults).not.toBeNull(); expect(data.relations).toBeNull(); }
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

test('raw Codex end survives actual import, execution API and page without DTO replacement', async ({ page, request, executionSession: { api, detail } }) => {
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
  test(`execution comprehension from raw Codex import at ${width}px`, async ({ page, executionSession: { detail } }) => {
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
    if (await captureDiagnosticScreenshot(page, { path: overview })) {
      await test.info().attach(`execution-${width}-synthetic-http`, { path: overview, contentType: 'image/png' });
    }
    await groups.first().evaluate(node => { node.scrollIntoView({ block: 'start' }); window.scrollBy(0, -64); });
    const process = test.info().outputPath(`process-${width}.png`);
    if (await captureDiagnosticScreenshot(page, { path: process })) {
      await test.info().attach(`process-${width}-synthetic-http`, { path: process, contentType: 'image/png' });
    }
  });
}

test('global diagnosis locates off-page tools once and exact upstream/output evidence remains lazy', async ({ page, executionSession: { detail } }) => {
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
  const source = failed.locator('xpath=ancestor::*[@data-execution-group][1]');
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
  if (await captureDiagnosticScreenshot(page, { path: failureShot })) {
    await test.info().attach('failure-evidence-raw-synthetic-http', { path: failureShot, contentType: 'image/png' });
  }
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
    test(`stale ${origin} ${outcome} cannot mutate a newer successful filter`, async ({ page, executionSession: { detail } }) => {
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

test('stale locate completion cannot clear loading or restore an obsolete pager while the filter is pending', async ({ page, executionSession: { detail } }) => {
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
  test(`current locate ${outcome} retains real Retry or Refresh recovery`, async ({ page, executionSession: { detail } }) => {
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
  test(`execution continuation rejects ${failure} without merging a bad page`, async ({ page, executionSession: { detail } }) => {
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

test('presentation-only: a long single response continues with an explicit stable group boundary', async ({ page, executionSession: { detail } }) => {
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
  const visibleIdentity = await groups.first().locator('header > h3').textContent();
  expect(visibleIdentity).toMatch(/(?:模型响应记录|本地响应记录) #\d+/);
  const firstTool = page.locator('[data-execution-tool]').first();
  await expect(firstTool.locator('.se-status')).toHaveText('执行器：完成');
  await firstTool.locator('summary').click();
  await expect(firstTool).toContainText('状态原值 completed');
  await page.locator('[data-content-pagination="execution"] button').click();
  await expect(page.locator('[data-execution-tool]')).toHaveCount(30);
  await expect(groups).toHaveCount(2);
  await expect(groups.last()).toHaveAttribute('data-execution-group', owner);
  await expect(groups.last().locator('h3')).toContainText('续 · 工具 21 起');
  await expect(groups.last().locator('h3')).toContainText(visibleIdentity);
  await expect(page.locator('[data-content-pagination="execution"]')).toContainText('1–30 / 30');
});

for (const width of [1440, 390]) {
  test(`presentation-only: wait/poll and same-name main/child tools remain distinct at ${width}px`, async ({ page, executionSession: { detail } }) => {
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
    await expect(context(2)).toHaveText('子上下文 synthetic-child-a · 独立上下文 · 下发 1 个工具');
    await expect(context(3)).toHaveText('子上下文 synthetic-child-b · 独立上下文 · 下发 1 个工具');
    await expect(context(4)).toHaveText(await context(2).textContent());
    await expect(context(2)).not.toContainText('子 Agent 1');
    await expect(context(3)).not.toContainText('子 Agent 2');
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
    if (await captureDiagnosticScreenshot(page.locator('[data-trace-panel]'), { path: screenshot })) {
      await test.info().attach(`synthetic-presentation-only-${width}`, { path: screenshot, contentType: 'image/png' });
    }
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

test('execution pagination and filters preserve global coverage, Payload is a separate lazy entry', async ({ page, request, executionSession: { api, detail } }) => {
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


test('说明层级 UI guard counts actual context-kind blocks, not totals or operation rows', async ({ page, request, executionSession: { api, detail } }) => {
  await page.goto(detail); await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  const source = await (await request.get(api + '/execution')).json();
  const guard = await page.evaluate(source => {
    const base = source.diagnostics.workloads[0];
    const row = extra => ({ ...base, ...extra });
    function inspect(workloads, failures, workloadGroups) {
      applyExecutionPage({ ...source, diagnostics: { ...source.diagnostics, totalTools: 10, failures, workloads, workloadGroups } }, false);
      const root = document.querySelector('[data-execution-judgment]');
      return { blocks: root.querySelectorAll('[data-execution-workloads]').length,
        tails: root.innerText.split('仅已测，非完整瓶颈，慢不等于异常。').length - 1,
        shared: root.querySelectorAll('[data-execution-shared-work-basis]').length,
        sources: root.querySelectorAll('[data-execution-delegation-sources]').length,
        note: root.querySelectorAll('.se-source-note').length,
        blockBasis: [...root.querySelectorAll('[data-execution-workloads] > .se-basis')].map(n => n.textContent),
        text: root.innerText };
    }
    const main = { scope: 'main', subagentId: '', kind: 'executor_reported' };
    return {
      same: inspect([row({ ...main, name: 'guard-first' }), row({ ...main, name: 'guard-second' })], 0, 99),
      multi: inspect([row(main), row({ ...main, subagentId: 'guard-child', scope: 'subagent' }), row({ ...main, kind: 'other-confirmed-kind' })], 0, 1),
      failed: inspect([row(main), row({ ...main, subagentId: 'guard-child', scope: 'subagent' })], 1, 2),
      missing: inspect([], 0, 99),
    };
  }, source);
  expect(guard.same).toMatchObject({ blocks: 1, tails: 1, shared: 0, sources: 0, note: 0 });
  expect(guard.same.text).toContain('99 组中的前 8 组');
  expect(guard.multi).toMatchObject({ blocks: 3, tails: 1, shared: 1, sources: 1, note: 1 });
  for (const basis of guard.multi.blockBasis) { expect(basis).toContain('执行器观测 · 仅本上下文、同口径比较'); expect(basis).not.toContain('非完整瓶颈'); }
  expect(guard.failed).toMatchObject({ blocks: 2, tails: 2, shared: 0, sources: 1, note: 1 });
  expect(guard.failed.text).toContain('1 个工具有失败信号');
  expect(guard.missing).toMatchObject({ blocks: 0, tails: 0, shared: 0, sources: 0, note: 0 });
  expect(guard.missing.text).toContain('0 个工具有失败信号');
  expect(guard.missing.text).toContain('已测工作量之和');
  await test.info().attach('explanation-ui-guard.json', { body: JSON.stringify(guard), contentType: 'application/json' });
});


test('记录身份 presentation-only guard preserves unnumbered input, unknown source and plain text', async ({ page, request, executionSession: { api, detail } }) => {
  await page.goto(detail); await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  const data = await (await request.get(api + '/execution')).json();
  await page.evaluate(source => {
    const base = source.items[0].group;
    const variants = [{ label: '输入记录', index: 0, response: false }, { label: '来源未知', index: 0, response: false },
      { label: '本地响应记录', index: 0, response: true }, { label: '模型响应记录', index: 9, response: true }];
    renderExecutionItems(variants.map((extra, i) => ({ group: { ...base, ...extra, id: 'identity-ui-' + i, round: 0,
      toolCount: 0, inputAvailable: false, outputAvailable: false, preview: 'UI identity guard plain text ' + i }, tool: null })), false);
  }, data);
  await expect(page.locator('[data-execution-group] header > h3')).toHaveText(['输入记录', '来源未知', '本地响应记录', '模型响应记录 #9']);
  await expect(page.locator('[data-execution-group] .se-response-text')).toHaveText(Array.from({ length: 4 }, (_, i) => 'UI identity guard plain text ' + i));
  await expect(page.locator('[data-execution-items]')).not.toContainText(/#0|undefined|真实LLM请求/);
  // Presentation-only truth table; these variants are not extra provider/parser evidence.
  await page.evaluate(source => {
    const base = source.items[0].group;
    const variants = [
      { response: true, toolCount: 0, outputAvailable: false },
      { response: true, toolCount: 0, outputAvailable: true },
      { response: true, toolCount: 0, outputAvailable: undefined },
      { response: true, toolCount: 1, outputAvailable: false },
      { response: true, toolCount: 2, outputAvailable: false },
      { response: false, toolCount: 0, outputAvailable: false },
      { response: 1, toolCount: 0, outputAvailable: false }
    ];
    renderExecutionItems(variants.map((extra, i) => ({ group: { ...base, id: 'zero-tools-ui-' + i,
      round: 0, inputAvailable: false, ...extra }, tool: null })), false);
  }, data);
  expect(await page.locator('[data-execution-group] .se-group-context').allTextContents()).toEqual([
    '主会话 · 本地未记录工具声明', '主会话 · 下发 0 个工具', '主会话 · 下发 0 个工具',
    '主会话 · 下发 1 个工具', '主会话 · 下发 2 个工具', '主会话 · 未观察到模型输出', '主会话 · 下发 0 个工具'
  ]);
});

// Same three synthetic role records as mature import-session qoderRoleJsonl; no timestamps/usage converted to duration.
function unmeasuredQoderRoleJsonl() {
  return [
    {
      role: 'user', sessionId: 'hifi-viz-session-001', uuid: 'synthetic-qoder-user',
      timestamp: '2026-06-01T10:00:00Z', cwd: '/synthetic/import-project',
      content: [{ type: 'text', text: 'Synthetic import request: qoder' }],
    },
    {
      role: 'assistant', sessionId: 'hifi-viz-session-001', uuid: 'synthetic-qoder-assistant',
      id: 'synthetic-qoder-message', timestamp: '2026-06-01T10:00:01Z', model: 'synthetic-qoder-model',
      content: [
        { type: 'text', text: 'Synthetic import response: qoder' },
        { type: 'tool_use', id: 'synthetic-tool', name: 'Bash', input: { command: 'echo synthetic-import-tool-input' } },
      ],
      usage: {
        input_tokens: 11, cache_read_input_tokens: 3, cache_creation_input_tokens: 2, output_tokens: 7,
      },
    },
    {
      role: 'user', sessionId: 'hifi-viz-session-001', uuid: 'synthetic-qoder-tool-result',
      timestamp: '2026-06-01T10:00:02Z',
      content: [{ type: 'tool_result', tool_use_id: 'synthetic-tool', content: 'Synthetic tool result: complete original output\nsynthetic-tool-result-end' }],
    },
  ].map((record) => JSON.stringify(record)).join('\n') + '\n';
}

for (const width of [1440, 390]) test('无计时指路 mature Qoder real import at ' + width + 'px', async ({ page, request, baseURL }) => {
  const raw = unmeasuredQoderRoleJsonl();
  const response = await request.post('/api/imports', { headers: { Origin: new URL(baseURL).origin }, multipart: { source: 'qoder', file: { name: 'synthetic-qoder.jsonl', mimeType: 'application/x-ndjson', buffer: Buffer.from(raw) } } });
  expect(response.status()).toBe(201); const imported = await response.json(), importedApi = '/api/imports/' + imported.import_id;
  const requests = []; page.on('request', r => { if (r.url().includes('/api/')) requests.push(r.url()); });
  try {
    const actual = await (await request.get(importedApi + '/execution')).json();
    expect(actual.diagnostics).toMatchObject({ totalTools: 1, failures: 0, measuredTools: 0, unrankedTools: 1, workloads: [] });
    await page.setViewportSize({ width, height: 900 }); await page.goto(imported.detail_url); await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
    const judgment = page.locator('[data-execution-judgment]'), basis = judgment.locator(':scope > .se-basis');
    expect((await basis.textContent()).startsWith('无可用工具时长，不能按耗时判断慢项；先查看下方操作与结果证据。')).toBe(true); // Fast original red; native source, no DTO replacement.
    await expect(basis).toContainText('已测工具 0 / 1'); await expect(basis).toContainText('未参与可信累计比较 1 次');
    await expect(basis).toContainText('模型耗时未测量'); await expect(basis).toContainText('— 表示来源未知，不是零'); await expect(basis).toContainText('工具返回不证明整个任务完成');
    await expect(basis).not.toContainText('异步任务状态未知');
    await expect(judgment.locator('.se-judgments')).toContainText('未观察到工具失败；不证明任务成功或记录完整');
    await expect(judgment.locator(':scope > .se-judgments article h3')).toHaveText('无可用工具时长');
    const measurement = judgment.locator('.se-measurement'); await expect(measurement).not.toHaveAttribute('open', '');
    expect(requests.some(url => url.includes('/payload/'))).toBe(false); expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await captureDiagnosticScreenshot(page, { path: test.info().outputPath('qoder-default-' + width + '.png'), fullPage: true });
    await measurement.locator('summary').click(); await expect(measurement).toContainText('不是墙钟时间或关键路径'); await expect(measurement).toContainText('工具结果、wait/poll 返回或子任务完成均不证明整个任务完成'); await expect(measurement).toContainText('异步任务状态未知'); await expect(measurement).toContainText('不能据工具或轮询结果判断其仍在运行或已结束');
    const tool = page.locator('[data-execution-tool="synthetic-tool"]'); await tool.locator('.se-tool-evidence > summary').click();
    await tool.getByRole('button', { name: '命令或参数', exact: true }).click(); await expect(page.locator('dialog.payload-modal pre').last()).toContainText('echo synthetic-import-tool-input'); await page.keyboard.press('Escape');
    await tool.getByRole('button', { name: '执行结果', exact: true }).click(); await expect(page.locator('dialog.payload-modal pre').last()).toHaveText('Synthetic tool result: complete original output\nsynthetic-tool-result-end'); await page.keyboard.press('Escape');
    await test.info().attach('qoder-source-api.json', { body: JSON.stringify({ raw, actual, width }), contentType: 'application/json' });
  } finally { expect((await request.delete(importedApi, { headers: { Origin: new URL(baseURL).origin } })).status()).toBe(204); }
});

// UI-only guards for the AND predicate; these synthetic diagnostics are not parser claims.
test('无计时指路 UI-only AND boundary preserves zero, partial, untrusted, no-tool and failure branches', async ({ page, request, executionSession: { api, detail } }) => {
  const original = await (await request.get(api + '/execution')).json();
  await page.goto(detail); await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  const results = await page.evaluate(original => {
    const source = original.diagnostics, work = { ...source.workloads[0], measuredWorkNanos: '0', measuredTools: 1, totalTools: 1, unknownTools: 0, otherKindTools: 0, slowest: [], longest: { ...source.workloads[0].longest, durationMs: 0, observation: { durationNanos: 0 } } };
    const scenarios = {
      eligible: { totalTools: 1, failures: 0, measuredTools: 0, workloads: [], unrankedTools: 1, workloadGroups: 0 },
      noTools: { totalTools: 0, failures: 0, measuredTools: 0, workloads: [], unrankedTools: 0, workloadGroups: 0 },
      failedUnmeasured: { totalTools: 1, failures: 1, measuredTools: 0, workloads: [], unrankedTools: 1, workloadGroups: 0 },
      measuredZero: { totalTools: 1, failures: 0, measuredTools: 1, workloads: [work], unrankedTools: 0, workloadGroups: 1 },
      partial: { totalTools: 3, failures: 0, measuredTools: 1, workloads: [{ ...work, totalTools: 3, unknownTools: 1, otherKindTools: 1 }], unrankedTools: 2, workloadGroups: 1 },
      untrusted: { totalTools: 1, failures: 0, measuredTools: 1, workloads: [], unrankedTools: 1, workloadGroups: 0 },
      hasWorkloadsDespiteZeroCount: { totalTools: 1, failures: 0, measuredTools: 0, workloads: [work], unrankedTools: 1, workloadGroups: 1 }
    };
    return Object.entries(scenarios).map(([scenario, fields]) => {
      applyExecutionPage({ ...original, diagnostics: { ...source, ...fields } });
      const host = document.querySelector('[data-execution-judgment]');
      return { scenario, title: host.querySelector(':scope > .se-judgments article h3')?.textContent || null, basis: Array.from(host.querySelectorAll(':scope > .se-basis')).map(n => n.textContent).join(' '), text: host.textContent, details: host.querySelector('.se-measurement').textContent, firstFailure: host.querySelector('[data-execution-locate]')?.dataset.executionLocate, cards: host.querySelectorAll('[data-execution-workload]').length };
    });
  }, original);
  for (const result of results) expect(result.basis.includes('不能按耗时判断慢项'), result.scenario).toBe(result.scenario === 'eligible');
  const by = Object.fromEntries(results.map(r => [r.scenario, r]));
  expect(Object.fromEntries(results.map(r => [r.scenario, r.title]))).toEqual({ eligible: '无可用工具时长', noTools: '此范围未观察到工具调用', failedUnmeasured: '1 个工具有失败信号', measuredZero: null, partial: null, untrusted: '0 个工具有失败信号', hasWorkloadsDespiteZeroCount: null });
  expect(by.eligible.basis).toContain('已测工具 0 / 1'); expect(by.eligible.basis).toContain('未参与可信累计比较 1 次'); expect(by.eligible.details).toContain('异步任务状态未知');
  expect(by.noTools.text).toContain('此范围未观察到工具调用'); expect(by.noTools.basis).toBe('模型耗时未测量。');
  expect(by.failedUnmeasured.basis).toContain('不是墙钟时间或关键路径'); expect(by.failedUnmeasured.text).toContain('1 个工具有失败信号'); expect(by.failedUnmeasured.firstFailure).toBe(original.diagnostics.firstFailure);
  expect(by.measuredZero.text).toContain('已测累计 0ms'); expect(by.measuredZero.cards).toBe(1);
  expect(by.partial.basis).toContain('已测工具 1 / 3'); expect(by.partial.text).toContain('未知 1 次'); expect(by.partial.text).toContain('其他/未确认口径 1 次');
  expect(by.untrusted.basis).toContain('已测工作量之和'); expect(by.untrusted.basis).toContain('不能据工具或轮询结果判断其仍在运行或已结束');
  expect(by.hasWorkloadsDespiteZeroCount.cards).toBe(1);
  await test.info().attach('unmeasured-and-ui-guards.json', { body: JSON.stringify(results), contentType: 'application/json' });
});

// Exact ten-record O9.3 raw source; recorded command is never executed.
const resultOccurrenceRaw = "{\"synthetic\":true,\"type\":\"session_meta\",\"timestamp\":\"2026-04-24T11:00:00Z\",\"payload\":{\"id\":\"synthetic-result-occurrences-v98\",\"cwd\":\"/synthetic/result-occurrences\",\"source\":\"cli\"}}\n{\"synthetic\":true,\"type\":\"turn_context\",\"timestamp\":\"2026-04-24T11:00:01Z\",\"payload\":{\"turn_id\":\"synthetic-result-occurrences-turn\",\"model\":\"synthetic-codex\"}}\n{\"synthetic\":true,\"type\":\"response_item\",\"timestamp\":\"2026-04-24T11:00:02Z\",\"payload\":{\"type\":\"message\",\"role\":\"user\",\"content\":[{\"type\":\"input_text\",\"text\":\"Synthetic causality audit. Read these records only; never execute the recorded command.\"}]}}\n{\"synthetic\":true,\"type\":\"response_item\",\"timestamp\":\"2026-04-24T11:00:03Z\",\"payload\":{\"type\":\"function_call\",\"call_id\":\"synthetic-result-occurrences-tool\",\"name\":\"exec_command\",\"arguments\":\"{\\\"cmd\\\":\\\"printf \\\\\\\"synthetic-result-occurrences\\\\\\\"\\\"}\"}}\n{\"synthetic\":true,\"type\":\"token_usage_record\",\"timestamp\":\"2026-04-24T11:00:04Z\",\"payload\":{\"response_id\":\"synthetic-result-occurrences-F1\",\"turn_id\":\"synthetic-result-occurrences-turn\",\"usage\":{\"input_tokens\":11,\"output_tokens\":2}}}\n{\"synthetic\":true,\"type\":\"response_item\",\"timestamp\":\"2026-04-24T11:00:05Z\",\"payload\":{\"type\":\"function_call_output\",\"call_id\":\"synthetic-result-occurrences-tool\",\"output\":\"SYNTHETIC_RESULT_OCCURRENCE_R1\"}}\n{\"synthetic\":true,\"type\":\"token_usage_record\",\"timestamp\":\"2026-04-24T11:00:06Z\",\"payload\":{\"response_id\":\"synthetic-result-occurrences-F2\",\"turn_id\":\"synthetic-result-occurrences-turn\",\"usage\":{\"input_tokens\":13,\"output_tokens\":3}}}\n{\"synthetic\":true,\"type\":\"response_item\",\"timestamp\":\"2026-04-24T11:00:07Z\",\"payload\":{\"type\":\"function_call_output\",\"call_id\":\"synthetic-result-occurrences-tool\",\"output\":\"SYNTHETIC_RESULT_OCCURRENCE_R2\"}}\n{\"synthetic\":true,\"type\":\"token_usage_record\",\"timestamp\":\"2026-04-24T11:00:08Z\",\"payload\":{\"response_id\":\"synthetic-result-occurrences-F3\",\"turn_id\":\"synthetic-result-occurrences-turn\",\"usage\":{\"input_tokens\":17,\"output_tokens\":5}}}\n{\"synthetic\":true,\"type\":\"event_msg\",\"timestamp\":\"2026-04-24T11:00:09Z\",\"payload\":{\"type\":\"exec_command_end\",\"call_id\":\"synthetic-result-occurrences-tool\",\"process_id\":\"synthetic-result-occurrences-process\",\"duration\":{\"secs\":0,\"nanos\":750000000},\"status\":\"completed\",\"exit_code\":0}}\n";
for (const width of [1440, 390]) {
  test(`result occurrence request causality at ${width}px`, async ({ page, request, baseURL }, testInfo) => {
    const buffer = Buffer.from(resultOccurrenceRaw);
    expect(buffer.length).toBe(2244);
    expect(createHash('sha256').update(buffer).digest('hex')).toBe('07309d407390505e7d31da28c4f230ff2b3aa358ba730ff1a3ec48a320efcac7');
    const response = await request.post('/api/imports', { headers: { Origin: new URL(baseURL).origin }, multipart: { source: 'codex', file: { name: 'synthetic-result-occurrences.jsonl', mimeType: 'application/x-ndjson', buffer } } });
    expect(response.status()).toBe(201);
    const imported = await response.json(), importedApi = '/api/imports/' + imported.import_id;
    const paths = [], errors = [];
    page.on('request', r => { if (r.url().includes(importedApi)) paths.push(r.url()); });
    page.on('pageerror', e => errors.push(String(e)));
    page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
    try {
      await page.setViewportSize({ width, height: 900 });
      await page.goto(imported.detail_url);
      await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
      const execution = await (await request.get(importedApi + '/execution')).json();
      await testInfo.attach('execution.json', { body: JSON.stringify(execution, null, 2), contentType: 'application/json' });
      expect(execution.total).toBe(3);
      expect(execution.items.filter(i => i.tool)).toHaveLength(1);
      expect(execution.items[0].tool).toMatchObject({ declaredByCallId: 'token_usage_record:synthetic-result-occurrences-F1', durationMs: 750, exitCode: 0 });
      expect(execution.diagnostics).toMatchObject({ totalTools: 1, measuredTools: 1, measuredWorkMs: 750, failures: 0 });
      require('fs').writeFileSync(testInfo.outputPath('execution.json'), JSON.stringify(execution, null, 2));
      const tool = page.locator('[data-execution-tool="synthetic-result-occurrences-tool"]');
      await expect(tool).toBeVisible();
      await expect(tool).toContainText('750ms');
      const defaults = paths.slice();
      expect(defaults.some(p => /\/payload\/|\/round\//.test(p))).toBe(false);
      expect(defaults.filter(p => /\/execution(?:\?|$)/.test(p))).toHaveLength(1);
      const group = tool.locator('xpath=ancestor::*[@data-execution-group][1]');
      await group.locator('[data-execution-response-actions]').getByRole('button', { name: '模型输出', exact: true }).click();
      const modal = page.locator('dialog.payload-modal[open]');
      await expect(modal).toContainText('exec_command');
      await captureDiagnosticScreenshot(page, { path: testInfo.outputPath('model-output.png') });
      await page.keyboard.press('Escape');
      await tool.locator('summary').click();
      await tool.getByRole('button', { name: '命令或参数', exact: true }).click();
      await expect(modal).toContainText('printf');
      await captureDiagnosticScreenshot(page, { path: testInfo.outputPath('tool-input.png') });
      await page.keyboard.press('Escape');
      await tool.getByRole('button', { name: '执行结果', exact: true }).click();
      await expect(modal).toContainText('SYNTHETIC_RESULT_OCCURRENCE_R1');
      await expect.soft(modal).toContainText('SYNTHETIC_RESULT_OCCURRENCE_R2');
      await expect(modal.locator('.sd-payload-meta')).toContainText('按记录原文展示；未拆分 output/result 字段');
      await expect(modal).not.toContainText('内容已截断');
      await expect(modal.locator('[data-local-result]')).toHaveCount(2);
      await captureDiagnosticScreenshot(page, { path: testInfo.outputPath('tool-result.png') });
      await page.keyboard.press('Escape');
      await page.locator('[data-evidence-analysis] > summary').click();
      const round = page.locator('[data-trace-round-row]').first();
      await round.locator('[data-action="toggle-round"]').click();
      for (const n of [1, 2, 3]) {
        await page.locator('[data-payload-id="main:req:token_usage_record:synthetic-result-occurrences-F' + n + '"]').click();
        await expect(modal).not.toContainText('Loading payload...');
        await expect(modal).toContainText('不代表完整 provider context');
        if (n > 1) await modal.locator('summary').filter({ hasText: '原始记录' }).click();
        const visibleText = await modal.innerText();
        if (n === 1) expect(visibleText).toContain('Synthetic causality audit');
        for (const r of [1, 2]) {
          if (n === r + 1) expect(visibleText).toContain('SYNTHETIC_RESULT_OCCURRENCE_R' + r);
          else expect(visibleText).not.toContain('SYNTHETIC_RESULT_OCCURRENCE_R' + r);
        }
        await captureDiagnosticScreenshot(page, { path: testInfo.outputPath('F' + n + '-request.png') });
        await page.keyboard.press('Escape');
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      expect(errors).toEqual([]);
      require('fs').writeFileSync(testInfo.outputPath('network.json'), JSON.stringify({ defaults, paths, errors }, null, 2));
      await testInfo.attach('network.json', { body: JSON.stringify({ defaults, paths, errors }, null, 2), contentType: 'application/json' });
    } finally {
      expect((await request.delete(importedApi, { headers: { Origin: new URL(baseURL).origin } })).status()).toBe(204);
    }
  });
}

for (const kind of ['normal', 'import']) for (const width of [1440, 390]) test('zero-tool missing-output boundary ' + kind + ' at ' + width + 'px', async ({ page, request, baseURL }) => {
  async function verify(url, apiBase) {
    const response = await request.get(apiBase + '/execution'); expect(response.status()).toBe(200); const execution = await response.json();
    expect(execution.total).toBe(3); expect(execution.items.filter(item => item.tool)).toHaveLength(1);
    expect(execution.diagnostics).toMatchObject({ totalTools: 1, measuredTools: 1, measuredWorkMs: 750, failures: 0 });
    expect(execution.items[0].tool).toMatchObject({ toolCallId: 'synthetic-result-occurrences-tool', declaredByCallId: 'token_usage_record:synthetic-result-occurrences-F1', durationMs: 750, exitCode: 0 });
    for (const item of execution.items.slice(1)) expect(item.group).toMatchObject({ response: true, toolCount: 0, outputAvailable: false, inputAvailable: true });
    const paths = [], errors = [], record = r => { if (r.url().includes('/api/')) paths.push(r.url()); }; page.on('request', record); page.on('pageerror', e => errors.push(String(e)));
    try {
      await page.setViewportSize({ width, height: 900 }); await page.goto(url); await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true'); await page.waitForLoadState('networkidle');
      await expect(page.locator('[data-execution-group]')).toHaveCount(3); await expect(page.locator('[data-execution-tool]')).toHaveCount(1);
      await expect(page.locator('[data-execution-tool="synthetic-result-occurrences-tool"]')).toContainText('750ms');
      for (const item of execution.items.slice(1)) {
        const group = page.locator('[data-execution-group]').filter({ has: page.locator('h3', { hasText: '#' + item.group.index }) });
        await expect(group).toHaveAttribute('data-execution-group', item.group.id);
        await expect(group.locator('.se-group-context')).toHaveText('主会话 · 本地未记录工具声明');
        await expect(group).not.toContainText('下发 0 个工具'); await expect(group).toContainText('模型输出未记录');
        await expect(group.getByRole('button', { name: '模型输入', exact: true })).toBeVisible();
      }
      expect(paths.some(p => /\/payload(?:s|\/)|\/round\//.test(p))).toBe(false); expect(paths.filter(p => /\/execution(?:\?|$)/.test(p))).toHaveLength(1);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true); expect(errors).toEqual([]);
      await captureDiagnosticScreenshot(page.locator('[data-execution-items]'), { path: test.info().outputPath('zero-tool-missing-output-' + kind + '-' + width + '.png') });
      await test.info().attach('zero-tool-missing-output-api.json', { body: JSON.stringify({ kind, width, execution, paths, errors, sourceSha256: createHash('sha256').update(resultOccurrenceRaw).digest('hex') }), contentType: 'application/json' });
    } finally { page.removeListener('request', record); }
  }
  if (kind === 'normal') await withMainTimingNormal(request, async ({ base, ids }) => verify(base + '/sessions/codex/' + ids[0], base + '/api/sessions/codex/' + ids[0]), [resultOccurrenceRaw]);
  else await importMainTimingRaw(request, baseURL, resultOccurrenceRaw, verify);
});

// Real supported Codex source, byte-identical to the explicit v125 reading.
const mainSourceTimingRaw = "{\"synthetic\":true,\"type\":\"session_meta\",\"timestamp\":\"2026-11-18T00:00:00.000Z\",\"payload\":{\"id\":\"synthetic-explicit-timing-v125\",\"cwd\":\"/synthetic/explicit-timing-reading\",\"source\":\"cli\",\"timestamp\":\"2026-11-18T00:00:00Z\"}}\n{\"synthetic\":true,\"type\":\"turn_context\",\"timestamp\":\"2026-11-18T00:00:01.000Z\",\"payload\":{\"turn_id\":\"synthetic-timed-turn\",\"model\":\"synthetic-codex\"}}\n{\"synthetic\":true,\"type\":\"event_msg\",\"timestamp\":\"2026-11-18T00:00:02.000Z\",\"payload\":{\"type\":\"task_started\",\"turn_id\":\"synthetic-timed-turn\",\"started_at\":\"2026-11-18T00:00:00Z\"}}\n{\"synthetic\":true,\"type\":\"response_item\",\"timestamp\":\"2026-11-18T00:00:03.000Z\",\"payload\":{\"type\":\"message\",\"role\":\"user\",\"content\":[{\"type\":\"input_text\",\"text\":\"Synthetic explicit timing reading. Never execute recorded commands. Task, turn, tools and model are distinct measurements.\"}]}}\n{\"synthetic\":true,\"type\":\"response_item\",\"timestamp\":\"2026-11-18T00:00:04.000Z\",\"payload\":{\"type\":\"message\",\"role\":\"assistant\",\"content\":[{\"type\":\"output_text\",\"text\":\"SYNTHETIC_TIMING_RESPONSE: two tools, no explicit model execution measurement.\"}]}}\n{\"synthetic\":true,\"type\":\"response_item\",\"timestamp\":\"2026-11-18T00:00:05.000Z\",\"payload\":{\"type\":\"function_call\",\"name\":\"exec_command\",\"call_id\":\"synthetic-timing-tool-1\",\"arguments\":\"{\\\"cmd\\\":\\\"printf \\\\\\\"SYNTHETIC_TIMING_TOOL_1_NEVER_EXECUTED\\\\\\\"\\\"}\"}}\n{\"synthetic\":true,\"type\":\"response_item\",\"timestamp\":\"2026-11-18T00:00:06.000Z\",\"payload\":{\"type\":\"function_call\",\"name\":\"exec_command\",\"call_id\":\"synthetic-timing-tool-2\",\"arguments\":\"{\\\"cmd\\\":\\\"printf \\\\\\\"SYNTHETIC_TIMING_TOOL_2_NEVER_EXECUTED\\\\\\\"\\\"}\"}}\n{\"synthetic\":true,\"type\":\"token_usage_record\",\"timestamp\":\"2026-11-18T00:00:07.000Z\",\"payload\":{\"response_id\":\"synthetic-timing-response\",\"turn_id\":\"synthetic-timed-turn\",\"usage\":{\"input_tokens\":100,\"output_tokens\":20}}}\n{\"synthetic\":true,\"type\":\"response_item\",\"timestamp\":\"2026-11-18T00:00:08.000Z\",\"payload\":{\"type\":\"function_call_output\",\"call_id\":\"synthetic-timing-tool-1\",\"output\":\"Synthetic timing result 1. Not executed.\"}}\n{\"synthetic\":true,\"type\":\"event_msg\",\"timestamp\":\"2026-11-18T00:00:09.000Z\",\"payload\":{\"type\":\"exec_command_end\",\"call_id\":\"synthetic-timing-tool-1\",\"process_id\":\"synthetic-timing-process-1\",\"duration\":{\"secs\":1,\"nanos\":0},\"exit_code\":0,\"status\":\"completed\"}}\n{\"synthetic\":true,\"type\":\"response_item\",\"timestamp\":\"2026-11-18T00:00:10.000Z\",\"payload\":{\"type\":\"function_call_output\",\"call_id\":\"synthetic-timing-tool-2\",\"output\":\"Synthetic timing result 2. Not executed.\"}}\n{\"synthetic\":true,\"type\":\"event_msg\",\"timestamp\":\"2026-11-18T00:00:11.000Z\",\"payload\":{\"type\":\"exec_command_end\",\"call_id\":\"synthetic-timing-tool-2\",\"process_id\":\"synthetic-timing-process-2\",\"duration\":{\"secs\":2,\"nanos\":0},\"exit_code\":0,\"status\":\"completed\"}}\n{\"synthetic\":true,\"type\":\"event_msg\",\"timestamp\":\"2026-11-18T00:00:12.000Z\",\"payload\":{\"type\":\"turn_duration\",\"durationMs\":4000}}\n{\"synthetic\":true,\"type\":\"event_msg\",\"timestamp\":\"2026-11-18T00:00:13.000Z\",\"payload\":{\"type\":\"task_complete\",\"turn_id\":\"synthetic-timed-turn\",\"started_at\":\"2026-11-18T00:00:00Z\",\"completed_at\":\"2026-11-18T00:00:10Z\",\"duration_ms\":10000}}\n";
const missingMainSourceTimingRaw = "{\"synthetic\":true,\"type\":\"session_meta\",\"timestamp\":\"2026-11-18T00:00:00.000Z\",\"payload\":{\"id\":\"synthetic-missing-timing-v125\",\"cwd\":\"/synthetic/explicit-timing-reading\",\"source\":\"cli\",\"timestamp\":\"2026-11-18T00:00:00Z\"}}\n{\"synthetic\":true,\"type\":\"turn_context\",\"timestamp\":\"2026-11-18T00:00:01.000Z\",\"payload\":{\"turn_id\":\"synthetic-timed-turn\",\"model\":\"synthetic-codex\"}}\n{\"synthetic\":true,\"type\":\"response_item\",\"timestamp\":\"2026-11-18T00:00:02.000Z\",\"payload\":{\"type\":\"message\",\"role\":\"user\",\"content\":[{\"type\":\"input_text\",\"text\":\"Synthetic explicit timing reading. Never execute recorded commands. Task, turn, tools and model are distinct measurements.\"}]}}\n{\"synthetic\":true,\"type\":\"response_item\",\"timestamp\":\"2026-11-18T00:00:03.000Z\",\"payload\":{\"type\":\"message\",\"role\":\"assistant\",\"content\":[{\"type\":\"output_text\",\"text\":\"SYNTHETIC_TIMING_RESPONSE: two tools, no explicit model execution measurement.\"}]}}\n{\"synthetic\":true,\"type\":\"response_item\",\"timestamp\":\"2026-11-18T00:00:04.000Z\",\"payload\":{\"type\":\"function_call\",\"name\":\"exec_command\",\"call_id\":\"synthetic-timing-tool-1\",\"arguments\":\"{\\\"cmd\\\":\\\"printf \\\\\\\"SYNTHETIC_TIMING_TOOL_1_NEVER_EXECUTED\\\\\\\"\\\"}\"}}\n{\"synthetic\":true,\"type\":\"response_item\",\"timestamp\":\"2026-11-18T00:00:05.000Z\",\"payload\":{\"type\":\"function_call\",\"name\":\"exec_command\",\"call_id\":\"synthetic-timing-tool-2\",\"arguments\":\"{\\\"cmd\\\":\\\"printf \\\\\\\"SYNTHETIC_TIMING_TOOL_2_NEVER_EXECUTED\\\\\\\"\\\"}\"}}\n{\"synthetic\":true,\"type\":\"token_usage_record\",\"timestamp\":\"2026-11-18T00:00:06.000Z\",\"payload\":{\"response_id\":\"synthetic-timing-response\",\"turn_id\":\"synthetic-timed-turn\",\"usage\":{\"input_tokens\":100,\"output_tokens\":20}}}\n{\"synthetic\":true,\"type\":\"response_item\",\"timestamp\":\"2026-11-18T00:00:07.000Z\",\"payload\":{\"type\":\"function_call_output\",\"call_id\":\"synthetic-timing-tool-1\",\"output\":\"Synthetic timing result 1. Not executed.\"}}\n{\"synthetic\":true,\"type\":\"event_msg\",\"timestamp\":\"2026-11-18T00:00:08.000Z\",\"payload\":{\"type\":\"exec_command_end\",\"call_id\":\"synthetic-timing-tool-1\",\"process_id\":\"synthetic-timing-process-1\",\"duration\":{\"secs\":1,\"nanos\":0},\"exit_code\":0,\"status\":\"completed\"}}\n{\"synthetic\":true,\"type\":\"response_item\",\"timestamp\":\"2026-11-18T00:00:09.000Z\",\"payload\":{\"type\":\"function_call_output\",\"call_id\":\"synthetic-timing-tool-2\",\"output\":\"Synthetic timing result 2. Not executed.\"}}\n{\"synthetic\":true,\"type\":\"event_msg\",\"timestamp\":\"2026-11-18T00:00:10.000Z\",\"payload\":{\"type\":\"exec_command_end\",\"call_id\":\"synthetic-timing-tool-2\",\"process_id\":\"synthetic-timing-process-2\",\"duration\":{\"secs\":2,\"nanos\":0},\"exit_code\":0,\"status\":\"completed\"}}\n";
async function withMainTimingNormal(request, read, sourceRaws = [mainSourceTimingRaw, missingMainSourceTimingRaw]) {
  const fs = require('fs'), path = require('path'), { spawn } = require('child_process');
  const { runTmpRoot } = require('./runtime-paths'), { copyDistribution, resolveJavaEnvironment } = require('./start-java-fixture-server');
  fs.mkdirSync(runTmpRoot, { recursive: true }); const directory = fs.mkdtempSync(path.join(runTmpRoot, 'main-timing-')), home = path.join(directory, 'home');
  const source = path.join(home, '.codex/sessions/synthetic'); fs.mkdirSync(source, { recursive: true });
  const ids = [];
  for (const raw of sourceRaws) {
    const id = JSON.parse(raw.split('\n')[0]).payload.id; ids.push(id);
    fs.writeFileSync(path.join(source, 'rollout-' + id + '.jsonl'), raw);
  }
  fs.writeFileSync(path.join(home, '.codex/session_index.jsonl'), ids.map(id => JSON.stringify({ id, thread_name: 'Synthetic MAIN timing ' + id })).join('\n') + '\n');
  const child = spawn(copyDistribution(directory), ['serve', '--host', '127.0.0.1', '--port', '0'], { env: { ...process.env, ...resolveJavaEnvironment(), HOME: home, INDEX_DIR: path.join(directory, 'index'), JAVA_OPTS: `"-Duser.home=${home}"`, APP_CLI_OPTS: '', JAVA_TOOL_OPTIONS: '', JDK_JAVA_OPTIONS: '', _JAVA_OPTIONS: '' }, stdio: ['ignore', 'pipe', 'pipe'] });
  let logs = '';
  try {
    const base = await new Promise((resolve, reject) => {
      child.once('error', reject); child.once('exit', c => reject(new Error('early ' + c + logs)));
      for (const stream of [child.stdout, child.stderr]) stream.on('data', d => {
        logs += d; const ready = logs.match(/serve 已就绪: (http:\/\/127\.0\.0\.1:\d+)/);
        if (/后台扫描失败结果:|启动扫描失败/.test(logs)) reject(new Error(logs));
        else if (ready && /后台扫描完成: tier=full window=all updated=\d+ perSource=/.test(logs)) resolve(ready[1]);
      });
    });
    await read({ base, ids });
  } finally {
    if (child.exitCode === null && child.signalCode === null) { child.kill('SIGTERM'); await new Promise(resolve => child.once('exit', resolve)); }
    fs.writeFileSync(path.join(directory, 'service.log'), logs);
  }
}
for (const kind of ['normal', 'import']) for (const width of [1440, 390]) test('MAIN source timing native entry ' + kind + ' at ' + width + 'px', async ({ page, request, baseURL }) => {
  expect(createHash('sha256').update(mainSourceTimingRaw).digest('hex')).toBe('d5577401288bf318f66d3c86329ccd7f3942ff8b38b535aeba2904861b1c1e62');
  async function verify(url, apiBase) {
    const paths = [], errors = []; page.on('request', r => { if (r.url().includes('/api/')) paths.push(r.url()); }); page.on('pageerror', e => errors.push(String(e)));
    const metrics = await (await request.get(apiBase + '/metrics')).json();
    expect(metrics.timing).toMatchObject({ activeTaskSeconds: 10, agentTurnSeconds: 4, modelExecutionSeconds: null });
    await page.setViewportSize({ width, height: 900 }); await page.goto(url); await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
    await expect(page.locator('[data-execution-judgment]')).toContainText('已测累计 3s');
    await expect(page.locator('[data-execution-judgment]')).toContainText('模型耗时未测量');
    const entry = page.locator('[data-main-source-timing-open]'), card = page.locator('[data-session-timing]');
    expect(await entry.count()).toBe(1); await expect(entry).toBeVisible();
    await expect(page.locator('[data-evidence-analysis]')).not.toHaveAttribute('open'); await expect(page.locator('[data-secondary-metrics]')).not.toHaveAttribute('open');
    await captureDiagnosticScreenshot(page, { path: test.info().outputPath('main-timing-default-' + kind + '-' + width + '.png') });
    const before = paths.length; await entry.focus(); await page.keyboard.press('Enter');
    await expect(card).toBeVisible(); await expect(card).toBeFocused(); expect(paths.length).toBe(before);
    await expect(card.locator('.sd-kpi__value')).toHaveText('10s');
    await expect(card).toHaveAttribute('aria-label', '主会话任务活动时间');
    await expect(card.locator('.sd-kpi__label')).toHaveText('主会话任务活动时间');
    await expect(card).toContainText('来源记录时间跨度 13s'); await expect(card).toContainText('主会话轮次累计 4s');
    await expect(card).toContainText('来源模型计时 N/A'); await expect(card).toContainText('来源工具计时 N/A');
    const note = card.locator('[data-session-timing-note]'); await expect(note).not.toHaveAttribute('open');
    await expect(note.locator('summary')).toHaveText('计时口径与来源');
    await note.locator('summary').focus(); await page.keyboard.press('Enter'); await expect(note).toHaveAttribute('open', '');
    const paragraphs = note.locator(':scope > p'); await expect(paragraphs).toHaveCount(3);
    await expect(paragraphs.nth(0)).toContainText('计时口径：'); await expect(paragraphs.nth(0)).toContainText('逐工具执行器观测累计');
    await expect(paragraphs.nth(1)).toContainText('来源依据：'); await expect(paragraphs.nth(1)).toContainText('重叠窗口只计一次'); await expect(paragraphs.nth(1)).toContainText('任务外记录跨度：3s');
    await expect(paragraphs.nth(2)).toContainText('缺测与记录：'); await expect(paragraphs.nth(2)).toContainText('N/A 表示未知而非 0'); await expect(paragraphs.nth(2)).toContainText('已结束：1');
    for (let i = 0; i < 3; i++) await expect(paragraphs.nth(i)).toBeVisible();
    await expect(note).toContainText('包含任务期间的工具和等待，不是模型推理耗时');
    await expect(note).toContainText('重叠窗口只计一次'); await expect(note).toContainText('不是 LLM 调用延迟');
    await expect(note).toContainText('逐工具执行器观测累计'); await expect(note).toContainText('N/A 表示未知而非 0');
    await expect(note).toContainText('不表示业务成功'); expect(paths.length).toBe(before);
    await captureDiagnosticScreenshot(card, { path: test.info().outputPath('main-timing-details-' + kind + '-' + width + '.png') });
    await note.locator('summary').click(); await expect(note).not.toHaveAttribute('open');
    await captureDiagnosticScreenshot(card, { path: test.info().outputPath('main-timing-card-' + kind + '-' + width + '.png') });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true); expect(errors).toEqual([]);
    await test.info().attach('main-timing-source-api-network.json', { body: JSON.stringify({ kind, width, metrics, paths, before, after: paths.length, errors }), contentType: 'application/json' });
  }
  if (kind === 'normal') await withMainTimingNormal(request, async ({ base, ids }) => verify(base + '/sessions/codex/' + ids[0], base + '/api/sessions/codex/' + ids[0]));
  else {
    const response = await request.post('/api/imports', { headers: { Origin: new URL(baseURL).origin }, multipart: { source: 'codex', file: { name: 'synthetic-main-timing.jsonl', mimeType: 'application/x-ndjson', buffer: Buffer.from(mainSourceTimingRaw) } } }); expect(response.status()).toBe(201); const imported = await response.json();
    try { await verify(imported.detail_url, '/api/imports/' + imported.import_id); }
    finally { expect((await request.delete('/api/imports/' + imported.import_id, { headers: { Origin: new URL(baseURL).origin } })).status()).toBe(204); }
  }
});

for (const kind of ['normal', 'import']) for (const width of [1440, 390]) test('MAIN source timing method without measurements ' + kind + ' at ' + width + 'px', async ({ page, request, baseURL }) => {
  async function verify(url, apiBase) {
    const metrics = await (await request.get(apiBase + '/metrics')).json();
    expect(metrics.timing).toMatchObject({ activeTaskSeconds: null, activeTaskPrecision: 'unknown', activeTaskBasis: 'main_task_windows', agentTurnSeconds: null, modelExecutionSeconds: null, toolExecutionSeconds: null, completedTaskCount: 0, incompleteTaskCount: 0, abortedTaskCount: 0 });
    const execution = await (await request.get(apiBase + '/execution')).json();
    expect(execution.diagnostics.measuredWorkMs).toBe(3000);
    await page.setViewportSize({ width, height: 900 }); await page.goto(url);
    await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true'); await page.waitForLoadState('networkidle');
    await expect(page.locator('[data-main-source-timing-open]')).toBeHidden();
    const paths = [], record = r => { if (r.url().includes('/api/')) paths.push(r.url()); }; page.on('request', record);
    try {
      await page.locator('[data-evidence-analysis] > summary').click(); await page.locator('[data-secondary-metrics] > summary').click();
      const card = page.locator('[data-session-timing]'), note = card.locator('[data-session-timing-note]'), summary = note.locator(':scope > summary');
      await expect(card.locator('.sd-kpi__value')).toHaveText('N/A'); await expect(card).toContainText('主会话轮次累计 N/A');
      await expect(note).not.toHaveAttribute('open'); await summary.focus(); await page.keyboard.press('Enter');
      await expect(note.locator(':scope > p')).toHaveCount(3); await expect(summary).toBeFocused();
      await expect(note.locator(':scope > p').nth(1)).toContainText('任务汇总方法：按主任务时间窗口计时，重叠窗口只计一次。');
      await expect(note).not.toContainText('任务依据：记录中的主任务时间窗口');
      await expect(note.locator(':scope > p').nth(2)).toContainText('N/A 表示未知而非 0');
      await captureDiagnosticScreenshot(card, { path: test.info().outputPath('missing-timing-method-' + kind + '-' + width + '.png') });
      await summary.click(); await expect(note).not.toHaveAttribute('open'); await summary.focus(); await page.keyboard.press('Space'); await expect(note).toHaveAttribute('open', '');
      expect(paths).toEqual([]); expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await test.info().attach('missing-timing-method-api.json', { body: JSON.stringify({ kind, width, metrics, execution, paths, sourceSha256: createHash('sha256').update(missingMainSourceTimingRaw).digest('hex') }), contentType: 'application/json' });
    } finally { page.removeListener('request', record); }
  }
  if (kind === 'normal') await withMainTimingNormal(request, async ({ base, ids }) => verify(base + '/sessions/codex/' + ids[0], base + '/api/sessions/codex/' + ids[0]), [missingMainSourceTimingRaw]);
  else await importMainTimingRaw(request, baseURL, missingMainSourceTimingRaw, verify);
});

async function importMainTimingRaw(request, baseURL, raw, read) {
  const response = await request.post('/api/imports', { headers: { Origin: new URL(baseURL).origin }, multipart: { source: 'codex', file: { name: 'synthetic-main-timing-guard.jsonl', mimeType: 'application/x-ndjson', buffer: Buffer.from(raw) } } });
  expect(response.status()).toBe(201); const imported = await response.json();
  try { await read(imported.detail_url, '/api/imports/' + imported.import_id); }
  finally { expect((await request.delete('/api/imports/' + imported.import_id, { headers: { Origin: new URL(baseURL).origin } })).status()).toBe(204); }
}

test('MAIN source timing real missing zero and partial eligibility', async ({ page, request, baseURL }) => {
  const zero = mainSourceTimingRaw.trim().split('\n').map(JSON.parse);
  for (const row of zero) {
    if (row.payload.type === 'task_started') row.payload.started_at = '2026-11-18T00:00:10Z';
    if (row.payload.type === 'task_complete') { row.payload.started_at = row.payload.completed_at; row.payload.duration_ms = 0; }
    if (row.payload.type === 'turn_duration') row.payload.durationMs = 0;
  }
  const partial = mainSourceTimingRaw + JSON.stringify({ synthetic: true, type: 'event_msg', timestamp: '2026-11-18T00:00:14Z', payload: { type: 'task_started', turn_id: 'synthetic-unfinished-turn', started_at: '2026-11-18T00:00:14Z' } }) + '\n';
  for (const [kind, raw] of [['missing', missingMainSourceTimingRaw], ['zero', zero.map(JSON.stringify).join('\n') + '\n'], ['partial', partial]]) await importMainTimingRaw(request, baseURL, raw, async (url, apiBase) => {
    const metrics = await (await request.get(apiBase + '/metrics')).json();
    await page.goto(url); await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
    const entry = page.locator('[data-main-source-timing-open]');
    if (kind === 'missing') { expect(metrics.timing.activeTaskSeconds).toBeNull(); expect(metrics.timing.agentTurnSeconds).toBeNull(); await expect(entry).not.toBeVisible(); }
    else {
      if (kind === 'zero') expect(metrics.timing).toMatchObject({ activeTaskSeconds: 0, agentTurnSeconds: 0 });
      else expect(metrics.timing).toMatchObject({ activeTaskSeconds: 10, activeTaskPrecision: 'partial' });
      await expect(entry).toBeVisible(); await entry.click(); await expect(page.locator('[data-session-timing]')).toBeFocused();
    }
    expect(metrics.timing.modelExecutionSeconds).toBeNull();
    await test.info().attach('main-timing-' + kind + '-api.json', { body: JSON.stringify({ metrics, sourceSha256: createHash('sha256').update(raw).digest('hex') }), contentType: 'application/json' });
  });
});

function mainTimingScopeRaws() {
  const parent = mainSourceTimingRaw.trim().split('\n').map(JSON.parse), rootId = parent[0].payload.id, childId = 'synthetic-main-timing-scope-child';
  const call = { type: 'function_call', name: 'spawn_agent', call_id: 'synthetic-main-timing-spawn', arguments: JSON.stringify({ message: 'Synthetic scope guard only; read records, do not execute' }) };
  parent.push({ type: 'response_item', payload: call }, { type: 'response_item', payload: { type: 'function_call_output', call_id: call.call_id, output: JSON.stringify({ agent_id: childId }) } }, { type: 'token_usage_record', payload: { response_id: 'synthetic-main-timing-spawn-response', usage: { input_tokens: 5, output_tokens: 1 } } });
  const child = [{ type: 'session_meta', payload: { id: childId, source: { subagent: { thread_spawn: { parent_thread_id: rootId } } } } }, { type: 'response_item', payload: { type: 'function_call', name: 'exec_command', call_id: 'synthetic-untimed-child-tool', arguments: JSON.stringify({ cmd: 'printf SYNTHETIC_CHILD_NOT_EXECUTED' }) } }, { type: 'token_usage_record', payload: { response_id: 'synthetic-child-response', usage: { input_tokens: 2, output_tokens: 1 } } }, { type: 'response_item', payload: { type: 'function_call_output', call_id: 'synthetic-untimed-child-tool', output: 'Synthetic child output; duration and model execution unknown' } }];
  const raws = [parent, child].map(rows => rows.map(JSON.stringify).join('\n') + '\n');
  return { raws, rootId, childId };
}

test('MAIN source timing real parent child scope guard', async ({ page, request }) => {
  const { raws, rootId, childId } = mainTimingScopeRaws();
  await withMainTimingNormal(request, async ({ base }) => {
    const apiBase = base + '/api/sessions/codex/' + rootId;
    const metrics = await (await request.get(apiBase + '/metrics')).json(), execution = await (await request.get(apiBase + '/execution')).json();
    expect(metrics.timing).toMatchObject({ activeTaskSeconds: 10, agentTurnSeconds: 4, modelExecutionSeconds: null });
    expect(execution.diagnostics.measuredWorkMs).toBe(3000); // Added spawn/untimed child change totals, not MAIN timing.
    await page.goto(base + '/sessions/codex/' + rootId); await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
    const entry = page.locator('[data-main-source-timing-open]'); await expect(entry).toBeVisible();
    const relation = page.locator('[data-collaboration-relation]').filter({ hasText: 'Synthetic scope guard only' }); await expect(relation).toBeVisible();
    await relation.getByRole('button', { name: /的过程与耗时$/ }).click();
    await expect.poll(() => page.evaluate(() => executionView.agent)).toBe('subagent:' + childId); await expect(page.locator('[data-execution-agent-context]')).toContainText('诊断仅限本上下文'); await expect(entry).not.toBeVisible();
    await page.locator('[data-execution-agent-reset]').click(); await expect(entry).toBeVisible(); await entry.click(); await expect(page.locator('[data-session-timing]')).toBeFocused();
    await test.info().attach('main-timing-scope-actual.json', { body: JSON.stringify({ metrics, diagnostics: execution.diagnostics, rawSha256: raws.map(raw => createHash('sha256').update(raw).digest('hex')) }), contentType: 'application/json' });
  }, raws);
});

for (const boundary of ['late', 'generation', 'retry']) test('MAIN source timing transport ' + boundary + ' guard', async ({ page, request, baseURL }) => {
  await importMainTimingRaw(request, baseURL, mainSourceTimingRaw, async (url, apiBase) => {
    let release, arrived, failed = false; const gate = new Promise(r => { release = r; }), arrival = new Promise(r => { arrived = r; });
    const match = '**' + apiBase + '/metrics';
    await page.route(match, async route => {
      const response = await route.fetch(); arrived(); await gate;
      if (boundary === 'retry' && !failed) { failed = true; await route.fulfill({ response, status: 503 }); }
      else if (boundary === 'generation') await route.fulfill({ response, headers: { ...response.headers(), 'x-session-index-generation': 'UI-ONLY-ILLEGAL-GENERATION' } });
      else await route.fulfill({ response });
    });
    try {
      await page.goto(url); await arrival;
      const entry = page.locator('[data-main-source-timing-open]'), elsewhere = page.locator('[data-execution-filter="all"]');
      await expect(entry).not.toBeVisible(); await elsewhere.focus(); release();
      if (boundary === 'generation') {
        // Import has an unstamped document: repeated mixed stamps reject every resource, not an SSR quarantine.
        await expect(page.locator('[data-resource-error="metrics"]')).toContainText('no consistent snapshot rendered');
        await expect(entry).not.toBeVisible();
      }
      else {
        if (boundary === 'retry') {
          const retry = page.locator('[data-resource-error="metrics"]').getByRole('button', { name: 'Retry', exact: true });
          await expect(retry).toBeVisible(); await expect(entry).not.toBeVisible(); await retry.click();
        }
        await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true'); await expect(entry).toBeVisible(); if (boundary === 'late') await expect(elsewhere).toBeFocused();
        await expect(page.locator('[data-evidence-analysis]')).not.toHaveAttribute('open'); await expect(page.locator('[data-secondary-metrics]')).not.toHaveAttribute('open');
        if (boundary === 'late') {
          // UI-only missing-object and stale-generation guards, not source/parser evidence.
          expect(await page.evaluate(() => {
            const saved = sessionDetailState.mainTiming, metrics = sessionDetailState.metrics;
            sessionDetailState.metrics = undefined; sessionDetailState.mainTiming = { metrics: undefined, generation: document.body.getAttribute('data-index-generation') };
            const missingHidden = !syncMainSourceTimingEntry();
            sessionDetailState.metrics = metrics; sessionDetailState.mainTiming = { metrics, generation: 'STALE-UI-ONLY-GENERATION' };
            const staleHidden = !syncMainSourceTimingEntry();
            sessionDetailState.mainTiming = saved; syncMainSourceTimingEntry();
            applySessionMetrics({}); const rejectedHidden = !syncMainSourceTimingEntry() && sessionDetailState.mainTiming === null;
            sessionDetailState.metrics = metrics; sessionDetailState.mainTiming = saved; syncMainSourceTimingEntry();
            return missingHidden && staleHidden && rejectedHidden;
          })).toBe(true);
          await expect(elsewhere).toBeFocused();
          // UI-only render lifetime: reapply the identical accepted data, never fabricate timing facts.
          await entry.focus(); const entryNode = await entry.elementHandle();
          await page.evaluate(() => applyExecutionPage(executionView.page, false));
          await expect(entry).toBeFocused(); expect(await entryNode.evaluate(n => n.isConnected && n === document.activeElement)).toBe(true);
          await entry.click(); const card = page.locator('[data-session-timing]'), cardNode = await card.elementHandle();
          await page.evaluate(() => applySessionMetrics(sessionDetailState.metrics));
          await expect(card).toBeFocused(); expect(await cardNode.evaluate(n => n.isConnected && n === document.activeElement)).toBe(true);
        }
      }
    } finally { release(); await page.unroute(match); }
  });
});

test('MAIN source timing pending target respects explicit timing focus', async ({ page, request, baseURL }) => {
  await importMainTimingRaw(request, baseURL, mainSourceTimingRaw, async (url, apiBase) => {
    const paths = []; page.on('request', r => { if (r.url().includes('/api/')) paths.push(r.url()); });
    await page.goto(url); await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
    const entry = page.locator('[data-main-source-timing-open]'), card = page.locator('[data-session-timing]'); await expect(entry).toBeVisible();
    let release, arrived; const gate = new Promise(r => { release = r; }), arrival = new Promise(r => { arrived = r; });
    const matches = url => url.pathname === apiBase + '/execution' && url.searchParams.get('target') === 'synthetic-timing-tool-2';
    await page.route(matches, async route => { const response = await route.fetch(); arrived(); await gate; await route.fulfill({ response }); });
    try {
      await page.evaluate(() => { window.mainTimingPendingBefore = executionView.page; });
      await page.getByRole('button', { name: '定位此动作', exact: true }).click(); await arrival;
      const before = paths.length; await entry.focus(); await page.keyboard.press('Enter'); await expect(card).toBeFocused(); expect(paths.length).toBe(before);
      release(); await expect.poll(() => page.evaluate(() => executionView.page !== window.mainTimingPendingBefore)).toBe(true);
      await expect(card).toBeFocused(); await expect(card).toBeVisible();
      expect(await card.evaluate(n => { const r = n.getBoundingClientRect(); return r.top >= 0 && r.bottom <= innerHeight; })).toBe(true);
      await test.info().attach('main-timing-pending-network.json', { body: JSON.stringify({ paths, before, after: paths.length }), contentType: 'application/json' });
    } finally { release(); await page.unroute(matches); }
  });
});

for (const reading of ['card', 'scrolled-away']) test('MAIN source timing pending child reset respects ' + reading + ' reading', async ({ page, request }) => {
  const { raws, rootId, childId } = mainTimingScopeRaws();
  await withMainTimingNormal(request, async ({ base }) => {
    const paths = []; page.on('request', r => { if (r.url().includes('/api/')) paths.push(r.url()); });
    await page.goto(base + '/sessions/codex/' + rootId); await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
    await page.locator('[data-collaboration-relation]').filter({ hasText: 'Synthetic scope guard only' }).getByRole('button', { name: /的过程与耗时$/ }).click();
    await expect.poll(() => page.evaluate(() => executionView.renderedAgent)).toBe('subagent:' + childId);
    const entry = page.locator('[data-main-source-timing-open]'), card = page.locator('[data-session-timing]'); await expect(entry).not.toBeVisible();
    let release, arrived; const gate = new Promise(r => { release = r; }), arrival = new Promise(r => { arrived = r; });
    const matches = url => url.pathname === '/api/sessions/codex/' + rootId + '/execution' && url.searchParams.get('agent_context') === '';
    await page.route(matches, async route => { const response = await route.fetch(); arrived(); await gate; await route.fulfill({ response }); });
    try {
      await page.evaluate(() => { window.mainTimingPendingBefore = executionView.page; });
      await page.locator('[data-execution-agent-reset]').click(); await arrival; await expect(entry).toBeVisible();
      const before = paths.length; await entry.focus(); await page.keyboard.press('Enter'); await expect(card).toBeFocused(); expect(paths.length).toBe(before);
      if (reading === 'scrolled-away') { await page.mouse.wheel(0, -10000); await expect.poll(() => page.evaluate(() => scrollY)).toBe(0); }
      release(); await expect.poll(() => page.evaluate(() => executionView.page !== window.mainTimingPendingBefore)).toBe(true);
      await expect(card).toBeFocused(); await expect(card).toBeVisible();
      if (reading === 'card') expect(await card.evaluate(n => { const r = n.getBoundingClientRect(); return r.top >= 0 && r.bottom <= innerHeight; })).toBe(true);
      else expect(await page.evaluate(() => scrollY)).toBe(0);
      await test.info().attach('main-timing-pending-network.json', { body: JSON.stringify({ paths, before, after: paths.length }), contentType: 'application/json' });
    } finally { release(); await page.unroute(matches); }
  }, raws);
});

for (const mode of ['normal', 'import']) for (const width of [1440, 390]) {
  test(`local result inclusion first reading and exact return ${mode} ${width}px`, async ({ page, request, baseURL }, testInfo) => {
    async function verify(url, apiBase) {
      const network = [], errors = [];
      page.on('request', r => { if (r.url().includes(apiBase)) network.push(new URL(r.url())); });
      page.on('pageerror', e => errors.push(e.message));
      await page.setViewportSize({ width, height: 900 });
      await page.goto(url);
      await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
      await expect(page.locator('[data-execution-group]')).toHaveCount(3);
      expect(network.filter(u => /\/payload\//.test(u.pathname))).toHaveLength(0);
      const tool = page.locator('[data-execution-tool="synthetic-result-occurrences-tool"]');
      await tool.locator('summary').click();
      const trigger = tool.getByRole('button', { name: '执行结果', exact: true });
      await trigger.click();
      const modal = page.locator('dialog.payload-modal[open]');
      const results = modal.locator('[data-local-result]');
      await expect(results).toHaveCount(2);
      for (const n of [1, 2]) {
        const result = results.nth(n - 1);
        await expect(result).toContainText('SYNTHETIC_RESULT_OCCURRENCE_R' + n);
        await expect(result).not.toContainText('SYNTHETIC_RESULT_OCCURRENCE_R' + (3 - n));
        await expect(result).toContainText('本地记录#' + (n + 1) + ' · 主会话');
      }
      expect(network.filter(u => /\/payload\//.test(u.pathname))).toHaveLength(1);
      expect(network.find(u => /\/payload\//.test(u.pathname)).searchParams.get('view')).toBe('local_results');
      await captureDiagnosticScreenshot(modal, { path: testInfo.outputPath('local-result-first-' + mode + '-' + width + '.png') });
      for (const n of [1, 2]) {
        const target = results.nth(n - 1).getByRole('button', { name: '查看准确引用', exact: true });
        await target.focus();
        await page.keyboard.press('Enter');
        await expect(modal.locator('[data-local-reference]')).toHaveCount(1);
        await expect(modal.locator('[data-local-reference]')).toContainText('SYNTHETIC_RESULT_OCCURRENCE_R' + n);
        await expect(modal.locator('[data-local-reference]')).not.toContainText('SYNTHETIC_RESULT_OCCURRENCE_R' + (3 - n));
        await expect(modal.locator('[data-local-reference]')).toBeFocused();
        await expect(modal).toContainText('本地记录中的工具结果');
        const attribution = modal.locator('[data-payload-attribution="request"]');
        await attribution.locator('summary').click();
        await expect(attribution).toHaveAttribute('data-attribution-call', 'token_usage_record:synthetic-result-occurrences-F' + (n + 1));
        await expect(attribution).toHaveAttribute('data-attribution-scope', 'main');
        await captureDiagnosticScreenshot(modal, { path: testInfo.outputPath('local-result-input-' + n + '-' + mode + '-' + width + '.png') });
        expect(network.filter(u => u.searchParams.has('target'))).toHaveLength(n);
        expect(network.filter(u => u.searchParams.has('occurrence'))).toHaveLength(0);
        await modal.getByRole('button', { name: '返回结果', exact: true }).focus();
        await page.keyboard.press('Enter');
        await expect(target).toBeFocused();
        await expect(results).toHaveCount(2);
      }
      await page.keyboard.press('Escape');
      await expect(trigger).toBeFocused();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      expect(errors).toEqual([]);
    }
    if (mode === 'normal') await withMainTimingNormal(request, async ({ base, ids }) => verify(base + '/sessions/codex/' + ids[0], base + '/api/sessions/codex/' + ids[0]), [resultOccurrenceRaw]);
    else await importMainTimingRaw(request, baseURL, resultOccurrenceRaw, verify);
  });
}

async function localResultFixture(page, api, setup) {
  const tool = page.locator('[data-execution-tool]').first();
  await tool.locator('summary').click();
  const trigger = tool.getByRole('button', { name: '执行结果', exact: true });
  const id = await trigger.getAttribute('data-payload-id');
  const rootPath = api + '/payload/' + encodeURIComponent(id);
  const targetPath = api + '/payload/' + encodeURIComponent('main:req:synthetic-exact-input');
  const target = (n = 0) => ({ callId: 'synthetic-input', requestPayloadId: 'main:req:synthetic-exact-input', referenceId: 'synthetic-ref-' + n,
    target: 'synthetic-target-' + n, apiUrl: targetPath, recordIndex: 42, scope: 'subagent' });
  const relation = (targets = [], extra = {}) => ({ targets, offset: 0, nextCursor: null, coverage: 'complete', identity: 'confirmed', reason: null, ...extra });
  const item = (text, extra = {}) => ({ referenceId: null, occurrence: 'synthetic-occurrence', toolName: 'exec_command', position: 0, identity: 'confirmed',
    content: { state: 'available', text, truncated: false }, targetPreview: relation([target()]), ...extra });
  const result = (items, extra = {}) => ({ payload: { kind: 'tool_result', status: 'available', content: 'SYNTHETIC_FULL_RESULT_TAIL' },
    localResults: { items, offset: 0, nextCursor: null, coverage: 'complete', targetReferenceId: null, ...extra }, relations: null });
  const input = n => ({ payload: { kind: 'llm_request', status: 'missing', content: '', reading: [] },
    localResults: { items: [item('SYNTHETIC_EXACT_REFERENCE_' + n, { referenceId: 'synthetic-ref-' + n, targetPreview: null })], offset: 40, nextCursor: null, coverage: 'complete', targetReferenceId: 'synthetic-ref-' + n }, relations: null });
  await setup({ trigger, rootPath, targetPath, target, relation, item, result, input });
}

test('local result inclusion manual bounded references and exact late window', async ({ page, executionSession: { api, detail } }) => {
  await page.goto(detail); await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  await localResultFixture(page, api, async ({ trigger, rootPath, targetPath, target, relation, item, result, input }) => {
    const requests = [];
    await page.route('**' + api + '/payload/**', async route => {
      const url = new URL(route.request().url()); requests.push(url);
      if (url.pathname === rootPath) {
        const data = url.searchParams.has('occurrence') ? { payload: null, localResults: null, relations: relation(Array.from({ length: 44 }, (_, i) => target(i + 1)), { offset: 1 }) }
          : result([item('SYNTHETIC_SAME_TEXT', { targetPreview: relation([target()], { nextCursor: 'synthetic-offset-one' }) })]);
        await route.fulfill({ json: data });
      } else { expect(url.pathname).toBe(targetPath); await route.fulfill({ json: input(44) }); }
    });
    await trigger.click(); const modal = page.locator('dialog.payload-modal[open]');
    await expect(modal).toContainText('本地记录#42 · 子上下文'); expect(requests).toHaveLength(1);
    await modal.getByRole('button', { name: '其他已确认输入', exact: true }).click();
    await expect(modal.locator('[data-local-target]')).toHaveCount(45);
    expect(requests[1].searchParams.get('cursor')).toBe('synthetic-offset-one');
    expect(requests[1].searchParams.get('occurrence')).toBe('synthetic-occurrence');
    await expect(modal.locator('.sd-local-target')).toHaveCount(1);
    const last = modal.getByRole('button', { name: '查看已载入引用 45', exact: true });
    await modal.locator('[data-tool-result-original] > summary').first().click();
    await last.focus();
    const savedScroll = await modal.locator('[data-payload-body]').evaluate(node => node.scrollTop);
    await page.keyboard.press('Enter'); await expect(modal.locator('[data-local-reference]')).toHaveText(/SYNTHETIC_EXACT_REFERENCE_44/);
    expect(requests).toHaveLength(3); expect(requests[2].searchParams.get('target')).toBe('synthetic-target-44'); expect(requests[2].searchParams.has('cursor')).toBe(false);
    await modal.getByRole('button', { name: '返回结果', exact: true }).click();
    await expect(last).toBeFocused(); await expect(modal.locator('[data-local-target]')).toHaveCount(45);
    await expect(modal.locator('[data-tool-result-original]').first()).toHaveAttribute('open');
    expect(await modal.locator('[data-payload-body]').evaluate(node => node.scrollTop)).toBe(savedScroll);
  });
});

test('local result inclusion null empty unknown ambiguous partial and safe complete raw', async ({ page, executionSession: { api, detail } }) => {
  await page.goto(detail); await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  await localResultFixture(page, api, async ({ trigger, rootPath, relation, item, result }) => {
    await page.route('**' + rootPath + '?**', route => route.fulfill({ json: result([
      item('', { targetPreview: null }), item('', { targetPreview: relation() }),
      item('SYNTHETIC_UNKNOWN', { targetPreview: relation([], { coverage: 'unknown' }) }),
      item('SYNTHETIC_AMBIGUOUS', { targetPreview: relation([], { identity: 'ambiguous' }) }),
      item('<script>synthetic_not_executed()</script> [REDACTED]', { targetPreview: relation([], { coverage: 'partial' }), content: { state: 'available', text: '<script>synthetic_not_executed()</script> [REDACTED]', truncated: true } }),
      item('', { targetPreview: relation(), content: { state: 'missing', text: null, truncated: false } }),
    ]) }));
    await trigger.click(); const modal = page.locator('dialog.payload-modal[open]'), rows = modal.locator('[data-local-result]');
    await expect(rows).toHaveCount(6);
    await expect(rows.nth(0)).toContainText('目标预览未载入'); await expect(rows.nth(0)).toContainText('已记录空结果（不是缺失）');
    await expect(rows.nth(1)).toContainText('本地未记录包含此结果的输入');
    await expect(rows.nth(2)).toContainText('尚不能确认包含关系'); await expect(rows.nth(3)).toContainText('来源记录有冲突');
    await expect(rows.nth(4)).toContainText('记录可能不完整'); await expect(rows.nth(4)).toContainText('此结果正文已截断');
    await expect(rows.nth(4).locator('script')).toHaveCount(0); await expect(rows.nth(5)).toContainText('此结果正文未记录');
    await modal.locator('[data-tool-result-original] > summary').first().click(); await expect(modal).toContainText('SYNTHETIC_FULL_RESULT_TAIL');
  });
});

for (const status of [500, 400, 409]) test(`local result inclusion target HTTP ${status} preserves scoped recovery`, async ({ page, executionSession: { api, detail } }) => {
  await page.goto(detail); await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  await localResultFixture(page, api, async ({ trigger, rootPath, targetPath, item, result, input }) => {
    const requests = []; let targetReads = 0;
    await page.route('**' + api + '/payload/**', async route => {
      const url = new URL(route.request().url()); requests.push(url);
      if (url.pathname === rootPath) await route.fulfill({ json: result([item('SYNTHETIC_RECOVERABLE_RESULT')]) });
      else {
        expect(url.pathname).toBe(targetPath); targetReads++;
        if (targetReads === 1) await route.fulfill({ status, json: { message: 'Synthetic scoped failure' } });
        else await route.fulfill({ json: input(0) });
      }
    });
    await trigger.click(); const modal = page.locator('dialog.payload-modal[open]');
    await modal.getByRole('button', { name: '查看准确引用', exact: true }).click();
    if (status === 500) {
      await modal.getByRole('button', { name: 'Retry', exact: true }).click();
      await expect(modal.locator('[data-local-reference]')).toContainText('SYNTHETIC_EXACT_REFERENCE_0');
      expect(requests[1].href).toBe(requests[2].href);
      await modal.getByRole('button', { name: '返回结果', exact: true }).click();
      await expect(modal).toContainText('SYNTHETIC_RECOVERABLE_RESULT');
    } else if (status === 400) {
      await expect(modal.getByRole('button', { name: 'Retry', exact: true })).toHaveCount(0);
      await modal.getByRole('button', { name: '重新读取原结果', exact: true }).click();
      await expect(modal).toContainText('SYNTHETIC_RECOVERABLE_RESULT');
      expect(requests[2].pathname).toBe(rootPath); expect(requests[2].searchParams.has('target')).toBe(false);
    } else {
      await expect(modal).toContainText('索引已变化');
      await expect(modal.locator('[data-local-result-return], [data-local-target]')).toHaveCount(0);
      expect(requests).toHaveLength(2);
    }
    expect(requests.every(u => u.pathname.startsWith(api + '/payload/'))).toBe(true);
  });
});

test('local result inclusion same ID reopening rejects late payload', async ({ page, executionSession: { api, detail } }) => {
  await page.goto(detail); await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  await localResultFixture(page, api, async ({ trigger, rootPath, item, result }) => {
    let release, arrived; const gate = new Promise(r => { release = r; }), waiting = new Promise(r => { arrived = r; }); let reads = 0;
    await page.route('**' + rootPath + '?**', async route => {
      reads++; const first = reads === 1;
      if (first) { arrived(); await gate; }
      await route.fulfill({ json: result([item(first ? 'SYNTHETIC_OLD_INTENT' : 'SYNTHETIC_NEW_INTENT')]) });
    });
    try {
      await trigger.click(); await waiting; await page.keyboard.press('Escape');
      await trigger.click(); const modal = page.locator('dialog.payload-modal[open]'); await expect(modal).toContainText('SYNTHETIC_NEW_INTENT');
      const completed = page.waitForResponse(r => r.url().includes(rootPath)); release(); await completed;
      await expect(modal).not.toContainText('SYNTHETIC_OLD_INTENT'); await expect(modal).toContainText('SYNTHETIC_NEW_INTENT');
    } finally { release(); }
  });
});

for (const action of ['focus', 'return', 'close']) test(`local result inclusion delayed target respects later ${action}`, async ({ page, executionSession: { api, detail } }) => {
  await page.goto(detail); await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  await localResultFixture(page, api, async ({ trigger, rootPath, item, result, input }) => {
    let release, arrived; const gate = new Promise(r => { release = r; }), waiting = new Promise(r => { arrived = r; });
    await page.route('**' + api + '/payload/**', async route => {
      if (new URL(route.request().url()).pathname === rootPath) await route.fulfill({ json: result([item('SYNTHETIC_RETURN_POSITION')]) });
      else { arrived(); await gate; await route.fulfill({ json: input(0) }); }
    });
    try {
      await trigger.click(); const modal = page.locator('dialog.payload-modal[open]'); const target = modal.locator('[data-local-target]');
      await target.click(); await waiting;
      if (action === 'focus') await modal.getByRole('button', { name: 'Close', exact: true }).focus();
      if (action === 'return') await modal.getByRole('button', { name: '返回结果', exact: true }).click();
      if (action === 'close') await page.keyboard.press('Escape');
      const completed = page.waitForResponse(r => new URL(r.url()).searchParams.has('target')); release(); await completed;
      if (action === 'focus') { await expect(modal.locator('[data-local-reference]')).toHaveCount(1); await expect(modal.getByRole('button', { name: 'Close', exact: true })).toBeFocused(); }
      if (action === 'return') { await expect(target).toBeFocused(); await expect(modal).toContainText('SYNTHETIC_RETURN_POSITION'); await expect(modal.locator('[data-local-reference]')).toHaveCount(0); }
      if (action === 'close') { await expect(page.locator('dialog.payload-modal')).not.toHaveAttribute('open'); await expect(trigger).toBeFocused(); }
    } finally { release(); }
  });
});

test('local result inclusion typed empty input survives missing legacy status and copies safe original', async ({ page, executionSession: { api, detail } }) => {
  await page.goto(detail); await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  await page.evaluate(() => { window.syntheticResultCopies = []; Object.defineProperty(navigator, 'clipboard', { configurable: true,
    value: { writeText: async text => window.syntheticResultCopies.push(text) } }); });
  await localResultFixture(page, api, async ({ trigger, rootPath, item, result, input }) => {
    let reads = 0;
    await page.route('**' + rootPath + '?**', route => {
      reads++;
      if (reads === 1) {
        const body = input(0); body.localResults.items[0].content.text = '';
        return route.fulfill({ json: body });
      }
      return route.fulfill({ json: result([item('{"output":"[REDACTED] SYNTHETIC_SAFE_OUTPUT"}')]) });
    });
    await trigger.click(); const modal = page.locator('dialog.payload-modal[open]');
    await expect(modal).toContainText('未单列输入正文；本条包含以下本地工具结果');
    await expect(modal.locator('[data-local-result]')).toContainText('已记录空结果（不是缺失）');
    await expect(modal).not.toContainText('Request 正文未记录');
    await page.keyboard.press('Escape'); await trigger.click();
    await modal.getByRole('button', { name: '复制此结果原文', exact: true }).click();
    await modal.locator('[data-tool-result-original] > summary').first().click();
    await modal.getByRole('button', { name: 'Copy', exact: true }).click();
    expect(await page.evaluate(() => window.syntheticResultCopies)).toEqual(['{"output":"[REDACTED] SYNTHETIC_SAFE_OUTPUT"}', 'SYNTHETIC_FULL_RESULT_TAIL']);
    await expect(modal).not.toContainText('内容已截断');
  });
});

test('local result inclusion late relationship page cannot revive closed source', async ({ page, executionSession: { api, detail } }) => {
  await page.goto(detail); await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  await localResultFixture(page, api, async ({ trigger, rootPath, relation, target, item, result }) => {
    let release, arrived; const gate = new Promise(r => { release = r; }), waiting = new Promise(r => { arrived = r; }); let reads = 0;
    await page.route('**' + rootPath + '?**', async route => {
      const url = new URL(route.request().url());
      if (url.searchParams.has('occurrence')) { arrived(); await gate; await route.fulfill({ json: { payload: null, localResults: null, relations: relation([target(1)]) } }); }
      else { reads++; await route.fulfill({ json: result([item(reads === 1 ? 'SYNTHETIC_OLD_PAGE' : 'SYNTHETIC_NEW_PAGE', { targetPreview: relation([target()], { nextCursor: 'synthetic-next' }) })]) }); }
    });
    try {
      await trigger.click(); const modal = page.locator('dialog.payload-modal[open]');
      await modal.getByRole('button', { name: '其他已确认输入', exact: true }).click(); await waiting;
      await page.keyboard.press('Escape'); await trigger.click(); await expect(modal).toContainText('SYNTHETIC_NEW_PAGE');
      const completed = page.waitForResponse(r => new URL(r.url()).searchParams.has('occurrence')); release(); await completed;
      await expect(modal.locator('[data-local-target]')).toHaveCount(1); await expect(modal).not.toContainText('SYNTHETIC_OLD_PAGE');
    } finally { release(); }
  });
});

test('local result inclusion rejects a target from another API scope without fallback', async ({ page, executionSession: { api, detail } }) => {
  await page.goto(detail); await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  await localResultFixture(page, api, async ({ trigger, rootPath, target, relation, item, result }) => {
    const requests = []; page.on('request', r => { if (r.url().includes('/payload/')) requests.push(r.url()); });
    await page.route('**' + rootPath + '?**', route => route.fulfill({ json: result([item('SYNTHETIC_SCOPED_RESULT', {
      targetPreview: relation([{ ...target(), apiUrl: '/api/imports/synthetic-other-scope/payload/synthetic-input' }]),
    })]) }));
    await trigger.click(); const modal = page.locator('dialog.payload-modal[open]');
    await modal.getByRole('button', { name: '查看准确引用', exact: true }).click();
    await expect(modal).toContainText('此入口不属于当前范围'); expect(requests).toHaveLength(1);
    await expect(modal).toContainText('SYNTHETIC_SCOPED_RESULT');
  });
});

for (const status of [500, 409]) test(`local result inclusion delayed attribution ${status} respects newer focus`, async ({ page, executionSession: { api, detail } }) => {
  await page.goto(detail); await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  await localResultFixture(page, api, async ({ trigger, rootPath, target, relation, item, result, input }) => {
    let release, arrived; const gate = new Promise(r => { release = r; }), waiting = new Promise(r => { arrived = r; });
    const attributionPath = '/attribution/call/synthetic-exact-input/request';
    await page.route('**' + api + '/payload/**', route => route.fulfill({ json: new URL(route.request().url()).pathname === rootPath
      ? result([item('SYNTHETIC_ATTRIBUTION_SOURCE', { targetPreview: relation([{ ...target(), attributionPath }]) })]) : input(0) }));
    await page.route('**' + api + attributionPath, async route => { arrived(); await gate; await route.fulfill({ status, json: { message: 'Synthetic attribution failure' } }); });
    try {
      await trigger.click(); const modal = page.locator('dialog.payload-modal[open]');
      await modal.getByRole('button', { name: '查看准确引用', exact: true }).click(); await waiting;
      const close = modal.getByRole('button', { name: 'Close', exact: true }); await close.focus();
      const completed = page.waitForResponse(r => r.url().endsWith(attributionPath)); release(); await completed;
      await expect(close).toBeFocused();
      await expect(modal.locator('[data-payload-attribution="request"]')).not.toHaveAttribute('open');
      if (status === 409) await expect(modal.locator('[data-local-result-return]')).toHaveCount(0);
      else await expect(modal.locator('[data-local-result-return]')).toHaveCount(1);
    } finally { release(); }
  });
});

test('local result inclusion input pagination keeps pending attribution and its Retry alive', async ({ page, executionSession: { api, detail } }) => {
  await page.goto(detail); await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  await localResultFixture(page, api, async ({ trigger, rootPath, target, relation, item, result, input }) => {
    let release, arrived; const gate = new Promise(r => { release = r; }), waiting = new Promise(r => { arrived = r; }); let reads = 0;
    const attributionPath = '/attribution/call/synthetic-exact-input/request';
    await page.route('**' + api + '/payload/**', route => {
      const url = new URL(route.request().url());
      if (url.pathname === rootPath) return route.fulfill({ json: result([item('SYNTHETIC_SOURCE_WITH_PAGING', { targetPreview: relation([{ ...target(), attributionPath }]) })]) });
      const body = input(url.searchParams.has('cursor') ? 1 : 0);
      if (!url.searchParams.has('cursor')) body.localResults.nextCursor = 'synthetic-input-next';
      return route.fulfill({ json: body });
    });
    await page.route('**' + api + attributionPath, async route => {
      reads++;
      if (reads === 1) { arrived(); await gate; await route.fulfill({ status: 500, json: { message: 'Synthetic transient attribution failure' } }); }
      else await route.fulfill({ json: { kind: 'llm.request_attribution', data: { callId: 'synthetic-input', scope: 'subagent', requestToolResultCount: 2 } } });
    });
    try {
      await trigger.click(); const modal = page.locator('dialog.payload-modal[open]');
      await modal.getByRole('button', { name: '查看准确引用', exact: true }).click(); await waiting;
      await modal.getByRole('button', { name: '继续读取结果记录', exact: true }).click();
      await expect(modal.locator('[data-local-reference]')).toHaveCount(2);
      const close = modal.getByRole('button', { name: 'Close', exact: true }); await close.focus();
      const completed = page.waitForResponse(r => r.url().endsWith(attributionPath)); release(); await completed;
      const attribution = modal.locator('[data-payload-attribution="request"]');
      await expect(attribution).toContainText('输入归因暂不可用'); await expect(close).toBeFocused();
      await attribution.locator('summary').click(); await attribution.getByRole('button', { name: 'Retry', exact: true }).click();
      await expect(attribution).toHaveAttribute('data-attribution-call', 'synthetic-input'); await expect(attribution).toHaveAttribute('data-attribution-scope', 'subagent');
      await modal.getByRole('button', { name: '返回结果', exact: true }).click(); await expect(modal).toContainText('SYNTHETIC_SOURCE_WITH_PAGING');
    } finally { release(); }
  });
});

test('local result inclusion result page Retry retains current rows and original cursor', async ({ page, executionSession: { api, detail } }) => {
  await page.goto(detail); await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  await localResultFixture(page, api, async ({ trigger, rootPath, relation, item, result }) => {
    const pages = []; let reads = 0;
    await page.route('**' + rootPath + '?**', async route => {
      const url = new URL(route.request().url());
      if (!url.searchParams.has('cursor')) return route.fulfill({ json: result([item('SYNTHETIC_PAGE_ONE', { targetPreview: relation() })], { nextCursor: 'synthetic-results-next' }) });
      pages.push(url.href); reads++;
      if (reads === 1) await route.fulfill({ status: 500, json: { message: 'Synthetic page read failure' } });
      else await route.fulfill({ json: result([item('SYNTHETIC_PAGE_TWO', { targetPreview: relation() })], { offset: 20 }) });
    });
    await trigger.click(); const modal = page.locator('dialog.payload-modal[open]');
    await modal.getByRole('button', { name: '继续读取结果记录', exact: true }).click();
    await expect(modal.locator('[data-local-result]')).toHaveCount(1);
    await modal.getByRole('button', { name: 'Retry', exact: true }).click();
    await expect(modal.locator('[data-local-result]')).toHaveCount(2);
    await expect(modal).toContainText('SYNTHETIC_PAGE_ONE'); await expect(modal).toContainText('SYNTHETIC_PAGE_TWO'); expect(pages[0]).toBe(pages[1]);
  });
});


test('local result inclusion tool-level truncation stays explicit without changing Copy', async ({ page, executionSession: { api, detail } }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 900 });
  await page.goto(detail); await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  await page.evaluate(() => { window.syntheticResultCopies = []; Object.defineProperty(navigator, 'clipboard', { configurable: true,
    value: { writeText: async text => window.syntheticResultCopies.push(text) } }); });
  await localResultFixture(page, api, async ({ trigger, rootPath, item, result }) => {
    const body = result([item('SYNTHETIC_COMPLETE_ITEM')]);
    body.payload.truncated = true; body.payload.content = 'SYNTHETIC_RECORDED_RAW_PREFIX';
    await page.route('**' + rootPath + '?**', route => route.fulfill({ json: body }));
    await trigger.click(); const modal = page.locator('dialog.payload-modal[open]');
    await expect(modal.getByText('工具级全文已截断；各结果正文状态见下方分项。', { exact: true })).toBeVisible();
    await captureDiagnosticScreenshot(modal, { path: testInfo.outputPath('local-result-truncated-first-390.png') });
    await expect(modal.locator('[data-local-result]')).not.toContainText('正文已截断');
    const original = modal.locator('[data-tool-result-original]').first();
    await expect(original.locator('summary').first()).toHaveText('工具级全文、包装说明与原始载荷（已截断）');
    await original.locator('summary').first().click(); await modal.getByRole('button', { name: 'Copy', exact: true }).click();
    expect(await page.evaluate(() => window.syntheticResultCopies)).toEqual(['SYNTHETIC_RECORDED_RAW_PREFIX']);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await captureDiagnosticScreenshot(modal, { path: testInfo.outputPath('local-result-truncated-390.png') });
  });
});

test('local result inclusion expired target recovery cannot reopen an old ID in a new API scope', async ({ page, executionSession: { api, detail } }) => {
  await page.goto(detail); await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  await localResultFixture(page, api, async ({ trigger, rootPath, item, result }) => {
    const otherApi = api + '-synthetic-other-scope', crossed = [];
    await page.route('**' + api + '/payload/**', route => new URL(route.request().url()).pathname === rootPath
      ? route.fulfill({ json: result([item('SYNTHETIC_ORIGINAL_SCOPE')]) }) : route.fulfill({ status: 400, json: { message: 'Synthetic expired target' } }));
    await page.route('**' + otherApi + '/payload/**', route => { crossed.push(route.request().url()); return route.fulfill({ json: result([item('SYNTHETIC_WRONG_SCOPE')]) }); });
    await trigger.click(); const modal = page.locator('dialog.payload-modal[open]');
    await modal.getByRole('button', { name: '查看准确引用', exact: true }).click();
    const recovery = modal.getByRole('button', { name: '重新读取原结果', exact: true }); await expect(recovery).toBeVisible();
    await page.locator('meta[name="payload-api-base"]').evaluate((meta, value) => meta.setAttribute('content', value), otherApi);
    await recovery.click();
    await expect(modal).toContainText('当前范围已变化，请关闭并重新打开原文');
    expect(crossed).toEqual([]); await expect(modal).not.toContainText('SYNTHETIC_WRONG_SCOPE');
  });
});
