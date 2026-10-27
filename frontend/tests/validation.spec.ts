import { expect, test, type Page } from "@playwright/test";
import { id, mockApi } from "./support/meta-mock";
import { defaultForm } from "../lib/portal-tools";

async function openForm(page: Page, reject?: Record<string, unknown>) {
  await mockApi(page);
  const saves: Record<string, unknown>[] = [];
  await page.route(`**/api/workspaces/${id}/forms/`, (route) => {
    if (route.request().method() === "GET") return route.fulfill({ json: [] });
    const body = route.request().postDataJSON();
    saves.push(body);
    if (reject && saves.length === 1)
      return route.fulfill({ status: 400, json: reject });
    return route.fulfill({ status: 201, json: { ...body, id: "form-new" } });
  });
  await page.goto(`/w/${id}/forms/`);
  await page.getByRole("button", { name: "Create form", exact: true }).click();
  return { dialog: page.getByRole("dialog", { name: "Create form" }), saves };
}

test("missing required form details are highlighted, described and focused before any save", async ({
  page,
}) => {
  const { dialog, saves } = await openForm(page);
  const title = dialog.getByRole("textbox", { name: "Title", exact: true });
  const address = dialog.getByRole("textbox", {
    name: "Public address",
    exact: true,
  });
  await expect(address).toHaveValue("contact-us");
  await title.fill("   ");
  await address.clear();
  await dialog.getByRole("button", { name: "Save form", exact: true }).click();
  await expect(title).toHaveAttribute("aria-invalid", "true");
  await expect(address).toHaveAttribute("aria-invalid", "true");
  await expect(title).toBeFocused();
  await expect(title).toHaveAccessibleDescription("Enter title.");
  await expect(address).toHaveAccessibleDescription(/Choose a public address/);
  expect(saves).toHaveLength(0);
  await page.screenshot({
    path: "test-results/form-validation-errors.png",
    fullPage: true,
  });
  await title.fill("Partnership enquiries");
  await address.fill("partnership");
  await expect(title).not.toHaveAttribute("aria-invalid", "true");
  await expect(address).not.toHaveAttribute("aria-invalid", "true");
  await dialog.getByRole("button", { name: "Save form", exact: true }).click();
  await expect(page.getByText("Form saved.", { exact: true })).toBeVisible();
  expect(saves).toHaveLength(1);
});

test("invalid public addresses give an example instead of technical terminology", async ({
  page,
}) => {
  const { dialog, saves } = await openForm(page);
  const address = dialog.getByRole("textbox", {
    name: "Public address",
    exact: true,
  });
  await address.fill("My Form!");
  await dialog.getByRole("button", { name: "Save form", exact: true }).click();
  await expect(address).toHaveAttribute("aria-invalid", "true");
  await expect(address).toHaveAccessibleDescription(
    /lowercase letters, numbers and hyphens/,
  );
  expect(saves).toHaveLength(0);
  await expect(dialog).not.toContainText(/\bslug\b/i);
});

for (const [label, payload] of [
  ["field errors", { slug: ["This field is required."] }],
  ["legacy messages", { detail: "Please provide slug." }],
] as const)
  test(`server address ${label} stay readable and highlight the matching input`, async ({
    page,
  }) => {
    const { dialog, saves } = await openForm(page, payload);
    await dialog
      .getByRole("button", { name: "Save form", exact: true })
      .click();
    const address = dialog.getByRole("textbox", {
      name: "Public address",
      exact: true,
    });
    await expect(address).toHaveAttribute("aria-invalid", "true");
    await expect(address).toBeFocused();
    await expect(address).toHaveAccessibleDescription(
      /Choose a public address/,
    );
    await expect(dialog).not.toContainText(/\bslug\b|\[object Object\]/i);
    await address.fill("another-form");
    await expect(address).not.toHaveAttribute("aria-invalid", "true");
    await dialog
      .getByRole("button", { name: "Save form", exact: true })
      .click();
    await expect(page.getByText("Form saved.", { exact: true })).toBeVisible();
    expect(saves).toHaveLength(2);
  });

test("nested server errors identify the question without exposing response objects", async ({
  page,
}) => {
  const { dialog } = await openForm(page, {
    fields: [{ label: ["This field may not be blank."] }],
  });
  await dialog.getByRole("button", { name: "Save form", exact: true }).click();
  const question = dialog.locator('[name="fields.0.label"]');
  await expect(question).toBeFocused();
  await expect(question).toHaveAttribute("aria-invalid", "true");
  await expect(question).toHaveAccessibleDescription(/question 1 text/i);
  await expect(dialog).not.toContainText(
    /\[object Object\]|fields\.0|non_field_errors/,
  );
});

test("offer amount limits are explained before a price is saved", async ({
  page,
}) => {
  await mockApi(page);
  let saved: Record<string, unknown> | undefined;
  await page.route(`**/api/workspaces/${id}/offers/`, (route) => {
    if (route.request().method() === "POST") {
      saved = route.request().postDataJSON();
      return route.fulfill({
        status: 201,
        json: { id: "offer-new", ...saved },
      });
    }
    return route.fulfill({ json: { results: [] } });
  });
  await page.route(`**/api/workspaces/${id}/payments/`, (route) =>
    route.fulfill({ json: [] }),
  );
  await page.goto(`/w/${id}/payments/`);
  const form = page
    .locator("form")
    .filter({ has: page.getByRole("button", { name: "Create offer" }) });
  await form
    .getByRole("textbox", { name: "Name", exact: true })
    .fill("Consultation");
  const amount = form.getByRole("spinbutton");
  await amount.fill("0.1");
  await form.getByRole("button", { name: "Create offer" }).click();
  await expect(amount).toHaveAttribute("aria-invalid", "true");
  await expect(amount).toHaveAccessibleDescription("Enter 0.5 or more.");
  expect(saved).toBeUndefined();
  await amount.fill("2.50");
  await form.getByRole("button", { name: "Create offer" }).click();
  await expect.poll(() => saved).toMatchObject({ amount_cents: 250 });
});

