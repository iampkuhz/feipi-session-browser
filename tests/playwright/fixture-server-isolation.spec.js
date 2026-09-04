import { test, expect } from '@playwright/test';

const { SPEC } = require('../fixtures/generate-session-fixtures');

test('[HOOK-HARNESS-016] Java fixture server only exposes synthetic Claude sessions', async ({
  request,
}) => {
  const expectedSessionCount = SPEC.mockCount + 2;
  const summaryResponse = await request.get('/api/sessions/summary');
  const rowsResponse = await request.get('/api/sessions/rows?page_size=100');

  expect(summaryResponse.ok()).toBe(true);
  expect(rowsResponse.ok()).toBe(true);

  const summary = await summaryResponse.json();
  const rowsPayload = await rowsResponse.json();
  const rows = rowsPayload.rows;

  expect(summary.totalCount).toBe(expectedSessionCount);
  expect(summary.projectCount).toBe(2);
  expect(rowsPayload.pagination.totalItems).toBe(expectedSessionCount);
  expect(rows).toHaveLength(expectedSessionCount);
  expect(rows.every((row) => row.agent === 'claude_code')).toBe(true);
  expect(new Set(rows.map((row) => row.projectKey))).toEqual(new Set([
    'test-hifi-project',
    'synthetic/workspace/projects/feipi-session-browser',
  ]));
});
