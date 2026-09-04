import { expect, test, type Page } from 'playwright/test';

import { IS_REAL_API, MOCK_ONLY_REASON } from './helpers/mode';

test.beforeEach(() => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
});

test.setTimeout(30_000);

async function openAnsweredChat(page: Page) {
  await page.goto('/dev/chat');
  await page.getByRole('button', { name: '지금 먹는 약을 같이 먹어도 되나요?' }).click();
  await expect(page.getByText('리바록사반을 복용하는 동안', { exact: false })).toBeVisible();
}

test('챗봇은 챗봇 이름과 최종 답변의 근거 메타데이터를 보여준다', async ({ page }) => {
  await openAnsweredChat(page);

  await expect(page.getByRole('heading', { name: '챗봇' })).toBeVisible();
  await expect(page.getByText('AI 상담', { exact: true })).toHaveCount(0);
  await expect(page.getByText('오늘 · 근거 2개', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '채팅 종료' })).toBeVisible();
});

test('채팅 종료는 content-height 평가 시트를 열고 좋아요·아쉬워요·건너뛰기 흐름을 제공한다', async ({ page }) => {
  await openAnsweredChat(page);
  await page.getByRole('button', { name: '채팅 종료' }).click();

  const endSheet = page.getByRole('dialog', { name: '상담 종료' });
  await expect(endSheet).toBeVisible();
  const endSheetBox = await endSheet.boundingBox();
  expect(endSheetBox?.height).toBeLessThan(844);

  await endSheet.getByRole('button', { name: '좋아요' }).click();
  const positiveSheet = page.getByRole('dialog', { name: '상담 평가' });
  await expect(positiveSheet).toContainText('좋았던 점을 선택해주세요');
  await positiveSheet.getByRole('button', { name: '이해하기 쉬워요' }).click();
  await positiveSheet.getByRole('button', { name: '제출하고 종료' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);

  await page.getByRole('button', { name: '채팅 종료' }).click();
  await page.getByRole('dialog', { name: '상담 종료' }).getByRole('button', { name: '아쉬워요' }).click();
  const negativeSheet = page.getByRole('dialog', { name: '상담 평가' });
  await expect(negativeSheet).toContainText('아쉬웠던 점을 선택해주세요');
  await negativeSheet.getByRole('button', { name: '답변이 어려워요' }).click();
  await negativeSheet.getByRole('button', { name: '제출하고 종료' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);

  await page.getByRole('button', { name: '채팅 종료' }).click();
  await page.getByRole('dialog', { name: '상담 종료' }).getByRole('button', { name: '건너뛰고 종료' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
});

test('대화 삭제 선택 화면은 Figma 제목과 확인 흐름을 사용한다', async ({ page }) => {
  await openAnsweredChat(page);
  await page.reload();

  await page.getByRole('button', { name: '대화 삭제' }).click();
  await expect(page.getByRole('heading', { name: '삭제할 대화를 선택하세요' })).toBeVisible();
  const question = '지금 먹는 약을 같이 먹어도 되나요?';
  await page.getByRole('checkbox', { name: `${question} 선택` }).check();
  await page.getByRole('button', { name: '1개 삭제' }).click();
  await expect(page.getByRole('dialog')).toContainText('선택한 대화를 삭제할까요?');
  await expect(page.getByRole('dialog')).toContainText('선택한 1개 대화는 목록에서 다시 볼 수 없어요.');
  await page.getByRole('button', { name: '취소', exact: true }).click();
  await expect(page.getByRole('heading', { name: '삭제할 대화를 선택하세요' })).toBeVisible();
});
