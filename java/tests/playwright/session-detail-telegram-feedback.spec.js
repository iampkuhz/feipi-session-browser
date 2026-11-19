const { test, expect } = require('@playwright/test');
const { executionSourceRecords } = require('../fixtures/generate-session-fixtures');

// 全部为合成原始 Codex 记录，经实际导入/normalization/API；绝不执行其中命令。
const COMMAND = 'git push origin synthetic-review';
const WRAPPER = `const receipt = await tools.exec_command({cmd:"${COMMAND}",yield_time_ms:1000}); text(JSON.stringify(receipt));`;
const OUTPUT = 'SYNTHETIC final stdout\nfirst line\nsecond line\n';
const RAW = 'Script completed\nWall time 5.1 seconds\nOutput:\n' + JSON.stringify({
  chunk_id: 'synthetic-chunk', exit_code: 0, script: 'synthetic wrapper explanation', output: OUTPUT,
});
const UNKNOWN = JSON.stringify({ script: 'synthetic declaration, not final output', message: 'unrecognized envelope' });
const FALLBACKS = [
  JSON.stringify({ output: ['synthetic non-text output'], extra: 'must remain visible' }),
  JSON.stringify({ output: 'one', result: 'two' }),
  '{"output":"synthetic incomplete',
];
const LONG_OUTPUT = 'synthetic long line ' + 'abcdef'.repeat(80);
let detail, api;

test.beforeEach(async ({ request, baseURL, page }) => {
  api = undefined;
  const records = executionSourceRecords();
  const call = n => records.find(r => r.payload.type === 'function_call' && r.payload.call_id === `synthetic-action-${n}`).payload;
  const result = n => records.find(r => r.payload.type === 'function_call_output' && r.payload.call_id === `synthetic-action-${n}`).payload;
  call(1).name = 'exec';
  call(1).arguments = WRAPPER;
  call(2).arguments = JSON.stringify({ parameters: { arguments: { script: 'printf one; printf two' } } });
  call(3).arguments = 'const dynamic = await tools.exec_command({cmd:buildCommand()});';
  call(4).arguments = JSON.stringify({ cmd: 'printf "four"' });
  result(1).output = RAW;
  result(2).output = JSON.stringify({ result: '' });
  result(3).output = UNKNOWN;
  result(4).output = 'Script completed\nWall time 1 seconds\nOutput:\n  synthetic plain stdout\n';
  FALLBACKS.forEach((value, i) => { result(i + 5).output = value; });
  result(8).output = JSON.stringify({ output: LONG_OUTPUT });
  const response = await request.post('/api/imports', {
    headers: { Origin: new URL(baseURL).origin },
    multipart: { source: 'codex', file: { name: 'synthetic-telegram-feedback.jsonl', mimeType: 'application/x-ndjson',
      buffer: Buffer.from(records.map(JSON.stringify).join('\n') + '\n') } },
  });
  expect(response.status()).toBe(201);
  const imported = await response.json();
  detail = imported.detail_url;
  api = '/api/imports/' + imported.import_id;
  await page.addInitScript(() => {
    window.syntheticCopied = [];
    Object.defineProperty(navigator, 'clipboard', { value: { writeText: async value => window.syntheticCopied.push(value) } });
  });
});

test.afterEach(async ({ request, baseURL }) => {
  if (api) expect((await request.delete(api, { headers: { Origin: new URL(baseURL).origin } })).status()).toBe(204);
});

async function openResult(page, n) {
  const row = page.locator(`[data-execution-tool="synthetic-action-${n}"]`);
  await row.locator('.se-tool-evidence > summary').click();
  await row.getByRole('button', { name: '执行结果', exact: true }).click();
  const modal = page.locator('dialog.payload-modal');
  await modal.locator('[data-tool-result-original] > summary').first().click();
  await expect(modal.locator('.sd-payload-shell--tool-result')).toBeVisible();
  return modal;
}

