const { test: base, expect } = require('@playwright/test');
const { captureDiagnosticScreenshot } = require('./start-java-fixture-server');

const { executionSourceRecords } = require('../fixtures/generate-session-fixtures');
const { createHash } = require('crypto');
const test = base.extend({
  executionImport: async ({ request, baseURL }, use) => {
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
  test(`raw cumulative work concentration partial=${partial}`, async ({ page, request, baseURL }) => {
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
      await page.goto(imported.detail_url);
      const timing = page.locator('[data-execution-judgment] details').filter({ hasText: '工具耗时证据' });
      await timing.locator('summary').click();
      const slow = data.diagnostics.workloads[0].slowest;
      expect(slow.length).toBe(3);
      const third = timing.locator('[data-execution-locate="' + slow[2].toolCallId + '"]');
      await expect(third).toContainText('#3');
      await third.click();
      await expect(page.locator('[data-tool-payload-pair][open][data-tool-id="' + slow[2].toolCallId + '"]')).toBeVisible();
    } finally {
      expect((await request.delete(importedApi, { headers: { Origin: new URL(baseURL).origin } })).status()).toBe(204);
    }
  });
}

function waitingActionSource(typed) {
  const tools = typed ? [
    { id: 'waiting-launch', name: 'exec_command', input: { cmd: 'node synthetic-task.js', yield_time_ms: 10 }, nanos: 2000000 },
    { id: 'waiting-poll', name: 'write_stdin', input: { session_id: 61001, chars: '', yield_time_ms: 1000 }, nanos: 1000000000 },
    { id: 'waiting-exit', name: 'write_stdin', input: { session_id: 61001, chars: '', yield_time_ms: 1000 }, nanos: 100000000, exit: 0 },
  ] : [
    { id: 'waiting-cell-launch', name: 'exec', input: 'text(await tools.exec_command({cmd:"node synthetic-long-task.js"}));' },
    { id: 'waiting-cell-poll', name: 'wait', input: { cell_id: 'cell-A', yield_time_ms: 1000, terminate: false } },
    { id: 'waiting-cell-stop', name: 'wait', input: { cell_id: 'cell-B', yield_time_ms: 1000, terminate: true } },
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
  test(`raw waiting action summaries preserve evidence and boundaries typed=${typed}`, async ({ page, request, baseURL }) => {
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
      expect(data.items.map(item => item.tool.executionKind)).toEqual([typed ? 'javascript' : 'shell', 'wait', typed ? 'wait' : 'stop']);
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
      const reads = [];
      page.on('request', req => {
        if (req.url().includes(importedApi + '/payload/')) reads.push(decodeURIComponent(new URL(req.url()).pathname));
      });
      await page.goto(imported.detail_url);
      await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
      for (const [index, tool] of tools.entries()) {
        const roundId = data.items[index].group.round;
        await page.locator(`[data-trace-round-row][data-round="${roundId}"] [data-action="toggle-round"]`).click();
        const round = page.locator(`#round-${roundId}-detail`);
        const pair = round.locator(`[data-tool-payload-pair][data-tool-id="${tool.id}"]`);
        await expect(round.locator(`[data-tool-call-id="${tool.id}"] .sd-action-category`)).toHaveText(
          [typed ? 'JavaScript' : 'Shell', '等待', typed ? '等待' : '终止'][index],
        );
        expect(reads).toHaveLength(index * 2);
        await pair.locator('summary').click();
        const bodies = pair.locator('.sd-tool-payload-grid pre');
        await expect(bodies.last()).toHaveText(tool.result);
        await expect.poll(async () => {
          const text = await bodies.first().textContent();
          try { return typeof tool.input === 'string' ? text : JSON.parse(text); }
          catch { return text; }
        }).toEqual(tool.input);
        expect(reads.filter(path => path.endsWith(':' + tool.id))).toEqual([
          importedApi + '/payload/tool:input:' + tool.id, importedApi + '/payload/tool:result:' + tool.id,
        ]);
      }
    } finally {
      expect((await request.delete(importedApi, { headers: { Origin: new URL(baseURL).origin } })).status()).toBe(204);
    }
  });
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
      const round = page.locator('[data-trace-round-row]').first();
      await expect(round).toContainText(inputRecorded ? 'Synthetic text-only question' : 'Synthetic text-only answer');
      await round.locator('[data-action="toggle-round"]').click();
      const detail = page.locator('#round-1-detail');
      await expect(detail.locator('[data-tool-call-id]')).toHaveCount(0);
      const modal = page.locator('dialog[open]');
      if (inputRecorded) {
        await round.getByRole('button', { name: 'Request', exact: true }).click();
        await expect(modal).toContainText('Synthetic text-only question');
        await page.keyboard.press('Escape');
      } else {
        await expect(round.getByRole('button', { name: 'Request', exact: true })).toHaveCount(0);
      }
      await round.getByRole('button', { name: 'Response', exact: true }).click();
      await expect(modal).toContainText('Synthetic text-only answer');
    } finally {
      expect((await request.delete('/api/imports/' + imported.import_id, { headers: { Origin: new URL(baseURL).origin } })).status()).toBe(204);
    }
  });
}

