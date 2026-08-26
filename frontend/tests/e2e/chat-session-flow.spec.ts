import { expect, test, type Page } from 'playwright/test';

const MOCK_ACCOUNT = 'patient@example.com';
const OTHER_MOCK_ACCOUNT = 'other-patient@example.com';
const ACCOUNT_PRINCIPAL_STORAGE_KEY = 'poke.account-principal';
const mockChatStorageKey = (account: string) =>
  `poke.mock-chat-sessions:${encodeURIComponent(account.toLowerCase())}`;

test.setTimeout(30_000);

async function createConversation(page: Page, question: string) {
  await page.getByRole('textbox', { name: '질문 입력' }).fill(question);
  await page.getByRole('button', { name: '보내기' }).click();
  await expect(page.getByText('리바록사반을 복용하는 동안', { exact: false })).toBeVisible();
}

test.beforeEach(async ({ page }) => {
  await page.goto('/dev/chat');
  await page.evaluate(
    ({ patientKey, otherKey, principalKey, account }) => {
      localStorage.removeItem(patientKey);
      localStorage.removeItem(otherKey);
      sessionStorage.setItem('poke.access-token', 'e2e-chat-token');
      sessionStorage.setItem(principalKey, account);
    },
    {
      patientKey: mockChatStorageKey(MOCK_ACCOUNT),
      otherKey: mockChatStorageKey(OTHER_MOCK_ACCOUNT),
      principalKey: ACCOUNT_PRINCIPAL_STORAGE_KEY,
      account: MOCK_ACCOUNT,
    },
  );
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

test('로그아웃 뒤 다른 계정으로 로그인하면 이전 계정 대화를 보여주지 않는다', async ({ page }) => {
  await createConversation(page, '로그아웃 전 상담 질문');
  await page.getByRole('button', { name: '마이', exact: true }).click();
  await page.getByRole('button', { name: '로그아웃' }).click();

  await page.getByRole('button', { name: '챗봇', exact: true }).click();
  await page.getByRole('button', { name: '로그인 · 회원가입' }).click();
  await page.getByLabel('이메일').fill(OTHER_MOCK_ACCOUNT);
  await page.getByLabel('비밀번호').fill('password1234');
  await page.getByRole('button', { name: '로그인', exact: true }).last().click();
  await page.getByRole('button', { name: '챗봇', exact: true }).click();

  await expect(page.getByRole('region', { name: '챗봇 시작 가이드' })).toBeVisible();
  await expect(page.getByText('대화 이력을 불러오지 못했어요.')).toHaveCount(0);
});

test('같은 계정으로 다시 로그인하면 저장된 대화 목록을 복구한다', async ({ page }) => {
  const question = '같은 계정 복구 확인 질문';
  await createConversation(page, question);
  await page.getByRole('button', { name: '마이', exact: true }).click();
  await page.getByRole('button', { name: '로그아웃' }).click();

  await page.getByRole('button', { name: '챗봇', exact: true }).click();
  await page.getByRole('button', { name: '로그인 · 회원가입' }).click();
  await page.getByLabel('이메일').fill(MOCK_ACCOUNT);
  await page.getByLabel('비밀번호').fill('password1234');
  await page.getByRole('button', { name: '로그인', exact: true }).last().click();
  await page.getByRole('button', { name: '챗봇', exact: true }).click();

  await expect(page.getByRole('heading', { name: '최근 대화' })).toBeVisible();
  await expect(page.getByRole('button', { name: new RegExp(question) })).toBeVisible();
});

test('답변 대기 중 로그아웃해도 이전 질문이 다음 계정에 저장되지 않는다', async ({ page }) => {
  const question = '로그아웃 경합 확인 질문';
  await page.getByRole('textbox', { name: '질문 입력' }).fill(question);
  await page.getByRole('button', { name: '보내기' }).click();
  await page.getByRole('button', { name: '마이', exact: true }).click();
  await page.getByRole('button', { name: '로그아웃' }).click();

  await page.getByRole('button', { name: '챗봇', exact: true }).click();
  await page.getByRole('button', { name: '로그인 · 회원가입' }).click();
  await page.getByLabel('이메일').fill(OTHER_MOCK_ACCOUNT);
  await page.getByLabel('비밀번호').fill('password1234');
  await page.getByRole('button', { name: '로그인', exact: true }).last().click();
  await page.getByRole('button', { name: '챗봇', exact: true }).click();

  await page.waitForTimeout(1_500);
  await expect(page.getByRole('region', { name: '챗봇 시작 가이드' })).toBeVisible();
  await expect(page.getByText(question, { exact: true })).toHaveCount(0);
});

test('삭제 대기 중 계정이 바뀌어도 다른 계정의 같은 ID 대화를 지우지 않는다', async ({ page }) => {
  const patientQuestion = '첫 계정에 남아야 하는 질문';
  const otherQuestion = '두 번째 계정 삭제 요청 질문';
  await createConversation(page, patientQuestion);
  await page.getByRole('button', { name: '마이', exact: true }).click();
  await page.getByRole('button', { name: '로그아웃' }).click();

  await page.goto('/login');
  await page.getByLabel('이메일').fill(OTHER_MOCK_ACCOUNT);
  await page.getByLabel('비밀번호').fill('password1234');
  await page.getByRole('button', { name: '로그인', exact: true }).last().click();
  await page.getByRole('button', { name: '챗봇', exact: true }).click();
  await createConversation(page, otherQuestion);
  await page.reload();
  await page.getByRole('button', { name: '대화 선택' }).click();
  await page.getByRole('checkbox', { name: new RegExp(otherQuestion) }).check();
  await page.getByRole('button', { name: '1개 삭제' }).click();
  await page.getByRole('button', { name: '삭제', exact: true }).click();

  await page.goto('/my');
  await page.getByRole('button', { name: '로그아웃' }).click();
  await page.goto('/login');
  await page.getByLabel('이메일').fill(MOCK_ACCOUNT);
  await page.getByLabel('비밀번호').fill('password1234');
  await page.getByRole('button', { name: '로그인', exact: true }).last().click();
  await page.getByRole('button', { name: '챗봇', exact: true }).click();

  await expect(page.getByRole('button', { name: new RegExp(patientQuestion) })).toBeVisible();
});

test('이력 API가 없어도 성공한 실 API 답변을 현재 화면에서 지우지 않는다', async ({ page }) => {
  await page.goto('/dev/chat-send-without-history');
  const question = '실제 API 경계 확인 질문';

  await page.getByRole('textbox', { name: '질문 입력' }).fill(question);
  await page.getByRole('button', { name: '보내기' }).click();

  await expect(page.getByText(question, { exact: true })).toBeVisible();
  await expect(page.getByText('실제 전송 API에서 받은 답변이에요.', { exact: true })).toBeVisible();
  await expect(page.getByText('대화 이력을 불러오지 못했어요.')).toHaveCount(0);
});

test('선택한 대화 이력을 불러오는 동안 이전 세션으로 질문을 보낼 수 없다', async ({ page }) => {
  await createConversation(page, '로딩 차단 확인 질문');
  await page.reload();
  await page.getByRole('button', { name: /로딩 차단 확인 질문/ }).click();

  await expect(page.getByRole('status', { name: '대화 이력 불러오는 중' })).toBeVisible();
  await expect(page.getByRole('textbox', { name: '질문 입력' })).toBeDisabled();
  await expect(page.getByRole('button', { name: '보내기' })).toBeDisabled();
  await expect(page.getByText('로딩 차단 확인 질문', { exact: true })).toBeVisible();
});

test('답변 대기 중 다른 탭에 다녀와도 완료된 활성 대화를 불러온다', async ({ page }) => {
  const question = '답변 대기 중 탭 이동 질문';
  await page.getByRole('textbox', { name: '질문 입력' }).fill(question);
  await page.getByRole('button', { name: '보내기' }).click();
  await page.getByRole('button', { name: '홈', exact: true }).click();
  await page.getByRole('button', { name: '챗봇', exact: true }).click();

  await expect(page.getByRole('textbox', { name: '질문 입력' })).toBeDisabled();
  await expect(page.getByRole('button', { name: '보내기' })).toBeDisabled();
  await expect(page.getByText(question, { exact: true })).toBeVisible();
  await expect(page.getByText('리바록사반을 복용하는 동안', { exact: false })).toBeVisible();
  await expect(page.getByRole('textbox', { name: '질문 입력' })).toBeEnabled();
});

test('후속 답변 뒤 목록으로 돌아오면 최신 미리보기로 갱신한다', async ({ page }) => {
  await createConversation(page, '목록 갱신 확인 질문');
  await page.reload();
  await page.getByRole('button', { name: /목록 갱신 확인 질문/ }).click();
  await page.getByRole('textbox', { name: '질문 입력' }).fill('일반적인 안내로 답해주세요');
  await page.getByRole('button', { name: '보내기' }).click();
  await expect(page.getByText('수술 후 회복 기간은 사람마다', { exact: false })).toBeVisible();
  await page.getByRole('button', { name: '뒤로' }).click();

  await expect(page.getByRole('button', { name: /목록 갱신 확인 질문/ })).toContainText(
    '수술 후 회복 기간은 사람마다',
  );
});

test('저장소에서 사라진 활성 대화는 오류 방에 머물지 않고 빈 대화로 복구한다', async ({ page }) => {
  await createConversation(page, '사라질 활성 대화');
  await page.getByRole('button', { name: '홈', exact: true }).click();
  await page.evaluate(
    (storageKey) => localStorage.removeItem(storageKey),
    mockChatStorageKey(MOCK_ACCOUNT),
  );
  await page.getByRole('button', { name: '챗봇', exact: true }).click();

  await expect(page.getByRole('region', { name: '챗봇 시작 가이드' })).toBeVisible();
  await expect(page.getByText('대화 이력을 불러오지 못했어요.')).toHaveCount(0);
});
