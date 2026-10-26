import { expect, test } from "@playwright/test";
import { automations, id, mockApi } from "./support/meta-mock";

test("automation actions open without navigating and deletion requires confirmation", async ({
  page,
}) => {
  await mockApi(page);
  let deletes = 0;
  await page.route(`**/api/workspaces/${id}/automations/a-1/`, (route) => {
    if (route.request().method() === "DELETE") {
      deletes += 1;
      return route.fulfill({ status: 204, body: "" });
    }
    return route.fulfill({ json: automations[0] });
  });
  await page.goto(`/w/${id}/automations/`);
  const actions = page.getByLabel(`Actions for ${automations[0].name}`, {
    exact: true,
  });
  await actions.click();
  await expect(page).toHaveURL(new RegExp(`/w/${id}/automations/$`));
  const menu = page.getByRole("group", {
    name: `Manage ${automations[0].name}`,
    exact: true,
  });
  await expect(
    menu.getByRole("link", { name: "Edit automation" }),
  ).toBeVisible();
  await actions.press("Escape");
  await expect(menu).not.toBeVisible();
  await actions.click();
  await menu
    .getByRole("button", { name: "Delete automation", exact: true })
    .click();
  const dialog = page.getByRole("dialog", {
    name: "Delete automation",
    exact: true,
  });
  await expect(dialog).toContainText(automations[0].name);
  await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
  expect(deletes).toBe(0);
  await expect(
    page.getByRole("link", { name: automations[0].name, exact: true }),
  ).toBeVisible();
  await actions.click();
  await menu
    .getByRole("button", { name: "Delete automation", exact: true })
    .click();
  await dialog
    .getByRole("button", { name: "Delete automation", exact: true })
    .click();
  await expect(
    page.getByRole("link", { name: automations[0].name, exact: true }),
  ).toHaveCount(0);
  expect(deletes).toBe(1);
  await expect(
    page.getByRole("link", { name: automations[1].name, exact: true }),
  ).toBeVisible();
});

test("duplicating creates a draft in the list without opening the editor", async ({
  page,
}) => {
  await mockApi(page);
  let duplicates = 0;
  await page.route(
    `**/api/workspaces/${id}/automations/a-1/duplicate/`,
    (route) => {
      duplicates += 1;
      return route.fulfill({
        status: 201,
        json: {
          ...automations[0],
          id: "copied-flow",
          name: "Copied automation",
          enabled: false,
          published: {},
          revision: 0,
        },
      });
    },
  );
  await page.goto(`/w/${id}/automations/`);
  await page
    .getByLabel(`Actions for ${automations[0].name}`, { exact: true })
    .click();
  await page.getByRole("button", { name: "Duplicate", exact: true }).click();
  await expect(
    page.getByRole("link", { name: "Copied automation", exact: true }),
  ).toBeVisible();
  expect(duplicates).toBe(1);
  await expect(page).toHaveURL(new RegExp(`/w/${id}/automations/$`));
});

test("failed deletion keeps the automation and shows the server error", async ({
  page,
}) => {
  await mockApi(page);
  await page.route(`**/api/workspaces/${id}/automations/a-1/`, (route) =>
    route.fulfill({
      status: 400,
      json: { detail: "Delete the A/B experiment first." },
    }),
  );
  await page.goto(`/w/${id}/automations/`);
  await page
    .getByLabel(`Actions for ${automations[0].name}`, { exact: true })
    .click();
  await page
    .getByRole("button", { name: "Delete automation", exact: true })
    .click();
  const dialog = page.getByRole("dialog", {
    name: "Delete automation",
    exact: true,
  });
  await dialog
    .getByRole("button", { name: "Delete automation", exact: true })
    .click();
  await expect(dialog.getByRole("alert")).toContainText(
    "Delete the A/B experiment first.",
  );
  await dialog.getByRole("button", { name: "Cancel", exact: true }).click();
  await expect(
    page.getByRole("link", { name: automations[0].name, exact: true }),
  ).toBeVisible();
});

test("simple builder restores six steps and a live phone for every channel", async ({
  page,
}) => {
  await mockApi(page);
  await page.goto(`/w/${id}/automations/`);
  await page.getByRole("button", { name: "Create New", exact: true }).click();
  await page.getByRole("button", { name: /Simple automation/ }).click();
  await expect(
    page.getByRole("group", {
      name: "3 Choose your trigger words",
      exact: true,
    }),
  ).toBeVisible();
  const preview = page.getByRole("complementary", {
    name: "Conversation preview",
  });
  const phone = preview.locator(".nm-guided-phone");
  await expect(phone).toHaveAttribute("data-channel", "instagram");
  await expect(
    page.getByRole("radio", { name: /Comments on a post/ }),
  ).toBeChecked();
  await page.getByRole("button", { name: "WhatsApp", exact: true }).click();
  await expect(phone).toHaveAttribute("data-channel", "whatsapp");
  await expect(preview.getByText("WhatsApp · online")).toBeVisible();
  await page
    .getByRole("textbox", { name: "Opening message", exact: true })
    .fill("Hello from our WhatsApp team.");
  await expect(
    preview.getByText("Hello from our WhatsApp team."),
  ).toBeVisible();
  await preview
    .getByRole("button", { name: "Send me the link", exact: true })
    .click();
  await expect(
    preview.getByText("Here are the resources you asked for."),
  ).toBeVisible();
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: "instant" }));
  await page.screenshot({
    path: test.info().outputPath("whatsapp-phone.png"),
  });
  await page.getByRole("button", { name: "Facebook", exact: true }).click();
  await expect(phone).toHaveAttribute("data-channel", "facebook");
  await expect(preview.getByText("Messenger · Active now")).toBeVisible();
  await page.getByRole("button", { name: "Telegram", exact: true }).click();
  await expect(phone).toHaveAttribute("data-channel", "telegram");
  await expect(preview.getByText("Telegram · bot")).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(preview).not.toBeVisible();
  await page
    .getByRole("button", { name: "Show phone preview", exact: true })
    .click();
  await expect(phone).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({ path: test.info().outputPath("mobile-phone.png") });
  await preview
    .getByRole("button", { name: "Close preview", exact: true })
    .click();
  await expect(preview).not.toBeVisible();
});
