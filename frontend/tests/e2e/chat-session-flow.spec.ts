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

  await page.getByRole('button', { name: '뒤로' }).click();
  await expect(page.getByRole('heading', { name: '최근 대화' })).toBeVisible();
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

test('대화 목록 조회 실패는 화면 안 카드에서 다시 시도할 수 있다', async ({ page }) => {
  await page.goto('/dev/chat-session-list-error');

  await expect(page.getByText('대화 목록을 불러오지 못했어요.', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '다시 시도' })).toBeVisible();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.getByRole('region', { name: '챗봇 시작 가이드' })).toBeVisible();
});

test('375px 목록과 선택 화면은 가로로 넘치지 않고 조작 이름을 제공한다', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await createConversation(page, '작은 화면 상담 질문');
  await page.reload();

  await expect(page.getByRole('button', { name: '새 채팅' })).toBeVisible();
  await expect(page.getByRole('button', { name: '대화 선택' })).toBeVisible();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
  ).toBe(true);

  await page.getByRole('button', { name: '대화 선택' }).click();
  await expect(page.getByRole('checkbox', { name: /작은 화면 상담 질문 선택/ })).toBeVisible();
  await expect(page.getByRole('button', { name: '0개 삭제' })).toBeDisabled();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
  ).toBe(true);
});

test('대화 삭제 실패 뒤에도 선택 상태를 유지해 다시 시도할 수 있다', async ({ page }) => {
  await createConversation(page, '삭제 실패 확인 질문');
  await page.goto('/dev/chat-delete-error');

  await page.getByRole('button', { name: '대화 선택' }).click();
  const checkbox = page.getByRole('checkbox', { name: /삭제 실패 확인 질문 선택/ });
  await checkbox.check();
  await page.getByRole('button', { name: '1개 삭제' }).click();
  await page.getByRole('button', { name: '삭제' }).click();

  await expect(page.getByRole('dialog')).toContainText('대화를 삭제하지 못했어요');
  await page.getByRole('button', { name: '닫기' }).click();
  await expect(checkbox).toBeChecked();
  await expect(page.getByRole('button', { name: '1개 삭제' })).toBeEnabled();
});
