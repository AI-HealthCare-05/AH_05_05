import { expect, test } from 'playwright/test';

import { IS_REAL_API, MOCK_ONLY_REASON } from './helpers/mode';

const ASSISTANT_AVATAR = 'img[src="/images/rxvita-mark-128.png"]';

test('스플래시와 튜토리얼을 거쳐 게스트·로그인 홈이 RxVita 로고를 서비스명으로 제공한다', async ({ page }) => {
  await page.addInitScript(() => sessionStorage.removeItem('poke:splash-seen'));
  await page.goto('/');

  const splashLogo = page.getByRole('img', { name: 'RxVita' });
  await expect(splashLogo).toBeVisible();
  await expect(splashLogo).toHaveAttribute('src', '/images/rxvita-logo-960.png');
  await expect(splashLogo).toHaveAttribute('width', '960');
  await expect(splashLogo).toHaveAttribute('height', '248');

  await expect(page).toHaveURL(/\/tutorial$/, { timeout: 3_000 });
  await expect(page.getByRole('heading', { name: /약봉투를 찍으면.*복약 일정이 만들어져요/ })).toBeVisible();
  await page.getByRole('button', { name: '건너뛰기' }).click();
  await expect(page).toHaveURL(/\/home$/);
  let homeHeading = page.getByRole('heading', { level: 1, name: 'RxVita' });
  await expect(homeHeading).toBeVisible();
  await expect(homeHeading.getByRole('img', { name: 'RxVita' })).toHaveAttribute(
    'src',
    '/images/rxvita-logo-480.png',
  );

  await page.goto('/dev/home-active');
  homeHeading = page.getByRole('heading', { level: 1, name: 'RxVita' });
  await expect(homeHeading).toBeVisible();
  await expect(homeHeading.getByRole('img', { name: 'RxVita' })).toHaveAttribute(
    'src',
    '/images/rxvita-logo-480.png',
  );
  await expect(page).toHaveTitle('RxVita · 건강한 복약관리');
});

test('챗 시작 가이드가 장식용 RxVita 마크를 보여준다', async ({ page }) => {
  await page.goto('/dev/chat');

  const guide = page.getByRole('region', { name: '챗봇 시작 가이드' });
  const mark = guide.locator('img[src="/images/rxvita-mark-256.png"]');
  await expect(mark).toBeVisible();
  await expect(mark).toHaveAttribute('alt', '');
  await expect(mark).toHaveAttribute('aria-hidden', 'true');
});

test('연속 어시스턴트 메시지는 첫 메시지에만 아바타를 보이고 같은 들여쓰기를 유지한다', async ({
  page,
}) => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
  const account = 'avatar@example.com';
  const storageKey = `poke.mock-chat-sessions:${encodeURIComponent(account)}`;
  await page.addInitScript(
    ({ principal, key }) => {
      sessionStorage.setItem('poke.access-token', 'avatar-test-token');
      sessionStorage.setItem('poke.account-principal', principal);
      localStorage.setItem(
        key,
        JSON.stringify({
          nextSessionId: 78,
          nextMessageId: 1204,
          sessions: [
            {
              sessionId: 77,
              createdAt: '2026-09-01T00:00:00.000Z',
              lastMessageAt: '2026-09-01T00:00:01.000Z',
              messages: [
                { role: 'user', text: '아바타 확인 질문', sources: [] },
                { role: 'assistant', text: '첫 번째 어시스턴트 답변', sources: [] },
                { role: 'assistant', text: '두 번째 연속 답변', sources: [] },
              ],
            },
          ],
        }),
      );
    },
    { principal: account, key: storageKey },
  );

  await page.goto('/dev/chat');
  await page.getByRole('button', { name: /아바타 확인 질문/ }).click();

  const avatars = page.locator(ASSISTANT_AVATAR);
  await expect(avatars).toHaveCount(1);
  await expect(avatars).toHaveAttribute('alt', '');
  await expect(avatars).toHaveAttribute('aria-hidden', 'true');
  await expect(page.getByText('아바타 확인 질문', { exact: true }).locator('..').locator('img')).toHaveCount(0);

  const firstBubble = page.getByText('첫 번째 어시스턴트 답변', { exact: true }).locator('..');
  const secondBubble = page.getByText('두 번째 연속 답변', { exact: true }).locator('..');
  await expect(firstBubble).toBeVisible();
  await expect(secondBubble).toBeVisible();
  const firstBox = await firstBubble.boundingBox();
  const secondBox = await secondBubble.boundingBox();
  expect(firstBox).not.toBeNull();
  expect(secondBox).not.toBeNull();
  expect(secondBox?.x).toBe(firstBox?.x);
});

test('진행 중 말풍선과 도착한 답변은 아바타를 유지하며 옆으로 움직이지 않는다', async ({ page }) => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
  await page.goto('/dev/chat');

  await page.getByRole('button', { name: '지금 먹는 약을 같이 먹어도 되나요?' }).click();
  const pendingBubble = page.getByText('질문 확인 중', { exact: true });
  await expect(pendingBubble).toBeVisible();
  await expect(page.locator(ASSISTANT_AVATAR)).toHaveCount(1);
  const pendingBox = await pendingBubble.boundingBox();

  const answerText = page.getByText('리바록사반을 복용하는 동안', { exact: false });
  await expect(answerText).toBeVisible();
  const answerBubble = answerText.locator('..');
  const answerBox = await answerBubble.boundingBox();
  expect(pendingBox).not.toBeNull();
  expect(answerBox).not.toBeNull();
  expect(answerBox?.x).toBe(pendingBox?.x);
});

test('마이페이지와 로그인 홈의 영양제 랭킹에서 RxVita 서비스명을 보여준다', async ({ page }) => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
  await page.goto('/dev/my-authenticated');
  await expect(page.getByText('RxVita 사용자', { exact: true })).toBeVisible();

  await page.goto('/dev/home-empty');
  await expect(page.getByText('RxVita가 골랐어요', { exact: true })).toBeVisible();
  await expect(page.getByRole('region', { name: 'RxVita 기능 소개' })).toHaveCount(0);
});
