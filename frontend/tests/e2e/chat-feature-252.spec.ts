import { expect, test, type Page } from 'playwright/test';

import { IS_REAL_API, MOCK_ONLY_REASON } from './helpers/mode';

test.beforeEach(() => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
});

test.setTimeout(30_000);

async function openAnsweredChat(page: Page) {
  await page.goto('/dev/chat');
  await page.getByRole('textbox', { name: '질문 입력' }).fill('지금 먹는 약을 같이 먹어도 되나요?');
  await page.getByRole('button', { name: '보내기' }).click();
  await expect(page.getByText('리바록사반을 복용하는 동안', { exact: false })).toBeVisible();
}

test('챗봇 근거는 개수와 함께 접어 두고 키보드로 내용을 펼치고 접는다', async ({ page }) => {
  await openAnsweredChat(page);

  await expect(page.getByRole('heading', { name: '챗봇' })).toBeVisible();
  await expect(page.getByText('AI 상담', { exact: true })).toHaveCount(0);
  await expect(page.getByText('오늘 · 근거 2개', { exact: true })).toBeVisible();
  await expect(page.getByRole('heading', { name: '주의와 한계' })).toBeVisible();
  await expect(
    page.getByText('이 답변은 진단이나 처방을 대신하지 않아요.', { exact: true }),
  ).toBeVisible();
  await expect(page.getByRole('heading', { name: '근거' })).toHaveCount(0);
  await expect(page.getByText('약봉투 · 리바록사반 10mg', { exact: true })).toBeHidden();

  const toggle = page.getByRole('button', { name: '근거 보기 2개' });
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');
  const controls = await toggle.getAttribute('aria-controls');
  expect(controls).toBeTruthy();
  await expect(toggle.locator('svg')).toBeVisible();
  const bounds = await toggle.boundingBox();
  expect(bounds).not.toBeNull();
  expect(bounds!.height).toBeGreaterThanOrEqual(44);

  await toggle.focus();
  await page.keyboard.press('Enter');
  const collapse = page.getByRole('button', { name: '근거 접기 2개' });
  await expect(collapse).toHaveAttribute('aria-expanded', 'true');
  await expect(page.locator(`#${controls}`)).toBeVisible();
  await expect(page.getByRole('heading', { name: '근거' })).toBeVisible();
  await expect(page.getByText('내 문서', { exact: true })).toBeVisible();
  await expect(page.getByText('공식 자료', { exact: true })).toHaveClass(/bg-info-bg/);
  await expect(page.getByText('식품의약품안전처', { exact: true })).toBeVisible();
  const sourceLink = page.getByRole('link', { name: '새 창에서 열기' });
  await expect(sourceLink).toHaveAttribute('href', 'https://nedrug.mfds.go.kr');
  await expect(sourceLink).toHaveAttribute('target', '_blank');
  await expect(sourceLink).toHaveAttribute('rel', /noopener/);

  await collapse.focus();
  await page.keyboard.press('Space');
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');
  await expect(page.getByRole('heading', { name: '근거' })).toHaveCount(0);
  await expect(page.getByRole('heading', { name: '이어서 물어보기' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '채팅 종료' })).toBeVisible();
});

test('각 챗봇 답변의 근거 토글은 서로 독립적으로 동작한다', async ({ page }) => {
  await openAnsweredChat(page);
  await page.getByRole('textbox', { name: '질문 입력' }).fill('이 약은 왜 먹는 건가요?');
  await page.getByRole('button', { name: '보내기' }).click();
  await expect(page.getByText('리바록사반을 복용하는 동안', { exact: false })).toHaveCount(2);

  const toggles = page.getByRole('button', { name: '근거 보기 2개' });
  await expect(toggles).toHaveCount(2);
  const firstControls = await toggles.nth(0).getAttribute('aria-controls');
  const secondControls = await toggles.nth(1).getAttribute('aria-controls');
  expect(firstControls).toBeTruthy();
  expect(secondControls).toBeTruthy();
  expect(firstControls).not.toBe(secondControls);

  await toggles.nth(0).click();
  await expect(page.getByRole('button', { name: '근거 접기 2개' })).toHaveCount(1);
  await expect(page.getByRole('button', { name: '근거 보기 2개' })).toHaveCount(1);
  await expect(page.locator(`#${firstControls}`)).toBeVisible();
  await expect(page.locator(`#${secondControls}`)).toBeHidden();
});

