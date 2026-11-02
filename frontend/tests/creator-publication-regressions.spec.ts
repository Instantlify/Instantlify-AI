import { test, expect } from "@playwright/test";
import { id, mockApi } from "./support/meta-mock";

test("public kit controls follow successful saves and retain the draft after validation failure", async ({
  page,
}) => {
  await mockApi(page);
  let saved = {
    slug: "qa-kit",
    name: "QA creator",
    headline: "QA",
    bio: "",
    contact_email: "",
    links: [] as { label: string; url: string }[],
    statistics: [],
    services: [],
    published: false,
  };
  await page.route(`**/api/workspaces/${id}/creator-kit/`, (route) => {
    if (route.request().method() === "PUT") {
      const draft = route.request().postDataJSON();
      if (
        draft.links.some((link: { url: string }) =>
          link.url.startsWith("http:"),
        )
      ) {
        return route.fulfill({
          status: 400,
          json: { detail: "Use complete HTTPS links without credentials." },
        });
      }
      saved = draft;
    }
    return route.fulfill({ json: saved });
  });
  await page.goto(`/w/${id}/creator-kit`);
  await page.getByRole("button", { name: "Add link", exact: true }).click();
  await page.getByLabel("Link label", { exact: true }).fill("My work");
  await page
    .getByLabel("HTTPS link", { exact: true })
    .fill("http://example.com/");
  await page.getByLabel("Publish creator kit", { exact: true }).check();
  await expect(page.getByRole("link", { name: "Open public kit" })).toHaveCount(
    0,
  );
  await page.getByRole("button", { name: "Save creator kit" }).click();
  await expect(
    page.getByText("Use complete HTTPS links without credentials.", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(page.getByLabel("HTTPS link", { exact: true })).toHaveValue(
    "http://example.com/",
  );
  await expect(page.getByRole("link", { name: "Open public kit" })).toHaveCount(
    0,
  );
  await page
    .getByLabel("HTTPS link", { exact: true })
    .fill("https://example.com/");
  await page.getByRole("button", { name: "Save creator kit" }).click();
  await expect(
    page.getByRole("link", { name: "Open public kit" }),
  ).toHaveAttribute("href", "/c/qa-kit");
  await page
    .getByLabel("Public address", { exact: true })
    .fill("unsaved-address");
  await expect(
    page.getByRole("link", { name: "Open public kit" }),
  ).toHaveAttribute("href", "/c/qa-kit");
  await page.reload();
  await expect(
    page.getByRole("link", { name: "Open public kit" }),
  ).toHaveAttribute("href", "/c/qa-kit");
  await page.getByLabel("Publish creator kit", { exact: true }).uncheck();
  await page.getByRole("button", { name: "Save creator kit" }).click();
  await expect(page.getByRole("link", { name: "Open public kit" })).toHaveCount(
    0,
  );
});

test("both public Creator Kit entries describe available manual publishing", async ({
  page,
}) => {
  await page.goto("/features");
  const catalogue = page
    .locator("#feature-catalog article")
    .filter({ hasText: "Creator media kits" });
  await expect(catalogue).toContainText("Available");
  await expect(catalogue).toContainText("manual audience figures");
  const toolkit = page.locator(".nm-tool-grid article").filter({
    has: page.getByRole("heading", {
      name: "Creator media kits",
      exact: true,
    }),
  });
  await expect(toolkit).toContainText("Available");
  await expect(toolkit).toContainText("provider permissions");
});
