const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

// Synthetic API payloads and exact worktree JS; this suite does not claim packaged-resource parity.
const resourceRoot = path.join(__dirname, '../../web/src/main/resources');
const detailPath = '/sessions/claude_code/hifi-viz-session-001';
const startedAt = '2026-01-01T23:59:58.000Z';
const timing = {
  wallSeconds: 90000, wallPrecision: 'measured', activeTaskSeconds: 120, activeTaskPrecision: 'measured',
  activeTaskBasis: 'main_task_windows', agentTurnSeconds: 45, agentTurnPrecision: 'measured',
  agentTurnBasis: 'main_agent_turn_duration', modelExecutionSeconds: null, modelExecutionPrecision: 'unknown',
  toolExecutionSeconds: null, toolExecutionPrecision: 'unknown', completedTaskCount: 2, incompleteTaskCount: 0, abortedTaskCount: 0,
};
const provenance = { freshInput: 'provider_reported', cacheRead: 'provider_reported', cacheWrite: 'provider_reported', output: 'provider_reported' };
const tokens = { fresh: 100, cacheRead: 0, cacheWrite: 0, output: 10, total: 110, provenance };
const pagination = { page: 1, pageSize: 25, totalItems: 1, totalPages: 1 };

async function syntheticPage(page, { timingValue = timing, statistics, injectSource = process.env.FEIPI_UI_PACKAGED_RESOURCES !== '1', lowCacheAvailable = false, start = startedAt } = {}) {
  if (injectSource) {
    await page.route('**/static/js/**', async (route) => {
      const relative = new URL(route.request().url()).pathname.replace(/^\/static\//, 'static/');
      const file = path.join(resourceRoot, relative);
      await route.fulfill({ contentType: 'application/javascript', body: fs.readFileSync(file, 'utf8') });
    });
    const helperFile = path.join(resourceRoot, 'static/js/session-timing.js');
    if (fs.existsSync(helperFile)) await page.addInitScript({ path: helperFile });
    await page.addInitScript((css) => {
      document.addEventListener('DOMContentLoaded', () => {
        const style = document.createElement('style');
        style.textContent = css;
        document.head.appendChild(style);
      });
    }, fs.readFileSync(path.join(resourceRoot, 'static/css/session-timing.css'), 'utf8'));
  }
  await page.route('**/api/**', async (route) => {
    const pathname = new URL(route.request().url()).pathname;
    let data = { rows: [], points: [], chips: [], filters: {} };
    if (pathname.endsWith('/summary') || pathname.endsWith('/metrics')) {
      data = { tokens, timing: timingValue, durationSeconds: 90000, modelExecutionSeconds: 89880,
        toolExecutionSeconds: 0, parity: { activeSeconds: 90000, waitingSeconds: 0, modelTimeAvailable: true, toolTimeAvailable: true,
          lowCacheRoundsAvailable: lowCacheAvailable, lowCacheRounds: 0 },
        totalCount: 1, sessionCount: 1, totalSessions: 1, cacheReadStatistics: statistics };
    }
    if (pathname.endsWith('/meta')) data = { title: 'Synthetic overnight task', filters: {},
      createdAt: start, updatedAt: '2026-01-03T01:00:00.000Z' };
    if (pathname.endsWith('/execution')) data = { items: [], total: 0, offset: 0, nextCursor: null };
    if (pathname.endsWith('/rounds')) data = { roundCount: 2, rounds: [
      { roundIndex: 1, callCount: 1, parity: { time: '23:59:58' } },
      { roundIndex: 2, callCount: 0 },
    ] };
    if (pathname.endsWith('/payloads')) data = { payloads: [], payloadCount: 0 };
    if (pathname.endsWith('/rows')) data = { rows: [{ title: 'Synthetic overnight task', sessionId: 'synthetic-timing',
      tokens, timing: timingValue, durationSeconds: 90000, processSeconds: 89880, detailUrl: detailPath }], pagination, filters: {} };
    if (pathname.endsWith('/options')) data = { agents: [], models: [], projects: [], statuses: [] };
    // Keep the live SSR snapshot identity while replacing synthetic timing data.
    const response = await route.fetch();
    await route.fulfill({ response, status: 200, json: data });
  });
}

test('timing helper distinguishes measured zero, partial task windows, unknown and cumulative workload', async ({ page }) => {
  await page.setContent('<main></main>');
  await page.addScriptTag({ path: path.join(resourceRoot, 'static/js/session-timing.js') });
  const values = await page.evaluate((sample) => {
    return [SessionTiming.value(sample, 'activeTaskSeconds'), SessionTiming.value(sample, 'modelExecutionSeconds'),
      SessionTiming.value({ activeTaskSeconds: 0, activeTaskPrecision: 'measured' }, 'activeTaskSeconds'),
      SessionTiming.value({ activeTaskSeconds: 0, activeTaskPrecision: 'unknown' }, 'activeTaskSeconds'),
      SessionTiming.value({ activeTaskSeconds: 25, activeTaskPrecision: 'partial' }, 'activeTaskSeconds'),
      SessionTiming.seconds({ activeTaskSeconds: 0.35, activeTaskPrecision: 'partial' }, 'activeTaskSeconds'),
      SessionTiming.value({ modelExecutionSeconds: 0, modelExecutionPrecision: 'measured' }, 'modelExecutionSeconds'),
      SessionTiming.value({ toolExecutionSeconds: 0, toolExecutionPrecision: 'unknown' }, 'toolExecutionSeconds'),
      SessionTiming.value({ agentTurnSeconds: 90001, agentTurnPrecision: 'measured' }, 'agentTurnSeconds')];
  }, timing);
  expect(values).toEqual(['2m 0s', 'N/A', '0s', 'N/A', '25s · Partial', 0.35, '0s', 'N/A', '25h 0m']);
});

for (const [label, sample, active] of [
  ['measured', timing, '2 分 0 秒'],
  ['rounds seconds', { ...timing, activeTaskSeconds: 21.899 }, '21.9 秒'],
  ['rounds across a minute', { ...timing, activeTaskSeconds: 59.96 }, '1 分 0 秒'],
  ['measured zero', { ...timing, activeTaskSeconds: 0 }, '0 秒'],
  ['subsecond', { ...timing, activeTaskSeconds: 0.35 }, '0.4 秒'],
  ['unknown', null, '未记录'],
  ['partial', { ...timing, activeTaskSeconds: 25, activeTaskPrecision: 'partial', incompleteTaskCount: 1 }, '25 秒 · 部分'],
]) {
  test(`detail shows ${label} source duration separately from start timestamps`, async ({ page }) => {
    await syntheticPage(page, { timingValue: sample, start: sample ? startedAt : null });
    await page.goto(detailPath);
    await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
    const started = page.locator('time[data-session-started]');
    await expect(started).toBeVisible();
    if (sample) {
      await expect(started).toHaveAttribute('datetime', startedAt);
      await expect(started).toHaveText(/\d{2}:\d{2}:\d{2}/);
    } else {
      await expect(started).not.toHaveAttribute('datetime');
      await expect(started).toHaveText('未记录');
    }
    const card = page.locator('[data-session-timing]');
    await expect(card.locator('.sd-kpi__label')).toHaveText('任务活动时长');
    await expect(card.locator('[data-session-timing-value]')).toHaveText(active);
    await expect(card.locator('.sd-kpi__subgrid > span')).toHaveText([
      '来源记录时间跨度 ' + (sample ? '1500 分 0 秒' : '未记录'),
      '主会话轮次累计 ' + (sample ? '45 秒' : '未记录'),
      '来源模型计时 未记录',
      '来源工具计时 未记录',
    ]);
    await expect(card).toHaveAttribute('title', /包括任务内工具和等待，不等于模型执行时间/);
    const trace = page.locator('[data-trace-list]');
    await expect(trace.locator('th.time-col')).toHaveAttribute('title', /首个已记录的调用时间点/);
    await expect(trace.locator('th.duration-col')).toHaveAttribute('title', /源中独立计量/);
    await expect(trace.locator('td.time-col .sd-time-point')).toHaveText(['23:59:58', '—']);
    await expect(trace.locator('td.duration-col .sd-time-duration')).toHaveText(['—', '—']);
    await expect(page.locator('.sd-kpi[aria-label="Cache Health"]')).toContainText('低缓存记录 N/A');
    for (const width of [1440, 1024]) {
      await page.setViewportSize({ width, height: 1100 });
      const overflow = await card.evaluate(element => [...element.querySelectorAll('.sd-kpi__value, .sd-kpi__subgrid > span')]
        .some(part => part.scrollWidth > part.clientWidth + 1));
      expect(overflow).toBe(false);
    }
  });
}

for (const url of ['/sessions', '/projects/test-hifi-project']) {
  test(`list Task Active uses typed task windows at ${url}`, async ({ page }) => {
    await syntheticPage(page);
    await page.goto(url);
    await expect(page.getByRole('columnheader', { name: 'Task Active' })).toBeVisible();
    await expect(page.locator('[data-task-active]').first()).toHaveText('2m 0s');
    if (url === '/sessions') await expect(page.locator('[data-wall-duration]')).toHaveCount(0);
    else await expect(page.locator('[data-wall-duration]').first()).toHaveText('25h 0m');
    await expect(page.locator('[data-session-timing-description]')).toContainText('MAIN task windows');
  });
}

for (const statistics of [
  { eligibleSessions: 2, p50SessionRatio: 0, lowReadSessions: 2, excludedSessions: 3, basis: 'provider_reported_input' },
  { eligibleSessions: 0, p50SessionRatio: null, lowReadSessions: 0, excludedSessions: 5, basis: 'provider_reported_input' },
]) {
  test(`cache distribution shows measurable subset with ${statistics.eligibleSessions} eligible sessions`, async ({ page }) => {
    await syntheticPage(page, { statistics });
    await page.goto('/dashboard');
    const card = page.locator('.metric-card--kpi').filter({ has: page.locator('.metric-card__label', { hasText: 'Cache Read Ratio' }) });
    await expect(card.locator('.metric-card__secondary-value')).toHaveText([
      String(statistics.eligibleSessions), statistics.eligibleSessions ? '0.0%' : 'N/A', String(statistics.lowReadSessions),
    ]);
    const toggle = card.locator('[data-token-provenance] summary');
    await expect(toggle).toHaveText('计量详情');
    await expect(card.locator('[data-cache-measurement]')).toBeHidden();
    await toggle.click();
    await expect(card.locator('[data-cache-measurement]')).toBeVisible();
    await expect(card.locator('[data-cache-measurement]')).toContainText(`Excluded: ${statistics.excludedSessions} sessions`);
    await expect(card.locator('[data-cache-measurement]')).toContainText('provider-reported input');
  });
}
