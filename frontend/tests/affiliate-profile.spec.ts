import { test, expect } from "@playwright/test";
import { id, mockApi } from "./support/meta-mock";

test("affiliate enrollment displays issued links and handles unavailable programs", async ({
  page,
}) => {
  await mockApi(page);
  let active = false;
  let configured = true;
  let enrollments = 0;
  await page.route("**/api/affiliate/", (route) => {
    if (route.request().method() === "POST") {
      active = true;
      enrollments++;
    }
    return route.fulfill({
      json: !configured
        ? { configured: false, status: "unavailable" }
        : active
          ? {
              configured: true,
              status: "active",
              is_confirmed: true,
              stats: { clicks_count: 7, referrals_count: 2, sales_count: 1 },
              revenue: "12.34",
              currency: "USD",
              campaigns: [
                {
                  name: "Partners",
                  state: "active",
                  ref_link: "https://example.com/?ref=issued",
                  coupon: "ALEX",
                },
              ],
            }
          : { configured: true, status: "not_enrolled" },
    });
  });
  await page.goto(`/w/${id}/affiliate/`);
  await expect(
    page.getByRole("button", { name: "Join referral program", exact: true }),
  ).toBeVisible();
  expect(enrollments).toBe(0);
  await page
    .getByRole("button", { name: "Join referral program", exact: true })
    .click();
  await expect(
    page.locator('input[value="https://example.com/?ref=issued"]'),
  ).toBeVisible();
  await expect(page.getByText("$12.34", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Refresh referral details" }).click();
  expect(enrollments).toBe(1);
  configured = false;
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Referral program unavailable" }),
  ).toBeVisible();
});

test("profile photo is uploaded with saved profile and survives refresh", async ({
  page,
}) => {
  await mockApi(page);
  let photo = "";
  let uploaded = false;
  const png = Buffer.from(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a3ioAAAAASUVORK5CYII=",
    "base64",
  );
  await page.route("**/api/auth/photo/**", (route) => {
    if (route.request().method() === "DELETE") {
      photo = "";
      return route.fulfill({ status: 204 });
    }
    return route.fulfill({ contentType: "image/png", body: png });
  });
  await page.route("**/api/auth/me/", (route) => {
    if (route.request().method() === "PATCH") {
      uploaded =
        route
          .request()
          .headers()
          ["content-type"].includes("multipart/form-data") &&
        (route.request().postData() || "").includes('filename="avatar.png"');
      photo = "/api/auth/photo/?v=saved";
    }
    return route.fulfill({
      json: {
        id: 1,
        name: "Alex Morgan",
        email: "alex@example.com",
        email_verified: true,
        photo_url: photo,
      },
    });
  });
  await page.goto(`/w/${id}/settings/`);
  await page
    .locator(
      'input[type="file"][accept="image/png,image/jpeg,image/gif,image/webp"]',
    )
    .setInputFiles({ name: "avatar.png", mimeType: "image/png", buffer: png });
  await page
    .locator("form")
    .filter({ has: page.getByLabel("Full Name", { exact: true }) })
    .getByRole("button", { name: /save/i })
    .click();
  await expect.poll(() => uploaded).toBe(true);
  await expect(page.getByAltText("Your profile photo")).toHaveAttribute(
    "src",
    photo,
  );
  await page.reload();
  await expect(page.getByAltText("Your profile photo")).toHaveAttribute(
    "src",
    photo,
  );
  await page.getByRole("button", { name: "Remove photo", exact: true }).click();
  await expect(page.getByAltText("Your profile photo")).toHaveCount(0);
});
