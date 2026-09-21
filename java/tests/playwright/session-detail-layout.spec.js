/**
 * session-detail-layout.spec.js — 会话详情 Phase 1 外壳布局门禁
 *
 * 验证会话详情页面不会受到 body.hide-left / body.focus / body.hide-right
 * 级联冲突的影响，导致 .main 被挤入 0px 宽的网格列。
 *
 * 需要服务运行在 BASE_URL（默认 http://127.0.0.1:18999）。
 */
const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');
const { runPlaywrightRoot } = require('./runtime-paths');

const ATTRIBUTION_FIXTURE = {
  kind: 'llm.response_attribution',
  data: {
    callId: 'layout-fixture-call-001',
    callKey: 'C1',
    model: 'layout-fixture-model',
    scope: 'main',
    timestamp: '2026-09-21T10:00:00Z',
    totalTokens: 210,
    freshInputTokens: 120,
    outputTokens: 90,
    cacheReadTokens: 30,
    cacheWriteTokens: 10,
    requestToolResultCount: 3,
    responseToolCallCount: 2,
  },
};

test.describe('会话详情 Phase 1 外壳布局', () => {
  test('[UI-SD-013][UI-SD-018][UI-VISUAL-003] 1440px 视口下外壳布局正确', async ({ page }) => {
    // 使用质量门禁指定的 1440x1100 视口
    await page.setViewportSize({ width: 1440, height: 1100 });

    // 先尝试已知会话 URL，回退到会话列表
    const knownUrl = '/sessions/claude_code/hifi-viz-session-001';
    const sessionsListUrl = '/sessions';

    let detailUrl = null;

    // 尝试已知会话
    const resp = await page.goto(knownUrl, { waitUntil: 'domcontentloaded', timeout: 10000 }).catch(() => null);
    if (resp && resp.ok()) {
      // 检查是否拿到真实会话页面（非 404 重定向）
      const hero = await page.locator('.page-head').first().isVisible({ timeout: 5000 }).catch(() => false);
      if (hero) {
        detailUrl = knownUrl;
      }
    }

    // 回退：从 /sessions 列表提取第一个会话链接
    if (!detailUrl) {
      await page.goto(sessionsListUrl, { waitUntil: 'domcontentloaded', timeout: 10000 });
      await expect(page.locator('.page-head').first()).toBeVisible({ timeout: 10000 });

      // 找到第一个会话详情链接
      const firstLink = await page.locator('a[href*="/sessions/"]').first();
      const href = await firstLink.getAttribute('href');
      if (!href) {
        throw new Error('在 /sessions 页面上未找到会话链接');
      }
      detailUrl = href;
    }

    // 导航到会话详情
    await page.goto(detailUrl, { waitUntil: 'domcontentloaded', timeout: 15000 });
    await expect(page.locator('.session-detail-page').first()).toBeVisible({ timeout: 10000 });

    // 评估布局指标
    const result = await page.evaluate(() => {
      const rect = (selector) => {
        const el = document.querySelector(selector);
        if (!el) return null;
        const r = el.getBoundingClientRect();
        return {
          left: r.left,
          right: r.right,
          width: r.width,
          top: r.top,
          bottom: r.bottom,
          height: r.height,
        };
      };

      const shell = document.querySelector('.shell');
      const main = document.querySelector('.main');
      const title = document.querySelector('.session-detail-page .page-head h1, .session-detail-page h1');
      const kpis = document.querySelector('.session-detail-page .sd-kpis, .session-detail-page .kpis');

      const titleRect = title ? title.getBoundingClientRect() : null;
      const kpisRect = kpis ? kpis.getBoundingClientRect() : null;

      return {
        viewport: `${window.innerWidth}x${window.innerHeight}`,
        scrollOk: document.documentElement.scrollWidth <= window.innerWidth + 2,
        scrollWidth: document.documentElement.scrollWidth,
        shellGridTemplateColumns: shell ? getComputedStyle(shell).gridTemplateColumns : null,
        shellClasses: shell ? shell.className : null,
        bodyClasses: document.body.className,
        mainGridColumn: main
          ? `${getComputedStyle(main).gridColumnStart}/${getComputedStyle(main).gridColumnEnd}`
          : null,
        main: rect('.main'),
        detail: rect('.session-detail-page'),
        hero: rect('.session-detail-page .main'),
        title: rect('.session-detail-page .page-head h1, .session-detail-page h1'),
        kpis: rect('.session-detail-page .sd-kpis, .session-detail-page .kpis'),
        titleBeforeKpis: titleRect && kpisRect
          ? titleRect.bottom <= kpisRect.top + 4
          : false,
      };
    });

    // 截图
    const tmpDir = path.join(runPlaywrightRoot, 'layout');
    if (!fs.existsSync(tmpDir)) fs.mkdirSync(tmpDir, { recursive: true });
    const screenshotPath = path.join(tmpDir, 'session-detail-layout-1440.png');
    await page.screenshot({ path: screenshotPath, fullPage: false });

    // 写入结果 JSON
    const resultJson = {
      viewport: result.viewport,
      scrollOk: result.scrollOk,
      shellGridTemplateColumns: result.shellGridTemplateColumns,
      mainWidth: result.main ? result.main.width : 0,
      detailWidth: result.detail ? result.detail.width : 0,
      heroWidth: result.hero ? result.hero.width : 0,
      titleBeforeKpis: result.titleBeforeKpis,
      titleHeight: result.title ? result.title.height : 0,
      bodyClasses: result.bodyClasses,
      shellClasses: result.shellClasses,
      mainGridColumn: result.mainGridColumn,
      screenshot: screenshotPath,
    };
    const resultJsonPath = path.join(tmpDir, 'session-detail-layout-result.json');
    fs.writeFileSync(resultJsonPath, JSON.stringify(resultJson, null, 2));

    // 断言布局正确性 — 失败时附带完整 JSON
    const resultStr = JSON.stringify(result, null, 2);

    expect(result.scrollOk, `不应出现水平滚动。结果：${resultStr}`).toBe(true);

    expect(result.shellGridTemplateColumns, `外壳网格首列不能为 0px。结果：${resultStr}`).not.toMatch(/^0px\s+/);

    expect(result.main.width, `.main 宽度不足。结果：${resultStr}`).toBeGreaterThan(1200);

    expect(result.detail.width, `.session-detail-page 宽度不足。结果：${resultStr}`).toBeGreaterThan(1100);

    expect(result.hero.width, `.hero 宽度不足。结果：${resultStr}`).toBeGreaterThan(900);

    expect(result.titleBeforeKpis, `标题必须出现在 KPI 上方。结果：${resultStr}`).toBe(true);

    expect(result.title.height, `标题高度不得超过 180px。结果：${resultStr}`).toBeLessThanOrEqual(180);
  });
});

