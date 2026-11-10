import { test, expect } from "@playwright/test";
import { id, mockApi } from "./support/meta-mock";

test("campaigns keep the saved draft after a failed launch and retry without duplication", async ({
  page,
}) => {
  await mockApi(page);
  await page.setViewportSize({ width: 1440, height: 1100 });
  let saved: Record<string, unknown> | null = null;
  let creates = 0;
  let launches = 0;
  await page.route(`**/api/workspaces/${id}/campaigns/**`, async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/audience/"))
      return route.fulfill({
        json: { eligible: 1, sample: [{ name: "Maya Chen", lead_id: "l-0" }] },
      });
    if (path.endsWith("/launch/")) {
      launches++;
      if (launches === 1)
        return route.fulfill({
          status: 503,
          json: { detail: "Temporary launch failure" },
        });
      saved = { ...saved, status: "queued", expected_count: 1 };
      return route.fulfill({ status: 202, json: saved });
    }
    if (
      route.request().method() === "POST" ||
      route.request().method() === "PATCH"
    ) {
      if (route.request().method() === "POST") creates++;
      saved = {
        ...route.request().postDataJSON(),
        id: "campaign-one",
        status: "draft",
        expected_count: 0,
        counts: {},
        created_at: new Date().toISOString(),
      };
      return route.fulfill({
        status: route.request().method() === "POST" ? 201 : 200,
        json: saved,
      });
    }
    return route.fulfill({ json: saved ? [saved] : [] });
  });
  await page.goto(`/w/${id}/crm/`);
  await page.getByRole("button", { name: "Campaign", exact: true }).click();
  await page.getByRole("button", { name: "New campaign", exact: true }).click();
  await page.getByLabel("Campaign name").fill("Spring guide");
  await page
    .getByRole("combobox", { name: "Sending account", exact: true })
    .selectOption("c-ig");
  await page
    .getByLabel("Campaign message")
    .fill("Hello {{name}}, here is your guide");
  await page.getByRole("button", { name: "Add link button" }).click();
  await page.getByLabel("Button HTTPS URL").fill("https://example.com/guide");
  await page.getByRole("button", { name: "Choose audience" }).click();
  await page.getByRole("button", { name: "Review audience" }).click();
  await expect(
    page.getByText("1 eligible contacts", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Send campaign", exact: true })
    .click();
  await expect(page.getByRole("dialog").getByRole("alert")).toContainText(
    "We couldn’t complete this request. Please try again in a moment.",
  );
  await expect(page.getByText("Saved draft", { exact: true })).toBeVisible();
  await page
    .getByRole("button", { name: "Send campaign", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Campaigns", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Spring guide", { exact: true })).toBeVisible();
  expect(creates).toBe(1);
  expect(launches).toBe(2);
  expect((saved as Record<string, unknown> | null)?.["buttons"]).toEqual([
    { type: "web_url", title: "Open", url: "https://example.com/guide" },
  ]);
});
