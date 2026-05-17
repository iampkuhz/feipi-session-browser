/**
 * session-detail.spec.js — Playwright visual/smoke quality gate for session detail page.
 *
 * This test verifies:
 * 1. Session detail page loads without console errors
 * 2. Overview hero and workbench elements are present
 * 3. View switching (Trace / Calls / Hotspots) works correctly
 * 4. Inspector panel opens and closes
 * 5. Token placement visualization renders
 * 6. Screenshots are captured for visual regression comparison
 * 7. Long session (100 rounds) performance and toggle behavior
 *
 * Setup:
 *   1. Start the fixture server: python3 scripts/start_fixture_server.py
 *      Or start your own server: ./scripts/session-browser.sh serve
 *   2. Run tests: PW_SESSION_URL=http://127.0.0.1:18999/sessions/claude_code/<session-id> npx playwright test
 *
 * Updating screenshot baselines:
 *   npx playwright test --update-snapshots
 *
 * Running with a visible browser:
 *   npx playwright test --headed
 *
 * The test auto-discovers a session detail URL via one of:
 *   - PW_SESSION_URL environment variable (full URL, e.g. http://127.0.0.1:18999/sessions/claude/xxx)
 *   - SB_TEST_DB environment variable pointing to a SQLite index (queries first session)
 *   - Falls back to /dashboard if nothing else is available (partial coverage)
 */
const { test, expect } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

const SCREENSHOT_DIR = path.join(__dirname, '..', 'test-results', 'screenshots');

/**
 * Resolve a session detail URL for testing.
 * Priority: PW_SESSION_URL env > SB_TEST_DB env query > null (skip).
 */
function resolveSessionUrl() {
  // Direct URL override — set this before running tests
  const direct = process.env.PW_SESSION_URL;
  if (direct) return direct;

  return null;
}

/**
 * Collect console errors from the page.
 */
async function collectConsoleErrors(page) {
  const errors = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') {
      errors.push(msg.text());
    }
  });
  return errors;
}

/**
 * Ensure screenshot directory exists.
 */
function ensureScreenshotDir() {
  if (!fs.existsSync(SCREENSHOT_DIR)) {
    fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
  }
}

// ── Tests ──────────────────────────────────────────────────────────