for (const width of [1440, 390]) {
  test(`voice feedback: compact commands and output layers from raw import at ${width}px`, async ({ page, request }) => {
    await page.setViewportSize({ width, height: 1100 });
    await page.goto(detail);
    await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
    const groups = page.locator('[data-execution-group]');
    await expect(groups.first().locator('h3')).toHaveText('模型响应记录 #1');
    await expect(groups.first().locator('[data-execution-tool]')).toHaveCount(3);
    await expect(groups.nth(1).locator('h3')).toHaveText('模型响应记录 #2');
    await expect(groups.nth(1).locator('[data-execution-tool]')).toHaveCount(1);
    await expect(groups.locator(':scope > .se-response-text')).toHaveCount(0);
    await expect(page.locator('[data-execution-tool="synthetic-action-1"] code')).toHaveText(COMMAND);
    await expect(page.locator('[data-execution-tool="synthetic-action-2"] code')).toHaveText('printf one; printf two');
    await expect(page.locator('[data-execution-tool="synthetic-action-3"] code')).toHaveText('const dynamic = await tools.exec_command({cmd:buildCommand()});');
    if (width === 1440) {
      const bounds = await groups.nth(1).boundingBox();
      expect(bounds.height).toBeLessThanOrEqual(60);
      const command = await groups.nth(1).locator('code').boundingBox();
      const number = await groups.nth(1).locator('h3').boundingBox();
      expect(Math.abs(command.y - number.y)).toBeLessThan(12);
    }
    const response = await request.get(api + '/execution');
    expect(response.ok()).toBe(true);
    const body = await response.json();
    expect(body.items[0].tool.inputPreview).toBe(COMMAND);
    expect(body.items[0].tool.durationMs).toBe(0);
    expect(body.diagnostics.totalTools).toBe(27);
    await groups.first().evaluate(n => { n.scrollIntoView({ block: 'start' }); window.scrollBy(0, -40); });
    await page.screenshot({ path: test.info().outputPath(`compact-process-${width}.png`) });
    await groups.first().screenshot({ path: test.info().outputPath(`command-summary-${width}.png`) });
    const modal = await openResult(page, 1);
    await expect(page.locator('[data-execution-tool="synthetic-action-1"] .se-status')).toHaveText('退出码 0');
    await expect(modal.locator('.sd-kv').filter({ hasText: /^内容状态/ })).toHaveText('内容状态available');
    const meta = await modal.locator('.sd-payload-meta').boundingBox();
    const main = await modal.locator('.sd-payload-shell .sd-payload-main').boundingBox();
    expect(main.y).toBeGreaterThanOrEqual(meta.y + meta.height);
    expect(Math.abs(main.width - meta.width)).toBeLessThan(4);
    await expect(modal.locator('[data-tool-output]')).toContainText('SYNTHETIC final stdout');
    await expect(modal.locator('[data-tool-output]')).not.toContainText('Script completed');
    await expect(modal.locator('[data-tool-output]')).not.toContainText('synthetic wrapper explanation');
    await expect(modal.locator('.sd-payload-shell--tool-result [data-tool-result-original]')).not.toHaveAttribute('open');
    await modal.locator('.payload-modal__panel').screenshot({ path: test.info().outputPath(`result-modal-${width}.png`) });
    await modal.locator('[data-tool-output]').screenshot({ path: test.info().outputPath(`actual-output-${width}.png`) });
    await modal.getByRole('button', { name: '复制输出', exact: true }).click();
    expect(await page.evaluate(() => window.syntheticCopied.at(-1))).toBe(OUTPUT);
    await modal.locator('.sd-payload-shell--tool-result [data-tool-result-original] > summary').focus();
    await page.keyboard.press('Enter');
    await expect(modal.locator('.sd-payload-shell--tool-result [data-tool-result-original] pre')).toHaveText(RAW);
    await modal.getByRole('button', { name: '复制原始载荷', exact: true }).click();
    expect(await page.evaluate(() => window.syntheticCopied.at(-1))).toBe(RAW);
    await page.keyboard.press('Escape');
    await expect(modal).toBeHidden();
    const first = groups.first();
    await first.locator('header').getByRole('button', { name: '模型输出', exact: true }).click();
    await expect(modal.locator('.sd-conversation-payload')).toContainText('合成模型输出 1：一次下发三个工具');
    await expect(modal.locator('[data-tool-output]')).toHaveCount(0);
    await page.keyboard.press('Escape');
    await page.locator('[data-execution-tool="synthetic-action-1"]').getByRole('button', { name: '命令或参数', exact: true }).click();
    await expect(modal.locator('.sd-kv').filter({ hasText: /^内容状态/ })).toHaveText('内容状态available');
    await expect(modal.locator('.sd-payload-shell .sd-payload-main')).toContainText(WRAPPER);
    await expect(modal.locator('[data-tool-output]')).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    await page.keyboard.press('Escape');
    await page.getByRole('button', { name: '定位首个失败', exact: true }).click();
    const failed = page.locator('[data-execution-tool="synthetic-action-27"]');
    await expect(failed).toBeFocused();
    await expect(failed.locator('.se-status')).toHaveText('退出码 7');
    await openResult(page, 27);
    // 正文可读与命令成功是两个维度：真实来源 exit 7 的 Result 仍为 available。
    await expect(modal.locator('.sd-kv').filter({ hasText: /^内容状态/ })).toHaveText('内容状态available');
    await expect(modal.locator('.sd-payload-shell .sd-payload-main')).toContainText('Synthetic failure: exit 7');
    await modal.getByRole('button', { name: 'Copy', exact: true }).click();
    expect(await page.evaluate(() => window.syntheticCopied.at(-1))).toBe('Synthetic failure: exit 7');
    await modal.screenshot({ path: test.info().outputPath(`failed-result-content-status-${width}.png`) });
    expect(await modal.locator('.payload-modal__panel').evaluate(n => n.scrollWidth <= n.clientWidth + 1)).toBe(true);
  });

  test(`voice feedback: empty output, unknown fallback and plain envelope at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1100 });
    await page.goto(detail);
    await expect(page.locator('[data-execution-tool]')).toHaveCount(20);
    let modal = await openResult(page, 2);
    await expect(modal.locator('[data-tool-output]')).toContainText('已记录空输出（不是缺失）');
    await page.keyboard.press('Escape');
    modal = await openResult(page, 3);
    await expect(page.locator('[data-execution-tool="synthetic-action-3"] .se-status')).toHaveText('已记录结果 · 退出未知');
    await expect(modal.locator('.sd-kv').filter({ hasText: /^内容状态/ })).toHaveText('内容状态available');
    await expect(modal.locator('[data-tool-output]')).toHaveCount(0);
    await expect(modal.locator('.sd-payload-shell .sd-payload-main')).toContainText(UNKNOWN);
    await expect(modal.locator('.sd-payload-meta')).toContainText('按记录原文展示；未拆分 output/result 字段');
    await expect(modal.locator('.sd-payload-shell--tool-result .sd-payload-warning')).toHaveCount(0);
    await modal.getByRole('button', { name: 'Copy', exact: true }).click();
    expect(await page.evaluate(() => window.syntheticCopied.at(-1))).toBe(UNKNOWN);
    expect(await modal.locator('.payload-modal__panel').evaluate(n => n.scrollWidth <= n.clientWidth + 1)).toBe(true);
    await modal.screenshot({ path: test.info().outputPath(`neutral-fallback-${width}.png`) });
    await page.keyboard.press('Escape');
    modal = await openResult(page, 4);
    await expect(modal.locator('[data-tool-output]')).toContainText('synthetic plain stdout');
    await modal.getByRole('button', { name: '复制输出', exact: true }).click();
    expect(await page.evaluate(() => window.syntheticCopied.at(-1))).toBe('  synthetic plain stdout\n');
    await page.keyboard.press('Escape');
    for (let i = 0; i < FALLBACKS.length; i += 1) {
      modal = await openResult(page, i + 5);
      await expect(modal.locator('[data-tool-output]')).toHaveCount(0);
      await expect(modal.locator('.sd-payload-shell .sd-payload-main')).toContainText(FALLBACKS[i]);
      await expect(modal.locator('.sd-payload-meta')).toContainText('按记录原文展示；未拆分 output/result 字段');
      await expect(modal.locator('.sd-payload-shell--tool-result .sd-payload-warning')).toHaveCount(0);
      await page.keyboard.press('Escape');
    }
    modal = await openResult(page, 8);
    await expect(modal.locator('[data-tool-output]')).toContainText(LONG_OUTPUT);
    await modal.getByRole('button', { name: '复制输出', exact: true }).click();
    expect(await page.evaluate(() => window.syntheticCopied.at(-1))).toBe(LONG_OUTPUT);
    expect(await modal.locator('.payload-modal__panel').evaluate(n => n.scrollWidth <= n.clientWidth + 1)).toBe(true);
    await page.keyboard.press('Escape');

    // UI-only 状态边界：字段拆分说明不能覆盖截断或未记录状态，不作为来源解析证明。
    let injected;
    await page.route('**' + api + '/payload/**', async route => {
      const response = await route.fetch();
      await route.fulfill({ response, status: 200, json: { payload: injected, localResults: { items: [], offset: 0, nextCursor: null, coverage: 'complete', reason: '', targetReferenceId: null }, relations: null } });
    });
    for (const status of ['available', 'missing', 'unavailable']) {
      injected = { kind: 'tool_result', status, text: status === 'available' ? UNKNOWN : '', truncated: status === 'available' };
      await page.locator('[data-execution-tool="synthetic-action-3"]').getByRole('button', { name: '执行结果', exact: true }).click();
      await modal.locator('[data-tool-result-original] > summary').first().click();
      await expect(modal.locator('.sd-kv').filter({ hasText: /^内容状态/ })).toHaveText('内容状态' + status);
      if (status === 'available') {
        await expect(modal.locator('.sd-payload-shell--tool-result .sd-payload-warning')).toHaveText('内容已截断。');
        await expect(modal.locator('.sd-payload-meta')).toContainText('按记录原文展示；未拆分 output/result 字段');
        await expect(modal.locator('.sd-payload-shell .sd-payload-main')).toContainText(UNKNOWN);
      } else {
        await expect(modal.locator('.sd-payload-shell--tool-result .sd-payload-empty')).toContainText('内容未记录');
        await expect(modal.locator('.sd-payload-meta')).not.toContainText('按记录原文展示');
        await expect(modal.getByRole('button', { name: 'Copy', exact: true })).toHaveCount(0);
      }
      await page.keyboard.press('Escape');
    }
  });
}

// Same mature Qoder template and literal multiline variant; never execute these commands.
const MULTILINE_QODER_RECORDS = [
  {
    "role": "user",
    "sessionId": "hifi-viz-session-001",
    "uuid": "synthetic-qoder-user",
    "timestamp": "2026-06-01T10:00:00Z",
    "cwd": "/synthetic/import-project",
    "content": [
      {
        "type": "text",
        "text": "Synthetic import request: qoder"
      }
    ]
  },
  {
    "role": "assistant",
    "sessionId": "hifi-viz-session-001",
    "uuid": "synthetic-qoder-assistant",
    "id": "synthetic-qoder-message",
    "timestamp": "2026-06-01T10:00:01Z",
    "model": "synthetic-qoder-model",
    "content": [
      {
        "type": "text",
        "text": "Synthetic import response: qoder"
      },
      {
        "type": "tool_use",
        "id": "synthetic-tool",
        "name": "Bash",
        "input": {
          "command": "# SYNTHETIC ONLY; NEVER EXECUTED\nprintf '%s\\n' 'phase A'\npython3 - <<'PY'\nprint('phase B')\nPY\nprintf '%s\\n' 'phase C'\n"
        }
      }
    ],
    "usage": {
      "input_tokens": 11,
      "cache_read_input_tokens": 3,
      "cache_creation_input_tokens": 2,
      "output_tokens": 7
    }
  },
  {
    "role": "user",
    "sessionId": "hifi-viz-session-001",
    "uuid": "synthetic-qoder-tool-result",
    "timestamp": "2026-06-01T10:00:02Z",
    "content": [
      {
        "type": "tool_result",
        "tool_use_id": "synthetic-tool",
        "content": "Synthetic tool result: complete original output\nsynthetic-tool-result-end"
      }
    ]
  }
];
for (const width of [1440, 390]) test('多行Input real Qoder source keeps one tool and exact parameters at ' + width + 'px', async ({ page, request, baseURL }) => {
  const raw = MULTILINE_QODER_RECORDS.map(JSON.stringify).join('\n') + '\n';
  const script = MULTILINE_QODER_RECORDS[1].content[1].input.command;
  const response = await request.post('/api/imports', { headers: { Origin: new URL(baseURL).origin }, multipart: { source: 'qoder', file: { name: 'synthetic-script.jsonl', mimeType: 'application/x-ndjson', buffer: Buffer.from(raw) } } });
  expect(response.status()).toBe(201); const imported = await response.json(), inputApi = '/api/imports/' + imported.import_id;
  const requests = []; page.on('request', r => { if (r.url().includes('/api/')) requests.push(r.url()); });
  try {
    await page.setViewportSize({ width, height: 900 }); await page.goto(imported.detail_url); await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
    const execution = await (await request.get(inputApi + '/execution')).json();
    expect(execution.items).toHaveLength(1); expect(execution.items[0].tool.toolCallId).toBe('synthetic-tool'); expect(execution.items[0].group.toolCount).toBe(1); expect(execution.items[0].tool.durationMs).toBeNull();
    expect(execution.diagnostics).toMatchObject({ totalTools: 1, measuredTools: 0 });
    expect(requests.some(url => url.includes('/payload/'))).toBe(false);
    await page.screenshot({ path: test.info().outputPath('multiline-default-' + width + '.png'), fullPage: true });
    const tool = page.locator('[data-execution-tool="synthetic-tool"]'); await tool.locator('.se-tool-evidence > summary').click(); await tool.getByRole('button', { name: '命令或参数', exact: true }).click();
    const modal = page.locator('dialog.payload-modal');
    await expect(modal.locator('.sd-payload-meta')).toContainText('tool_input'); // Wait for the actual payload, not merely the dialog shell.
    expect(await modal.locator('[data-tool-input-command]').count()).toBe(1); // Native original red retained; not a DTO source.
    expect(await modal.locator('[data-tool-input-command] pre').textContent()).toBe(script);
    await expect(modal.locator('[data-tool-input-original]')).not.toHaveAttribute('open', '');
    const payload = await (await request.get(inputApi + '/payload/' + encodeURIComponent('tool:input:synthetic-tool'))).json();
    expect(payload.kind).toBe('tool_input'); const original = payload.text || payload.content;
    await modal.getByRole('button', { name: '复制命令文本', exact: true }).click(); expect(await page.evaluate(() => syntheticCopied.at(-1))).toBe(script);
    await modal.screenshot({ path: test.info().outputPath('multiline-input-' + width + '.png') });
    await modal.locator('[data-tool-input-original] > summary').click(); expect(await modal.locator('[data-tool-input-original] pre').textContent()).toBe(original);
    await modal.getByRole('button', { name: '复制原始参数', exact: true }).click(); expect(await page.evaluate(() => syntheticCopied.at(-1))).toBe(original);
    await modal.screenshot({ path: test.info().outputPath('multiline-original-' + width + '.png') });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true); await page.keyboard.press('Escape'); await expect(modal).not.toBeVisible();
    await test.info().attach('multiline-native-source-api.json', { body: JSON.stringify({ raw, script, execution, payload, width }), contentType: 'application/json' });
  } finally { expect((await request.delete(inputApi, { headers: { Origin: new URL(baseURL).origin } })).status()).toBe(204); }
});

// Explicit consumer-only payload guards: transport bodies below are not parser/source evidence.
async function multilineGuardReader(page) {
  await page.goto(detail); await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  const row = page.locator('[data-execution-tool="synthetic-action-4"]'); await row.locator('.se-tool-evidence > summary').click();
  const button = row.getByRole('button', { name: '命令或参数', exact: true }); let body, index = 0;
  await page.route('**/payload/**', route => route.fulfill({ json: body }));
  return async payload => {
    body = { kind: 'tool_input', status: 'available', ...payload };
    await button.evaluate((node, id) => node.setAttribute('data-payload-id', id), 'tool:input:ui-multiline-guard-' + index++);
    const response = page.waitForResponse(r => r.url().includes('/payload/')); await button.click(); await response;
    return page.locator('dialog.payload-modal');
  };
}

test('多行Input UI-only literal command preservation and plain-text safety guards', async ({ page }) => {
  const read = await multilineGuardReader(page);
  const script = '  echo "引号 🧪"\r\n\tprintf "C:\\synthetic\\x"\n<img src=x onerror="window.syntheticInputExecuted=true">\n[REDACTED_TOKEN]\n';
  const cases = ['cmd', 'command', 'script'].map(key => ({ text: JSON.stringify({ [key]: script }), expected: script }));
  const atLimit = 'x'.repeat(65536 - JSON.stringify({ cmd: '\n' }).length) + '\n';
  cases.push({ text: JSON.stringify({ cmd: atLimit }), expected: atLimit }); expect(cases.at(-1).text.length).toBe(65536);
  await page.evaluate(() => window.syntheticInputExecuted = false);
  for (const payload of cases) {
    const modal = await read(payload); await expect(modal.locator('[data-tool-input-command] pre')).toHaveText(payload.expected);
    expect(await modal.locator('[data-tool-input-command] pre').textContent()).toBe(payload.expected);
    await expect(modal.locator('img, svg, script')).toHaveCount(0); expect(await page.evaluate(() => syntheticInputExecuted)).toBe(false);
    await modal.getByRole('button', { name: '复制命令文本', exact: true }).click(); expect(await page.evaluate(() => syntheticCopied.at(-1))).toBe(payload.expected);
    await modal.locator('[data-tool-input-original] > summary').click(); expect(await modal.locator('[data-tool-input-original] pre').textContent()).toBe(payload.text);
    await modal.getByRole('button', { name: '复制原始参数', exact: true }).click(); expect(await page.evaluate(() => syntheticCopied.at(-1))).toBe(payload.text);
    await page.keyboard.press('Escape');
  }
  await test.info().attach('multiline-literal-ui-guards.json', { body: JSON.stringify({ keys: ['cmd', 'command', 'script'], text: script, exactCopy: true, inclusiveLimit: 65536, sourceEvidence: false }), contentType: 'application/json' });
});

test('多行Input UI-only ambiguity and incomplete bodies conservatively keep original payload', async ({ page }) => {
  const read = await multilineGuardReader(page), literal = JSON.stringify('echo one\necho two');
  const fallbacks = [
    { text: '{"cmd":' + literal + ',"cmd":' + literal + '}' },
    { text: '{"cmd":' + literal + ',"c\\u006dd":' + literal + '}' },
    { text: '{"c\\u006dd":' + literal + '}' },
    { text: '{"cmd":' + literal + ',"command":' + literal + '}' },
    { text: '{"cmd":' + literal + ',"cwd":"/synthetic"}' },
    { text: JSON.stringify({ parameters: { command: 'echo one\necho two' } }) },
    ...[null, 7, true, ['echo one\necho two'], { script: 'echo one\necho two' }].map(cmd => ({ text: JSON.stringify({ cmd }) })),
    { text: 'const dynamic = buildCommand();\n' }, { text: '{"cmd":"bad\\x"}' }, { text: '{"cmd":"unterminated' },
    { text: '{"cmd":' + literal + '} trailing' }, { text: '{"cmd":' + literal + ',}' },
    ...['\u00a0', '\ufeff', '\u2028', '\u2029'].map(space => ({ text: space + '{"cmd":' + literal + '}' })),
    { text: JSON.stringify({ cmd: 'echo one' }) }, { text: JSON.stringify({ cmd: 'echo one\\necho two' }) },
    { text: JSON.stringify({ cmd: 'x'.repeat(65536) + '\n' }) },
    { text: '{"cmd":' + literal + '}', truncated: true }, { text: '{"cmd":' + literal + '}', status: 'truncated' },
    { text: '{"cmd":' + literal + '}', status: 'missing' },
    { text: '{"cmd":' + literal + '}', kind: 'tool_result' }, { text: '{"cmd":' + literal + '}', kind: 'llm_response' },
  ];
  for (const payload of fallbacks) {
    const modal = await read(payload); await expect.poll(() => modal.locator('pre').allTextContents()).toContain(payload.text);
    await expect(modal.locator('[data-tool-input-command], [data-tool-input-original]')).toHaveCount(0);
    if (!payload.kind || payload.kind === 'tool_result') {
      await modal.getByRole('button', { name: 'Copy', exact: true }).click(); expect(await page.evaluate(() => syntheticCopied.at(-1))).toBe(payload.text);
    }
    await page.keyboard.press('Escape');
  }
  await test.info().attach('multiline-fallback-ui-guards.json', { body: JSON.stringify({ cases: fallbacks, sourceEvidence: false }), contentType: 'application/json' });
});
