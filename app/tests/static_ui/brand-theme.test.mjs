import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const staticRoot = new URL("../../static/", import.meta.url);
const readStatic = (path) => readFile(new URL(path, staticRoot), "utf8");

test("administrator styles expose the approved RxVita palette", async () => {
  const styles = await readStatic("css/styles.css");

  assert.match(styles, /--brand-primary:\s*#18bfb3;/);
  assert.match(styles, /--brand-primary-hover:\s*#0e9384;/);
  assert.match(styles, /--brand-primary-strong:\s*#0b7f75;/);
  assert.match(styles, /--brand-primary-strong-hover:\s*#096c64;/);
  assert.match(styles, /--brand-primary-soft:\s*#e8f9f7;/);
  assert.match(styles, /--brand-primary-faint:\s*rgba\(24, 191, 179, 0\.06\);/);
  assert.match(styles, /--brand-focus:\s*rgba\(24, 191, 179, 0\.18\);/);
  assert.match(styles, /--brand-hover-row:\s*rgba\(24, 191, 179, 0\.04\);/);
  assert.match(styles, /--brand-navy:\s*#06356f;/);
});

test("administrator styles no longer carry the legacy blue interaction palette", async () => {
  const source = (await Promise.all([
    readStatic("css/styles.css"),
    readStatic("css/management.css"),
  ])).join("\n");

  for (const legacy of ["#1c64f2", "#1554d1", "#1d4ed8", "#eff6ff", "28,100,242", "28, 100, 242"]) {
    assert.equal(source.includes(legacy), false, `legacy brand color remains: ${legacy}`);
  }
});

test("semantic management colors remain distinct from the brand palette", async () => {
  const management = await readStatic("css/management.css");

  assert.match(management, /\.status-active\s*\{[^}]*background:\s*#dcfce7;[^}]*color:\s*#166534;/s);
  assert.match(management, /\.status-processing\s*\{[^}]*background:\s*#fef3c7;[^}]*color:\s*#92400e;/s);
  assert.match(management, /\.status-failed\s*\{[^}]*background:\s*#fee2e2;[^}]*color:\s*#b91c1c;/s);
  assert.match(management, /\.ui-button-danger\s*\{[^}]*background:\s*#dc2626;/s);
});

test("every administrator entry page loads the same stylesheet cache version", async () => {
  const pages = [
    "templates/login.html",
    "templates/dashboard.html",
    "templates/user-management.html",
    "templates/screen-4-admin-management.html",
    "templates/screen-5-task-management.html",
    "templates/supplement-ranking.html",
  ];

  for (const page of pages) {
    const html = await readStatic(page);
    for (const stylesheet of ["styles", "management", "overlays"]) {
      assert.match(html, new RegExp(`href="\\.\\.\\/css\\/${stylesheet}\\.css\\?v=20260831-5"`), page);
    }
  }
});
