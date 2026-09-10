import { expect, test, type Page } from 'playwright/test';

test.skip(process.env.VITE_USE_MOCK !== 'false', 'Uses isolated challenge API responses.');
test.setTimeout(45_000);

async function prepare(page: Page) {
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'browse-filter-review');
    sessionStorage.setItem('poke.account-principal', 'filter@example.com');
  });
  await page.route('https://fonts.googleapis.com/**', route => route.abort());
  await page.route('https://fonts.gstatic.com/**', route => route.abort());
  await page.route(url => url.pathname.startsWith('/api/'), route => route.fulfill({ status: 404, json: {} }));
  await page.route('**/api/v1/user/challenge-catalog?*', route => route.fulfill({ json: {
    items: [{
      id: 101, name: '매일 걷기', phrase: '매일 실천해요', description: '하루 한 번 기록해요.',
      challenge_type_code: 'OFFICIAL', period_code: 'D14', duration_days: 14,
      check_type_code: 'SELF', frequency_code: 'DAILY', reward_badge: null,
      recruit_start_at: '2026-09-01T00:00:00+09:00', recruit_end_at: '2026-09-30T23:59:59+09:00',
      can_join: true, participation_id: null,
    }], total_count: 1, offset: 0, limit: 100,
  } }));
  await page.route('**/api/v1/user/challenges', route => route.fulfill({ json: { items: [], total_count: 0 } }));
  await page.route('**/api/v1/user/custom-challenge-recommendations', route => route.fulfill({ json: {
    items: [{ templateId: 31, challengeType: 'MEDICATION', challengeName: '처방 일정 지키기', rewardBadge: null,
      action: 'NONE', targets: [{ id: 41, name: '새 처방', existingParticipationId: null }] }], totalCount: 1,
  } }));
}

for (const width of [320, 390, 1440]) {
  test(`browse filter popup stays within the app content at ${width}px and preserves keyboard filtering`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    await prepare(page);
    await page.goto('/challenges/browse');
    const filter = page.getByRole('combobox', { name: '챌린지 종류 필터' });
    const rows = page.getByRole('region', { name: '챌린지 목록' }).getByRole('button');
    await expect(rows).toHaveCount(2);
    const triggerBounds = (await filter.boundingBox())!;
    await filter.click();
    const popup = page.getByRole('listbox');
    await expect(popup).toBeVisible();
    await expect(popup.getByRole('option')).toHaveText(['전체', '공식', '맞춤']);
    await expect(popup.getByRole('option', { name: '전체', exact: true })).toHaveAttribute('aria-selected', 'true');
    const popupBounds = (await popup.boundingBox())!;
    expect(Math.abs(popupBounds.x - triggerBounds.x)).toBeLessThanOrEqual(1);
    expect(Math.abs(popupBounds.width - triggerBounds.width)).toBeLessThanOrEqual(1);
    expect(popupBounds.x + popupBounds.width).toBeLessThanOrEqual(width);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`browse-filter-open-${width}.png`), fullPage: true, animations: 'disabled' });

    await page.keyboard.press('Escape');
    await expect(popup).toBeHidden();
    await expect(filter).toBeFocused();
    await expect(rows).toHaveCount(2);
    await filter.press('Enter');
    await expect(popup).toBeVisible();
    await expect(popup.getByRole('option', { name: '전체', exact: true })).toBeFocused();
    await page.keyboard.press('ArrowDown');
    await expect(popup.getByRole('option', { name: '공식', exact: true })).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(filter).toContainText('공식');
    await expect(filter).toBeFocused();
    await expect(rows).toHaveCount(1);
    await expect(rows).toHaveAccessibleName('매일 걷기 자세히 보기');

    await filter.click();
    await popup.getByRole('option', { name: '맞춤', exact: true }).click();
    await expect(rows).toHaveCount(1);
    await expect(rows).toHaveAccessibleName('처방 일정 지키기 대상 선택');
    await filter.click();
    await popup.getByRole('option', { name: '전체', exact: true }).click();
    await expect(rows).toHaveCount(2);
  });
}
