import { expect, test, type Page } from 'playwright/test';

const MOCK_CHAT_STORAGE_KEY = 'poke.mock-chat-sessions';

test.setTimeout(30_000);

async function createConversation(page: Page, question: string) {
  await page.getByRole('textbox', { name: '질문 입력' }).fill(question);
  await page.getByRole('button', { name: '보내기' }).click();
  await expect(page.getByText('리바록사반을 복용하는 동안', { exact: false })).toBeVisible();
}

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

test('새로고침하면 최신 대화 목록을 보여주고 선택한 세션을 연다', async ({ page }) => {
  const question = '영양제와 같이 먹어도 괜찮나요?';
  await page.getByRole('button', { name: question }).click();
  await expect(page.getByText('리바록사반을 복용하는 동안', { exact: false })).toBeVisible();

  await page.reload();
  await expect(page.getByRole('heading', { name: '최근 대화' })).toBeVisible();
  const row = page.getByRole('button', { name: new RegExp(question) });
  await expect(row).toContainText(question);
  await expect(row).toContainText('리바록사반을 복용하는 동안');

  await row.click();
  await expect(page.getByText(question, { exact: true })).toBeVisible();
});

test('새 채팅 버튼은 빈 세션을 저장하지 않고 시작 가이드를 연다', async ({ page }) => {
  const question = '이 약은 왜 먹는 건가요?';
  await page.getByRole('button', { name: question }).click();
  await expect(page.getByText('리바록사반을 복용하는 동안', { exact: false })).toBeVisible();
  await page.reload();

  await page.getByRole('button', { name: '새 채팅' }).click();
  await expect(page.getByRole('region', { name: '챗봇 시작 가이드' })).toBeVisible();
  await page.reload();

  await expect(page.getByRole('heading', { name: '최근 대화' })).toBeVisible();
  await expect(page.getByRole('button', { name: new RegExp(question) })).toHaveCount(1);
});

test('선택 모드에서 마우스로 여러 대화를 고르고 삭제할 수 있다', async ({ page }) => {
  await createConversation(page, '첫 번째 상담 질문');
  await page.reload();
  await page.getByRole('button', { name: '새 채팅' }).click();
  await createConversation(page, '두 번째 상담 질문');
  await page.reload();

  await page.getByRole('button', { name: '대화 선택' }).click();
  await page.getByRole('checkbox', { name: /첫 번째 상담 질문/ }).check();
  await page.getByRole('checkbox', { name: /두 번째 상담 질문/ }).check();
  await expect(page.getByRole('button', { name: '2개 삭제' })).toBeEnabled();

  await page.getByRole('button', { name: '2개 삭제' }).click();
  await page.getByRole('button', { name: '취소' }).click();
  await expect(page.getByText('첫 번째 상담 질문', { exact: true })).toBeVisible();

  await page.getByRole('button', { name: '2개 삭제' }).click();
  await page.getByRole('button', { name: '삭제' }).click();
  await expect(page.getByRole('region', { name: '챗봇 시작 가이드' })).toBeVisible();
});
