/**
 * session-detail-layout.spec.js — 会话详情 Phase 1 外壳布局门禁
 *
 * 验证会话详情页面不会受到 body.hide-left / body.focus / body.hide-right
 * 级联冲突的影响，导致 .main 被挤入 0px 宽的网格列。
 *
 * 使用 Playwright 管理的合成会话服务。
 */
const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');
const { runPlaywrightRoot } = require('./runtime-paths');

test.describe('会话详情 Phase 1 外壳布局', () => {
  test('[UI-SD-013][UI-SD-018][UI-VISUAL-003] 1440px 视口下外壳布局正确', async ({ page }) => {
    // 使用质量门禁指定的 1440x1100 视口
    await page.setViewportSize({ width: 1440, height: 1100 });

    await page.goto('/sessions/claude_code/hifi-viz-session-001');
    await expect(page.locator('.session-detail-page')).toBeVisible();
    await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
    await expect(page.getByRole('tablist')).toHaveCount(0);
    const trace = page.locator('section[data-trace-panel]');
    await expect(trace.getByRole('heading', { name: '执行过程', exact: true })).toBeVisible();
    await expect(trace.locator('[data-trace-list]')).toBeVisible();
    await expect(trace.locator('[data-round-sources], [data-payload-index]')).toHaveCount(0);
    const analysis = page.locator('#session-analysis');
    await expect(analysis.locator('[data-token-composition]')).toBeVisible();
    await expect(analysis.locator('[data-session-diagnostics]')).toBeVisible();
    const metrics = page.locator('[data-session-metrics-shell]');
    const cards = metrics.locator(':scope > .sd-kpi');
    await expect(cards.locator('.sd-kpi__label')).toHaveText(['Token 总量', '输入缓存命中率', '本地归一化记录', '任务活动时长']);
    for (const card of await cards.all()) {
      await expect(card.locator('.sd-kpi__value')).toBeVisible();
      await expect(card.locator('.sd-kpi__value')).not.toHaveText('Loading…');
      const values = card.locator('.sd-kpi__subgrid b');
      expect(await values.count()).toBeGreaterThanOrEqual(2);
      for (const value of await values.all()) {
        await expect(value).toBeVisible();
        await expect(value).not.toHaveText(/Loading|^$/);
      }
    }
    await expect(metrics.locator('details, summary, button, [role="button"]')).toHaveCount(0);

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

test.describe('正文弹框内的归因布局', () => {
  async function openAttribution(page, width) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/sessions/claude_code/hifi-viz-session-001');
    await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
    await page.locator('[data-attribution-path*="/response"]:visible').first().click();
    const modal = page.locator('dialog.payload-modal');
    const disclosure = modal.locator('[data-payload-attribution="response"]');
    await expect(modal).toBeVisible();
    await expect(disclosure).toHaveAttribute('data-attribution-call', /.+/);
    await expect(disclosure.locator('.sd-kv').first()).toBeVisible();
    return { modal, disclosure };
  }

  test('[UI-SD-LAYOUT-001] 输出用量紧凑排列，正文占满同一弹框', async ({ page }) => {
    const { modal, disclosure } = await openAttribution(page, 1440);
    const summary = disclosure.locator(':scope > .sd-reading-usage-heading');
    const grid = disclosure.locator('.sd-attribution-summary-grid');
    await expect(summary).toHaveText(/^输出用量明细 · 来源报告 [\d,]+ tokens · 推理等非正文用量未单列$/);
    await expect(grid.locator('.sd-kv > span:first-child')).toHaveText(['调用', '已记录工具指令']);
    await expect(grid.locator('.sd-reading-usage-part > span:first-child')).toHaveText('输出');
    await expect(grid.locator('.sd-reading-usage-band')).toHaveCount(0);
    const reading = modal.locator('.sd-content-block').first();
    await expect(reading).toBeVisible();
    const readingBox = await reading.boundingBox();
    const meterBox = await disclosure.boundingBox();
    const summaryBox = await summary.boundingBox();
    const composition = modal.locator('.sd-reading-composition');
    const visibleNoteBox = await composition.boundingBox();
    const panelBox = await modal.locator('.sd-modal-panel').boundingBox();
    expect(visibleNoteBox.y + visibleNoteBox.height).toBeLessThanOrEqual(summaryBox.y);
    const usageGroupBox = await modal.locator('.sd-reading-panel').boundingBox();
    expect(usageGroupBox.x).toBeCloseTo(readingBox.x, 0);
    expect(usageGroupBox.width).toBeCloseTo(readingBox.width, 0);
    expect(visibleNoteBox.x).toBeCloseTo(meterBox.x, 0);
    expect(visibleNoteBox.width).toBeCloseTo(meterBox.width, 0);
    expect(meterBox.y + meterBox.height).toBeLessThanOrEqual(readingBox.y);
    expect(summaryBox.height).toBeLessThanOrEqual(32);
    expect(usageGroupBox.y + usageGroupBox.height).toBeLessThanOrEqual(readingBox.y);
    expect(panelBox.width - readingBox.width).toBeLessThanOrEqual(44);
    await expect(grid).toBeVisible();
    await expect(disclosure.locator('summary')).toHaveCount(0);
  });

  for (const width of [1440, 1024]) {
    test(`[UI-SD-LAYOUT-003] 已记录工具指令的标签和值不重叠 (${width}px)`, async ({ page }) => {
      const { modal, disclosure } = await openAttribution(page, width);
      const toolCount = disclosure.locator('.sd-kv').filter({ has: page.getByText('已记录工具指令', { exact: true }) });
      await expect(toolCount).toBeVisible();
      await expect(toolCount.locator('span').last()).toHaveText(/^\d+$/);
      const [label, value] = await toolCount.locator('span').evaluateAll(spans => spans.map(span => {
        const { left, right, top, bottom } = span.getBoundingClientRect();
        return { left, right, top, bottom };
      }));
      expect(value.right).toBeLessThanOrEqual(width);
      expect(label.right <= value.left + 1 || label.bottom <= value.top + 1).toBe(true);
      expect(await modal.locator('.sd-modal-panel').evaluate(panel => panel.scrollLeft)).toBe(0);
    });
  }
});

test('常驻摘要和首问在 1024px 可用，详细分析不吸顶', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1024, height: 740 });
  const model = 'synthetic-model-' + 'verylongidentifier'.repeat(16);
  await page.route('**/api/sessions/claude_code/hifi-viz-session-001/meta', async route => {
    const response = await route.fetch();
    await route.fulfill({ response, json: { ...await response.json(), model } });
  });
  await page.goto('/sessions/claude_code/hifi-viz-session-001');
  await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
  await page.locator('[data-session-info] > summary').click();
  await expect(page.locator('[data-session-model-brief]')).toHaveText(model);
  await expect(page.locator('[data-session-info]').getByText(model, { exact: true })).toHaveCount(1);
  const modelFits = await page.locator('[data-session-model-brief]').evaluate(el => {
    const text = document.createRange();
    text.selectNodeContents(el);
    return text.getBoundingClientRect().right <= el.getBoundingClientRect().right;
  });
  expect(modelFits).toBe(true);
  await page.locator('[data-session-info] > summary').click();

  const head = page.locator('.sd-workspace-head');
  await expect(head.locator('.sd-kpi')).toHaveCount(4);
  await expect(head.locator('.sd-kpi__value').first()).not.toHaveText('Loading…');
  const stickyHeight = await head.evaluate(el => el.getBoundingClientRect().height);
  expect(stickyHeight).toBeLessThan(185);
  await expect(head.locator('[data-session-timing-note]')).toHaveCount(0);
  const timing = page.locator('[data-session-timing-explanation] [data-session-timing-note]');
  await timing.getByText('计时口径与来源', { exact: true }).press('Enter');
  await expect(timing).toHaveAttribute('open');
  await expect(timing).toContainText('不是模型推理耗时');
  expect(await head.evaluate(el => el.getBoundingClientRect().height)).toBe(stickyHeight);
  await timing.getByText('计时口径与来源', { exact: true }).press('Enter');
  const kpiBounds = await head.locator('.sd-kpi').evaluateAll(cards => cards.map(card => {
    const { x, y, width } = card.getBoundingClientRect();
    return { x, y, width };
  }));
  expect(new Set(kpiBounds.map(card => card.y)).size).toBe(1);
  expect(kpiBounds[3].x + kpiBounds[3].width).toBeLessThanOrEqual(1024);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(1026);
  const screenshot = testInfo.outputPath('session-detail-layout-1024.png');
  await page.screenshot({ path: screenshot });
  await testInfo.attach('1024px 默认布局', { path: screenshot, contentType: 'image/png' });

  const analysis = page.locator('#session-analysis');
  await expect(analysis.locator('[data-session-diagnostics]')).toBeVisible();
  await page.evaluate(() => window.scrollTo(0, 300));
  await expect.poll(() => head.evaluate(el => Math.round(el.getBoundingClientRect().top))).toBe(0);
  expect(await analysis.evaluate(el => el.getBoundingClientRect().top)).toBeLessThan(0);
  expect(await head.evaluate(el => el.getBoundingClientRect().height)).toBe(stickyHeight);
  const firstQuestion = head.getByRole('button', { name: '查看首问' });
  await firstQuestion.click();
  const dialog = page.getByRole('dialog');
  await expect(dialog).toContainText('create the implementation plan.');
  const [panel, close] = await Promise.all([
    dialog.locator('.payload-modal__panel').boundingBox(),
    dialog.locator('.sd-modal-close').boundingBox(),
  ]);
  expect(panel.x).toBeGreaterThan(0);
  expect(panel.x + panel.width).toBeLessThan(1024);
  expect(close.x + close.width).toBeLessThan(1024);
  await page.keyboard.press('Escape');
  await expect(firstQuestion).toBeFocused();
});

