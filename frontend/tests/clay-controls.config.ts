import { defineConfig } from 'playwright/test';
import { fileURLToPath } from 'node:url';

export default defineConfig({
  testDir: './e2e', timeout: 45_000, workers: 1, reporter: 'line',
  outputDir: '../test-results/clay-controls',
  use: {
    baseURL: 'http://127.0.0.1:44422', channel: 'chromium',
    viewport: { width: 390, height: 844 }, video: 'on',
  },
  webServer: {
    cwd: fileURLToPath(new URL('..', import.meta.url)),
    command: 'node node_modules/vite/bin/vite.js --config tests/clay-controls.vite.config.ts --host 127.0.0.1 --port 44422 --strictPort --mode e2e-real',
    url: 'http://127.0.0.1:44422', reuseExistingServer: true,
  },
});
