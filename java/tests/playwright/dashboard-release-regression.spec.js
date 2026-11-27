const { test, expect } = require('@playwright/test');

const model = 'claude-sonnet-4-20250514'; // Shipped synthetic fixture.
const drilldowns = [
  { table: 'All Agents', label: 'Claude Code', dashboard: '/dashboard?grain=week' },
  { table: 'Agent / Model Efficiency', label: model, dashboard: '/dashboard' },
  { table: 'Model Mix', label: model, dashboard: '/dashboard?agent=claude-code' },
  { table: 'Model Efficiency Detail', label: model, dashboard: '/dashboard?agent=claude-code' },
];

function dashboardTable(page, title) {
  if (title === 'Model Mix') {
    return trendCard(page, 'model-mix').getByRole('table');
  }
  return page.getByRole('region', { name: title, exact: true }).getByRole('table');
}

async function tabTo(page, control) {
  // Do not call focus(): the drilldown must be in the normal keyboard tab order.
  await expect(control).toBeVisible();
  const limit = await page.locator('a, button, input, select, textarea, summary, [tabindex]').count();
  for (let step = 0; step <= limit; step++) {
    await page.keyboard.press('Tab');
    if (await control.evaluate(element => document.activeElement === element)) return;
  }
  await expect(control).toBeFocused();
}

for (const { table, label, dashboard } of drilldowns) {
  for (const input of ['mouse', 'keyboard']) {
    test(`${table} drills down with ${input}`, async ({ page }) => {
      await page.goto(dashboard);
      const owner = dashboardTable(page, table);
      const row = owner.getByRole('row').filter({ has: page.getByText(label, { exact: true }) });
      await expect(row).toBeVisible();
      if (input === 'keyboard') {
        await tabTo(page, row.getByRole('link', { name: label, exact: true }));
        await page.keyboard.press('Enter');
      } else if (table === 'Agent / Model Efficiency') {
        await row.getByText('计量详情', { exact: true }).click();
        await expect(row.getByText(/^Samples:/)).toBeVisible();
        await expect(page).toHaveURL(url => url.pathname === '/dashboard');
        // A plain data cell retains the row-click shortcut; it is not the link.
        await row.getByRole('cell', { name: /^\d/ }).first().click();
      } else {
        await row.getByText(label, { exact: true }).click();
      }
      if (table === 'All Agents') {
        await expect(page).toHaveURL(url => url.pathname === '/dashboard'
          && url.searchParams.get('agent') === 'claude-code' && url.searchParams.get('grain') === 'week');
      } else {
        await expect(page).toHaveURL(url => url.pathname === '/sessions');
        await expect(page.locator('select[name="agent"]')).toHaveValue('claude_code');
        await expect(page.locator('select[name="model"]')).toHaveValue(model);
        const { searchParams } = new URL(page.url());
        expect(searchParams.get('agent')).toBe('claude_code');
        expect(searchParams.get('model')).toBe(model);
      }
    });
  }
}

const asOf = '2021-02-02';
const paths = ['sessions', 'prompts', 'tokens', 'cache-health'];
const provenance = Object.fromEntries(['freshInput', 'cacheRead', 'cacheWrite', 'output']
  .map(part => [part, 'provider_reported']));
const trendPayload = {
  sessions: (date, n) => ({ points: [{ date, totalCount: n, claudeCount: n }], rangeTotal: n }),
  prompts: (date, n) => ({ points: [{ date, totalPrompts: n, claudePrompts: n,
    measuredUserMessages: n, userMessageSampleCount: 1,
    claudeMeasuredUserMessages: n, claudeUserMessageSampleCount: 1, codexPrompts: 0,
    codexMeasuredUserMessages: 0, codexUserMessageSampleCount: 0 }], rangeTotalPrompts: n }),
  tokens: (date, n) => {
    const tokens = { total: n, fresh: n, cacheRead: 0, cacheWrite: 0, output: 0, provenance };
    return { points: [{ date, tokens, claudeTokens: n }], rangeTotals: tokens };
  },
  'cache-health': (date, n) => {
    const usage = { fresh: 100 - n, cacheRead: n, cacheWrite: 0, provenance, ratio: { value: n / 100 } };
    return { points: [{ date, average: usage, claudeCode: usage }] };
  },
};

function trendCard(page, name) {
  return page.locator(`[data-chart-card="${name}"]`);
}

function expectNoAxes(card) {
  return expect(card.locator('.x-axis, .y-axis')).toHaveCount(0);
}

function pauseResponse() {
  let release;
  const pending = new Promise(resolve => { release = resolve; });
  return { pending, release };
}

// Preserve the packaged server's index generation unless a test explicitly changes it.
async function mockTrends(page, handler) {
  await page.clock.setFixedTime(new Date(`${asOf}T12:00:00Z`));
  await page.route('**/api/dashboard/trends/*?*', async route => {
    const name = new URL(route.request().url()).pathname.split('/').pop();
    const response = await route.fetch();
    await route.fulfill({ response, ...await handler(name, response) });
  });
}