for (const width of [1024, 1440]) {
  test(`轮次摘要等高且卡片间隙不露白 @ ${width}`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.route('**/rounds', async route => {
      const response = await route.fetch();
      const data = await response.json();
      Object.assign(data.rounds[0], { callCount: 1234, toolCallCount: 3456, failedToolCount: 9,
        signals: ['Failed', 'Subagent', 'Payload Gap'], parity: { ...data.rounds[0].parity, summary: '很长的轮次摘要'.repeat(80) } });
      await route.fulfill({ response, json: data });
    });
    await page.goto('/sessions/claude_code/hifi-viz-session-001');
    await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
    const row = page.locator('.round-row').first();
    await expect(row.locator('.metric-calls-tools')).toHaveAttribute('title', /记录.*工具/);
    const table = page.locator('[data-trace-list]');
    await expect(table.getByRole('columnheader')).toHaveText(['轮次', '摘要', '本行 Token', '原文入口', '时间', '耗时']);
    await expect(row.getByRole('cell')).toHaveCount(6);
    const summary = row.locator('.summary-col');
    await expect(summary).toContainText('9 次工具失败');
    await summary.getByRole('button', { name: '查看全部信号' }).click();
    await expect(summary.locator('[popover]')).toBeVisible();
    await expect(summary.locator('[popover]')).toContainText('Payload Gap');
    await expect(row.locator('[data-action="toggle-round"]')).toHaveAttribute('aria-expanded','false');
    await page.keyboard.press('Escape');
    await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
    const geometry = await page.evaluate(() => {
      const rect = s => document.querySelector(s).getBoundingClientRect();
      const center = s => rect(s).top + rect(s).height / 2;
      const roundHeight = [...document.querySelectorAll('.round-row')].map(el => el.getBoundingClientRect().height);
      const gap = rect('.sd-kpis').top - rect('.sd-hero').bottom;
      return { roundHeight, header: rect('.trace-table th').height, gap,
        nextGap: rect('.se-analysis').top - rect('.sd-kpis').bottom,
        canvas: getComputedStyle(document.body).backgroundColor,
        backing: getComputedStyle(document.querySelector('.sd-workspace-head')).backgroundColor,
        bars: [...document.querySelectorAll('.tokenbar-wrap')].map(el => el.getBoundingClientRect().left),
        delta: Math.abs(center('.metric-token') - center('.tokenbar-wrap')),
        x: [rect('.sd-hero').left, rect('.sd-kpis').left, rect('.se-analysis').left, rect('.sd-record-card').left],
        summaryWidth: rect('.summary-col').width,
        tableWidth: rect('.trace-table').width,
        clipped: document.querySelector('.summary-title').scrollWidth > rect('.summary-title').width,
        overflow: document.documentElement.scrollWidth - innerWidth };
    });
    expect(new Set(geometry.roundHeight).size).toBe(1);
    expect(geometry.roundHeight[0]).toBeCloseTo(36, 0);
    expect(geometry.header).toBeCloseTo(36, 0);
    expect(new Set(geometry.bars).size).toBe(1);
    expect(geometry.delta).toBeLessThan(1);
    expect(geometry.x.every(x => x === geometry.x[0])).toBe(true);
    expect(geometry.gap).toBe(8);
    expect(geometry.nextGap).toBe(8);
    expect(geometry.backing).toBe(geometry.canvas);
    expect(geometry.summaryWidth).toBeGreaterThan(geometry.tableWidth / 2);
    expect(geometry.clipped).toBe(true);
    expect(geometry.overflow).toBeLessThanOrEqual(1);
  });
}

