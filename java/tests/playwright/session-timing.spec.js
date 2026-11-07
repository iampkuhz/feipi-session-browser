const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

// Synthetic API payloads and exact worktree JS; this suite does not claim packaged-resource parity.
const resourceRoot = path.join(__dirname, '../../web/src/main/resources');
const detailPath = '/sessions/claude_code/hifi-viz-session-001';
const timing = {
  wallSeconds: 90000, wallPrecision: 'measured', activeTaskSeconds: 120, activeTaskPrecision: 'measured',
  activeTaskBasis: 'main_task_windows', agentTurnSeconds: 45, agentTurnPrecision: 'measured',
  agentTurnBasis: 'main_agent_turn_duration', modelExecutionSeconds: null, modelExecutionPrecision: 'unknown',
  toolExecutionSeconds: null, toolExecutionPrecision: 'unknown', completedTaskCount: 2, incompleteTaskCount: 0, abortedTaskCount: 0,
};
const provenance = { freshInput: 'provider_reported', cacheRead: 'provider_reported', cacheWrite: 'provider_reported', output: 'provider_reported' };
const tokens = { fresh: 100, cacheRead: 0, cacheWrite: 0, output: 10, total: 110, provenance };
const pagination = { page: 1, pageSize: 25, totalItems: 1, totalPages: 1 };

async function syntheticPage(page, { timingValue = timing, statistics, injectSource = process.env.FEIPI_UI_PACKAGED_RESOURCES !== '1', lowCacheAvailable = false } = {}) {
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
    if (pathname.endsWith('/meta')) data = { title: 'Synthetic overnight task', filters: {} };
    if (pathname.endsWith('/rounds')) data = { rounds: [], roundCount: 0 };
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
      SessionTiming.nonTaskWall({ ...sample, activeTaskPrecision: 'partial' }),
      SessionTiming.value({ modelExecutionSeconds: 0, modelExecutionPrecision: 'measured' }, 'modelExecutionSeconds'),
      SessionTiming.value({ toolExecutionSeconds: 0, toolExecutionPrecision: 'unknown' }, 'toolExecutionSeconds'),
      SessionTiming.value({ agentTurnSeconds: 90001, agentTurnPrecision: 'measured' }, 'agentTurnSeconds')];
  }, timing);
  expect(values).toEqual(['2m 0s', 'N/A', '0s', 'N/A', '25s · Partial', 'N/A', '0s', 'N/A', '25h 0m']);
});

for (const [label, sample] of [['measured', timing], ['unknown', undefined],
  ['partial', { ...timing, activeTaskSeconds: 25, activeTaskPrecision: 'partial', incompleteTaskCount: 1 }]]) {
  test(`detail shows ${label} source timing without legacy execution/wait fallback`, async ({ page }) => {
    await syntheticPage(page, { timingValue: sample === undefined ? null : sample });
    await page.goto(detailPath);
    await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
    const card = page.locator('[data-session-timing]');
    await expect(card).toContainText('Source Task Active');
    await expect(card.locator('.sd-kpi__value')).toHaveText(sample ? (label === 'partial' ? '25s · Partial' : '2m 0s') : 'N/A');
    await expect(card).toContainText(sample ? 'Agent Turn 45s' : 'Agent Turn N/A');
    await expect(card).toContainText('Model Execution N/A');
    await expect(card).toContainText('Tool Execution N/A');
    const disclosure = card.locator('[data-session-timing-note]');
    const toggle = disclosure.locator('summary');
    await expect(toggle).toHaveText('Timing details');
    await expect(disclosure.locator('p')).toBeHidden();
    await page.setViewportSize({ width: 390, height: 900 });
    await toggle.focus();
    await toggle.press('Enter');
    await expect(disclosure.locator('p')).toBeVisible();
    if (sample) {
      await expect(disclosure).toContainText('Completed: 2');
      await expect(disclosure).toContainText('recorded main-agent turn durations');
      await expect(disclosure).not.toContainText(/main_task_windows|main_agent_turn_duration/);
    }
    await expect(card).toContainText('Non-task Wall Time');
    await expect(card).not.toContainText('Waiting Time');
    await expect(card).toContainText('not model inference');
    await expect(page.locator('.sd-kpi[aria-label="Cache Health"]')).toContainText('Low-cache rows N/A');
    await expect(card).toContainText('Non-task Wall Time: ' + (label === 'measured' ? '24h 58m' : 'N/A'));
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: 1100 });
      const overflow = await card.evaluate((element) => Array.from(element.querySelectorAll('.session-timing-note, .session-timing-value'))
        .some((part) => part.scrollWidth > part.clientWidth + 1));
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
    await expect(page.locator('[data-wall-duration]').first()).toHaveText('25h 0m');
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
    await expect(toggle).toHaveText('Measurement details');
    await expect(card.locator('[data-cache-measurement]')).toBeHidden();
    await toggle.click();
    await expect(card.locator('[data-cache-measurement]')).toBeVisible();
    await expect(card.locator('[data-cache-measurement]')).toContainText(`Excluded: ${statistics.excludedSessions} sessions`);
    await expect(card.locator('[data-cache-measurement]')).toContainText('provider-reported input');
  });
}