async function expectPromptTooltip(page, cohort) {
  const bar = trendCard(page, 'prompts').locator('.plot > .bar').last();
  await bar.hover();
  const tip = bar.locator('.dashboard-tooltip');
  await expect(tip).toBeVisible();
  const overall = tip.locator('.tooltip-row').filter({ has: page.getByText('Overall', { exact: true }) });
  const codex = tip.locator('.tooltip-row:not(.tooltip-row--line)')
    .filter({ has: page.getByText('Codex', { exact: true }) });
  await expect(overall.locator('.tooltip-value')).toHaveText('13.0');
  await expect(overall).toContainText(`samples 1 / ${cohort} cohort`);
  await expect(codex.locator('.tooltip-value')).toHaveText('N/A');
}

test('a failed session trend does not fabricate zero or block successful siblings and Retry restores it', async ({ page }) => {
  let sessionRequests = 0;
  const retry = pauseResponse();
  await mockTrends(page, async name => {
    if (name === 'sessions') {
      if (++sessionRequests === 1) return { status: 500, json: {} };
      await retry.pending;
    }
    const value = { sessions: 7, prompts: 13, tokens: 73, 'cache-health': 25 }[name];
    const json = trendPayload[name](asOf, value);
    if (name === 'sessions') Object.assign(json.points[0], { claudeCount: 5, codexCount: 2, qoderCount: 0 });
    return { json };
  });
  await page.goto('/dashboard?grain=day');

  const sessions = trendCard(page, 'sessions');
  const failure = page.getByRole('alert').filter({ hasText: /HTTP 500/ });
  await expect(failure).toBeVisible();
  for (const [name, latest] of [['prompts', 13], ['tokens', 73], ['cache-health', '25.0%']]) {
    const card = trendCard(page, name);
    await expect(card.locator('[data-stat^="latest-"]')).toContainText(String(latest));
    await expect(card.locator('.x-axis > span')).toHaveCount(30);
  }
  await expect(sessions.locator('[data-stat]').filter({ hasText: /loading|:\s*0$/i })).toHaveCount(0);
  await expectNoAxes(sessions);
  await expectPromptTooltip(page, 'N/A');
  await failure.getByRole('button', { name: 'Retry', exact: true }).click();
  const tokenPoint = trendCard(page, 'tokens').locator('[data-token-breakdown][tabindex="0"]').last();
  try {
    await expect(failure).toHaveCount(0);
    await expect(sessions.locator('[data-stat="latest-sessions"]')).toContainText(/loading/i);
    await expectNoAxes(sessions);
    await expectPromptTooltip(page, 'N/A');
    await tokenPoint.focus();
    await expect(tokenPoint).toBeFocused();
  } finally {
    retry.release();
  }
  await expect(sessions.locator('[data-stat="latest-sessions"]')).toHaveText('Latest: 7');
  await expect(tokenPoint).toBeFocused();
  await expect(sessions.locator('.x-axis > span')).toHaveCount(30);
  const bucketValues = sessions.locator('.plot > .bar .tooltip-row--total .tooltip-value');
  await expect(bucketValues.first()).toHaveText('0');
  await expect(bucketValues.last()).toHaveText('7');
  await expectPromptTooltip(page, 7);
  expect(sessionRequests).toBe(2);
});

test('Retry cannot combine a different index generation with the original Dashboard', async ({ page }) => {
  let requests = 0;
  await mockTrends(page, async (name, response) => {
    const json = trendPayload[name](asOf, 13);
    if (name !== 'sessions') return { json };
    if (++requests === 1) return { status: 500, json: {} };
    if (requests === 2) return {
      headers: { ...response.headers(), 'x-session-index-generation': 'different-synthetic-generation' },
      json: trendPayload.sessions(asOf, 777),
    };
    return { json };
  });
  await page.goto('/dashboard?grain=day');
  await expect(trendCard(page, 'prompts').locator('[data-stat="latest-prompts"]')).toHaveText('Latest: 13');
  await page.getByRole('button', { name: 'Retry', exact: true }).click();
  const reload = page.getByRole('button', { name: 'Reload entire page', exact: true });
  await expect(reload).toBeVisible();
  await expect(page.locator('main')).toBeHidden();
  const latest = trendCard(page, 'sessions').locator('[data-stat="latest-sessions"]');
  await expect(latest).not.toHaveText('Latest: 777');
  await reload.click();
  await expect(latest).toHaveText('Latest: 13');
  expect(requests).toBe(3);
});

