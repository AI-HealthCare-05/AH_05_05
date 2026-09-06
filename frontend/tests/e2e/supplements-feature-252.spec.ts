import { expect, test, type Page, type Route } from 'playwright/test';

import { IS_REAL_API, MOCK_ONLY_REASON, REAL_API_ONLY_REASON } from './helpers/mode';

test('등록 영양제는 상세에서 내 기록을 보여주고 별점 수정과 복용 중단을 제공한다', async ({ page }) => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
  await page.goto('/dev/supplements');

  const list = page.getByRole('region', { name: '먹고 있는 영양제' });
  await list.getByRole('button', { name: /오메가3/ }).click();

  await expect(page.getByRole('heading', { name: '내 영양제' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '내 기록' })).toBeVisible();
  const record = page.getByRole('region', { name: '내 기록' });
  await expect(record.getByText('내 별점', { exact: true })).toBeVisible();
  await expect(record.getByText('내 메모', { exact: true })).toBeVisible();
  await expect(record.getByText('아침 식후에 먹기', { exact: true })).toBeVisible();
  await expect(record.getByText('내 후기', { exact: true })).toBeVisible();
  await expect(record.getByText('꾸준히 챙겨 먹기 편해요.', { exact: true })).toBeVisible();
  await expect(record.getByRole('button', { name: '제품 정보 보기' })).toBeVisible();

  await page.getByRole('button', { name: '별점 수정' }).click();
  const ratingSheet = page.getByRole('dialog', { name: '별점 수정' });
  await expect(ratingSheet).toBeVisible();
  await ratingSheet.getByRole('button', { name: '별 5점' }).click();
  await ratingSheet.getByRole('button', { name: '저장' }).click();
  await expect(ratingSheet).toBeHidden();
  await expect(record.getByText('★★★★★', { exact: true })).toBeVisible();

  await page.getByRole('button', { name: '복용 중단하기' }).click();
  const stopDialog = page.getByRole('dialog', { name: '오메가3 복용을 중단할까요?' });
  await expect(stopDialog).toBeVisible();
  await expect(stopDialog.getByText('오메가3 · 1정 · 아침 · 저녁', { exact: true })).toBeVisible();
  await stopDialog.getByRole('button', { name: '중단하기' }).click();
  await expect(page.getByRole('heading', { name: '내 영양제' })).toHaveCount(0);
  await expect(page.getByRole('region', { name: '먹고 있는 영양제' }).getByText('오메가3')).toHaveCount(0);
});

test('미평가 영양제는 별점 선택 상태와 상세 요약을 즉시 반영한다', async ({ page }) => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
  await page.goto('/dev/supplements');

  await page.getByRole('region', { name: '먹고 있는 영양제' }).getByRole('button', { name: /종합비타민/ }).click();
  const summary = page.getByRole('region', { name: '내 영양제 요약' });
  const record = page.getByRole('region', { name: '내 기록' });
  await expect(record.getByText('☆☆☆☆☆', { exact: true })).toBeVisible();
  await record.getByRole('button', { name: '별점 수정' }).click();

  const ratingSheet = page.getByRole('dialog', { name: '별점 수정' });
  const ratingGroup = ratingSheet.getByRole('group', { name: '별점 선택' });
  const oneStar = ratingGroup.getByRole('button', { name: '별 1점' });
  const threeStars = ratingGroup.getByRole('button', { name: '별 3점' });
  const fourStars = ratingGroup.getByRole('button', { name: '별 4점' });
  await expect(oneStar).toHaveAttribute('aria-pressed', 'false');
  await expect(oneStar).toHaveClass(/text-muted-foreground/);
  await threeStars.click();
  await expect(threeStars).toHaveAttribute('aria-pressed', 'true');
  await expect(threeStars).toHaveClass(/text-warning-strong/);
  await expect(fourStars).toHaveClass(/text-muted-foreground/);
  await ratingSheet.getByRole('button', { name: '저장' }).click();

  await expect(summary.getByLabel('별 3점')).toBeVisible();
  await expect(summary.getByText('★★★☆☆', { exact: true })).toBeVisible();
});

test('일괄 중단 부분 실패는 성공 행을 재시도하지 않고 실패 행만 남긴다', async ({ page }) => {
  test.skip(!IS_REAL_API, REAL_API_ONLY_REASON);
  await authenticate(page);

  const registrations = [
    registrationFor('성공한 영양제', 9201),
    registrationFor('실패한 영양제', 9202),
  ];
  const deletedIds: number[] = [];
  let failOnce = true;

  await page.route('**/api/v1/med/user-suppl-nutr**', async (route) => {
    const request = route.request();
    if (request.method() === 'GET') {
      await fulfillJson(route, {
        items: registrations,
        total: registrations.length,
        offset: 0,
        limit: 100,
        nutrient_standard: null,
      });
      return;
    }
    const id = Number(new URL(request.url()).pathname.split('/').pop());
    deletedIds.push(id);
    if (id === 9202 && failOnce) {
      failOnce = false;
      await fulfillJson(route, { detail: '일시적인 중단 실패' }, 500);
      return;
    }
    await route.fulfill({ status: 204 });
  });
  await page.route('**/api/v1/users/me', async (route) => {
    await fulfillJson(route, {
      name: '테스트 사용자',
      maskedName: '테***자',
      phoneNumber: '01012345678',
      birthDate: '2000-01-01',
      gender: 'MALE',
    });
  });

  await page.goto('/supplements');
  const list = page.getByRole('region', { name: '먹고 있는 영양제' });
  await expect(list.getByRole('button', { name: /성공한 영양제/ })).toBeVisible();
  await page.getByRole('button', { name: '편집' }).click();
  await page.getByRole('checkbox', { name: '성공한 영양제 선택' }).check();
  await page.getByRole('checkbox', { name: '실패한 영양제 선택' }).check();
  await page.getByRole('button', { name: '선택한 2개 삭제' }).click();

  await page.getByRole('button', { name: '확인' }).click();
  await expect(list.getByText('성공한 영양제', { exact: true })).toHaveCount(0);
  await expect(list.getByText('실패한 영양제', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '선택한 1개 삭제' })).toBeVisible();
  await page.getByRole('button', { name: '선택한 1개 삭제' }).click();

  await expect.poll(() => deletedIds).toEqual([9201, 9202, 9202]);
  await expect(page.getByRole('button', { name: '완료' })).toHaveCount(0);
  await expect(page.getByText('실패한 영양제', { exact: true })).toHaveCount(0);
});

function registrationFor(name: string, id: number) {
  return {
    id,
    custom_name: name,
    dose_amount: '1.000',
    dose_unit: '정',
    start_date: '2026-09-04',
    end_date: null,
    status: 'ACTIVE',
    score: null,
    review_body: null,
    note: null,
    created_at: '2026-09-04T09:00:00+09:00',
    updated_at: null,
    slots: [{ slot: 'MORNING', time: '08:00:00' }],
    supplement: null,
  };
}

async function authenticate(page: Page) {
  await page.addInitScript((token) => {
    window.sessionStorage.setItem('poke.access-token', token);
    window.sessionStorage.setItem('poke.account-principal', 'supplement-e2e@example.com');
  }, 'e2e-supplement-token');
}

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });
}
