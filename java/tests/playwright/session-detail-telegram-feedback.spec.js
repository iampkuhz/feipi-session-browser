const { test: base, expect } = require('@playwright/test');
const { captureDiagnosticScreenshot } = require('./start-java-fixture-server');
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
const test = base.extend({
  feedbackImport: async ({ request, baseURL }, use) => {
    const headers = { Origin: new URL(baseURL).origin };
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
      headers,
      multipart: { source: 'codex', file: { name: 'synthetic-telegram-feedback.jsonl', mimeType: 'application/x-ndjson',
        buffer: Buffer.from(records.map(JSON.stringify).join('\n') + '\n') } },
    });
    expect(response.status(), await response.text()).toBe(201);
    const imported = await response.json();
    const api = '/api/imports/' + imported.import_id;
    try {
      await use({ detail: imported.detail_url, api });
    } finally {
      expect((await request.delete(api, { headers })).status()).toBe(204);
    }
  },
});

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    window.syntheticCopied = [];
    Object.defineProperty(navigator, 'clipboard', { value: { writeText: async value => window.syntheticCopied.push(value) } });
  });
});

async function expandTools(page) {
  await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  const rows = page.locator('[data-trace-round-row]');
  const all = page.locator('[data-action="toggle-all"]');
  if (await all.getAttribute('data-state') === 'collapse') {
    await expect(rows.first()).toBeVisible();
    await all.click();
  }
}

function resultButton(page, id) {
  return page.locator('[data-tool-call-id="' + id + '"] [data-payload-kind="tool_result"]');
}

async function openInput(page, id) {
  const pair = page.locator('[data-tool-payload-pair][data-tool-id="' + id + '"]');
  if (!await pair.getAttribute('open')) await pair.locator('summary').click();
  const button = pair.locator('[data-payload-kind="tool_input"]');
  await button.click();
  return button;
}

async function openResult(page, n) {
  await resultButton(page, 'synthetic-action-' + n).click();
  const modal = page.locator('dialog.payload-modal');
  await expect(modal.locator('.sd-local-results')).toBeVisible();
  await expect(modal.locator('[data-tool-result-original]')).not.toHaveAttribute('open');
  return modal;
}

