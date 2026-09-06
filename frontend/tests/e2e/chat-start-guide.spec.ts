import { expect, test } from 'playwright/test';

import { IS_REAL_API, MOCK_ONLY_REASON } from './helpers/mode';

test.beforeEach(() => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
});

const FAQS = [
  '같이 먹어도 될까요?',
  '언제 먹는 게 좋나요?',
  '주의할 증상이 있나요?',
] as const;

test('H-2 빈 대화에는 시작 제목과 세 개의 자주 묻는 질문, 안전 안내를 보여준다', async ({ page }) => {
  await page.goto('/dev/chat');

  await expect(page.getByRole('heading', { name: '무엇이 궁금하세요?' })).toBeVisible();
  await expect(
    page.getByText('등록한 복용 정보를 바탕으로 답변해요.', { exact: true }),
  ).toBeVisible();

  const guide = page.getByRole('region', { name: '챗봇 시작 가이드' });
  await expect(guide.getByRole('heading', { name: '이 챗봇에서 확인할 수 있어요' })).toBeVisible();
  await expect(guide.getByRole('listitem')).toHaveCount(4);
  await expect(guide.getByText('복용 중인 약의 효능 · 부작용 · 주의사항', { exact: true })).toBeVisible();
  await expect(guide.getByText('영양제 성분의 기능과 섭취 주의사항', { exact: true })).toBeVisible();
  await expect(
    guide.getByText('약과 약, 약과 영양제를 함께 먹을 때의 주의점', { exact: true }),
  ).toBeVisible();
  await expect(
    guide.getByText('임신 · 수유 · 고령자 · 간신장 질환자 주의사항', { exact: true }),
  ).toBeVisible();
  await expect(guide.getByText('답변에는 근거 자료의 출처를 함께 보여드려요')).toBeVisible();

  const faq = page.getByRole('region', { name: '자주 묻는 질문' });
  await expect(faq.getByRole('heading', { name: '자주 묻는 질문' })).toBeVisible();
  const buttons = faq.getByRole('button');
  await expect(buttons).toHaveCount(3);
  for (const [index, question] of FAQS.entries()) {
    await expect(buttons.nth(index)).toHaveText(question);
  }

  await expect(
    page.getByText('제공되는 내용은 참고 정보이며 진단이나 처방을 대신하지 않아요.'),
  ).toBeVisible();
  await expect(
    page.getByText('복용 변경이 필요한 경우 의료진 또는 약사와 상담해 주세요.'),
  ).toBeVisible();
  expect(
    await page.evaluate(() => ({
      horizontal: document.documentElement.scrollWidth <= window.innerWidth,
      vertical: document.documentElement.scrollHeight <= window.innerHeight,
    })),
  ).toEqual({ horizontal: true, vertical: true });
});

test('자주 묻는 질문은 입력칸에 머물지 않고 바로 전송되며 시작 내용을 즉시 숨긴다', async ({ page }) => {
  await page.goto('/dev/chat');

  const question = FAQS[0];
  const expectedProgress = ['질문 확인 중', '근거 검색 중', '답변 정리 중', '안전 확인 중'];
  const progressObserver = await page.evaluateHandle((messages) => {
    const observed: string[] = [];
    const capture = () => {
      const text = document.body.innerText;
      for (const message of messages) {
        if (text.includes(message) && !observed.includes(message)) observed.push(message);
      }
    };
    const observer = new MutationObserver(capture);
    observer.observe(document.body, { childList: true, subtree: true, characterData: true });
    capture();
    return { observed, observer };
  }, expectedProgress);
  await page.getByRole('button', { name: question }).click();

  await expect(page.getByRole('textbox', { name: '질문 입력' })).toHaveValue('');
  await expect(page.getByText(question, { exact: true })).toBeVisible();
  await expect(page.getByRole('region', { name: '챗봇 시작 가이드' })).toHaveCount(0);
  await expect(page.getByRole('region', { name: '자주 묻는 질문' })).toHaveCount(0);
  await expect
    .poll(() => progressObserver.evaluate(({ observed }) => observed))
    .toEqual(expectedProgress);
  await progressObserver.evaluate(({ observer }) => observer.disconnect());
  await progressObserver.dispose();
});

test('기존 대화 이력이 있으면 시작 가이드와 자주 묻는 질문을 처음부터 보이지 않는다', async ({ page }) => {
  await page.goto('/dev/chat-history');

  await expect(page.getByText('이전에 물어본 질문이에요.', { exact: true })).toBeVisible();
  await expect(page.getByRole('region', { name: '챗봇 시작 가이드' })).toHaveCount(0);
  await expect(page.getByRole('region', { name: '자주 묻는 질문' })).toHaveCount(0);
});

test('이력 조회 실패는 팝업 대신 화면 안 카드와 시작 내용을 함께 보여준다', async ({ page }) => {
  await page.goto('/dev/chat-history-error');

  await expect(page.getByText('대화 이력을 불러오지 못했어요.', { exact: true })).toBeVisible();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.getByRole('region', { name: '챗봇 시작 가이드' })).toBeVisible();
  await expect(page.getByRole('region', { name: '자주 묻는 질문' })).toBeVisible();
});
