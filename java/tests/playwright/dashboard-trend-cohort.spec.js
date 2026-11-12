const { test, expect } = require('@playwright/test');

// Keep the live SSR snapshot identity while replacing only synthetic renderer data.
async function fulfillIndexedJson(route, json) {
  const response = await route.fetch();
  return route.fulfill({ response, status: 200, json });
}

test('event coverage presents measured counts in prose without exposing API keys', async ({ page }) => {
  await page.route('**/api/dashboard/event-activity?*', (route) => fulfillIndexedJson(route, {
    coverage: 'partial', windowDays: 30, days: [], coverageCounts: {
      indexedSessions: 1234, summarizedSessions: 23, unknownSessions: 1211,
      observedUserMessages: 39, undatedUserMessages: 2, supportedUsageEvents: 57,
      unsupportedUsageEvents: 14, undatedUsageEvents: 0,
      futureExcludedDayBuckets: 1, futureExcludedObservedUserMessages: 3,
    },
  }));
  await page.goto('/dashboard');
  const coverage = page.locator('[data-event-activity-coverage]');
  await expect(coverage).toBeHidden();
  const disclosure = page.locator('[data-event-activity-disclosure] summary');
  await expect(disclosure).toBeVisible();
  await disclosure.press('Enter');
  await expect(coverage).toBeVisible();
  await expect(coverage).toContainText('1,234 indexed sessions', { timeout: 3000 });
  await expect(coverage).toContainText('1,211 without event coverage');
  await expect(coverage).not.toContainText(/indexedSessions=|futureExcluded/);
  await expect(page.locator('[data-event-activity-future]')).toContainText('3 observed user messages');
});

test('dashboard secondary values disclose partial segments and describe UTC session starts', async ({ page }) => {
  await page.route('**/api/dashboard/summary?*', async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    body.tokens = { ...tokens(500, 'provider_reported'), cacheWrite: 0 };
    body.tokens.provenance.cacheWrite = 'mixed';
    await route.fulfill({ response, json: body });
  });
  await page.goto('/dashboard?agent=qoder');
  await expect(page.locator('[data-secondary-tooltip="Cache Write"] .metric-card__secondary-value'))
    .toHaveText('N/A · Partial', { timeout: 2500 });
  await expect(page.locator('[data-secondary-tooltip="Today"]')).toHaveAttribute('data-tooltip-def', /UTC.*started_at/);
});

// Synthetic daily cohort API points; resources are always served by the packaged launcher.
const samples = [
  ['2020-12-27', 1, 2, 10, 'provider_reported'],
  ['2020-12-28', 2, 6, 20, 'estimated'],
  ['2021-01-03', 1, 4, 30, 'unknown'],
  ['2021-01-04', 1, 8, 40, 'provider_reported'],
  ['2021-01-31', 2, 6, 50, 'provider_reported'],
  ['2021-02-01', 3, 15, 60, 'provider_reported'],
  ['2021-02-02', 2, 8, 70, 'provider_reported'],
  ['2020-01-01', 999, 999, 999, 'unknown'], // Outside every frozen calendar window.
  ['2021-02-03', 999, 999, 999, 'unknown'], // Future, including in the current week/month.
  ['not-a-date', 999, 999, 999, 'unknown'],
];

// Independent calendar oracle: the frozen as-of is 2021-02-02, not the last API date.
// Explicit nonempty buckets retain ISO year-boundary evidence; the rest are calendar blanks.
const dayLabels = Array.from({ length: 30 }, (_, index) => {
  const date = new Date(Date.UTC(2021, 0, 4 + index));
  return date.toISOString().slice(5, 10);
});
const weekLabels = [
  ...Array.from({ length: 15 }, (_, index) => `2020-W${39 + index}`),
  '2021-W01', '2021-W02', '2021-W03', '2021-W04', '2021-W05',
];
const monthLabels = ['2020-03', '2020-04', '2020-05', '2020-06', '2020-07', '2020-08',
  '2020-09', '2020-10', '2020-11', '2020-12', '2021-01', '2021-02'];
