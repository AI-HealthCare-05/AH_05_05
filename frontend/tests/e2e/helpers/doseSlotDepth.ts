import { expect, type Locator } from 'playwright/test';

/** Selected slots need visible depth as well as equal colors after interaction. */
export async function expectSelectedSlotDepth(buttons: Locator) {
  const surfaces = await buttons.evaluateAll((elements) => elements.map((element) => {
    const style = getComputedStyle(element);
    return {
      backgroundImage: style.backgroundImage,
      backgroundColor: style.backgroundColor,
      boxShadow: style.boxShadow,
    };
  }));
  expect(surfaces.length).toBeGreaterThanOrEqual(2);
  for (const surface of surfaces) {
    expect(surface.backgroundImage).toContain('linear-gradient(');
    const shadows = surface.boxShadow.split(/,(?![^(]*\))/);
    expect(shadows.some((shadow) => shadow.includes('inset'))).toBe(true);
    expect(shadows.some((shadow) => !shadow.includes('inset') && shadow.trim() !== 'none')).toBe(true);
  }
  expect(new Set(surfaces.map((surface) => JSON.stringify(surface))).size).toBe(1);
}
