import { test, expect, type Locator } from "@playwright/test";
import { id, mockApi } from "./support/meta-mock";

/** Real brand logos (not generic glyphs) wherever a channel or integration is shown. */

const fillOf = (mark: Locator) =>
  mark.locator("path").first().getAttribute("fill");

test("landing page shows the real channel and integration logos", async ({
  page,
}) => {
  await page.route("**/api/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/public/plans/")
      return route.fulfill({ json: { trial_days: 10, plans: [] } });
    if (path === "/api/public/branding/")
      return route.fulfill({
        json: { brand_name: "Instantlify", primary_color: "#347359", logo_url: "" },
      });
    if (path === "/api/auth/me/")
      return route.fulfill({
        status: 401,
        json: { detail: "Sign in required" },
      });
    return route.fulfill({ json: {} });
  });
  await page.goto("/");
  const strip = page.getByRole("region", {
    name: "Supported messaging channels",
  });
  for (const brand of ["instagram", "whatsapp", "messenger", "telegram"])
    await expect(strip.locator(`[data-brand="${brand}"]`)).toBeVisible();
  // Instagram and Messenger keep their gradients; the rest use the brand colour.
  await expect(
    strip.locator('[data-brand="instagram"] radialGradient'),
  ).toHaveCount(1);
  await expect(
    strip.locator('[data-brand="messenger"] linearGradient'),
  ).toHaveCount(1);
  expect(await fillOf(strip.locator('[data-brand="whatsapp"]'))).toBe(
    "#25D366",
  );
  expect(await fillOf(strip.locator('[data-brand="telegram"]'))).toBe(
    "#26A5E4",
  );

  const grid = page.locator(".nm-integration-grid");
  await grid.scrollIntoViewIfNeeded();
  for (const brand of ["slack", "stripe", "zapier", "googlecalendar", "openai"])
    await expect(grid.locator(`[data-brand="${brand}"]`)).toBeVisible();
});

test("integrations gallery uses official marks and vendor logos that load", async ({
  page,
}) => {
  await mockApi(page);
  await page.goto(`/w/${id}/integrations`);
  const cards = page.locator(".boosend-int-card");
  for (const [name, brand] of [
    ["Google Sheets", "googlesheets"],
    ["Gmail", "gmail"],
    ["Slack", "slack"],
    ["Stripe", "stripe"],
    ["HubSpot", "hubspot"],
    ["Zapier", "zapier"],
  ])
    await expect(
      cards
        .filter({ hasText: name })
        .first()
        .locator(`[data-brand="${brand}"]`),
    ).toBeVisible();

  // Brands without an open-source mark use artwork served from /brands.
  for (const brand of ["gohighlevel", "klaviyo", "mailerlite"]) {
    const logo = page.locator(`img[data-brand="${brand}"]`).first();
    await expect(logo).toBeVisible();
    await expect
      .poll(() =>
        logo.evaluate((image: HTMLImageElement) => image.naturalWidth),
      )
      .toBeGreaterThan(0);
  }
});

test("inbox, CRM and the account switcher mark each channel with its logo", async ({
  page,
}) => {
  await mockApi(page);
  await page.goto(`/w/${id}/inbox`);
  const rows = page.locator(".boosend-conv-item");
  await expect(
    rows.filter({ hasText: "Maya Chen" }).locator('[data-brand="instagram"]'),
  ).toBeVisible();
  await expect(
    rows.filter({ hasText: "Omar Haddad" }).locator('[data-brand="whatsapp"]'),
  ).toBeVisible();
  await expect(
    rows
      .filter({ hasText: "Lena Fischer" })
      .locator('[data-brand="messenger"]'),
  ).toBeVisible();

  await page.locator(".social-account-card-trigger").click();
  const menu = page.locator(".social-account-menu-popover");
  const whatsapp = menu
    .getByRole("button", { name: /\+1 555 0100/ })
    .locator('[data-brand="whatsapp"]');
  await expect(whatsapp).toBeVisible();
  // On a coloured badge the mark is drawn in the badge's text colour.
  expect(await fillOf(whatsapp)).toBe("currentColor");

  await page.goto(`/w/${id}/crm`);
  const table = page.locator(".boosend-crm-table");
  await expect(
    table
      .locator("tr", { hasText: "Maya Chen" })
      .locator('[data-brand="instagram"]'),
  ).toBeVisible();
  await expect(
    table
      .locator("tr", { hasText: "Omar Haddad" })
      .locator('[data-brand="whatsapp"]'),
  ).toBeVisible();
  // Messenger contacts carry the Messenger mark, not the Instagram fallback.
  await expect(
    table
      .locator("tr", { hasText: "Lena Fischer" })
      .locator('[data-brand="messenger"]'),
  ).toBeVisible();
});

test("automation builder platform picker shows each platform's logo", async ({
  page,
}) => {
  await mockApi(page);
  await page.goto(`/w/${id}/automations`);
  await page.getByRole("button", { name: "Create New" }).click();
  await page.getByRole("button", { name: /Simple automation/ }).click();
  const picker = page.locator(".platform-cards-grid");
  for (const brand of ["instagram", "telegram", "whatsapp", "facebook"])
    await expect(picker.locator(`[data-brand="${brand}"]`)).toBeVisible();
});
