import { expect, test, type Page, type Route } from 'playwright/test';

import { IS_REAL_API, REAL_API_ONLY_REASON } from './helpers/mode';

test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
test.setTimeout(30_000);

const ACCESS_TOKEN = 'e2e-chat-feedback-token';
const ANSWER = '실 API 평가 계약 답변입니다.';

interface FeedbackPayload {
  isLike: boolean | null;
  reasonCode: string | null;
}

interface CommonCodeResponseItem {
  detail_code: string;
  detail_name: string;
  sort_order: number;
}

interface FeedbackHarnessOptions {
  commonCodeItems?: Partial<Record<'P_REASON' | 'N_REASON', CommonCodeResponseItem[]>>;
  commonCodeFailures?: Partial<Record<'P_REASON' | 'N_REASON', number>>;
  feedbackHandler?: (route: Route, payload: FeedbackPayload, attempt: number) => Promise<void>;
}

interface FeedbackHarness {
  feedbackRequests: FeedbackPayload[];
  commonCodeAttempts: Record<'P_REASON' | 'N_REASON', number>;
}

const DEFAULT_COMMON_CODES: Record<'P_REASON' | 'N_REASON', CommonCodeResponseItem[]> = {
  P_REASON: [
    { detail_code: 'P01', detail_name: '긍정 사유 1', sort_order: 1 },
    { detail_code: 'P02', detail_name: '긍정 사유 2', sort_order: 2 },
    { detail_code: 'P03', detail_name: '긍정 사유 3', sort_order: 3 },
    { detail_code: 'P04', detail_name: '긍정 사유 4', sort_order: 4 },
    { detail_code: 'P05', detail_name: '긍정 사유 5', sort_order: 5 },
  ],
  N_REASON: [
    { detail_code: 'N01', detail_name: '부정 사유 1', sort_order: 1 },
    { detail_code: 'N02', detail_name: '부정 사유 2', sort_order: 2 },
    { detail_code: 'N03', detail_name: '부정 사유 3', sort_order: 3 },
    { detail_code: 'N04', detail_name: '부정 사유 4', sort_order: 4 },
    { detail_code: 'N05', detail_name: '부정 사유 5', sort_order: 5 },
  ],
};

async function installFeedbackHarness(
  page: Page,
  options: FeedbackHarnessOptions = {},
): Promise<FeedbackHarness> {
  const feedbackRequests: FeedbackPayload[] = [];
  const commonCodeAttempts = { P_REASON: 0, N_REASON: 0 } as Record<
    'P_REASON' | 'N_REASON',
    number
  >;

  await page.addInitScript((token) => {
    window.sessionStorage.setItem('poke.access-token', token);
    window.sessionStorage.setItem('poke.account-principal', 'chat-feedback-e2e@example.com');
  }, ACCESS_TOKEN);

  await page.route('**/api/v1/chat/sessions', async (route) => {
    expect(route.request().method()).toBe('GET');
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ items: [] }),
    });
  });

  await page.route('**/api/v1/chat/stream', async (route) => {
    expect(route.request().method()).toBe('POST');
    await route.fulfill({
      status: 200,
      headers: { 'content-type': 'text/event-stream' },
      body: `event: complete\ndata: ${JSON.stringify({
        conversationId: 101,
        messageId: 1001,
        answer: ANSWER,
        sources: [],
      })}\n\n`,
    });
  });

  await page.route('**/api/v1/common-codes/CHAT/*', async (route) => {
    expect(route.request().method()).toBe('GET');
    const groupCode = new URL(route.request().url()).pathname.split('/').at(-1) as
      | 'P_REASON'
      | 'N_REASON';
    commonCodeAttempts[groupCode] += 1;
    const failuresRemaining = options.commonCodeFailures?.[groupCode] ?? 0;
    if (commonCodeAttempts[groupCode] <= failuresRemaining) {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({ code: 'COMMON_CODE_FAILURE', message: 'internal lookup detail' }),
      });
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        items: options.commonCodeItems?.[groupCode] ?? DEFAULT_COMMON_CODES[groupCode],
      }),
    });
  });

  await page.route('**/api/v1/chat/sessions/101/feedback', async (route) => {
    expect(route.request().method()).toBe('PUT');
    const payload = route.request().postDataJSON() as FeedbackPayload;
    feedbackRequests.push(payload);
    if (options.feedbackHandler) {
      await options.feedbackHandler(route, payload, feedbackRequests.length);
      return;
    }

    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: { sessionId: 101, ...payload },
        error: null,
      }),
    });
  });

  return { feedbackRequests, commonCodeAttempts };
}