test("duplicate answer names open advanced settings and cannot be saved", async ({
  page,
}) => {
  const { dialog, saves } = await openForm(page);
  const question = dialog
    .locator("fieldset")
    .filter({ has: page.locator("legend", { hasText: "Question 3" }) });
  await question.getByText("Advanced answer settings", { exact: true }).click();
  const answerName = question.getByRole("textbox").first();
  await answerName.fill("name");
  await question.locator("summary").click();
  await dialog.getByRole("button", { name: "Save form", exact: true }).click();
  await expect(answerName).toBeVisible();
  await expect(answerName).toBeFocused();
  await expect(answerName).toHaveAttribute("aria-invalid", "true");
  await expect(answerName).toHaveAccessibleDescription(
    /already used by another question/,
  );
  expect(saves).toHaveLength(0);
});

test("public forms validate email and permission without sending invalid answers", async ({
  page,
}) => {
  await mockApi(page);
  let submissions = 0;
  await page.route("**/api/public/forms/check-details/", (route) => {
    if (route.request().method() === "POST") {
      submissions++;
      return route.fulfill({ json: { message: "Thank you." } });
    }
    return route.fulfill({
      json: { ...defaultForm(), id: "public", slug: "check-details" },
    });
  });
  await page.goto("/f/check-details/");
  await page.getByLabel("Your name *", { exact: true }).fill("A Person");
  const email = page.getByLabel("Email address *", { exact: true });
  await email.fill("incorrect-address");
  await page
    .getByRole("button", { name: "Send response", exact: true })
    .click();
  await expect(email).toHaveAttribute("aria-invalid", "true");
  await expect(email).toHaveAccessibleDescription(/name@example.com/);
  await expect(page.getByRole("checkbox")).toHaveAttribute(
    "aria-invalid",
    "true",
  );
  expect(submissions).toBe(0);
  await email.fill("person@example.com");
  await page.getByRole("checkbox").check();
  await page
    .getByRole("button", { name: "Send response", exact: true })
    .click();
  await expect(page.getByRole("status")).toHaveText("Thank you.");
  expect(submissions).toBe(1);
});

test("contact creation blocks a blank name and malformed optional email", async ({
  page,
}) => {
  await mockApi(page);
  await page.goto(`/w/${id}/crm/`);
  await page
    .getByRole("button", { name: /Create contact|Add contact/i })
    .first()
    .click();
  const dialog = page.getByRole("dialog", { name: "Create contact" });
  await dialog
    .getByRole("button", { name: "Create contact", exact: true })
    .click();
  const name = dialog.getByRole("textbox", { name: "Name", exact: true });
  await expect(name).toHaveAttribute("aria-invalid", "true");
  await name.fill("A Person");
  const email = dialog.getByRole("textbox", {
    name: "Email (optional)",
    exact: true,
  });
  await email.fill("not-an-email");
  await dialog
    .getByRole("button", { name: "Create contact", exact: true })
    .click();
  await expect(email).toHaveAccessibleDescription(/name@example.com/);
  await email.clear();
  await dialog
    .getByRole("button", { name: "Create contact", exact: true })
    .click();
  await expect(dialog).toHaveCount(0);
});

test("integration setup highlights every missing required value", async ({
  page,
}) => {
  await mockApi(page);
  await page.goto(`/w/${id}/integrations/`);
  await page
    .locator(".boosend-int-card")
    .filter({ hasText: "ZorroMail" })
    .getByRole("button", { name: "Create Integration", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Save Configuration", exact: true })
    .click();
  await expect(
    page.getByLabel("Transactional API key", { exact: true }),
  ).toHaveAttribute("aria-invalid", "true");
  await expect(
    page.getByRole("textbox", { name: "Verified sender email", exact: true }),
  ).toHaveAttribute("aria-invalid", "true");
  await page
    .getByRole("textbox", { name: "Verified sender email", exact: true })
    .fill("sender@example.com");
  await expect(
    page.getByRole("textbox", { name: "Verified sender email", exact: true }),
  ).not.toHaveAttribute("aria-invalid", "true");
});

test("password settings match the server’s length rule and explain mismatched confirmation", async ({
  page,
}) => {
  await mockApi(page);
  let updates = 0;
  await page.route("**/api/auth/password/", (route) => {
    updates++;
    return route.fulfill({ json: { detail: "Password updated." } });
  });
  await page.goto(`/w/${id}/settings/`);
  const password = page.getByLabel("New password", { exact: true });
  const confirmation = page.getByLabel("Confirm Password", { exact: true });
  await password.fill("short-pass");
  await confirmation.fill("different-value");
  await page
    .getByRole("button", { name: "Update password", exact: true })
    .click();
  await expect(password).toHaveAttribute("aria-invalid", "true");
  await expect(password).toHaveAccessibleDescription(/at least 12 characters/);
  await expect(confirmation).toHaveAccessibleDescription(
    /Passwords don’t match/,
  );
  expect(updates).toBe(0);
  await password.fill("A-long-new-password-42");
  await confirmation.fill("A-long-new-password-42");
  await page
    .getByRole("button", { name: "Update password", exact: true })
    .click();
  await expect.poll(() => updates).toBe(1);
});
