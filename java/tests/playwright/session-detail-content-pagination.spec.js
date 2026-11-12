const { test, expect } = require('@playwright/test');

const SESSION = '/sessions/claude_code/hifi-viz-session-001';

// Synthetic pages keep the real fixture's generation header, except the explicit stale-page case.
async function pagedRounds(page, stale = false) {
  const requests = [];
  await page.route('**/rounds*', async (route) => {
    const url = new URL(route.request().url());
    if (!url.pathname.includes('/api/')) return route.continue();
    requests.push(url.searchParams.get('cursor'));
    const baseline = new URL(route.request().url());
    ['cursor', 'tool_cursor', 'limit'].forEach((key) => baseline.searchParams.delete(key));
    const response = await route.fetch({ url: baseline.toString() });
    const original = await response.json();
    const source = original.rounds[0];
    const tail = url.searchParams.has('cursor');
    const round = { ...source, roundIndex: tail ? 999 : 1, parity: { ...source.parity,
      summary: tail ? 'Synthetic final round' : 'Synthetic first round', summaryRole: 'assistant' } };
    await route.fulfill({ response,
      headers: { ...response.headers(), ...(tail && stale ? { 'x-session-index-generation': 'synthetic-other-generation' } : {}) },
      json: { ...original, rounds: [round], roundCount: 2, total: 2, nextCursor: tail ? null : 'synthetic-round-tail' },
    });
  });
  return requests;
}

test('round pages are explicitly loaded and retain the first page and exact total', async ({ page }) => {
  const requests = await pagedRounds(page);
  await page.goto(SESSION);
  await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  await page.locator('[data-evidence-analysis] > summary').click();
  await expect(page.locator('[data-trace-round-row]')).toHaveCount(1);
  expect(requests).toEqual([null]);
  await expect(page.locator('[data-content-pagination="rounds"]')).toContainText('1 / 2');
  await page.locator('[data-content-pagination="rounds"] button').click();
  const final = page.locator('[data-trace-round-row][data-round="999"]');
  await expect(final.locator('.summary-title')).toHaveText('Synthetic final round');
  await expect(final.locator('.summary-role')).toHaveText('助手');
  await expect(page.locator('[data-trace-round-row][data-round="1"]')).toBeVisible();
  await expect(page.locator('[data-content-pagination="rounds"]')).toContainText('2 / 2');
  await expect(page.locator('[data-content-pagination="rounds"] button')).toHaveCount(0);
});

test('a page from another generation never appends to the existing rounds', async ({ page }) => {
  await pagedRounds(page, true);
  await page.goto(SESSION);
  await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  await page.locator('[data-evidence-analysis] > summary').click();
  await page.locator('[data-content-pagination="rounds"] button').click();
  await expect(page.locator('[data-content-pagination="rounds"]')).toContainText(/refresh/i);
  await expect(page.locator('[data-trace-round-row][data-round="999"]')).toHaveCount(0);
  await expect(page.locator('[data-trace-round-row][data-round="1"]')).toHaveCount(1);
});

test('small unpaged sessions have no ineffective load-more control', async ({ page }) => {
  await page.goto(SESSION);
  await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  await page.locator('[data-evidence-analysis] > summary').click();
  await expect(page.locator('[data-content-pagination] button')).toHaveCount(0);
});

