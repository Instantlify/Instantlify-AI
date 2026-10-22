import { test, expect } from "@playwright/test";
import { id, mockApi } from "./support/meta-mock";

/** Meta client surfaces against a mocked API: account switcher, app dock, overview
 * telemetry, automations hub, unified inbox, CRM pipeline and app store. */

test.beforeEach(async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
});

const nav = (page: import("@playwright/test").Page) =>
  page.getByRole("navigation", { name: "Workspace navigation" });

test("account switcher lists Meta accounts with token health and scopes the inbox", async ({
  page,
}) => {
  await mockApi(page);
  await page.goto(`/w/${id}/overview`);
  const channels = page.getByRole("region", { name: "Channel status" });
  await expect(channels).toContainText("studio.north");
  await expect(channels).toContainText("1 Page");
  await expect(channels).toContainText("1 number");
  await expect(page.locator(".metric-kpi-card").first()).toContainText("120");
  await expect(page.locator(".channel-matrix")).toContainText("3 min");
  await expect(page.locator(".lifetime-badge")).toHaveText("Pro");
  await page.screenshot({
    path: "test-results/meta-overview.png",
    fullPage: true,
  });

  const trigger = page.locator(".social-account-card-trigger");
  await expect(trigger).toContainText("All accounts");
  // The Messenger token expires in 3 days, so one account needs attention.
  await expect(trigger.locator(".account-attention")).toHaveText("1");
  await trigger.click();
  const menu = page.locator(".social-account-menu-popover");
  await expect(menu).toContainText("12.4K followers");
  await expect(menu).toContainText("Expiring soon");
  await expect(menu).toContainText("WhatsApp number");
  await page.screenshot({ path: "test-results/meta-switcher.png" });
  await menu.getByRole("button", { name: /\+1 555 0100/ }).click();
  await expect(trigger).toContainText("+1 555 0100");

  const requested = page.waitForRequest((request) =>
    request.url().includes("connection=c-wa"),
  );
  await nav(page)
    .getByRole("link", { name: "Conversations", exact: true })
    .click();
  await requested;
  await expect(page.locator(".account-chip")).toBeVisible();
});

test("inbox shows channel filter, window countdown and distinct bubbles", async ({
  page,
}) => {
  await mockApi(page);
  await page.goto(`/w/${id}/inbox`);
  await expect(page.locator(".window-chip")).toContainText(/h \d+m left/);
  await expect(page.locator(".bubble.sender-ai")).toContainText("AI Agent");
  await expect(page.locator(".bubble.sender-automation")).toContainText(
    "Automation",
  );
  await expect(page.locator(".bubble.sender-human .bubble-author")).toHaveText(
    "AL",
  );
  await expect(page.locator(".system-event")).toContainText(
    "Automation triggered: Comment → lead magnet",
  );
  await page.getByRole("button", { name: "Insert emoji" }).click();
  await page.getByRole("button", { name: "Insert 👋" }).click();
  await expect(page.getByLabel("Reply")).toHaveValue("👋");
  await page.getByRole("button", { name: "Contact details" }).click();
  await expect(page.getByLabel("Lead stage")).toHaveValue("new");
  await page.screenshot({
    path: "test-results/meta-inbox.png",
    fullPage: true,
  });

  const filtered = page.waitForRequest((request) =>
    request.url().includes("provider=whatsapp"),
  );
  await page.getByRole("button", { name: "Filter by channel" }).click();
  await page.getByRole("option", { name: /WhatsApp/ }).click();
  await filtered;
});

test("inbox blocks replies once the 24-hour window has closed", async ({
  page,
}) => {
  await mockApi(page);
  await page.goto(`/w/${id}/inbox?conversation=v-2`);
  await expect(page.locator(".window-chip")).toHaveText("24h window closed");
  await expect(page.getByLabel("Reply")).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Send message" }),
  ).toBeDisabled();
});

