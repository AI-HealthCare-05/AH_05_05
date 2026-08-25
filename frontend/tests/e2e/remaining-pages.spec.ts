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
  await expect(page.getByText('poke@example.com')).toHaveCount(0);
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

test('복용약의 알림 시간은 시간 네 개만 있는 전용 화면으로 들어간다', async ({ page }) => {
  await page.goto('/dev/medications');
  await page.getByRole('button', { name: /알림 시간/ }).click();

  await expect(page).toHaveURL(/\/medication-alarm-times$/);
  await expect(page.getByRole('heading', { name: '알림 시간' })).toBeVisible();
  await expect(page.getByRole('button', { name: /취침약 22:30/ })).toBeVisible();
  await expect(page.getByText('처음 약을 언제부터 드셨나요?')).toHaveCount(0);
  await expect(page.getByRole('region', { name: '자동 배정 시간 확인' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: /저장하고|건너뛰기/ })).toHaveCount(0);
});

test('알림 시각을 고치면 즉시 저장하고 같은 화면에 남는다', async ({ page }) => {
  await page.goto('/dev/medication-alarm-times');
  await page.getByRole('button', { name: /취침약 22:30/ }).click();
  await page.getByRole('button', { name: '취침약 22:00' }).click();
  await page.getByRole('button', { name: '이 시간 적용' }).click();

  await expect(page).toHaveURL(/\/dev\/medication-alarm-times$/);
  await expect(page.getByRole('button', { name: /취침약 22:00/ })).toBeVisible();
  await expect(page.getByText('알림 시간을 바꿨어요.')).toBeVisible();
});

test('복용약 카드를 누르면 그 약의 시간대만 시트에서 바꾼다', async ({ page }) => {
  await page.goto('/dev/medications');
  await page.getByRole('button', { name: /셀레콕시브 200mg/ }).click();

  const sheet = page.getByRole('dialog');
  await expect(sheet.getByRole('heading', { name: '셀레콕시브 복용 시간' })).toBeVisible();
  await expect(sheet.getByRole('button', { name: '셀레콕시브 점심약' })).toHaveAttribute(
    'aria-pressed',
    'false',
  );
  await expect(sheet.getByText('리바록사반 10mg')).toHaveCount(0);
  await sheet.getByRole('button', { name: '셀레콕시브 점심약' }).click();
  await sheet.getByRole('button', { name: '저장' }).click();

  await expect(page.getByRole('button', { name: /셀레콕시브 200mg/ }).getByText('점심')).toBeVisible();
});

test('복용약 화면은 이 기록의 약봉투 원본 한 장을 다시 보여준다', async ({ page }) => {
  await page.goto('/dev/medications');

  await expect(page.getByRole('img', { name: '등록한 약봉투 원본' })).toBeVisible();
  await expect(page.getByRole('region', { name: '약 4개' }).getByRole('img')).toHaveCount(0);
});