// Tuple: sessions, raw prompts, measured prompts, measured sessions, tokens, precision.
const known = {
  day: { '01-04': [1, 8, 8, 1, 40, 'provider_reported'], '01-31': [2, 6, 3, 1, 50, 'provider_reported'],
    '02-01': [3, 15, 15, 3, 60, 'provider_reported'], '02-02': [2, 8, 8, 2, 70, 'provider_reported'] },
  week: { '2020-W52': [1, 2, 2, 1, 10, 'provider_reported'], '2020-W53': [3, 10, 10, 3, 50, 'partial'],
    '2021-W01': [1, 8, 8, 1, 40, 'provider_reported'], '2021-W04': [2, 6, 3, 1, 50, 'provider_reported'],
    '2021-W05': [5, 23, 23, 5, 130, 'provider_reported'] },
  month: { '2020-12': [3, 8, 8, 3, 30, 'partial'], '2021-01': [4, 18, 15, 3, 120, 'partial'],
    '2021-02': [5, 23, 23, 5, 130, 'provider_reported'] },
};
const expected = Object.fromEntries(Object.entries({ day: dayLabels, week: weekLabels, month: monthLabels }).map(([grain, labels]) => {
  const rows = labels.map(label => known[grain][label] || [0, 0, 0, 0, 0, 'unknown']);
  const step = { day: 3, week: 2, month: 1 }[grain];
  return [grain, { labels, axisLabels: labels.map((label, index) => index % step === 0 ? label : ''),
    rows, sessions: rows.map(row => row[0]), prompts: rows.map(row => row[1]),
    averages: rows.map(row => row[3] ? (row[2] / row[3]).toFixed(1) : 'N/A'),
    totalSessions: grain === 'day' ? 8 : 12, totalPrompts: grain === 'day' ? 37 : 49,
    totalTokens: grain === 'day' ? 220 : 280 }];
}));

/** 构造显式来源的纯合成 token 四段。 */
function tokens(total, state) {
  return { fresh: total, cacheRead: 0, cacheWrite: 0, output: 0, total, provenance: {
    freshInput: state, cacheRead: state, cacheWrite: state, output: state,
    estimatedSessionCount: state === 'estimated' ? 1 : 0,
    unknownSessionCount: state === 'unknown' ? 1 : 0,
  } };
}

/** 提供日级合成 cohort 点，保留未知日期和来源以检验 UI 守卫。 */
async function cohortApis(page, scope, grain, points) {
  await page.clock.setFixedTime(new Date('2021-02-02T12:00:00Z'));
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url());
    let data = { rows: [], points: [] };
    if (url.pathname.endsWith('/summary')) data = { tokens: tokens(280, 'unknown'), sessionCount: 12 };
    if (url.pathname.startsWith('/api/dashboard/trends/')) {
      expect(url.searchParams.get('agent')).toBe(scope);
      expect(url.searchParams.get('grain')).toBe(grain);
    }
    if (url.pathname.endsWith('/trends/sessions')) data = {
      points: points.map(([date, count]) => ({ date, totalCount: count, claudeCount: count })), rangeTotal: points.reduce((sum, point) => sum + point[1], 0),
    };
    if (url.pathname.endsWith('/trends/tokens')) data = {
      points: points.map(([date, , , total, state]) => ({ date, tokens: tokens(total, state), claudeTokens: total })),
      rangeTotals: tokens(points.reduce((sum, point) => sum + point[3], 0), 'unknown'),
    };
    if (url.pathname.endsWith('/trends/cache-health')) {
      const cacheTuple = (fresh, cacheRead, state) => ({ fresh, cacheRead, cacheWrite: 0,
        provenance: tokens(0, state).provenance,
        ratio: { value: state === 'provider_reported' && fresh + cacheRead > 0
          ? cacheRead / (fresh + cacheRead) : null } });
      data = { points: points.map(([date, , , total, state]) => {
        const measuredZero = date === '2021-02-01';
        const cohort = cacheTuple(measuredZero ? 0 : total, measuredZero || date === '2021-02-02' ? 0 : total, state);
        return { date, average: cohort, claudeCode: cohort };
      }) };
    }
    if (url.pathname.endsWith('/trends/prompts')) data = {
      points: points.map(([date, count, prompts]) => ({ date, totalPrompts: prompts, claudePrompts: prompts,
        measuredUserMessages: date === '2021-01-31' ? 3 : prompts,
        userMessageSampleCount: date === '2021-01-31' ? 1 : count,
        claudeMeasuredUserMessages: date === '2021-01-31' ? 3 : prompts,
        claudeUserMessageSampleCount: date === '2021-01-31' ? 1 : count })),
      rangeTotalPrompts: points.reduce((sum, point) => sum + point[2], 0),
    };
    await fulfillIndexedJson(route, data);
  });
}

