const { test, expect } = require('@playwright/test');
const fs = require('fs');
const { pathToFileURL } = require('url');

// Fetch the packaged synthetic fixture export; change only table text, never CSS or resources.
const exportPath = '/sessions/claude_code/hifi-viz-session-001/export.html';
const longCells = [
  [0, `syntheticPayloadId${'X'.repeat(180)}End`],
  [2, `syntheticCallId${'Y'.repeat(160)}End`],
  [3, `SyntheticPayloadTitle${'Z'.repeat(220)}End`],
];

for (const width of [1440, 800]) {
  test(`static export wraps complete long payload identifiers offline at ${width}px`, async ({ browser, request }, testInfo) => {
    const response = await request.get(exportPath);
    expect(response.ok()).toBeTruthy();
    const html = await response.text();
    expect(html).toMatch(/^<!DOCTYPE html>/);
    expect(html).not.toMatch(/<(?:script|link|img|iframe|object|embed)\b|@import\b|url\(/i);

    const context = await browser.newContext({
      javaScriptEnabled: false,
      offline: true,
      viewport: { width, height: 1100 },
    });
    try {
      const page = await context.newPage();
      await page.setContent(html);
      const row = page.locator('.payload-table tbody tr').first();
      await expect(row.locator('td')).toHaveCount(5);
      const measurement = await page.locator('.sd-metrics, [data-export-token-provenance], .visibility-note').allTextContents();
      expect(measurement[0].trim()).not.toBe('');
      await row.evaluate((element, replacements) => {
        for (const [column, value] of replacements) element.cells[column].textContent = value;
      }, longCells);
      const expectedBody = await page.locator('body').textContent();
      const offlineFile = testInfo.outputPath(`synthetic-export-${width}.html`);
      fs.mkdirSync(testInfo.outputDir, { recursive: true });
      fs.writeFileSync(offlineFile, await page.content(), { mode: 0o600 });

      const externalRequests = [];
      page.on('request', (item) => {
        if (!item.url().startsWith('file:')) externalRequests.push(item.url());
      });
      await page.goto(pathToFileURL(offlineFile).href);
      expect(new URL(page.url()).protocol).toBe('file:');
      await expect(page.locator('body')).toHaveText(expectedBody, { useInnerText: false });
      expect(await page.locator('.sd-metrics, [data-export-token-provenance], .visibility-note').allTextContents()).toEqual(measurement);
      for (const [column, value] of longCells) {
        await expect(row.locator('td').nth(column)).toHaveText(value);
        await expect(row.locator('td').nth(column)).toBeVisible();
      }

      const layout = await page.evaluate(() => {
        const issues = [];
        if (document.documentElement.scrollWidth > innerWidth + 1) issues.push('Page has horizontal overflow');
        const table = document.querySelector('.payload-table');
        const tableBox = table.getBoundingClientRect();
        if (tableBox.left < 0 || tableBox.right > innerWidth + 1) issues.push('Payload table exceeds viewport');
        table.querySelectorAll('th, td').forEach((cell, index) => {
          const style = getComputedStyle(cell);
          const box = cell.getBoundingClientRect();
          if (cell.scrollWidth > cell.clientWidth + 1) issues.push(`Cell ${index} has horizontal overflow`);
          if (style.display === 'none' || style.visibility !== 'visible' || style.opacity === '0'
            || ['hidden', 'clip'].includes(style.overflowX) || ['hidden', 'clip'].includes(style.overflowY)
            || style.textOverflow === 'ellipsis' || box.width === 0 || box.height === 0) {
            issues.push(`Cell ${index} hides content`);
          }
          const range = document.createRange();
          range.selectNodeContents(cell);
          for (const fragment of range.getClientRects()) {
            if (fragment.left < box.left - 1 || fragment.right > box.right + 1
              || fragment.top < box.top - 1 || fragment.bottom > box.bottom + 1) {
              issues.push(`Cell ${index} text exceeds its bounds`);
              break;
            }
          }
        });
        for (const column of [0, 2, 3]) {
          const range = document.createRange();
          range.selectNodeContents(table.tBodies[0].rows[0].cells[column]);
          if (new Set([...range.getClientRects()].map((line) => line.top)).size < 2) {
            issues.push(`Long column ${column} does not wrap`);
          }
        }
        table.querySelectorAll('td:nth-child(2) .payload-kind, td:nth-child(5)').forEach((label) => {
          const range = document.createRange();
          range.selectNodeContents(label);
          if (new Set([...range.getClientRects()].map((line) => line.top)).size > 1) {
            issues.push('Short kind/status label is squeezed into multiple lines');
          }
        });
        return issues;
      });
      expect(layout, `offline payload layout at ${width}px`).toEqual([]);
      expect(externalRequests).toEqual([]);
    } finally {
      await context.close();
    }
  });
}