test.describe('Attribution 弹框布局', () => {
  async function openHydratedSession(page) {
    const response = await page.goto('/sessions/claude_code/hifi-viz-session-001', {
      waitUntil: 'domcontentloaded',
      timeout: 30_000,
    });
    expect(response && response.ok(), 'fixture URL must return HTTP success').toBe(true);
    await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true', { timeout: 10_000 });
    await expect(page.locator('[data-trace-round-row]').first()).toBeVisible({ timeout: 10_000 });
  }

  async function installAttributionRoute(page) {
    await page.route(/\/api\/sessions\/[^/]+\/[^/]+\/attribution\/\d+\/\d+\/(request|response)$/, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(ATTRIBUTION_FIXTURE),
      });
    });
  }

  async function openAttributionModal(page) {
    const button = page
      .locator('button[data-action="open-payload"][data-payload-kind="llm.response_attribution"]:visible')
      .first();
    await expect(button, 'response attribution trigger must be visible').toBeVisible({ timeout: 10_000 });
    await button.click();
    const modal = page.locator('dialog.payload-modal');
    await expect.poll(
      () => modal.evaluate((dialog) => dialog.open).catch(() => false),
      { message: 'attribution modal must open', timeout: 5_000 },
    ).toBe(true);
    await expect(modal, 'attribution API must complete successfully').toHaveAttribute(
      'data-attribution-state',
      'success',
      { timeout: 10_000 },
    );
    return modal;
  }

  test('[UI-SD-LAYOUT-001] 桌面宽屏 attribution 弹框为两列卡片布局', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await installAttributionRoute(page);
    await openHydratedSession(page);
    await openAttributionModal(page);

    const layout = await page.evaluate(() => {
      const topgrids = document.querySelectorAll('.sd-attribution-topgrid');
      if (topgrids.length === 0) return { error: 'no topgrid found' };
      const firstGrid = topgrids[0];
      const style = getComputedStyle(firstGrid);
      const cards = firstGrid.querySelectorAll('.sd-attribution-topcard');
      const cardRects = Array.from(cards).map((c) => {
        const r = c.getBoundingClientRect();
        return { top: Math.round(r.top), left: Math.round(r.left), width: Math.round(r.width) };
      });
      const hasTwoColumns = cards.length >= 2 && cardRects[0].top === cardRects[1].top && cardRects[0].left < cardRects[1].left;
      return {
        gridColumns: style.gridTemplateColumns,
        cardCount: cards.length,
        cardRects,
        hasTwoColumns,
        topgridCount: topgrids.length,
      };
    });

    const layoutStr = JSON.stringify(layout, null, 2);
    expect(layout.cardCount, `桌面首行应有至少 2 张卡片。结果：${layoutStr}`).toBeGreaterThanOrEqual(2);
    expect(layout.hasTwoColumns, `桌面卡片应水平排列。结果：${layoutStr}`).toBe(true);
  });

  test('[UI-SD-LAYOUT-002] 窄屏 attribution 弹框回退单列', async ({ page }) => {
    await page.setViewportSize({ width: 800, height: 600 });
    await installAttributionRoute(page);
    await openHydratedSession(page);
    await openAttributionModal(page);

    const layout = await page.evaluate(() => {
      const topgrids = document.querySelectorAll('.sd-attribution-topgrid');
      if (topgrids.length === 0) return { error: 'no topgrid found' };
      const firstGrid = topgrids[0];
      const style = getComputedStyle(firstGrid);
      const cards = firstGrid.querySelectorAll('.sd-attribution-topcard');
      const cardRects = Array.from(cards).map((c) => {
        const r = c.getBoundingClientRect();
        return { top: Math.round(r.top), left: Math.round(r.left), width: Math.round(r.width) };
      });
      const isSingleColumn = cards.length < 2 || cardRects.every((r, i) => i === 0 || r.top > cardRects[i - 1].top);
      return {
        gridColumns: style.gridTemplateColumns,
        cardCount: cards.length,
        cardRects,
        isSingleColumn,
      };
    });

    const layoutStr = JSON.stringify(layout, null, 2);
    expect(layout.isSingleColumn, `窄屏卡片应垂直排列。结果：${layoutStr}`).toBe(true);
  });

  for (const width of [1440, 390]) {
  test(`[UI-SD-LAYOUT-003] 工具计数 label 与 value bounding boxes 不相交 (${width}px)`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await installAttributionRoute(page);
    await openHydratedSession(page);
    await openAttributionModal(page);

    const kvGeometry = await page.evaluate(() => {
      const toolCountsCard = document.querySelector('[data-attribution-card="tool-counts"]');
      if (!toolCountsCard) return { error: 'tool-counts card not found' };
      const kvRows = toolCountsCard.querySelectorAll('.sd-kv');
      return Array.from(kvRows).map((kv) => {
        const spans = kv.querySelectorAll(':scope > span');
        if (spans.length < 2) return { error: 'missing spans', kv: kv.getAttribute('data-attribution-kv') };
        const labelRect = spans[0].getBoundingClientRect();
        const valueRect = spans[1].getBoundingClientRect();
        return {
          kv: kv.getAttribute('data-attribution-kv'),
          label: { left: Math.round(labelRect.left), right: Math.round(labelRect.right), width: Math.round(labelRect.width) },
          value: { left: Math.round(valueRect.left), right: Math.round(valueRect.right), width: Math.round(valueRect.width) },
          overlap: labelRect.right > valueRect.left,
          gap: Math.round(valueRect.left - labelRect.right),
        };
      });
    });

    const geomStr = JSON.stringify(kvGeometry, null, 2);
    if (kvGeometry.error) {
      throw new Error(`工具计数卡片未找到。结果：${geomStr}`);
    }
    expect(kvGeometry.length, `工具计数应有至少 2 行。结果：${geomStr}`).toBeGreaterThanOrEqual(2);
    for (const row of kvGeometry) {
      expect(row.error).toBeUndefined();
      expect(row.label.left).toBeGreaterThanOrEqual(0);
      expect(row.value.width).toBeGreaterThan(0);
      expect(row.value.right).toBeLessThanOrEqual(width);
      expect(row.overlap, `${row.kv} label 与 value 不得重叠。结果：${geomStr}`).toBe(false);
      expect(row.gap, `${row.kv} label 与 value 间距应 >= 0。结果：${geomStr}`).toBeGreaterThanOrEqual(0);
    }
    expect(await page.locator('dialog .sd-modal-panel').evaluate((panel) => panel.scrollLeft)).toBe(0);
  });
  }
});
