import { expect, test, type Page } from "@playwright/test";
import { connections, conversations, id, mockApi } from "./support/meta-mock";

const prefix = `/api/workspaces/${id}`;

test("own-account setup sends the WhatsApp business account with live credentials", async ({
  page,
}) => {
  await mockApi(page);
  const requests: Record<string, unknown>[] = [];
  await page.route("**/channels/connect/", (route) => {
    requests.push(route.request().postDataJSON());
    return route.fulfill({
      status: 202,
      json: { id: "own-number", status: "verifying" },
    });
  });
  await page.goto(`/w/${id}/integrations/?tab=channels`);
  await page
    .getByText("Advanced: manual credentials and test channels", {
      exact: true,
    })
    .click();
  const form = page
    .locator("form")
    .filter({ has: page.locator('input[name="business_account_id"]') });
  await form.locator('input[name="external_account_id"]').fill("222");
  await form
    .getByLabel("WhatsApp business account ID", { exact: true })
    .fill("333");
  await form.locator('input[name="display_name"]').fill("My test number");
  await form.locator('input[name="access_token"]').fill("test-only-token");
  await form.getByRole("button", { name: "Connect", exact: true }).click();
  await expect(
    page.getByText(
      "Connection requested. Verification runs in the background.",
      { exact: true },
    ),
  ).toBeVisible();
  expect(requests).toEqual([
    {
      provider: "whatsapp",
      external_account_id: "222",
      business_account_id: "333",
      display_name: "My test number",
      access_token: "test-only-token",
      is_test: false,
    },
  ]);
});

const approved = {
  id: "700",
  name: "order_update",
  language: "en_US",
  category: "UTILITY",
  signature: "a".repeat(64),
  text: "Hello {{1}}, your order {{2}} is ready.",
  buttons: ["View order"],
  supported: true,
  reason: "",
  fields: [
    {
      key: "body_1",
      label: "Message detail 1",
      type: "text",
      max_length: 1024,
    },
    {
      key: "body_2",
      label: "Message detail 2",
      type: "text",
      max_length: 1024,
    },
  ],
};

async function inbox(page: Page, templates = [approved]) {
  await mockApi(page);
  await page.route("**/conversations/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path !== `${prefix}/conversations/`) return route.fallback();
    return route.fulfill({
      json: {
        results: conversations.map((item) =>
          item.id === "v-1"
            ? {
                ...item,
                last_inbound_at: new Date(Date.now() - 3 * 864e5).toISOString(),
              }
            : item,
        ),
      },
    });
  });
  const sends: { data: Record<string, unknown>; key: string }[] = [];
  await page.route("**/whatsapp-templates/", (route) => {
    if (route.request().method() === "GET")
      return route.fulfill({ json: { results: templates } });
    sends.push({
      data: route.request().postDataJSON(),
      key: route.request().headers()["idempotency-key"],
    });
    return route.fulfill({
      status: 202,
      json: { id: "delivery-1", status: "pending" },
    });
  });
  await page.goto(`/w/${id}/inbox/?conversation=v-1`);
  await expect(page.getByLabel("Reply")).toBeDisabled();
  await page
    .getByRole("button", { name: "Send approved message", exact: true })
    .click();
  return {
    dialog: page.getByRole("dialog", {
      name: "Send approved WhatsApp message",
    }),
    sends,
  };
}

