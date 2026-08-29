import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

import {
  buildSmtpSettingsPayload,
  populateSmtpSettingsForm,
} from "../../static/js/smtp-settings.js";

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
