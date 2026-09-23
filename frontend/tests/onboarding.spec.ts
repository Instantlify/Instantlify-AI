import { test, expect, type Page } from "@playwright/test";

/**
 * End-to-end pass over the product against the local Compose stack (fake providers):
 * account → workspace → test channel → automation → simulated comment → inbox →
 * AI agent → analytics → bio page → offers → invites → sign out/in → mobile.
 */
test.describe.configure({ mode: "serial" });

const email = `e2e-${Date.now()}@example.com`;
const password = "River!Saffron42Cloud";
const slug = `e2e-${Date.now().toString(36)}`;
let workspaceUrl = "";

async function nav(page: Page, label: string) {
  if (!["Overview", "Inbox", "Automations", "AI agent"].includes(label)) {
    const tools = page.locator(".nav-tools");
    if (!(await tools.getAttribute("open"))) {
      if (
        !(await tools.evaluate(
          (element) => (element as HTMLDetailsElement).open,
        ))
      )
        await tools.locator("summary").click();
    }
  }
  await page
    .getByRole("navigation", { name: "Workspace navigation" })
    .getByRole("link", { name: label, exact: true })
    .click();
}

test("sign up, create a workspace and connect a test channel", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("link", { name: "Get started", exact: true }).click();
  await page.getByLabel("Your name").fill("Alex");
  await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  // Short setup: optionally connect Instagram, then name the workspace.
  await expect(
    page.getByRole("heading", { name: "Connect your Instagram" }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "I’ll connect my account later" })
    .click();
  await page.getByLabel("Workspace name").fill("E2E Studio");
  await page
    .getByRole("button", { name: "Open my workspace", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Your business at a glance, Alex." }),
  ).toBeVisible();
  await expect(page).toHaveURL(/\/w\/[0-9a-f-]+\/overview/);
  workspaceUrl = page.url().replace(/\/overview.*$/, "");
  await expect(
    page.getByText("E2E Studio is ready for your team."),
  ).toBeVisible();
  // Skipped the Instagram step, so the overview insists on it until connected.
  await expect(page.getByText("Connect your Instagram account")).toBeVisible();
  await page.getByRole("button", { name: "Connect Instagram" }).click();
  await expect(page).toHaveURL(/integrations/);
  await nav(page, "Overview");
  await expect(page.getByText("Local connection test completed")).toBeVisible();
});

test("rename the workspace", async ({ page }) => {
  await signIn(page);
  await nav(page, "Settings");
  await page
    .getByLabel("Workspace name", { exact: true })
    .fill("E2E Studio Updated");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByRole("status")).toHaveText("Workspace name updated.");
});

test("build and publish a comment → DM automation", async ({ page }) => {
  await signIn(page);
  await nav(page, "Automations");
  await page.getByLabel("New automation").fill("Pricing comment");
  await page.getByRole("button", { name: "Create", exact: true }).click();
  await expect(page).toHaveURL(/\/automations\/[0-9a-f-]+/);
  await expect(
    page.getByRole("heading", { name: "Pricing comment" }),
  ).toBeVisible();
  // The starter graph already has a trigger on "price"; publish it as-is.
  await expect(page.getByLabel("Keyword")).toHaveValue("price");
  await page.getByRole("button", { name: "Publish" }).click();
  await expect(page.getByRole("status")).toContainText("Published");
  await nav(page, "Automations");
  await expect(
    page.getByRole("cell", { name: /Pricing comment/ }),
  ).toBeVisible();
  await expect(page.getByText("live", { exact: true })).toBeVisible();
});

test("a simulated comment fires the flow and lands in the inbox", async ({
  page,
}) => {
  await signIn(page);
  await nav(page, "Integrations");
  await page
    .getByLabel("Simulate an inbound message")
    .fill("What is the PRICE?");
  await page.getByLabel("Kind").selectOption("comment");
  await page.getByLabel("Sender ID").fill("lead-one");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByRole("status")).toBeVisible();
  await nav(page, "Inbox");
  const row = page.getByRole("button", { name: /lead-one/ });
  await expect(row).toBeVisible({ timeout: 30000 });
  await row.click();
  await expect(page.getByText("What is the PRICE?")).toBeVisible();
  await expect(
    page.getByText("Thanks for asking! Here is everything you need."),
  ).toBeVisible({
    timeout: 30000,
  });
  // Human reply through the composer.
  await page.getByLabel("Reply").fill("Happy to help!");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByText("Happy to help!")).toBeVisible();
  await page.getByLabel("Internal note").fill("Warm lead, follow up tomorrow");
  await page.getByRole("button", { name: "Add note" }).click();
  await expect(page.getByText("Warm lead, follow up tomorrow")).toBeVisible();
});

