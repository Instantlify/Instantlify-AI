import { test, expect } from "@playwright/test";
import { id, mockApi } from "./support/meta-mock";
import type { LeadForm } from "../lib/portal-tools";

test("forms save submission actions and show provider suppression in response history", async ({
  page,
}) => {
  await mockApi(page);
  const integrationId = "55555555-5555-4555-8555-555555555555";
  await page.route(`**/api/workspaces/${id}/integrations/**`, (route) =>
    route.fulfill({
      json: {
        results: [
          {
            id: integrationId,
            provider: "zorromail",
            enabled: true,
            status: "active",
            configured: true,
          },
        ],
      },
    }),
  );
  let saved: LeadForm | undefined;
  await page.route(`**/api/workspaces/${id}/forms/`, (route) => {
    if (route.request().method() === "POST") {
      saved = { ...route.request().postDataJSON(), id: "form-one" };
      return route.fulfill({ status: 201, json: saved });
    }
    return route.fulfill({ json: saved ? [saved] : [] });
  });
  await page.route(
    `**/api/workspaces/${id}/forms/form-one/submissions/`,
    (route) =>
      route.fulfill({
        json: [
          {
            id: "submission-one",
            answers: { name: "A Person", email: "person@example.com" },
            consent_text: "Contact me",
            created_at: new Date().toISOString(),
            actions: [
              {
                id: "job-one",
                operation: "send_email",
                status: "complete",
                accepted: false,
                error: "",
              },
            ],
          },
        ],
      }),
  );
  await page.goto(`/w/${id}/forms/`);
  await page.getByRole("button", { name: "Create form", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await dialog
    .getByRole("textbox", { name: "Public address", exact: true })
    .fill("form-followup");
  await dialog
    .getByRole("button", { name: "Add submission action", exact: true })
    .click();
  await expect(
    dialog.getByRole("combobox", { name: "Action 1 integration", exact: true }),
  ).toHaveValue(integrationId);
  await dialog
    .getByRole("textbox", { name: "Email subject", exact: true })
    .fill("Thanks {{name}}");
  await dialog
    .getByRole("textbox", { name: "Message text", exact: true })
    .fill("We received your enquiry.");
  await dialog.getByRole("button", { name: "Save form", exact: true }).click();
  await expect(page.getByText("Form saved.", { exact: true })).toBeVisible();
  expect(saved?.submission_actions).toEqual([
    {
      operation: "send_email",
      integration_id: integrationId,
      subject: "Thanks {{name}}",
      text: "We received your enquiry.",
    },
  ]);
  await page.getByRole("button", { name: "Responses", exact: true }).click();
  await page.getByRole("dialog").locator("summary").click();
  await expect(page.getByRole("dialog")).toContainText(
    "Provider suppressed this recipient",
  );
});
