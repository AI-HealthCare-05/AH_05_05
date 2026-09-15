import { expect, test } from 'playwright/test';
import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);

for (const trigger of ['Enter', 'button'] as const) {
  test(`${trigger} 전송 후 재클릭 없이 다음 질문을 쓰고 응답 중에는 중복 전송하지 않는다`, async ({ page }) => {
    await page.route('https://fonts.googleapis.com/**', route => route.abort());
    let release!: () => void;
    const responseReady = new Promise<void>(resolve => { release = resolve; });
    const requests: string[] = [];
    await page.route('**/api/v1/chat/stream', async route => {
      requests.push(route.request().postDataJSON().message);
      if (requests.length === 1) await responseReady;
      await route.fulfill({ contentType: 'text/event-stream', body:
        'event: complete\ndata: {"conversationId":42,"messageId":101,"answer":"테스트 답변","sources":[]}\n\n' });
    });
    await page.goto('/dev/chat');
    const composer = page.getByRole('textbox', { name: '질문 입력' });
    const send = page.getByRole('button', { name: '보내기', exact: true });
    await composer.fill('첫 질문');
    if (trigger === 'Enter') await page.keyboard.press('Enter');
    else await send.click();
    await expect.poll(() => requests.length).toBe(1);
    await expect(composer).toBeFocused();
    await expect(composer).toBeEditable();
    await page.keyboard.insertText('다음 질문');
    await expect(composer).toHaveValue('다음 질문');
    await expect(send).toBeDisabled();
    await page.keyboard.press('Enter');
    await expect(composer).toHaveValue('다음 질문');
    expect(requests).toEqual(['첫 질문']);
    release();
    await expect(send).toBeEnabled();
    await expect(composer).toBeFocused();
    await page.keyboard.press('Enter');
    await expect.poll(() => requests).toEqual(['첫 질문', '다음 질문']);
  });
}

test('응답이 실패해도 초안은 보존하고 다른 컨트롤로 옮긴 포커스를 빼앗지 않는다', async ({ page }) => {
  let release!: () => void;
  const responseReady = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/api/v1/chat/stream', async route => {
    await responseReady;
    await route.fulfill({ status: 500, json: { message: '테스트 응답 실패' } });
  });
  await page.goto('/dev/chat');
  const composer = page.getByRole('textbox', { name: '질문 입력' });
  const send = page.getByRole('button', { name: '보내기', exact: true });
  await composer.fill('첫 질문');
  await send.click();
  await expect(composer).toBeFocused();
  await page.keyboard.insertText('작성 중인 질문');
  const other = page.getByRole('navigation', { name: '주요 화면' }).getByRole('button').first();
  await other.focus();
  release();
  await expect(send).toBeEnabled();
  await expect(composer).toHaveValue('작성 중인 질문');
  await expect(other).toBeFocused();
});
