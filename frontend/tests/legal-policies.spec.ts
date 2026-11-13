import { test, expect } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.route("**/api/**", (route) =>
    route.fulfill({
      status: route.request().url().includes("/auth/me/") ? 401 : 200,
      json: {},
    }),
  );
});

test("legal pages are public, identify the operator and fit mobile screens", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  for (const path of ["privacy", "terms", "data-deletion"]) {
    await page.goto(`/${path}/`);
    await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
    await expect(page.locator("article")).toContainText(
      "SKY INNOVA SERVICES (PRIVATE) LIMITED",
    );
    await expect(page.locator("article")).toContainText("Pakistan");
    const footer = page.locator("article footer");
    await expect(
      footer.getByRole("link", {
        name: "support@instantlify.com",
        exact: true,
      }),
    ).toHaveAttribute("href", "mailto:support@instantlify.com");
    await expect(
      footer.getByRole("link", { name: "+92 324 8686799", exact: true }),
    ).toHaveAttribute("href", "tel:+923248686799");
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  }
  await page.screenshot({
    path: "test-results/data-deletion-mobile.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/privacy/");
  await page.screenshot({
    path: "test-results/privacy-desktop.png",
    fullPage: true,
  });
});

test("deletion status remains pending until the worker reports completion", async ({
  page,
}) => {
  let completed = false;
  const code = "a1234567890123456789012345678901";
  await page.route("**/api/public/data-deletion/**", (route) =>
    route.fulfill({
      json: {
        confirmation_code: code,
        status: completed ? "completed" : "pending",
        requested_at: "2026-11-13T10:00:00Z",
        completed_at: completed ? "2026-11-13T10:01:00Z" : null,
        connections_disconnected: 1,
        connections_deleted: completed ? 1 : 0,
      },
    }),
  );
  await page.clock.install();
  await page.goto(`/data-deletion/?code=${code}`);
  const status = page.getByRole("region", { name: "Deletion request status" });
  await expect(status.getByRole("heading")).toHaveText("Request received");
  await expect(status).toContainText("has not been marked complete");
  completed = true;
  await page.clock.fastForward(10001);
  await expect(status.getByRole("heading")).toHaveText("Completed");
});
