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
    if (pathname.endsWith('/execution')) data = { items: [], total: 0, offset: 0, nextCursor: null };
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
  await page.locator('[data-evidence-analysis] > summary').click();
    await page.locator('[data-secondary-metrics] > summary').click();
    const card = page.locator('[data-session-timing]');
    await expect(card).toContainText('主会话任务活动时间');
    await expect(card.locator('.sd-kpi__value')).toHaveText(sample ? (label === 'partial' ? '25s · Partial' : '2m 0s') : 'N/A');
    await expect(card).toContainText(sample ? '主会话轮次累计 45s' : '主会话轮次累计 N/A');
    await expect(card).toContainText('来源模型计时 N/A');
    await expect(card).toContainText('来源工具计时 N/A');
    const disclosure = card.locator('[data-session-timing-note]');
    const toggle = disclosure.locator('summary');
    await expect(toggle).toHaveText('计时口径与来源');
    await expect(disclosure.locator(':scope > p')).toHaveCount(3);
    for (let i = 0; i < 3; i++) await expect(disclosure.locator(':scope > p').nth(i)).toBeHidden();
    await page.setViewportSize({ width: 390, height: 900 });
    await toggle.focus();
    await toggle.press('Enter');
    for (let i = 0; i < 3; i++) await expect(disclosure.locator(':scope > p').nth(i)).toBeVisible();
    await expect(disclosure.locator('p').nth(0)).toContainText('计时口径：');
    await expect(disclosure.locator('p').nth(1)).toContainText('来源依据：');
    await expect(disclosure.locator('p').nth(2)).toContainText('缺测与记录：');
    if (sample) {
      await expect(disclosure).toContainText('已结束：2');
      await expect(disclosure).toContainText('记录中的主会话轮次时长累计');
      await expect(disclosure).not.toContainText(/main_task_windows|main_agent_turn_duration/);
    }
    await expect(card).toContainText('任务外记录跨度');
    await expect(card).not.toContainText('Waiting Time');
    await expect(card).toContainText('不是模型推理耗时');
    await expect(page.locator('.sd-kpi[aria-label="Cache Health"]')).toContainText('Low-cache rows N/A');
    await expect(card).toContainText('任务外记录跨度：' + (label === 'measured' ? '24h 58m' : 'N/A'));
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

test('source timing Chinese basis and record states stay presentation-only', async ({ page }) => {
  // UI-only basis/count boundary data, not additional provider/parser evidence.
  await page.setContent('<div class="sd-kpi" tabindex="-1"><div class="sd-kpi__value">0s</div><div class="sd-kpi__label"></div></div>');
  await page.addScriptTag({ path: path.join(resourceRoot, 'static/js/session-timing.js') });
  const proof = await page.evaluate(sample => {
    const card = document.querySelector('.sd-kpi'); SessionTiming.applyDetail(card, sample);
    const note = card.querySelector('details'), summary = note.querySelector('summary'); note.open = true; summary.focus();
    const fallback = SessionTiming.description({ ...sample, activeTaskBasis: 'other', agentTurnBasis: 'main_task_duration_sum', activeTaskPrecision: 'partial', incompleteTaskCount: 1, abortedTaskCount: 2 });
    const unknown = SessionTiming.description({});
    const methods = [
      { ...sample, activeTaskSeconds: 0, activeTaskPrecision: 'measured' },
      { ...sample, activeTaskSeconds: 25, activeTaskPrecision: 'partial' },
      { ...sample, activeTaskSeconds: null, activeTaskPrecision: 'unknown', completedTaskCount: 0, incompleteTaskCount: 0, abortedTaskCount: 0 },
      { ...sample, activeTaskSeconds: -1, activeTaskPrecision: 'measured' }
    ].map(value => ({ text: SessionTiming.description(value), value: SessionTiming.value(value, 'activeTaskSeconds') }));
    const updates = [sample, { ...sample, activeTaskBasis: 'other', agentTurnBasis: 'main_task_duration_sum' }, {}, { ...sample, activeTaskSeconds: 0, activeTaskPrecision: 'measured' }, { ...sample, activeTaskPrecision: 'partial' }, sample].map(value => {
      SessionTiming.applyDetail(card, value);
      return { count: note.querySelectorAll(':scope > p').length, paragraphs: Array.from(note.querySelectorAll(':scope > p'), p => p.textContent), same: note === card.querySelector('details') && summary === note.querySelector('summary'), focus: document.activeElement === summary, open: note.open };
    });
    return { methods, updates, text: note.textContent, fallback, unknown, sameCard: card === document.querySelector('[data-session-timing]'), sameNote: note === card.querySelector('details'), sameSummary: summary === note.querySelector('summary'), focused: document.activeElement === summary, open: note.open, value: card.querySelector('.sd-kpi__value').textContent, aria: card.getAttribute('aria-label') };
  }, timing);
  expect(proof).toMatchObject({ sameCard: true, sameNote: true, sameSummary: true, focused: true, open: true, value: '0s', aria: '主会话任务活动时间' });
  for (const update of proof.updates) { expect(update).toMatchObject({ count: 3, same: true, focus: true, open: true }); expect(update.paragraphs.map(p => p.split('：')[0])).toEqual(['计时口径', '来源依据', '缺测与记录']); }
  expect(proof.updates[1].paragraphs[1]).toContain('不冒称实测轮次'); expect(proof.updates[1].paragraphs[1]).not.toContain('重叠窗口只计一次');
  expect(proof.updates[2].paragraphs[1]).not.toContain('轮次依据'); expect(proof.updates[2].paragraphs[1]).not.toContain('主任务时间窗口');
  expect(proof.updates[5].paragraphs[1]).not.toContain('不冒称实测轮次');
  expect(proof.methods.map(method => method.value)).toEqual(['0s', '25s · Partial', 'N/A', 'N/A']);
  for (const method of proof.methods) {
    expect(method.text).toContain('任务汇总方法：按主任务时间窗口计时，重叠窗口只计一次。');
    expect(method.text).not.toContain('任务依据：记录中的主任务时间窗口');
  }
  expect(proof.text).toContain('重叠窗口只计一次'); expect(proof.text).toContain('记录中的主会话轮次时长累计');
  expect(proof.fallback).toContain('无可用时间窗口时的主任务时长累计，不冒称实测轮次'); expect(proof.fallback).not.toContain('重叠窗口只计一次');
  expect(proof.fallback).toContain('已结束：2 · 未闭合：1 · 中止：2'); expect(proof.fallback).toContain('任务外记录跨度：N/A');
  expect(proof.unknown).toContain('已结束：未报告 · 未闭合：未报告 · 中止：未报告'); expect(proof.unknown).not.toContain('重叠窗口只计一次');
  expect(proof.unknown).toContain('N/A 表示未知而非 0'); expect(proof.unknown).toContain('Partial 表示部分测量'); expect(proof.text).toContain('不表示业务成功');
});
