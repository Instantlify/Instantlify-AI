import { test, expect } from "@playwright/test";
import { id, mockApi } from "./support/meta-mock";

test("CRM creates, edits and pauses a named AI segment", async ({ page }) => {
  await mockApi(page);
  let segment: {
    id: string;
    name: string;
    prompt: string;
    enabled: boolean;
  } | null = null;
  await page.route(`**/api/workspaces/${id}/agent/`, (route) =>
    route.fulfill({
      json: {
        enabled: true,
        segmentation_enabled: true,
        segmentation_prompt: "",
      },
    }),
  );
  await page.route(`**/api/workspaces/${id}/segments/**`, (route) => {
    if (route.request().method() === "POST") {
      segment = { id: "segment-one", ...route.request().postDataJSON() };
      return route.fulfill({ status: 201, json: segment });
    }
    if (route.request().method() === "PATCH") {
      segment = { ...segment!, ...route.request().postDataJSON() };
      return route.fulfill({ json: segment });
    }
    return route.fulfill({ json: segment ? [segment] : [] });
  });
  await page.goto(`/w/${id}/crm/`);
  await page
    .getByRole("button", { name: "AI segmentation", exact: true })
    .click();
  const dialog = page.getByRole("dialog", {
    name: "AI contact segmentation",
    exact: true,
  });
  await dialog
    .getByRole("button", { name: "New segment", exact: true })
    .click();
  await dialog.getByLabel("Segment name", { exact: true }).fill("Enterprise");
  await dialog
    .getByRole("textbox", { name: "Segment prompt", exact: true })
    .fill("Asked for a team demo");
  await dialog
    .getByRole("button", { name: "Create segment", exact: true })
    .click();
  await expect(
    dialog.getByText("Asked for a team demo", { exact: true }),
  ).toBeVisible();
  await dialog
    .getByRole("button", { name: "Edit Enterprise", exact: true })
    .click();
  await dialog
    .getByRole("textbox", { name: "Segment prompt", exact: true })
    .fill("Asked for enterprise pricing");
  await dialog
    .getByRole("button", { name: "Save segment", exact: true })
    .click();
  await expect(
    dialog.getByText("Asked for enterprise pricing", { exact: true }),
  ).toBeVisible();
  await dialog
    .getByRole("button", { name: "Pause Enterprise", exact: true })
    .click();
  await expect(
    dialog.getByRole("button", { name: "Enable Enterprise", exact: true }),
  ).toBeVisible();
});