test("approved WhatsApp messages validate details and consent outside the reply window", async ({
  page,
}) => {
  const { dialog, sends } = await inbox(page);
  await expect(dialog).toContainText("Omar Haddad");
  await dialog
    .getByRole("button", { name: "Send approved message", exact: true })
    .click();
  await expect(
    dialog.getByLabel("Approved message", { exact: true }),
  ).toHaveAttribute("aria-invalid", "true");
  await dialog
    .getByLabel("Approved message", { exact: true })
    .selectOption("700");
  await dialog.getByLabel("Message detail 1", { exact: true }).fill("Alex");
  await dialog
    .getByRole("button", { name: "Send approved message", exact: true })
    .click();
  await expect(
    dialog.getByLabel("Message detail 2", { exact: true }),
  ).toHaveAttribute("aria-invalid", "true");
  expect(sends).toHaveLength(0);
  await dialog.getByLabel("Message detail 2", { exact: true }).fill("A100");
  await expect(dialog.getByLabel("Message preview")).toContainText(
    "Hello Alex, your order A100 is ready.",
  );
  await dialog
    .getByRole("button", { name: "Send approved message", exact: true })
    .click();
  const consent = dialog.getByRole("checkbox");
  await expect(consent).toHaveAttribute("aria-invalid", "true");
  await consent.check();
  await dialog
    .getByRole("button", { name: "Send approved message", exact: true })
    .click();
  await expect(dialog).toHaveCount(0);
  expect(sends).toHaveLength(1);
  expect(sends[0].data).toMatchObject({
    name: "order_update",
    language: "en_US",
    consent_confirmed: true,
    values: { body_1: "Alex", body_2: "A100" },
  });
  expect(sends[0].key).toBeTruthy();
});

test("unsupported approved formats explain why sending is unavailable", async ({
  page,
}) => {
  const { dialog, sends } = await inbox(page, [
    {
      ...approved,
      supported: false,
      reason:
        "This message uses a special format that cannot be sent from the inbox yet.",
    },
  ]);
  await dialog
    .getByLabel("Approved message", { exact: true })
    .selectOption("700");
  await expect(dialog).toContainText("special format");
  await expect(
    dialog.getByRole("button", { name: "Send approved message", exact: true }),
  ).toBeDisabled();
  expect(sends).toHaveLength(0);
});

test("empty approved-message catalog gives a useful next step", async ({
  page,
}) => {
  const { dialog } = await inbox(page, []);
  await expect(dialog).toContainText("WhatsApp Manager");
  await expect(
    dialog.getByRole("button", { name: "Send approved message", exact: true }),
  ).toHaveCount(0);
});

test("missing WhatsApp setup shows administrator instructions without requesting credentials", async ({
  page,
}) => {
  await mockApi(page);
  await page.route("**/whatsapp/connect/", (route) =>
    route.fulfill({
      json: {
        ready: false,
        steps: [
          "Add the Meta app credentials",
          "Set a public HTTPS app address",
        ],
        webhook_url: "http://localhost:3000/webhooks/whatsapp/",
      },
    }),
  );
  await page.goto(`/w/${id}/integrations/?tab=channels`);
  await page
    .getByRole("button", { name: "Connect WhatsApp", exact: true })
    .click();
  const dialog = page.getByRole("dialog", {
    name: "Connect WhatsApp Business",
  });
  await expect(dialog).toContainText("administrator");
  await expect(
    dialog.getByRole("button", { name: "Continue with Meta" }),
  ).toHaveCount(0);
  await expect(dialog.getByLabel("Access token")).toHaveCount(0);
  await dialog
    .getByText("Administrator setup details", { exact: true })
    .click();
  await expect(
    dialog.getByText("WhatsApp notification address", { exact: true }),
  ).toBeVisible();
});

type TestMetaWindow = Window & {
  testCode?: (response: { authResponse?: { code: string } }) => void;
  FB?: {
    init: () => void;
    login: (callback: TestMetaWindow["testCode"]) => void;
  };
};

