import { defineConfig } from 'playwright/test';
import base from './playwright.config';
const { channel: _channel, ...use } = base.use ?? {};
export default defineConfig({ ...base, use, testMatch: '**/563-calendar.spec.ts', workers: 1,
  projects: [{ name: 'chromium', use: { browserName: 'chromium', channel: 'chromium' } }, { name: 'webkit', use: { browserName: 'webkit' } }],
});