test("the AI agent answers with the local test provider", async ({ page }) => {
  await signIn(page);
  await nav(page, "AI agent");
  await page.getByLabel("Use the local test provider (no API key)").check();
  await page.getByLabel("Agent enabled").check();
  await page.getByRole("button", { name: "Save agent settings" }).click();
  await expect(page.getByRole("status").first()).toContainText(
    "Agent settings saved.",
  );
  await page.getByLabel("Title").fill("Pricing FAQ");
  await page
    .getByLabel("Paste FAQ text")
    .fill("Our starter plan costs $49 per month.");
  await page.getByRole("button", { name: "Add to knowledge base" }).click();
  await expect(page.getByText("Pricing FAQ")).toBeVisible();
  await expect(page.getByText("ready", { exact: true })).toBeVisible({
    timeout: 30000,
  });
  await nav(page, "Inbox");
  await page.getByRole("button", { name: /lead-one/ }).click();
  // The toggle is optimistic; wait for the save itself so the reload cannot abort it.
  const saved = page.waitForResponse(
    (response) =>
      response.request().method() === "PATCH" &&
      response.url().includes("/conversations/"),
  );
  await page.getByLabel("AI replies").check();
  expect((await saved).ok()).toBeTruthy();
  // Reload so the assertion reflects the server, not the optimistic UI state.
  await page.reload();
  await page.getByRole("button", { name: /lead-one/ }).click();
  await expect(page.getByLabel("AI replies")).toBeChecked();
  await nav(page, "Integrations");
  await page.getByLabel("Simulate an inbound message").fill("Hello there");
  await page.getByLabel("Sender ID").fill("lead-one");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await nav(page, "Inbox");
  await page.getByRole("button", { name: /lead-one/ }).click();
  await expect(
    page.getByText("[Local test] Thanks for reaching out."),
  ).toBeVisible({
    timeout: 30000,
  });
});

test("analytics, bio page, offers and invitations", async ({ page }) => {
  await signIn(page);
  await nav(page, "Analytics");
  await expect(
    page.getByRole("cell", { name: "Pricing comment" }),
  ).toBeVisible();
  await nav(page, "Link in bio");
  await page.getByLabel("Page address").fill(slug);
  await page.getByLabel("Title", { exact: true }).fill("E2E Studio");
  await page.getByLabel("Bio").fill("Book a call with us.");
  await page.getByLabel("Published (visible to anyone with the link)").check();
  await page.getByRole("button", { name: "Save page" }).click();
  await expect(page.getByRole("status")).toContainText("saved");
  await nav(page, "Payments");
  await page.getByLabel("Name", { exact: true }).fill("Starter pack");
  await page.getByLabel("Amount").fill("49");
  await page.getByRole("button", { name: "Create offer" }).click();
  await expect(page.getByRole("cell", { name: "Starter pack" })).toBeVisible();
  await nav(page, "Team");
  await page.getByLabel("Email address").fill("teammate@example.com");
  await page.getByRole("button", { name: "Create invite" }).click();
  await expect(page.getByText("One-time invite link")).toBeVisible();
  await page.goto(`/p/${slug}/`);
  await expect(page.getByRole("heading", { name: "E2E Studio" })).toBeVisible();
  await expect(page.getByText("Book a call with us.")).toBeVisible();
});

test("sign out, sign in, and the mobile layout", async ({ page }) => {
  await signIn(page);
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await page
    .getByRole("link", { name: "Sign in", exact: true })
    .first()
    .click();
  await expect(
    page.getByRole("heading", { name: "Welcome back." }),
  ).toBeVisible();
  await signIn(page);
  await expect(
    page.getByRole("combobox", { name: "Current workspace" }),
  ).toContainText("E2E Studio Updated");
  await expect(page).toHaveURL(/integrations/);
  await nav(page, "Overview");
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
  await page
    .getByRole("link", { name: "Sign in", exact: true })
    .first()
    .click();
  await expect(
    page.getByRole("heading", { name: "Welcome back." }),
  ).toBeVisible();
});

async function signIn(page: Page) {
  await page.goto("/auth");
  // Either the sign-in form appears, or a live session redirects straight into a workspace.
  const heading = page.getByRole("heading", { name: "Welcome back." });
  const needsLogin = await heading
    .waitFor({ state: "visible", timeout: 10000 })
    .then(() => true)
    .catch(() => false);
  if (needsLogin) {
    await page.getByLabel("Email address").fill(email);
    await page.getByLabel("Password", { exact: true }).fill(password);
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
  }
  await expect(page).toHaveURL(/\/w\/[0-9a-f-]+\//, { timeout: 15000 });
  if (!workspaceUrl)
    workspaceUrl = page.url().replace(/\/(overview|inbox).*$/, "");
}

test("the support assistant opens a ticket for a signed-in user", async ({
  page,
}) => {
  await signIn(page);
  await page.goto(`${workspaceUrl}/help`);
  const chat = page.getByRole("region", { name: "Support chat" });
  // Name and email come from the account, so no capture card is needed here.
  await chat
    .getByLabel("Message", { exact: true })
    .fill("I need a support ticket please");
  await chat.getByRole("button", { name: "Send message" }).click();
  await expect(chat.getByText(/Ticket #\d+ is open/)).toBeVisible();
});
