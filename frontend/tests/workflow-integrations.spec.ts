import { test, expect } from "@playwright/test";
import { id, mockApi } from "./support/meta-mock";

test("Sheets configuration keeps destinations separate and preserves saved tokens on edit", async ({
  page,
}) => {
  await mockApi(page);
  let saved: Record<string, unknown> | undefined;
  let configured = false;
  await page.route(`**/api/workspaces/${id}/integrations/`, (route) => {
    if (route.request().method() === "POST") {
      saved = route.request().postDataJSON();
      configured = true;
      return route.fulfill({
        json: { id: "sheets", ...saved, configured: true },
      });
    }
    return route.fulfill({
      json: configured
        ? [
            {
              id: "sheets",
              provider: "google_sheets",
              configured: true,
              enabled: true,
              is_test: false,
              options: saved?.options,
            },
          ]
        : [],
    });
  });
  await page.goto(`/w/${id}/integrations`);
  const card = page
    .locator(".boosend-int-card")
    .filter({ hasText: "Google Sheets" });
  await card
    .getByRole("button", { name: "Create Integration", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Save Configuration", exact: true })
    .click();
  await expect(
    page.getByText("Enter Access token.", { exact: true }),
  ).toBeVisible();
  expect(saved).toBeUndefined();
  await page
    .getByLabel("Access token", { exact: true })
    .fill("provider-test-token");
  await page.getByLabel("Spreadsheet ID", { exact: true }).fill("sheet-123");
  await page.getByLabel("Sheet range", { exact: true }).fill("Leads!A:C");
  await page
    .getByRole("button", { name: "Save Configuration", exact: true })
    .click();
  await expect
    .poll(() => saved)
    .toMatchObject({
      provider: "google_sheets",
      credentials: { access_token: "provider-test-token" },
      options: { spreadsheet_id: "sheet-123", range: "Leads!A:C" },
    });
  await card.getByRole("button", { name: "Configure", exact: true }).click();
  await expect(page.getByLabel("Access token", { exact: true })).toHaveValue(
    "",
  );
  await expect(page.getByLabel("Spreadsheet ID", { exact: true })).toHaveValue(
    "sheet-123",
  );
  await page.getByLabel("Sheet range", { exact: true }).fill("Customers!A:C");
  await page
    .getByRole("button", { name: "Save Configuration", exact: true })
    .click();
  await expect
    .poll(() => saved)
    .toMatchObject({
      credentials: {},
      options: { spreadsheet_id: "sheet-123", range: "Customers!A:C" },
    });
});

test("failed Google authorization stays an error and never creates a fake connection", async ({
  page,
}) => {
  await mockApi(page);
  let oauth: unknown;
  let creates = 0;
  await page.route(
    `**/api/workspaces/${id}/integrations/google_sheets/oauth/`,
    (route) => {
      oauth = route.request().postDataJSON();
      return route.fulfill({
        status: 503,
        json: { detail: "Google authorization is unavailable." },
      });
    },
  );
  await page.route(`**/api/workspaces/${id}/integrations/`, (route) => {
    if (route.request().method() === "POST") creates++;
    return route.fulfill({ json: [] });
  });
  await page.goto(`/w/${id}/integrations`);
  await page
    .locator(".boosend-int-card")
    .filter({ hasText: "Google Sheets" })
    .getByRole("button", { name: "Create Integration", exact: true })
    .click();
  await page.getByLabel("Spreadsheet ID", { exact: true }).fill("sheet-123");
  await page.getByRole("button", { name: "Connect", exact: true }).click();
  await expect(
    page.getByText("Google authorization is unavailable.", { exact: true }),
  ).toBeVisible();
  expect(oauth).toEqual({
    options: { spreadsheet_id: "sheet-123", range: "Sheet1!A:C" },
  });
  expect(creates).toBe(0);
});
