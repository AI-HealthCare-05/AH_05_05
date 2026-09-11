import { defineConfig } from 'playwright/test';
import path from 'node:path';

process.env.VITE_USE_MOCK = 'false';
export default defineConfig({
  testDir: './e2e', testMatch: ['315-detail-claim.spec.ts', '369-badge-award-core.spec.ts'],
  timeout: 60_000, workers: 1, retries: 0, reporter: 'line', outputDir: '../test-results/detail-claim315',
  use: { baseURL: 'http://127.0.0.1:44427', viewport: { width: 390, height: 844 } },
  webServer: {
    command: 'node node_modules/vite/bin/vite.js --config tests/detail-claim.vite.config.ts --host 127.0.0.1 --port 44427 --strictPort --mode e2e-real',
    cwd: path.resolve(import.meta.dirname, '..'), url: 'http://127.0.0.1:44427', reuseExistingServer: false,
    env: { ...process.env, VITE_USE_MOCK: 'false', VITE_API_PROXY_TARGET: 'http://127.0.0.1:9' },
  },
});