test("automations list shows real runs, channels and status, and toggles through the API", async ({
  page,
}) => {
  const calls = await mockApi(page);
  await page.goto(`/w/${id}/automations`);
  await expect(page.getByText("Comment → lead magnet").first()).toBeVisible();
  // Runs and status come from the API, never placeholder rows or numbers.
  await expect(page.locator(".metric-runs").first()).toHaveText("41");
  await expect(page.locator(".metric-reach").first()).toHaveText("37");
  await expect(page.locator(".status-pill").first()).toHaveText("Active");
  await expect(page.getByText("DMs Reply")).toHaveCount(0);
  await expect(
    page
      .locator(".row-channel-icon")
      .first()
      .locator('[data-brand="instagram"]'),
  ).toBeVisible();
  await page.getByRole("button", { name: "Inactive" }).click();
  await expect(
    page.getByRole("link", { name: "WhatsApp greeting", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Comment → lead magnet", exact: true }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "All", exact: true }).click();
  await page.screenshot({
    path: "test-results/meta-automations.png",
    fullPage: true,
  });

  // The switch pauses a live automation through the API.
  await page
    .getByRole("switch", { name: "Comment → lead magnet active" })
    .click();
  await expect
    .poll(
      () => calls.find((call) => call.path.endsWith("/automations/a-1/"))?.body,
    )
    .toEqual({ enabled: false });
  // An unpublished draft cannot be switched on.
  await expect(
    page.getByRole("switch", { name: "WhatsApp greeting active" }),
  ).toBeDisabled();
});

test("CRM table, pipeline and bulk actions", async ({ page }) => {
  const calls = await mockApi(page);
  await page.goto(`/w/${id}/crm`);
  await expect(page.getByText("Maya Chen")).toBeVisible();
  await page.getByRole("checkbox", { name: "Select all contacts" }).check();
  await expect(page.locator(".boosend-crm-selected-count")).toContainText(
    "4 selected",
  );
  await page.getByRole("button", { name: "Bulk Actions" }).click();
  await page.getByLabel("Tag to apply").fill("vip");
  await page.getByRole("button", { name: "Apply tag" }).click();
  await expect
    .poll(() => calls.find((call) => call.path.endsWith("/leads/bulk/"))?.body)
    .toEqual({
      ids: ["l-0", "l-1", "l-2", "l-3"],
      action: "tag",
      value: "vip",
    });
  await page.screenshot({
    path: "test-results/meta-crm-table.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "Kanban" }).click();
  await page.getByLabel("Move Maya Chen to stage").selectOption("won");
  await expect
    .poll(() => calls.find((call) => call.path.endsWith("/leads/l-0/"))?.body)
    .toEqual({ stage: "won" });
  await page.screenshot({
    path: "test-results/meta-crm-pipeline.png",
    fullPage: true,
  });
});

test("CRM creates a contact from the form, not a sample person", async ({
  page,
}) => {
  const calls = await mockApi(page);
  await page.goto(`/w/${id}/crm`);
  await page.getByRole("button", { name: "Create contact" }).click();
  await page.getByLabel("Name").fill("Priya Shah");
  await page.getByLabel("Email (optional)").fill("priya@example.com");
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Create contact" })
    .click();
  await expect
    .poll(
      () =>
        calls.find(
          (call) =>
            call.path === `/api/workspaces/${id}/leads/` &&
            call.body !== undefined,
        )?.body,
    )
    .toEqual({ name: "Priya Shah", email: "priya@example.com", stage: "new" });
});

test("app store pins apps to the sidebar dock", async ({ page }) => {
  await mockApi(page);
  await page.goto(`/w/${id}/app-store`);
  await expect(
    nav(page).getByRole("link", { name: "Content calendar" }),
  ).toBeVisible();
  await page
    .locator(".boosend-appstore-card", { hasText: "Content Calendar" })
    .getByRole("button", { name: "Remove From Menu" })
    .click();
  await expect(
    nav(page).getByRole("link", { name: "Content calendar" }),
  ).toHaveCount(0);
  await expect(page.locator(".boosend-appstore-btn-soon")).not.toHaveCount(0);
  await page.screenshot({
    path: "test-results/meta-app-store.png",
    fullPage: true,
  });
});

test("mobile drawer opens, navigates and closes", async ({ page }) => {
  await mockApi(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/w/${id}/overview`);
  const sidebar = page.locator(".boosend-sidebar");
  await expect(sidebar).not.toBeInViewport();
  await page.getByRole("button", { name: "Open navigation" }).click();
  await expect(sidebar).toHaveClass(/drawer-open/);
  await expect(sidebar).toBeInViewport({ ratio: 0.9 });
  await page.screenshot({ path: "test-results/meta-mobile-drawer.png" });
  await nav(page).getByRole("link", { name: "CRM", exact: true }).click();
  await expect(page).toHaveURL(/\/crm\/$/);
  await expect(sidebar).not.toHaveClass(/drawer-open/);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
});
