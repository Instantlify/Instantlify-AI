import { test, expect } from "@playwright/test";
import { id, mockApi } from "./support/meta-mock";

for (const width of [390, 1440]) {
  test(`CRM modal contains focus and restores it at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 850 });
    await mockApi(page);
    await page.goto(`/w/${id}/crm`);
    const opener = page.getByRole("button", {
      name: "Create contact",
      exact: true,
    });
    await opener.click();
    const dialog = page.getByRole("dialog", { name: "Create contact" });
    await expect(dialog).toBeVisible();
    await dialog.getByRole("button", { name: "Close dialog" }).focus();
    await page.keyboard.press("Shift+Tab");
    await expect
      .poll(() => dialog.evaluate((el) => el.contains(document.activeElement)))
      .toBe(true);
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
    await expect(opener).toBeFocused();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  });
}

test("HTTP destinations explain the error inside the dialog and retain focus and values", async ({
  page,
}) => {
  await mockApi(page);
  await page.goto(`/w/${id}/deeplinks`);
  await page.getByRole("button", { name: "Create deep link" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Link Title").fill("QA link");
  await dialog.getByLabel("App Target").selectOption("custom");
  const target = dialog.getByLabel("Destination HTTPS URL");
  await target.fill("http://example.com/");
  await dialog.getByRole("button", { name: "Generate Smart Link" }).click();
  await expect(
    dialog.getByText("Enter a destination starting with https://."),
  ).toBeVisible();
  await expect(target).toBeFocused();
  await expect(target).toHaveValue("http://example.com/");
});

test("Creator Kit handles missing arrays", async ({ page }) => {
  await mockApi(page);
  await page.route(`**/api/workspaces/${id}/creator-kit/`, (route) =>
    route.fulfill({ json: { name: "QA creator", slug: "qa", links: null } }),
  );
  await page.goto(`/w/${id}/creator-kit`);
  await expect(
    page.getByRole("button", { name: "Save creator kit" }),
  ).toBeVisible();
  await expect(page.getByLabel("Name", { exact: true })).toHaveValue(
    "QA creator",
  );
  await page.getByRole("button", { name: "Add metric" }).click();
  await expect(page.getByLabel("Metric", { exact: true })).toBeVisible();
});

test("Product menu dismisses and reopens", async ({ page }) => {
  await page.goto("/");
  const trigger = page.locator(".nm-mega > summary");
  await trigger.click();
  await expect(page.locator(".nm-mega")).toHaveAttribute("open", "");
  await page.keyboard.press("Escape");
  await expect(page.locator(".nm-mega")).not.toHaveAttribute("open");
  await expect(trigger).toBeFocused();
  await trigger.click();
  await page.getByRole("heading", { level: 1 }).click();
  await expect(page.locator(".nm-mega")).not.toHaveAttribute("open");
});

for (const width of [320, 390, 768]) {
  test(`workspace apps fit mobile width ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 850 });
    await mockApi(page);
    await page.route(`**/api/workspaces/${id}/creator-kit/`, (route) =>
      route.fulfill({ json: null }),
    );
    await page.route(`**/api/workspaces/${id}/forms/`, (route) =>
      route.fulfill({ json: [] }),
    );
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(error.message));
    for (const path of ["forms", "deeplinks", "creator-kit"]) {
      await page.goto(`/w/${id}/${path}`);
      await expect(page.locator("main h1")).toBeVisible();
      if (path === "forms")
        await expect(
          page.getByText("Your first form", { exact: true }),
        ).toBeVisible();
      if (path === "creator-kit")
        await expect(
          page.getByRole("button", { name: "Save creator kit" }),
        ).toBeVisible();
      await expect
        .poll(() =>
          page.evaluate(
            () => document.documentElement.scrollWidth <= innerWidth,
          ),
        )
        .toBe(true);
      if (path === "deeplinks") {
        await page.getByRole("button", { name: "Create deep link" }).click();
        const dialog = page.getByRole("dialog");
        await expect(dialog).toBeVisible();
        const bounds = await dialog.locator(".modal").boundingBox();
        expect(bounds?.x).toBeGreaterThanOrEqual(0);
        expect((bounds?.x || 0) + (bounds?.width || 0)).toBeLessThanOrEqual(
          width,
        );
        await page.screenshot({
          path: `test-results/qa-links-mobile-${width}.png`,
        });
        await page.keyboard.press("Escape");
      }
    }
    expect(errors).toEqual([]);
  });
}

for (const count of [0, 1, 2]) {
  test(`form response labels and updates preserve ${count} responses`, async ({
    page,
  }) => {
    const { defaultForm } = await import("../lib/portal-tools");
    await mockApi(page);
    let saved = {
      ...defaultForm(),
      id: "qa-form",
      title: "QA form",
      slug: "qa-form",
      published: true,
      submissions: count,
    };
    await page.route(`**/api/workspaces/${id}/forms/`, (route) =>
      route.fulfill({ json: [saved] }),
    );
    await page.route(`**/api/workspaces/${id}/forms/qa-form/`, (route) => {
      saved = {
        ...saved,
        ...route.request().postDataJSON(),
        submissions: count,
      };
      return route.fulfill({ json: saved });
    });
    await page.route(
      `**/api/workspaces/${id}/forms/qa-form/submissions/`,
      (route) =>
        route.fulfill({
          json: Array.from({ length: count }, (_, index) => ({
            id: `${index}`,
            answers: {},
            created_at: new Date().toISOString(),
            consent_text: "Consent",
          })),
        }),
    );
    await page.goto(`/w/${id}/forms`);
    const label = `${count} ${count === 1 ? "response" : "responses"}`;
    await expect(page.getByText(label, { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Edit form" }).click();
    await page.getByLabel("Publish form", { exact: true }).uncheck();
    await page.getByRole("button", { name: "Save form", exact: true }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(page.getByText(label, { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Responses", exact: true }).click();
    await expect(page.getByRole("dialog")).toContainText(`Latest ${label}`);
  });
}

test("tracking-link labels use singular counts and server errors stay in the dialog", async ({
  page,
}) => {
  await mockApi(page);
  await page.route(`**/api/workspaces/${id}/deeplinks/`, (route) => {
    if (route.request().method() === "POST")
      return route.fulfill({
        status: 400,
        json: { target: ["This destination is unavailable."] },
      });
    return route.fulfill({
      json: [
        {
          id: "qa-link",
          code: "qa-link",
          title: "QA link",
          platform: "custom",
          target: "https://example.com",
          active: true,
          clicks: 1,
        },
      ],
    });
  });
  await page.route(
    `**/api/workspaces/${id}/deeplinks/qa-link/stats/`,
    (route) =>
      route.fulfill({ json: { clicks: 1, form_submissions: 1, daily: [] } }),
  );
  await page.goto(`/w/${id}/deeplinks`);
  await expect(
    page.getByText("1 link configured", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: /View activity/ }).click();
  await expect(page.getByRole("dialog")).toContainText(
    "1 click · 1 attributed form submission",
  );
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Create deep link" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Link Title").fill("Server validation");
  const target = dialog.getByLabel("Destination HTTPS URL");
  await target.fill("https://example.com");
  await dialog.getByRole("button", { name: "Generate Smart Link" }).click();
  await expect(dialog.locator(".field-error")).toContainText(
    "This destination is unavailable.",
  );
  await expect(target).toBeFocused();
  await expect(target).toHaveValue("https://example.com");
});
