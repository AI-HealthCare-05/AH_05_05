import { expect, test } from 'playwright/test';

import { IS_REAL_API, MOCK_ONLY_REASON } from './helpers/mode';

test.beforeEach(() => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
});

test.setTimeout(30_000);

test('평가 사유는 공통코드 다섯 개를 표시하고 처음에는 선택하지 않는다', async ({ page }) => {
  await page.goto('/dev/chat');
  await page.getByRole('button', { name: '지금 먹는 약을 같이 먹어도 되나요?' }).click();
  await expect(page.getByText('리바록사반을 복용하는 동안', { exact: false })).toBeVisible();

  await page.getByRole('button', { name: '채팅 종료' }).click();
  const endSheet = page.getByRole('dialog', { name: '상담 종료' });
  await endSheet.getByRole('button', { name: '좋아요' }).click();

  const positiveSheet = page.getByRole('dialog', { name: '상담 평가' });
  const reasonButtons = positiveSheet.locator('button[aria-pressed]');
  await expect(reasonButtons).toHaveCount(5);
  for (let index = 0; index < 5; index += 1) {
    await expect(reasonButtons.nth(index)).toHaveAttribute('aria-pressed', 'false');
  }
});

test('선택한 평가 사유는 코드로 저장되고 사유를 해제해도 제출할 수 있다', async ({ page }) => {
  await page.goto('/dev/chat');
  await page.getByRole('button', { name: '지금 먹는 약을 같이 먹어도 되나요?' }).click();
  await expect(page.getByText('리바록사반을 복용하는 동안', { exact: false })).toBeVisible();

  await page.getByRole('button', { name: '채팅 종료' }).click();
  await page.getByRole('dialog', { name: '상담 종료' }).getByRole('button', { name: '좋아요' }).click();

  const positiveSheet = page.getByRole('dialog', { name: '상담 평가' });
  const reasonButtons = positiveSheet.locator('button[aria-pressed]');
  await expect(reasonButtons).toHaveCount(5);
  await reasonButtons.nth(1).click();
  await expect(reasonButtons.nth(1)).toHaveAttribute('aria-pressed', 'true');
  await reasonButtons.nth(1).click();
  await expect(reasonButtons.nth(1)).toHaveAttribute('aria-pressed', 'false');
  await positiveSheet.getByRole('button', { name: '제출하고 종료' }).click();

  await expect(page.getByRole('dialog')).toHaveCount(0);
  const sessions = await page.evaluate(() => {
    const raw = localStorage.getItem('poke.mock-chat-sessions:guest');
    return raw
      ? (JSON.parse(raw) as {
          sessions: Array<{ isLike?: boolean | null; reasonCode?: string | null }>;
        }).sessions
      : [];
  });
  expect(sessions.at(-1)).toMatchObject({ isLike: true, reasonCode: null });
});
