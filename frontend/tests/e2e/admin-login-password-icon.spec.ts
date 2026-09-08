import { readFile } from 'node:fs/promises';

import { expect, test } from 'playwright/test';

test('관리자 로그인 비밀번호 입력에는 현재 상태의 눈 아이콘만 표시한다', async ({ page }) => {
  const [html, styles] = await Promise.all([
    readFile(new URL('../../../app/static/templates/login.html', import.meta.url), 'utf8'),
    readFile(new URL('../../../app/static/css/styles.css', import.meta.url), 'utf8'),
  ]);
  await page.setContent(html.replace('</head>', `<style>${styles}</style></head>`));

  await expect(page.locator('[data-password-icon="eye"]')).toBeHidden();
  await expect(page.locator('[data-password-icon="eye-off"]')).toBeVisible();
});
