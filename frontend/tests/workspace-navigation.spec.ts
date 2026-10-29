import { expect, test, type Page } from "@playwright/test";
import { id, mockApi, workspace } from "./support/meta-mock";

const otherId = "33333333-3333-4333-8333-333333333333";
const otherWorkspace = { ...workspace, id: otherId, name: "Olive Studio" };

async function mockWorkspaces(page: Page) {
  await mockApi(page);
  await page.route("**/api/workspaces/", (route) =>
    route.fulfill({ json: { results: [workspace, otherWorkspace], count: 2 } }),
  );
  await page.route(`**/api/workspaces/${otherId}/**`, (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/billing/"))
      return route.fulfill({
        json: {
          plan: "pro",
          status: "active",
          catalog: [{ slug: "pro", name: "Pro" }],
        },
      });
    if (path.endsWith("/telemetry/"))
      return route.fulfill({
        json: {
          days: [],
          totals: { inbound: 0, contacts: 0, conversations: 0, ai_rate: null },
          channels: [],
        },
      });
    if (path.includes("/analytics/funnel/"))
      return route.fulfill({
        json: { unique_leads: 0, steps: [], automations: [], channels: [] },
      });
    if (path.includes("/announcements/") || path.endsWith("/automation-runs/"))
      return route.fulfill({ json: [] });
    return route.fulfill({ json: { results: [], count: 0 } });
  });
}

test.beforeEach(async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
});

test("desktop rail expands on hover and collapses without shifting the page", async ({
  page,
}) => {
  await mockApi(page);
  await page.goto(`/w/${id}/overview`);
  await page.mouse.move(900, 100);
  const sidebar = page.locator("#workspace-sidebar");
  const home = sidebar.getByRole("link", { name: "Home", exact: true });
  const label = home.locator(".nav-label-text");
  await expect(label).toBeHidden();
  await expect(home.locator("svg")).toBeVisible();
  await expect.poll(async () => (await sidebar.boundingBox())?.width).toBe(76);
  const canvas = await page.locator(".main-content-canvas").boundingBox();
  const icon = await home.locator("svg").boundingBox();
  await sidebar.hover();
  await expect(label).toBeVisible();
  await expect.poll(async () => (await sidebar.boundingBox())?.width).toBe(250);
  expect((await page.locator(".main-content-canvas").boundingBox())?.x).toBe(
    canvas?.x,
  );
  expect((await home.locator("svg").boundingBox())?.y).toBe(icon?.y);
  await page.screenshot({ path: "test-results/sidebar-expanded.png" });
  await page.mouse.move(900, 100);
  await expect(label).toBeHidden();
  await expect.poll(async () => (await sidebar.boundingBox())?.width).toBe(76);
  await page.screenshot({ path: "test-results/sidebar-collapsed.png" });
});

test("keyboard navigation expands the rail and workspace menus dismiss with Escape", async ({
  page,
}) => {
  await mockApi(page);
  await page.goto(`/w/${id}/overview`);
  await page.mouse.move(900, 100);
  const sidebar = page.locator("#workspace-sidebar");
  // Start at the brand link rather than the browser's dev-tools focus target.
  await sidebar
    .getByRole("link", { name: "Nemio Home", exact: true })
    .press("Tab");
  await expect(
    sidebar
      .getByRole("link", { name: "Home", exact: true })
      .locator(".nav-label-text"),
  ).toBeVisible();
  const switcher = sidebar.getByRole("button", { name: /Switch workspace/ });
  await expect(switcher).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(switcher).toHaveAttribute("aria-expanded", "true");
  await page.keyboard.press("Escape");
  await expect(switcher).toHaveAttribute("aria-expanded", "false");
});

test("switching workspaces from Automation opens the new workspace Home", async ({
  page,
}) => {
  await mockWorkspaces(page);
  await page.goto(`/w/${id}/automations`);
  await page.getByRole("button", { name: /Switch workspace/ }).click();
  await page
    .locator(".workspace-dropdown-popover")
    .getByRole("button", { name: /Olive Studio/ })
    .click();
  await expect(page).toHaveURL(new RegExp(`/w/${otherId}/overview/?$`));
  await expect(page.locator(".workspace-crumb")).toHaveText("Olive Studio");
  await expect(
    page
      .getByRole("navigation", { name: "Workspace navigation" })
      .getByRole("link", { name: "Home", exact: true }),
  ).toHaveAttribute("aria-current", "page");
});

test("Settings workspace cards open a different workspace at Home", async ({
  page,
}) => {
  await mockWorkspaces(page);
  await page.goto(`/w/${id}/settings`);
  await page.getByRole("button", { name: "Workspaces", exact: true }).click();
  await page
    .locator(".my-workspaces-stack")
    .getByRole("link", { name: /Olive Studio/ })
    .click();
  await expect(page).toHaveURL(new RegExp(`/w/${otherId}/overview/?$`));
  await expect(page.locator(".workspace-crumb")).toHaveText("Olive Studio");
});

test("mobile drawer shows labels and closes after workspace switching", async ({
  page,
}) => {
  await mockWorkspaces(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/w/${id}/automations`);
  const sidebar = page.locator("#workspace-sidebar");
  await expect(sidebar).toBeHidden();
  await page.getByRole("button", { name: "Open navigation" }).click();
  await expect(
    sidebar
      .getByRole("link", { name: "Home", exact: true })
      .locator(".nav-label-text"),
  ).toBeVisible();
  await sidebar.getByRole("button", { name: /Switch workspace/ }).click();
  await sidebar.getByRole("button", { name: /Olive Studio/ }).click();
  await expect(page).toHaveURL(new RegExp(`/w/${otherId}/overview/?$`));
  await expect(sidebar).toBeHidden();
  await expect(page.locator(".drawer-backdrop")).toHaveCount(0);
});
