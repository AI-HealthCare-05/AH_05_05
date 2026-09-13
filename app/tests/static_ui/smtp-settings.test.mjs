import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

import * as smtpSettings from "../../static/js/smtp-settings.js";

const { buildSmtpSettingsPayload, populateSmtpSettingsForm } = smtpSettings;
const smtpSidebarPages = [
  "common-code-management.html",
  "challenge-management.html",
  "custom-challenge-template-management.html",
  "badge-management.html",
];

test("SMTP settings opens with overlay styles on every management page", async () => {
  for (const filename of smtpSidebarPages) {
    const pageUrl = new URL(`../../static/templates/${filename}`, import.meta.url);
    const html = await readFile(pageUrl, "utf8");

    assert.match(html, /href="\.\.\/css\/overlays\.css\?v=[^"]+"/, filename);
  }
});

function fakePanel(initial = {}) {
  const fields = new Map(Object.entries(initial).map(([name, value]) => [name, { value }]));
  return {
    field(name) { return fields.get(name); },
    querySelector(selector) {
      const name = selector.match(/name='([^']+)'/)?.[1];
      return fields.get(name);
    },
  };
}

test("populateSmtpSettingsForm fills public SMTP values and leaves password blank", () => {
  const panel = fakePanel({
    smtpHost: "",
    smtpPort: "",
    smtpUser: "",
    smtpPassword: "must-be-cleared",
    smtpFromEmail: "",
  });

  populateSmtpSettingsForm(panel, {
    smtpHost: "smtp.gmail.com",
    smtpPort: 587,
    smtpUser: "sender@example.com",
    smtpFromEmail: "from@example.com",
    smtpPasswordConfigured: true,
  });

  assert.equal(panel.field("smtpHost").value, "smtp.gmail.com");
  assert.equal(panel.field("smtpPort").value, "587");
  assert.equal(panel.field("smtpUser").value, "sender@example.com");
  assert.equal(panel.field("smtpFromEmail").value, "from@example.com");
  assert.equal(panel.field("smtpPassword").value, "");
});

test("buildSmtpSettingsPayload trims text fields and converts the port", () => {
  const panel = fakePanel({
    smtpHost: " smtp.gmail.com ",
    smtpPort: "587",
    smtpUser: " sender@example.com ",
    smtpPassword: " app-password ",
    smtpFromEmail: " from@example.com ",
  });

  assert.deepEqual(buildSmtpSettingsPayload(panel), {
    smtpHost: "smtp.gmail.com",
    smtpPort: 587,
    smtpUser: "sender@example.com",
    smtpPassword: "app-password",
    smtpFromEmail: "from@example.com",
  });
});

test("buildSmtpSettingsPayload omits an unchanged blank password", () => {
  const panel = fakePanel({
    smtpHost: "smtp.gmail.com",
    smtpPort: "587",
    smtpUser: "sender@example.com",
    smtpPassword: "   ",
    smtpFromEmail: "from@example.com",
  });

  assert.deepEqual(buildSmtpSettingsPayload(panel), {
    smtpHost: "smtp.gmail.com",
    smtpPort: 587,
    smtpUser: "sender@example.com",
    smtpFromEmail: "from@example.com",
  });
});

test("unchanged SMTP settings skip the confirmation", () => {
  const initial = {
    smtpHost: "smtp.gmail.com",
    smtpPort: 587,
    smtpUser: "sender@example.com",
    smtpFromEmail: "from@example.com",
    smtpPasswordConfigured: true,
  };
  let confirmationCount = 0;

  const accepted = smtpSettings.confirmSmtpSettingsChanges?.(initial, {
    smtpHost: "smtp.gmail.com",
    smtpPort: 587,
    smtpUser: "sender@example.com",
    smtpFromEmail: "from@example.com",
  }, () => {
    confirmationCount += 1;
    return false;
  });

  assert.equal(accepted, true);
  assert.equal(confirmationCount, 0);
});

test("changed SMTP settings show the warning and respect cancellation", () => {
  const messages = [];

  const accepted = smtpSettings.confirmSmtpSettingsChanges?.(
    {
      smtpHost: "smtp.gmail.com",
      smtpPort: 587,
      smtpUser: "sender@example.com",
      smtpFromEmail: "from@example.com",
    },
    {
      smtpHost: "smtp.changed.example.com",
      smtpPort: 587,
      smtpUser: "sender@example.com",
      smtpFromEmail: "from@example.com",
    },
    (message) => {
      messages.push(message);
      return false;
    },
  );

  assert.equal(accepted, false);
  assert.deepEqual(messages, [
    "[주의] 임시비밀번호 발송과 이메일 인증 발송 시 사용되는 정보이므로 변경 시 주의해 주세요. 저장하시겠습니까?",
  ]);
});

test("entering a new SMTP password requires confirmation", () => {
  let confirmationCount = 0;

  const accepted = smtpSettings.confirmSmtpSettingsChanges?.(
    {
      smtpHost: "smtp.gmail.com",
      smtpPort: 587,
      smtpUser: "sender@example.com",
      smtpFromEmail: "from@example.com",
      smtpPasswordConfigured: true,
    },
    {
      smtpHost: "smtp.gmail.com",
      smtpPort: 587,
      smtpUser: "sender@example.com",
      smtpFromEmail: "from@example.com",
      smtpPassword: "new-app-password",
    },
    () => {
      confirmationCount += 1;
      return true;
    },
  );

  assert.equal(accepted, true);
  assert.equal(confirmationCount, 1);
});

test("SMTP settings overlay follows the common admin edit popup design", async () => {
  const templateUrl = new URL("../../static/templates/overlay-smtp-settings.html", import.meta.url);
  const html = await readFile(templateUrl, "utf8");

  assert.match(html, /class="overlay-panel overlay-form"/);
  assert.match(html, /id="smtp-settings-title" class="text-lg font-semibold"/);
  assert.match(html, /class="text-sm text-gray-600"/);
  assert.match(html, /class="overlay-actions"/);
  assert.doesNotMatch(html, /style=/);
  assert.doesNotMatch(html, /aria-label="SMTP 설정 닫기"/);

  for (const fieldName of ["smtpHost", "smtpPort", "smtpUser", "smtpPassword", "smtpFromEmail"]) {
    assert.match(html, new RegExp(`data-error-for="${fieldName}"`));
  }
});

test("SMTP port accepts at most five numeric characters without a number stepper", async () => {
  const templateUrl = new URL("../../static/templates/overlay-smtp-settings.html", import.meta.url);
  const html = await readFile(templateUrl, "utf8");
  const portInput = html.match(/<input id="smtp-port"[^>]*>/)?.[0] ?? "";

  assert.match(portInput, /type="text"/);
  assert.match(portInput, /inputmode="numeric"/);
  assert.match(portInput, /maxlength="5"/);
  assert.match(portInput, /pattern="\[0-9\]\{1,5\}"/);
  assert.doesNotMatch(portInput, /type="number"/);
});
