import { test, expect } from "@playwright/test";
import { id, mockApi } from "./support/meta-mock";

test("recent deliveries shows five newest entries and navigates older pages", async ({
  page,
}) => {
  await mockApi(page);
  const rows = Array.from({ length: 12 }, (_, index) => ({
    id: `delivery-${index}`,
    recipient_id: `recipient-${12 - index}`,
    status: "sent",
    attempts: 1,
    error_code: "",
    created_at: new Date(Date.now() - index * 1000).toISOString(),
  }));
  await page.route("**/deliveries/**", (route) => {
    const number = Number(
      new URL(route.request().url()).searchParams.get("page") || 1,
    );
    return route.fulfill({
      json: {
        count: 12,
        next: number < 3 ? "next" : null,
        results: rows.slice((number - 1) * 5, number * 5),
      },
    });
  });
  await page.goto(`/w/${id}/integrations/?tab=channels`);
  const panel = page.locator("section.panel").filter({
    has: page.getByRole("heading", {
      name: "Recent deliveries",
      exact: true,
    }),
  });
  const dataRows = panel.locator("tbody tr");
  await expect(dataRows).toHaveCount(5);
  await expect(dataRows.first()).toContainText("recipient-12");
  await expect(
    panel.getByRole("button", { name: "Previous", exact: true }),
  ).toBeDisabled();
  await panel.getByRole("button", { name: "Next", exact: true }).click();
  await expect(dataRows).toHaveCount(5);
  await expect(dataRows.first()).toContainText("recipient-7");
  await expect(panel.getByText("6–10 of 12", { exact: true })).toBeVisible();
  await panel.getByRole("button", { name: "Next", exact: true }).click();
  await expect(dataRows).toHaveCount(2);
  await expect(
    panel.getByRole("button", { name: "Next", exact: true }),
  ).toBeDisabled();
  await panel.getByRole("button", { name: "Previous", exact: true }).click();
  await expect(dataRows.first()).toContainText("recipient-7");
});
