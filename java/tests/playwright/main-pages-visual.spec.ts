import { test, expect, type Page } from '@playwright/test';

type SmokePage = {
  name: string;
  url: string;
  expectedStatus?: number;
  selectors: string[];
};

type BrowserError = {
  text: string;
  url: string;
};

const smokePages: SmokePage[] = [
  {
    name: 'Dashboard',
    url: '/dashboard',
    selectors: [
      '.page-head',
      '.kpi-grid',
      '.metric-card__secondary-row',
      '[data-hbar="session-share"]',
      '[data-hbar="token-share"]',
      '[data-hbar="prompt-share"]',
      '.chart-card',
    ],
  },
  {
    name: 'Sessions',
    url: '/sessions',
    selectors: ['.page-head', '.filter-card', '.data-table'],
  },
  {
    name: 'Projects',
    url: '/projects',
    selectors: ['.page-head', '.metric-grid', '.data-table'],
  },
  {
    name: 'Project Detail',
    url: '/projects/test-hifi-project',
    selectors: ['.page-head', '.metric-grid', '.data-table'],
  },
  {
    name: 'Glossary',
    url: '/glossary',
    selectors: ['.page-head', '.metric-grid', '.filter-card', '.data-table'],
  },
  {
    name: '404',
    url: '/__main_pages_visual_missing__',
    expectedStatus: 404,
    selectors: ['.state-panel', '.state-panel__title', '.state-panel__links'],
  },
];

async function expectNoLayoutOverflow(page: Page) {
  const metrics = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
    mainHeight: document.querySelector('main')?.getBoundingClientRect().height ?? 0,
    contentWidth: document.querySelector('.content')?.getBoundingClientRect().width ?? 0,
  }));

  expect(metrics.scrollWidth, 'page should not create horizontal overflow').toBeLessThanOrEqual(
    metrics.clientWidth + 2,
  );
  expect(metrics.mainHeight, 'main shell should occupy visible height').toBeGreaterThan(300);
  expect(metrics.contentWidth, 'content region should have usable width').toBeGreaterThan(600);
}

test.describe('main page visual smoke', () => {
  for (const smoke of smokePages) {
    test(`${smoke.name} shell and core content render without browser errors`, async ({ page }) => {
      const browserErrors: BrowserError[] = [];
      page.on('console', (message) => {
        if (message.type() === 'error') {
          browserErrors.push({ text: message.text(), url: message.location().url });
        }
      });
      page.on('pageerror', (error) => browserErrors.push({ text: error.message, url: '' }));

      await page.setViewportSize({ width: 1440, height: 900 });
      const response = await page.goto(smoke.url, { waitUntil: 'domcontentloaded', timeout: 15_000 });
      if (smoke.expectedStatus !== undefined) {
        expect(response?.status(), `${smoke.name} HTTP status`).toBe(smoke.expectedStatus);
      }

      await expect(page.locator('.shell'), `${smoke.name} shell`).toBeVisible();
      await expect(page.locator('.sidebar'), `${smoke.name} sidebar`).toBeVisible();
      await expect(page.locator('.topbar'), `${smoke.name} topbar`).toBeVisible();
      await expect(page.locator('.content'), `${smoke.name} content`).toBeVisible();
      await expect(page.locator('.footer'), `${smoke.name} footer`).toBeVisible();
      await expect(page.locator('#payload-modal'), `${smoke.name} payload modal`).toHaveCount(1);

      for (const selector of smoke.selectors) {
        await expect(page.locator(selector).first(), `${smoke.name} ${selector}`).toBeVisible();
      }

      await expectNoLayoutOverflow(page);
      const unexpectedBrowserErrors = browserErrors.filter((error) => {
        const expectedTopLevel404 =
          smoke.expectedStatus === 404 &&
          error.url === page.url() &&
          error.text === 'Failed to load resource: the server responded with a status of 404 (Not Found)';
        return !expectedTopLevel404;
      });
      expect(unexpectedBrowserErrors, `${smoke.name} console/page errors`).toEqual([]);
    });
  }

  test('Dashboard hydration replaces loading placeholders in all and agent scopes', async ({ page }) => {
    await page.goto('/dashboard', { waitUntil: 'domcontentloaded', timeout: 15_000 });

    for (const stat of ['latest-sessions', 'latest-prompts', 'latest-tokens']) {
      await expect(page.locator(`[data-stat="${stat}"]`), `${stat} should finish loading`).not.toContainText(
        'Loading',
      );
    }
    await expect(page.locator('main'), 'all-agent Dashboard should finish hydration').not.toContainText(
      /Loading (?:agent summary|agent\/model efficiency|session share|token share|prompt share)/,
    );

    await Promise.all([
      page.waitForURL((url) => url.pathname === '/dashboard' && url.searchParams.get('agent') === 'claude-code'),
      page.getByRole('button', { name: 'Claude Code' }).click(),
    ]);

    const modelMixBody = page.locator('section[data-chart-card="model-mix"] tbody');
    await expect(modelMixBody, 'agent Model Mix should finish hydration').not.toContainText(
      'Loading model mix',
    );
    const modelRows = modelMixBody.locator('tr.clickable-row');
    await expect(modelRows.first(), 'fixture should render at least one model row').toBeVisible();
    await expect(modelRows.first().locator('td'), 'Model Mix rows should have four columns').toHaveCount(4);
    await expect(page.locator('main'), 'agent Dashboard should not retain loading placeholders').not.toContainText(
      'Loading',
    );
  });

  test('Project Detail search filters API-backed session rows', async ({ page }) => {
    await page.goto('/projects/test-hifi-project', { waitUntil: 'domcontentloaded', timeout: 15_000 });

    const search = page.getByLabel('Search project sessions by title or session id');
    await search.fill('Synthetic mock request 43');
    await page.getByRole('button', { name: 'Apply' }).click();

    await expect(page).toHaveURL(/(?:\?|&)q=Synthetic\+mock\+request\+43(?:&|$)/);
    await expect(page.locator('#project-sessions-table tbody tr')).toHaveCount(1);
    await expect(page.locator('#project-sessions-table tbody')).toContainText('Synthetic mock request 43');
    await expect(page.locator('#project-sessions-table tbody')).not.toContainText('Synthetic mock request 42');
  });

  test('Glossary only shows its empty state for an unmatched search', async ({ page }) => {
    await page.goto('/glossary', { waitUntil: 'domcontentloaded', timeout: 15_000 });

    const emptyState = page.locator('#glossary-empty');
    await expect(emptyState).toBeHidden();

    const search = page.getByLabel('Search glossary terms');
    await search.fill('no-such-glossary-term');
    await expect(emptyState).toBeVisible();
    await expect(page.locator('#glossary-match-count')).toHaveText('0 条匹配');

    await search.fill('cache read');
    await expect(emptyState).toBeHidden();
    await expect(page.locator('[data-glossary-term]:visible')).not.toHaveCount(0);
  });
});