for (const order of ["event-first", "code-first"] as const) {
  test(`guided signup joins Meta code and verified-origin session exactly once (${order})`, async ({
    page,
  }) => {
    await mockApi(page);
    await page.addInitScript(() => {
      const win = window as TestMetaWindow;
      win.FB = {
        init() {},
        login(callback) {
          win.testCode = callback;
        },
      };
    });
    await page.route("**/whatsapp/connect/", (route) =>
      route.fulfill({
        json:
          route.request().method() === "GET"
            ? {
                ready: true,
                steps: [],
                webhook_url:
                  "https://instantlify.example.com/webhooks/whatsapp/",
              }
            : {
                state: "state-1",
                app_id: "123",
                config_id: "999",
                version: "v23.0",
              },
      }),
    );
    const completions: Record<string, unknown>[] = [];
    const registrations: Record<string, unknown>[] = [];
    await page.route("**/whatsapp/complete/", (route) => {
      completions.push(route.request().postDataJSON());
      return route.fulfill({
        status: 202,
        json: { id: "new-number", status: "setup_required" },
      });
    });
    await page.route("**/whatsapp/new-number/activate/", (route) => {
      registrations.push(route.request().postDataJSON());
      return route.fulfill({ json: { status: "active" } });
    });
    await page.goto(`/w/${id}/integrations/?tab=channels`);
    await page
      .getByRole("button", { name: "Connect WhatsApp", exact: true })
      .click();
    const dialog = page.getByRole("dialog", {
      name: "Connect WhatsApp Business",
    });
    await dialog.getByRole("button", { name: "Continue with Meta" }).click();
    await page.evaluate(() =>
      window.dispatchEvent(
        new MessageEvent("message", {
          origin: "https://facebook.com.evil.example",
          data: JSON.stringify({
            type: "WA_EMBEDDED_SIGNUP",
            event: "FINISH",
            data: { waba_id: "999", phone_number_id: "888" },
          }),
        }),
      ),
    );
    expect(completions).toHaveLength(0);
    await page.evaluate((eventFirst) => {
      const finish = () =>
        window.dispatchEvent(
          new MessageEvent("message", {
            origin: "https://www.facebook.com",
            data: JSON.stringify({
              type: "WA_EMBEDDED_SIGNUP",
              event: "FINISH",
              data: { waba_id: "333", phone_number_id: "222" },
            }),
          }),
        );
      const code = () =>
        (window as TestMetaWindow).testCode?.({
          authResponse: { code: "code-1" },
        });
      if (eventFirst) {
        finish();
        code();
        finish();
      } else {
        code();
        finish();
        finish();
      }
    }, order === "event-first");
    const pin = dialog.getByLabel("WhatsApp security PIN", { exact: true });
    await expect(pin).toBeVisible();
    expect(completions).toHaveLength(1);
    expect(completions[0]).toEqual({
      state: "state-1",
      code: "code-1",
      waba_id: "333",
      phone_number_id: "222",
    });
    await dialog.getByRole("button", { name: "Finish connection" }).click();
    await expect(pin).toHaveAttribute("aria-invalid", "true");
    expect(registrations).toHaveLength(0);
    await pin.fill("123456");
    await dialog.getByRole("button", { name: "Finish connection" }).click();
    await expect(dialog).toHaveCount(0);
    expect(registrations).toEqual([{ pin: "123456" }]);
  });
}

test("interrupted number registration can be resumed from its channel card", async ({
  page,
}) => {
  await mockApi(page);
  await page.route("**/connections/", (route) =>
    route.fulfill({
      json: {
        results: connections.map((item) =>
          item.provider === "whatsapp"
            ? { ...item, status: "setup_required" }
            : item,
        ),
      },
    }),
  );
  const calls: Record<string, unknown>[] = [];
  await page.route("**/whatsapp/c-wa/activate/", (route) => {
    calls.push(route.request().postDataJSON());
    return route.fulfill({ json: { status: "active" } });
  });
  await page.goto(`/w/${id}/integrations/?tab=channels`);
  await page.getByRole("button", { name: "Finish WhatsApp setup" }).click();
  const dialog = page.getByRole("dialog", {
    name: "Connect WhatsApp Business",
  });
  await expect(
    dialog.getByLabel("WhatsApp security PIN", { exact: true }),
  ).toBeVisible();
  await dialog.getByRole("checkbox").check();
  await expect(
    dialog.getByLabel("WhatsApp security PIN", { exact: true }),
  ).toHaveCount(0);
  await dialog.getByRole("button", { name: "Finish connection" }).click();
  await expect(dialog).toHaveCount(0);
  expect(calls).toEqual([{ already_registered: true }]);
});