async function openAnsweredChat(page: Page) {
  await page.goto('/chat');
  await page.getByRole('textbox', { name: '질문 입력' }).fill('평가 API 계약을 확인해 주세요.');
  await page.getByRole('button', { name: '보내기' }).click();
  await expect(page.getByText(ANSWER, { exact: true })).toBeVisible();
}

async function openEndSheet(page: Page) {
  await page.getByRole('button', { name: '채팅 종료' }).click();
  return page.getByRole('dialog', { name: '상담 종료' });
}

async function openFeedbackStep(
  page: Page,
  sentiment: 'positive' | 'negative',
  expectedReasonCount = 5,
) {
  const endSheet = await openEndSheet(page);
  await endSheet
    .getByRole('button', { name: sentiment === 'positive' ? '좋아요' : '아쉬워요' })
    .click();
  const feedbackSheet = page.getByRole('dialog', { name: '상담 평가' });
  await expect(feedbackSheet.locator('button[aria-pressed]')).toHaveCount(expectedReasonCount);
  return feedbackSheet;
}

test('실 API 좋아요 평가는 PUT에 P02 detailCode를 전송한다', async ({ page }) => {
  const harness = await installFeedbackHarness(page);
  await openAnsweredChat(page);

  const feedbackSheet = await openFeedbackStep(page, 'positive');
  await feedbackSheet.locator('button[aria-pressed]').nth(1).click();
  await feedbackSheet.getByRole('button', { name: '제출하고 종료' }).click();

  await expect(page.getByRole('dialog')).toHaveCount(0);
  expect(harness.feedbackRequests).toEqual([{ isLike: true, reasonCode: 'P02' }]);
});

test('실 API 아쉬워요 평가는 PUT에 N03 detailCode를 전송한다', async ({ page }) => {
  const harness = await installFeedbackHarness(page);
  await openAnsweredChat(page);

  const feedbackSheet = await openFeedbackStep(page, 'negative');
  await feedbackSheet.locator('button[aria-pressed]').nth(2).click();
  await feedbackSheet.getByRole('button', { name: '제출하고 종료' }).click();

  await expect(page.getByRole('dialog')).toHaveCount(0);
  expect(harness.feedbackRequests).toEqual([{ isLike: false, reasonCode: 'N03' }]);
});

