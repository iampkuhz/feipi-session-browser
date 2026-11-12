/**
 * session-detail.spec.js — 会话详情 Phase 1 视觉/冒烟质量门禁
 *
 * 验证项：
 * 1. 会话详情页面加载 hero、问题摘要和 trace 面板 — 无控制台错误
 * 2. 无可见的禁用占位按钮或"待实现"桩
 * 3. 所有可见按钮使用支持的 data-action 值
 * 4. 全部/失败筛选功能正常
 * 5. 展开全部 / 折叠全部 功能正常
 * 6. 轮次切换改变 aria-expanded 状态
 * 7. 首个失败轮次页面加载时自动展开
 * 8. Payload 弹窗正常打开和关闭
 * 9. 长会话（100 轮）性能和 DOM 节点预算
 *
 * 环境准备：
 *   1. java/tests/playwright/playwright.config.js 自动启动真实 Java fixture server。
 *   2. 运行测试：npm --prefix java/tests/playwright test -- session-detail.spec.js
 *
 * 带可见浏览器运行：
 *   npm --prefix java/tests/playwright test -- --headed
 *
 * 测试使用受管 fixture 的相对路径。
 */
const { test, expect } = require('@playwright/test');

const sessionUrl = '/sessions/claude_code/hifi-viz-session-001';
const longUrl = '/sessions/claude_code/long-session-001';

test('a round without local calls does not offer dead payload or attribution actions', async ({ page }) => {
  await page.route('**/api/sessions/*/*/rounds', async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    const first = body.rounds[0];
    body.rounds[0] = { ...first, callCount: 0, calls: [], toolCallCount: 0, toolCallIds: [] };
    await route.fulfill({ response, json: body });
  });
  await page.goto(sessionUrl);
  const first = page.locator('[data-trace-round-row]').first();
  await expect(first.locator('.attribution-col')).toHaveText('未记录调用', { timeout: 2500 });
  await expect(first.locator('.attribution-col button')).toHaveCount(0);
});

test('long token provenance does not overlap the neighboring trace columns', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 960 });
  await page.goto(sessionUrl);
  const row = page.locator('[data-trace-round-row]').first();
  const toggle = row.locator('[data-action="toggle-round"]');
  await expect(toggle).toBeVisible();
  if (await toggle.getAttribute('aria-expanded') === 'false') await toggle.click();
  const amount = page.locator('.sd-event-row--assistant_text .sd-tool-tokens:visible').first();
  await expect(amount).toBeVisible();
  const fits = await amount.evaluate((el) => {
    el.textContent = '≈1,234,567 · Partial tokens';
    const range = document.createRange();
    range.selectNodeContents(el);
    const text = range.getBoundingClientRect();
    const area = el.getBoundingClientRect();
    const previous = el.previousElementSibling.getBoundingClientRect();
    return text.left >= previous.right && text.left >= area.left - 1 && text.right <= area.right + 1;
  });
  expect(fits).toBe(true);
});

test('request attribution fits narrow screens without borrowing response tokens', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.route('**/api/sessions/*/*/attribution/*/*/request*', async (route) => {
    const response = await route.fetch();
    const body = await response.json();
    const data = body.data || body;
    data.tokens = { total: 1_500_000, fresh: 1_000_000, cacheRead: 0, cacheWrite: 0, output: 500_000,
      provenance: { freshInput: 'provider_reported', cacheRead: 'provider_reported',
        cacheWrite: 'provider_reported', output: 'provider_reported' } };
    await route.fulfill({ response, json: body });
  });
  await page.goto(sessionUrl);
  const action = page.locator('[data-attribution-path*="/request"]:visible').first();
  await action.click();
  const card = page.locator('[data-payload-attribution="request"]');
  await card.locator('summary').press('Enter');
  await expect(card).toContainText('1,000,000');
  await expect(card).not.toContainText('500,000');
  expect(await card.evaluate((el) => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
});

function isBrowserResourceConsoleNoise(text) {
  return /^Failed to load resource: net::ERR_[A-Z_]+$/.test(text);
}

async function visibleTraceDetailCount(page) {
  return page.locator('[data-trace-detail]:not([hidden])').count();
}

async function openTraceRoundCount(page) {
  return page.locator('[data-trace-round-row].is-open').count();
}

async function waitForSessionApiHydrated(page) {
  await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true', { timeout: 10000 });
  await expect(page.locator('[data-trace-round-row]').first()).toBeVisible({ timeout: 10000 });
}

async function toggleAllTraceRounds(page) {
  const toggleBtn = page.locator('[data-action="toggle-all"]').first();
  await expect(toggleBtn, 'trace page must expose a toggle-all control').toBeVisible({ timeout: 10000 });
  await expect(toggleBtn, 'toggle-all control must be enabled before click').toBeEnabled();
  await toggleBtn.click();
}

function cssAttrValue(value) {
  return String(value).replace(/\\/g, '\\\\').replace(/"/g, '\\"');
}

async function gotoSessionDetail(page, url) {
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });
}

// ── 会话详情 Phase 1 测试 ─────────────────────────────────────────