test('출처가 없는 답변에는 근거 블록을 렌더하지 않는다', async ({ page }) => {
  await page.goto('/dev/chat');
  await page.getByRole('textbox', { name: '질문 입력' }).fill('보통 회복은 얼마나 걸려요?');
  await page.getByRole('button', { name: '보내기' }).click();

  await expect(page.getByText('수술 후 회복 기간은 사람마다', { exact: false })).toBeVisible();
  await expect(page.getByRole('heading', { name: '주의와 한계' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '근거' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: /근거 (보기|접기)/ })).toHaveCount(0);
  await expect(
    page.getByText('이 답변은 일반적인 안내이며 등록하신 약에 근거하지 않았습니다.'),
  ).toBeVisible();
});

test('채팅 종료는 하단 content-height 시트에서 평가를 제출하고 새 대화로 종료한다', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await openAnsweredChat(page);
  await page.getByRole('button', { name: '채팅 종료' }).click();

  const endSheet = page.getByRole('dialog', { name: '상담 종료' });
  await expect(endSheet).toBeVisible();
  const endSheetBox = await endSheet.boundingBox();
  expect(endSheetBox).not.toBeNull();
  expect(endSheetBox?.height).toBeLessThan(844);
  expect(Math.abs((endSheetBox?.y ?? 0) + (endSheetBox?.height ?? 0) - 844)).toBeLessThanOrEqual(1);

  await endSheet.getByRole('button', { name: '좋아요' }).click();
  const positiveSheet = page.getByRole('dialog', { name: '상담 평가' });
  await expect(positiveSheet).toContainText('좋았던 점을 선택해주세요');
  await positiveSheet.locator('button[aria-pressed]').first().click();
  await positiveSheet.getByRole('button', { name: '제출하고 종료' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.getByRole('heading', { name: '무엇이 궁금하세요?' })).toBeVisible();

  // 종료 뒤 새 상담을 시작하면 mock API가 새 sessionId를 발급한다.
  // 삭제된 세션에 이어 쓰지 않고 새 대화를 정상 생성하는지 검증한다.
  await page.getByRole('textbox', { name: '질문 입력' }).fill('이 약은 왜 먹는 건가요?');
  await page.getByRole('button', { name: '보내기' }).click();
  await expect(page.getByText('리바록사반을 복용하는 동안', { exact: false })).toBeVisible();
  const sessionsAfterNewMessage = await page.evaluate(() => {
    const raw = localStorage.getItem('poke.mock-chat-sessions:guest');
    return raw ? (JSON.parse(raw) as { sessions: Array<{ sessionId: number }> }).sessions : [];
  });
  expect(sessionsAfterNewMessage).toHaveLength(1);
  expect(new Set(sessionsAfterNewMessage.map((session) => session.sessionId)).size).toBe(1);

  await page.getByRole('button', { name: '채팅 종료' }).click();
  await page.getByRole('dialog', { name: '상담 종료' }).getByRole('button', { name: '건너뛰고 종료' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.getByRole('heading', { name: '무엇이 궁금하세요?' })).toBeVisible();
});

test('아쉬워요 평가를 제출하면 현재 상담도 종료한다', async ({ page }) => {
  await openAnsweredChat(page);
  await page.getByRole('button', { name: '채팅 종료' }).click();
  await page.getByRole('dialog', { name: '상담 종료' }).getByRole('button', { name: '아쉬워요' }).click();

  const negativeSheet = page.getByRole('dialog', { name: '상담 평가' });
  await expect(negativeSheet).toContainText('아쉬웠던 점을 선택해주세요');
  await negativeSheet.locator('button[aria-pressed]').first().click();
  await negativeSheet.getByRole('button', { name: '제출하고 종료' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.getByRole('heading', { name: '무엇이 궁금하세요?' })).toBeVisible();
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
