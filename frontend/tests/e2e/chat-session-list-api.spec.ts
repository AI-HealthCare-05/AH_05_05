import { expect, test } from 'playwright/test';

import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

const ACCESS_TOKEN = 'e2e-chat-list-token';

test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);

test('실 API 대화 목록을 GET으로 조회해 최근 대화에 렌더링한다', async ({ page }) => {
  await page.addInitScript((token) => {
    window.sessionStorage.setItem('poke.access-token', token);
    window.sessionStorage.setItem('poke.account-principal', 'chat-list-e2e@example.com');
  }, ACCESS_TOKEN);

  await page.route('**/api/v1/chat/sessions', async (route) => {
    const request = route.request();
    expect(request.method()).toBe('GET');
    expect(new URL(request.url()).pathname).toBe('/api/v1/chat/sessions');
    expect(request.headers().authorization).toBe(`Bearer ${ACCESS_TOKEN}`);

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        items: [
          {
            sessionId: 101,
            title: '아침 복약 상담',
            lastMessagePreview: '식후에 드시는 편이 좋아요.',
            lastMessageAt: '2026-09-02T09:00:00+09:00',
          },
          {
            sessionId: 102,
            title: '영양제 병용 질문',
            lastMessagePreview: '성분이 겹치는지 먼저 확인할게요.',
            lastMessageAt: '2026-09-01T18:30:00+09:00',
          },
        ],
      }),
    });
  });

  await page.goto('/chat');

  const recentConversations = page.getByRole('heading', { name: '최근 대화' }).locator('..');
  await expect(recentConversations.getByRole('button', { name: /아침 복약 상담/ })).toContainText(
    '식후에 드시는 편이 좋아요.',
  );
  await expect(recentConversations.getByRole('button', { name: /영양제 병용 질문/ })).toContainText(
    '성분이 겹치는지 먼저 확인할게요.',
  );
});