test('long payload index stays internal and tail Request and Response open from their round', async ({ page }) => {
  let bodyReads = 0;
  let indexReads = 0;
  let memberReads = 0;
  await page.route('**/api/**/payloads*', async route => {
    indexReads++;
    const response = await route.fetch();
    await route.fulfill({ response, json: { payloadCount: 202, total: 202, nextCursor: 'synthetic-index-tail',
      payloads: Array.from({ length: 100 }, (_, i) => ({ payloadId: 'main:req:synthetic-' + i,
        kind: 'llm_request', status: 'available', title: 'Synthetic index item' })),
    } });
  });
  await page.route('**/api/**/rounds*', async route => {
    const response = await route.fetch();
    const original = await response.json();
    await route.fulfill({ response, json: { ...original, rounds: [{ ...original.rounds[0], roundIndex: 1,
      callCount: 101, parity: { summary: 'Round 1' } }], roundCount: 1 } });
  });
  await page.route('**/api/**/round/1*', async route => {
    memberReads++;
    const url = new URL(route.request().url());
    const tail = url.searchParams.has('cursor');
    url.search = '';
    const response = await route.fetch({ url: url.toString() });
    const original = await response.json();
    const calls = Array.from({ length: tail ? 1 : 100 }, (_, i) => ({ callId: 'synthetic-' + (tail ? 100 : i),
      callKey: 'C' + (tail ? 101 : i + 1), scope: 'main', usage: {} }));
    await route.fulfill({ response, json: { ...original, total: 101, membersPaged: true,
      nextCursor: tail ? null : 'synthetic-member-tail', round: { ...original.round, calls, tools: [], callAssistantTexts: {} } } });
  });
  await page.route(/\/payload\/main%3A(?:req|resp)%3Asynthetic-100(?:\?|$)/, async route => {
    bodyReads++;
    const response = await route.fetch();
    const side = decodeURIComponent(new URL(route.request().url()).pathname).includes(':req:') ? 'request' : 'response';
    await route.fulfill({ response, status: 200, json: { kind: 'llm_' + side, text: 'Synthetic tail ' + side } });
  });
  await page.goto(SESSION);
  await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  await page.locator('[data-evidence-analysis] > summary').click();
  await expect(page.locator('[data-content-payload-index], [data-content-pagination="payloads"]')).toHaveCount(0);
  await expect(page.locator('body')).not.toContainText('Payload index:');
  await expect(page.locator('[data-timeline-item]')).toHaveCount(0);
  expect({ bodyReads, indexReads, memberReads }).toEqual({ bodyReads: 0, indexReads: 0, memberReads: 0 });
  const row = page.locator('[data-trace-round-row]').first();
  await expect(row.locator('.summary-title')).toHaveText('摘要未记录');
  await page.setViewportSize({ width: 390, height: 850 });
  expect(await row.evaluate(e => {
    const panel = e.closest('[data-trace-panel]');
    const header = panel.querySelector('.sd-trace-head');
    const actions = header.querySelector('.sd-trace-actions');
    const box = header.getBoundingClientRect();
    const controls = actions.getBoundingClientRect();
    return panel.scrollWidth <= panel.clientWidth + 1 && controls.bottom <= box.bottom
      && controls.right <= box.right && box.bottom <= e.getBoundingClientRect().top;
  })).toBe(true);
  await row.locator('[data-action="toggle-round"]').click();
  await page.locator('[data-content-pagination="round-members"] button').click();
  await expect(page.locator('[data-content-pagination="round-members"]')).toContainText('101 / 101');
  expect(bodyReads).toBe(0);
  for (const [id, side] of [['req', 'request'], ['resp', 'response']]) {
    await page.locator(`#round-1-detail [data-payload-id="main:${id}:synthetic-100"]`).click();
    const modal = page.locator('dialog.payload-modal');
    await expect(modal).toContainText('Synthetic tail ' + side);
    await page.keyboard.press('Escape');
  }
  expect({ bodyReads, indexReads, memberReads }).toEqual({ bodyReads: 2, indexReads: 0, memberReads: 2 });
});

