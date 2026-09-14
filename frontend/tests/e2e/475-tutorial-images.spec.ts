import { expect, test } from 'playwright/test';

test.setTimeout(60_000);

const steps = [
  { heading: '약봉투를 찍으면', image: '약봉투 촬영으로 복약 일정을 등록하는 모습' },
  { heading: '먹을 시간에', image: '설정한 복용 시간에 휴대폰 알림을 받는 모습' },
  { heading: '영양제 성분을', image: '두 영양제의 성분을 합산해 기준선과 비교하는 모습' },
  { heading: '내 약을 근거로', image: '병아리 챗봇의 답변과 연결된 출처 문서' },
] as const;

test.beforeEach(async ({ context }) => {
  await context.route('https://fonts.googleapis.com/**', (route) =>
    route.fulfill({ contentType: 'text/css', body: '' }),
  );
});

for (const viewport of [
  { width: 320, height: 568 },
  { width: 390, height: 844 },
  { width: 768, height: 1024 },
]) {
  test(`${viewport.width}px 튜토리얼 네 화면에 서로 다른 실제 이미지가 잘림 없이 표시된다`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize(viewport);
    await page.goto('/tutorial', { waitUntil: 'domcontentloaded' });
    const loadedSources = new Set<string>();

    for (const [index, step] of steps.entries()) {
      await expect(page.getByRole('heading', { name: new RegExp(step.heading) })).toBeVisible();
      const illustration = page.getByRole('img', { name: step.image, exact: true });
      await expect(illustration).toBeVisible();
      await expect
        .poll(() =>
          illustration.evaluate((element: HTMLImageElement) =>
            element.complete && element.naturalWidth > 0 && element.naturalHeight > 0,
          ),
        )
        .toBe(true);
      loadedSources.add(await illustration.evaluate((element: HTMLImageElement) => element.currentSrc));

      const bounds = await illustration.evaluate((element) => {
        const image = element.getBoundingClientRect();
        const frame = element.parentElement!.getBoundingClientRect();
        return {
          image: { left: image.left, top: image.top, right: image.right, bottom: image.bottom },
          frame: { left: frame.left, top: frame.top, right: frame.right, bottom: frame.bottom },
          fit: getComputedStyle(element).objectFit,
          pageWidth: document.documentElement.scrollWidth,
          viewportWidth: window.innerWidth,
        };
      });
      expect(bounds.fit).toBe('contain');
      expect(bounds.image.left).toBeGreaterThanOrEqual(bounds.frame.left);
      expect(bounds.image.right).toBeLessThanOrEqual(bounds.frame.right);
      expect(bounds.image.top).toBeGreaterThanOrEqual(bounds.frame.top);
      expect(bounds.image.bottom).toBeLessThanOrEqual(bounds.frame.bottom);
      expect(bounds.pageWidth).toBeLessThanOrEqual(bounds.viewportWidth);

      const next = page.getByRole('button', {
        name: index === steps.length - 1 ? '시작하기' : '다음',
        exact: true,
      });
      await next.scrollIntoViewIfNeeded();
      await expect(next).toBeInViewport();
      await page.screenshot({ path: testInfo.outputPath(`step-${index + 1}.png`), fullPage: true });
      await next.click();
    }

    expect(loadedSources.size).toBe(4);
    await expect(page).toHaveURL(/\/home$/);
  });
}