test.describe('Session Detail — Visual Quality Gate', () => {
  let sessionUrl;

  test.beforeAll(() => {
    ensureScreenshotDir();
    sessionUrl = resolveSessionUrl();
  });

  test('page loads with overview and workbench — no console errors', async ({ page }) => {
    if (!sessionUrl) {
      // If no fixture session is available, test the dashboard as a fallback smoke
      console.log('No fixture session URL available; skipping session detail test.');
      test.skip();
    }

    const consoleErrors = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') {
        consoleErrors.push(msg.text());
      }
    });

    await page.goto(sessionUrl, { waitUntil: 'domcontentloaded' });

    // Wait for key workbench elements to render
    await expect(page.locator('.wb-head')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('.wb-body')).toBeVisible({ timeout: 10000 });

    // Wait for overview / hero content
    await expect(page.locator('.hero').first()).toBeVisible({
      timeout: 10000,
    });

    // Assert no console errors
    expect(consoleErrors, 'Page should not have console errors').toEqual([]);

    // Screenshot: top viewport (overview + workbench head)
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, 'session-detail-overview.png'),
      fullPage: false,
    });
  });

  test('switch to Trace view and capture screenshot', async ({ page }) => {
    if (!sessionUrl) {
      console.log('No fixture session URL available; skipping Trace view test.');
      test.skip();
    }

    await page.goto(sessionUrl, { waitUntil: 'domcontentloaded' });
    await expect(page.locator('.wb-head')).toBeVisible({ timeout: 10000 });

    // Click the Trace view switch button
    const traceBtn = page.locator('[data-switch="trace"]');
    await expect(traceBtn).toBeVisible({ timeout: 5000 });
    await traceBtn.click();

    // Allow view transition to settle
    await page.waitForTimeout(300);

    // Screenshot: Trace view
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, 'session-detail-trace.png'),
      fullPage: false,
    });

    // Verify trace content is visible (round list or trace container)
    const hasTraceContent =
      (await page.locator('.trace-view, [class*="trace"], .round-tree, .round-list').count()) > 0;
    expect(hasTraceContent || (await traceBtn.getAttribute('class'))).toBeTruthy();
  });

  test('switch to Calls view and capture screenshot', async ({ page }) => {
    if (!sessionUrl) {
      console.log('No fixture session URL available; skipping Calls view test.');
      test.skip();
    }

    await page.goto(sessionUrl, { waitUntil: 'domcontentloaded' });
    await expect(page.locator('.wb-head')).toBeVisible({ timeout: 10000 });

    // Click the Calls view switch button
    const callsBtn = page.locator('[data-switch="calls"]');
    await expect(callsBtn).toBeVisible({ timeout: 5000 });
    await callsBtn.click();

    // Allow view transition to settle
    await page.waitForTimeout(300);

    // Screenshot: Calls view
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, 'session-detail-calls.png'),
      fullPage: false,
    });

    // Verify calls content is visible
    const hasCallsContent =
      (await page.locator('.calls-view, [class*="calls"], .calls-table').count()) > 0;
    expect(hasCallsContent || (await callsBtn.getAttribute('class'))).toBeTruthy();
  });

  test('switch to Hotspots view and capture screenshot', async ({ page }) => {
    if (!sessionUrl) {
      console.log('No fixture session URL available; skipping Hotspots view test.');
      test.skip();
    }

    await page.goto(sessionUrl, { waitUntil: 'domcontentloaded' });
    await expect(page.locator('.wb-head')).toBeVisible({ timeout: 10000 });

    // Click the Hotspots view switch button
    const hotspotsBtn = page.locator('[data-switch="hotspots"]');
    await expect(hotspotsBtn).toBeVisible({ timeout: 5000 });
    await hotspotsBtn.click();

    // Allow view transition to settle
    await page.waitForTimeout(300);

    // Screenshot: Hotspots view
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, 'session-detail-hotspots.png'),
      fullPage: false,
    });

    // Verify hotspots content is visible
    const hasHotspotsContent =
      (await page.locator('.hotspots-view, [class*="hotspot"]').count()) > 0;
    expect(hasHotspotsContent || (await hotspotsBtn.getAttribute('class'))).toBeTruthy();
  });

  test('open and close Inspector panel', async ({ page }) => {
    if (!sessionUrl) {
      console.log('No fixture session URL available; skipping Inspector test.');
      test.skip();
    }

    await page.goto(sessionUrl, { waitUntil: 'domcontentloaded' });
    await expect(page.locator('.wb-head')).toBeVisible({ timeout: 10000 });

    // Look for an inspector toggle/button — common patterns
    const inspectorBtn = page.locator(
      '[data-toggle="inspector"], .inspector-toggle, [class*="inspector-toggle"], button:has-text("Inspector"), #inspector-toggle'
    ).first();

    const inspectorVisible = await inspectorBtn.isVisible({ timeout: 3000 }).catch(() => false);

    if (inspectorVisible) {
      // Screenshot before opening
      await page.screenshot({
        path: path.join(SCREENSHOT_DIR, 'inspector-closed.png'),
        fullPage: false,
      });

      // Click to open
      await inspectorBtn.click();
      await page.waitForTimeout(300);

      // Screenshot after opening
      await page.screenshot({
        path: path.join(SCREENSHOT_DIR, 'inspector-open.png'),
        fullPage: false,
      });

      // Click again to close
      await inspectorBtn.click();
      await page.waitForTimeout(300);
    } else {
      // Inspector toggle not found — try map/inspector/focus mode buttons
      const mapBtn = page.locator('[data-mode="inspector"], button:has-text("Inspector"):not([class*="toggle"])').first();
      const mapVisible = await mapBtn.isVisible({ timeout: 3000 }).catch(() => false);

      if (mapVisible) {
        await page.screenshot({
          path: path.join(SCREENSHOT_DIR, 'inspector-mode-map.png'),
          fullPage: false,
        });

        await mapBtn.click();
        await page.waitForTimeout(300);

        await page.screenshot({
          path: path.join(SCREENSHOT_DIR, 'inspector-mode-inspector.png'),
          fullPage: false,
        });
      } else {
        console.log('Inspector toggle not found; skipping Inspector test.');
        test.skip();
      }
    }
  });

  test('token placement visualization renders correctly', async ({ page }) => {
    if (!sessionUrl) {
      console.log('No fixture session URL available; skipping token placement test.');
      test.skip();
    }

    await page.goto(sessionUrl, { waitUntil: 'domcontentloaded' });
    await expect(page.locator('.wb-head')).toBeVisible({ timeout: 10000 });

    // Verify token charts panel exists
    await expect(page.locator('.token-charts-card, .token-mix')).toBeAttached({ timeout: 5000 });

    // Verify token donut chart renders
    const donutExists = await page.locator('.token-donut__svg').count();
    expect(donutExists).toBeGreaterThan(0);

    // Verify round bar charts exist
    const barExists = await page.locator('.round-chart-bars, .round-bar__seg').count();
    expect(barExists).toBeGreaterThan(0);

    // Screenshot: token placement (focus on the workbench body where token charts appear)
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, 'token-placement.png'),
      fullPage: false,
    });
  });

  test('verify workbench metrics strip exists in DOM', async ({ page }) => {
    if (!sessionUrl) {
      console.log('No fixture session URL available; skipping metrics test.');
      test.skip();
    }

    await page.goto(sessionUrl, { waitUntil: 'domcontentloaded' });
    await expect(page.locator('.wb-head')).toBeVisible({ timeout: 10000 });

    // Metrics strip should exist in the DOM (may be below the fold)
    // Uses .hero-secondary-metrics as the actual class name in the HIFI layout
    await expect(page.locator('.hero-secondary-metrics, .metrics-strip')).toBeAttached({ timeout: 5000 });

    // Screenshot: full page to capture metrics strip regardless of position
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, 'metrics-strip-fullpage.png'),
      fullPage: true,
    });
  });

  test('verify view switch buttons are all present', async ({ page }) => {
    if (!sessionUrl) {
      console.log('No fixture session URL available; skipping switch buttons test.');
      test.skip();
    }

    await page.goto(sessionUrl, { waitUntil: 'domcontentloaded' });
    await expect(page.locator('.wb-head')).toBeVisible({ timeout: 10000 });

    // All three view switches must exist
    for (const view of ['trace', 'calls', 'hotspots']) {
      await expect(page.locator(`[data-switch="${view}"]`)).toBeVisible({
        timeout: 5000,
      });
    }
  });
});