for (const width of [1440, 1024]) {
  test(`voice feedback: compact commands and output layers from raw import at ${width}px`, async ({ page, request, feedbackImport: { detail, api } }) => {
    await page.setViewportSize({ width, height: 1100 });
    await page.goto(detail);
    await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
    await expandTools(page);
    const groups = page.locator('[data-call-tools]');
    await expect(groups.first().locator('[data-tool-call-id]')).toHaveCount(3);
    await expect(groups.nth(1).locator('[data-tool-call-id]')).toHaveCount(1);
    for (const [n, command] of [[1, COMMAND], [2, 'printf one; printf two'], [3, 'const dynamic = await tools.exec_command({cmd:buildCommand()});']]) {
      await expect(page.locator('[data-tool-call-id="synthetic-action-' + n + '"] .sd-tool-cmd')).toContainText(command);
    }
    const response = await request.get(api + '/execution');
    expect(response.ok()).toBe(true);
    const body = await response.json();
    expect(body.items[0].tool.inputPreview).toBe(COMMAND);
    expect(body.items[0].tool.durationMs).toBe(0);
    expect(body.diagnostics.totalTools).toBe(27);
    await groups.first().evaluate(n => { n.scrollIntoView({ block: 'start' }); window.scrollBy(0, -40); });
    await captureDiagnosticScreenshot(page, { path: test.info().outputPath(`compact-process-${width}.png`) });
    await captureDiagnosticScreenshot(groups.first(), { path: test.info().outputPath(`command-summary-${width}.png`) });
    const modal = await openResult(page, 1);
    const output = modal.locator('[data-reading-category="result"] pre');
    await expect(output).toHaveText(OUTPUT.trim());
    await expect(output).not.toContainText(/Script completed|synthetic wrapper explanation/);
    await captureDiagnosticScreenshot(modal.locator('.payload-modal__panel'), { path: test.info().outputPath(`result-modal-${width}.png`) });
    await captureDiagnosticScreenshot(output, { path: test.info().outputPath(`actual-output-${width}.png`) });
    await modal.getByRole('button', { name: '复制输出', exact: true }).click();
    expect(await page.evaluate(() => window.syntheticCopied.at(-1))).toBe(OUTPUT);
    const original = modal.locator('[data-tool-result-original]');
    await original.locator(':scope > summary').press('Enter');
    expect(await original.locator('pre').textContent()).toBe(RAW);
    await original.getByRole('button', { name: 'Copy', exact: true }).click();
    expect(await page.evaluate(() => window.syntheticCopied.at(-1))).toBe(RAW);
    await page.keyboard.press('Escape');
    await expect(modal).toBeHidden();
    await page.locator('[data-trace-round-row]').first().getByRole('button', { name: 'Response', exact: true }).click();
    await expect(modal.locator('.sd-conversation-payload')).toContainText('合成模型输出 1：一次下发三个工具');
    await expect(modal.locator('[data-tool-output]')).toHaveCount(0);
    await page.keyboard.press('Escape');
    await openInput(page, 'synthetic-action-1');
    await expect(modal.locator('.sd-kv').filter({ hasText: /^内容状态/ })).toHaveText('内容状态available');
    await expect(modal.locator('.sd-payload-shell .sd-payload-main')).toContainText(WRAPPER);
    await expect(modal.locator('[data-tool-output]')).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    await page.keyboard.press('Escape');
    await page.getByRole('button', { name: '定位首个失败', exact: true }).click();
    const failed = page.locator('[data-tool-call-id="synthetic-action-27"]');
    await expect(page.locator('[data-tool-payload-pair][data-tool-id="synthetic-action-27"] > summary')).toBeFocused();
    await expect(failed).toHaveAttribute('data-status', 'failed');
    await expect(failed).toContainText('7');
    const failedResult = page.waitForResponse(r => decodeURIComponent(new URL(r.url()).pathname).endsWith('/payload/tool:result:synthetic-action-27'));
    await openResult(page, 27);
    // 正文可读与命令成功是两个维度：真实来源 exit 7 的 Result 仍为 available。
    expect((await (await failedResult).json()).payload.status).toBe('available');
    await expect(modal.locator('[data-reading-category="result"]')).toContainText('Synthetic failure: exit 7');
    const failedOriginal = modal.locator('[data-tool-result-original]');
    await failedOriginal.locator(':scope > summary').click();
    await failedOriginal.getByRole('button', { name: 'Copy', exact: true }).click();
    expect(await page.evaluate(() => window.syntheticCopied.at(-1))).toBe('Synthetic failure: exit 7');
    await captureDiagnosticScreenshot(modal, { path: test.info().outputPath(`failed-result-content-status-${width}.png`) });
    expect(await modal.locator('.payload-modal__panel').evaluate(n => n.scrollWidth <= n.clientWidth + 1)).toBe(true);
  });

  test(`voice feedback: empty output, unknown fallback and plain envelope at ${width}px`, async ({ page, feedbackImport: { detail, api } }) => {
    await page.setViewportSize({ width, height: 1100 });
    await page.goto(detail);
    await expandTools(page);
    expect((await (await page.request.get(api + '/execution')).json()).items).toHaveLength(20);
    let modal = await openResult(page, 2);
    await expect(modal.locator('.sd-local-results')).toContainText('已记录空输出（不是缺失）');
    await page.keyboard.press('Escape');
    modal = await openResult(page, 3);
    await expect(modal.getByRole('button', { name: '复制输出', exact: true })).toHaveCount(0);
    await expect(modal.locator('[data-reading-category="result"] pre')).toHaveText(UNKNOWN);
    const original = modal.locator('[data-tool-result-original]');
    await original.locator(':scope > summary').click();
    await original.getByRole('button', { name: 'Copy', exact: true }).click();
    expect(await page.evaluate(() => window.syntheticCopied.at(-1))).toBe(UNKNOWN);
    expect(await modal.locator('.payload-modal__panel').evaluate(n => n.scrollWidth <= n.clientWidth + 1)).toBe(true);
    await captureDiagnosticScreenshot(modal, { path: test.info().outputPath(`neutral-fallback-${width}.png`) });
    await page.keyboard.press('Escape');
    modal = await openResult(page, 4);
    await expect(modal.locator('[data-reading-category="result"] pre')).toHaveText('synthetic plain stdout');
    await modal.getByRole('button', { name: '复制输出', exact: true }).click();
    expect(await page.evaluate(() => window.syntheticCopied.at(-1))).toBe('  synthetic plain stdout\n');
    await page.keyboard.press('Escape');
    for (let i = 0; i < FALLBACKS.length; i += 1) {
      modal = await openResult(page, i + 5);
      await expect(modal.getByRole('button', { name: '复制输出', exact: true })).toHaveCount(0);
      await expect(modal.locator('[data-reading-category="result"] pre')).toHaveText(FALLBACKS[i]);
      await page.keyboard.press('Escape');
    }
    modal = await openResult(page, 8);
    await expect(modal.locator('[data-reading-category="result"] pre')).toHaveText(LONG_OUTPUT);
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
      await resultButton(page, 'synthetic-action-3').click();
      await expect(modal.locator('.sd-local-results')).toBeVisible();
      if (status === 'available') {
        await expect(modal.locator('[data-unitemized-tool-output]')).toContainText('已截断');
        await expect(modal.locator('[data-reading-category="result"] pre')).toHaveText(UNKNOWN);
        await expect(modal.getByRole('button', { name: '复制输出', exact: true })).toHaveCount(0);
      } else {
        await expect(modal.locator('[data-reading-category="result"]')).toHaveCount(0);
        await expect(modal.locator('.sd-local-results')).toContainText(/未记录|未能单列/);
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
for (const width of [1440, 1024]) test('多行Input real Qoder source keeps one tool and exact parameters at ' + width + 'px', async ({ page, request, baseURL }) => {
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
    await captureDiagnosticScreenshot(page, { path: test.info().outputPath('multiline-default-' + width + '.png'), fullPage: true });
    await expandTools(page);
    await openInput(page, 'synthetic-tool');
    const modal = page.locator('dialog.payload-modal');
    await expect(modal.locator('.sd-payload-meta')).toContainText('tool_input'); // Wait for the actual payload, not merely the dialog shell.
    expect(await modal.locator('[data-tool-input-command]').count()).toBe(1); // Native original red retained; not a DTO source.
    expect(await modal.locator('[data-tool-input-command] pre').textContent()).toBe(script);
    await expect(modal.locator('[data-tool-input-original]')).not.toHaveAttribute('open', '');
    const payload = await (await request.get(inputApi + '/payload/' + encodeURIComponent('tool:input:synthetic-tool'))).json();
    expect(payload.kind).toBe('tool_input'); const original = payload.text || payload.content;
    await modal.getByRole('button', { name: '复制命令文本', exact: true }).click(); expect(await page.evaluate(() => syntheticCopied.at(-1))).toBe(script);
    await captureDiagnosticScreenshot(modal, { path: test.info().outputPath('multiline-input-' + width + '.png') });
    await modal.locator('[data-tool-input-original] > summary').click(); expect(await modal.locator('[data-tool-input-original] pre').textContent()).toBe(original);
    await modal.getByRole('button', { name: '复制原始参数', exact: true }).click(); expect(await page.evaluate(() => syntheticCopied.at(-1))).toBe(original);
    await captureDiagnosticScreenshot(modal, { path: test.info().outputPath('multiline-original-' + width + '.png') });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true); await page.keyboard.press('Escape'); await expect(modal).not.toBeVisible();
    await test.info().attach('multiline-native-source-api.json', { body: JSON.stringify({ raw, script, execution, payload, width }), contentType: 'application/json' });
  } finally { expect((await request.delete(inputApi, { headers: { Origin: new URL(baseURL).origin } })).status()).toBe(204); }
});

// Explicit consumer-only payload guards: transport bodies below are not parser/source evidence.
async function multilineGuardReader(page, detail) {
  await page.goto(detail); await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  await expandTools(page);
  const pair = page.locator('[data-tool-payload-pair][data-tool-id="synthetic-action-4"]');
  await pair.locator('summary').click();
  const button = pair.locator('[data-payload-kind="tool_input"]');
  // The native button is created by the real lazy pair read; intercept only the subsequent UI-only modal reads.
  await expect(button).toBeVisible();
  let body, index = 0;
  await page.route('**/payload/tool%3Ainput%3Aui-multiline-guard-*', route => route.fulfill({ json: body }));
  return async payload => {
    body = { kind: 'tool_input', status: 'available', ...payload };
    const id = 'tool:input:ui-multiline-guard-' + index++;
    await button.evaluate((node, id) => node.setAttribute('data-payload-id', id), id);
    const response = page.waitForResponse(r => new URL(r.url()).pathname.endsWith('/payload/' + encodeURIComponent(id)));
    await button.click();
    expect((await response).ok()).toBe(true);
    return page.locator('dialog.payload-modal');
  };
}

test('多行Input UI-only literal command preservation and plain-text safety guards', async ({ page, feedbackImport: { detail } }) => {
  const read = await multilineGuardReader(page, detail);
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

test('多行Input UI-only ambiguity and incomplete bodies conservatively keep original payload', async ({ page, feedbackImport: { detail } }) => {
  const read = await multilineGuardReader(page, detail), literal = JSON.stringify('echo one\necho two');
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
