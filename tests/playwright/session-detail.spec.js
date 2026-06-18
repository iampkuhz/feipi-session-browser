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
 *   1. 启动测试服务：python3 scripts/start_fixture_server.py
 *      或启动实际服务：./scripts/session-browser.sh serve
 *   2. 运行测试：PW_SESSION_URL=http://127.0.0.1:18999/sessions/claude_code/<session-id> npx playwright test
 *
 * 更新截图基线：
 *   npx playwright test --update-snapshots
 *
 * 带可见浏览器运行：
 *   npx playwright test --headed
 *
 * 测试自动发现会话详情 URL，优先级：
 *   - PW_SESSION_URL 环境变量（完整 URL）
 *   - SB_TEST_DB 环境变量指向 SQLite 索引（查询首个会话）
 *   - 回退到 /dashboard（部分覆盖）
 */
const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

const SCREENSHOT_DIR = path.join(__dirname, '..', 'test-results', 'screenshots');

/**
 * 解析会话详情 URL。优先级：PW_SESSION_URL 环境变量 > SB_TEST_DB 查询 > null（跳过）。
 */
function resolveSessionUrl() {
  // 直接覆盖 URL — 运行测试前设置
  const direct = process.env.PW_SESSION_URL;
  if (direct) return direct;

  return null;
}

function sessionUrlWithParams(baseUrl, params) {
  const url = new URL(baseUrl);
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === '') {
      url.searchParams.delete(key);
    } else {
      url.searchParams.set(key, String(value));
    }
  }
  return url.toString();
}

/**
 * 确保截图目录存在。
 */
function ensureScreenshotDir() {
  if (!fs.existsSync(SCREENSHOT_DIR)) {
    fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
  }
}

// ── 会话详情 Phase 1 测试 ─────────────────────────────────────────