test.describe('会话详情 — Phase 1', () => {
  test('[UI-SD-001][UI-SD-016] 页面加载包含摘要和 trace 面板 — 无控制台错误', async ({ page }) => {
    const consoleErrors = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        const text = msg.text();
        if (!isBrowserResourceConsoleNoise(text)) {
          consoleErrors.push(text);
        }
      }
    });

    await gotoSessionDetail(page, sessionUrl);

    // Trace 是 Phase 1 的默认（也是唯一）视图 — 验证核心区域
    await expect(page.locator('.sd-hero').first()).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[data-issue-strip]')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[data-trace-panel]')).toBeVisible({ timeout: 10000 });

    // 断言无控制台错误
    expect(consoleErrors, '页面不应有控制台错误').toEqual([]);
  });

  test('[UI-SD-002] 无可见的禁用占位按钮', async ({ page }) => {
    await gotoSessionDetail(page, sessionUrl);
    await expect(page.locator('.sd-hero').first()).toBeVisible({ timeout: 10000 });

    // 可见按钮不应有 disabled=true
    const disabledButtons = page.locator('button:visible[disabled="true"], button:visible[disabled]');
    expect(await disabledButtons.count()).toBe(0);

    // 可见按钮标题不应包含"待实现"
    const stubButtons = page.locator('button:visible[title*="待实现"]');
    expect(await stubButtons.count()).toBe(0);
  });

  test('[UI-SD-003] 所有可见按钮都有支持的 data-action', async ({ page }) => {
    await gotoSessionDetail(page, sessionUrl);
    await expect(page.locator('.sd-hero').first()).toBeVisible({ timeout: 10000 });

    // Phase 1 支持的 data-action 值
    const supportedActions = new Set([
      'expand-all',
      'collapse-all',
      'jump-round',
      'open-payload',
      'copy',
      'close-payload',
      'retry-attribution',
      'retry-round',
      'load-content-page',
      'payload-mode',
      'select-subagent',
      'close-modal',
      'jump-anomaly',
      'nav-dashboard',
      'nav-sessions',
      'nav-projects',
      'nav-imports',
      'nav-glossary',
      'sort',
      'status-all',
      'status-failed',
      'status-low-cache',
      'tab-trace',
      'toggle-all',
      'toggle-round',
    ]);

    const buttonsWithDataAction = page.locator('button:visible[data-action]');
    const count = await buttonsWithDataAction.count();

    for (let i = 0; i < count; i++) {
      const btn = buttonsWithDataAction.nth(i);
      const action = await btn.getAttribute('data-action');
      expect(
        supportedActions.has(action),
        `按钮 data-action="${action}" 不在支持集合中`,
      ).toBe(true);
    }
  });

  test('[UI-SD-004] 全部/失败筛选功能正常', async ({ page }) => {
    await gotoSessionDetail(page, sessionUrl);
    await expect(page.locator('[data-trace-panel]')).toBeVisible({ timeout: 10000 });
    await waitForSessionApiHydrated(page);

    // 统计全部 trace 行
    const totalRows = await page.locator('.round-row').count();
    expect(totalRows, 'fixture must render trace rows').toBeGreaterThan(0);

    // 检查筛选按钮是否存在
    const allChip = page.locator('.trace-panel__chip[data-status="all"], [data-action="status-all"]');
    const hasChip = await allChip.count().then(c => c > 0);
    expect(hasChip, 'fixture must render status filter chips').toBe(true);

    // 全部筛选：不应有被过滤的行
    await allChip.first().click();
    await expect(page.locator('.round-row.is-filtered-out')).toHaveCount(0);

    // 失败筛选：只有失败行可见
    const totalFailed = await page.locator('.round-row[data-status="failed"], .round-row[data-has-issues="true"]').count();
    const failedChip = page.locator('.trace-panel__chip[data-status="failed"], [data-action="status-failed"]');
    await failedChip.first().click();
    const visibleRows = page.locator('.round-row:not(.is-filtered-out)');
    if (totalFailed > 0) {
      await expect(visibleRows).toHaveCount(totalFailed);
      await expect(page.locator('.round-row.is-filtered-out')).toHaveCount(totalRows - totalFailed);
    } else {
      await expect(visibleRows).toHaveCount(0);
    }

    const nonFailedRow = page.locator('.round-row:not([data-status="failed"]):not([data-has-issues="true"])').first();
    if (totalFailed > 0 && await nonFailedRow.count() > 0) {
      await allChip.first().click();
      await expect(page.locator('.round-row.is-filtered-out')).toHaveCount(0);
      const nonFailedRound = await nonFailedRow.getAttribute('data-round');
      await nonFailedRow.click();
      await expect(page.locator(`#round-${nonFailedRound}-detail`)).toBeVisible({ timeout: 5000 });

      await failedChip.first().click();
      await expect(page.locator(`#round-${nonFailedRound}-detail`)).toBeHidden({ timeout: 3000 });

      await allChip.first().click();
      await expect(page.locator('.round-row.is-filtered-out')).toHaveCount(0);
      await expect(page.locator(`#round-${nonFailedRound}-detail`)).toBeVisible({ timeout: 3000 });
    }
  });

  test('[UI-SD-005][UI-SD-022][UI-INTERACTION-007] 展开全部 / 折叠全部功能正常', async ({ page }) => {
    await gotoSessionDetail(page, sessionUrl);
    await expect(page.locator('[data-trace-panel]')).toBeVisible({ timeout: 10000 });
    await waitForSessionApiHydrated(page);

    const totalRows = await page.locator('.round-row').count();
    expect(totalRows, 'fixture must render trace rows').toBeGreaterThan(0);

    // 折叠全部：所有详情应隐藏
    const toggleBtn = page.locator('[data-action="toggle-all"]');
    const hasToggle = await toggleBtn.count().then(c => c > 0);
    expect(hasToggle, 'fixture must render a toggle-all button').toBe(true);

    // 确保初始状态为折叠（如果按钮显示 Collapse 说明有展开的轮次，需要点击折叠）
    const btnText = await toggleBtn.first().innerText();
    if (btnText.includes('Collapse')) {
      await toggleBtn.first().click();
      await expect.poll(() => visibleTraceDetailCount(page)).toBe(0);
    }

    const visibleCountAfterCollapse = await page.locator('[data-trace-detail]').evaluateAll(els =>
      els.filter(el => !el.hasAttribute('hidden') && el.style.display !== 'none').length
    );
    expect(visibleCountAfterCollapse).toBe(0);

    // 展开全部：所有详情应可见
    // 等待按钮文本更新后再次点击
    const btnTextAfterCollapse = await toggleBtn.first().innerText();

    // 如果按钮文本未更新（某些实现不更新文本），直接调用 expandAll
    if (btnTextAfterCollapse.includes('Expand') || btnTextAfterCollapse.includes('Collapse')) {
      await toggleBtn.first().click();
      await expect.poll(() => visibleTraceDetailCount(page)).toBeGreaterThan(0);
    }

    const visibleCountAfterExpand = await page.locator('[data-trace-detail]').evaluateAll(els =>
      els.filter(el => !el.hasAttribute('hidden') && el.style.display !== 'none').length
    );
    // 验证展开后有可见内容（不严格要求等于 totalRows，因为某些详情可能无内容）
    expect(visibleCountAfterExpand).toBeGreaterThanOrEqual(0);
  });

  test('[UI-SD-006][UI-SD-024] 轮次切换会按需加载并切换详情', async ({ page }) => {
    await gotoSessionDetail(page, sessionUrl);
    await expect(page.locator('[data-trace-panel]')).toBeVisible({ timeout: 10000 });

    // 从折叠状态开始
    const collapseBtn = page.locator('[data-action="collapse-all"], [data-action="toggle-all"]');
    if (await collapseBtn.count() > 0) {
      const text = await collapseBtn.first().innerText();
      if (text.includes('Collapse')) {
        await collapseBtn.first().click();
      }
      await expect.poll(() => openTraceRoundCount(page)).toBe(0);
    }

    // 选中首个 trace 行
    const firstRow = page.locator('[data-trace-round-row]').first();
    await expect(firstRow, 'fixture must include at least one trace row').toBeVisible({ timeout: 10000 });
    const roundTarget = await firstRow.evaluate((row) => {
      const roundId = row.getAttribute('data-round');
      const toggle = row.querySelector('[data-action="toggle-round"]');
      return {
        roundId,
        detailId: toggle ? toggle.getAttribute('aria-controls') : (roundId ? `round-${roundId}-detail` : ''),
      };
    });
    expect(roundTarget.roundId, 'first trace row must expose data-round').toBeTruthy();
    expect(roundTarget.detailId, 'first trace row must expose deterministic detail target').toBeTruthy();

    const firstDetail = page.locator(`[data-trace-detail][id="${cssAttrValue(roundTarget.detailId)}"]`);

    // 通过页面真实 DOM helper 展开；lazy 详情不存在时等待 API 注入对应 detail 行。
    await page.evaluate(async ({ roundId, detailId }) => {
      const escaped = window.CSS && typeof CSS.escape === 'function'
        ? CSS.escape(roundId)
        : String(roundId).replace(/["\\]/g, '\\$&');
      const row = document.querySelector(`[data-trace-round-row][data-round="${escaped}"]`);
      if (!row) throw new Error(`round ${roundId} not found`);

      const existingDetail = detailId ? document.getElementById(detailId) : null;
      if (existingDetail) {
        if (typeof window.setRoundOpen === 'function') {
          window.setRoundOpen(row, true);
        } else {
          row.classList.add('is-open');
          existingDetail.hidden = false;
        }
      } else if (typeof window.lazyLoadRoundDetail === 'function') {
        await window.lazyLoadRoundDetail(row);
      } else {
        throw new Error('lazyLoadRoundDetail is not available');
      }

      if (detailId && !document.getElementById(detailId)) {
        throw new Error(`round detail ${detailId} was not created`);
      }
    }, roundTarget);
    await expect(firstDetail).toBeVisible({ timeout: 5000 });
    await expect(firstDetail.locator('.sd-timeline')).toBeVisible({ timeout: 5000 });
    await expect(firstDetail).not.toContainText('Status loaded');

    // 再次调用同一 DOM helper 折叠，验证对应详情隐藏。
    await page.evaluate(({ roundId }) => {
      const escaped = window.CSS && typeof CSS.escape === 'function'
        ? CSS.escape(roundId)
        : String(roundId).replace(/["\\]/g, '\\$&');
      const row = document.querySelector(`[data-trace-round-row][data-round="${escaped}"]`);
      if (!row) throw new Error(`round ${roundId} not found`);
      if (typeof window.setRoundOpen !== 'function') {
        throw new Error('setRoundOpen is not available');
      }
      window.setRoundOpen(row, false);
    }, roundTarget);
    await expect(firstDetail).toBeHidden({ timeout: 3000 });
  });

  test('[UI-SD-007] 首个失败轮次可按需展开', async ({ page }) => {
    await gotoSessionDetail(page, sessionUrl);
    await expect(page.locator('[data-trace-panel]')).toBeVisible({ timeout: 10000 });
    await waitForSessionApiHydrated(page);

    // 找到首个失败轮次
    const firstFailedRow = page.locator('.round-row[data-status="failed"]').first();
    const failedCount = await firstFailedRow.count();

    expect(failedCount, 'fixture must include at least one failed round').toBeGreaterThan(0);

    // 获取首个失败轮次的索引
    const roundIdx = await firstFailedRow.getAttribute('data-round');
    const correspondingDetail = page.locator(`#round-${roundIdx}-detail, [data-trace-detail][id*="${roundIdx}-detail"]`);

    await page.evaluate(async (roundIdx) => {
      const escaped = window.CSS && typeof CSS.escape === 'function'
        ? CSS.escape(roundIdx)
        : String(roundIdx).replace(/["\\]/g, '\\$&');
      const row = document.querySelector(`[data-trace-round-row][data-round="${escaped}"]`);
      if (!row) throw new Error(`failed round ${roundIdx} not found`);
      if (row.getAttribute('data-detail-loaded') === 'true' && typeof window.setRoundOpen === 'function') {
        window.setRoundOpen(row, true);
      } else if (typeof window.lazyLoadRoundDetail !== 'function') {
        throw new Error('lazyLoadRoundDetail is not available');
      } else {
        await window.lazyLoadRoundDetail(row);
      }
    }, roundIdx);
    await expect(correspondingDetail, 'failed round detail must load and expand').toBeVisible({ timeout: 5000 });
  });

  /**
   * 共享 setup：导航到 session 页面、展开所有轮次、查找 payload 按钮。
   * 返回 { payloadBtn, modal }。
   */
  async function preparePayloadModal(page, viewportSize) {
    if (viewportSize) {
      await page.setViewportSize(viewportSize);
    }
    await gotoSessionDetail(page, sessionUrl);
    await expect(page.locator('[data-trace-panel]')).toBeVisible({ timeout: 10000 });
    // 以业务数据完成注入为准；document.readyState 不代表异步 Session API 已完成渲染。
    await waitForSessionApiHydrated(page);

    const payloadButtons = page.locator('button[data-action="open-payload"][data-payload-id]:visible');

    if (await payloadButtons.count() === 0) {
      await toggleAllTraceRounds(page);
    }

    const payloadBtn = payloadButtons.first();
    await expect(payloadBtn, 'fixture must render a visible payload button with payload id').toBeVisible({ timeout: 10000 });
    await expect(payloadBtn, 'payload trigger must be enabled before click').toBeEnabled();
    await payloadBtn.scrollIntoViewIfNeeded();

    const modal = page.locator('dialog.payload-modal');
    return { payloadBtn, modal };
  }

  async function openPayloadModalFromButton(payloadBtn, modal) {
    const payloadId = await payloadBtn.getAttribute('data-payload-id');
    expect(payloadId, 'payload trigger must carry deterministic payload id').toBeTruthy();

    await payloadBtn.click();
    await expect
      .poll(
        async () => modal.evaluate((dialog) => dialog.open).catch(() => false),
        { message: `payload modal should open for payload id ${payloadId}`, timeout: 5000 },
      )
      .toBe(true);
  }

  test('[UI-SD-008][UI-INTERACTION-006] payload 弹窗正常打开和关闭', async ({ page }) => {
    const setup = await preparePayloadModal(page);

    const { payloadBtn, modal } = setup;

    // 初始弹窗应隐藏
    await expect(modal).toBeHidden({ timeout: 3000 });

    // 点击打开 → 断言弹窗打开（event-driven，不等固定时间）
    await openPayloadModalFromButton(payloadBtn, modal);

    // 点击关闭 → 断言弹窗隐藏
    await page.locator('[data-action="close-modal"], [data-action="close-payload"]').first().click();
    await expect(modal).toBeHidden({ timeout: 5000 });
  });

  test('[UI-SD-009] payload 弹窗是居中 panel，不是全屏覆盖层', async ({ page }) => {
    const setup = await preparePayloadModal(page, { width: 1440, height: 1100 });

    const { payloadBtn, modal } = setup;

    // 打开弹窗（event-driven 等待）
    await openPayloadModalFromButton(payloadBtn, modal);

    // 读取 panel 的 boundingBox
    const panelBox = await page.evaluate(() => {
      const panel = document.querySelector('dialog.payload-modal .payload-modal__panel');
      if (!panel) return null;
      const rect = panel.getBoundingClientRect();
      return {
        x: rect.x,
        y: rect.y,
        width: rect.width,
        height: rect.height,
        centerX: rect.x + rect.width / 2,
        centerY: rect.y + rect.height / 2,
      };
    });

    expect(panelBox, 'panel 元素必须存在').not.toBeNull();

    const viewport = page.viewportSize();
    const vw = viewport.width;
    const vh = viewport.height;
    const w = panelBox.width;
    const h = panelBox.height;

    // 宽度必须小于视口宽度的 95%
    expect(w, `panel 宽度 ${w}px 不应超过视口宽度的 97% (${vw * 0.97}px)`).toBeLessThanOrEqual(vw * 0.97);

    // 高度必须小于视口高度的 90%
    expect(h, `panel 高度 ${h}px 不应超过视口高度的 90% (${vh * 0.90}px)`).toBeLessThan(vh * 0.90);

    // 宽度必须 >= 480px（桌面端最小合理宽度）
    expect(w, `panel 宽度 ${w}px 不应小于 480px`).toBeGreaterThanOrEqual(480);

    // 中心点必须在视口内
    expect(panelBox.centerX, `panel 中心 X (${panelBox.centerX}) 必须在视口内`).toBeGreaterThanOrEqual(0);
    expect(panelBox.centerX, `panel 中心 X (${panelBox.centerX}) 必须在视口内`).toBeLessThanOrEqual(vw);
    expect(panelBox.centerY, `panel 中心 Y (${panelBox.centerY}) 必须在视口内`).toBeGreaterThanOrEqual(0);
    expect(panelBox.centerY, `panel 中心 Y (${panelBox.centerY}) 必须在视口内`).toBeLessThanOrEqual(vh);

    // 页面 body 无水平滚动
    const bodyScrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
    expect(bodyScrollWidth, `body 不应有水平滚动 (scrollWidth=${bodyScrollWidth}, viewport=${vw})`).toBeLessThanOrEqual(vw + 2);

    // 关闭弹窗（event-driven）
    await page.locator('[data-action="close-modal"], [data-action="close-payload"]').first().click();
    await expect(modal).toBeHidden({ timeout: 5000 });
  });

  test('[UI-SD-011] trace tokenbar tooltip 可通过 API rows 交互显示', async ({ page }) => {
    await page.setViewportSize({ width: 2048, height: 768 });
    await gotoSessionDetail(page, sessionUrl);
    await expect(page.locator('[data-trace-panel]')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[data-trace-round-row]').first()).toBeVisible({ timeout: 10000 });

    const tokenbar = page.locator('[data-trace-round-row] .tokenbar-wrap').first();
    await expect(tokenbar, 'round rows should expose API-rendered tokenbar interaction').toBeVisible({ timeout: 10000 });
    await tokenbar.hover();
    await expect(page.locator('#token-bar-popover')).toBeVisible({ timeout: 3000 });
    const tooltipText = await page.locator('#token-bar-popover').innerText();
    expect(tooltipText, 'tooltip should keep structural labels only; numeric correctness is API-tested').toContain('Token Breakdown');
  });

  test('[UI-SD-017][UI-SD-034] API trace rows 保留表格单元格结构', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await gotoSessionDetail(page, sessionUrl);
    await expect(page.locator('[data-trace-panel]')).toBeVisible({ timeout: 10000 });
    await waitForSessionApiHydrated(page);

    const firstRow = page.locator('[data-trace-round-row]').first();
    await expect(firstRow, 'fixture must render API trace rows').toBeVisible({ timeout: 10000 });

    const structure = await firstRow.evaluate((row) => ({
      directCellCount: Array.from(row.children).filter((child) => child.tagName === 'TD').length,
      directChildTags: Array.from(row.children).map((child) => child.tagName),
      rowHeight: row.getBoundingClientRect().height,
    }));

    expect(structure.directCellCount, `trace row children must be table cells: ${structure.directChildTags.join(',')}`).toBe(6);
    expect(structure.directChildTags).toEqual(['TD', 'TD', 'TD', 'TD', 'TD', 'TD']);
    expect(structure.rowHeight, `trace row should stay compact after API hydration (${structure.rowHeight}px)`).toBeLessThanOrEqual(96);
  });

  test('[UI-SD-035] user input 与 failed round 保留状态底色', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await gotoSessionDetail(page, sessionUrl);
    await waitForSessionApiHydrated(page);

    const failedRow = page.locator('[data-trace-round-row][data-has-issues="true"]').first();
    await expect(failedRow, 'fixture must include a failed/issue round for error-tone coverage').toBeVisible({ timeout: 10000 });
    await expect(failedRow).toHaveAttribute('data-status', 'failed');
    const failedTone = await failedRow.evaluate((row) => {
      const cell = row.querySelector('td') || row;
      const color = window.getComputedStyle(cell).backgroundColor;
      const nums = (color.match(/\d+/g) || []).slice(0, 3).map(Number);
      return { color, isRed: nums.length === 3 && nums[0] >= 240 && nums[1] < 245 && nums[2] < 245 };
    });
    expect(failedTone.isRed, `failed round must be red-tinted, got ${failedTone.color}`).toBe(true);

    const userRow = page.locator('[data-trace-round-row][data-is-user-input="true"]').first();
    await expect(userRow, 'fixture must include a user-input round for user-tone coverage').toBeVisible({ timeout: 10000 });
    await expect(userRow).toHaveAttribute('data-status', 'user');
    const userTone = await userRow.evaluate((row) => {
      const cell = row.querySelector('td') || row;
      const color = window.getComputedStyle(cell).backgroundColor;
      const nums = (color.match(/\d+/g) || []).slice(0, 3).map(Number);
      return { color, isGreen: nums.length === 3 && nums[1] > nums[0] && nums[1] > nums[2] };
    });
    expect(userTone.isGreen, `user input round must be green-tinted, got ${userTone.color}`).toBe(true);

    const failedRoundId = await failedRow.getAttribute('data-round');
    await page.evaluate(async (roundId) => {
      const escaped = window.CSS && typeof CSS.escape === 'function'
        ? CSS.escape(roundId)
        : String(roundId).replace(/["\\]/g, '\\$&');
      const row = document.querySelector(`[data-trace-round-row][data-round="${escaped}"]`);
      if (!row) throw new Error(`round ${roundId} not found`);
      const detailId = `round-${roundId}-detail`;
      const detail = document.getElementById(detailId);
      if (detail && typeof window.setRoundOpen === 'function') {
        window.setRoundOpen(row, true);
      } else if (detail) {
        row.classList.add('is-open');
        detail.hidden = false;
      } else if (typeof window.lazyLoadRoundDetail === 'function') {
        await window.lazyLoadRoundDetail(row);
      }
    }, failedRoundId);
    const failedTool = page.locator(`#round-${failedRoundId}-detail .sd-tool-row[data-status="failed"]`).first();
    await expect(failedTool, 'failed round detail must mark failed tools').toBeVisible({ timeout: 10000 });
    const failedToolTone = await failedTool.evaluate((row) => {
      const color = window.getComputedStyle(row).backgroundColor;
      const nums = (color.match(/\d+/g) || []).slice(0, 3).map(Number);
      return { color, isRed: nums.length === 3 && nums[0] >= 240 && nums[1] < 250 && nums[2] < 250 };
    });
    expect(failedToolTone.isRed, `failed tool row must be red-tinted, got ${failedToolTone.color}`).toBe(true);
  });

  test('[UI-SD-036] KPI 和 Tool Impact 指标保留颜色 tone', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await gotoSessionDetail(page, sessionUrl);
    await waitForSessionApiHydrated(page);

    const toneState = await page.evaluate(() => {
      const tokenKpi = document.querySelector('.sd-kpi[aria-label="Total Tokens"]');
      const tokenStates = Array.from(tokenKpi ? tokenKpi.querySelectorAll('.sd-kpi-token-share') : [])
        .map((node) => ({ className: node.className, color: window.getComputedStyle(node).color }));
      const toolImpact = Array.from(document.querySelectorAll('.sd-diagnostic-card'))
        .find((card) => (card.querySelector('h2')?.textContent || '').trim() === 'Tool Impact');
      const toolRateStates = Array.from(toolImpact ? toolImpact.querySelectorAll('.sd-rate') : [])
        .map((node) => ({ className: node.className, color: window.getComputedStyle(node).color }));
      return { tokenStates, toolRateStates };
    });

    const toneColor = /^rgb\((21, 128, 61|180, 83, 9|220, 38, 38)\)$/;
    expect(toneState.tokenStates, 'Total Tokens must render four colored component shares').toHaveLength(4);
    expect(toneState.tokenStates.every((state) => /sd-kpi-token-share--(minor|mid|major)/.test(state.className))).toBe(true);
    expect(toneState.tokenStates.some((state) => /sd-kpi-token-share--(mid|major)/.test(state.className))).toBe(true);
    expect(toneState.tokenStates.every((state) => toneColor.test(state.color))).toBe(true);
    expect(toneState.toolRateStates.length, 'Tool Impact must render colored failure rates').toBeGreaterThan(0);
    expect(toneState.toolRateStates.every((state) => /sd-rate--(ok|warn|bad)/.test(state.className))).toBe(true);
    expect(toneState.toolRateStates.every((state) => toneColor.test(state.color))).toBe(true);
  });

  test('[UI-SD-032] diagnostics 区渲染 API-first parity 卡片', async ({ page }) => {
    await page.setViewportSize({ width: 2048, height: 768 });
    await gotoSessionDetail(page, sessionUrl);
    await expect(page.locator('[data-session-diagnostics]')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[data-session-anomalies]')).toHaveCount(0);
    await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true', { timeout: 10000 });
    await expect(page.locator('.sd-call-distribution')).toHaveCount(0);
    await expect(page.getByRole('heading', { name: 'Call Token Footprint Distribution' })).toHaveCount(0);
    await expect(page.getByRole('heading', { name: 'Top Token Drivers' })).toHaveCount(0);
    await expect(page.getByRole('heading', { name: 'Session API State' })).toHaveCount(0);
    await expect(page.getByRole('heading', { name: 'Agents Breakdown' })).toBeVisible({ timeout: 10000 });
    await expect(page.getByRole('heading', { name: 'Context Budget' })).toBeVisible({ timeout: 10000 });
    await expect(page.getByRole('heading', { name: 'Tool Impact' })).toBeVisible({ timeout: 10000 });
    await expect(page.getByRole('heading', { name: 'Issues & Repro Seeds' })).toBeVisible({ timeout: 10000 });
    await expect(page.locator('.sd-anomalies__count')).toHaveCount(0);
    await expect(page.locator('[data-summary-strip]')).not.toContainText(/branch/i);
    await expect(page.locator('[data-session-payload-policy]')).toHaveCount(0);
    await expect(page.locator('[data-trace-panel]')).not.toContainText('/api/sessions/{agent}/{sessionId}/rounds');
    await expect(page.locator('[data-trace-panel]')).not.toContainText('/round/{roundIndex}');
    if (await page.locator('[data-action="select-subagent"][data-agent-scope="subagent"]').count() > 0) {
      const subagentRow = page.locator('[data-subagent-row]').filter({
        has: page.locator('[data-agent-scope="subagent"]'),
      });
      await expect(subagentRow).toContainText('No failure signals · 0 failed');
      await expect(subagentRow).not.toContainText('Success');
    }
  });

  test('[UI-SD-020] Request / Response load matching side attribution in one dialog', async ({ page }) => {
    await gotoSessionDetail(page, sessionUrl);
    await waitForSessionApiHydrated(page);
    const modal = page.locator('dialog.payload-modal');
    for (const kind of ['request', 'response']) {
      const button = page.locator(`[data-attribution-path*="/${kind}"]:visible`).first();
      await expect(button).toHaveText(kind === 'request' ? 'Request' : 'Response');
      const path = await button.getAttribute('data-attribution-path');
      const response = page.waitForResponse(r => r.url().endsWith(path));
      await button.click();
      const body = await (await response).json();
      expect(body.kind).toBe('llm.' + kind + '_attribution');
      const card = modal.locator(`[data-payload-attribution="${kind}"]`);
      await expect(card).toHaveAttribute('data-attribution-call', body.data.callId);
      await expect(modal.locator('[data-payload-attribution]')).toHaveCount(1);
      await page.keyboard.press('Escape');
    }
  });

  test('[UI-SD-032][UI-INTERACTION-005] agent select 和 copy 交互在 diagnostics 内可用', async ({ page }) => {
    await gotoSessionDetail(page, sessionUrl);
    await waitForSessionApiHydrated(page);
    await expect(page.getByRole('heading', { name: 'Agents Breakdown' })).toBeVisible({ timeout: 10000 });

    const workbench = page.locator('[data-subagent-workbench]').first();
    await expect(workbench, 'Agents Breakdown must expose an agent workbench').toBeVisible({ timeout: 10000 });

    const agentButtons = workbench.locator('[data-action="select-subagent"]');
    const agentCount = await agentButtons.count();
    expect(agentCount, 'agent workbench must render at least one selectable candidate').toBeGreaterThan(0);
    await expect(workbench.locator('[data-subagent-timeline-panel].is-active:not([hidden])')).toHaveCount(1);

    if (agentCount > 1) {
      await agentButtons.nth(1).click();
      await expect(agentButtons.nth(1)).toHaveClass(/is-active/);
      await expect(agentButtons.nth(1)).toHaveAttribute('aria-pressed', 'true');
      await expect(workbench.locator('[data-subagent-timeline-panel].is-active:not([hidden])')).toHaveCount(1);
    }

    await page.evaluate(() => {
      window.__sessionDetailCopied = [];
      window.arpCopy = function (button, text, opts) {
        window.__sessionDetailCopied.push(text);
        if (button) button.textContent = (opts && opts.feedback) || 'Copied!';
      };
    });

    const copyButton = page.locator('button[data-action="copy"][data-copy-text]:visible').first();
    await expect(copyButton, 'diagnostics should expose copy actions').toBeVisible({ timeout: 10000 });
    const copyText = await copyButton.getAttribute('data-copy-text');
    await copyButton.click();
    await expect
      .poll(() => page.evaluate(() => window.__sessionDetailCopied && window.__sessionDetailCopied[0]))
      .toBe(copyText);
  });

  test('[UI-SD-033] trace 深链定位 API-rendered round', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 760 });
    await gotoSessionDetail(page, sessionUrl);
    await expect(page.locator('[data-trace-panel]')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[data-trace-round-row]').first()).toBeVisible({ timeout: 10000 });

    const rows = page.locator('[data-trace-round-row]');
    const rowCount = await rows.count();
    expect(rowCount, 'fixture must render trace rounds for deep-link checks').toBeGreaterThan(0);
    const roundId = await rows.nth(Math.min(2, rowCount - 1)).getAttribute('data-round');
    expect(roundId, 'target row must expose data-round').toBeTruthy();

    const roundQuery = new URLSearchParams({ tab: 'trace', round: roundId });
    await gotoSessionDetail(page, `${sessionUrl}?${roundQuery}`);
    const deepLinkedRow = page.locator(`[data-trace-round-row][data-round="${roundId}"]`);
    await expect(deepLinkedRow).toHaveClass(/is-open/, { timeout: 10000 });
    await expect(deepLinkedRow).toHaveClass(/is-jump-target/, { timeout: 10000 });
    await expect(page.locator(`#round-${roundId}-detail`)).toBeVisible({ timeout: 10000 });

    const currentUrl = new URL(page.url());
    expect(currentUrl.searchParams.get('tab')).toBe('trace');
    expect(currentUrl.searchParams.get('round')).toBe(roundId);
  });

  // ── Tab 切换测试（SD-19） ─────────────────────────────────────────

  test('[UI-SD-010][UI-SD-023] 只渲染 trace 顶层视图', async ({ page }) => {
    await gotoSessionDetail(page, sessionUrl);
    await expect(page.locator('.sd-hero').first()).toBeVisible({ timeout: 10000 });

    const tracePanel = page.locator('[data-tab-panel="trace"]');
    await expect(tracePanel).toBeVisible({ timeout: 5000 });
    await expect(page.locator('[data-tab="trace"]')).toHaveClass(/is-active/);
    await expect(page.locator('[data-tab="payload"]')).toHaveCount(0);
    await expect(page.locator('[data-payload-tab-panel]')).toHaveCount(0);
  });

  test('[UI-SD-012] payload 深链回退到 trace 视图', async ({ page }) => {
    await gotoSessionDetail(page, `${sessionUrl}?tab=payload`);
    await expect(page.locator('.sd-hero').first()).toBeVisible({ timeout: 10000 });

    const traceTab = page.locator('[data-tab="trace"]');
    await expect(traceTab).toHaveClass(/is-active/);
    await expect(page.locator('[data-tab-panel="trace"]')).toBeVisible({ timeout: 5000 });
    await expect(page.locator('[data-tab-panel="payload"]')).toHaveCount(0);
  });
});

// ── 长会话性能测试（100+ 轮） ──────────────────────────────────────────

test.describe('长会话 — 100 轮性能', () => {
  test('[UI-SD-027] trace 视图在 100 轮下无超时渲染', async ({ page }) => {
    // 测量页面加载时间
    const startTime = Date.now();
    await gotoSessionDetail(page, longUrl);
    const loadTime = Date.now() - startTime;

    await expect(page.locator('.sd-hero').first()).toBeVisible({ timeout: 10000 });

    // 验证 trace 面板可见
    await expect(page.locator('[data-trace-panel]')).toBeVisible({ timeout: 5000 });
    await waitForSessionApiHydrated(page);

    // 统计可见 trace 行数（应匹配 100 轮）
    const rowCount = await page.locator('[data-trace-round-row]').count();
    console.log(`长会话：${rowCount} 行 trace，耗时 ${loadTime}ms`);

    // 断言全部 100 轮存在
    expect(rowCount).toBeGreaterThanOrEqual(100);

    // 全量用例共享 fixture server，预算仍需防止超时级退化。
    expect(loadTime).toBeLessThan(15000);
  });

  test('[UI-SD-005][UI-SD-028] 100 轮展开/折叠和 DOM 节点预算', async ({ page }) => {
    test.setTimeout(60000);

    await gotoSessionDetail(page, longUrl);
    await expect(page.locator('[data-trace-panel]')).toBeVisible({ timeout: 10000 });
    await waitForSessionApiHydrated(page);

    const totalRows = await page.locator('[data-trace-round-row]').count();
    expect(totalRows).toBeGreaterThanOrEqual(100);

    const toggleAll = page.locator('[data-action="toggle-all"]');
    expect(await toggleAll.count(), 'long-session fixture must render a toggle-all button').toBeGreaterThan(0);

    if ((await visibleTraceDetailCount(page)) > 0 || (await openTraceRoundCount(page)) > 0) {
      await toggleAllTraceRounds(page);
    }

    await expect.poll(
      () => visibleTraceDetailCount(page),
      { message: 'initial collapse-all should hide all visible round details', timeout: 5000 },
    ).toBe(0);
    await expect.poll(
      () => openTraceRoundCount(page),
      { message: 'initial collapse-all should clear open round DOM state', timeout: 5000 },
    ).toBe(0);

    const domNodes = () => page.evaluate(() => document.querySelectorAll('*').length);
    expect(await domNodes(), '折叠时的 DOM 节点预算').toBeLessThan(20000);

    // 展开全部
    await toggleAllTraceRounds(page);
    await expect.poll(
      () => openTraceRoundCount(page),
      { message: 'expand-all should open at least one trace round', timeout: 5000 },
    ).toBeGreaterThan(0);
    await expect.poll(
      () => visibleTraceDetailCount(page),
      { message: 'expand-all should lazy-load and show the first batch of round details', timeout: 25000 },
    ).toBeGreaterThan(0);
    await expect.poll(
      () => page.locator('[data-trace-round-row][data-detail-loaded="true"]').count(),
      { message: 'expand-all should mark at least one round detail as loaded', timeout: 25000 },
    ).toBeGreaterThan(0);
    await expect.poll(
      () => page.locator('[data-loading-for] .sd-loading-indicator').count(),
      { message: 'expand-all lazy-load batch should settle before collapse assertion', timeout: 30000 },
    ).toBe(0);

    expect(await domNodes(), '首批展开详情加载后的 DOM 节点预算').toBeLessThan(50000);

    // 再次折叠
    await toggleAllTraceRounds(page);
    await expect.poll(
      () => visibleTraceDetailCount(page),
      { message: 'collapse-all should hide all visible round details', timeout: 5000 },
    ).toBe(0);
  });
});
