import { defineConfig } from 'playwright/test';
import base from './playwright.config';

const { channel: _channel, ...use } = base.use ?? {};
export default defineConfig({
  ...base,
  timeout: 60_000,
  use,
  testMatch: ['**/follow-up-visits.spec.ts', '**/my-management-api.spec.ts', '**/remaining-pages.spec.ts'],
  workers: 1,
  projects: [
    { name: 'chromium', use: { browserName: 'chromium', channel: 'chromium' } },
    { name: 'webkit', use: { browserName: 'webkit' } },
  ],
});
