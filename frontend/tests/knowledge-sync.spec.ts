import { test, expect } from "@playwright/test";
import { id, mockApi } from "./support/meta-mock";

test("connected knowledge sync is opt in and persists frequency and pause", async ({
  page,
}) => {
  await mockApi(page);
  await page.route(`**/api/workspaces/${id}/integrations/`, (route) =>
    route.fulfill({
      json: {
        results: [
          {
            id: "sheets",
            provider: "google_sheets",
            configured: true,
            enabled: true,
            status: "active",
            is_test: false,
            options: { spreadsheet_id: "sheet" },
          },
        ],
        count: 1,
      },
    }),
  );
  let saved: Record<string, unknown> | undefined;
  let schedule = {
    enabled: false,
    interval_minutes: 60,
    status: "idle",
    next_run_at: null as string | null,
    last_success_at: null,
    error_code: "",
  };
  await page.route(
    `**/api/workspaces/${id}/integrations/sheets/knowledge/schedule/`,
    (route) => {
      if (route.request().method() === "PUT") {
        saved = route.request().postDataJSON();
        schedule = {
          ...schedule,
          ...saved,
          next_run_at: saved?.enabled
            ? new Date(Date.now() + 60000).toISOString()
            : null,
        };
      }
      return route.fulfill({ json: schedule });
    },
  );
  await page.goto(`/w/${id}/integrations/`);
  const card = page
    .locator(".boosend-int-card")
    .filter({ hasText: "Google Sheets" });
  await card
    .getByRole("button", { name: "Automatic knowledge sync", exact: true })
    .click();
  const settings = card.getByRole("region", {
    name: "Google Sheets automatic knowledge sync",
    exact: true,
  });
  await expect(settings.getByRole("checkbox")).not.toBeChecked();
  expect(saved).toBeUndefined();
  await settings.getByRole("checkbox").check();
  await settings
    .getByRole("combobox", { name: "Refresh frequency", exact: true })
    .selectOption("360");
  await settings
    .getByRole("button", { name: "Save automatic sync", exact: true })
    .click();
  await expect
    .poll(() => saved)
    .toEqual({ enabled: true, interval_minutes: 360 });
  await expect(
    settings.getByRole("status").filter({ hasText: "Automatic sync enabled" }),
  ).toBeVisible();
  await settings.getByRole("checkbox").uncheck();
  await settings
    .getByRole("button", { name: "Save automatic sync", exact: true })
    .click();
  await expect
    .poll(() => saved)
    .toEqual({ enabled: false, interval_minutes: 360 });
  await expect(
    settings.getByRole("status").filter({ hasText: "Automatic sync paused" }),
  ).toBeVisible();
});
