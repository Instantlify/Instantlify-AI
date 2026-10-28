import { expect, test, type Page } from "@playwright/test";
import { id, mockApi, workspace } from "./support/meta-mock";

const otherId = "33333333-3333-4333-8333-333333333333";
const png = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
  "base64",
);
async function mockAppearance(page: Page, role = "owner") {
  await mockApi(page);
  const initial = {
    ...workspace.branding,
    primary_color: "#10244a",
    sidebar_bg_color: "#ffffff",
    sidebar_text_color: "#41516e",
  };
  const records = [
    { ...workspace, name: "Studio North", role, branding: { ...initial } },
    {
      ...workspace,
      id: otherId,
      name: "Second Studio",
      role: "owner",
      branding: { ...initial, primary_color: "#c2410c" },
    },
  ];
  const saves: Record<string, unknown>[] = [];
  await page.route("**/api/workspaces/", (route) =>
    route.fulfill({ json: { results: records, count: 2 } }),
  );
  await page.route(`**/api/workspaces/${otherId}/**`, (route) => {
    const path = new URL(route.request().url()).pathname;
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
    if (path.endsWith("/billing/"))
      return route.fulfill({
        json: {
          plan: "pro",
          status: "active",
          catalog: [{ slug: "pro", name: "Pro" }],
        },
      });
    return route.fulfill({ json: { results: [], count: 0 } });
  });
  await page.route(`**/api/workspaces/${id}/branding/`, (route) => {
    if (route.request().method() === "GET")
      return route.fulfill({
        json: { own: records[0].branding, effective: records[0].branding },
      });
    if (
      route.request().headers()["content-type"].includes("multipart/form-data")
    ) {
      saves.push({
        multipart: true,
        content: route.request().postDataBuffer()?.toString("latin1"),
      });
      records[0].branding.logo_url = `/api/public/workspace-logos/${id}/image-version/`;
    } else {
      const data = route.request().postDataJSON();
      saves.push(data);
      records[0].name = data.workspace_name || records[0].name;
      Object.assign(records[0].branding, data);
    }
    return route.fulfill({ json: records[0].branding });
  });
  await page.route("**/api/public/workspace-logos/**", (route) =>
    route.fulfill({ contentType: "image/png", body: png }),
  );
  return { saves, records };
}

async function openAppearance(page: Page) {
  await page.goto(`/w/${id}/settings/`);
  await page.getByRole("button", { name: "Workspaces", exact: true }).click();
  return page.getByRole("form", { name: "Workspace appearance" });
}

test("saved appearance applies immediately, survives refresh, and follows the selected workspace", async ({
  page,
}) => {
  const { saves } = await mockAppearance(page);
  const form = await openAppearance(page);
  await form
    .getByLabel("Workspace Name", { exact: true })
    .fill("Custom Studio");
  await form.getByLabel("Workspace Color", { exact: true }).fill("#7c3aed");
  await form
    .getByLabel("Sidebar background color", { exact: true })
    .fill("#10244a");
  await form.getByLabel("Sidebar text color", { exact: true }).fill("#ffffff");
  await form.getByLabel("Brand name", { exact: true }).fill("North Brand");
  await form.getByRole("button", { name: "Save Changes", exact: true }).click();
  await expect(
    page.getByText("Workspace settings saved successfully!", { exact: true }),
  ).toBeVisible();
  expect(saves[0]).toMatchObject({
    workspace_name: "Custom Studio",
    primary_color: "#7c3aed",
    sidebar_bg_color: "#10244a",
    sidebar_text_color: "#ffffff",
    brand_name: "North Brand",
  });
  const shell = page.locator(".app-shell-root");
  const sidebar = page.locator("#workspace-sidebar");
  await expect
    .poll(() =>
      shell.evaluate((el) =>
        getComputedStyle(el).getPropertyValue("--brand-action").trim(),
      ),
    )
    .toBe("#7c3aed");
  await expect(sidebar).toHaveCSS("background-color", "rgb(16, 36, 74)");
  await sidebar.hover();
  await expect(sidebar.locator(".brand-title")).toHaveText("North Brand");
  await expect(sidebar.locator(".brand-title")).toHaveCSS(
    "color",
    "rgb(255, 255, 255)",
  );
  await page.reload();
  await page.getByRole("button", { name: "Workspaces", exact: true }).click();
  await expect(
    form.getByLabel("Sidebar background color", { exact: true }),
  ).toHaveValue("#10244a");
  await expect(form.getByLabel("Workspace Color", { exact: true })).toHaveValue(
    "#7c3aed",
  );
  await sidebar.hover();
  await sidebar.getByRole("button", { name: /Switch workspace/ }).click();
  await sidebar.getByRole("button", { name: /Second Studio/ }).click();
  await expect(page).toHaveURL(new RegExp(`/w/${otherId}/overview/?$`));
  await expect(sidebar).toHaveCSS("background-color", "rgb(255, 255, 255)");
  await expect
    .poll(() =>
      shell.evaluate((el) =>
        getComputedStyle(el).getPropertyValue("--brand-action").trim(),
      ),
    )
    .toBe("#c2410c");
  await sidebar.hover();
  await sidebar.getByRole("button", { name: /Switch workspace/ }).click();
  await sidebar.getByRole("button", { name: /Custom Studio/ }).click();
  await expect(page).toHaveURL(new RegExp(`/w/${id}/overview/?$`));
  await expect(sidebar).toHaveCSS("background-color", "rgb(16, 36, 74)");
  await page.screenshot({ path: "test-results/workspace-custom-theme.png" });
});

