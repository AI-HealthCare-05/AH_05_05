import { expect, test } from 'playwright/test';

import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);

test('SSE에서는 검증 완료 이벤트의 답변만 말풍선으로 표시한다', async ({ page }) => {
  await page.route('**/api/v1/chat/stream', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream; charset=utf-8',
      body: [
        'event: progress',
        'data: {"stage":"ANSWER_GENERATING","message":"검사 전 원문을 표시하면 안 됩니다"}',
        '',
        'event: progress',
        'data: {"stage":"SAFETY_CHECKING","message":"안전 확인 중"}',
        '',
        'event: complete',
        'data: {"conversationId":42,"messageId":101,"answer":"안전성 검사를 통과한 최종 답변입니다.","sources":[]}',
        '',
        '',
      ].join('\n'),
    });
  });

  await page.goto('/dev/chat');
  const question = '이 약은 왜 먹는 건가요?';
  await page.getByRole('button', { name: question }).click();

  await expect(page.getByText('안전성 검사를 통과한 최종 답변입니다.')).toBeVisible();
  await expect(page.getByText('검사 전 원문을 표시하면 안 됩니다')).toHaveCount(0);
});
