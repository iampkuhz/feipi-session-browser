const { test, expect } = require('@playwright/test');
const fs = require('fs');
const { pathToFileURL } = require('url');

// 使用真实全文 snapshot，只替换合成长标识文本，不改 CSS、链接或资源。
const exportPath = '/sessions/claude_code/hifi-viz-session-001/export.html';
const longValues = [
  `syntheticCallId${'Y'.repeat(160)}End`,
  `syntheticToolId${'X'.repeat(180)}End`,
  `syntheticPayloadId${'Z'.repeat(220)}End`,
  `SyntheticPayloadBody${'W'.repeat(220)}End`,
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
      const calls = page.locator('details[id^="call-"]');
      const tools = page.locator('details[id^="tool-"]');
      expect(await calls.count()).toBeGreaterThan(0);
      expect(await tools.count()).toBeGreaterThan(0);
      expect(await page.locator('pre').count()).toBeGreaterThanOrEqual(2 * (await calls.count() + await tools.count()));
      const measurement = await page.locator('body > p').allTextContents();
      expect(measurement.join('\n')).toContain('Trace rows:');
      expect(measurement.join('\n')).toContain('Total tokens:');
      expect(measurement.join('\n')).toContain('模型耗时未测量。工具时长仅使用来源观测');
      expect(measurement.join('\n')).toContain('优先使用 HTML');
      expect((await page.locator('pre').allTextContents()).some(text => text.trim())).toBe(true);

      await page.evaluate((values) => {
        const call = document.querySelector('details[id^="call-"]');
        const tool = document.querySelector('details[id^="tool-"]');
        const payload = [...call.querySelectorAll(':scope > p')].find(node => node.textContent.startsWith('payloadId:'));
        const nodes = [call.querySelector('summary'), tool.querySelector('summary'), payload, call.querySelector('pre')];
        nodes.forEach((node, index) => {
          node.dataset.layoutLong = String(index);
          node.textContent += ` ${values[index]}`;
        });
        document.querySelectorAll('details').forEach(node => { node.open = true; });
      }, longValues);
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
      expect(await page.locator('body > p').allTextContents()).toEqual(measurement);
      for (const [index, value] of longValues.entries()) {
        const node = page.locator(`[data-layout-long="${index}"]`);
        await expect(node).toContainText(value);
        await expect(node).toBeVisible();
      }

      const layout = await page.evaluate(() => {
        const issues = [];
        if (document.documentElement.scrollWidth > innerWidth + 1) issues.push('Page has horizontal overflow');
        const nodes = [...document.querySelectorAll('[data-layout-long]')];
        const measurements = nodes.map((node) => {
          const index = Number(node.dataset.layoutLong);
          const style = getComputedStyle(node);
          const box = node.getBoundingClientRect();
          if (box.left < 0 || box.right > innerWidth + 1) issues.push(`Node ${index} exceeds viewport`);
          if (node.scrollWidth > node.clientWidth + 1) issues.push(`Node ${index} has horizontal overflow`);
          if (style.display === 'none' || style.visibility !== 'visible' || style.opacity === '0'
            || ['hidden', 'clip'].includes(style.overflowX) || ['hidden', 'clip'].includes(style.overflowY)
            || style.textOverflow === 'ellipsis' || box.width === 0 || box.height === 0) {
            issues.push(`Node ${index} hides content`);
          }
          const range = document.createRange();
          range.selectNodeContents(node);
          const fragments = [...range.getClientRects()];
          for (const fragment of fragments) {
            if (fragment.left < box.left - 1 || fragment.right > box.right + 1
              || fragment.top < box.top - 1 || fragment.bottom > box.bottom + 1) {
              issues.push(`Node ${index} text exceeds its bounds`);
              break;
            }
          }
          const lines = new Set(fragments.map(line => line.top)).size;
          if (lines < 2) issues.push(`Long node ${index} does not wrap`);
          return { index, lines, scrollWidth: node.scrollWidth, clientWidth: node.clientWidth, overflowWrap: style.overflowWrap };
        });
        return { issues, viewport: innerWidth, scrollWidth: document.documentElement.scrollWidth, measurements };
      });
      fs.writeFileSync(testInfo.outputPath('layout.json'), JSON.stringify(layout, null, 2));
      expect(layout.issues, `offline payload layout at ${width}px`).toEqual([]);
      await page.locator('[data-layout-long="0"]').screenshot({ path: testInfo.outputPath('call-summary.png') });
      await page.locator('[data-layout-long="1"]').screenshot({ path: testInfo.outputPath('tool-summary.png') });

      // 保留原生展开和实际 HTML 来源定位，不用脚本模拟导航。
      const call = calls.first();
      await call.locator(':scope > summary').click();
      await expect(call).not.toHaveAttribute('open');
      await call.locator(':scope > summary').focus();
      await page.keyboard.press('Enter');
      await expect(call).toHaveAttribute('open');
      for (const name of ['模型输入', '模型输出']) {
        const link = tools.first().getByRole('link', { name, exact: true });
        const href = await link.getAttribute('href');
        expect(href).toMatch(/^#(?:input|output)-[a-f0-9]{64}$/);
        await link.click();
        expect(new URL(page.url()).hash).toBe(href);
        await expect(page.locator(href)).toBeVisible();
      }
      expect(externalRequests).toEqual([]);
    } finally {
      await context.close();
    }
  });
}