test("invalid colors and unreadable sidebar text are highlighted before saving", async ({
  page,
}) => {
  const { saves } = await mockAppearance(page);
  const form = await openAppearance(page);
  const text = form.getByLabel("Sidebar text color", { exact: true });
  await text.fill("#ffffff");
  await form.getByRole("button", { name: "Save Changes", exact: true }).click();
  await expect(text).toHaveAttribute("aria-invalid", "true");
  await expect(text).toHaveAccessibleDescription(/easier to read/);
  expect(saves).toHaveLength(0);
  await text.fill("#41516e");
  const primary = form.getByLabel("Workspace Color", { exact: true });
  await primary.fill("#zzzzzz");
  await form.getByRole("button", { name: "Save Changes", exact: true }).click();
  await expect(primary).toHaveAttribute("aria-invalid", "true");
  expect(saves).toHaveLength(0);
});

test("logo uploads send an image file and keep the saved logo after refresh", async ({
  page,
}) => {
  const { saves } = await mockAppearance(page);
  const form = await openAppearance(page);
  await form
    .getByLabel("Workspace logo", { exact: true })
    .setInputFiles({ name: "logo.png", mimeType: "image/png", buffer: png });
  await form.getByRole("button", { name: "Save Changes", exact: true }).click();
  await expect(
    page.getByText("Workspace settings saved successfully!", { exact: true }),
  ).toBeVisible();
  expect(saves[0]).toMatchObject({ multipart: true });
  expect(saves[0].content).toContain('name="logo"; filename="logo.png"');
  const image = page.locator(
    '#workspace-sidebar img[src*="/api/public/workspace-logos/"]',
  );
  await expect(image).toBeVisible();
  await page.reload();
  await expect(image).toBeVisible();
  expect(
    await image.evaluate(
      (el: HTMLImageElement) => el.complete && el.naturalWidth === 1,
    ),
  ).toBe(true);
});

test("nonowners can see the appearance but cannot save changes", async ({
  page,
}) => {
  await mockAppearance(page, "admin");
  const form = await openAppearance(page);
  await expect(
    form.getByLabel("Workspace Color", { exact: true }),
  ).toBeDisabled();
  await expect(
    form.getByRole("button", { name: "Save Changes", exact: true }),
  ).toBeDisabled();
  await expect(form).toContainText("Only the workspace owner");
});

test("a bright workspace accent keeps action text readable", async ({
  page,
}) => {
  const { records } = await mockAppearance(page);
  records[0].branding.primary_color = "#c3ff5c";
  const form = await openAppearance(page);
  const button = form.getByRole("button", {
    name: "Save Changes",
    exact: true,
  });
  await expect(button).toHaveCSS("background-color", "rgb(195, 255, 92)");
  await expect(button).toHaveCSS("color", "rgb(12, 27, 58)");
});
