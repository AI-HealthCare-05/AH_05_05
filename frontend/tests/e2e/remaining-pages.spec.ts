import { expect, test, type Page } from 'playwright/test';

async function chooseAlarmTime(page: Page, hour: string, minute: string) {
  const sheet = page.getByRole('dialog');
  await sheet.getByLabel('시').click();
  await page.getByRole('option', { name: `${hour}시`, exact: true }).click();
  await sheet.getByLabel('분').click();
  await page.getByRole('option', { name: `${minute}분`, exact: true }).click();
}

test.setTimeout(20_000);

test('복용약 화면은 약봉투 원본 없이 care episode 목록을 보여준다', async ({ page }) => {
  await page.goto('/dev/medications');

  await expect(page.getByRole('heading', { name: '복용약' })).toBeVisible();
  await expect(page.getByRole('button', { name: /8월 22일 처방.*약 4개/ })).toBeVisible();
  await expect(page.getByRole('button', { name: /8월 24일 처방.*약 1개/ })).toBeVisible();
  await expect(page.getByRole('img', { name: '등록한 약봉투 원본' })).toHaveCount(0);
  await expect(page.getByText('이 기록의 약봉투 원본')).toHaveCount(0);
});

test('care episode를 누르면 그 회차의 알림 시간과 약만 상세에서 보여준다', async ({ page }) => {
  await page.goto('/dev/medications');
  await page.getByRole('button', { name: /8월 22일 처방.*약 4개/ }).click();

  await expect(page).toHaveURL(/\/medications\/12$/);
  await expect(page.getByRole('heading', { name: '처방 상세' })).toBeVisible();
  await expect(page.getByText('아침 08:00 · 점심 13:00 · 저녁 19:00')).toBeVisible();
  await expect(page.getByRole('heading', { name: '약 4개' })).toBeVisible();
  await expect(page.getByText('필요할 때만 · 알림 없음')).toBeVisible();
  await expect(page.getByText('아목시실린 500mg')).toHaveCount(0);
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

test('챗봇 답변의 문단 줄바꿈을 화면에서도 유지한다', async ({ page }) => {
  await page.goto('/dev/chat');
  await page.getByRole('textbox', { name: '질문 입력' }).fill('리바록사반 주의사항을 알려줘');
  await page.getByRole('button', { name: '보내기' }).click();

  const answer = page.getByText(/리바록사반을 복용하는 동안/);
  await expect(answer).toBeVisible();
  await expect(answer).toHaveCSS('white-space', 'pre-wrap');
  await expect(answer).toContainText(/알려주세요\.\n\n임의로 중단하지 마세요\./);
});

test('로그인하지 않은 마이 방문은 뒤로 가도 마이페이지를 복원하지 않고 로그인으로 이동한다', async ({ page }) => {
  await page.goto('/home');
  await page.getByRole('button', { name: '마이', exact: true }).click();

  await expect(page).toHaveURL(/\/login$/);
  await page.goBack();
  await expect(page).toHaveURL(/\/home$/);
});

test('개발용 게스트 마이페이지는 리디렉션하지 않고 로그인 유도 카드를 보여주지 않는다', async ({ page }) => {
  await page.goto('/dev/my-guest');

  await expect(page).toHaveURL(/\/dev\/my-guest$/);
  await expect(page.getByRole('heading', { name: '마이페이지' })).toBeVisible();
  await expect(page.getByText('로그인하지 않았어요')).toHaveCount(0);
  await expect(page.getByText('이용약관')).toHaveCount(0);
  await expect(page.getByText('개인정보 처리 안내')).toHaveCount(0);
  await expect(page.getByRole('heading', { name: '내 관리' })).toHaveCount(0);
  await expect(page.getByRole('switch')).toHaveCount(0);
  await expect(page.getByRole('navigation', { name: '주요 화면' })).toBeVisible();
});

test('로그인 페이지는 법적 안내와 게스트 안전 하단 탭을 제공한다', async ({ page }) => {
  await page.goto('/login');

  await expect(page.getByRole('link', { name: '이용약관' })).toHaveAttribute('href', '/terms');
  await expect(page.getByRole('link', { name: '개인정보 처리 안내' })).toHaveAttribute(
    'href',
    '/privacy',
  );
  await expect(page.getByRole('button', { name: '마이', exact: true })).toHaveAttribute(
    'aria-current',
    'page',
  );
  await page.getByRole('button', { name: '복약', exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.getByRole('button', { name: '홈', exact: true }).click();
  await expect(page).toHaveURL(/\/home$/);
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
  await page.evaluate(() => {
    sessionStorage.setItem('poke.access-token', 'e2e-navigation-token');
    sessionStorage.setItem('poke.account-principal', 'navigation@example.com');
  });
  await page.reload();
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
  await carousel.evaluate((element) => {
    const banners = Array.from(element.children) as HTMLElement[];
    const firstOffset = banners[0]?.offsetLeft ?? 0;
    element.scrollTo({ left: banners[2].offsetLeft - firstOffset, behavior: 'instant' });
  });
  await expect(page.getByLabel('현재 배너 3 / 3')).toBeVisible();
});

test('홈 기능 배너는 마우스가 배너 위에 있어도 자동으로 다음 장을 보여준다', async ({ page }) => {
  await page.goto('/home');
  await page.getByRole('region', { name: '포케 기능 소개' }).hover();

  await expect(page.getByLabel('현재 배너 1 / 3')).toBeVisible();
  await expect(page.getByLabel('현재 배너 2 / 3')).toBeVisible({ timeout: 4_500 });
});

test('홈 기능 배너는 마지막 장에서도 같은 방향으로 첫 장을 이어 보여준다', async ({ page }) => {
  await page.goto('/home');
  const carousel = page.getByRole('region', { name: '포케 기능 소개' }).locator('.overflow-x-auto');

  await carousel.evaluate((element) => {
    const banners = Array.from(element.children) as HTMLElement[];
    const firstOffset = banners[0]?.offsetLeft ?? 0;
    element.scrollTo({ left: banners[2].offsetLeft - firstOffset, behavior: 'instant' });
  });
  await expect(page.getByLabel('현재 배너 3 / 3')).toBeVisible();
  await page.waitForTimeout(200);

  await carousel.evaluate((element) => {
    element.dataset.autoplayBaseline = String(element.scrollLeft);
    element.dataset.autoplayMax = String(element.scrollLeft);
    element.addEventListener('scroll', () => {
      const previousMax = Number(element.dataset.autoplayMax ?? element.scrollLeft);
      element.dataset.autoplayMax = String(Math.max(previousMax, element.scrollLeft));
    });
  });
  await page.waitForTimeout(3_500);

  const movement = await carousel.evaluate((element) => ({
    baseline: Number(element.dataset.autoplayBaseline),
    max: Number(element.dataset.autoplayMax),
  }));
  expect(movement.max).toBeGreaterThan(movement.baseline + 10);
  await expect(page.getByLabel('현재 배너 1 / 3')).toBeVisible();
});

test('홈 기능 배너에는 자동 넘김 제어 문구를 노출하지 않는다', async ({ page }) => {
  await page.goto('/home');

  await expect(page.getByRole('button', { name: /자동 넘김/ })).toHaveCount(0);
});

test('동작 줄이기 환경에서는 홈 기능 배너를 자동으로 넘기지 않는다', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/home');

  await expect(page.getByRole('button', { name: /자동 넘김/ })).toHaveCount(0);
  await page.waitForTimeout(3_500);
  await expect(page.getByLabel('현재 배너 1 / 3')).toBeVisible();
});

test('복용약의 알림 시간은 시간 네 개만 있는 전용 화면으로 들어간다', async ({ page }) => {
  await page.goto('/dev/medications');
  await page.getByRole('button', { name: /8월 22일 처방.*약 4개/ }).click();
  await page.getByRole('button', { name: /알림 시간/ }).click();

  await expect(page).toHaveURL(/\/medication-alarm-times$/);
  await expect(page.getByRole('heading', { name: '알림 시간' })).toBeVisible();
  await expect(page.getByRole('button', { name: /취침약 22:30/ })).toBeVisible();
  await expect(page.getByText('처음 약을 언제부터 드셨나요?')).toHaveCount(0);
  await expect(page.getByRole('region', { name: '자동 배정 시간 확인' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: /저장하고|건너뛰기/ })).toHaveCount(0);
});

test('시간 선택 시트는 기본 시간 프리셋을 보여주지 않는다', async ({ page }) => {
  await page.goto('/dev/medication-alarm-times');
  await page.getByRole('button', { name: /취침약 22:30/ }).click();

  const sheet = page.getByRole('dialog');
  await expect(sheet.getByRole('button', { name: '아침약 08:00' })).toHaveCount(0);
  await expect(sheet.getByRole('button', { name: '점심약 13:00' })).toHaveCount(0);
  await expect(sheet.getByRole('button', { name: '저녁약 19:00' })).toHaveCount(0);
  await expect(sheet.getByRole('button', { name: '취침약 22:00' })).toHaveCount(0);
});

test('앞뒤 시간보다 같거나 넘어가면 팝업을 띄우고 적용하지 않는다', async ({ page }) => {
  await page.goto('/dev/medication-alarm-times');
  await page.getByRole('button', { name: /점심약 13:00/ }).click();
  await chooseAlarmTime(page, '19', '00');
  await page.getByRole('button', { name: '이 시간 적용' }).click();

  await expect(page.getByRole('heading', { name: '시간을 적용할 수 없어요' })).toBeVisible();
  await expect(
    page.getByText('복약 시간은 아침약 → 점심약 → 저녁약 → 취침약 순서로 설정해주세요.'),
  ).toBeVisible();
  await page.getByRole('button', { name: '확인' }).click();
  await expect(page.getByRole('heading', { name: '시간 선택' })).toBeVisible();
  await page.getByRole('button', { name: '취소' }).click();
  await expect(page.getByRole('button', { name: /점심약 13:00/ })).toBeVisible();
  await expect(page.getByText('알림 시간을 바꿨어요.')).toHaveCount(0);
});

test('3시간 미만이어도 앞뒤 순서만 맞으면 즉시 저장한다', async ({ page }) => {
  await page.goto('/dev/medication-alarm-times');
  await page.getByRole('button', { name: /아침약 08:00/ }).click();
  await chooseAlarmTime(page, '12', '30');
  await page.getByRole('button', { name: '이 시간 적용' }).click();

  await expect(page).toHaveURL(/\/dev\/medication-alarm-times$/);
  await expect(page.getByRole('button', { name: /아침약 12:30/ })).toBeVisible();
  await expect(page.getByText('알림 시간을 바꿨어요.')).toBeVisible();
});

test('최초 복약 시간 설정에서도 순서가 겹치는 시각은 적용하지 않는다', async ({ page }) => {
  await page.goto('/dev/medication-schedule');
  await page.getByRole('button', { name: /점심약 13:00/ }).click();
  await chooseAlarmTime(page, '19', '00');
  await page.getByRole('button', { name: '이 시간 적용' }).click();

  await expect(page.getByRole('heading', { name: '시간을 적용할 수 없어요' })).toBeVisible();
  await expect(
    page.getByText('아침약 → 점심약 → 저녁약 → 취침약 순서로 정해주세요.'),
  ).toHaveCount(0);
  await page.getByRole('button', { name: '확인' }).click();
  await page.getByRole('button', { name: '취소' }).click();
  await expect(page.getByRole('button', { name: /점심약 13:00/ })).toBeVisible();
});

test('복약 시간 설정은 약별 시간, 시작일, 알림 시각, 저장 순서로 보여준다', async ({ page }) => {
  await page.goto('/dev/medication-schedule');

  const medicationSection = page.getByText('약마다 먹는 시간을 확인해주세요', { exact: true });
  const startSection = page.getByText('처음 약을 언제부터 드셨나요?', { exact: true });
  const alarmSection = page.getByText('어느 시간에 알람을 드릴까요?', { exact: true });
  const saveSection = page.getByRole('button', { name: '저장하고 계속' });
  const positions = await Promise.all(
    [medicationSection, startSection, alarmSection, saveSection].map(async (locator) => {
      const box = await locator.boundingBox();
      expect(box).not.toBeNull();
      return box!.y;
    }),
  );

  expect(positions[0]).toBeLessThan(positions[1]);
  expect(positions[1]).toBeLessThan(positions[2]);
  expect(positions[2]).toBeLessThan(positions[3]);
});

test('복약 시작 시간대는 알림을 위한 필수 선택임을 표시한다', async ({ page }) => {
  await page.goto('/dev/medication-schedule');

  const startSlotGroup = page.getByRole('group', { name: '복약 시작 시간대 (필수)' });
  await expect(startSlotGroup).toBeVisible();
  await expect(startSlotGroup.getByRole('button')).toHaveCount(4);
  await expect(page.getByText('필수', { exact: true })).toBeVisible();
  await expect(
    page.getByText('알림을 받으려면 복약 시작 시간대를 선택해주세요.', { exact: true }),
  ).toBeVisible();
});

test('복용약 카드를 누르면 그 약의 시간대만 시트에서 바꾼다', async ({ page }) => {
  await page.goto('/dev/medications');
  await page.getByRole('button', { name: /8월 22일 처방.*약 4개/ }).click();
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

test('복용약 목록과 상세 어디에도 약봉투 원본을 다시 보여주지 않는다', async ({ page }) => {
  await page.goto('/dev/medications');

  await expect(page.getByRole('img', { name: '등록한 약봉투 원본' })).toHaveCount(0);
  await page.getByRole('button', { name: /8월 22일 처방.*약 4개/ }).click();
  await expect(page.getByRole('img', { name: '등록한 약봉투 원본' })).toHaveCount(0);
});
