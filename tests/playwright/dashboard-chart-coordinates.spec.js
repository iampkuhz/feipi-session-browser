/**
 * dashboard-chart-coordinates.spec.js — Dashboard chart coordinate guard.
 *
 * Verifies that SVG line layers and HTML marker/hover layers share the same
 * computed coordinate space. This catches regressions where a line SVG falls
 * back to its 1:1 viewBox aspect ratio instead of filling the plot width.
 */
const { test, expect } = require('@playwright/test');

async function readLineLayerMetrics(page, chartSelector, layerSelector, pathSelector) {
  return await page.evaluate(({ chartSelector, layerSelector, pathSelector }) => {
    const chart = document.querySelector(chartSelector);
    if (!chart) throw new Error(`Missing chart ${chartSelector}`);

    const plot = chart.querySelector('.plot');
    const svg = chart.querySelector('svg.line-plot--bar-aligned');
    const layer = chart.querySelector(layerSelector);
    const path = chart.querySelector(pathSelector);
    const points = Array.from(layer.querySelectorAll('.line-point'));

    if (!plot) throw new Error(`Missing plot in ${chartSelector}`);
    if (!svg) throw new Error(`Missing line SVG in ${chartSelector}`);
    if (!layer) throw new Error(`Missing marker layer ${layerSelector}`);
    if (!path) throw new Error(`Missing line path ${pathSelector}`);

    const rect = (el) => {
      const r = el.getBoundingClientRect();
      return {
        left: r.left,
        top: r.top,
        width: r.width,
        height: r.height,
        right: r.right,
        bottom: r.bottom,
      };
    };

    const coords = Array.from((path.getAttribute('d') || '').matchAll(/[ML]\s*([0-9.-]+),([0-9.-]+)/g))
      .map((match) => ({ x: Number(match[1]), y: Number(match[2]) }));

    const svgRect = rect(svg);
    const toScreen = (coord) => ({
      x: svgRect.left + (coord.x / 100) * svgRect.width,
      y: svgRect.top + (coord.y / 100) * svgRect.height,
    });

    const center = (el) => {
      const r = el.getBoundingClientRect();
      return {
        x: r.left + r.width / 2,
        y: r.top + r.height / 2,
      };
    };

    return {
      plot: rect(plot),
      svg: svgRect,
      layer: rect(layer),
      firstPathPoint: coords.length >= 2 ? toScreen(coords[0]) : null,
      lastPathPoint: coords.length >= 2 ? toScreen(coords[coords.length - 1]) : null,
      firstMarker: points.length >= 2 ? center(points[0]) : null,
      lastMarker: points.length >= 2 ? center(points[points.length - 1]) : null,
      pointCount: points.length,
      pathPointCount: coords.length,
    };
  }, { chartSelector, layerSelector, pathSelector });
}

function expectClose(actual, expected, message, tolerance = 1.5) {
  expect(Math.abs(actual - expected), `${message}: expected ${actual} ~= ${expected}`).toBeLessThanOrEqual(tolerance);
}

async function assertLineLayerAligned(page, spec) {
  const metrics = await readLineLayerMetrics(page, spec.chartSelector, spec.layerSelector, spec.pathSelector);

  expect(metrics.svg.width, `${spec.name}: SVG width must not collapse to a square`).toBeGreaterThan(metrics.plot.width * 0.9);
  expectClose(metrics.svg.left, metrics.layer.left, `${spec.name}: SVG/layer left`);
  expectClose(metrics.svg.width, metrics.layer.width, `${spec.name}: SVG/layer width`);

  if (metrics.pointCount >= 2 && metrics.pathPointCount >= 2) {
    expectClose(metrics.firstPathPoint.x, metrics.firstMarker.x, `${spec.name}: first marker x`);
    expectClose(metrics.firstPathPoint.y, metrics.firstMarker.y, `${spec.name}: first marker y`);
    expectClose(metrics.lastPathPoint.x, metrics.lastMarker.x, `${spec.name}: last marker x`);
    expectClose(metrics.lastPathPoint.y, metrics.lastMarker.y, `${spec.name}: last marker y`);
  }
}

test.describe('Dashboard chart coordinates', () => {
  test('[DASHBOARD-CHART-001] Prompt Activity and Cache Health line markers align with SVG paths', async ({ page }) => {
    await page.setViewportSize({ width: 1880, height: 1400 });
    await page.goto('/dashboard', { waitUntil: 'domcontentloaded', timeout: 15000 });
    await expect(page.locator('#prompt-activity-chart svg.line-plot--bar-aligned')).toBeAttached({ timeout: 10000 });
    await expect(page.locator('#cache-health-chart svg.line-plot--bar-aligned')).toBeAttached({ timeout: 10000 });

    await assertLineLayerAligned(page, {
      name: 'Prompt Activity',
      chartSelector: '#prompt-activity-chart',
      layerSelector: '.prompt-line-markers',
      pathSelector: 'path.line-series--prompt-average',
    });

    await assertLineLayerAligned(page, {
      name: 'Cache Health',
      chartSelector: '#cache-health-chart',
      layerSelector: '.line-targets--bar-aligned',
      pathSelector: 'path.line-series--highlight',
    });
  });
});
