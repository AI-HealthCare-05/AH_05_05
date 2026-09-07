import { expect, test } from 'playwright/test';

import { IS_REAL_API, MOCK_ONLY_REASON } from './helpers/mode';

test.beforeEach(() => {
  test.skip(IS_REAL_API, MOCK_ONLY_REASON);
});

test('맞춤 챌린지에서 복약 참여 대상 화면으로 이동한다', async ({ page }) => {
  await page.goto('/dev/challenges/tailored');

  await expect(page.getByRole('heading', { name: '맞춤 챌린지' })).toBeVisible();
  await expect(page.getByText('추천 챌린지', { exact: true })).toHaveCount(0);

  await page.getByRole('link', { name: /내 복약 루틴/ }).click();
  await expect(page).toHaveURL(/\/dev\/challenges\/tailored\/medication$/);
  await expect(page.getByRole('heading', { name: '내 복약 루틴' })).toBeVisible();
  await expect(page.getByText('감기약 · 09.11 ~ 09.13')).toBeVisible();
});

test('맞춤 기록이 없을 때 등록과 둘러보기 경로를 안내한다', async ({ page }) => {
  await page.goto('/dev/challenges/tailored-empty');

  await expect(page.getByRole('heading', { name: '맞춤 챌린지' })).toBeVisible();
  await expect(page.getByText('맞춤 챌린지에 활용할 기록이 아직 없어요')).toBeVisible();
  await expect(page.getByRole('link', { name: /기록 등록하기/ })).toHaveAttribute('href', '/dev/medications');
  await expect(page.getByRole('link', { name: /둘러보기/ })).toHaveAttribute('href', '/dev/challenges/browse');
});

test('영양제 참여 대상을 여러 개 선택해 하나의 챌린지로 시작한다', async ({ page }) => {
  await page.goto('/dev/challenges/tailored/supplement');

  await expect(page.getByRole('checkbox', { name: '오메가3 · 저녁' })).toBeChecked();
  await expect(page.getByRole('checkbox', { name: '종합비타민 · 아침' })).toBeChecked();
  await page.getByRole('checkbox', { name: '유산균 · 아침' }).check();
  await expect(page.getByText('선택한 영양제 3개')).toBeVisible();

  await page.getByRole('button', { name: '선택한 영양제로 참여하기' }).click();
  await expect(page).toHaveURL(/\/dev\/challenges\/participations\/part-supplement-active$/);
  await expect(page.getByText('선택한 대상 · 오메가3 · 종합비타민 · 유산균')).toBeVisible();
});

test('참여 후 다시 연 복약·영양제 대상 화면은 저장한 선택을 복원한다', async ({ page }) => {
  await page.goto('/dev/challenges/tailored/supplement');
  await page.getByRole('checkbox', { name: '오메가3 · 저녁' }).uncheck();
  await page.getByRole('checkbox', { name: '종합비타민 · 아침' }).uncheck();
  await page.getByRole('checkbox', { name: '유산균 · 아침' }).check();
  await page.getByRole('button', { name: '선택한 영양제로 참여하기' }).click();
  await expect(page.getByText('선택한 대상 · 유산균')).toBeVisible();

  await page.getByRole('button', { name: '뒤로 가기' }).click();
  await page.getByRole('link', { name: '둘러보기' }).click();
  await page.getByRole('link', { name: '내 기록으로 맞춤 챌린지 보기' }).click();
  await page.getByRole('link', { name: /내 영양제 루틴/ }).click();
  await expect(page.getByRole('checkbox', { name: '오메가3 · 저녁' })).not.toBeChecked();
  await expect(page.getByRole('checkbox', { name: '종합비타민 · 아침' })).not.toBeChecked();
  await expect(page.getByRole('checkbox', { name: '유산균 · 아침' })).toBeChecked();

  await page.getByRole('link', { name: '맞춤 챌린지로 돌아가기' }).click();
  await page.getByRole('link', { name: /내 복약 루틴/ }).click();
  await expect(page.getByRole('checkbox', { name: /감기약/ })).toBeDisabled();
  await page.getByRole('checkbox', { name: /9월 7일 처방/ }).check();
  await page.getByRole('button', { name: '이 대상으로 참여하기' }).click();
  await expect(page.getByRole('article', { name: '9월 7일 처방 복약 챌린지', exact: true })).toBeVisible();
  await page.getByRole('link', { name: '둘러보기' }).click();
  await page.getByRole('link', { name: '내 기록으로 맞춤 챌린지 보기' }).click();
  await page.getByRole('link', { name: /내 복약 루틴/ }).click();
  await expect(page.getByRole('checkbox', { name: /감기약/ })).toBeChecked();
  await expect(page.getByRole('checkbox', { name: /9월 7일 처방/ })).toBeChecked();
});