test('execution API pagination and filters preserve diagnostics', async ({ request, executionImport: { api } }) => {
  const response = await request.get(api + '/execution');
  const first = await response.json();
  expect(first.total).toBe(27);
  expect(first.items).toHaveLength(20);
  expect(JSON.stringify(first)).not.toContain('Synthetic result');
  for (const query of ['limit=0', 'limit=101', 'limit=no', 'cursor=broken', 'status=other']) {
    expect((await request.get(api + '/execution?' + query)).status()).toBe(400);
  }
  expect((await request.get(api + '/execution?status=failed&cursor=' + first.nextCursor)).status()).toBe(400);
  const continuation = await (await request.get(api + '/execution?cursor=' + first.nextCursor)).json();
  expect(continuation.items).toHaveLength(7);
  expect(continuation.diagnostics).toEqual(first.diagnostics);
  expect(continuation.items.find(item => item.tool.toolCallId === 'synthetic-action-24').tool.observation.durationNanos).toBe(9e9);
  expect(first.diagnostics.measuredTools).toBe(26);
  const filtered = await (await request.get(api + '/execution?status=failed')).json();
  expect(filtered.items.map(item => item.tool.toolCallId)).toEqual(['synthetic-action-27']);
  expect(filtered.diagnostics).toEqual(first.diagnostics);
  const summary = await (await request.get(api + '/execution?summary=1')).json();
  expect(summary.items ?? []).toEqual([]);
  expect(summary.diagnostics).toEqual(first.diagnostics);
});

test('failure locator finds an off-page round and opens the exact source tool and call', async ({ page, executionImport: { api, detail } }) => {
  const calls = [];
  page.on('request', req => {
    const url = new URL(req.url());
    if (url.pathname.startsWith(api + '/')) calls.push(url);
  });
  // Use the production first-page and target windows, with a one-round initial page.
  await page.route(`**${api}/rounds`, route => {
    const url = new URL(route.request().url());
    url.searchParams.set('limit', '1');
    return route.continue({ url: url.href });
  });
  await page.goto(detail);
  await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  const trace = page.locator('[data-trace-panel]');
  const failure = trace.locator('[data-execution-locate="synthetic-action-27"]');
  await expect(failure).toBeVisible();
  await expect(trace.locator('[data-trace-round-row]')).toHaveCount(1);
  expect(calls.filter(url => url.pathname.endsWith('/execution')).map(url => url.search)).toEqual(['?summary=1']);
  expect(calls.filter(url => url.pathname.includes('/payload/'))).toHaveLength(0);

  await failure.click();
  const failed = page.locator('[data-tool-call-id="synthetic-action-27"]');
  await expect(failed).toBeVisible();
  await expect(failed).toHaveAttribute('data-status', 'failed');
  const detailRow = trace.locator('[data-trace-detail]').filter({ has: failed });
  const pair = detailRow.locator('[data-tool-payload-pair][data-tool-id="synthetic-action-27"]');
  await expect(pair).toHaveAttribute('open');
  await expect(pair.locator('summary')).toBeFocused();
  expect(calls.some(url => url.pathname.endsWith('/rounds') && url.searchParams.has('target'))).toBe(true);
  expect(calls.some(url => /\/round\/\d+$/.test(url.pathname)
    && url.searchParams.get('target') === 'synthetic-action-27' && url.searchParams.get('target_kind') === 'tool')).toBe(true);
  await expect(pair.locator('pre').last()).toHaveText('Synthetic failure: exit 7');

  const modal = page.locator('dialog[open]');
  const callId = 'token_usage_record:synthetic-response-25';
  await expect(detailRow.locator(`[data-execution-call="${callId}"]`)).toContainText('合成模型输出 25');
  const roundId = new URL(page.url()).searchParams.get('round');
  const row = trace.locator(`[data-trace-round-row][data-round="${roundId}"]`);
  await row.getByRole('button', { name: 'Response', exact: true }).click();
  await expect(modal).toContainText('合成模型输出 25');
  await expect(modal).toContainText('synthetic-action-27');
  await expect(modal).not.toContainText('Synthetic failure: exit 7');
  await page.keyboard.press('Escape');
  await row.getByRole('button', { name: 'Request', exact: true }).click();
  await expect(modal).toContainText('Synthetic result 26');
});

