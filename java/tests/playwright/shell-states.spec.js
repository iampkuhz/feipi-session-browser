const { test, expect } = require('@playwright/test');
const path = require('path');
const { runPlaywrightRoot } = require('./runtime-paths');

function measureState(page, state) {
  return page.evaluate((state) => {
    const body = document.body;
    for (const name of ['hide-left', 'hide-right', 'focus']) {
      body.classList.toggle(name, name === state);
    }
    const width = (selector) => document.querySelector(selector)?.getBoundingClientRect().width ?? 0;
    return {
      main: width('.main'),
      sidebar: width('.sidebar'),
      inspector: width('.inspector'),
      overflow: document.documentElement.scrollWidth - window.innerWidth,
    };
  }, state);
}

for (const [width, height] of [[1440, 1100], [1280, 800], [1180, 800]]) {
  test(`[UI-SD-014][UI-VISUAL-002][UI-INTERACTION-001][UI-VISUAL-004][UI-VISUAL-005] Session Detail shell states at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height });
    await page.goto('/sessions/claude_code/hifi-viz-session-001', { waitUntil: 'domcontentloaded', timeout: 15000 });
    await expect(page.locator('.session-detail-page').first()).toBeVisible({ timeout: 10000 });

    // Each read sets all three classes; a previous measurement cannot leave a state active.
    const minMainAt1440 = { normal: 800, 'hide-left': 900, 'hide-right': 800, focus: 1100 };
    for (const [state, minMain] of Object.entries(minMainAt1440)) {
      await test.step(state, async () => {
        const size = await measureState(page, state);
        expect(size.main).toBeGreaterThan(width === 1440 ? minMain : 600);
        if (width === 1440) {
          if (state === 'hide-left' || state === 'focus') expect(size.sidebar).toBe(0);
          else expect(size.sidebar).toBeGreaterThan(0);
          if (state === 'hide-right' || state === 'focus') expect(size.inspector).toBe(0);
          expect(size.overflow).toBeLessThanOrEqual(2);
        }
        // Acceptance cases UI-VISUAL-004/005 explicitly require these saved views.
        await page.screenshot({
          path: path.join(runPlaywrightRoot, 'screenshots', `shell-${state}-${width}.png`),
          fullPage: false,
          timeout: 30000,
        });
      });
    }
  });
}

test('[UI-VISUAL-006] Dashboard shell measures normal and collapsed sidebar', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/dashboard', { waitUntil: 'domcontentloaded', timeout: 10000 });
  await expect(page.locator('.page-head').first()).toBeVisible({ timeout: 5000 });

  const normal = await measureState(page, 'normal');
  expect(normal.main).toBeGreaterThan(800);
  expect(normal.sidebar).toBeGreaterThan(0);
  const collapsed = await measureState(page, 'hide-left');
  expect(collapsed.sidebar).toBe(0);
  expect(collapsed.main).toBeGreaterThan(900);
  expect(collapsed.overflow).toBeLessThanOrEqual(2);
});
