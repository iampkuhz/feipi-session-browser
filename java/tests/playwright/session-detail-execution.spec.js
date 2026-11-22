const { test: base, expect } = require('@playwright/test');

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
