import { expect, test } from 'playwright/test';
import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
test.use({ screenshot: 'only-on-failure' });

test('저장된 답변의 안전 안내와 출처를 유지하고 참고정보 안내를 입력창 위에 표시한다', async ({ page }, testInfo) => {
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', '390-synthetic-preview');
    sessionStorage.setItem('poke.account-principal', '390-preview@example.com');
  });
  await page.route(/^https:\/\//, route => route.abort());
  await page.route('**/api/v1/**', route => route.abort());
  await page.route('**/api/v1/chat/sessions', route => route.fulfill({ json: {
    items: [{ sessionId: 390, title: '약 복용 전 확인할 내용', lastMessagePreview: '약 봉투와 처방 안내를 확인하세요.', lastMessageAt: '2026-09-10T09:00:00+09:00' }],
  } }));
  await page.route('**/api/v1/chat/sessions/390', route => route.fulfill({ json: {
    success: true, error: null, data: {
      sessionId: 390, careEpisodeKey: null, status: 'ACTIVE',
      lastMessageAt: '2026-09-10T09:00:00+09:00', createdAt: '2026-09-10T09:00:00+09:00',
      messages: [
        { messageId: 3901, role: 'USER', content: '약을 먹기 전에 무엇을 확인하나요?', status: 'COMPLETED', replyToMessageId: null, sources: [], createdAt: '2026-09-10T09:00:00+09:00' },
        { messageId: 3902, role: 'ASSISTANT', content: '**복용 전 확인해 주세요.**\n\n약 봉투에 적힌 복용 시간과 용량을 확인하세요. 궁금한 점은 약사에게 문의하세요.', status: 'COMPLETED', replyToMessageId: 3901,
          sources: [{ sourceType: 'PUBLIC_DATA', sourceName: '의약품안전나라', vectorChunkId: 'preview:390', sourceOrganization: '식품의약품안전처', sourceUrl: 'https://example.com/medicine', datasetVersion: '20260910' }], createdAt: '2026-09-10T09:00:00+09:00' },
      ],
    },
  } }));
  await page.goto('/chat');
  await page.getByRole('button', { name: /약 복용 전 확인할 내용/ }).click({ timeout: 15000 });
  const main = page.getByRole('main');
  const aiNotice = main.getByText('이 답변은 AI가 생성한 답변입니다', { exact: true });
  const referenceNotice = main.getByText('이 안내는 보유한 자료를 바탕으로 한 참고 정보이며 의료진의 진료, 진단 또는 처방을 대체하지 않습니다. 복용 시작·중단·용량 변경은 의료진 또는 약사와 상의하세요.', { exact: true });
  await page.getByRole('button', { name: '근거 보기 1개', exact: true }).click();
  for (const width of [390, 320, 1280]) {
    await page.setViewportSize({ width, height: 1000 });
    await main.evaluate(el => { el.scrollTop = el.scrollHeight; });
    await expect(aiNotice).toBeVisible();
    await expect(referenceNotice).toBeVisible();
    await expect(main.getByLabel('주의와 한계')).toContainText('이 답변은 진단이나 처방을 대신하지 않아요.');
    await expect(main.getByText('의약품안전나라', { exact: true })).toBeVisible();
    const input = (await page.getByRole('textbox', { name: '질문 입력' }).boundingBox())!;
    const notice = (await referenceNotice.boundingBox())!;
    expect(notice.y + notice.height).toBeLessThan(input.y);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`chat-notice-${width}.png`), fullPage: true });
  }
});