for (const timezoneId of ['America/Los_Angeles', 'Asia/Shanghai']) {
  test.describe(timezoneId, () => {
    test.use({ timezoneId });
    // Keep all grain boundaries in LA; Shanghai repeats day/week only because the
    // date renderer uses API calendar strings (month adds no independent TZ boundary).
    for (const scope of ['all', 'claude-code']) {
      const grains = timezoneId === 'Asia/Shanghai'
        ? (scope === 'all' ? ['day', 'week'] : [])
        : ['day', 'week', 'month'];
      for (const grain of grains) {
        test(`${scope}/${grain} groups UTC started cohorts with intact usage precision and prompt denominator`, async ({ page }) => {
          // Keep a valid-only ISO week oracle as well as the malformed-date guard.
          const points = timezoneId === 'Asia/Shanghai' && grain === 'week' ? samples.slice(0, -1) : samples;
          await cohortApis(page, scope, grain, points);
          await page.goto(`/dashboard?agent=${scope}&grain=${grain}`);
          const sample = expected[grain];
          const sessionBars = page.locator('#trend-chart .plot > .bar');
          const promptBars = page.locator('#prompt-activity-chart .plot > .bar');
          const tokenTargets = page.locator('#token-trend-chart .chart-hover-target');
          await expect(sessionBars).toHaveCount(sample.labels.length);
          await expect(promptBars).toHaveCount(sample.labels.length);
          await expect(tokenTargets).toHaveCount(sample.labels.length);
          const cacheTargets = page.locator('#cache-health-chart .chart-hover-target');
          await expect(cacheTargets.locator('.tooltip-date')).toHaveText(sample.labels);
          for (const id of ['trend-chart', 'prompt-activity-chart', 'token-trend-chart', 'cache-health-chart']) {
            await expect(page.locator(`#${id} .x-axis > span`)).toHaveText(sample.axisLabels);
          }
          if (grain === 'day') {
            for (const [date, plotted] of [['01-04', 1], ['01-05', 0], ['02-01', 0], ['02-02', 1]]) {
              const point = cacheTargets.filter({ has: page.locator('.tooltip-date').getByText(date, { exact: true }) });
              await expect(point.locator('.line-point')).toHaveCount(plotted);
            }
            const first = page.locator('#cache-health-chart .chart-legend__item').first();
            await expect(first).toHaveText(scope === 'all' ? 'Average' : 'Claude Code');
            const alignment = await page.locator('[data-dashboard-chart] .plot').evaluateAll(plots =>
              plots.map(plot => {
                const box = plot.getBoundingClientRect();
                const chart = plot.closest('.chart-card').getBoundingClientRect();
                return [Math.round(box.left - chart.left), Math.round(chart.right - box.right)];
              }));
            expect(new Set(alignment.map(value => JSON.stringify(value))).size).toBe(1);
          }
          await expect(sessionBars.locator('.tooltip-row--total .tooltip-value')).toHaveText(sample.sessions.map(String));
          await expect(promptBars.locator('.tooltip-row--total .tooltip-value')).toHaveText(sample.prompts.map(String));
          await expect(sessionBars.locator('.tooltip-date')).toHaveText(sample.labels);
          await expect(promptBars.locator('.tooltip-date')).toHaveText(sample.labels);
          expect(await tokenTargets.evaluateAll(targets => targets.map(target => JSON.parse(target.dataset.tokenBreakdown).title))).toEqual(sample.labels);
          const promptRows = await promptBars.evaluateAll(bars => bars.map(bar => ({
            average: bar.querySelector('.tooltip-row--line .tooltip-value')?.textContent,
            denominator: bar.querySelector('.tooltip-row--line .tooltip-share')?.textContent,
          })));
          expect(promptRows.map(row => row.average)).toEqual(sample.averages);
          expect(promptRows.map(row => row.denominator)).toEqual(sample.rows.map(row =>
            `/ measured session · samples ${row[3]} / ${row[0]} cohort`));
          const tokenParts = await tokenTargets.evaluateAll(targets => targets.map(target => {
            const data = JSON.parse(target.dataset.tokenBreakdown);
            const panel = TokenProvenance.breakdown(data.tokens, data);
            return { total: panel.querySelector('[data-token-part="total"] strong').textContent,
              read: panel.querySelector('[data-token-part="cacheRead"] strong').textContent,
              state: TokenProvenance.state(data.tokens), estimated: (data.tokens.provenance || {}).estimatedSessionCount > 0 };
          }));
          expect(tokenParts.map(part => part.total)).toEqual(sample.rows.map(row => row[5] === 'provider_reported'
            ? String(row[4]) + ' · 服务商上报' : row[5] === 'partial' ? expect.stringContaining('部分数据') : 'N/A · 来源未知'));
          expect(tokenParts.filter((part, index) => sample.rows[index][5] === 'provider_reported').map(part => part.read))
            .toEqual(sample.rows.filter(row => row[5] === 'provider_reported').map(() => '0 · 服务商上报'));
          const partial = tokenParts.filter(part => part.estimated);
          expect(partial).toHaveLength(grain === 'day' ? 0 : 1);
          if (grain !== 'day') expect(partial[0].state).toBe('mixed');
          await expect(page.locator('[data-stat="range-total-sessions"]')).toHaveText('Range total: ' + sample.totalSessions);
          await expect(page.locator('[data-stat="range-total-prompts"]')).toHaveText('Range total: ' + sample.totalPrompts);
          await expect(page.locator('[data-stat="range-total-tokens"]')).toContainText(String(sample.totalTokens));
          const label = scope === 'all' ? 'All agents' : 'Claude Code';
          const grainLabel = { day: '天', week: 'ISO 周', month: '自然月' }[grain];
          await expect(page.getByText(`按 UTC 开始日，按${grainLabel}统计 ${label} 新增会话`, { exact: false })).toBeVisible();
          await expect(page.getByText(`该批 ${label} 会话的整段累计 tokens`, { exact: false })).toBeVisible();
          await expect(page.getByText(`该批 ${label} 会话的整段累计 user prompts`, { exact: false })).toBeVisible();
          if (scope === 'all' && grain !== 'day') {
            await expect(page.locator('[data-stat="latest-sessions"]')).toHaveText('Latest: 5');
            await expect(page.locator('[data-stat="latest-prompts"]')).toHaveText('Latest: 23');
            await expect(page.locator('[data-stat="latest-tokens"]')).toHaveText('Latest: 130');
          }
        });
      }
    }
  });
}