test('a card Retry and a summary Retry both recover when clicked before either finishes', async ({ page }) => {
  let sessionRequests = 0;
  let summaryRequests = 0;
  const trendRetry = pauseResponse();
  await mockTrends(page, async name => {
    if (name !== 'sessions') return { json: trendPayload[name](asOf, 13) };
    if (++sessionRequests === 1) return { status: 500, json: {} };
    await trendRetry.pending;
    return { json: trendPayload.sessions(asOf, 7) };
  });
  await page.route('**/api/dashboard/summary?*', async route => {
    const response = await route.fetch();
    if (++summaryRequests === 1) return route.fulfill({ response, status: 500, json: {} });
    const json = { ...await response.json(), sessionCount: 61 };
    await route.fulfill({ response, json });
  });
  await page.goto('/dashboard?grain=day');

  const sessions = trendCard(page, 'sessions');
  const cardRetry = sessions.getByRole('button', { name: 'Retry', exact: true });
  const summaryFailure = page.getByRole('alert').filter({ hasText: /dashboard\/summary.*HTTP 500/ });
  await expect(cardRetry).toBeVisible();
  await expect(summaryFailure).toBeVisible();
  try {
    await Promise.all([
      page.waitForRequest(url => new URL(url.url()).pathname === '/api/dashboard/trends/sessions'),
      cardRetry.click(),
    ]);
    await summaryFailure.getByRole('button', { name: 'Retry', exact: true }).click();
  } finally {
    trendRetry.release();
  }

  const summaryValue = page.getByRole('article', { name: 'Sessions', exact: true })
    .locator('.metric-card__value');
  await expect(summaryValue).toHaveText('61');
  await expect(sessions.locator('[data-stat="latest-sessions"]')).toHaveText('Latest: 7');
  await expect(summaryFailure).toHaveCount(0);
  await expect(cardRetry).toHaveCount(0);
  expect({ sessionRequests, summaryRequests }).toEqual({ sessionRequests: 2, summaryRequests: 2 });
});

test('a successful HTTP response without points is a resource error, but a retried empty array is empty', async ({ page }) => {
  const requests = Object.fromEntries(paths.map(name => [name, 0]));
  await mockTrends(page, async name => {
    requests[name]++;
    if (name !== 'tokens') return { json: trendPayload[name](asOf, 13) };
    return { json: requests.tokens === 1 ? {} : { points: [] } };
  });
  await page.goto('/dashboard?grain=day');

  const tokens = trendCard(page, 'tokens');
  const failure = tokens.getByRole('alert');
  await expect(failure).toBeVisible();
  await expectNoAxes(tokens);
  await failure.getByRole('button', { name: 'Retry', exact: true }).click();
  await expect(tokens.getByRole('status')).toContainText(/无数据|no data/i);
  await expect(failure).toHaveCount(0);
  await expectNoAxes(tokens);
  expect(requests).toEqual({ sessions: 1, prompts: 1, tokens: 2, 'cache-health': 1 });
});

test('a measured positive cache ratio below display precision is not labelled as zero', async ({ page }) => {
  const usage = { fresh: 999999, cacheRead: 1, cacheWrite: 0, provenance, ratio: { value: 1 / 1000000 } };
  await mockTrends(page, async name => ({
    json: name === 'cache-health' ? { points: [{ date: asOf, average: usage }] } : trendPayload[name](asOf, 13),
  }));
  await page.goto('/dashboard?grain=day');

  const cache = trendCard(page, 'cache-health');
  await expect(cache.locator('[data-stat="latest-ratio"]')).toHaveText(/:\s*<0\.1%$/);
  await expect(cache.locator('[data-stat="lowest-ratio"]')).toHaveText(/:\s*<0\.1%$/);
  const point = cache.locator('.chart-hover-target').last();
  await point.hover();
  const tip = point.locator('.dashboard-tooltip');
  await expect(tip).toBeVisible();
  const average = tip.locator('.tooltip-row').filter({ has: page.getByText('Average', { exact: true }) });
  await expect(average.locator('.tooltip-value')).toHaveText('<0.1%');
});

test('pending, an empty window, and observed zero render as three different states', async ({ page }) => {
  const initial = pauseResponse();
  let observed = false;
  await mockTrends(page, async name => {
    if (observed) return { json: trendPayload[name](asOf, 0) };
    await initial.pending;
    const otherDate = { sessions: '2020-01-01', prompts: 'not-a-date', 'cache-health': '2021-02-03' }[name];
    return { json: otherDate ? trendPayload[name](otherDate, 9) : { points: [] } };
  });
  await page.goto('/dashboard?grain=day');
  try {
    for (const name of paths) {
      const card = trendCard(page, name);
      await expect(card.locator('[data-stat^="latest-"]')).toContainText(/loading/i);
      await expect(card.locator('[data-dashboard-chart]')).not.toContainText(/无数据|no data/i);
      await expectNoAxes(card);
    }
  } finally {
    initial.release();
  }
  for (const name of paths) {
    const card = trendCard(page, name);
    await expect(card.locator('[data-dashboard-chart]')).toContainText(/无数据|no data/i);
    await expect(card.locator('[data-stat^="latest-"]')).not.toContainText(/loading|:\s*0(?:\.0+%)?$/i);
    await expectNoAxes(card);
  }

  observed = true;
  await page.reload();
  for (const name of paths) {
    const card = trendCard(page, name);
    await expect(card.locator('[data-stat^="latest-"]')).toHaveText(/:\s*0(?:\.0+%)?$/);
    await expect(card.locator('.x-axis > span')).toHaveCount(30);
  }
});
