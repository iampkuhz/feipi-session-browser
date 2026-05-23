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

test.describe('会话详情 Phase 1 外壳布局', () => {
  test('1440px 视口下外壳布局正确', async ({ page }) => {
    // 使用质量门禁指定的 1440x1100 视口
    await page.setViewportSize({ width: 1440, height: 1100 });

    // 先尝试已知会话 URL，回退到会话列表
    const knownUrl = '/sessions/claude_code/7d7347d4-4501-44f5-afc0-ff6de915ce5b';
    const sessionsListUrl = '/sessions';

    let detailUrl = null;

    // 尝试已知会话
    const resp = await page.goto(knownUrl, { waitUntil: 'domcontentloaded', timeout: 10000 }).catch(() => null);
    if (resp && resp.ok()) {
      // 检查是否拿到真实会话页面（非 404 重定向）
      const hero = await page.locator('.hero').first().isVisible({ timeout: 5000 }).catch(() => false);
      if (hero) {
        detailUrl = knownUrl;
      }
    }

    // 回退：从 /sessions 列表提取第一个会话链接
    if (!detailUrl) {
      await page.goto(sessionsListUrl, { waitUntil: 'domcontentloaded', timeout: 10000 });
      await expect(page.locator('.hero').first()).toBeVisible({ timeout: 10000 });

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
    await expect(page.locator('.session-detail-phase1').first()).toBeVisible({ timeout: 10000 });

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
      const title = document.querySelector('.session-detail-phase1 .hero-title');
      const kpis = document.querySelector('.session-detail-phase1 .kpis');

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
        detail: rect('.session-detail-phase1'),
        hero: rect('.session-detail-phase1 .hero, .session-detail-phase1 .hero-main'),
        title: rect('.session-detail-phase1 .hero-title'),
        kpis: rect('.session-detail-phase1 .kpis'),
        titleBeforeKpis: titleRect && kpisRect
          ? titleRect.bottom <= kpisRect.top + 4
          : false,
      };
    });

    // 截图
    const tmpDir = path.join(process.cwd(), 'tmp');
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

    expect(result.detail.width, `.session-detail-phase1 宽度不足。结果：${resultStr}`).toBeGreaterThan(1100);

    expect(result.hero.width, `.hero 宽度不足。结果：${resultStr}`).toBeGreaterThan(900);

    expect(result.titleBeforeKpis, `标题必须出现在 KPI 上方。结果：${resultStr}`).toBe(true);
  });
});
