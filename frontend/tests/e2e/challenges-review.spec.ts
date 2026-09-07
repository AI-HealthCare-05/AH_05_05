import { expect, test } from 'playwright/test';

const screens = [
  ['home-preview', '/dev/home-challenges'],
  ['my', '/dev/challenges'],
  ['browse', '/dev/challenges/browse'],
  ['official', '/dev/challenges/official/official-water-7d'],
  ['active', '/dev/challenges/participations/part-official-active'],
  ['achieved', '/dev/challenges/participations/part-official-achieved'],
  ['missed', '/dev/challenges/participations/part-official-missed'],
  ['tailored', '/dev/challenges/tailored'],
  ['medication', '/dev/challenges/tailored/medication'],
  ['supplement', '/dev/challenges/tailored/supplement'],
  ['create', '/dev/challenges/create'],
  ['review', '/dev/challenges/participations/part-review-active'],
  ['visit', '/dev/challenges/participations/part-visit-active'],
  ['badges', '/dev/challenges/badges'],
  ['badge', '/dev/challenges/badges/badge-walk'],
] as const;

for (const width of [320, 375, 390, 430]) {
  test(`챌린지 전체 화면 ${width}px에서 가로 넘침과 런타임 오류 없이 표시한다`, async ({ page }, testInfo) => {
    test.setTimeout(90_000);
    await page.setViewportSize({ width, height: 844 });
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    for (const [name, path] of screens) {
      await page.goto(path);
      await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
      await expect.poll(() => page.locator('img').evaluateAll((images) =>
        images.every((image) => image.complete && image.naturalWidth > 0),
      )).toBe(true);
      await expect(page.locator('body')).not.toContainText('추천 챌린지');
      const overflow = await page.evaluate(() => ({
        document: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        main: [...document.querySelectorAll('main')].map((node) => node.scrollWidth - node.clientWidth),
      }));
      expect(overflow.document, `${name}: document overflow`).toBeLessThanOrEqual(1);
      for (const extra of overflow.main) expect(extra, `${name}: main overflow`).toBeLessThanOrEqual(1);
      if (width === 390) {
        await page.screenshot({ path: testInfo.outputPath(`${name}.png`), fullPage: true });
      }
    }
    expect(errors).toEqual([]);
  });
}

test('맞춤 및 자동 연동 화면은 별도 복약·영양제 기록 액션을 만들지 않는다', async ({ page }) => {
  for (const id of ['part-medication-active', 'part-supplement-active']) {
    await page.goto(`/dev/challenges/participations/${id}`);
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
    await expect(page.getByRole('button', { name: /했어요|복약 기록하기|영양제 기록하기/ })).toHaveCount(0);
    await expect(page.getByRole('link', { name: /복약 기록하기|영양제 기록하기/ })).toHaveCount(0);
  }
});

test('생성한 배지 이미지 네 종류를 로컬 자산으로 표시하고 필터를 두지 않는다', async ({ page }) => {
  await page.goto('/dev/challenges/badges');
  await expect(page.getByRole('heading', { name: '내 배지' })).toBeVisible();
  for (const name of ['walk', 'medication', 'supplement', 'review']) {
    const asset = page.locator(`img[src="/images/challenges/badge-${name}.png"]`).first();
    await expect(asset).toBeVisible();
    await expect.poll(() => asset.evaluate((image: HTMLImageElement) =>
      image.complete && image.naturalWidth > 0,
    )).toBe(true);
  }
  await expect(page.getByRole('button', { name: /^(전체|기본|공식)$/ })).toHaveCount(0);
  await expect(page.getByRole('tab', { name: /^(전체|기본|공식)$/ })).toHaveCount(0);
});
