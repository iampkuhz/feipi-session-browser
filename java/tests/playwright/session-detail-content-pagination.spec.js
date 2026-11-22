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
    const round = { ...source, roundIndex: tail ? 999 : 1, status: tail ? 'failed' : 'ok', parity: { ...source.parity,
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

test('failure filter applies to appended rounds and clearing it restores the first page', async ({ page }) => {
  const requests = [];
  await page.route('**/rounds*', async route => {
    const url = new URL(route.request().url());
    const status = url.searchParams.get('trace_status');
    const cursor = url.searchParams.get('cursor');
    requests.push([status, cursor]);
    const response = await route.fetch({ url: url.origin + url.pathname });
    const original = await response.json();
    const roundIndex = status === 'failed' ? (cursor ? 999 : 998) : 1;
    await route.fulfill({ response, json: { ...original, total: 2, roundCount: 2,
      nextCursor: cursor ? null : status === 'failed' ? 'synthetic-failure-tail' : 'synthetic-all-tail',
      rounds: [{ ...original.rounds[0], roundIndex, status: status === 'failed' ? 'failed' : 'ok' }],
    } });
  });
  await page.goto(SESSION);
  await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  const first = page.locator('[data-trace-round-row][data-round="1"]');
  const firstFailure = page.locator('[data-trace-round-row][data-round="998"]');
  const finalFailure = page.locator('[data-trace-round-row][data-round="999"]');
  await expect(first).toBeVisible();
  await page.locator('[data-action="status-failed"]').click();
  await expect(firstFailure).toBeVisible();
  await expect(first).toHaveCount(0);
  await page.locator('[data-content-pagination="rounds"] button').click();
  await expect(finalFailure).toBeVisible();
  await expect(firstFailure).toBeVisible();
  await page.locator('[data-action="status-all"]').click();
  await expect(first).toBeVisible();
  await expect(finalFailure).toHaveCount(0);
  expect(requests).toEqual([[null, null], ['failed', null], ['failed', 'synthetic-failure-tail'], ['all', null]]);
});

test('a page from another generation never appends to the existing rounds', async ({ page }) => {
  await pagedRounds(page, true);
  await page.goto(SESSION);
  await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  await page.locator('[data-content-pagination="rounds"] button').click();
  await expect(page.locator('[data-content-pagination="rounds"]')).toContainText(/refresh/i);
  await expect(page.locator('[data-trace-round-row][data-round="999"]')).toHaveCount(0);
  await expect(page.locator('[data-trace-round-row][data-round="1"]')).toHaveCount(1);
});

test('small unpaged sessions have no ineffective load-more control', async ({ page }) => {
  await page.goto(SESSION);
  await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  await expect(page.locator('[data-content-pagination] button')).toHaveCount(0);
});

test('paginated round members are the sole route to identity-bound original bodies', async ({ page }) => {
  let bodyReads = 0;
  const indexReads = [];
  let memberReads = 0;
  page.on('request', req => {
    if (new URL(req.url()).pathname.endsWith('/payloads')) indexReads.push(req.url());
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
  await expect(page.locator('[data-content-payload-index], [data-content-pagination="payloads"]')).toHaveCount(0);
  await expect(page.locator('body')).not.toContainText('Payload index:');
  await expect(page.locator('[data-timeline-item]')).toHaveCount(0);
  expect({ bodyReads, indexReads, memberReads }).toEqual({ bodyReads: 0, indexReads: [], memberReads: 0 });
  const row = page.locator('[data-trace-round-row]').first();
  await expect(row.locator('.summary-title')).toHaveText('摘要未记录');
  await page.setViewportSize({ width: 1024, height: 850 });
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
  expect({ bodyReads, indexReads, memberReads }).toEqual({ bodyReads: 2, indexReads: [], memberReads: 2 });
  await expect(page.locator('[data-round-sources], [data-payload-index]')).toHaveCount(0);
});

test('round and tool pages retain each tool under its main or child call', async ({ page }) => {
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
    const firstCall = { callId: 'synthetic-first-call', scope: 'main', usage: {},
      responseToolCallIds: ['synthetic-first-tool', 'synthetic-final-tool'] };
    const finalCall = { callId: 'synthetic-final-call', scope: 'main', usage: {} };
    const childCall = { callId: 'synthetic-child-call', subagentId: 'synthetic-child', scope: 'subagent', usage: {},
      responseToolCallIds: ['synthetic-first-child-tool', 'synthetic-final-child-tool'] };
    const owner = memberTail ? childCall : firstCall;
    const tool = { toolCallId: owner.responseToolCallIds[toolTail ? 1 : 0], declaredByCallId: owner.callId,
      scope: owner.scope, name: 'Synthetic', inputPreview: 'Synthetic tool input' };
    await route.fulfill({ response, json: { ...original,
      total: 3, membersPaged: true, nextCursor: memberTail ? null : 'synthetic-member-tail',
      toolTotal: 2, toolsComplete: toolTail, nextToolCursor: toolTail ? null : 'synthetic-tool-tail',
      assistantTextsArePreviews: true, assistantTextPreviewsAvailable: false,
      round: { ...original.round, calls: memberTail ? [finalCall, childCall] : [firstCall], tools: [tool], callAssistantTexts: {} },
    } });
  });
  await page.goto(SESSION);
  await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  await page.locator('[data-trace-round-row][data-round="1"] [data-action="toggle-round"]').click();
  await expect(page.locator('#round-1-detail [title*=synthetic-first-call]').first()).toBeVisible();
  await page.locator('[data-content-pagination="round-tools"] button').click();
  const detail = page.locator('#round-1-detail');
  const main = detail.locator('[data-call-actions="synthetic-first-call"]');
  await expect(main.locator('[data-tool-call-id="synthetic-final-tool"]')).toBeVisible();
  await expect(main.locator('[data-tool-call-id]')).toHaveCount(2);
  await page.locator('[data-content-pagination="round-members"] button').click();
  await expect(page.locator('#round-1-detail [title*=synthetic-final-call]').first()).toBeVisible();
  await expect(page.locator('[data-content-pagination="round-members"]')).toContainText('3 / 3');
  expect(seen).toContainEqual({ member: null, tool: 'synthetic-tool-tail' });
  expect(seen).toContainEqual({ member: 'synthetic-member-tail', tool: null });
  await page.locator('[data-content-pagination="round-tools"] button').click();
  await expect.poll(() => seen).toContainEqual({ member: 'synthetic-member-tail', tool: 'synthetic-tool-tail' });
  const child = detail.locator('[data-subagent-block][data-subagent-id="synthetic-child"]');
  await child.locator('[data-action="toggle-sub-round"]').click();
  const childActions = child.locator('[data-call-actions="synthetic-child-call"]');
  await expect(childActions.locator('[data-tool-call-id="synthetic-final-child-tool"]')).toBeVisible();
  await expect(childActions.locator('[data-tool-call-id]')).toHaveCount(2);
  await expect(main.locator('[data-tool-call-id]')).toHaveCount(2);
  await expect(detail.locator('[data-tool-call-id]')).toHaveCount(4);
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
