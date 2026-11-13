import { test, expect, type Page } from "@playwright/test";

const id = "11111111-1111-4111-8111-111111111111";
async function fixture(page: Page) {
  const state = {
    published: false,
    expired: false,
    read: false,
    acknowledged: false,
    revoked: false,
    signedOut: false,
    renewals: 0,
  };
  const workspace = {
    id,
    name: "Studio",
    role: "owner",
    checkout_pending: false,
    branding: { brand_name: "Instantlify" },
  };
  await page.route("**/api/**", (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === "/api/auth/me/")
      return route.fulfill({
        status: state.signedOut ? 401 : 200,
        json: {
          id: 1,
          name: "Alex",
          email: "alex@example.com",
          email_verified: true,
        },
      });
    if (path === "/api/auth/session/") {
      if (request.method() === "POST") state.renewals++;
      return route.fulfill({
        json: {
          authenticated: !state.signedOut,
          remaining: 3600,
          idle_timeout: 3600,
        },
      });
    }
    if (path === "/api/auth/csrf/")
      return route.fulfill({ json: { csrfToken: "test" } });
    if (path === "/api/workspaces/")
      return route.fulfill({ json: { results: [workspace] } });
    if (path === `/api/workspaces/${id}/`)
      return route.fulfill({ json: workspace });
    if (path === "/api/notifications/") {
      if (request.method() === "PATCH") {
        const body = request.postDataJSON();
        state.read = true;
        if (body.acknowledge) state.acknowledged = true;
        return route.fulfill({ status: 204 });
      }
      return route.fulfill({
        json: {
          count: state.published ? 1 : 0,
          unread_count: state.published && !state.read ? 1 : 0,
          next: null,
          previous: null,
          results: state.published
            ? [
                {
                  id: "notice-1",
                  title: "Scheduled maintenance",
                  body: "A short service pause.",
                  link_url: "",
                  delivered_at: "2026-11-12T09:00:00Z",
                  read_at: state.read ? "2026-11-12T09:01:00Z" : null,
                  acknowledged_at: state.acknowledged
                    ? "2026-11-12T09:02:00Z"
                    : null,
                  requires_acknowledgement: true,
                  expired: state.expired,
                },
              ]
            : [],
        },
      });
    }
    if (path === "/api/growth/announcements/")
      return route.fulfill({
        json:
          state.published && !state.expired && !state.acknowledged
            ? [
                {
                  id: 1,
                  revision: 1,
                  type: "strip",
                  name: "Maintenance",
                  title: "Scheduled maintenance",
                  body: "A short service pause.",
                  tone: "blue",
                  link_url: "",
                  requires_acknowledgement: true,
                },
              ]
            : [],
      });
    if (path === "/api/auth/sessions/")
      return route.fulfill({
        json: {
          results: [
            {
              id: "current",
              device: "Chrome on Windows",
              current: true,
              ip_address: "127.0.0.1",
              last_activity: "2026-11-12T09:00:00Z",
              expires_at: "2026-11-12T10:00:00Z",
            },
            ...(!state.revoked
              ? [
                  {
                    id: "remote",
                    device: "Safari on iPhone",
                    current: false,
                    ip_address: null,
                    last_activity: "2026-11-12T09:00:00Z",
                    expires_at: "2026-11-12T10:00:00Z",
                  },
                ]
              : []),
          ],
        },
      });
    if (path === "/api/auth/sessions/remote/") {
      state.revoked = true;
      return route.fulfill({ status: 204 });
    }
    if (path === "/api/auth/sessions/revoke-all/") {
      state.signedOut = true;
      return route.fulfill({ status: 204 });
    }
    if (path.endsWith("/telemetry/"))
      return route.fulfill({
        json: {
          totals: { inbound: 0, contacts: 0, conversations: 0, ai_rate: null },
          days: [],
          channels: [],
        },
      });
    if (path.includes("/analytics/funnel/"))
      return route.fulfill({ json: { steps: [], unique_leads: 0 } });
    if (path.endsWith("/assignment-notifications/"))
      return route.fulfill({ json: { results: [], unread_count: 0 } });
    return route.fulfill({ json: { results: [], count: 0 } });
  });
  return state;
}

test("new notices appear without navigation and retain read/acknowledgement history", async ({
  page,
}) => {
  await page.clock.install();
  const state = await fixture(page);
  await page.goto(`/w/${id}/overview/`);
  await expect(
    page.getByRole("button", { name: "Notifications, 0 unread" }),
  ).toBeVisible();
  state.published = true;
  await page.clock.fastForward(16000);
  await expect(page.locator(".announcement-strip")).toContainText(
    "Scheduled maintenance",
  );
  expect(state.renewals).toBe(0);
  await page.getByRole("button", { name: "Notifications, 1 unread" }).click();
  const inbox = page.getByRole("region", {
    name: "Notifications",
    exact: true,
  });
  await inbox.getByRole("button", { name: "Mark announcements read" }).click();
  await expect(
    page.getByRole("button", { name: "Notifications, 0 unread" }),
  ).toBeVisible();
  expect(state.acknowledged).toBe(false);
  await inbox.getByRole("button", { name: "Acknowledge", exact: true }).click();
  await expect(inbox).toContainText("Acknowledged");
  await expect(page.locator(".announcement-strip")).toHaveCount(0);
  state.expired = true;
  await page.clock.fastForward(16000);
  await expect(inbox).toContainText("Expired");
});

test("devices can be revoked individually or everywhere on mobile", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const state = await fixture(page);
  await page.goto(`/w/${id}/settings/`);
  const devices = page.getByRole("region", { name: "Devices and sessions" });
  await expect(devices).toContainText("Safari on iPhone");
  await devices
    .getByRole("button", { name: "Sign out Safari on iPhone" })
    .click();
  await page
    .getByRole("alertdialog")
    .getByRole("button", { name: "Sign out", exact: true })
    .click();
  await expect(devices).not.toContainText("Safari on iPhone");
  expect(state.revoked).toBe(true);
  await expect
    .poll(() =>
      page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
    )
    .toBeTruthy();
  await devices.getByRole("button", { name: "Sign out everywhere" }).click();
  await page
    .getByRole("alertdialog")
    .getByRole("button", { name: "Sign out", exact: true })
    .click();
  await expect(page).toHaveURL(/\/auth\/$/);
  expect(state.signedOut).toBe(true);
});

test("unavailable integrations are labelled Coming soon without a connect action", async ({
  page,
}) => {
  await fixture(page);
  await page.goto(`/w/${id}/integrations/?tab=apps`);
  for (const name of [
    "Notavo",
    "Poppy AI",
    "Salesforce",
    "HubSpot",
    "Zapier",
  ]) {
    const card = page
      .locator(".boosend-int-card")
      .filter({ has: page.locator(".boosend-int-name", { hasText: name }) });
    await expect(card).toContainText("Coming soon");
    await expect(
      card.getByRole("button", { name: /connect|configure/i }),
    ).toHaveCount(0);
  }
});

test("a revoked open session is detected without extending inactivity", async ({
  page,
}) => {
  await page.clock.install();
  const state = await fixture(page);
  await page.goto(`/w/${id}/overview/`);
  await expect(
    page.getByRole("button", { name: "Notifications, 0 unread" }),
  ).toBeVisible();
  state.signedOut = true;
  await page.clock.fastForward(31000);
  await expect(page).toHaveURL(/\/auth\/\?session=expired$/);
  expect(state.renewals).toBe(0);
});