test('round members and tools each reach their final explicit page', async ({ page }) => {
  const seen = [];
  await page.route('**/attribution/1/1/request*', async (route) => {
    const id = new URL(route.request().url()).searchParams.get('call_id');
    const response = await route.fetch({ url: route.request().url().split('?')[0] });
    await route.fulfill({ response, status: 200, json: { kind: 'llm.request_attribution', data: { callId: id || 'wrong-index-selected-first-call' } } });
  });
  await page.route('**/api/**/round/1*', async (route) => {
    const baseline = new URL(route.request().url());
    ['cursor', 'tool_cursor', 'limit'].forEach((key) => baseline.searchParams.delete(key));
    const response = await route.fetch({ url: baseline.toString() });
    const original = await response.json();
    const url = new URL(route.request().url());
    const memberTail = url.searchParams.has('cursor');
    const toolTail = url.searchParams.has('tool_cursor');
    seen.push({ member: url.searchParams.get('cursor'), tool: url.searchParams.get('tool_cursor') });
    const callId = memberTail ? 'synthetic-final-call' : 'synthetic-first-call';
    const call = { callId, callKey: callId, scope: 'main', responseToolCallIds: ['synthetic-first-tool', 'synthetic-final-tool'], usage: {} };
    const tool = { toolCallId: toolTail ? 'synthetic-final-tool' : 'synthetic-first-tool', declaredByCallId: callId, name: 'Synthetic', inputPreview: toolTail ? 'Synthetic final tool input' : 'Synthetic first tool input' };
    await route.fulfill({ response, json: { ...original,
      total: 2, membersPaged: true, nextCursor: memberTail ? null : 'synthetic-member-tail',
      toolTotal: 2, toolsComplete: toolTail, nextToolCursor: toolTail ? null : 'synthetic-tool-tail',
      assistantTextsArePreviews: true, assistantTextPreviewsAvailable: false,
      round: { ...original.round, calls: [call], tools: [tool], callAssistantTexts: {} },
    } });
  });
  await page.goto(SESSION);
  await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  await page.locator('[data-evidence-analysis] > summary').click();
  await page.locator('[data-trace-round-row][data-round="1"] [data-action="toggle-round"]').click();
  await expect(page.locator('#round-1-detail')).toContainText('synthetic-first-call');
  await page.locator('[data-content-pagination="round-tools"] button').click();
  await expect(page.locator('#round-1-detail [data-tool-call-id="synthetic-final-tool"]')).toBeVisible();
  await page.locator('[data-content-pagination="round-members"] button').click();
  await expect(page.locator('#round-1-detail')).toContainText('synthetic-final-call');
  await expect(page.locator('[data-content-pagination="round-members"]')).toContainText('2 / 2');
  expect(seen).toContainEqual({ member: null, tool: 'synthetic-tool-tail' });
  expect(seen).toContainEqual({ member: 'synthetic-member-tail', tool: null });
  await page.locator('[data-content-pagination="round-tools"] button').click();
  await expect.poll(() => seen).toContainEqual({ member: 'synthetic-member-tail', tool: 'synthetic-tool-tail' });
  await stubMemberRequest(page, 'main:req:synthetic-final-call');
  await page.locator('#round-1-detail [data-payload-id="main:req:synthetic-final-call"]').click();
  await expect(page.locator('[data-payload-attribution="request"]')).toHaveAttribute('data-attribution-call', 'synthetic-final-call');
});

test('paged child Request uses stable call identity and retains child scope', async ({ page }) => {
  const attributionIds = [];
  await page.route('**/api/**/round/1*', async (route) => {
    const baseline = new URL(route.request().url());
    const tail = baseline.searchParams.has('cursor');
    baseline.search = '';
    const response = await route.fetch({ url: baseline.toString() });
    const original = await response.json();
    await route.fulfill({ response, json: { ...original, membersPaged: true, total: 2,
      nextCursor: tail ? null : 'child-tail',
      round: { ...original.round, tools: [], calls: [{ callId: tail ? 'child-call-final' : 'child-call-first', subagentId: 'synthetic-child', scope: 'subagent', usage: {} }] },
    } });
  });
  await page.route('**/attribution/1/1/request*', async (route) => {
    const id = new URL(route.request().url()).searchParams.get('call_id');
    attributionIds.push(id);
    const response = await route.fetch({ url: route.request().url().split('?')[0] });
    await route.fulfill({ response, status: 200, json: { kind: 'llm.request_attribution', data: { callId: id, scope: 'subagent' } } });
  });
  await stubMemberRequest(page, 'sa:req:child-call-final');
  await page.goto(SESSION);
  await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  await page.locator('[data-evidence-analysis] > summary').click();
  await page.locator('[data-trace-round-row][data-round="1"] [data-action="toggle-round"]').click();
  await page.locator('[data-content-pagination="round-members"] button').click();
  await page.locator('#round-1-detail [data-payload-id="sa:req:child-call-final"]').click();
  const attr = page.locator('[data-payload-attribution="request"]');
  await expect(attr).toHaveAttribute('data-attribution-call', 'child-call-final');
  await expect(attr).toHaveAttribute('data-attribution-scope', 'subagent');
  expect(attributionIds).toEqual(['child-call-final']);
});

async function stubMemberRequest(page, id) {
  await page.route(`**/payload/${encodeURIComponent(id)}`, async (route) => {
    const url = route.request().url().split('/payload/')[0] + '/payload/' + encodeURIComponent('round:req:1');
    const response = await route.fetch({ url });
    await route.fulfill({ response, status: 200, json: { kind: id.startsWith('sa:') ? 'subagent_request' : 'llm_request', text: 'Synthetic member request' } });
  });
}