test('주간 목표 횟수와 수행 주 수를 인라인으로 입력한다', async ({ page }) => {
  await page.goto('/dev/challenges/create');
  await page.getByRole('button', { name: '주 몇 회' }).click();
  await page.getByRole('button', { name: '직접 입력' }).click();

  const targetDays = page.getByRole('spinbutton', { name: '일주일 목표 횟수' });
  const durationWeeks = page.getByRole('spinbutton', { name: '수행 주 수' });
  await expect(targetDays).toBeVisible();
  await expect(durationWeeks).toBeVisible();
  await targetDays.fill('4');
  await durationWeeks.fill('2');
  await expect(page.getByText('매주 서로 다른 4일')).toBeVisible();
  await expect(page.getByText('2주 동안 진행해요.')).toBeVisible();
});

test('나만의 챌린지 필수 항목을 검증하고 만든 챌린지로 이동한다', async ({ page }) => {
  await page.goto('/dev/challenges/create');

  await page.getByRole('button', { name: '챌린지 만들기' }).click();
  await expect(page.getByText('목표 이름을 입력해주세요.')).toBeVisible();
  await expect(page.getByText('달성항목을 입력해주세요.')).toBeVisible();

  await page.getByLabel('목표 이름').fill('저녁 산책하기');
  await page.getByLabel('달성항목').fill('저녁에 20분 걷기');
  await page.getByLabel('시작 날짜').fill('2026-09-15');
  await page.getByRole('button', { name: '챌린지 만들기' }).click();

  await expect(page).toHaveURL(/\/dev\/challenges\/participations\//);
  await expect(page.getByRole('heading', { name: '저녁 산책하기' })).toBeVisible();
});

test('기록을 정상적으로 확인하면 체크되고 다시 열어도 한 번만 반영된다', async ({ page }) => {
  await page.goto('/dev/challenges/participations/part-review-active');

  await expect(page.getByText('복약 기록 6회')).toBeVisible();
  await expect(page.getByText('영양제 기록 5회')).toBeVisible();
  const lookup = page.getByRole('link', { name: /복용약 확인/ });
  await expect(lookup).toHaveAttribute('data-checked', 'false');
  await lookup.click();
  await expect(page.getByRole('heading', { name: '복약 기록' })).toBeVisible();
  await expect(page.getByText('9월 7일 처방')).toBeVisible();
  await page.getByRole('link', { name: '챌린지로 돌아가기' }).click();
  await expect(lookup).toHaveAttribute('data-checked', 'true');

  await page.getByRole('link', { name: /복용약 확인/ }).click();
  await page.getByRole('link', { name: '챌린지로 돌아가기' }).click();
  await expect(lookup).toHaveAttribute('data-checked', 'true');
  await expect(page.getByText('1 / 2개 확인')).toBeVisible();
});

test('비어 있거나 잘못 연결된 기록은 열어도 체크하지 않는다', async ({ page }) => {
  await page.goto('/dev/challenges/participations/part-review-active');

  const lookup = page.getByRole('link', { name: /복약 메모 확인/ });
  await expect(lookup).toHaveAttribute('data-checked', 'false');
  await lookup.click();
  await expect(page.getByText('확인할 기록이 아직 없어요.')).toBeVisible();
  await page.getByRole('link', { name: '챌린지로 돌아가기' }).click();
  await expect(lookup).toHaveAttribute('data-checked', 'false');
  await expect(page.getByText('0 / 2개 확인')).toBeVisible();

  await page.goto('/dev/challenges/participations/part-review-active/records/not-a-record');
  await expect(page.getByText('기록을 불러오지 못했어요.')).toBeVisible();
  await page.getByRole('link', { name: '챌린지로 돌아가기' }).click();
  await expect(page.getByText('0 / 2개 확인')).toBeVisible();
});
