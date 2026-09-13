import { execFileSync } from 'node:child_process';
import { writeFileSync } from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { expect, test } from 'playwright/test';

test('encrypted HTML opens offline only with birthdate and preserves report disclosures', async ({ page }, testInfo) => {
  test.setTimeout(30_000);
  const root = path.resolve('..');
  const python = path.join(root, process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python');
  const file = testInfo.outputPath('RxVita-synthetic-report.html');
  const script = `
from datetime import date
import sys
from ai_worker.tests.reports.test_intake_email_parity import sample_email_report
from app.core.email.intake_report_renderer import render_intake_report_email
from app.core.email.payload import EmailJobPayload, EmailTemplate
from app.core.email.renderer import EmailTemplateRenderer
markup, plain = render_intake_report_email(sample_email_report(), standalone=True)
message = EmailTemplateRenderer().render(EmailJobPayload(template=EmailTemplate.INTAKE_REPORT, recipient_email="synthetic@example.org", recipient_name="가상 사용자", report_id="synthetic", report_markdown=plain, report_html=markup, report_birth_date=date(1990,1,2)))
sys.stdout.buffer.write(message.attachments[0].data)
`;
  writeFileSync(file, execFileSync(python, ['-c', script], { cwd: root, maxBuffer: 3_000_000 }));
  const requests: string[] = [];
  page.on('request', request => { if (/^https?:/.test(request.url())) requests.push(request.url()); });
  await page.context().setOffline(true);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(pathToFileURL(file).href);
  await expect(page.getByRole('heading', { name: 'AI 보고서 확인하기' })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath('locked-mobile.png') });
  await page.getByLabel('생년월일 6자리 (YYMMDD)').fill('900103');
  await page.getByRole('button', { name: '보고서 열기', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('생년월일 6자리를 확인');
  await expect(page.locator('#viewer')).toBeHidden();
  await page.getByLabel('생년월일 6자리 (YYMMDD)').fill('900102');
  await page.getByRole('button', { name: '보고서 열기', exact: true }).click();
  const report = page.frameLocator('#report');
  await expect(report.locator('body')).toHaveCSS('color', 'rgb(23, 32, 51)');
  await expect(report.getByRole('heading', { name: '영양제 성분 합계', exact: true })).toBeVisible();
  const medicine = report.locator('.medicine');
  await expect(medicine.getByText('효능', { exact: true })).toBeHidden();
  await medicine.locator('summary').click();
  await expect(medicine.getByText('효능', { exact: true })).toBeVisible();
  await report.locator('.registered-products > summary').click();
  await expect(report.locator('.registered-products')).toContainText('등록한 영양제');
  for (const width of [390, 1280]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await report.locator('body').evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`unlocked-${width}.png`) });
  }
  expect(requests).toEqual([]);
  await page.getByRole('button', { name: '다시 잠그기' }).click();
  await expect(page.locator('#viewer')).toBeHidden();
  await expect(page.locator('#report')).not.toHaveAttribute('srcdoc');
});
