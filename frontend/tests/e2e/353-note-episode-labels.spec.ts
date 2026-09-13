import { expect, test } from 'playwright/test';

import { IS_REAL_API } from './helpers/mode';

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'note-episode-labels-test');
    sessionStorage.setItem('poke.account-principal', 'note-episode-labels@example.com');
  });
});

test('동일 이름·날짜의 처방은 실제 약으로 구분하고 같은 약·정보 누락은 지역 순번으로 구분한다', async ({ page }) => {
  test.skip(!IS_REAL_API, 'Route-stub API contract test');
  const longName = '아세트아미노펜'.repeat(12);
  const variants = [
    { representativeMedicationName: '타이레놀', medicationCount: 3 },
    { representativeMedicationName: '아목시실린', medicationCount: 1 },
    { representativeMedicationName: '타이레놀', medicationCount: 3 },
    {},
    { representativeMedicationName: null, medicationCount: 0 },
    { representativeMedicationName: longName, medicationCount: 2 },
    { alias: null, startDate: null, representativeMedicationName: '무명약', medicationCount: 1 },
    { alias: null, startDate: null, representativeMedicationName: '무명약', medicationCount: 1 },
  ];
  await page.route('**/api/v1/med/notes/episodes**', (route) => route.fulfill({
    json: variants.map((variant, index) => ({
      careEpisodeId: 7001 + index, alias: '감기약', startDate: '2026-09-01', status: 'ACTIVE',
      noteCount: index === 2 ? 3 : 1, ...variant,
    })),
  }));
  await page.route(/\/api\/v1\/med\/notes(?:\?.*)?$/, (route) => {
    const filter = new URL(route.request().url()).searchParams.get('episodeId');
    return route.fulfill({ json: { items: [], total: filter === '7003' ? 3 : 0, nextCursor: null } });
  });
  await page.goto('/medications/notes');
  await page.getByRole('tab', { name: '작성한 메모' }).click();
  for (const label of [
    '감기약 · 처방 1', '감기약', '감기약 · 처방 2',
    '처방 · 처방 1', '처방 · 처방 2',
  ]) {
    await expect(page.getByText(label, { exact: true }).first()).toBeVisible();
  }
  await expect(page.getByRole('button', { name: new RegExp(`${longName} 외 1개 펼치기`) })).toBeVisible();
  await page.getByRole('button', { name: /감기약 · 처방 2 · 2026년 9월 1일 · 타이레놀 외 2개 펼치기/ }).click();
  await expect(page).toHaveURL('/medications/notes?episodeId=7003');
  await expect(page.getByRole('heading', { name: '건강상태 기록 3개' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test('mock 요약도 실제 약 목록의 대표약과 개수로 중복 처방을 구분한다', async ({ page }) => {
  test.skip(IS_REAL_API, 'Mock adapter parity test');
  await page.addInitScript(() => {
    const notes = [
      { careEpisodeId: 7001, availableMedications: [{ id: 10, name: '타이레놀', dose: null }] },
      { careEpisodeId: 7002, availableMedications: [{ id: 30, name: '두번째 약', dose: null }, { id: 20, name: '아목시실린', dose: null }] },
    ].map((episode, index) => ({
      id: 901 + index, ...episode, careEpisodeAlias: '감기약', careEpisodeStartDate: '2026-09-01',
      careEpisodeStatus: 'ACTIVE', medicationId: null, medication: null,
      dosedAt: '2026-09-02T08:00:00', body: `메모 ${index + 1}`, createdAt: '2026-09-02T09:00:00', updatedAt: null,
    }));
    sessionStorage.setItem('rxvita.mock.medication-notes:note-episode-labels%40example.com', JSON.stringify(notes));
  });
  await page.goto('/medications/notes');
  await page.getByRole('tab', { name: '작성한 메모' }).click();
  await expect(page.getByRole('button', { name: /감기약 · 2026년 9월 1일 · 아목시실린 외 1개 펼치기/ })).toBeVisible();
  await page.getByRole('button', { name: /감기약 · 2026년 9월 1일 · 타이레놀 펼치기/ }).click();
  await expect(page.getByText('메모 1', { exact: true })).toBeVisible();
  await expect(page.getByText('메모 2', { exact: true })).toHaveCount(0);
});
