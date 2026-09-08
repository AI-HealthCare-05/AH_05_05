import { expect, test } from 'playwright/test';

import { IS_REAL_API, MOCK_ONLY_REASON } from './helpers/mode';

const FIRST_ACCOUNT = 'isolation-first@example.com';
const SECOND_ACCOUNT = 'isolation-second@example.com';
const FIRST_QUESTION = '첫 계정에만 보이는 상담 질문';
const SECOND_QUESTION = '두 번째 계정에만 보이는 상담 질문';
const ACCOUNT_PRINCIPAL_STORAGE_KEY = 'poke.account-principal';
const ACCESS_TOKEN_STORAGE_KEY = 'poke.access-token';
const AUTH_SESSION_EXPIRED_EVENT = 'poke:auth-session-expired';

const mockChatStorageKey = (account: string) =>
  `poke.mock-chat-sessions:${encodeURIComponent(account.toLowerCase())}`;

test.setTimeout(30_000);

test.beforeEach(async ({ page }) => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
  await page.goto('/dev/chat');
  await page.evaluate(
    ({
      accessTokenKey,
      firstAccount,
      firstKey,
      firstQuestion,
      principalKey,
      secondKey,
      secondQuestion,
    }) => {
      localStorage.setItem(firstKey, JSON.stringify({
        nextSessionId: 78,
        nextMessageId: 1_205,
        sessions: [{
          sessionId: 77,
          createdAt: '2026-09-08T09:00:00.000Z',
          lastMessageAt: '2026-09-08T09:00:00.000Z',
          messages: [
            { role: 'user', text: firstQuestion, sources: [] },
            { role: 'assistant', text: `${firstQuestion} 답변`, sources: [] },
          ],
        }],
      }));
      localStorage.setItem(secondKey, JSON.stringify({
        nextSessionId: 89,
        nextMessageId: 1_305,
        sessions: [{
          sessionId: 88,
          createdAt: '2026-09-08T10:00:00.000Z',
          lastMessageAt: '2026-09-08T10:00:00.000Z',
          messages: [
            { role: 'user', text: secondQuestion, sources: [] },
            { role: 'assistant', text: `${secondQuestion} 답변`, sources: [] },
          ],
        }],
      }));
      sessionStorage.setItem(accessTokenKey, 'fabricated-isolation-token');
      sessionStorage.setItem(principalKey, firstAccount);
    },
    {
      accessTokenKey: ACCESS_TOKEN_STORAGE_KEY,
      firstAccount: FIRST_ACCOUNT,
      firstKey: mockChatStorageKey(FIRST_ACCOUNT),
      firstQuestion: FIRST_QUESTION,
      principalKey: ACCOUNT_PRINCIPAL_STORAGE_KEY,
      secondKey: mockChatStorageKey(SECOND_ACCOUNT),
      secondQuestion: SECOND_QUESTION,
    },
  );
  await page.reload();
});

test('현재 채팅 화면에서 인증이 끝나면 이전 계정의 세션 목록을 즉시 버린다', async ({ page }) => {
  await expect(page.getByRole('button', { name: new RegExp(FIRST_QUESTION) })).toBeVisible();

  await page.evaluate((eventName) => {
    window.dispatchEvent(new Event(eventName));
  }, AUTH_SESSION_EXPIRED_EVENT);

  await expect(page.getByText(FIRST_QUESTION, { exact: true })).toHaveCount(0);
  await expect(page.getByText(SECOND_QUESTION, { exact: true })).toHaveCount(0);
  await expect(page.getByRole('region', { name: '챗봇 시작 가이드' })).toBeVisible();
  await expect.poll(() => page.evaluate(
    ({ accessTokenKey, principalKey }) => ({
      accessToken: sessionStorage.getItem(accessTokenKey),
      principal: sessionStorage.getItem(principalKey),
    }),
    {
      accessTokenKey: ACCESS_TOKEN_STORAGE_KEY,
      principalKey: ACCOUNT_PRINCIPAL_STORAGE_KEY,
    },
  )).toEqual({ accessToken: null, principal: null });
});

test('답변 대기 중 인증이 끝나면 이전 계정의 질문과 늦은 답변을 남기지 않는다', async ({ page }) => {
  await page.getByRole('button', { name: '새 채팅' }).click();
  const pendingQuestion = '인증 종료 전에 보낸 질문';
  await page.getByRole('textbox', { name: '질문 입력' }).fill(pendingQuestion);
  await page.getByRole('button', { name: '보내기' }).click();
  await expect(page.getByText(pendingQuestion, { exact: true })).toBeVisible();

  await page.evaluate((eventName) => {
    window.dispatchEvent(new Event(eventName));
  }, AUTH_SESSION_EXPIRED_EVENT);

  await expect(page.getByText(pendingQuestion, { exact: true })).toHaveCount(0);
  await expect(page.getByText('리바록사반을 복용하는 동안', { exact: false })).toHaveCount(0);
  await expect(page.getByRole('region', { name: '챗봇 시작 가이드' })).toBeVisible();
});