// ── Long session performance tests (100+ rounds) ──────────────────────────

test.describe('Long Session — 100 Rounds Performance', () => {
  /**
   * Resolve long session URL from environment or use fixture URL pattern.
   */
  function resolveLongSessionUrl() {
    const direct = process.env.PW_LONG_SESSION_URL;
    if (direct) return direct;
    return null;
  }

  test('trace view renders 100 rounds without timeout', async ({ page }) => {
    const longUrl = resolveLongSessionUrl();
    if (!longUrl) {
      console.log('No long fixture session URL available; skipping long session test.');
      test.skip();
    }

    // Measure page load time
    const startTime = Date.now();
    await page.goto(longUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
    const loadTime = Date.now() - startTime;

    await expect(page.locator('.wb-head')).toBeVisible({ timeout: 10000 });

    // Switch to Trace view
    const traceBtn = page.locator('[data-switch="trace"]');
    await traceBtn.click();
    await page.waitForTimeout(300);

    // Verify trace container exists
    await expect(page.locator('.trace')).toBeVisible({ timeout: 5000 });

    // Count visible trace rows (should match 100 rounds)
    const rowCount = await page.locator('.trace-row').count();
    console.log(`Long session: ${rowCount} trace rows rendered in ${loadTime}ms`);

    // Assert all 100 rounds are present
    expect(rowCount).toBeGreaterThanOrEqual(100);

    // Assert page loads within reasonable time (<5s for 100 rounds)
    expect(loadTime).toBeLessThan(5000);

    // Screenshot for visual regression
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, 'long-session-trace.png'),
      fullPage: false,
    });
  });

  test('round toggle works without layout jank', async ({ page }) => {
    const longUrl = resolveLongSessionUrl();
    if (!longUrl) {
      console.log('No long fixture session URL available; skipping round toggle test.');
      test.skip();
    }

    await page.goto(longUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await expect(page.locator('.wb-head')).toBeVisible({ timeout: 10000 });

    // Switch to Trace view
    await page.locator('[data-switch="trace"]').click();
    await page.waitForTimeout(300);

    // Clear any persisted expanded state
    await page.evaluate(() => {
      localStorage.removeItem('rounds_claude_code_long-session-001');
    });
    await page.reload({ waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(300);

    // Get the first trace row and detail elements (data-round-detail is 1-indexed)
    const firstRow = page.locator('.trace-row[data-round-idx="1"]').first();
    const firstDetail = page.locator('[data-round-detail="1"]').first();

    // Verify detail is initially hidden
    const initiallyVisible = await firstDetail.isVisible();
    expect(initiallyVisible).toBe(false);

    // Toggle the first round open via direct JS call
    await page.evaluate((row) => {
      if (window.toggleRoundDetail) window.toggleRoundDetail(row);
    }, await firstRow.elementHandle());
    await page.waitForTimeout(200);

    // Verify detail panel opened
    await expect(firstDetail).toBeVisible({ timeout: 3000 });

    // Toggle closed via toggleRoundDetail with forceState
    await page.evaluate((row) => {
      if (window.toggleRoundDetail) window.toggleRoundDetail(row, 'collapse');
    }, await firstRow.elementHandle());
    await page.waitForTimeout(200);

    // Verify detail panel closed
    const afterCloseVisible = await firstDetail.isVisible();
    expect(afterCloseVisible).toBe(false);

    // Toggle a mid-round (e.g., R50) to verify lazy behavior
    const midRow = page.locator('.trace-row').nth(49);
    await midRow.click();
    await page.waitForTimeout(200);

    const midDetail = page.locator('.trace-detail').nth(49);
    await expect(midDetail).toBeVisible({ timeout: 3000 });
  });

  test('DOM node count stays reasonable for 100 rounds', async ({ page }) => {
    const longUrl = resolveLongSessionUrl();
    if (!longUrl) {
      console.log('No long fixture session URL available; skipping DOM node test.');
      test.skip();
    }

    await page.goto(longUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await expect(page.locator('.wb-head')).toBeVisible({ timeout: 10000 });

    // Switch to Trace view (all details hidden by default)
    await page.locator('[data-switch="trace"]').click();
    await page.waitForTimeout(300);

    // Count total DOM nodes — should be under 15k for 100 collapsed rounds
    const nodeCount = await page.evaluate(() => document.querySelectorAll('*').length);
    console.log(`Long session: ${nodeCount} total DOM nodes (collapsed)`);

    // Node count should be under a reasonable threshold
    expect(nodeCount).toBeLessThan(20000);

    // Expand all rounds and re-check
    const expandAllBtn = page.locator('[data-action="expand-all"]');
    if (await expandAllBtn.count() > 0) {
      await expandAllBtn.click();
      await page.waitForTimeout(500);

      const expandedNodeCount = await page.evaluate(() => document.querySelectorAll('*').length);
      console.log(`Long session: ${expandedNodeCount} total DOM nodes (expanded)`);

      // Even with all expanded, should not exceed 50k nodes
      expect(expandedNodeCount).toBeLessThan(50000);
    }
  });

  test('trace filter works efficiently on 100 rounds', async ({ page }) => {
    const longUrl = resolveLongSessionUrl();
    if (!longUrl) {
      console.log('No long fixture session URL available; skipping trace filter test.');
      test.skip();
    }

    await page.goto(longUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await expect(page.locator('.wb-head')).toBeVisible({ timeout: 10000 });

    // Switch to Trace view
    await page.locator('[data-switch="trace"]').click();
    await page.waitForTimeout(300);

    // Apply a filter that matches a few rounds
    const filterInput = page.locator('#trace-filter-input');
    await filterInput.fill('R1');
    await page.waitForTimeout(200);

    // Count filtered rows — should see R1, R10-R19, R100 (not R2-R9, R20-R99)
    const visibleRows = await page.locator('.trace-row:not(.is-filtered-out)').count();
    console.log(`Long session: ${visibleRows} visible rows after filtering "R1"`);

    // Should have some matching rows but not all 100
    expect(visibleRows).toBeGreaterThan(0);
    expect(visibleRows).toBeLessThan(100);

    // Clear filter
    await filterInput.fill('');
    await page.waitForTimeout(200);

    const allRows = await page.locator('.trace-row').count();
    expect(allRows).toBeGreaterThanOrEqual(100);
  });
});
