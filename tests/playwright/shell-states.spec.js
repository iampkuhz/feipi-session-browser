/**
 * shell-states.spec.js — Shell layout state visual/structural smoke tests
 *
 * Covers all 4 body-level shell states: normal, hide-left, hide-right, focus.
 * Tests structural assertions via getComputedStyle(grid-template-columns) and
 * screenshot baselines.
 *
 * Requires fixture server running at BASE_URL (default http://127.0.0.1:18999).
 */
const { test, expect } = require('@playwright/test');
const path = require('path');
const fs = require('fs');

const TMP_DIR = path.join(process.cwd(), 'tmp');

test.describe('Shell states — Session Detail', () => {
  const viewports = [
    { width: 1440, height: 1100, label: '1440' },
    { width: 1280, height: 800, label: '1280' },
    { width: 1180, height: 800, label: '1180' },
  ];

  // ── Helper: navigate to a session detail page ─────────────────
  async function gotoSessionDetail(page) {
    const knownUrl = '/sessions/claude_code/hifi-viz-session-001';
    await page.goto(knownUrl, { waitUntil: 'domcontentloaded', timeout: 15000 });
    await expect(page.locator('.session-detail-page').first()).toBeVisible({ timeout: 10000 });
  }

  // ── Helper: set body shell state and measure grid ─────────────
  async function setShellStateAndMeasure(page, state) {
    await page.evaluate((s) => {
      document.body.classList.remove('hide-left', 'hide-right', 'focus');
      if (s === 'hide-left') document.body.classList.add('hide-left');
      else if (s === 'hide-right') document.body.classList.add('hide-right');
      else if (s === 'focus') document.body.classList.add('focus');
    }, state);
    await page.waitForTimeout(100);

    return await page.evaluate(() => {
      const shell = document.querySelector('.shell');
      const main = document.querySelector('.main');
      const sidebar = document.querySelector('.sidebar');
      const inspector = document.querySelector('.inspector');
      const gtc = shell ? getComputedStyle(shell).gridTemplateColumns : null;
      const gw = shell ? getComputedStyle(shell).gridTemplateColumns.split(' ').map(Number) : [];

      const rect = (sel) => {
        const el = document.querySelector(sel);
        if (!el) return { width: 0, height: 0 };
        const r = el.getBoundingClientRect();
        return { width: r.width, height: r.height };
      };

      return {
        bodyClass: document.body.className,
        gridTemplateColumns: gtc,
        gridWidths: gw,
        shellWidth: rect('.shell').width,
        mainWidth: rect('.main').width,
        sidebarWidth: rect('.sidebar').width,
        inspectorWidth: rect('.inspector').width,
        scrollWidth: document.documentElement.scrollWidth,
        viewportWidth: window.innerWidth,
      };
    });
  }

  // ── Shell state matrix: normal ────────────────────────────────
  test('normal state — sidebar + main + inspector visible', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1100 });
    await gotoSessionDetail(page);
    const result = await setShellStateAndMeasure(page, 'normal');

    expect(result.mainWidth, 'normal: .main 宽度必须 > 800').toBeGreaterThan(800);
    expect(result.sidebarWidth, 'normal: .sidebar 宽度必须 > 0').toBeGreaterThan(0);
    expect(result.scrollWidth, 'normal: 不应出现水平滚动').toBeLessThanOrEqual(result.viewportWidth + 2);
  });

  // ── Shell state matrix: hide-left ─────────────────────────────
  test('hide-left state — sidebar collapsed, main visible (no-inspector page)', async ({ page }) => {
    // Previously fixme: body.hide-left caused .main width → 0px; fixed by
    // adding explicit .no-inspector body state variants in shell.css.
    // Note: session detail pages use no-inspector class, so there is no inspector element.
    await page.setViewportSize({ width: 1440, height: 1100 });
    await gotoSessionDetail(page);
    const result = await setShellStateAndMeasure(page, 'hide-left');

    expect(result.sidebarWidth, 'hide-left: .sidebar 宽度必须为 0').toBe(0);
    expect(result.mainWidth, 'hide-left: .main 宽度必须 > 900').toBeGreaterThan(900);
    expect(result.scrollWidth, 'hide-left: 不应出现水平滚动').toBeLessThanOrEqual(result.viewportWidth + 2);
  });

  // ── Shell state matrix: hide-right ────────────────────────────
  test('hide-right state — sidebar + main visible, inspector collapsed', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1100 });
    await gotoSessionDetail(page);
    const result = await setShellStateAndMeasure(page, 'hide-right');

    expect(result.sidebarWidth, 'hide-right: .sidebar 宽度必须 > 0').toBeGreaterThan(0);
    expect(result.mainWidth, 'hide-right: .main 宽度必须 > 800').toBeGreaterThan(800);
    expect(result.inspectorWidth, 'hide-right: .inspector 宽度必须为 0').toBe(0);
    expect(result.scrollWidth, 'hide-right: 不应出现水平滚动').toBeLessThanOrEqual(result.viewportWidth + 2);
  });

  // ── Shell state matrix: focus ─────────────────────────────────
  test('focus state — only main visible, sidebar + inspector collapsed', async ({ page }) => {
    // Previously fixme: body.focus caused .main width → 0px; fixed by
    // adding explicit .no-inspector body state variants in shell.css.
    await page.setViewportSize({ width: 1440, height: 1100 });
    await gotoSessionDetail(page);
    const result = await setShellStateAndMeasure(page, 'focus');

    expect(result.sidebarWidth, 'focus: .sidebar 宽度必须为 0').toBe(0);
    expect(result.mainWidth, 'focus: .main 宽度必须 > 1100').toBeGreaterThan(1100);
    expect(result.inspectorWidth, 'focus: .inspector 宽度必须为 0').toBe(0);
    expect(result.scrollWidth, 'focus: 不应出现水平滚动').toBeLessThanOrEqual(result.viewportWidth + 2);
  });

  // ── Screenshot baselines for stable shell states ──────────────
  for (const vp of viewports) {
    for (const state of ['normal', 'hide-right']) {
      test(`shell @ ${state} ${vp.label} — screenshot`, async ({ page }) => {
        await page.setViewportSize({ width: vp.width, height: vp.height });
        await gotoSessionDetail(page);
        await setShellStateAndMeasure(page, state);

        if (!fs.existsSync(TMP_DIR)) fs.mkdirSync(TMP_DIR, { recursive: true });
        await page.screenshot({
          path: path.join(TMP_DIR, `shell-${state}-${vp.label}.png`),
          fullPage: false,
        });

        // Structural assertion: main must have visible width in all states
        const result = await setShellStateAndMeasure(page, state);
        expect(result.mainWidth, `${state} @ ${vp.label}: .main 宽度必须 > 600`).toBeGreaterThan(600);
      });
    }
  }

  // ── Screenshot baselines for hide-left and focus states ──
  for (const vp of viewports) {
    for (const state of ['hide-left', 'focus']) {
      test(`shell @ ${state} ${vp.label} — screenshot`, async ({ page }) => {
        await page.setViewportSize({ width: vp.width, height: vp.height });
        await gotoSessionDetail(page);
        await setShellStateAndMeasure(page, state);

        if (!fs.existsSync(TMP_DIR)) fs.mkdirSync(TMP_DIR, { recursive: true });
        await page.screenshot({
          path: path.join(TMP_DIR, `shell-${state}-${vp.label}.png`),
          fullPage: false,
        });

        const result = await setShellStateAndMeasure(page, state);
        expect(result.mainWidth, `${state} @ ${vp.label}: .main 宽度必须 > 600`).toBeGreaterThan(600);
      });
    }
  }
});

