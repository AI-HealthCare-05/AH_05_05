import { mkdirSync, readFileSync, existsSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { expect, test, type Locator, type Page } from 'playwright/test';

test.setTimeout(60_000);

async function surface(control: Locator) {
  return control.evaluate(element => {
    const css = getComputedStyle(element);
    return { width: element.getBoundingClientRect().width, height: element.getBoundingClientRect().height,
      border: css.borderWidth, radius: css.borderRadius, shadow: css.boxShadow,
      background: css.backgroundImage, color: css.backgroundColor };
  });
}

function outerDepth(shadow: string) {
  return Math.max(0, ...shadow.split(/,(?![^()]*\))/).filter(layer => !layer.includes('inset')).map(layer => {
    const lengths = layer.match(/-?[\d.]+px/g)?.map(parseFloat) ?? [];
    return Math.abs(lengths[1] ?? 0) + (lengths[2] ?? 0) + (lengths[3] ?? 0);
  }));
}

async function capture(page: Page, name: string) {
  const directory = process.env.UI562_SCREENSHOT_DIR;
  if (!directory) return;
  mkdirSync(directory, { recursive: true });
  await page.screenshot({ path: path.join(directory, `${name}.png`), fullPage: true, animations: 'disabled' });
}

for (const width of [390, 1280]) {
  test(`white action shadows stay below primary depth without changing geometry (${width}px)`, async ({ page }) => {
    await page.setViewportSize({ width, height: 844 });
    await page.clock.setFixedTime(new Date('2026-09-02T12:00:00+09:00'));
    await page.addInitScript(() => {
      sessionStorage.setItem('poke.access-token', 'issue-562');
      sessionStorage.setItem('poke.account-principal', 'issue-562@example.com');
    });
    const metrics: Record<string, Awaited<ReturnType<typeof surface>>> = {};
    await page.goto('/dev/gallery');
    const primary = page.getByRole('button', { name: '저장하기', exact: true });
    const secondary = page.getByRole('button', { name: '다시 촬영 · 재업로드', exact: true });
    await secondary.scrollIntoViewIfNeeded();
    metrics.primary = await surface(primary);
    metrics.secondary = await surface(secondary);
    metrics.card = await surface(page.getByRole('button', { name: /다음 일정/ }));
    await capture(page, `gallery-${width}`);
    await secondary.focus();
    await expect(secondary).toBeFocused();
    await expect(secondary).toHaveCSS('outline-style', 'solid');
    await secondary.hover();
    metrics.secondaryHover = await surface(secondary);

    await page.goto('/dev/medications');
    const period = page.getByRole('button', { name: '최근 6개월', exact: true });
    await expect(period).toBeVisible();
    metrics.period = await surface(period);
    metrics.report = await surface(page.getByRole('button', { name: 'AI 보고서 받기', exact: true }));
    await expect(page.getByRole('button', { name: '선택', exact: true })).toBeVisible();
    await capture(page, `medications-${width}`);
    await page.getByRole('button', { name: '선택', exact: true }).click();
    await page.getByRole('checkbox').first().check();
    await page.getByRole('button', { name: '삭제 1개', exact: true }).click();
    const deletion = page.getByRole('dialog');
    metrics.cancel = await surface(deletion.getByRole('button', { name: '취소', exact: true }));
    metrics.danger = await surface(deletion.getByRole('button', { name: '삭제하기', exact: true }));
    await capture(page, `medication-dialog-${width}`);

    await page.goto('/dev/supplements');
    await page.getByRole('region', { name: '먹고 있는 영양제' }).getByRole('button', { name: /종합비타민/ }).click();
    const detail = page.getByRole('dialog', { name: '종합비타민', exact: true });
    const edit = detail.getByRole('button', { name: '복용 정보 수정', exact: true });
    metrics.edit = await surface(edit);
    await capture(page, `supplement-detail-${width}`);
    await edit.click();
    await expect(page.getByRole('dialog', { name: '복용 정보 수정', exact: true })).toBeVisible();

    const directory = process.env.UI562_SCREENSHOT_DIR;
    if (directory) writeFileSync(path.join(directory, `metrics-${width}.json`), JSON.stringify(metrics, null, 2));
    const baseline = process.env.UI562_BASELINE_DIR;
    if (baseline && existsSync(path.join(baseline, `metrics-${width}.json`))) {
      const before = JSON.parse(readFileSync(path.join(baseline, `metrics-${width}.json`), 'utf8'));
      for (const [name, value] of Object.entries(metrics)) {
        expect(value.width, `${name} width`).toBe(before[name].width);
        expect(value.height, `${name} height`).toBe(before[name].height);
      }
      for (const name of ['primary', 'report', 'danger', 'card']) expect(metrics[name]).toEqual(before[name]);
    }
    expect(metrics.secondary.height).toBe(52);
    expect(metrics.secondary.width).toBe(metrics.primary.width);
    expect(metrics.cancel.height).toBe(metrics.danger.height);
    for (const name of ['secondary', 'secondaryHover', 'period', 'cancel', 'edit']) {
      expect.soft(metrics[name].height, name).toBeGreaterThanOrEqual(44);
      expect.soft(outerDepth(metrics[name].shadow), `${name} white shadow is quieter than primary`).toBeLessThan(outerDepth(metrics.primary.shadow));
      expect.soft(outerDepth(metrics[name].shadow), `${name} white shadow footprint`).toBeLessThanOrEqual(3);
    }
  });
}