for (const width of [1024, 1440]) {
  test(`执行表原文按钮可独立操作且不侵占摘要 @ ${width}`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/sessions/claude_code/hifi-viz-session-001');
    await expect(page.locator('body')).toHaveAttribute('data-session-api-hydrated', 'true');
    const row = page.locator('[data-trace-round-row]').filter({
      has: page.getByRole('button', { name: 'Response', exact: true }),
    }).first();
    const cell = row.locator('.attribution-col');
    const request = cell.getByRole('button', { name: 'Request', exact: true });
    const response = cell.getByRole('button', { name: 'Response', exact: true });
    await expect(request).toHaveCount(1);
    await expect(response).toHaveCount(1);
    const [input, output, area, summary, time] = await Promise.all(
      [request, response, cell, row.locator('.summary-col'), row.locator('.time-col')].map(locator => locator.boundingBox()),
    );
    expect(output.x - (input.x + input.width)).toBeGreaterThanOrEqual(6);
    expect(input.x).toBeGreaterThanOrEqual(area.x);
    expect(time.x - (output.x + output.width)).toBeGreaterThanOrEqual(6);
    expect(summary.width).toBeGreaterThan(area.width * 2);
    for (const control of [request, response]) {
      const textBox = await control.evaluate(button => {
        const range = document.createRange();
        range.selectNodeContents(button);
        const text = range.getBoundingClientRect();
        const edge = button.getBoundingClientRect();
        return { left: text.left - edge.left, right: edge.right - text.right, label: button.textContent };
      });
      expect(textBox.left, textBox.label).toBeGreaterThanOrEqual(0);
      expect(textBox.right, textBox.label).toBeGreaterThanOrEqual(0);
    }
    const modal = page.locator('dialog.payload-modal');
    for (const [control, side] of [[request, 'request'], [response, 'response']]) {
      await control.click();
      const attribution = modal.locator(`[data-payload-attribution="${side}"]`);
      await expect(attribution).toHaveAttribute('data-attribution-call', /.+/);
      await page.keyboard.press('Escape');
      await expect(control).toBeFocused();
      await control.press('Space');
      await expect(attribution).toHaveAttribute('data-attribution-call', /.+/);
      await page.keyboard.press('Escape');
    }
    await expect(row.locator('[data-action="toggle-round"]')).toHaveAttribute('aria-expanded', 'false');
  });
}
