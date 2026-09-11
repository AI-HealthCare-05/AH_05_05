import { defineConfig } from 'playwright/test';
import { fileURLToPath } from 'node:url';

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  workers: 1,
  reporter: 'line',
  outputDir: '../test-results/auth-stagger',
  use: { baseURL: 'http://127.0.0.1:44420', channel: 'chromium', viewport: { width: 390, height: 844 } },
  webServer: {
    cwd: fileURLToPath(new URL('..', import.meta.url)),
    command: 'node node_modules/vite/bin/vite.js --config tests/auth-stagger.vite.config.ts --host 127.0.0.1 --port 44420 --strictPort --mode e2e-real',
    url: 'http://127.0.0.1:44420',
    reuseExistingServer: true,
  },
});
