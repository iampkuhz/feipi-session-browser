const { test, expect } = require('@playwright/test');
const path = require('path');
const fs = require('fs');

// Keep the live SSR snapshot identity while replacing only synthetic renderer data.
async function fulfillIndexedJson(route, json) {
  const response = await route.fetch();
  return route.fulfill({ response, status: 200, json });
}

// All values below are synthetic. API interception tests renderer semantics, not API parity.
const helperPath = path.join(__dirname, '../../web/src/main/resources/static/js/token-provenance.js');
test.beforeEach(async ({ page }) => {
  if (process.env.FEIPI_UI_SOURCE_RESOURCES !== '1') return;
  const resourceRoot = path.join(__dirname, '../../web/src/main/resources');
  await page.route('**/static/js/**', async (route) => {
    const relative = new URL(route.request().url()).pathname.replace(/^\/static\//, 'static/');
    await route.fulfill({ contentType: 'application/javascript', body: fs.readFileSync(path.join(resourceRoot, relative), 'utf8') });
  });
  await page.route(/\/static\/css\/sessions-list\.css(?:\?|$)/, async (route) => {
    await route.fulfill({ contentType: 'text/css', body: fs.readFileSync(path.join(resourceRoot, 'static/css/sessions-list.css'), 'utf8') });
  });
  await page.addInitScript({ path: path.join(resourceRoot, 'static/js/session-timing.js') });
});
const detailPath = '/sessions/claude_code/hifi-viz-session-001';
const projectKey = 'test-hifi-project';
const provenance = {
  freshInput: 'estimated', cacheRead: 'unavailable', cacheWrite: 'unavailable', output: 'estimated',
  estimationMethod: 'visible_context_v1,cache_transcript_v1', estimatedSessionCount: 1,
  unavailableSessionCount: 1, unknownSessionCount: 0,
};
const tokens = { fresh: 9000000, cacheRead: 0, cacheWrite: 0, output: 500000, total: 9500000, provenance };
const filters = { q: '', agent: 'all', model: '', project: '', status: '' };
const pagination = { page: 1, pageSize: 25, totalItems: 1, totalPages: 1, hasPrevious: false, hasNext: false };
const sessionRow = {
  sessionKey: 'synthetic-session', sessionId: 'synthetic-provenance-session', title: 'Synthetic estimated session',
  agent: 'qoder', model: 'synthetic-model', tokens, rounds: 1, tools: 0, subagents: 0,
  projectKey, projectName: 'Synthetic Project', projectUrl: '/projects/' + projectKey,
  detailUrl: detailPath, createdAt: '2026-01-01T00:00:00Z', updatedAt: '2026-01-01T00:01:00Z',
};
const ratio = { value: null, reason: 'partial_token_measurement', provenance };
const summary = { tokens, filters, totalCount: 1, sessionCount: 1, totalSessions: 1, projectCount: 1,
  qoderSessions: 1, failedTools: 0, cacheReadRatio: ratio };
const round = { roundIndex: 1, callCount: 1, toolCallCount: 0, tokens: {
  fresh: 0, cacheRead: 0, cacheWrite: 0, output: 0, total: 0,
}, parity: { summary: 'Synthetic round without usage', isLowCache: true } };

async function syntheticApis(page, agents = [{ agent: 'Synthetic agent', scope: 'main', tokens: '9.5M' }], contextSegments = [], rounds = [round]) {
  await page.route('**/api/**', async (route) => {
    const pathname = new URL(route.request().url()).pathname;
    let data = { filters, rows: [], points: [], chips: [] };
    if (pathname.endsWith('/summary')) data = summary;
    if (pathname === '/api/sessions/options') data = { agents: [], models: [], projects: [], statuses: [] };
    if (pathname === '/api/sessions/rows' || pathname.endsWith('/sessions/rows')) data = { rows: [sessionRow], pagination, filters };
    if (pathname === '/api/projects/rows') data = { rows: [{ ...sessionRow, totalSessions: 1, agents: [{ agent: 'qoder', sessions: 1 }] }], pagination, filters };
    if (pathname.endsWith('/token-trend') || pathname.endsWith('/trends/tokens')) {
      data = { points: [{ date: '2026-01-01', label: 'Synthetic day', tokens }], rangeTotals: tokens };
    }
    if (pathname.endsWith('/trends/cache-health')) data = { points: [{ date: '2026-01-01', average: { ...tokens, ratio }, qoder: { ...tokens, ratio } }], latestRatio: ratio, lowestRatio: ratio };
    if (pathname.endsWith('/agents/contribution') || pathname.endsWith('/agent-mix')) data = { rows: [{ agent: 'qoder', label: 'Qoder', tokens, sessionCount: 1, sessions: 1, tokenShare: 100, sessionShare: 100 }] };
    if (pathname.endsWith('/agents/efficiency') || pathname.endsWith('/deep-dive')) data = { rows: [{ agent: 'qoder', model: 'synthetic-model', avgTokensPerSession: tokens.total, sessionCount: 1, cacheReuseRatio: null, provenance }] };
    if (pathname.endsWith('/meta')) data = { title: 'Synthetic estimated session', filters: { agent: 'qoder', sessionId: 'synthetic-provenance-session' } };
    if (pathname.endsWith('/metrics')) data = summary;
    if (pathname.endsWith('/diagnostics')) data = { parity: { agents, contextSegments } };
    if (pathname.endsWith('/execution')) data = { items: [], total: 0, offset: 0, nextCursor: null };
    if (pathname.endsWith('/rounds')) data = { roundCount: rounds.length, rounds };
    if (pathname.endsWith('/payloads')) data = { payloadCount: 0, payloads: [] };
    if (pathname.endsWith('/round/1')) data = { round: { calls: [{ callId: 'synthetic-call', scope: 'main', usage: { total: 0 }, timestamp: '2026-01-01T00:00:00Z' }] } };
    await fulfillIndexedJson(route, data);
  });
}

async function assertMeasurementLayout(page) {
  await page.setViewportSize({ width: 1440, height: 1100 });
  const layout = await page.evaluate(() => {
    const issues = [];
    document.querySelectorAll('[data-token-provenance], [data-token-measurement]').forEach((element) => {
      if (element.closest('[role="tabpanel"][hidden]')) return;
      const box = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      if (!box.width || !box.height) issues.push('Hidden measurement disclosure');
      if (style.whiteSpace === 'nowrap' && !element.matches('.token-total__value')) issues.push('Measurement disclosure cannot wrap');
      if (element.scrollWidth > element.clientWidth + 1) issues.push('Measurement disclosure text overflows');
      if (element.hasAttribute('data-token-provenance') && element.closest('.metric-cell') && box.width < 60) issues.push('Trace disclosure is squeezed');
    });
    document.querySelectorAll('.metric-card [data-token-measurement]').forEach((element) => {
      const secondary = element.closest('.metric-card').querySelector('.metric-card__secondary');
      if (secondary && element.getBoundingClientRect().bottom > secondary.getBoundingClientRect().top + 1) issues.push('KPI value overlaps secondary metrics');
      if (element.getBoundingClientRect().height > parseFloat(getComputedStyle(element).lineHeight) * 2 + 1) issues.push('KPI value is squeezed into more than two lines');
    });
    document.querySelectorAll('.chart-card h2').forEach((title) => {
      if (title.scrollWidth > title.clientWidth + 1) issues.push('Chart title overlaps stats');
    });
    if (document.documentElement.scrollWidth > window.innerWidth + 1) issues.push('Page has horizontal overflow');
    return issues;
  });
  expect(layout, `measurement layout at 1440px`).toEqual([]);
}

test('measurement helper distinguishes reported zero, unavailable, unknown and overlapping mixed coverage', async ({ page }) => {
  await page.setContent('<main id="measurement"></main>');
  await page.addScriptTag({ path: helperPath });
  const result = await page.evaluate(() => {
    const all = (state) => ({ freshInput: state, cacheRead: state, cacheWrite: state, output: state });
    const zero = { fresh: 0, cacheRead: 0, cacheWrite: 0, output: 0, total: 0 };
    const reported = { ...zero, fresh: 10, total: 10, provenance: all('provider_reported') };
    const missing = { ...zero, provenance: all('unavailable') };
    const unknown = { ...zero, total: 53 };
    const mixed = { ...zero, total: 9000000, provenance: { ...all('mixed'), estimatedSessionCount: 2, unavailableSessionCount: 2, unknownSessionCount: 1,
      estimationMethod: '<img src=x onerror=alert(1)>' } };
    TokenProvenance.attach(document.getElementById('measurement'), mixed);
    return {
      reportedZero: TokenProvenance.value(reported, 'cacheRead', String),
      reportedRatio: TokenProvenance.ratio(reported),
      unavailable: TokenProvenance.value(missing, 'cacheRead', String),
      unavailableRatio: TokenProvenance.ratio(missing),
      absentReadRatio: TokenProvenance.ratio({ ...reported, cacheRead: null }),
      absentDisplay: TokenProvenance.percent(null),
      ratioFormats: [0, 25, 100, 0.01, 99.99].map(TokenProvenance.percent),
      unknown: TokenProvenance.total(unknown, String),
      unknownZero: TokenProvenance.total(zero, String),
      mixed: TokenProvenance.total(mixed, String),
      mixedRatio: TokenProvenance.ratio(mixed, { value: 0 }),
    };
  });
  expect(result).toEqual({ reportedZero: '0', reportedRatio: '0%', unavailable: 'N/A',
    unavailableRatio: 'N/A', unknown: '53', unknownZero: 'N/A',
    absentReadRatio: 'N/A', absentDisplay: 'N/A', ratioFormats: ['0%', '25%', '100%', '<0.1%', '>99.9%'],
    mixed: '≈9000000', mixedRatio: 'N/A' });
  const evidence = page.locator('.token-evidence');
  await expect(evidence.locator('dt')).toHaveText(['本地估算（Estimated）', '未上报', '来源未知', '估算依据']);
  await expect(evidence.locator('dd')).toHaveText(['2 个会话', '2 个会话', '1 个会话', '当前视图未提供估算方法']);
  await expect(page.locator('#measurement img')).toHaveCount(0);
});

for (const [name, url, selector] of [
  ['Dashboard', '/dashboard', '.metric-card--kpi'],
  ['Sessions', '/sessions', '.page-head__stats'],
  ['Projects', '/projects', '.metric-grid'],
  ['Project Detail', '/projects/' + projectKey, '.project-detail-kpis'],
]) {
  test(`${name} uses the same synthetic estimated/partial semantics`, async ({ page }) => {
    const errors = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await syntheticApis(page);
    await page.goto(url);
    const measurement = page.locator(selector).filter({ has: page.locator('[data-token-provenance]') }).first();
    await expect(measurement).toContainText('≈9.5M');
    const disclosure = measurement.locator('[data-token-provenance]').first();
    const toggle = disclosure.locator('summary');
    const evidence = disclosure.locator('.token-evidence').first();
    await expect(toggle).toHaveText('计量详情');
    await expect(evidence).toBeHidden();
    await toggle.focus();
    await toggle.press('Enter');
    await expect(evidence).toBeVisible();
    await expect(evidence.locator('dt')).toHaveText(['本地估算（Estimated）', '未上报', '估算依据']);
    await expect(evidence.locator('dd').nth(0)).toHaveText('1 个会话');
    await expect(evidence).toContainText('可见对话上下文');
    await expect(evidence).toContainText('本地 transcript 缓存');
    await expect(evidence).not.toContainText(/visible_context_v1|cache_transcript_v1/);
    await toggle.click();
    await expect(evidence).toBeHidden();
    if (name === 'Dashboard') {
      const cache = page.locator('.metric-card--kpi').filter({ has: page.locator('.metric-card__label', { hasText: 'Cache Read Ratio' }) });
      await expect(cache).toContainText('N/A');
      await expect(cache.locator('.metric-card__secondary-value')).toHaveText(['N/A', 'N/A', 'N/A']);
      const tokenCard = page.locator('.metric-card--kpi').filter({ has: page.locator('.metric-card__label', { hasText: 'Total Tokens' }) });
      await expect(tokenCard.locator('.metric-card__secondary-value')).toHaveText(['≈9.0M', 'N/A', 'N/A', '≈500.0K']);
      const paths = page.locator('#cache-health-chart path.line-series');
      await expect(paths).toHaveCount(4);
      expect(await paths.evaluateAll((lines) => lines.every((line) => line.getAttribute('d') === ''))).toBe(true);
    }
    if (name === 'Sessions' || name === 'Projects' || name === 'Project Detail') {
      await expect(page.locator('td.token-cell').first()).toContainText('≈9.5M');
      if (name !== 'Sessions') {
        const rowDisclosure = page.locator('td.token-cell [data-token-provenance]').first();
        await expect(rowDisclosure).toContainText('未上报');
        const listUrl = page.url();
        await rowDisclosure.locator('summary').click();
        await expect(rowDisclosure.locator('.token-composition')).toBeVisible();
        await expect(page).toHaveURL(listUrl);
        await rowDisclosure.locator('summary').click();
      }
      const expectedCells = name === 'Sessions' ? 11 : name === 'Projects' ? 8 : 12;
      await expect(page.locator('td.token-cell').first().locator('..').locator(':scope > td')).toHaveCount(expectedCells);
    }
    await assertMeasurementLayout(page);
    expect(errors).toEqual([]);
  });
}

test('session estimate stays at session scope; round/call missing usage remains Unknown and is not low cache', async ({ page }) => {
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await syntheticApis(page);
  await page.goto(detailPath);
  await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  await expect(page.locator('.sd-kpi[aria-label="Total Tokens"]')).toContainText('≈9.5M');
  await expect(page.locator('.sd-kpi[aria-label="Total Tokens"]')).toContainText('缓存读取 N/A');
  await expect(page.locator('.sd-kpi[aria-label="Cache Health"] .sd-kpi__value')).toHaveText('N/A');
  await assertMeasurementLayout(page);
  const row = page.locator('[data-trace-round-row]').first();
  await expect(row).toHaveAttribute('data-is-low-cache', 'false');
  await expect(row.locator('.metric-token')).toHaveText('N/A');
  await row.locator('[data-action="toggle-round"]').click();
  await expect(row.locator('.metric-token')).toHaveText('N/A');
  const measurement = row.locator('[data-token-breakdown]');
  const source = await measurement.evaluate(el => TokenProvenance.state(JSON.parse(el.dataset.tokenBreakdown).tokens, 'output'));
  expect(source).toBe('unknown');
  await expect(page.locator('[data-trace-detail] .sd-tool-tokens:has-text("N/A")')).toHaveCount(0);
  await expect(page.locator('[data-trace-detail]')).not.toContainText('9.5M');
  await assertMeasurementLayout(page);
  await page.locator('[data-action="status-low-cache"]').click();
  await expect(row).toBeHidden();
  expect(errors).toEqual([]);
});

function agentSegments(total, state) {
  return { fresh: total, cacheRead: 0, cacheWrite: 0, output: 0, total,
    provenance: { freshInput: state, cacheRead: state, cacheWrite: state, output: state } };
}

test('an empty server-side round filter preserves session metrics and agent analysis', async ({ page }) => {
  await page.route('**/rounds*', async route => {
    const url = new URL(route.request().url());
    const response = await route.fetch({ url: url.origin + url.pathname });
    const json = await response.json();
    json.total = json.roundCount; // Enable the paged API contract used for long sessions.
    if (url.searchParams.get('trace_status') === 'failed') Object.assign(json, { total: 0, roundCount: 0, rounds: [], nextCursor: null });
    await route.fulfill({ response, json });
  });
  await page.goto(detailPath);
  await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  const workload = page.locator('[aria-label="Workload"] .sd-kpi__value');
  await expect(workload).toHaveText(/\d/);
  const count = await workload.innerText();
  const agents = page.locator('[data-subagent-row]');
  const known = await agents.allTextContents();
  expect(known.length).toBeGreaterThan(0);
  await page.locator('[data-action="status-failed"]').click();
  await expect(page.locator('[data-trace-round-row]')).toHaveCount(0);
  await expect(workload).toHaveText(count);
  await expect(agents).toHaveText(known);
  await page.locator('[data-action="status-all"]').click();
  await expect(page.locator('[data-trace-round-row]').first()).toBeVisible();
});

test('Diagnostics uses own MAIN and child tokenSegments rather than legacy combined workload', async ({ page }) => {
  await syntheticApis(page, [
    { agent: 'Synthetic MAIN', scope: 'main', tokens: '30', tokenSegments: agentSegments(10, 'provider_reported'),
      tokenShareValue: 100 / 3, tokenShareStatus: 'available', tokenShareBasis: 'observed_agent_usage' },
    { agent: 'Synthetic child', scope: 'subagent', subagentId: 'synthetic-child', tokens: '999',
      tokenSegments: agentSegments(20, 'provider_reported'), tokenShareValue: 200 / 3,
      tokenShareStatus: 'available', tokenShareBasis: 'observed_agent_usage',
      localRecords: 3, confirmedModelCalls: 3, models: ['child-model'] },
    { agent: 'Synthetic off-page child', scope: 'subagent', subagentId: 'off-page-child',
      tokenSegments: agentSegments(31, 'provider_reported'), localRecords: 7, confirmedModelCalls: 4, tools: 2, failures: 0 },
  ], [], [{ ...round, parity: { ...round.parity, agentUsage: [
    { owner: 'main', tokens: agentSegments(10, 'provider_reported') },
    { owner: 'subagent:synthetic-child', tokens: agentSegments(20, 'provider_reported') },
  ] } }]);
  await page.goto(detailPath);
  await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  await expect(page.locator('[data-subagent-row] td:nth-child(3)')).toHaveText(['10', '20', '31']);
  const panel = scope => page.locator('[data-subagent-timeline-panel][data-agent-scope="' + scope + '"] .sd-token-round');
  expect(JSON.parse(await panel('main').getAttribute('data-token-breakdown')).tokens.total).toBe(10);
  expect(JSON.parse(await panel('subagent').getAttribute('data-token-breakdown')).tokens.total).toBe(20);
  const offPage = page.locator('[data-subagent-timeline-panel][data-subagent="off-page-child"]');
  const rows = page.locator('[data-subagent-row]');
  await expect(rows.nth(1).locator('td:nth-child(2)')).toHaveText('3 次');
  await expect(rows.nth(1).locator('td:first-child')).toContainText('child-model');
  await rows.nth(2).getByRole('button', { name: 'Synthetic off-page child' }).click();
  await expect(offPage).toBeVisible();
  await expect(offPage).toContainText('4 次');
  await expect(offPage).not.toContainText('记录 7');
  await expect(offPage).toContainText(/工具：2 次\s*失败 0 次/);
  await expect(offPage.locator('[data-token-part="total"] strong')).toHaveText('31');
  await expect(offPage.locator('.sd-token-round')).toHaveCount(0);

});

test('unidentified child scope selects its own failure and tokens without inventing an Agent ID', async ({ page }) => {
  await syntheticApis(page, [
    { agent: 'Main', scope: 'main', tokenSegments: agentSegments(10, 'provider_reported'), tools: 1, failures: 0 },
    { agent: '未识别子 Agent（汇总）', scope: 'subagent_unknown', subagentId: '',
      tokenSegments: agentSegments(12, 'provider_reported'), tools: 1, failures: 1 },
    { agent: 'Identified child', scope: 'subagent', subagentId: 'unknown',
      tokenSegments: agentSegments(2, 'provider_reported'), tools: 0, failures: 0 },
  ], [], [{ ...round, parity: { ...round.parity, agentUsage: [
    { owner: 'main', tokens: agentSegments(10, 'provider_reported') },
    { owner: 'subagent_unknown', tokens: agentSegments(12, 'provider_reported'), failed: true },
    { owner: 'subagent:unknown', tokens: agentSegments(2, 'provider_reported') },
  ] } }]);
  await page.goto(detailPath);
  await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  const card = page.locator('.sd-diagnostic-card--agents');
  await expect(card.locator('header')).toContainText('2 个 Agent · 另有未识别子 Agent');
  const choice = card.getByRole('button', { name: '未识别子 Agent（汇总）' });
  await expect(choice).toHaveAttribute('data-subagent', '');
  await expect(choice.locator('..').locator('..')).toContainText('失败 1');
  await choice.click();
  const panel = card.locator('[data-subagent-timeline-panel]:visible');
  await expect(panel).toHaveAttribute('data-agent-scope', 'subagent_unknown');
  await expect(panel.locator('.sd-agent-source')).toHaveCount(0);
  const data = JSON.parse(await panel.locator('.sd-token-round').getAttribute('data-token-breakdown'));
  expect(data.tokens.total).toBe(12);
  expect(data.scale).toContain('issue');
});

test('Diagnostics preserves reported zero, unknown and missing measurements with legacy compatibility', async ({ page }) => {
  await syntheticApis(page, [
    { agent: 'Synthetic measured zero', scope: 'main', tokens: '999', tokenSegments: agentSegments(0, 'provider_reported') },
    { agent: 'Synthetic unknown zero', scope: 'subagent', tokens: '999', tokenSegments: agentSegments(0, 'unknown') },
    { agent: 'Synthetic missing zero', scope: 'subagent', tokens: '999', tokenSegments: agentSegments(0, 'unavailable') },
    { agent: 'Synthetic old structured', scope: 'subagent', tokens: agentSegments(17, 'unknown') },
    { agent: 'Synthetic old string', scope: 'subagent', tokens: '29' },
  ]);
  await page.goto(detailPath);
  await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  await expect(page.locator('[data-subagent-row] td:nth-child(3)')).toHaveText([
    '0', 'N/A', 'N/A', '17', 'N/A',
  ]);
});

test('Diagnostics single MAIN estimate stays estimated without borrowing session or tool workload', async ({ page }) => {
  await syntheticApis(page, [
    { agent: 'Synthetic estimated MAIN', scope: 'main', tokens: '999', tokenSegments: agentSegments(7, 'estimated'),
      tokenShareValue: 100, tokenShareStatus: 'partial', tokenShareBasis: 'session_estimate' },
  ], [], [{ ...round, parity: { ...round.parity, agentUsage: [{ owner: 'main', tokens: agentSegments(7, 'estimated') }] } }]);
  await page.goto(detailPath);
  await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  await expect(page.locator('[data-subagent-row]')).toHaveCount(1);
  await expect(page.locator('[data-subagent-row] td:nth-child(3)')).toHaveText('≈7');
  const chart = page.locator('[data-subagent-timeline-panel] .sd-token-round');
  expect(JSON.parse(await chart.getAttribute('data-token-breakdown')).tokens).toEqual(agentSegments(7, 'estimated'));
});

test('Trace child calls without lifecycle evidence stay Unknown and retain tool expansion', async ({ page }) => {
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await syntheticApis(page);
  await page.route('**/round/1', async (route) => fulfillIndexedJson(route, { round: {
    calls: [{ callId: 'synthetic-child-call', scope: 'subagent', subagentId: 'synthetic-child',
      usage: { total: 0 }, responseToolCallIds: ['synthetic-child-tool'] }],
    tools: [{ toolCallId: 'synthetic-child-tool', declaredByCallId: 'synthetic-child-call',
      name: 'shell', executionKind: 'shell', status: 'ok', exitCode: 0 }],
  } }));
  await page.goto(detailPath);
  await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  await page.locator('[data-trace-round-row]').first().locator('[data-action="toggle-round"]').click();
  const child = page.locator('[data-trace-detail] [data-subagent-block]');
  await expect(child).toHaveCount(1);
  await expect(child.locator('[data-subagent-state="unknown"]')).toHaveText('状态未记录');
  await expect(child.locator('.sd-subagent__head')).not.toContainText('completed');
  await expect(child.locator('.sd-subagent__head .sd-pill--ok')).toHaveCount(0);
  await expect(child.locator('.sd-subagent__meta')).toContainText('1 tools');
  const steps = child.locator('[data-sub-round-steps]');
  const expandAll = child.locator('[data-action="toggle-subagent-rounds"]');
  await expect(steps).toBeHidden();
  await expandAll.click();
  await expect(expandAll).toHaveAttribute('aria-expanded', 'true');
  await expect(steps).toBeVisible();
  await expect(steps.locator('[data-tool-call-id="synthetic-child-tool"]')).toContainText('Shell');
  await expandAll.click();
  await expect(expandAll).toHaveAttribute('aria-expanded', 'false');
  await expect(steps).toBeHidden();
  await child.locator('[data-action="toggle-sub-round"]').click();
  await expect(steps).toBeVisible();
  await expect(steps.locator('[data-tool-call-id="synthetic-child-tool"]')).toContainText('Shell');
  expect(errors).toEqual([]);
});

test('Context precision marks partial shares and excludes huge tool estimates from usage composition', async ({ page }) => {
  const segments = [
    { label: 'System', tokens: -1, tokensLabel: 'N/A', precision: 'unavailable', includedInUsage: false, shareStatus: 'unavailable' },
    ...[['Provider Cached Input', 924, 92.4], ['Fresh Input', 50, 5], ['Cache Write', 20, 2], ['Output', 6, 0.6]]
      .map(([label, total, shareValue]) => ({ label, tokens: total, tokensLabel: String(total), precision: 'mixed',
        includedInUsage: true, shareStatus: 'partial', shareValue, share: shareValue + '%' })),
    { label: 'Tool Results', tokens: 1000000000000, tokensLabel: '~1000G', precision: 'estimated',
      includedInUsage: false, shareStatus: 'unavailable', shareValue: 99, share: '99%' },
  ];
  await syntheticApis(page, undefined, segments);
  await page.goto(detailPath);
  await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  const context = page.locator('.sd-token-composition');
  const bars = context.locator('.sd-context-segment');
  await expect(bars).toHaveCount(4);
  expect(await bars.evaluateAll((elements) => elements.map((element) => element.style.getPropertyValue('--seg-width')))).toEqual(['92.4%', '5%', '2%', '0.6%']);
  await expect(context.locator('.sd-context-budget__item > span')).toHaveText(['缓存输入', '新输入', '缓存写入', '输出']);
  await expect(context.locator('.sd-context-budget__item > b')).toHaveText([
    '≈924 · ≈92.4%', '≈50 · ≈5%', '≈20 · ≈2%', '≈6 · ≈0.6%',
  ]);
  await page.setViewportSize({ width: 1440, height: 1100 });
  expect(await context.locator('.sd-context-budget__item span, .sd-context-budget__item b').evaluateAll((elements) =>
    elements.some((element) => element.scrollWidth > element.clientWidth + 1)), `Context legend at 1440px`).toBe(false);
});

test('Token 构成只展示正占比，区分实测与估算，不把未知或零当作有效分段', async ({ page }) => {
  await syntheticApis(page, undefined, [
    { label: 'Provider Cached Input', tokens: 30, precision: 'provider_reported', includedInUsage: true, shareStatus: 'available', shareValue: 75 },
    { label: 'Cache Write', tokens: 0, precision: 'provider_reported', includedInUsage: true, shareStatus: 'available', shareValue: 0 },
    { label: 'Output', tokens: 10, precision: 'estimated', includedInUsage: true, shareStatus: 'partial', shareValue: 25 },
    { label: 'Fresh Input', tokens: 0, precision: 'unknown', includedInUsage: true, shareStatus: 'unavailable', shareValue: 0 },
  ]);
  await page.goto(detailPath);
  await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  const context = page.locator('.sd-token-composition');
  await expect(context.locator('.sd-context-segment')).toHaveCount(2);
  await expect(context.locator('.sd-context-budget__item > span')).toHaveText(['缓存输入', '输出']);
  await expect(context.locator('.sd-context-budget__item > b')).toHaveText(['30 · 75%', '≈10 · ≈25%']);
});

for (const state of ['mixed', 'unknown', 'provider_reported']) {
  test(`Cache precision guards stale SSR pp badge for ${state} input`, async ({ page }) => {
    await page.addInitScript(() => document.addEventListener('DOMContentLoaded', () => {
      const card = Array.from(document.querySelectorAll('.metric-card--kpi')).find((element) =>
        element.querySelector('.metric-card__label')?.textContent.trim() === 'Cache Read Ratio');
      const badge = document.createElement('span');
      badge.className = 'metric-card__badge';
      badge.dataset.syntheticCacheBadge = '';
      badge.textContent = '-30.1pp';
      (card.querySelector('.metric-card__primary-row') || card).appendChild(badge);
    }));
    await syntheticApis(page);
    await page.route(/\/api\/dashboard\/summary(?:\?|$)/, async (route) => fulfillIndexedJson(route, {
      ...summary, tokens: agentSegments(100, state), cacheReadRatio: { value: state === 'provider_reported' ? 0 : null },
    }));
    await page.goto('/dashboard');
    const card = page.locator('.metric-card--kpi').filter({ has: page.locator('.metric-card__label', { hasText: 'Cache Read Ratio' }) });
    await expect(card.locator('.metric-card__value')).toHaveText(state === 'provider_reported' ? '0%' : 'N/A');
    await expect(card).toBeVisible();
    if (state === 'provider_reported') await expect(card.locator('[data-synthetic-cache-badge]')).toHaveText('-30.1pp');
    else await expect(card).not.toContainText(/\d(?:\.\d+)?\s*pp/);
  });
}

for (const state of ['provider_reported', 'estimated', 'mixed']) {
  test(`Sessions summary keeps ${state} token pills and provenance within header bounds`, async ({ page }) => {
    const measured = agentSegments(40100000, state);
    if (state !== 'provider_reported') Object.assign(measured.provenance, {
      estimatedSessionCount: 3, unavailableSessionCount: state === 'mixed' ? 2 : 0,
      unknownSessionCount: state === 'mixed' ? 1 : 0,
      estimationMethod: 'synthetic_visible_context_and_output_length_without_provider_usage',
    });
    await syntheticApis(page);
    await page.route(/\/api\/sessions\/summary(?:\?|$)/, async (route) => fulfillIndexedJson(route, {
      ...summary, totalCount: 5, projectCount: 4, tokens: measured,
    }));
    await page.goto('/sessions');
    const header = page.locator('.sessions-page .page-head');
    await expect(header.locator('.ui-stat-pill')).toHaveCount(3);
    await expect(header.locator('.ui-stat-pill').first()).toHaveText('5 sessions');
    await expect(header.locator('.ui-stat-pill').nth(1)).toHaveText('4 projects');
    await expect(header.locator('.ui-stat-pill').last()).toContainText('40.1M');
    if (state !== 'provider_reported') await expect(header.locator('[data-token-provenance]')).toContainText('Estimated');
    await page.setViewportSize({ width: 1440, height: 1100 });
    const issues = await header.evaluate((element) => {
      const result = [];
      const inside = (inner, outer) => inner.top >= outer.top - 1 && inner.bottom <= outer.bottom + 1
        && inner.left >= outer.left - 1 && inner.right <= outer.right + 1;
      const overlap = (a, b) => Math.min(a.right, b.right) - Math.max(a.left, b.left) > 1
        && Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top) > 1;
      const stats = element.querySelector('.page-head__stats');
      const statsBox = stats.getBoundingClientRect();
      const pills = Array.from(stats.querySelectorAll('.ui-stat-pill'));
      const boxes = pills.map((pill) => pill.getBoundingClientRect());
      if (statsBox.left < 0 || statsBox.right > window.innerWidth + 1) result.push('Stats outside viewport');
      if (overlap(element.firstElementChild.getBoundingClientRect(), statsBox)) result.push('Title overlaps stats');
      pills.forEach((pill, index) => {
        const range = document.createRange();
        range.selectNodeContents(pill);
        if (Array.from(range.getClientRects()).some((rect) => !inside(rect, boxes[index]))) result.push('Pill content outside border: ' + index);
        if (parseFloat(getComputedStyle(pill.querySelector('b')).fontSize) < 12) result.push('Pill value too small');
        if (boxes.some((box, other) => other !== index && overlap(box, boxes[index]))) result.push('Pills overlap');
      });
      stats.querySelectorAll('[data-token-provenance]').forEach((note) => {
        const box = note.getBoundingClientRect();
        if (!box.width || !box.height || !inside(box, statsBox) || note.scrollWidth > note.clientWidth + 1) result.push('Provenance hidden or outside stats');
        if (getComputedStyle(note).whiteSpace === 'nowrap') result.push('Provenance cannot wrap');
        if (boxes.some((pill) => overlap(pill, box))) result.push('Provenance overlaps pill');
      });
      return result;
    });
    expect(issues, `Sessions ${state} summary at 1440px`).toEqual([]);
  });
}

