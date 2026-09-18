import { defineConfig } from 'playwright/test';
import base from './playwright.config';

const { channel: _chromiumChannel, ...sharedUse } = base.use ?? {};

export default defineConfig({
  ...base,
  use: sharedUse,
  testMatch: '**/556-input-focus-zoom.spec.ts',
  workers: 1,
  projects: [
    { name: 'chromium', use: { browserName: 'chromium', channel: 'chromium' } },
    { name: 'webkit', use: { browserName: 'webkit' } },
  ],
});
