import { expect, test } from 'playwright/test';

import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

const ACCESS_TOKEN = 'e2e-chat-list-token';

test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);

test('실 API 대화 목록에서 세션을 선택해 저장된 메시지를 연다', async ({ page }) => {
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

  await page.route('**/api/v1/chat/sessions/101', async (route) => {
    const request = route.request();
    expect(request.method()).toBe('GET');
    expect(new URL(request.url()).pathname).toBe('/api/v1/chat/sessions/101');
    expect(request.headers().authorization).toBe(`Bearer ${ACCESS_TOKEN}`);

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: {
          sessionId: 101,
          careEpisodeKey: null,
          status: 'ACTIVE',
          lastMessageAt: '2026-09-02T09:00:00+09:00',
          createdAt: '2026-09-02T08:50:00+09:00',
          messages: [
            {
              messageId: 1001,
              role: 'USER',
              content: '아침 약은 언제 먹나요?',
              status: 'COMPLETED',
              replyToMessageId: null,
              guideId: null,
              sources: [],
              createdAt: '2026-09-02T08:55:00+09:00',
            },
            {
              messageId: 1002,
              role: 'ASSISTANT',
              content: '식후에 드시는 편이 좋아요.',
              status: 'COMPLETED',
              replyToMessageId: 1001,
              guideId: null,
              sources: [
                {
                  sourceType: 'PUBLIC_DATA',
                  sourceName: '의약품안전나라',
                  vectorChunkId: 'medicine-guide:101',
                  sourceOrganization: '식품의약품안전처',
                  sourceUrl: 'https://example.com/medicine',
                  datasetVersion: '20260902',
                },
              ],
              createdAt: '2026-09-02T09:00:00+09:00',
            },
            {
              messageId: 1003,
              role: 'ASSISTANT',
              content: '화면에 표시하면 안 되는 처리 중 답변',
              status: 'PENDING',
              replyToMessageId: 1001,
              guideId: null,
              sources: [],
              createdAt: '2026-09-02T09:01:00+09:00',
            },
          ],
        },
        error: null,
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
  await expect(page.getByRole('button', { name: '대화 삭제' })).toBeVisible();

  await recentConversations.getByRole('button', { name: /아침 복약 상담/ }).click();

  await expect(page.getByText('아침 약은 언제 먹나요?', { exact: true })).toBeVisible();
  await expect(page.getByText('식후에 드시는 편이 좋아요.', { exact: true })).toBeVisible();
  await expect(page.getByText('의약품안전나라', { exact: true })).toBeVisible();
  await expect(page.getByText('화면에 표시하면 안 되는 처리 중 답변')).toHaveCount(0);
});
