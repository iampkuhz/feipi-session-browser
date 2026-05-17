// @ts-check
const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

/**
 * Session Detail Phase 1 Shell Layout Gate
 *
 * Verifies that the session detail page is NOT affected by
 * body.hide-left / body.focus / body.hide-right cascade conflicts
 * that would push .main into a 0px grid column.
 *
 * Requires server running at BASE_URL (default http://127.0.0.1:18999).
 */
test.describe('Session Detail Phase 1 Shell Layout', () => {
  test('shell layout is correct at 1440px viewport', async ({ page }) => {
    // Use 1440x1100 viewport as specified in quality gate
    await page.setViewportSize({ width: 1440, height: 1100 });

    // Try the known session URL first; fall back to sessions list
    const knownUrl = '/sessions/claude_code/7d7347d4-4501-44f5-afc0-ff6de915ce5b';
    const sessionsListUrl = '/sessions';

    let detailUrl = null;

    // Try known session
    const resp = await page.goto(knownUrl, { waitUntil: 'domcontentloaded', timeout: 10000 }).catch(() => null);
    if (resp && resp.ok()) {
      // Check if we got a real session page (not a 404 redirect)
      const hero = await page.locator('.hero').first().isVisible({ timeout: 5000 }).catch(() => false);
      if (hero) {
        detailUrl = knownUrl;
      }
    }

    // Fall back: extract first session link from /sessions list
    if (!detailUrl) {
      await page.goto(sessionsListUrl, { waitUntil: 'domcontentloaded', timeout: 10000 });
      await expect(page.locator('.hero').first()).toBeVisible({ timeout: 10000 });

      // Find first session detail link
      const firstLink = await page.locator('a[href*="/sessions/"]').first();
      const href = await firstLink.getAttribute('href');
      if (!href) {
        throw new Error('No session links found on /sessions page');
      }
      detailUrl = href;
    }

    // Navigate to session detail
    await page.goto(detailUrl, { waitUntil: 'domcontentloaded', timeout: 15000 });
    await expect(page.locator('.session-detail-phase1').first()).toBeVisible({ timeout: 10000 });

    // Evaluate layout metrics
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

    // Take screenshot
    const tmpDir = path.join(process.cwd(), 'tmp');
    if (!fs.existsSync(tmpDir)) fs.mkdirSync(tmpDir, { recursive: true });
    const screenshotPath = path.join(tmpDir, 'session-detail-layout-1440.png');
    await page.screenshot({ path: screenshotPath, fullPage: false });

    // Write result JSON
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

    // Assert layout correctness — each includes full JSON on failure
    const resultStr = JSON.stringify(result, null, 2);

    expect(result.scrollOk, `No horizontal scroll expected. Result: ${resultStr}`).toBe(true);

    expect(result.shellGridTemplateColumns, `Shell grid must not start with 0px column. Result: ${resultStr}`).not.toMatch(/^0px\s+/);

    expect(result.main.width, `.main must be wide enough. Result: ${resultStr}`).toBeGreaterThan(1200);

    expect(result.detail.width, `.session-detail-phase1 must be wide enough. Result: ${resultStr}`).toBeGreaterThan(1100);

    expect(result.hero.width, `.hero must be wide enough. Result: ${resultStr}`).toBeGreaterThan(900);

    expect(result.titleBeforeKpis, `Title must appear before KPIs vertically. Result: ${resultStr}`).toBe(true);
  });
});
