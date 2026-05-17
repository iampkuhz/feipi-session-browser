/**
 * session-detail.spec.js — Playwright visual/smoke quality gate for Phase 1 session detail page.
 *
 * This test verifies:
 * 1. Session detail page loads with hero, issue summary, and trace panel — no console errors
 * 2. No visible disabled placeholder buttons or "待实现" stubs
 * 3. All visible buttons use supported data-action values
 * 4. All/Failed filter works correctly
 * 5. Expand All / Collapse All works
 * 6. Round toggle changes aria-expanded state
 * 7. First failed round is auto-expanded on page load
 * 8. Payload modal opens and closes
 * 9. Long session (100 rounds) performance and DOM node budget
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
 * Ensure screenshot directory exists.
 */
function ensureScreenshotDir() {
  if (!fs.existsSync(SCREENSHOT_DIR)) {
    fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
  }
}

// ── Tests ──────────────────────────────────────────────────────────

test.describe('Session Detail — Phase 1', () => {
  let sessionUrl;

  test.beforeAll(() => {
    ensureScreenshotDir();
    sessionUrl = resolveSessionUrl();
  });

  test('page loads with summary and trace panel — no console errors', async ({ page }) => {
    if (!sessionUrl) {
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

    // Trace is the default (and only) view in Phase 1 — verify core sections
    await expect(page.locator('.hero').first()).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[data-issue-summary]')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[data-trace-panel]')).toBeVisible({ timeout: 10000 });

    // Assert no console errors
    expect(consoleErrors, 'Page should not have console errors').toEqual([]);

    // Screenshot: top viewport
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, 'session-detail-overview.png'),
      fullPage: false,
    });
  });

  test('no visible disabled placeholder buttons', async ({ page }) => {
    if (!sessionUrl) {
      console.log('No fixture session URL available; skipping disabled placeholder test.');
      test.skip();
    }

    await page.goto(sessionUrl, { waitUntil: 'domcontentloaded' });
    await expect(page.locator('.hero').first()).toBeVisible({ timeout: 10000 });

    // No visible button should have disabled=true
    const disabledButtons = page.locator('button:visible[disabled="true"], button:visible[disabled]');
    expect(await disabledButtons.count()).toBe(0);

    // No visible button with title containing "待实现"
    const stubButtons = page.locator('button:visible[title*="待实现"]');
    expect(await stubButtons.count()).toBe(0);
  });

  test('all visible buttons have supported data-action', async ({ page }) => {
    if (!sessionUrl) {
      console.log('No fixture session URL available; skipping data-action test.');
      test.skip();
    }

    await page.goto(sessionUrl, { waitUntil: 'domcontentloaded' });
    await expect(page.locator('.hero').first()).toBeVisible({ timeout: 10000 });

    // Supported data-action values in Phase 1
    const supportedActions = new Set([
      'filter-status',
      'expand-all',
      'collapse-all',
      'jump-round',
      'open-payload',
      'payload-mode',
      'close-modal',
      'jump-anomaly',
    ]);

    const buttonsWithDataAction = page.locator('button:visible[data-action]');
    const count = await buttonsWithDataAction.count();

    for (let i = 0; i < count; i++) {
      const btn = buttonsWithDataAction.nth(i);
      const action = await btn.getAttribute('data-action');
      expect(
        supportedActions.has(action),
        `Button with data-action="${action}" is not in supported set`,
      ).toBe(true);
    }
  });

  test('All/Failed filter works', async ({ page }) => {
    if (!sessionUrl) {
      console.log('No fixture session URL available; skipping filter test.');
      test.skip();
    }

    await page.goto(sessionUrl, { waitUntil: 'domcontentloaded' });
    await expect(page.locator('[data-trace-panel]')).toBeVisible({ timeout: 10000 });

    // Count all trace rows
    const totalRows = await page.locator('.trace-row').count();
    expect(totalRows).toBeGreaterThan(0);

    // All filter: no rows should have is-filtered-out
    await page.locator('.trace-panel__chip[data-status="all"]').click();
    await page.waitForTimeout(100);
    const filteredOutAll = await page.locator('.trace-row.is-filtered-out').count();
    expect(filteredOutAll).toBe(0);

    // Failed filter: only failed rows visible, at least one non-failed row gets filtered
    const totalFailed = await page.locator('.trace-row[data-status="failed"]').count();
    await page.locator('.trace-panel__chip[data-status="failed"]').click();
    await page.waitForTimeout(100);

    // All visible rows should be failed
    const visibleRows = await page.locator('.trace-row:not(.is-filtered-out)').count();
    if (totalFailed > 0) {
      expect(visibleRows).toBe(totalFailed);
      // Non-failed rows should be filtered out
      const filteredOutFailed = await page.locator('.trace-row.is-filtered-out').count();
      expect(filteredOutFailed).toBe(totalRows - totalFailed);
    } else {
      // No failed rows — all should be filtered out
      expect(visibleRows).toBe(0);
    }
  });

  test('Expand All / Collapse All works', async ({ page }) => {
    if (!sessionUrl) {
      console.log('No fixture session URL available; skipping expand/collapse test.');
      test.skip();
    }

    await page.goto(sessionUrl, { waitUntil: 'domcontentloaded' });
    await expect(page.locator('[data-trace-panel]')).toBeVisible({ timeout: 10000 });

    const totalRows = await page.locator('.trace-row').count();
    expect(totalRows).toBeGreaterThan(0);

    // Collapse All: all trace-row details should be hidden
    const collapseBtn = page.locator('[data-action="collapse-all"]');
    await expect(collapseBtn).toBeVisible({ timeout: 5000 });
    await collapseBtn.click();
    await page.waitForTimeout(200);

    const visibleCountAfterCollapse = await page.locator('.trace-detail').evaluateAll(els =>
      els.filter(el => el.style.display !== 'none').length
    );
    expect(visibleCountAfterCollapse).toBe(0);

    // Expand All: all trace-row details should be visible
    const expandBtn = page.locator('[data-action="expand-all"]');
    await expect(expandBtn).toBeVisible({ timeout: 5000 });
    await expandBtn.click();
    await page.waitForTimeout(200);

    const visibleCountAfterExpand = await page.locator('.trace-detail').evaluateAll(els =>
      els.filter(el => el.style.display !== 'none').length
    );
    expect(visibleCountAfterExpand).toBe(totalRows);
  });

  test('round toggle changes aria-expanded', async ({ page }) => {
    if (!sessionUrl) {
      console.log('No fixture session URL available; skipping round toggle test.');
      test.skip();
    }

    await page.goto(sessionUrl, { waitUntil: 'domcontentloaded' });
    await expect(page.locator('[data-trace-panel]')).toBeVisible({ timeout: 10000 });

    // Start from a collapsed state
    await page.locator('[data-action="collapse-all"]').click();
    await page.waitForTimeout(100);

    // Pick the first trace row
    const firstRow = page.locator('.trace-row').first();
    const firstDetail = page.locator('[data-round-detail]').first();
    const toggleIcon = firstRow.locator('[data-toggle-icon]').first();

    // Verify detail is initially hidden
    await expect(firstDetail).toBeHidden({ timeout: 3000 });

    // Click the trace row to expand
    await firstRow.click();
    await page.waitForTimeout(150);

    // Detail should now be visible
    await expect(firstDetail).toBeVisible({ timeout: 3000 });

    // Click again to collapse
    await firstRow.click();
    await page.waitForTimeout(150);

    // Detail should be hidden again
    await expect(firstDetail).toBeHidden({ timeout: 3000 });
  });

  test('first failed round expanded by default', async ({ page }) => {
    if (!sessionUrl) {
      console.log('No fixture session URL available; skipping first-failed-round test.');
      test.skip();
    }

    await page.goto(sessionUrl, { waitUntil: 'domcontentloaded' });
    await expect(page.locator('[data-trace-panel]')).toBeVisible({ timeout: 10000 });

    // Find the first failed round
    const firstFailedRow = page.locator('.trace-row[data-status="failed"]').first();
    const failedCount = await firstFailedRow.count();

    if (failedCount === 0) {
      // No failed rounds — nothing to auto-expand, test passes vacuously
      console.log('No failed rounds in this session; skipping first-failed-round test.');
      return;
    }

    // Get the round index of the first failed round
    const roundIdx = await firstFailedRow.getAttribute('data-round-idx');
    const correspondingDetail = page.locator(`[data-round-detail="${roundIdx}"]`);

    // On page load, the first failed round detail should be visible
    await expect(correspondingDetail).toBeVisible({ timeout: 3000 });
  });

  test('payload modal opens and closes', async ({ page }) => {
    if (!sessionUrl) {
      console.log('No fixture session URL available; skipping payload modal test.');
      test.skip();
    }

    await page.goto(sessionUrl, { waitUntil: 'domcontentloaded' });
    await expect(page.locator('[data-trace-panel]')).toBeVisible({ timeout: 10000 });

    // Expand all rounds to find payload buttons inside trace details
    await page.locator('[data-action="expand-all"]').click();
    await page.waitForTimeout(200);

    // Look for open-payload buttons
    const payloadBtn = page.locator('button[data-action="open-payload"]').first();
    const hasPayloadBtn = await payloadBtn.count().then(c => c > 0);

    if (!hasPayloadBtn) {
      console.log('No payload buttons available in this session; skipping payload modal test.');
      return;
    }

    const modal = page.locator('#payload-modal');

    // Modal should be hidden initially
    await expect(modal).toBeHidden({ timeout: 3000 });

    // Click to open
    await payloadBtn.click();
    await page.waitForTimeout(200);

    // Modal should be open (dialog with showModal() is :modal or [open])
    await expect(modal).toHaveAttribute('open', { timeout: 5000 });

    // Click close button
    const closeBtn = page.locator('[data-action="close-modal"]');
    await closeBtn.click();
    await page.waitForTimeout(200);

    // Modal should be closed
    await expect(modal).toBeHidden({ timeout: 5000 });
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

    await expect(page.locator('.hero').first()).toBeVisible({ timeout: 10000 });

    // Verify trace panel is visible (trace is default in Phase 1 — no switching needed)
    await expect(page.locator('[data-trace-panel]')).toBeVisible({ timeout: 5000 });

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

  test('DOM node count stays reasonable for 100 rounds', async ({ page }) => {
    const longUrl = resolveLongSessionUrl();
    if (!longUrl) {
      console.log('No long fixture session URL available; skipping DOM node test.');
      test.skip();
    }

    await page.goto(longUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await expect(page.locator('.hero').first()).toBeVisible({ timeout: 10000 });

    // Collapse all rounds (details hidden by default after auto-expand of first failed)
    await page.locator('[data-action="collapse-all"]').click();
    await page.waitForTimeout(200);

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

  test('expand-all behavior on 100 rounds', async ({ page }) => {
    const longUrl = resolveLongSessionUrl();
    if (!longUrl) {
      console.log('No long fixture session URL available; skipping expand-all test.');
      test.skip();
    }

    await page.goto(longUrl, { waitUntil: 'domcontentloaded', timeout: 30000 });
    await expect(page.locator('[data-trace-panel]')).toBeVisible({ timeout: 10000 });

    const totalRows = await page.locator('.trace-row').count();
    expect(totalRows).toBeGreaterThanOrEqual(100);

    // Collapse all first
    await page.locator('[data-action="collapse-all"]').click();
    await page.waitForTimeout(200);

    const collapsedVisible = await page.locator('.trace-detail:not([style*="display: none"])').count();
    expect(collapsedVisible).toBe(0);

    // Expand all
    await page.locator('[data-action="expand-all"]').click();
    await page.waitForTimeout(300);

    const expandedVisible = await page.locator('.trace-detail:not([style*="display: none"])').count();
    expect(expandedVisible).toBe(totalRows);

    // Collapse all again
    await page.locator('[data-action="collapse-all"]').click();
    await page.waitForTimeout(200);

    const reCollapsedVisible = await page.locator('.trace-detail:not([style*="display: none"])').count();
    expect(reCollapsedVisible).toBe(0);
  });
});
