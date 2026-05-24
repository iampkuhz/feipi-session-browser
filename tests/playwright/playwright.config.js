// Temporary Playwright config for baseline generation
const path = require('path');
const { defineConfig } = require('@playwright/test');

module.exports = defineConfig({
  testDir: '.',
  use: {
    baseURL: process.env.BASE_URL || 'http://127.0.0.1:18999',
  },
  projects: [
    {
      name: 'chromium',
      use: { browserName: 'chromium' },
    },
  ],
});