test('event table keeps coverage and exact values available without a full-height table', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-11-20T12:00:00Z'));
  const measured = { reportedTokens: 12345678, reportedSamples: 1, estimatedSamples: 0,
    unavailableSamples: 0, unknownSamples: 0, mixedSamples: 0 };
  await page.route('**/api/dashboard/event-activity?*', route => fulfillIndexedJson(route, {
    coverage: 'partial', windowDays: 30, coverageCounts: { indexedSessions: 9, summarizedSessions: 3, unknownSessions: 6 },
    days: Array.from({ length: 20 }, (_, i) => ({ date: '2026-11-' + String(i + 1).padStart(2, '0'),
      observedUserMessages: i, tokens: { fresh: measured, cacheRead: { ...measured, reportedTokens: 0 }, cacheWrite: { ...measured, reportedSamples: 0 }, output: measured } })),
  }));
  await page.goto('/dashboard');
  const scroll = page.locator('.event-activity-scroll');
  await expect(scroll.locator('tbody tr')).toHaveCount(20);
  await expect(scroll.locator('tbody tr').first()).toContainText('2026-11-20');
  await expect(scroll.locator('tbody tr').first()).toContainText('12.3M');
  expect(await scroll.evaluate(e => e.scrollHeight > e.clientHeight && e.clientHeight <= 360)).toBe(true);
  await expect(page.locator('[data-event-activity-coverage]')).toBeHidden();
  const coverage = page.locator('[data-event-activity-disclosure] summary');
  await coverage.press('Enter');
  await expect(page.locator('[data-event-activity-coverage]')).toBeVisible();
  await page.locator('[data-event-activity-exact]').press('Space');
  await expect(scroll.locator('tbody tr').first()).toContainText('12,345,678');
});
