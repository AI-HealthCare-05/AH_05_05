import { expect, test } from 'playwright/test';

const MOCK_CHAT_STORAGE_KEY = 'poke.mock-chat-sessions';

test.beforeEach(async ({ page }) => {
  await page.goto('/dev/chat');
  await page.evaluate((key) => localStorage.removeItem(key), MOCK_CHAT_STORAGE_KEY);
  await page.evaluate(() => sessionStorage.setItem('poke.access-token', 'e2e-chat-token'));
  await page.reload();
});

test('다른 하단 탭에 다녀오면 활성 채팅방과 메시지를 다시 불러온다', async ({ page }) => {
  const question = '지금 먹는 약을 같이 먹어도 되나요?';
  await page.getByRole('button', { name: question }).click();
  await expect(page.getByText('리바록사반을 복용하는 동안', { exact: false })).toBeVisible();

  await page.getByRole('button', { name: '홈' }).click();
  await page.getByRole('button', { name: '챗봇' }).click();

  await expect(page.getByText(question, { exact: true })).toBeVisible();
  await expect(page.getByText('리바록사반을 복용하는 동안', { exact: false })).toBeVisible();
});
