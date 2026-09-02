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

test('실 API 대화 목록에서 선택한 세션을 소프트 삭제한다', async ({ page }) => {
  await page.addInitScript((token) => {
    window.sessionStorage.setItem('poke.access-token', token);
    window.sessionStorage.setItem('poke.account-principal', 'chat-list-e2e@example.com');
  }, ACCESS_TOKEN);

  await page.route('**/api/v1/chat/sessions', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        items: [
          {
            sessionId: 101,
            title: '삭제할 복약 상담',
            lastMessagePreview: '삭제 API 연결을 확인합니다.',
            lastMessageAt: '2026-09-02T09:00:00+09:00',
          },
        ],
      }),
    });
  });

  await page.route('**/api/v1/chat/sessions/101', async (route) => {
    const request = route.request();
    expect(request.method()).toBe('DELETE');
    expect(new URL(request.url()).pathname).toBe('/api/v1/chat/sessions/101');
    expect(request.headers().authorization).toBe(`Bearer ${ACCESS_TOKEN}`);

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: {
          sessionId: 101,
          status: 'DELETED',
          deletedAt: '2026-09-02T10:00:00+09:00',
        },
        error: null,
      }),
    });
  });

  await page.goto('/chat');
  await page.getByRole('button', { name: '대화 삭제' }).click();
  await page.getByRole('checkbox', { name: /삭제할 복약 상담 선택/ }).check();
  await page.getByRole('button', { name: '1개 삭제' }).click();
  await page.getByRole('button', { name: '삭제', exact: true }).click();

  await expect(page.getByRole('region', { name: '챗봇 시작 가이드' })).toBeVisible();
  await expect(page.getByText('삭제할 복약 상담', { exact: true })).toHaveCount(0);
});

test('실 API 다중 삭제는 성공·이미 없는 행을 즉시 없애고 실패한 행만 다시 시도한다', async ({ page }) => {
  await page.addInitScript((token) => {
    window.sessionStorage.setItem('poke.access-token', token);
    window.sessionStorage.setItem('poke.account-principal', 'chat-list-e2e@example.com');
  }, ACCESS_TOKEN);

  const deleteAttempts: number[] = [];
  await page.route('**/api/v1/chat/sessions', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        items: [
          {
            sessionId: 101,
            title: '삭제 성공 대화',
            lastMessagePreview: '성공한 행입니다.',
            lastMessageAt: '2026-09-02T09:00:00+09:00',
          },
          {
            sessionId: 102,
            title: '재시도할 대화',
            lastMessagePreview: '첫 삭제는 실패합니다.',
            lastMessageAt: '2026-09-02T08:00:00+09:00',
          },
          {
            sessionId: 103,
            title: '이미 없는 대화',
            lastMessagePreview: '404도 목록에서는 제거합니다.',
            lastMessageAt: '2026-09-02T07:00:00+09:00',
          },
        ],
      }),
    });
  });
  await page.route('**/api/v1/chat/sessions/*', async (route) => {
    const sessionId = Number(new URL(route.request().url()).pathname.split('/').at(-1));
    expect(route.request().method()).toBe('DELETE');
    deleteAttempts.push(sessionId);
    if (sessionId === 102 && deleteAttempts.filter((id) => id === 102).length === 1) {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ code: 'DELETE_FAILED', message: '재시도할 대화를 삭제하지 못했어요.' }),
      });
      return;
    }
    if (sessionId === 103) {
      await route.fulfill({
        status: 404,
        contentType: 'application/json',
        body: JSON.stringify({ code: 'CHAT_SESSION_NOT_FOUND', message: '대화를 찾지 못했어요.' }),
      });
      return;
    }
    await route.fulfill({ status: 204 });
  });

  await page.goto('/chat');
  await page.getByRole('button', { name: '대화 삭제' }).click();
  await page.getByRole('checkbox', { name: '삭제 성공 대화 선택' }).check();
  await page.getByRole('checkbox', { name: '재시도할 대화 선택' }).check();
  await page.getByRole('checkbox', { name: '이미 없는 대화 선택' }).check();
  await page.getByRole('button', { name: '3개 삭제' }).click();
  await page.getByRole('button', { name: '삭제', exact: true }).click();

  await expect(page.getByRole('dialog')).toContainText('대화를 삭제하지 못했어요');
  await expect(page.getByText('삭제 성공 대화', { exact: true })).toHaveCount(0);
  await expect(page.getByText('이미 없는 대화', { exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: '닫기' }).click();
  const failedSelection = page.getByRole('checkbox', { name: '재시도할 대화 선택' });
  await expect(failedSelection).toBeChecked();
  await expect(page.getByRole('button', { name: '1개 삭제' })).toBeEnabled();

  await page.getByRole('button', { name: '1개 삭제' }).click();
  await page.getByRole('button', { name: '삭제', exact: true }).click();

  await expect(page.getByRole('region', { name: '챗봇 시작 가이드' })).toBeVisible();
  expect(deleteAttempts.filter((id) => id === 101)).toHaveLength(1);
  expect(deleteAttempts.filter((id) => id === 103)).toHaveLength(1);
  expect(deleteAttempts.filter((id) => id === 102)).toHaveLength(2);
});