test.describe('Shell states — Dashboard (no-inspector)', () => {
  test('normal state — dashboard sidebar + main visible', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/dashboard', { waitUntil: 'domcontentloaded', timeout: 10000 });
    await expect(page.locator('.page-head').first()).toBeVisible({ timeout: 5000 });

    const result = await page.evaluate(() => {
      const shell = document.querySelector('.shell');
      const gtc = shell ? getComputedStyle(shell).gridTemplateColumns : null;
      const rect = (sel) => {
        const el = document.querySelector(sel);
        return el ? el.getBoundingClientRect().width : 0;
      };
      return {
        bodyClass: document.body.className,
        gridTemplateColumns: gtc,
        mainWidth: rect('.main'),
        sidebarWidth: rect('.sidebar'),
        inspectorWidth: rect('.inspector'),
      };
    });

    expect(result.mainWidth, 'dashboard normal: .main 宽度必须 > 800').toBeGreaterThan(800);
    expect(result.sidebarWidth, 'dashboard normal: .sidebar 宽度必须 > 0').toBeGreaterThan(0);
  });

  test('hide-left state — dashboard sidebar collapsed', async ({ page }) => {
    // Previously fixme: same shell grid bug; fixed by adding explicit
    // .no-inspector body state variants in shell.css.
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/dashboard', { waitUntil: 'domcontentloaded', timeout: 10000 });
    await expect(page.locator('.page-head').first()).toBeVisible({ timeout: 5000 });

    await page.evaluate(() => {
      document.body.classList.remove('hide-left', 'hide-right', 'focus');
      document.body.classList.add('hide-left');
    });
    await page.waitForTimeout(100);

    const result = await page.evaluate(() => {
      const rect = (sel) => {
        const el = document.querySelector(sel);
        return el ? el.getBoundingClientRect().width : 0;
      };
      return {
        sidebarWidth: rect('.sidebar'),
        mainWidth: rect('.main'),
        scrollWidth: document.documentElement.scrollWidth,
        viewportWidth: window.innerWidth,
      };
    });

    expect(result.sidebarWidth, 'dashboard hide-left: .sidebar 宽度必须为 0').toBe(0);
    expect(result.mainWidth, 'dashboard hide-left: .main 宽度必须 > 900').toBeGreaterThan(900);
    expect(result.scrollWidth, 'dashboard hide-left: 不应出现水平滚动').toBeLessThanOrEqual(result.viewportWidth + 2);
  });
});