test('three tools declared by the same response remain together without reads of their bodies', async ({ page, executionImport: { api, detail } }) => {
  const reads = [];
  page.on('request', req => { if (req.url().includes(api + '/payload/')) reads.push(req.url()); });
  await page.goto(detail);
  await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  await page.locator('[data-trace-round-row]').first().locator('[data-action="toggle-round"]').click();
  const group = page.locator('[data-call-tools="token_usage_record:synthetic-response-1"]');
  await expect(group.locator('[data-tool-call-id]')).toHaveCount(3);
  for (const id of [1, 2, 3]) await expect(group.locator(`[data-tool-call-id="synthetic-action-${id}"]`)).toBeVisible();
  await expect(group.locator('[data-tool-payload-pair][open]')).toHaveCount(0);
  expect(reads).toHaveLength(0);
});

async function localResultFixture(page, api, setup) {
  await page.locator('[data-trace-round-row]').first().locator('[data-action="toggle-round"]').click();
  const trigger = page.locator('[data-tool-call-id="synthetic-action-1"] [data-payload-kind="tool_result"]');
  await expect(trigger).toBeVisible();
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
  const input = n => ({ payload: { payloadId: 'main:req:synthetic-exact-input', kind: 'llm_request', status: 'missing', content: '', reading: [] },
    localResults: { items: [item('SYNTHETIC_EXACT_REFERENCE_' + n, { referenceId: 'synthetic-ref-' + n, targetPreview: null })], offset: 40, nextCursor: null, coverage: 'complete', targetReferenceId: 'synthetic-ref-' + n }, relations: null });
  await setup({ trigger, rootPath, targetPath, target, relation, item, result, input });
}