test('실 API 평가는 사유 없이 reasonCode null을 보낸다', async ({ page }) => {
  const harness = await installFeedbackHarness(page);
  await openAnsweredChat(page);

  const positiveSheet = await openFeedbackStep(page, 'positive');
  const reason = positiveSheet.locator('button[aria-pressed]').nth(1);
  await reason.click();
  await expect(reason).toHaveAttribute('aria-pressed', 'true');
  await reason.click();
  await expect(reason).toHaveAttribute('aria-pressed', 'false');
  await positiveSheet.getByRole('button', { name: '제출하고 종료' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  expect(harness.feedbackRequests).toEqual([{ isLike: true, reasonCode: null }]);
});

test('건너뛰고 종료는 실 API PUT을 보내지 않는다', async ({ page }) => {
  const harness = await installFeedbackHarness(page);
  await openAnsweredChat(page);

  await page.getByRole('button', { name: '채팅 종료' }).click();
  await page.getByRole('dialog', { name: '상담 종료' }).getByRole('button', { name: '건너뛰고 종료' }).click();
  expect(harness.feedbackRequests).toHaveLength(0);
});

test('공통코드 조회 실패는 안전한 문구와 다시 시도를 제공한다', async ({ page }) => {
  const harness = await installFeedbackHarness(page, { commonCodeFailures: { P_REASON: 1 } });
  await openAnsweredChat(page);

  const feedbackSheet = await openFeedbackStep(page, 'positive', 0);
  await expect(feedbackSheet.getByRole('alert')).toHaveText('사유를 불러오지 못했어요');
  await expect(feedbackSheet.getByText('internal lookup detail', { exact: true })).toHaveCount(0);
  await feedbackSheet.getByRole('button', { name: '다시 시도' }).click();
  await expect(feedbackSheet.locator('button[aria-pressed]')).toHaveCount(5);
  expect(harness.commonCodeAttempts.P_REASON).toBe(2);
});

test('공통코드가 비어도 사유 영역 없이 reasonCode null로 저장한다', async ({ page }) => {
  const harness = await installFeedbackHarness(page, { commonCodeItems: { P_REASON: [] } });
  await openAnsweredChat(page);

  const feedbackSheet = await openFeedbackStep(page, 'positive', 0);
  await expect(feedbackSheet.getByRole('status')).toHaveCount(0);
  await expect(feedbackSheet.getByRole('region', { name: '평가 사유' })).toHaveCount(0);
  await feedbackSheet.getByRole('button', { name: '제출하고 종료' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  expect(harness.feedbackRequests).toEqual([{ isLike: true, reasonCode: null }]);
});

test('INVALID_CHAT_FEEDBACK_REASON은 원문을 숨기고 같은 PUT을 다시 시도할 수 있다', async ({ page }) => {
  const harness = await installFeedbackHarness(page, {
    feedbackHandler: async (route, payload, attempt) => {
      if (attempt === 1) {
        await route.fulfill({
          status: 422,
          contentType: 'application/json',
          body: JSON.stringify({
            code: 'INVALID_CHAT_FEEDBACK_REASON',
            message: 'P02 internal validation detail',
          }),
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          data: { sessionId: 101, ...payload },
          error: null,
        }),
      });
    },
  });
  await openAnsweredChat(page);

  const feedbackSheet = await openFeedbackStep(page, 'positive');
  await feedbackSheet.locator('button[aria-pressed]').nth(1).click();
  await feedbackSheet.getByRole('button', { name: '제출하고 종료' }).click();
  await expect(feedbackSheet.getByRole('alert')).toHaveText(
    '평가를 저장하지 못했어요. 다시 시도해주세요.',
  );
  await expect(feedbackSheet.getByText('P02 internal validation detail', { exact: true })).toHaveCount(0);

  await feedbackSheet.getByRole('button', { name: '제출하고 종료' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  expect(harness.feedbackRequests).toEqual([
    { isLike: true, reasonCode: 'P02' },
    { isLike: true, reasonCode: 'P02' },
  ]);
});

test('지연된 이전 저장이 닫았다가 다시 연 부정 평가를 닫지 않는다', async ({ page }) => {
  let firstSaveSettled = false;
  const harness = await installFeedbackHarness(page, {
    feedbackHandler: async (route, payload, attempt) => {
      if (attempt === 1) await new Promise((resolve) => setTimeout(resolve, 3000));
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          data: { sessionId: 101, ...payload },
          error: null,
        }),
      });
      if (attempt === 1) firstSaveSettled = true;
    },
  });
  await openAnsweredChat(page);

  const positiveSheet = await openFeedbackStep(page, 'positive');
  await positiveSheet.locator('button[aria-pressed]').first().click();
  await positiveSheet.getByRole('button', { name: '제출하고 종료' }).click();
  await expect.poll(() => harness.feedbackRequests.length).toBe(1);
  await positiveSheet.getByRole('button', { name: '평가 닫기' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);

  const negativeSheet = await openFeedbackStep(page, 'negative');
  await expect.poll(() => firstSaveSettled, { timeout: 10_000 }).toBe(true);

  await expect(negativeSheet).toBeVisible();
  await expect(page.getByText(ANSWER, { exact: true })).toBeVisible();
  expect(harness.feedbackRequests).toEqual([{ isLike: true, reasonCode: 'P01' }]);
  await negativeSheet.getByRole('button', { name: '평가 닫기' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
});
