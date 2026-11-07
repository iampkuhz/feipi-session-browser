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
    const round = { ...source, roundIndex: tail ? 999 : 1, summary: tail ? 'Synthetic final round' : 'Synthetic first round' };
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
  await expect(page.locator('[data-trace-round-row][data-round="999"]')).toBeVisible();
  await expect(page.locator('[data-trace-round-row][data-round="1"]')).toBeVisible();
  await expect(page.locator('[data-content-pagination="rounds"]')).toContainText('2 / 2');
  await expect(page.locator('[data-content-pagination="rounds"] button')).toHaveCount(0);
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

test('payload index pages expose the tail payload without fetching body until opened', async ({ page }) => {
  let bodyReads = 0;
  await page.route('**/api/**/payloads*', async (route) => {
    const baseline = new URL(route.request().url());
    ['cursor', 'tool_cursor', 'limit'].forEach((key) => baseline.searchParams.delete(key));
    const response = await route.fetch({ url: baseline.toString() });
    const original = await response.json();
    const tail = new URL(route.request().url()).searchParams.has('cursor');
    await route.fulfill({ response, json: { ...original, payloadCount: 2, total: 2,
      nextCursor: tail ? null : 'synthetic-payload-tail',
      payloads: [{ payloadId: tail ? 'synthetic-tail' : 'synthetic-first', kind: 'llm_response', status: 'available', title: tail ? 'Synthetic tail payload' : 'Synthetic first payload' }],
    } });
  });
  await page.route('**/payload/synthetic-tail', async (route) => {
    bodyReads += 1;
    const baseline = new URL(route.request().url());
    ['cursor', 'tool_cursor', 'limit'].forEach((key) => baseline.searchParams.delete(key));
    const response = await route.fetch({ url: baseline.toString() });
    await route.fulfill({ response, status: 200, json: { payloadId: 'synthetic-tail', kind: 'llm_response', text: 'Synthetic final payload body', content: 'Synthetic final payload body' } });
  });
  await page.goto(SESSION);
  await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  await expect(page.locator('[data-content-pagination="payloads"]')).toContainText('1 / 2');
  await page.locator('[data-content-pagination="payloads"] button').click();
  await expect(page.locator('template[data-payload-source="synthetic-tail"]')).toHaveCount(1);
  expect(bodyReads).toBe(0);
  await page.locator('[data-content-payload-index] [data-payload-id="synthetic-tail"]').click();
  await expect(page.locator('[data-payload-body]')).toContainText('Synthetic final payload body');
  expect(bodyReads).toBe(1);
});

test('round members and tools each reach their final explicit page', async ({ page }) => {
  const seen = [];
  await page.route('**/attribution/1/1/request*', async (route) => {
    const id = new URL(route.request().url()).searchParams.get('call_id');
    await route.fulfill({ status: 200, json: { kind: 'llm.request_attribution', data: { callId: id || 'wrong-index-selected-first-call' } } });
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
  await page.locator('#round-1-detail [data-attribution-call-id="synthetic-final-call"][data-payload-kind="llm.request_attribution"]').click();
  await expect(page.locator('[data-payload-body]')).toContainText('synthetic-final-call');
});

test('paged child attribution keeps call identity and clears previous main bucket context', async ({ page }) => {
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
  await page.route('**/attribution/subagent/**', async (route) => {
    const id = new URL(route.request().url()).searchParams.get('call_id');
    attributionIds.push(id);
    await route.fulfill({ status: 200, json: { kind: 'llm.request_attribution', data: { callId: id || 'wrong-index-selected-first-call', scope: 'subagent' } } });
  });
  await page.goto(SESSION);
  await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  await page.locator('[data-trace-round-row][data-round="1"] [data-action="toggle-round"]').click();
  await page.locator('[data-content-pagination="round-members"] button').click();
  await page.locator('[data-trace-round-row][data-round="1"] [data-payload-kind="llm.request_attribution"]').click();
  await expect(page.locator('#sd-payload-modal, #payload-modal')).toHaveAttribute('data-attribution-state', 'success');
  await page.evaluate(() => {
    const modal = document.getElementById('sd-payload-modal') || document.getElementById('payload-modal');
    modal.setAttribute('data-bucket-detail-round', '999');
    modal.close();
  });
  await page.locator('#round-1-detail [data-sub-round-id] [data-payload-kind="llm.request_attribution"]').last().click();
  await expect(page.locator('[data-payload-body]')).toContainText('child-call-final');
  expect(attributionIds).toEqual(['child-call-final']);
  await expect(page.locator('#sd-payload-modal, #payload-modal')).not.toHaveAttribute('data-bucket-detail-round', /.+/);
});
