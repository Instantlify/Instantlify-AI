import { test, expect } from "@playwright/test";

test("sign up, create a workspace, test connection, sign out, and sign in", async ({
  page,
}) => {
  const email = `e2e-${Date.now()}@example.com`;
  const password = "River!Saffron42Cloud";
  await page.goto("/");
  await page.getByRole("button", { name: "Create an account" }).click();
  await page.getByLabel("Your name").fill("Alex");
  await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await page.getByLabel("Workspace name").fill("E2E Studio");
  await page
    .getByRole("button", { name: "Create workspace", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "A fresh start, Alex." }),
  ).toBeVisible();
  await expect(
    page.getByText("E2E Studio is ready for your team."),
  ).toBeVisible();
  await page.getByRole("button", { name: "Test connection setup" }).click();
  await expect(page.getByText("Local connection test completed")).toBeVisible();
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await page
    .getByLabel("Workspace name", { exact: true })
    .fill("E2E Studio Updated");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByRole("status")).toHaveText("Workspace name updated.");
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "A fresh start, Alex." }),
  ).toBeVisible();
  await expect(
    page.getByRole("combobox", { name: "Current workspace" }),
  ).toContainText("E2E Studio Updated");
  await expect(page.getByText("Local connection test completed")).toBeVisible();
  await page.screenshot({
    path: "test-results/dashboard-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(
    page.getByRole("button", { name: "Sign out on mobile" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: "test-results/dashboard-mobile.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "Sign out on mobile" }).click();
  await expect(
    page.getByRole("heading", { name: "Welcome back." }),
  ).toBeVisible();
});
