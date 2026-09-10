import { expect, test, type Page } from 'playwright/test';
import type { CustomChallengeParticipation } from '../../src/entities/custom-challenge';

test.skip(process.env.VITE_USE_MOCK !== 'false', 'Uses isolated API fixtures.');
test.setTimeout(60_000);

async function openCalendar(page: Page, type: 'MEDICATION' | 'SUPPLEMENT' = 'MEDICATION') {
  const item: CustomChallengeParticipation = {
    id: 701, templateId: 31, challengeType: type, challengeName: '매일 챙기는 건강 루틴',
    rewardBadge: null, status: 'ACTIVE', joinedAt: '2026-09-09T00:00:00+09:00',
    endAt: '2026-09-12T23:59:59+09:00', actualEndDate: '2026-09-12',
    targetCount: 3, completedCount: 1, progressRate: '33.33', action: 'NONE',
    targets: [{ id: 801, sourceId: 101, name: '실제 복용 대상' }],
    // Daily completion remains editable because a later challenge goal is still pending.
    occurrences: [...[0, 1].map(index => ({ id: 900 + index, targetId: 801, scheduledDate: '2026-09-10',
      slot: index === 0 ? 'MORNING' : 'EVENING', scheduledAt: `2026-09-10T${index === 0 ? '08' : '18'}:00:00+09:00`, isCompleted: index === 0 })),
      { id: 902, targetId: 801, scheduledDate: '2026-09-11', slot: 'MORNING', scheduledAt: '2026-09-11T08:00:00+09:00', isCompleted: false }],
  };
  const unexpected: string[] = [];
  await page.clock.setFixedTime(new Date('2026-09-10T19:00:00+09:00'));
  await page.addInitScript(() => {
    sessionStorage.setItem('poke.access-token', 'motion-fixture');
    sessionStorage.setItem('poke.account-principal', 'motion@example.com');
  });
  await page.route('https://fonts.googleapis.com/**', route => route.abort());
  await page.route('https://fonts.gstatic.com/**', route => route.abort());
  await page.route(url => url.pathname.startsWith('/api/'), route => {
    const request = route.request(); const path = new URL(request.url()).pathname;
    if (request.method() === 'GET' && path === '/api/v1/user/custom-challenge-participations/701') return route.fulfill({ json: item });
    if (request.method() === 'GET' && path === '/api/v1/user/custom-challenges/badges') return route.fulfill({ json: { items: [], totalCount: 0 } });
    unexpected.push(`${request.method()} ${path}`); return route.fulfill({ status: 404, json: {} });
  });
  await page.goto('/challenges/custom-participations/701');
  const calendar = page.getByRole('region', { name: '챌린지 달력', exact: true });
  await expect(calendar).toBeVisible();
  const refresh = async () => {
    const response = page.waitForResponse(response => new URL(response.url()).pathname === '/api/v1/user/custom-challenge-participations/701');
    await page.evaluate(() => window.dispatchEvent(new Event('focus'))); await response;
  };
  return { item, calendar, unexpected, refresh };
}

for (const type of ['MEDICATION', 'SUPPLEMENT'] as const) {
  test(`${type} draws the centered daily circle and check only after all actual records complete`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 390, height: 900 });
    const { item, calendar, unexpected, refresh } = await openCalendar(page, type);
    await expect(calendar.getByRole('status')).toHaveCount(0);
    const recordCheck = calendar.getByRole('listitem').first().locator('svg path');
    expect(await recordCheck.evaluate(element => element.getAnimations().length)).toBeGreaterThan(0);
    item.occurrences[1].isCompleted = true;
    await refresh();
    const status = calendar.getByRole('status');
    await expect(status).toBeVisible();
    await expect(status.locator('circle')).toHaveCount(1);
    const timelines = await status.locator('svg').evaluate(element => element.getAnimations({ subtree: true }).map(animation => ({ delay: animation.effect!.getTiming().delay, duration: animation.effect!.getTiming().duration })));
    expect(timelines).toHaveLength(2);
    expect(timelines.some(timing => timing.delay > 0)).toBe(true);
    await status.locator('svg').evaluate(element => element.getAnimations({ subtree: true }).forEach(animation => { animation.pause(); animation.currentTime = 240; }));
    await calendar.screenshot({ path: testInfo.outputPath(`${type}-circle-drawing.png`) });
    await status.locator('svg').evaluate(element => element.getAnimations({ subtree: true }).forEach(animation => animation.finish()));
    await calendar.screenshot({ path: testInfo.outputPath(`${type}-complete.png`) });
    const box = (await status.boundingBox())!; const mark = (await status.locator('svg').boundingBox())!;
    expect(Math.abs(box.x + box.width / 2 - mark.x - mark.width / 2)).toBeLessThan(1);
    await expect(calendar.getByRole('button', { pressed: true })).toHaveAccessibleName(/모두 완료/);
    await expect(calendar.getByRole('checkbox')).toHaveCount(0);
    await expect(page.getByRole('dialog')).toHaveCount(0);
    expect(unexpected).toEqual([]);
  });
}

test('refresh, date navigation and reload do not replay completion; observed undo permits a new true completion', async ({ page }) => {
  const { item, calendar, refresh } = await openCalendar(page);
  item.occurrences[1].isCompleted = true; await refresh();
  const status = calendar.getByRole('status');
  await expect(status).toBeVisible();
  await status.locator('svg').evaluate(element => element.getAnimations({ subtree: true }).forEach(animation => animation.finish()));
  await refresh();
  expect(await status.locator('svg').evaluate(element => element.getAnimations({ subtree: true }).filter(animation => animation.playState === 'running').length)).toBe(0);
  await calendar.getByRole('button', { name: /^2026.09.09,/ }).click();
  await expect(calendar.getByRole('status')).toHaveCount(0);
  await calendar.getByRole('button', { name: /^2026.09.10,/ }).click();
  await expect(status).toBeVisible();
  expect(await status.locator('svg').evaluate(element => element.getAnimations({ subtree: true }).length)).toBe(0);
  await page.reload(); await expect(status).toBeVisible();
  expect(await status.locator('svg').evaluate(element => element.getAnimations({ subtree: true }).length)).toBe(0);
  item.occurrences[1].isCompleted = false; await refresh(); await expect(status).toHaveCount(0);
  item.occurrences[1].isCompleted = true; await refresh(); await expect(status).toBeVisible();
  expect(await status.locator('svg').evaluate(element => element.getAnimations({ subtree: true }).length)).toBe(2);
});

test('reduced motion immediately settles record and daily checks without animations or overflow at 320px', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' }); await page.setViewportSize({ width: 320, height: 900 });
  const { item, calendar, refresh } = await openCalendar(page);
  item.occurrences[1].isCompleted = true; await refresh();
  await expect(calendar.getByRole('status')).toBeVisible();
  expect(await calendar.evaluate(element => element.getAnimations({ subtree: true }).length)).toBe(0);
  await expect(calendar.getByRole('status').locator('circle')).toHaveCount(1);
  expect(await calendar.getByRole('status').locator('path').evaluate(element => getComputedStyle(element).strokeDashoffset)).toBe('0px');
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