test('실 API 목록 조회는 인증 세대가 바뀐 뒤 늦은 결과를 거부한다', async ({ page }) => {
  await page.addInitScript((token) => {
    window.sessionStorage.setItem('poke.access-token', token);
    window.sessionStorage.setItem('poke.account-principal', 'chat-list-e2e@example.com');
  }, ACCESS_TOKEN);

  let releaseResponse: () => void = () => undefined;
  const responseReleased = new Promise<void>((resolve) => {
    releaseResponse = resolve;
  });
  let requested = false;
  await page.route('**/api/v1/chat/sessions', async (route) => {
    requested = true;
    await responseReleased;
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ items: [] }) });
  });

  await page.goto('/login');
  const operation = page.evaluate(async () => {
    const { listChatSessions } = await import('/src/entities/chat/api.ts');
    try {
      await listChatSessions();
      return null;
    } catch (error) {
      return error instanceof Error ? error.message : String(error);
    }
  });
  await expect.poll(() => requested).toBe(true);
  await page.evaluate(async () => {
    const { setAccessToken } = await import('/src/shared/api/client.ts');
    setAccessToken('rotated-list-token');
  });
  releaseResponse();

  await expect(operation).resolves.toBe('로그인 상태가 바뀌어 대화 목록 조회를 중단했어요.');
});

test('실 API 대화 상세 조회는 인증 세대가 바뀐 뒤 늦은 결과를 거부한다', async ({ page }) => {
  await page.addInitScript((token) => {
    window.sessionStorage.setItem('poke.access-token', token);
    window.sessionStorage.setItem('poke.account-principal', 'chat-list-e2e@example.com');
  }, ACCESS_TOKEN);

  let releaseResponse: () => void = () => undefined;
  const responseReleased = new Promise<void>((resolve) => {
    releaseResponse = resolve;
  });
  let requested = false;
  await page.route('**/api/v1/chat/sessions/101', async (route) => {
    requested = true;
    await responseReleased;
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: { messages: [] }, error: null }),
    });
  });

  await page.goto('/login');
  const operation = page.evaluate(async () => {
    const { getChatMessages } = await import('/src/entities/chat/api.ts');
    try {
      await getChatMessages(101);
      return null;
    } catch (error) {
      return error instanceof Error ? error.message : String(error);
    }
  });
  await expect.poll(() => requested).toBe(true);
  await page.evaluate(async () => {
    const { setAccessToken } = await import('/src/shared/api/client.ts');
    setAccessToken('rotated-detail-token');
  });
  releaseResponse();

  await expect(operation).resolves.toBe('로그인 상태가 바뀌어 대화 조회를 중단했어요.');
});

test('실 API 삭제는 인증 세대가 바뀐 뒤 늦은 결과를 거부한다', async ({ page }) => {
  await page.addInitScript((token) => {
    window.sessionStorage.setItem('poke.access-token', token);
    window.sessionStorage.setItem('poke.account-principal', 'chat-list-e2e@example.com');
  }, ACCESS_TOKEN);

  let releaseResponse: () => void = () => undefined;
  const responseReleased = new Promise<void>((resolve) => {
    releaseResponse = resolve;
  });
  let requested = false;
  await page.route('**/api/v1/chat/sessions/101', async (route) => {
    requested = true;
    await responseReleased;
    await route.fulfill({ status: 204 });
  });

  await page.goto('/login');
  const operation = page.evaluate(async () => {
    const { deleteChatSessions } = await import('/src/entities/chat/api.ts');
    try {
      await deleteChatSessions([101]);
      return null;
    } catch (error) {
      return error instanceof Error ? error.message : String(error);
    }
  });
  await expect.poll(() => requested).toBe(true);
  await page.evaluate(async () => {
    const { setAccessToken } = await import('/src/shared/api/client.ts');
    setAccessToken('rotated-delete-token');
  });
  releaseResponse();

  await expect(operation).resolves.toBe('로그인 상태가 바뀌어 대화 삭제를 중단했어요.');
});
