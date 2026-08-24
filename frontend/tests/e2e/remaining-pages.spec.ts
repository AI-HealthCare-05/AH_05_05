import { expect, test } from 'playwright/test';

test('복용약 화면은 남은 기간과 알림 시간, 약 4개의 상태를 구분해 보여준다', async ({ page }) => {
  await page.goto('/dev/medications');

  await expect(page.getByRole('heading', { name: '복용약' })).toBeVisible();
  await expect(page.getByText('3일 남음', { exact: true }).first()).toBeVisible();
  await expect(page.getByText('아침 08:00 · 점심 13:00 · 저녁 19:00')).toBeVisible();
  await expect(page.getByRole('heading', { name: '약 4개' })).toBeVisible();
  await expect(page.getByText('필요할 때만 · 알림 없음')).toBeVisible();
});

test('근거가 없는 챗봇 답변은 등록한 약에 근거하지 않았음을 명시한다', async ({ page }) => {
  await page.goto('/dev/chat');
  await page.getByRole('textbox', { name: '질문 입력' }).fill('보통 회복은 얼마나 걸려요?');
  await page.getByRole('button', { name: '보내기' }).click();

  await expect(page.getByText(/등록하신 약에 근거하지 않았습니다/)).toBeVisible();
  await expect(page.getByText(/개인 진료기록에 근거하지 않았습니다/)).toHaveCount(0);
});

test('약에 근거한 챗봇 답변은 약봉투와 공식 자료 출처를 함께 표시한다', async ({ page }) => {
  await page.goto('/dev/chat');
  await page.getByRole('textbox', { name: '질문 입력' }).fill('리바록사반 먹을 때 조심할 점은?');
  await page.getByRole('button', { name: '보내기' }).click();

  await expect(page.getByText('약봉투 · 리바록사반 10mg')).toBeVisible();
  await expect(page.getByText('e약은요 · 리바록사반')).toBeVisible();
});

test('게스트 마이페이지는 로그인 유도와 약관·개인정보만 보여준다', async ({ page }) => {
  await page.goto('/dev/my-guest');

  await expect(page.getByText('로그인하지 않았어요')).toBeVisible();
  await expect(page.getByText('이용약관')).toBeVisible();
  await expect(page.getByText('개인정보 처리 안내')).toBeVisible();
  await expect(page.getByRole('heading', { name: '내 관리' })).toHaveCount(0);
  await expect(page.getByRole('switch')).toHaveCount(0);
});

test('로그인 마이페이지는 내 관리와 알림 토글, 계정을 보여준다', async ({ page }) => {
  await page.goto('/dev/my-authenticated');

  await expect(page.getByRole('heading', { name: '내 관리' })).toBeVisible();
  await expect(page.getByRole('button', { name: /복용약 4개/ })).toBeVisible();
  await expect(page.getByRole('button', { name: /영양제 3개/ })).toBeVisible();
  await expect(page.getByRole('switch')).toHaveCount(2);
  await expect(page.getByText('poke@example.com').first()).toBeVisible();
});

test('하단 탭은 구현된 실제 화면 경로로 이동한다', async ({ page }) => {
  await page.goto('/dev/medications');
  await page.getByRole('button', { name: '영양제', exact: true }).click();
  await expect(page).toHaveURL(/\/supplements$/);
  await page.getByRole('button', { name: '챗봇', exact: true }).click();
  await expect(page).toHaveURL(/\/chat$/);
  await page.getByRole('button', { name: '마이', exact: true }).click();
  await expect(page).toHaveURL(/\/my$/);
});

test('게스트 배너를 넘기면 현재 위치 인디케이터가 함께 바뀐다', async ({ page }) => {
  await page.goto('/home');
  const carousel = page.getByRole('region', { name: '포케 기능 소개' }).locator('.overflow-x-auto');

  await expect(page.getByLabel('현재 배너 1 / 3')).toBeVisible();
  await carousel.evaluate((element) => element.scrollTo({ left: element.scrollWidth, behavior: 'instant' }));
  await expect(page.getByLabel('현재 배너 3 / 3')).toBeVisible();
});
