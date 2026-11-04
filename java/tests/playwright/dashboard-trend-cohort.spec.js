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
  ['not-a-date', 999, 999, 999, 'unknown'],
];

const expected = {
  day: { labels: ['12-27', '12-28', '01-03', '01-04', '01-31', '02-01', '02-02'],
    sessions: [1, 2, 1, 1, 2, 3, 2], prompts: [2, 6, 4, 8, 6, 15, 8], averages: ['2.0', '3.0', '4.0', '8.0', '3.0', '5.0', '4.0'] },
  week: { labels: ['2020-W52', '2020-W53', '2021-W01', '2021-W04', '2021-W05'],
    sessions: [1, 3, 1, 2, 5], prompts: [2, 10, 8, 6, 23], averages: ['2.0', '3.3', '8.0', '3.0', '4.6'] },
  month: { labels: ['2020-12', '2021-01', '2021-02'],
    sessions: [3, 4, 5], prompts: [8, 18, 23], averages: ['2.7', '4.5', '4.6'] },
};

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
      points: points.map(([date, count]) => ({ date, totalCount: count, claudeCount: count })), rangeTotal: includeUnknownDate ? 1011 : 12,
    };
    if (url.pathname.endsWith('/trends/tokens')) data = {
      points: points.map(([date, , , total, state]) => ({ date, tokens: tokens(total, state), claudeTokens: total })),
      rangeTotals: tokens(includeUnknownDate ? 1279 : 280, 'unknown'),
    };
    if (url.pathname.endsWith('/trends/prompts')) data = {
      points: points.map(([date, , prompts]) => ({ date, totalPrompts: prompts, claudePrompts: prompts })),
      rangeTotalPrompts: includeUnknownDate ? 1048 : 49,
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
            await expect(page.locator(`#${id} .x-axis > span`)).toHaveText(sample.labels);
          }
          await expect(sessionBars.locator('.tooltip-row--total .tooltip-value')).toHaveText(sample.sessions.map(String));
          await expect(promptBars.locator('.tooltip-row--total .tooltip-value')).toHaveText(sample.prompts.map(String));
          for (let index = 0; index < sample.averages.length; index++) {
            await expect(promptBars.nth(index).locator('.tooltip-row--line .tooltip-value').first()).toHaveText(sample.averages[index]);
          }
          const partial = tokenTargets.filter({ hasText: 'Estimated' });
          await expect(partial).toHaveCount(1);
          await expect(partial).toContainText(grain === 'day' ? '≈20' : 'Partial');
          await expect(page.locator('[data-stat="range-total-sessions"]')).toContainText('12');
          await expect(page.locator('[data-stat="range-total-prompts"]')).toContainText('49');
          await expect(page.locator('[data-stat="range-total-tokens"]')).toContainText('280');
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
      await expect(page.locator('#trend-chart .x-axis > span')).toHaveText(expected.week.labels);
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
