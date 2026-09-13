import type { Page } from 'playwright/test';

export async function waitForVisibleImages(page: Page) {
  const images = page.locator('img:visible');
  await images.evaluateAll(async (elements) => {
    await Promise.all(elements.map(async (element) => {
      const image = element as HTMLImageElement;
      await image.decode();
      if (image.naturalWidth <= 0 || image.naturalHeight <= 0) {
        throw new Error(`Visible image failed to decode: ${image.currentSrc || image.src}`);
      }
    }));
  });
}