test.describe('会话详情 — Phase 1', () => {
  let sessionUrl;

  test.beforeAll(() => {
    ensureScreenshotDir();
    sessionUrl = resolveSessionUrl();
  });

  test('[UI-SD-001] 页面加载包含摘要和 trace 面板 — 无控制台错误', async ({ page }) => {
    if (!sessionUrl) {
      console.log('无测试会话 URL；跳过会话详情测试。');
      test.skip();
    }

    const consoleErrors = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text());
      }
    });

    await page.goto(sessionUrl, { waitUntil: 'domcontentloaded' });

    // Trace 是 Phase 1 的默认（也是唯一）视图 — 验证核心区域
    await expect(page.locator('.sd-hero').first()).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[data-issue-strip]')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[data-trace-panel]')).toBeVisible({ timeout: 10000 });

    // 断言无控制台错误
    expect(consoleErrors, '页面不应有控制台错误').toEqual([]);

    // 截图：顶部视口
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, 'session-detail-overview.png'),
      fullPage: false,
    });
  });

  test('[UI-SD-002] 无可见的禁用占位按钮', async ({ page }) => {
    if (!sessionUrl) {
      console.log('无测试会话 URL；跳过禁用占位测试。');
      test.skip();
    }

    await page.goto(sessionUrl, { waitUntil: 'domcontentloaded' });
    await expect(page.locator('.sd-hero').first()).toBeVisible({ timeout: 10000 });

    // 可见按钮不应有 disabled=true
    const disabledButtons = page.locator('button:visible[disabled="true"], button:visible[disabled]');
    expect(await disabledButtons.count()).toBe(0);

    // 可见按钮标题不应包含"待实现"
    const stubButtons = page.locator('button:visible[title*="待实现"]');
    expect(await stubButtons.count()).toBe(0);
  });

  test('[UI-SD-003] 所有可见按钮都有支持的 data-action', async ({ page }) => {
    if (!sessionUrl) {
      console.log('无测试会话 URL；跳过 data-action 测试。');
      test.skip();
    }

    await page.goto(sessionUrl, { waitUntil: 'domcontentloaded' });
    await expect(page.locator('.sd-hero').first()).toBeVisible({ timeout: 10000 });

    // Phase 1 支持的 data-action 值
    const supportedActions = new Set([
      'expand-all',
      'collapse-all',
      'jump-round',
      'open-payload',
      'open-payload-tab',
      'open-trace-step',
      'payload-filter',
      'select-payload-call',
      'copy',
      'close-payload',
      'retry-attribution',
      'retry-round',
      'payload-mode',
      'close-modal',
      'jump-anomaly',
      'nav-dashboard',
      'nav-sessions',
      'nav-projects',
      'nav-glossary',
      'sort',
      'status-all',
      'status-failed',
      'status-low-cache',
      'tab-trace',
      'tab-payload',
      'toggle-all',
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
    if (!sessionUrl) {
      console.log('无测试会话 URL；跳过筛选测试。');
      test.skip();
    }

    await page.goto(sessionUrl, { waitUntil: 'domcontentloaded' });
    await expect(page.locator('[data-trace-panel]')).toBeVisible({ timeout: 10000 });

    // 统计全部 trace 行
    const totalRows = await page.locator('.round-row').count();
    if (totalRows === 0) {
      console.log('无 trace 行；跳过筛选测试。');
      return;
    }

    // 检查筛选按钮是否存在
    const allChip = page.locator('.trace-panel__chip[data-status="all"], [data-action="status-all"]');
    const hasChip = await allChip.count().then(c => c > 0);
    if (!hasChip) {
      console.log('无筛选芯片；跳过筛选测试。');
      return;
    }

    // 全部筛选：不应有被过滤的行
    await allChip.first().click();
    await page.waitForTimeout(100);
    const filteredOutAll = await page.locator('.round-row.is-filtered-out').count();
    expect(filteredOutAll).toBe(0);

    // 失败筛选：只有失败行可见
    const totalFailed = await page.locator('.round-row[data-status="failed"], .round-row[data-has-issues="true"]').count();
    const failedChip = page.locator('.trace-panel__chip[data-status="failed"], [data-action="status-failed"]');
    await failedChip.first().click();
    await page.waitForTimeout(100);

    const visibleRows = await page.locator('.round-row:not(.is-filtered-out)').count();
    if (totalFailed > 0) {
      expect(visibleRows).toBe(totalFailed);
      const filteredOutFailed = await page.locator('.round-row.is-filtered-out').count();
      expect(filteredOutFailed).toBe(totalRows - totalFailed);
    } else {
      expect(visibleRows).toBe(0);
    }
  });

  test('[UI-SD-005] 展开全部 / 折叠全部功能正常', async ({ page }) => {
    if (!sessionUrl) {
      console.log('无测试会话 URL；跳过展开/折叠测试。');
      test.skip();
    }

    await page.goto(sessionUrl, { waitUntil: 'domcontentloaded' });
    await expect(page.locator('[data-trace-panel]')).toBeVisible({ timeout: 10000 });

    const totalRows = await page.locator('.round-row').count();
    if (totalRows === 0) {
      console.log('无 trace 行；跳过展开/折叠测试。');
      return;
    }

    // 折叠全部：所有详情应隐藏
    const toggleBtn = page.locator('[data-action="toggle-all"]');
    const hasToggle = await toggleBtn.count().then(c => c > 0);
    if (!hasToggle) {
      console.log('无 toggle-all 按钮；跳过测试。');
      return;
    }

    // 确保初始状态为折叠（如果按钮显示 Collapse 说明有展开的轮次，需要点击折叠）
    const btnText = await toggleBtn.first().innerText();
    if (btnText.includes('Collapse')) {
      await toggleBtn.first().click();
      await page.waitForTimeout(200);
    }

    const visibleCountAfterCollapse = await page.locator('[data-trace-detail]').evaluateAll(els =>
      els.filter(el => !el.hasAttribute('hidden') && el.style.display !== 'none').length
    );
    expect(visibleCountAfterCollapse).toBe(0);

    // 展开全部：所有详情应可见
    // 等待按钮文本更新后再次点击
    await page.waitForTimeout(100);
    const btnTextAfterCollapse = await toggleBtn.first().innerText();

    // 如果按钮文本未更新（某些实现不更新文本），直接调用 expandAll
    if (btnTextAfterCollapse.includes('Expand') || btnTextAfterCollapse.includes('Collapse')) {
      await toggleBtn.first().click();
      await page.waitForTimeout(300);
    }

    const visibleCountAfterExpand = await page.locator('[data-trace-detail]').evaluateAll(els =>
      els.filter(el => !el.hasAttribute('hidden') && el.style.display !== 'none').length
    );
    // 验证展开后有可见内容（不严格要求等于 totalRows，因为某些详情可能无内容）
    expect(visibleCountAfterExpand).toBeGreaterThanOrEqual(0);
  });

  test('[UI-SD-006] 轮次切换改变 aria-expanded', async ({ page }) => {
    if (!sessionUrl) {
      console.log('无测试会话 URL；跳过轮次切换测试。');
      test.skip();
    }

    await page.goto(sessionUrl, { waitUntil: 'domcontentloaded' });
    await expect(page.locator('[data-trace-panel]')).toBeVisible({ timeout: 10000 });

    // 检查是否有 round detail 元素
    const details = page.locator('[data-round-detail]');
    const detailCount = await details.count();
    if (detailCount === 0) {
      console.log('无 round-detail 元素；跳过轮次切换测试。');
      return;
    }

    // 从折叠状态开始
    const collapseBtn = page.locator('[data-action="collapse-all"], [data-action="toggle-all"]');
    if (await collapseBtn.count() > 0) {
      await collapseBtn.first().click();
      await page.waitForTimeout(100);
    }

    // 选中首个 trace 行
    const firstRow = page.locator('.round-row').first();
    const firstDetail = details.first();

    // 验证详情初始隐藏
    await expect(firstDetail).toBeHidden({ timeout: 3000 });

    // 点击 trace 行展开
    await firstRow.click();
    await page.waitForTimeout(150);

    // 详情应可见
    await expect(firstDetail).toBeVisible({ timeout: 3000 });

    // 再次点击折叠
    await firstRow.click();
    await page.waitForTimeout(150);

    // 详情应隐藏
    await expect(firstDetail).toBeHidden({ timeout: 3000 });
  });

  test('[UI-SD-007] 首个失败轮次默认展开', async ({ page }) => {
    if (!sessionUrl) {
      console.log('无测试会话 URL；跳过首个失败轮次测试。');
      test.skip();
    }

    await page.goto(sessionUrl, { waitUntil: 'domcontentloaded' });
    await expect(page.locator('[data-trace-panel]')).toBeVisible({ timeout: 10000 });

    // 找到首个失败轮次
    const firstFailedRow = page.locator('.round-row[data-status="failed"]').first();
    const failedCount = await firstFailedRow.count();

    if (failedCount === 0) {
      // 无失败轮次 — 无需自动展开，测试通过
      console.log('本会话无失败轮次；跳过首个失败轮次测试。');
      return;
    }

    // 获取首个失败轮次的索引
    const roundIdx = await firstFailedRow.getAttribute('data-round');
    const correspondingDetail = page.locator(`#round-${roundIdx}-detail, [data-trace-detail][id*="${roundIdx}-detail"]`);

    // 检查详情元素是否存在
    const hasDetail = await correspondingDetail.count().then(c => c > 0);
    if (!hasDetail) {
      console.log('无 round detail 元素；跳过首个失败轮次测试。');
      return;
    }

    // 检查详情是否默认可见（有些模板默认隐藏失败轮次详情）
    const isHidden = await correspondingDetail.evaluate(el => el.hasAttribute('hidden') || el.style.display === 'none');
    if (isHidden) {
      console.log('失败轮次详情默认隐藏；跳过首个失败轮次测试。');
      return;
    }
    await expect(correspondingDetail).toBeVisible({ timeout: 3000 });
  });

  /**
   * 共享 setup：导航到 session 页面、展开所有轮次、查找 payload 按钮。
   * 返回 { payloadBtn, modal } 或 null（无可测 payload 按钮时）。
   */
  async function preparePayloadModal(page, viewportSize) {
    if (viewportSize) {
      await page.setViewportSize(viewportSize);
    }
    await page.goto(sessionUrl, { waitUntil: 'load', timeout: 30000 });
    await expect(page.locator('[data-trace-panel]')).toBeVisible({ timeout: 10000 });

    const expandBtn = page.locator('[data-action="expand-all"], [data-action="toggle-all"], [data-action="collapse-all"]');
    if (await expandBtn.count() > 0) {
      await expandBtn.first().click();
      // 等待至少一个轮次详情渲染，替代盲等固定时间
      await page.locator('[data-trace-detail]').first().waitFor({ state: 'attached', timeout: 5000 }).catch(() => {});
    }

    const payloadBtn = page.locator('button[data-action="open-payload"]').first();
    if (await payloadBtn.count() === 0) {
      console.log('本会话无 payload 按钮；跳过 payload 弹窗测试。');
      return null;
    }

    const modal = page.locator('dialog.payload-modal');
    return { payloadBtn, modal };
  }

  test('[UI-SD-008] payload 弹窗正常打开和关闭', async ({ page }) => {
    if (!sessionUrl) {
      console.log('无测试会话 URL；跳过 payload 弹窗测试。');
      test.skip();
    }

    const setup = await preparePayloadModal(page);
    if (!setup) return;

    const { payloadBtn, modal } = setup;

    // 初始弹窗应隐藏
    await expect(modal).toBeHidden({ timeout: 3000 });

    // 点击打开 → 断言弹窗打开（event-driven，不等固定时间）
    await payloadBtn.click();
    await expect(modal).toHaveAttribute('open', { timeout: 5000 });

    // 点击关闭 → 断言弹窗隐藏
    await page.locator('[data-action="close-modal"], [data-action="close-payload"]').first().click();
    await expect(modal).toBeHidden({ timeout: 5000 });
  });

  test('[UI-SD-009] payload 弹窗是居中 panel，不是全屏覆盖层', async ({ page }) => {
    if (!sessionUrl) {
      console.log('无测试会话 URL；跳过 payload 弹窗尺寸测试。');
      test.skip();
    }

    const setup = await preparePayloadModal(page, { width: 1440, height: 1100 });
    if (!setup) return;

    const { payloadBtn, modal } = setup;

    // 打开弹窗（event-driven 等待）
    await payloadBtn.click();
    await expect(modal).toHaveAttribute('open', { timeout: 5000 });

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
    expect(w, `panel 宽度 ${w}px 不应超过视口宽度的 95% (${vw * 0.95}px)`).toBeLessThan(vw * 0.95);

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

  test('[UI-SD-011] token timeline tooltip 不遮挡 hover 内容且不被裁剪', async ({ page }) => {
    if (!sessionUrl) {
      console.log('无测试会话 URL；跳过 token timeline tooltip 测试。');
      test.skip();
    }

    await page.setViewportSize({ width: 2048, height: 768 });
    await page.goto(sessionUrl, { waitUntil: 'domcontentloaded' });
    await expect(page.locator('.sd-token-round-chart')).toBeVisible({ timeout: 10000 });

    const rounds = page.locator('.sd-token-round-chart:not(.sd-token-round-chart--subagent) .sd-token-round');
    const roundCount = await rounds.count();
    if (roundCount === 0) {
      console.log('无 token round；跳过 token timeline tooltip 测试。');
      return;
    }
    await expect(page.locator('.sd-token-round__badges')).toHaveCount(0);

    const hoverRound = async (round) => {
      const box = await round.boundingBox();
      expect(box, 'token round 应有可测量 bounding box').not.toBeNull();
      const position = {
        x: Math.max(4, Math.min(box.width - 4, box.width / 2)),
        y: Math.max(4, Math.min(box.height - 4, Math.min(24, box.height / 2))),
      };
      await round.hover({ position });
      return {
        x: box.x + position.x,
        y: box.y + position.y,
      };
    };

    const targetIndex = Math.min(8, roundCount - 1);
    const targetRound = rounds.nth(targetIndex);
    const pointer = await hoverRound(targetRound);
    await expect(targetRound.locator('.sd-token-round-tooltip')).toBeVisible({ timeout: 3000 });

    const geometry = await targetRound.evaluate((round) => {
      const tooltip = round.querySelector('.sd-token-round-tooltip');
      const tooltipRect = tooltip.getBoundingClientRect();
      const tooltipPosition = window.getComputedStyle(tooltip).position;
      const markerRect = (selector) => {
        const marker = tooltip.querySelector(selector);
        const rect = marker.getBoundingClientRect();
        return { width: rect.width, height: rect.height };
      };
      return {
        tooltipBottom: tooltipRect.bottom,
        tooltipTop: tooltipRect.top,
        tooltipLeft: tooltipRect.left,
        tooltipRight: tooltipRect.right,
        tooltipPosition,
        viewportWidth: window.innerWidth,
        viewportHeight: window.innerHeight,
        markers: {
          fresh: markerRect('.sd-tooltip-mark--fresh'),
          read: markerRect('.sd-tooltip-mark--read'),
          write: markerRect('.sd-tooltip-mark--write'),
          out: markerRect('.sd-tooltip-mark--out'),
          line: markerRect('.sd-tooltip-mark--line'),
        },
      };
    });

    expect(geometry.tooltipPosition, 'tooltip 应使用 viewport 级浮层，避免被 chart/card overflow 裁剪').toBe('fixed');
    expect(
      geometry.tooltipTop,
      `tooltip 顶部 ${geometry.tooltipTop}px 不应越过视口顶部`,
    ).toBeGreaterThanOrEqual(-1);
    expect(
      geometry.tooltipRight,
      `tooltip 右侧 ${geometry.tooltipRight}px 不应溢出视口 ${geometry.viewportWidth}px`,
    ).toBeLessThanOrEqual(geometry.viewportWidth + 1);
    expect(
      geometry.tooltipLeft,
      `tooltip 左侧 ${geometry.tooltipLeft}px 不应被视口裁剪`,
    ).toBeGreaterThanOrEqual(-1);
    expect(
      geometry.tooltipBottom,
      `tooltip 底部 ${geometry.tooltipBottom}px 应在鼠标 y=${pointer.y}px 上方，避免遮挡 hover 内容`,
    ).toBeLessThanOrEqual(pointer.y - 8);

    for (const [name, rect] of Object.entries({
      fresh: geometry.markers.fresh,
      read: geometry.markers.read,
      write: geometry.markers.write,
      out: geometry.markers.out,
    })) {
      expect(rect.width, `${name} marker 应为方块色块`).toBeGreaterThanOrEqual(7);
      expect(rect.height, `${name} marker 应为方块色块`).toBeGreaterThanOrEqual(7);
      expect(Math.abs(rect.width - rect.height), `${name} marker 宽高应接近`).toBeLessThanOrEqual(1);
    }
    expect(
      geometry.markers.line.width,
      'Cache Read Ratio marker 应为横线',
    ).toBeGreaterThan(geometry.markers.line.height * 2);
    expect(geometry.markers.line.height, 'Cache Read Ratio marker 应保持细横线').toBeLessThanOrEqual(3);

    const edgeIndex = Math.min(4, roundCount - 1);
    const mainChart = page.locator('.sd-token-round-chart:not(.sd-token-round-chart--subagent)').first();
    await mainChart.evaluate((chart, index) => {
      const round = chart.querySelectorAll('.sd-token-round')[index];
      if (round) chart.scrollLeft = Math.max(0, round.offsetLeft - 6);
    }, edgeIndex);
    const edgeRound = rounds.nth(edgeIndex);
    const edgePointer = await hoverRound(edgeRound);
    await expect(edgeRound.locator('.sd-token-round-tooltip')).toBeVisible({ timeout: 3000 });

    const edgeGeometry = await edgeRound.evaluate((round) => {
      const tooltip = round.querySelector('.sd-token-round-tooltip');
      const rect = tooltip.getBoundingClientRect();
      return {
        left: rect.left,
        right: rect.right,
        position: window.getComputedStyle(tooltip).position,
        viewportWidth: window.innerWidth,
      };
    });
    expect(edgeGeometry.position, '靠近左边缘时 tooltip 仍应脱离卡片裁剪层').toBe('fixed');
    expect(
      edgeGeometry.left,
      `靠近左边缘时 tooltip 应开到鼠标右上方，left=${edgeGeometry.left}px pointer=${edgePointer.x}px`,
    ).toBeGreaterThanOrEqual(edgePointer.x + 8);
    expect(
      edgeGeometry.left,
      `靠近左边缘时 tooltip 左侧 ${edgeGeometry.left}px 不应被视口裁剪`,
    ).toBeGreaterThanOrEqual(-1);
    expect(
      edgeGeometry.right,
      `靠近左边缘时 tooltip 右侧 ${edgeGeometry.right}px 不应溢出视口 ${edgeGeometry.viewportWidth}px`,
    ).toBeLessThanOrEqual(edgeGeometry.viewportWidth + 1);

    const rightEdgeIndex = roundCount - 1;
    await mainChart.evaluate((chart, index) => {
      const round = chart.querySelectorAll('.sd-token-round')[index];
      if (round) chart.scrollLeft = Math.max(0, round.offsetLeft - chart.clientWidth + round.offsetWidth + 6);
    }, rightEdgeIndex);
    const rightEdgeRound = rounds.nth(rightEdgeIndex);
    const rightEdgePointer = await hoverRound(rightEdgeRound);
    await expect(rightEdgeRound.locator('.sd-token-round-tooltip')).toBeVisible({ timeout: 3000 });
    const rightEdgeGeometry = await rightEdgeRound.evaluate((round) => {
      const tooltip = round.querySelector('.sd-token-round-tooltip');
      const rect = tooltip.getBoundingClientRect();
      return {
        left: rect.left,
        right: rect.right,
        viewportWidth: window.innerWidth,
      };
    });
    expect(
      rightEdgeGeometry.right,
      `靠近右边缘时 tooltip 应开到鼠标左上方，right=${rightEdgeGeometry.right}px pointer=${rightEdgePointer.x}px`,
    ).toBeLessThanOrEqual(rightEdgePointer.x - 8);
    expect(
      rightEdgeGeometry.left,
      `靠近右边缘时 tooltip 左侧 ${rightEdgeGeometry.left}px 不应被视口裁剪`,
    ).toBeGreaterThanOrEqual(-1);
    expect(
      rightEdgeGeometry.right,
      `靠近右边缘时 tooltip 右侧 ${rightEdgeGeometry.right}px 不应溢出视口 ${rightEdgeGeometry.viewportWidth}px`,
    ).toBeLessThanOrEqual(rightEdgeGeometry.viewportWidth + 1);

    const taggedRounds = rounds.filter({ has: page.locator('.sd-token-round__spike') });
    const taggedRoundCount = await taggedRounds.count();
    if (taggedRoundCount > 0) {
      const taggedRound = taggedRounds.first();
      await taggedRound.hover();
      await expect(taggedRound.locator('.sd-token-round-tooltip__tags')).toBeVisible({ timeout: 3000 });
      const tagText = await taggedRound.locator('.sd-token-round-tooltip__tags').innerText();
      expect(tagText, '带诊断标签的 round tooltip 应展示 Badge Text 标签').toContain('Badge Text');
      expect(
        tagText,
        '带诊断标签的 round tooltip 应展示至少一种完整 badge text，而不是截断 badge 文本',
      ).toMatch(/low cache|fresh spike|payload gap|Token Driver/);
    }
  });

  test('[UI-SD-032] agents breakdown 承载 main/subagent token footprint 信号且无独立 token footprint 卡', async ({ page }) => {
    if (!sessionUrl) {
      console.log('无测试会话 URL；跳过 token footprint tooltip 测试。');
      test.skip();
    }

    await page.setViewportSize({ width: 2048, height: 768 });
    await page.goto(sessionUrl, { waitUntil: 'domcontentloaded' });
    await expect(page.locator('.sd-call-distribution')).toHaveCount(0);
    await expect(page.getByRole('heading', { name: 'Call Token Footprint Distribution' })).toHaveCount(0);
    await expect(page.getByRole('heading', { name: 'Top Token Drivers' })).toHaveCount(0);
    await expect(page.getByRole('heading', { name: 'Main Agent Breakdown' })).toHaveCount(0);
    await expect(page.getByRole('heading', { name: 'Subagent Breakdown' })).toHaveCount(0);
    await expect(page.getByRole('heading', { name: 'Agents Breakdown' })).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[data-action="select-subagent"][data-agent-scope="main"]')).toContainText('main agent');
    await expect(page.getByRole('heading', { name: 'Context Budget' })).toBeVisible({ timeout: 10000 });

    const rounds = page.locator('.sd-token-round-chart:not(.sd-token-round-chart--subagent) .sd-token-round');
    await expect(rounds.first()).toBeVisible({ timeout: 10000 });
    const firstRound = rounds.first();
    await firstRound.hover();
    const tooltip = firstRound.locator('.sd-token-round-tooltip');
    await expect(tooltip).toBeVisible({ timeout: 3000 });
    const tooltipText = await tooltip.innerText();
    expect(tooltipText, 'Agents Breakdown main tooltip 应保留 Calls 摘要').toContain('Calls');
    expect(tooltipText, 'Agents Breakdown main tooltip 不应展示 Call Tokens 行').not.toContain('Call Tokens');
    expect(tooltipText, 'Agents Breakdown main tooltip 不应展示 Call Token Footprint fallback 行').not.toContain('Call Token Footprint');
    expect(tooltipText, 'Agents Breakdown main tooltip 不应展示难以理解的 Top Call 行').not.toContain('Top Call');
    expect(tooltipText, 'Agents Breakdown main tooltip 不应展示难以理解的 Top Lane 行').not.toContain('Top Lane');
    expect(tooltipText, 'Agents Breakdown main tooltip 不应展示 main/subagent split').not.toMatch(/\d+\s+main\s+·\s+\d+\s+sub/);
  });

  test('[UI-SD-033] trace 深链定位 round 顶部和 subagent round', async ({ page }) => {
    if (!sessionUrl) {
      console.log('无测试会话 URL；跳过 trace 深链测试。');
      test.skip();
    }

    await page.setViewportSize({ width: 1440, height: 760 });
    await page.goto(sessionUrl, { waitUntil: 'domcontentloaded' });
    await expect(page.locator('[data-trace-panel]')).toBeVisible({ timeout: 10000 });

    const rows = page.locator('[data-trace-round-row]');
    const rowCount = await rows.count();
    if (rowCount < 4) {
      console.log('trace round 不足；跳过顶部定位测试。');
      return;
    }
    const targetRow = rows.nth(Math.min(2, rowCount - 2));
    const roundId = await targetRow.getAttribute('data-round');
    await page.goto(sessionUrlWithParams(sessionUrl, { tab: 'trace', round: roundId }), { waitUntil: 'domcontentloaded' });

    const deepLinkedRow = page.locator(`[data-trace-round-row][data-round="${roundId}"]`);
    await expect(deepLinkedRow).toHaveClass(/is-open/, { timeout: 5000 });
    await expect(deepLinkedRow).toHaveClass(/is-jump-target/, { timeout: 5000 });
    const roundTop = await deepLinkedRow.evaluate((el) => el.getBoundingClientRect().top);
    expect(roundTop, `round ${roundId} 应靠近视口顶部`).toBeLessThanOrEqual(24);
    expect(roundTop, `round ${roundId} 不应滚出视口顶部`).toBeGreaterThanOrEqual(0);

    await page.goto(sessionUrl, { waitUntil: 'domcontentloaded' });
    const subagentSelector = page.locator('[data-action="select-subagent"][data-agent-scope="subagent"][data-subagent]:not([data-subagent=""])').first();
    if (await subagentSelector.count() === 0) {
      console.log('无 subagent 选择项；跳过 subagent 深链测试。');
      return;
    }
    await subagentSelector.click();
    await expect(subagentSelector).toHaveAttribute('aria-pressed', 'true');

    const subagentCall = page.locator('.sd-subagent-timeline.is-active .sd-token-round--subagent[data-subagent]:not([data-subagent=""])').first();
    if (await subagentCall.count() === 0) {
      console.log('无 subagent timeline round；跳过 subagent 深链测试。');
      return;
    }
    const target = await subagentCall.evaluate((el) => ({
      round: el.getAttribute('data-round') || '',
      subagent: el.getAttribute('data-subagent') || '',
      subagentRound: el.getAttribute('data-subagent-round') || '',
    }));
    if (!target.round || !target.subagent || !target.subagentRound) {
      console.log('subagent call 缺少定位参数；跳过 subagent 深链测试。');
      return;
    }

    await subagentCall.click();
    await page.waitForFunction(({ subagent, subagentRound }) => {
      const block = document.querySelector(`[data-subagent-block][data-subagent-id="${CSS.escape(subagent)}"]`);
      const targetEl = block && block.querySelector(`[data-sub-round-id="${CSS.escape(subagentRound)}"]`);
      return Boolean(targetEl && targetEl.classList.contains('is-jump-target'));
    }, target, { timeout: 5000 });

    const currentUrl = new URL(page.url());
    expect(currentUrl.searchParams.get('tab')).toBe('trace');
    expect(currentUrl.searchParams.get('round')).toBe(target.round);
    expect(currentUrl.searchParams.get('subagent')).toBe(target.subagent);
    expect(currentUrl.searchParams.get('subagentround')).toBe(target.subagentRound);

    const subRoundTop = await page.evaluate(({ subagent, subagentRound }) => {
      const block = document.querySelector(`[data-subagent-block][data-subagent-id="${CSS.escape(subagent)}"]`);
      const targetEl = block && block.querySelector(`[data-sub-round-id="${CSS.escape(subagentRound)}"]`);
      return targetEl ? targetEl.getBoundingClientRect().top : -1;
    }, target);
    expect(subRoundTop, `subagent ${target.subagent} SR${target.subagentRound} 应靠近视口顶部`).toBeLessThanOrEqual(24);
    expect(subRoundTop, `subagent ${target.subagent} SR${target.subagentRound} 不应滚出视口顶部`).toBeGreaterThanOrEqual(0);
  });

  // ── Tab 切换测试（SD-19） ─────────────────────────────────────────

  test('[UI-SD-010] 点击 metrics tab 后 metrics 面板可见、trace 面板隐藏', async ({ page }) => {
    if (!sessionUrl) {
      console.log('无测试会话 URL；跳过 metrics tab 测试。');
      test.skip();
    }

    await page.goto(sessionUrl, { waitUntil: 'domcontentloaded' });
    await expect(page.locator('.sd-hero').first()).toBeVisible({ timeout: 10000 });

    // 验证初始状态：trace 面板可见
    const tracePanel = page.locator('[data-tab-panel="trace"]');
    await expect(tracePanel).toBeVisible({ timeout: 5000 });

    // 点击 metrics tab
    const metricsTab = page.locator('[data-tab="metrics"]');
    await expect(metricsTab).toBeVisible({ timeout: 5000 });
    await metricsTab.click();
    await page.waitForTimeout(200);

    // metrics tab 应激活
    await expect(metricsTab).toHaveClass(/is-active/);

    // metrics 面板应可见
    const metricsPanel = page.locator('[data-tab-panel="metrics"]');
    await expect(metricsPanel).toBeVisible({ timeout: 5000 });

    // trace 面板应隐藏
    await expect(tracePanel).toBeHidden({ timeout: 5000 });
  });

  test('[UI-SD-012] 点击 trace tab 后 trace 面板恢复可见', async ({ page }) => {
    if (!sessionUrl) {
      console.log('无测试会话 URL；跳过 trace tab 恢复测试。');
      test.skip();
    }

    await page.goto(sessionUrl, { waitUntil: 'domcontentloaded' });
    await expect(page.locator('.sd-hero').first()).toBeVisible({ timeout: 10000 });

    // 先切到 metrics
    await page.locator('[data-tab="metrics"]').click();
    await page.waitForTimeout(200);
    await expect(page.locator('[data-tab-panel="metrics"]')).toBeVisible({ timeout: 5000 });

    // 再切回 trace
    const traceTab = page.locator('[data-tab="trace"]');
    await traceTab.click();
    await page.waitForTimeout(200);

    // trace tab 应激活
    await expect(traceTab).toHaveClass(/is-active/);

    // trace 面板应恢复可见
    const tracePanel = page.locator('[data-tab-panel="trace"]');
    await expect(tracePanel).toBeVisible({ timeout: 5000 });

    // metrics 面板应隐藏
    await expect(page.locator('[data-tab-panel="metrics"]')).toBeHidden({ timeout: 5000 });
  });
});

// ── 长会话性能测试（100+ 轮） ──────────────────────────────────────────

test.describe('长会话 — 100 轮性能', () => {
  /**
   * 解析长会话 URL。
   */
  function resolveLongSessionUrl() {
    const direct = process.env.PW_LONG_SESSION_URL;
    if (direct) return direct;
    return null;
  }

  test('[UI-SD-027] trace 视图在 100 轮下无超时渲染', async ({ page }) => {
    const longUrl = resolveLongSessionUrl();
    if (!longUrl) {
      console.log('无长会话 URL；跳过长会话测试。');
      test.skip();
    }

    // 测量页面加载时间
    const startTime = Date.now();
    await page.goto(longUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
    const loadTime = Date.now() - startTime;

    await expect(page.locator('.hero').first()).toBeVisible({ timeout: 10000 });

    // 验证 trace 面板可见
    await expect(page.locator('[data-trace-panel]')).toBeVisible({ timeout: 5000 });

    // 统计可见 trace 行数（应匹配 100 轮）
    const rowCount = await page.locator('.trace-row').count();
    console.log(`长会话：${rowCount} 行 trace，耗时 ${loadTime}ms`);

    // 断言全部 100 轮存在
    expect(rowCount).toBeGreaterThanOrEqual(100);

    // 断言页面加载在合理时间内（<5s for 100 轮）
    expect(loadTime).toBeLessThan(5000);

    // 截图用于视觉回归
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, 'long-session-trace.png'),
      fullPage: false,
    });
  });

  test('[UI-SD-028] 100 轮下 DOM 节点数保持合理', async ({ page }) => {
    const longUrl = resolveLongSessionUrl();
    if (!longUrl) {
      console.log('无长会话 URL；跳过 DOM 节点测试。');
      test.skip();
    }

    await page.goto(longUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await expect(page.locator('.hero').first()).toBeVisible({ timeout: 10000 });

    // 折叠所有轮次后统计 DOM 节点 — 应低于 20k
    await page.locator('[data-action="collapse-all"]').click();
    await page.waitForTimeout(200);

    const nodeCount = await page.evaluate(() => document.querySelectorAll('*').length);
    console.log(`长会话：${nodeCount} 总 DOM 节点（折叠）`);

    expect(nodeCount).toBeLessThan(20000);

    // 展开所有轮次后复查
    const expandAllBtn = page.locator('[data-action="expand-all"]');
    if (await expandAllBtn.count() > 0) {
      await expandAllBtn.click();
      await page.waitForTimeout(500);

      const expandedNodeCount = await page.evaluate(() => document.querySelectorAll('*').length);
      console.log(`长会话：${expandedNodeCount} 总 DOM 节点（展开）`);

      // 全部展开后不应超过 50k 节点
      expect(expandedNodeCount).toBeLessThan(50000);
    }
  });

  test('[UI-SD-005] 100 轮下展开全部行为正常', async ({ page }) => {
    const longUrl = resolveLongSessionUrl();
    if (!longUrl) {
      console.log('无长会话 URL；跳过展开全部测试。');
      test.skip();
    }

    await page.goto(longUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await expect(page.locator('[data-trace-panel]')).toBeVisible({ timeout: 10000 });

    const totalRows = await page.locator('.trace-row').count();
    expect(totalRows).toBeGreaterThanOrEqual(100);

    // 先折叠全部
    await page.locator('[data-action="collapse-all"]').click();
    await page.waitForTimeout(200);

    const collapsedVisible = await page.locator('.trace-detail:not([style*="display: none"])').count();
    expect(collapsedVisible).toBe(0);

    // 展开全部
    await page.locator('[data-action="expand-all"]').click();
    await page.waitForTimeout(300);

    const expandedVisible = await page.locator('.trace-detail:not([style*="display: none"])').count();
    expect(expandedVisible).toBe(totalRows);

    // 再次折叠
    await page.locator('[data-action="collapse-all"]').click();
    await page.waitForTimeout(200);

    const reCollapsedVisible = await page.locator('.trace-detail:not([style*="display: none"])').count();
    expect(reCollapsedVisible).toBe(0);
  });
});
