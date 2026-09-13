import { defineConfig } from 'playwright/test';

const port = Number(process.env.PLAYWRIGHT_TEST_PORT ?? '45547');

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 30_000,
  reporter: 'line',
  outputDir: './node_modules/.playwright-447-results',
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    channel: process.env.PLAYWRIGHT_CHANNEL || undefined,
    viewport: { width: 390, height: 844 },
  },
  webServer: {
    command: `${JSON.stringify(process.execPath)} tests/e2e/helpers/447-server.mjs`,
    url: `http://127.0.0.1:${port}`,
    reuseExistingServer: false,
    timeout: 30_000,
    env: {
      ...process.env,
      PLAYWRIGHT_TEST_PORT: String(port),
    },
  },
});
