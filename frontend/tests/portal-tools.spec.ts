import { test, expect } from "@playwright/test";
import { id, mockApi } from "./support/meta-mock";
import type { LeadForm, CreatorKit } from "../lib/portal-tools";

test("a form has its own editor, public submission and response list", async ({
  page,
}) => {
  await mockApi(page);
  let saved: LeadForm | undefined;
  let submitted: Record<string, unknown> | undefined;
  await page.route(`**/api/workspaces/${id}/forms/`, (route) => {
    if (route.request().method() === "POST") {
      saved = {
        ...route.request().postDataJSON(),
        id: "form-1",
        submissions: 0,
      };
      return route.fulfill({ json: saved, status: 201 });
    }
    return route.fulfill({ json: saved ? [saved] : [] });
  });
  await page.route("**/api/public/forms/partnership/", (route) => {
    if (route.request().method() === "POST") {
      submitted = route.request().postDataJSON();
      return route.fulfill({
        json: {
          received: true,
          message: "Thank you. Your response has been received.",
        },
        status: 201,
      });
    }
    return route.fulfill({ json: saved });
  });
  await page.route(
    `**/api/workspaces/${id}/forms/form-1/submissions/`,
    (route) =>
      route.fulfill({
        json: [
          {
            id: "response-1",
            answers: submitted?.answers,
            consent_text: saved?.consent_text,
            created_at: new Date().toISOString(),
          },
        ],
      }),
  );
  await page.goto(`/w/${id}/forms`);
  await page.getByRole("button", { name: "Create form", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Title", { exact: true }).fill("Partnership enquiry");
  await dialog
    .getByLabel("Public address", { exact: true })
    .fill("partnership");
  await dialog.getByLabel("Publish form", { exact: true }).check();
  await dialog.getByRole("button", { name: "Save form", exact: true }).click();
  await expect(page.getByText("Form saved.", { exact: true })).toBeVisible();
  expect(saved?.fields.map((field) => field.id)).toEqual([
    "name",
    "email",
    "message",
  ]);
  await page.goto("/f/partnership?ref=launch");
  await page.getByLabel("Your name *", { exact: true }).fill("Local Test");
  await page
    .getByLabel("Email address *", { exact: true })
    .fill("test@example.com");
  await page
    .getByLabel("Your message", { exact: true })
    .fill("I would like to collaborate.");
  await page.getByRole("checkbox").check();
  await page
    .getByRole("button", { name: "Send response", exact: true })
    .click();
  await expect(page.getByRole("status")).toContainText(
    "Your response has been received",
  );
  expect(submitted).toMatchObject({
    ref: "launch",
    consent: true,
    answers: { email: "test@example.com" },
  });
  await page.goto(`/w/${id}/forms`);
  await page.getByRole("button", { name: "Responses", exact: true }).click();
  await page
    .getByRole("dialog")
    .locator("summary")
    .filter({ hasText: "Local Test" })
    .click();
  await expect(
    page
      .getByRole("dialog")
      .getByText("I would like to collaborate.", { exact: true }),
  ).toBeVisible();
});

test("creator kits publish their saved profile instead of sample statistics", async ({
  page,
}) => {
  await mockApi(page);
  let saved: CreatorKit | undefined;
  await page.route(`**/api/workspaces/${id}/creator-kit/`, (route) => {
    if (route.request().method() === "PUT")
      saved = route.request().postDataJSON();
    return route.fulfill({ json: saved || null });
  });
  await page.route("**/api/public/creator/local-creator/", (route) =>
    route.fulfill({ json: saved }),
  );
  await page.goto(`/w/${id}/creator-kit`);
  await page
    .getByLabel("Public address", { exact: true })
    .fill("local-creator");
  await page.getByLabel("Name", { exact: true }).fill("Local Creator");
  await page
    .getByLabel("Headline", { exact: true })
    .fill("Food stories worth sharing");
  await page.getByRole("button", { name: "Add metric", exact: true }).click();
  await page.getByLabel("Metric", { exact: true }).fill("Monthly reach");
  await page.getByLabel("Value", { exact: true }).fill("18,400");
  await page.getByLabel("Publish creator kit", { exact: true }).check();
  await page
    .getByRole("button", { name: "Save creator kit", exact: true })
    .click();
  await expect(
    page.getByText("Creator kit saved.", { exact: true }),
  ).toBeVisible();
  await page.goto("/c/local-creator");
  await expect(
    page.getByRole("heading", { name: "Local Creator", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("18,400", { exact: true })).toBeVisible();
  await expect(
    page.getByText("Audience figures provided by the creator.", {
      exact: true,
    }),
  ).toBeVisible();
});

test("tracking-link creation persists campaign, source and medium", async ({
  page,
}) => {
  await mockApi(page);
  let saved: Record<string, unknown> | undefined;
  await page.route(`**/api/workspaces/${id}/deeplinks/`, (route) => {
    if (route.request().method() === "POST") {
      saved = route.request().postDataJSON();
      return route.fulfill({
        json: { ...saved, id: "tracking-1", active: true, clicks: 0 },
      });
    }
    return route.fulfill({ json: [] });
  });
  await page.goto(`/w/${id}/deeplinks`);
  await page
    .getByRole("button", { name: "Create deep link", exact: true })
    .click();
  await page
    .getByRole("dialog")
    .getByLabel(/Title|Name/)
    .fill("October launch");
  await page
    .getByLabel("Destination HTTPS URL", { exact: true })
    .fill("https://example.com/offer");
  await page
    .getByLabel("Campaign (utm_campaign)", { exact: true })
    .fill("october");
  await page
    .getByLabel("Source (utm_source)", { exact: true })
    .fill("instagram");
  await page.getByLabel("Medium (utm_medium)", { exact: true }).fill("dm");
  await page
    .getByRole("button", { name: "Generate Smart Link", exact: true })
    .click();
  await expect
    .poll(() => saved)
    .toMatchObject({ campaign: "october", source: "instagram", medium: "dm" });
});