test('click opens the Sessions Token composition without navigating the row', async ({ page }) => {
  await syntheticApis(page);
  await page.goto('/sessions');
  const cell = page.locator('.sessions-row .token-cell').first();
  await expect(cell.locator('.token-total__value')).toHaveText('≈9.5M');
  await expect(cell.locator('.token-total__status')).toHaveCount(0);
  await expect(cell.locator('details')).toHaveCount(0);
  const listUrl = page.url();
  await cell.getByRole('button', { name: 'Token breakdown' }).click();
  const panel = page.locator('#token-bar-popover');
  await expect(panel.locator('.tokenbar-seg')).toHaveCount(0);
  await expect(panel.locator('[data-token-part]')).toHaveCount(5);
  await expect(panel.locator('.token-breakdown__row')).toHaveText([
    'Fresh≈9,000,000≈94.7%', 'Cache ReadN/AN/A', 'Cache WriteN/AN/A', 'Output≈500,000≈5.3%', 'Total≈9,500,000≈100%',
  ]);
  expect(await panel.evaluate(node => {
    const b = node.getBoundingClientRect();
    return b.left >= 0 && b.right <= innerWidth && b.top >= 0 && b.bottom <= innerHeight;
  })).toBe(true);
  await expect(page).toHaveURL(listUrl);
  await page.keyboard.press('Escape');
  const header = page.locator('.page-head__stats [data-token-provenance]');
  await header.locator('summary').press('Enter');
  await expect(header.locator('.token-evidence dt')).toHaveText(['本地估算（Estimated）', '未上报', '估算依据']);
  await expect(header).toContainText('会话数可能重叠，不能直接相加');
});