test('local result inclusion manual bounded references and exact late window', async ({ page, executionImport: { api, detail } }) => {
  await page.goto(detail); await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  await localResultFixture(page, api, async ({ trigger, rootPath, targetPath, target, relation, item, result, input }) => {
    const requests = [];
    await page.route('**' + api + '/payload/**', async route => {
      const url = new URL(route.request().url());
      requests.push(url);
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

test('local result inclusion null empty unknown ambiguous partial and safe complete raw', async ({ page, executionImport: { api, detail } }) => {
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

for (const status of [500, 400, 409]) test(`local result inclusion target HTTP ${status} preserves scoped recovery`, async ({ page, executionImport: { api, detail } }) => {
  await page.goto(detail); await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  await localResultFixture(page, api, async ({ trigger, rootPath, targetPath, item, result, input }) => {
    const requests = []; let targetReads = 0;
    await page.route('**' + api + '/payload/**', async route => {
      const url = new URL(route.request().url());
      requests.push(url);
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

test('local result inclusion same ID reopening rejects late payload', async ({ page, executionImport: { api, detail } }) => {
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

for (const action of ['focus', 'return', 'close']) test(`local result inclusion delayed target respects later ${action}`, async ({ page, executionImport: { api, detail } }) => {
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

test('local result inclusion typed empty input survives missing legacy status and copies safe original', async ({ page, executionImport: { api, detail } }) => {
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

test('local result inclusion late relationship page cannot revive closed source', async ({ page, executionImport: { api, detail } }) => {
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

test('local result inclusion rejects a target from another API scope without fallback', async ({ page, executionImport: { api, detail } }) => {
  await page.goto(detail); await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  await localResultFixture(page, api, async ({ trigger, rootPath, target, relation, item, result }) => {
    const requests = [];
    page.on('request', r => {
      const url = new URL(r.url());
      if (url.pathname.includes('/payload/')) requests.push(url);
    });
    await page.route('**' + rootPath + '?**', route => route.fulfill({ json: result([item('SYNTHETIC_SCOPED_RESULT', {
      targetPreview: relation([{ ...target(), apiUrl: '/api/imports/synthetic-other-scope/payload/synthetic-input' }]),
    })]) }));
    await trigger.click(); const modal = page.locator('dialog.payload-modal[open]');
    await modal.getByRole('button', { name: '查看准确引用', exact: true }).click();
    await expect(modal).toContainText('此入口不属于当前范围'); expect(requests).toHaveLength(1);
    await expect(modal).toContainText('SYNTHETIC_SCOPED_RESULT');
  });
});

for (const status of [500, 409]) test(`local result inclusion delayed attribution ${status} respects newer focus`, async ({ page, executionImport: { api, detail } }) => {
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
      await expect(modal.locator('[data-payload-attribution="request"]')).toContainText(status === 409 ? '索引已变化' : '输入用量明细暂不可用。');
      if (status === 409) await expect(modal.locator('[data-local-result-return]')).toHaveCount(0);
      else await expect(modal.locator('[data-local-result-return]')).toHaveCount(1);
    } finally { release(); }
  });
});

test('local result inclusion input pagination keeps pending attribution and its Retry alive', async ({ page, executionImport: { api, detail } }) => {
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
      await expect(attribution).toContainText('输入用量明细暂不可用。'); await expect(close).toBeFocused();
      await attribution.getByRole('button', { name: 'Retry', exact: true }).click();
      await expect(attribution).toHaveAttribute('data-attribution-call', 'synthetic-input'); await expect(attribution).toHaveAttribute('data-attribution-scope', 'subagent');
      await modal.getByRole('button', { name: '返回结果', exact: true }).click(); await expect(modal).toContainText('SYNTHETIC_SOURCE_WITH_PAGING');
    } finally { release(); }
  });
});

test('local result inclusion result page Retry retains current rows and original cursor', async ({ page, executionImport: { api, detail } }) => {
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


test('local result inclusion tool-level truncation stays explicit without changing Copy', async ({ page, executionImport: { api, detail } }, testInfo) => {
  await page.setViewportSize({ width: 1024, height: 900 });
  await page.goto(detail); await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  await page.evaluate(() => { window.syntheticResultCopies = []; Object.defineProperty(navigator, 'clipboard', { configurable: true,
    value: { writeText: async text => window.syntheticResultCopies.push(text) } }); });
  await localResultFixture(page, api, async ({ trigger, rootPath, item, result }) => {
    const body = result([item('SYNTHETIC_COMPLETE_ITEM')]);
    body.payload.truncated = true; body.payload.content = 'SYNTHETIC_RECORDED_RAW_PREFIX';
    await page.route('**' + rootPath + '?**', route => route.fulfill({ json: body }));
    await trigger.click(); const modal = page.locator('dialog.payload-modal[open]');
    await expect(modal.getByText('工具级全文已截断；各结果正文状态见下方分项。', { exact: true })).toBeVisible();
    await captureDiagnosticScreenshot(modal, { path: testInfo.outputPath('local-result-truncated-first-1024.png') });
    await expect(modal.locator('[data-local-result]')).not.toContainText('正文已截断');
    const original = modal.locator('[data-tool-result-original]').first();
    await expect(original.locator('summary').first()).toHaveText('工具级全文、包装说明与原始载荷（已截断）');
    await original.locator('summary').first().click(); await modal.getByRole('button', { name: 'Copy', exact: true }).click();
    expect(await page.evaluate(() => window.syntheticResultCopies)).toEqual(['SYNTHETIC_RECORDED_RAW_PREFIX']);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await captureDiagnosticScreenshot(modal, { path: testInfo.outputPath('local-result-truncated-1024.png') });
  });
});

test('local result inclusion expired target recovery cannot reopen an old ID in a new API scope', async ({ page, executionImport: { api, detail } }) => {
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
