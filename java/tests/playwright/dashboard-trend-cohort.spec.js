const { test, expect } = require('@playwright/test');

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
async function cohortApis(page, scope, grain, includeUnknownDate = true) {
  await page.clock.setFixedTime(new Date('2021-02-02T12:00:00Z'));
  const points = includeUnknownDate ? samples : samples.slice(0, -1);
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
    if (url.pathname.endsWith('/trends/prompts')) data = {
      points: points.map(([date, count, prompts]) => ({ date, totalPrompts: prompts, claudePrompts: prompts,
        measuredUserMessages: date === '2021-01-31' ? 3 : prompts,
        userMessageSampleCount: date === '2021-01-31' ? 1 : count,
        claudeMeasuredUserMessages: date === '2021-01-31' ? 3 : prompts,
        claudeUserMessageSampleCount: date === '2021-01-31' ? 1 : count })),
      rangeTotalPrompts: points.reduce((sum, point) => sum + point[2], 0),
    };
    await route.fulfill({ json: data });
  });
}

for (const timezoneId of ['America/Los_Angeles', 'Asia/Shanghai']) {
  test.describe(timezoneId, () => {
    test.use({ timezoneId });
    for (const scope of ['all', 'claude-code']) {
      for (const grain of ['day', 'week', 'month']) {
        test(`${scope}/${grain} groups UTC started cohorts with intact usage precision and prompt denominator`, async ({ page }) => {
          await cohortApis(page, scope, grain);
          await page.goto(`/dashboard?agent=${scope}&grain=${grain}`);
          const sample = expected[grain];
          const sessionBars = page.locator('#trend-chart .plot > .bar');
          const promptBars = page.locator('#prompt-activity-chart .plot > .bar');
          const tokenTargets = page.locator('#token-trend-chart .chart-hover-target');
          await expect(sessionBars).toHaveCount(sample.labels.length);
          await expect(promptBars).toHaveCount(sample.labels.length);
          await expect(tokenTargets).toHaveCount(sample.labels.length);
          for (const id of ['trend-chart', 'prompt-activity-chart', 'token-trend-chart']) {
            await expect(page.locator(`#${id} .x-axis > span`)).toHaveText(sample.axisLabels);
          }
          await expect(sessionBars.locator('.tooltip-row--total .tooltip-value')).toHaveText(sample.sessions.map(String));
          await expect(promptBars.locator('.tooltip-row--total .tooltip-value')).toHaveText(sample.prompts.map(String));
          await expect(sessionBars.locator('.tooltip-date')).toHaveText(sample.labels);
          await expect(promptBars.locator('.tooltip-date')).toHaveText(sample.labels);
          await expect(tokenTargets.locator('.tooltip-date')).toHaveText(sample.labels);
          for (let index = 0; index < sample.averages.length; index++) {
            const row = sample.rows[index];
            await expect(promptBars.nth(index).locator('.tooltip-row--line .tooltip-value').first()).toHaveText(sample.averages[index]);
            await expect(promptBars.nth(index).locator('.tooltip-row--line .tooltip-share').first())
              .toHaveText(`/ measured session · samples ${row[3]} / ${row[0]} cohort`);
            const total = tokenTargets.nth(index).locator('.tooltip-row').filter({ has: page.locator('.tooltip-label', { hasText: /^Total$/ }) }).locator('.tooltip-value');
            if (row[5] === 'provider_reported') {
              await expect(total).toHaveText(String(row[4]));
              // Cache-read zero is measured zero; a blank bucket must not acquire that precision.
              await expect(tokenTargets.nth(index).locator('.tooltip-row').nth(1).locator('.tooltip-value')).toHaveText('0');
            } else if (row[5] === 'partial') {
              await expect(total).toContainText('Partial');
            } else {
              await expect(total).toHaveText('N/A · Unknown');
            }
          }
          const partial = tokenTargets.filter({ hasText: 'Estimated' });
          await expect(partial).toHaveCount(grain === 'day' ? 0 : 1);
          if (grain !== 'day') await expect(partial).toContainText('Partial');
          await expect(page.locator('[data-stat="range-total-sessions"]')).toHaveText('Range total: ' + sample.totalSessions);
          await expect(page.locator('[data-stat="range-total-prompts"]')).toHaveText('Range total: ' + sample.totalPrompts);
          await expect(page.locator('[data-stat="range-total-tokens"]')).toContainText(String(sample.totalTokens));
          const label = scope === 'all' ? 'All agents' : 'Claude Code';
          const grainLabel = { day: '天', week: 'ISO 周', month: '自然月' }[grain];
          await expect(page.getByText(`按 UTC 开始日，按${grainLabel}统计 ${label} 新增会话`, { exact: false })).toBeVisible();
          await expect(page.getByText(`该批 ${label} 会话的整段累计 tokens`, { exact: false })).toBeVisible();
          await expect(page.getByText(`该批 ${label} 会话的整段累计 user prompts`, { exact: false })).toBeVisible();
        });
      }
    }
    test('valid UTC daily points retain ISO week-year across the browser timezone', async ({ page }) => {
      await cohortApis(page, 'all', 'week', false);
      await page.goto('/dashboard?grain=week');
      await expect(page.locator('#trend-chart .x-axis > span')).toHaveText(expected.week.axisLabels);
      await expect(page.locator('#prompt-activity-chart .plot > .bar .tooltip-row--total .tooltip-value')).toHaveText(expected.week.prompts.map(String));
    });
  });
}

for (const grain of ['week', 'month']) {
  test(`${grain} Latest uses the whole final cohort bucket rather than the last API day`, async ({ page }) => {
    await cohortApis(page, 'all', grain, false);
    await page.goto(`/dashboard?grain=${grain}`);
    await expect(page.locator('[data-stat="latest-sessions"]')).toHaveText('Latest: 5');
    await expect(page.locator('[data-stat="latest-prompts"]')).toHaveText('Latest: 23');
    await expect(page.locator('[data-stat="latest-tokens"]')).toHaveText('Latest: 130');
  });
}
