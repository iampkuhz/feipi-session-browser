const { test, expect } = require('@playwright/test');
const { readFileSync } = require('node:fs');
const path = require('node:path');

test('同一条合成回复的两次工具调用可分别查看结果', async ({ page, request, baseURL }, testInfo) => {
  await page.setViewportSize({ width: 1440, height: 1100 });
  const filename = 'mixed-tool-calls.jsonl';
  const source = readFileSync(path.resolve(__dirname, '../fixtures', filename));
  const created = await request.post('/api/imports', {
    headers: { Origin: baseURL },
    multipart: { source: 'claude_code', file: { name: filename, mimeType: 'application/x-ndjson', buffer: source } },
  });
  expect(created.status()).toBe(201);
  const { import_id, detail_url } = await created.json();
  try {
    const api = '/api/imports/' + import_id;
    const { round } = await (await request.get(api + '/round/2')).json();
    const ids = ['tool_read_001', 'tool_grep_001'];
    expect(round.calls).toHaveLength(1);
    expect(round.calls[0].responseToolCallIds).toEqual(ids);
    expect(round.tools.map(tool => tool.declaredByCallId)).toEqual([round.calls[0].callId, round.calls[0].callId]);

    await page.goto(detail_url);
    const row = page.locator('[data-trace-round-row][data-round="2"]');
    await expect(row.locator('[data-action="toggle-round"]')).toHaveAttribute('aria-expanded', 'false');
    await row.getByRole('button', { name: 'Response', exact: true }).click();
    const modal = page.locator('dialog.payload-modal');
    for (const id of ids) {
      await expect(modal.locator(`[data-payload-id="tool:result:${id}"]`)).toBeVisible();
    }
    await modal.getByRole('button', { name: 'Close' }).click();
    await row.locator('[data-action="toggle-round"]').click();
    const detail = page.locator('#round-2-detail');
    await expect(detail).toBeVisible();
    const group = detail.locator('[data-call-tools="C2"]');
    await expect(group.locator('[data-tool-call-id]')).toHaveCount(2);
    const response = group.getByRole('button', { name: 'Response', exact: true });
    await expect(response).toHaveCount(0);
    await expect(page.locator('[data-trace-round-row][data-round="2"]').getByRole('button', { name: 'Response', exact: true })).toBeVisible();
    await page.locator('[data-trace-list]').screenshot({ path: testInfo.outputPath('multi-tool-round.png') });
    for (const [index, expected] of ['// test file content', '3 matches found'].entries()) {
      await detail.locator(`[data-tool-call-id="${ids[index]}"]`).getByRole('button', { name: 'Result', exact: true }).click();
      await expect(modal.locator('.sd-reading-preview')).toHaveText(expected);
      await modal.getByRole('button', { name: /^返回 .+ · C2 · Response$/ }).click();
      await expect(modal.locator('[data-payload-attribution="response"]')).toHaveAttribute('data-attribution-call', round.calls[0].callId);
      await modal.getByRole('button', { name: 'Close' }).click();
      const pair = detail.locator('[data-tool-payload-pair][data-tool-id="' + ids[index] + '"]');
      await pair.locator('summary').click();
      await expect(pair.locator('pre').last()).toHaveText(expected);
    }
    const toolGroup = group.locator('[data-timeline-item="tool-call"]').first().locator('.sd-tool-group--flat');
    const commandRow = toolGroup.locator('.sd-tool-row');
    const inlineSource = toolGroup.locator('[data-tool-payload-pair]');
    await expect(commandRow).toHaveCSS('border-bottom-width', '0px');
    await expect(inlineSource).toHaveCSS('border-bottom-width', '0px');
    await expect(toolGroup).toHaveCSS('border-bottom-width', '1px');

    await page.setViewportSize({ width: 1024, height: 900 });
    await expect(inlineSource.locator('summary')).toBeVisible();
    const sourceGrid = inlineSource.locator('.sd-tool-payload-grid');
    const payloadColumns = await sourceGrid.evaluate(grid => [...grid.children].map(part => part.getBoundingClientRect().left));
    expect(payloadColumns[0]).toBeLessThan(payloadColumns[1]);
    await expect(inlineSource.locator('pre').last()).toHaveText('// test file content');
    expect(await sourceGrid.evaluate(grid => grid.scrollWidth <= grid.clientWidth + 1)).toBe(true);
    await inlineSource.locator('summary').press('Enter');
    await expect(inlineSource).not.toHaveAttribute('open');
    await inlineSource.locator('summary').press('Space');
    await expect(inlineSource).toHaveAttribute('open');
    await expect(inlineSource.locator('pre').last()).toHaveText('// test file content');
  } finally {
    expect((await request.delete('/api/imports/' + import_id, { headers: { Origin: baseURL } })).status()).toBe(204);
  }
});
