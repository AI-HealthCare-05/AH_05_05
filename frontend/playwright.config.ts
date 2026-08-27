import { defineConfig } from 'playwright/test';

const testUseMock = process.env.VITE_USE_MOCK === 'false' ? 'false' : 'true';
const testPort = 44175;
const testMode = testUseMock === 'false' ? 'e2e-real' : 'e2e-mock';
const testVapidPublicKey =
  'BAEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQE';

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: false,
  timeout: 10_000,
  retries: 0,
  reporter: 'line',
  use: {
    baseURL: `http://127.0.0.1:${testPort}`,
    channel: 'chrome',
    viewport: { width: 375, height: 812 },
  },
  webServer: {
    command: `node node_modules/vite/bin/vite.js --host 127.0.0.1 --port ${testPort} --mode ${testMode}`,
    url: `http://127.0.0.1:${testPort}`,
    reuseExistingServer: true,
    env: {
      ...process.env,
      VITE_VAPID_PUBLIC_KEY: testVapidPublicKey,
    },
  },
});
