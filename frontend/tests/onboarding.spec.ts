import { test, expect, type Cookie, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import path from "node:path";

/**
 * End-to-end pass over the product against the local Compose stack: account →
 * workspace → local test channel → automation → simulated comment → inbox → AI agent
 * → analytics → bio page → offers → invites → sign out/in → mobile. The channel is a
 * local test channel, so no provider is ever contacted whatever the adapter mode.
 */
test.describe.configure({ mode: "serial" });
test.skip(
  !!process.env.E2E_BASE_URL,
  "Requires the local Compose backend to provision the test workspace.",
);

const email = `e2e-${Date.now()}@example.com`;
const password = "River!Saffron42Cloud";
const slug = `e2e-${Date.now().toString(36)}`;
let workspaceUrl = "";
// This serial journey represents one signed-in user. Keep its session across
// isolated pages instead of repeatedly hitting the real IP-based login limit.
let sessionCookies: Cookie[] = [];
test.beforeEach(async ({ context }) => {
  await context.addCookies(sessionCookies);
});
test.afterEach(async ({ context }) => {
  sessionCookies = await context.cookies();
});
/** Live-mode backends refuse local test channels; the steps that need one skip then. */
let testChannels = true;
const NO_TEST_CHANNELS =
  "This backend refuses local test channels; run it with CHANNEL_ADAPTER_MODE=fake.";

/** Sections that live in the collapsible "Business tools" group of the sidebar. */
const TOOLS = [
  "AI agent",
  "Analytics",
  "Templates",
  "Payments",
  "Team",
  "Activity",
];

async function nav(page: Page, label: string) {
  if (TOOLS.includes(label)) {
    const tools = page.locator(".nav-tools");
    if (
      !(await tools.evaluate((element) => (element as HTMLDetailsElement).open))
    )
      await tools.locator("summary").click();
  }
  await page
    .getByRole("navigation", { name: "Workspace navigation" })
    .getByRole("link", { name: label, exact: true })
    .click();
}

async function simulate(page: Page, text: string, kind = "dm") {
  await nav(page, "Integrations");
  await page.getByRole("button", { name: "Channels", exact: true }).click();
  await page.getByLabel("Simulate an inbound message").fill(text);
  await page.getByLabel("Kind").selectOption(kind);
  await page.getByLabel("Sender ID").fill("lead-one");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "Test message queued" }),
  ).toBeVisible();
}

test("sign up, create a workspace and connect a test channel", async ({
  page,
}) => {
  test.slow(); // real signup against the live backend
  await page.goto("/");
  await page
    .getByRole("link", { name: "Get started", exact: true })
    .first()
    .click();
  await expect(page).toHaveURL(/\/auth\/?\?mode=signup/);
  await page
    .getByRole("textbox", { name: "Your name", exact: true })
    .fill("Alex");
  await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  // Short setup: optionally connect Instagram, then name the workspace.
  await expect(
    page.getByRole("heading", { name: "Connect your Instagram" }),
  ).toBeVisible({ timeout: 30000 });
  await page
    .getByRole("button", { name: "I’ll connect my account later" })
    .click();
  await page.getByLabel("Workspace name").fill("E2E Studio");
  await page
    .getByRole("button", { name: "Continue to plans", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Choose a plan" }),
  ).toBeVisible({ timeout: 30000 });
  const workspaceId = await page.evaluate(async () => {
    const response = await fetch("/api/workspaces/");
    const { results } = await response.json();
    return results[0].id as string;
  });
  expect(workspaceId).toMatch(/^[a-f0-9-]{36}$/);
  await page.goto(`/w/${workspaceId}/overview`);
  await expect(page).toHaveURL(
    new RegExp(`/onboarding/?\\?workspace=${workspaceId}`),
  );
  // The billing tests cover Stripe activation. Provision this workspace for
  // the rest of the local product smoke test.
  execFileSync(
    "docker",
    [
      "compose",
      "exec",
      "-T",
      "backend",
      "python",
      "manage.py",
      "shell",
      "-c",
      `from apps.tenants.models import Workspace; Workspace.objects.filter(pk='${workspaceId}').update(checkout_pending=False)`,
    ],
    { cwd: path.resolve(__dirname, "..", "..") },
  );
  await page.goto(`/onboarding?workspace=${workspaceId}&billing=success`);
  await expect(page).toHaveURL(/\/w\/[0-9a-f-]+\/overview/, { timeout: 30000 });
  workspaceUrl = page.url().replace(/\/overview.*$/, "");
  await expect(
    page.getByRole("heading", { name: "Your Statistics" }),
  ).toBeVisible();
  await expect(page.locator(".workspace-crumb")).toHaveText("E2E Studio");
  // Skipped the Instagram step, so the overview asks for a channel until one exists.
  await expect(page.getByText("Connect your Instagram account")).toBeVisible();
  await page.getByRole("link", { name: "Connect account" }).click();
  await expect(page).toHaveURL(/integrations\/?\?tab=channels/);

  await page
    .getByText("Advanced: manual credentials and test channels")
    .click();
  const connect = page.locator(".channel-advanced");
  await connect
    .getByRole("combobox", { name: /^Provider/ })
    .selectOption("instagram");
  await connect
    .getByLabel("Account ID", { exact: true })
    .fill(`e2e-instagram-${workspaceId}`);
  await connect
    .getByLabel("Display name", { exact: true })
    .fill("E2E Test Account");
  await connect
    .getByLabel("Create a local test channel (no provider calls)")
    .check();
  await connect.getByRole("button", { name: "Connect", exact: true }).click();
  const requested = page
    .getByRole("status")
    .filter({ hasText: "Connection requested" });
  const refused = page
    .getByRole("alert")
    .filter({ hasText: "Test connections are disabled" });
  await expect(requested.or(refused)).toBeVisible();
  if (await refused.isVisible()) {
    // The refusal is shown to the user and nothing is connected.
    await expect(page.getByText("No channels yet.")).toBeVisible();
    testChannels = false;
    test.info().annotations.push({
      type: "skipped steps",
      description: NO_TEST_CHANNELS,
    });
    return;
  }
  await expect(page.getByText("E2E Test Account")).toBeVisible();

  await nav(page, "Home");
  await expect(
    page.getByRole("region", { name: "Channel status" }),
  ).toContainText("Local test connection");
  await expect(page.getByText("Connect your Instagram account")).toHaveCount(0);
});

test("rename the workspace", async ({ page }) => {
  await signIn(page);
  await nav(page, "Settings");
  await page.getByRole("button", { name: "Workspaces", exact: true }).click();
  await page
    .getByLabel("Workspace Name", { exact: true })
    .fill("E2E Studio Updated");
  await page.getByRole("button", { name: "Save Changes", exact: true }).click();
  await expect(
    page
      .getByRole("status")
      .filter({ hasText: "Workspace settings saved successfully!" }),
  ).toBeVisible();
});

test("build and publish a comment → DM automation", async ({ page }) => {
  await signIn(page);
  await nav(page, "Automation");
  await page.getByRole("button", { name: "Create New" }).click();
  await page.getByRole("button", { name: /Advanced builder/ }).click();
  await expect(page).toHaveURL(/\/automations\/[0-9a-f-]+/);
  await expect(
    page.getByRole("heading", { name: "Untitled automation" }),
  ).toBeVisible();
  // The starter graph already has a trigger on "price"; publish it as-is.
  await expect(page.getByLabel("Keyword")).toHaveValue("price");
  await page.getByRole("button", { name: "Publish" }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "Published" }),
  ).toBeVisible();
  await nav(page, "Automation");
  await expect(
    page.getByRole("link", { name: "Untitled automation", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".status-pill").first()).toHaveText("Active");
  await expect(
    page.getByRole("switch", { name: "Untitled automation active" }),
  ).toBeChecked();
});

test("a simulated comment fires the flow and lands in the inbox", async ({
  page,
}) => {
  test.skip(!testChannels, NO_TEST_CHANNELS);
  await signIn(page);
  await simulate(page, "What is the PRICE?", "comment");
  await nav(page, "Conversations");
  const row = page.getByRole("button", { name: /lead[- .]one/i });
  await expect(row).toBeVisible({ timeout: 30000 });
  await row.click();
  const messages = page.locator(".bubble-text");
  await expect(
    messages.getByText("What is the PRICE?", { exact: true }),
  ).toBeVisible();
  await expect(
    messages.getByText("Thanks for asking! Here is everything you need.", {
      exact: true,
    }),
  ).toBeVisible({
    timeout: 30000,
  });
  // A comment permits one private automation reply, but does not open the
  // normal DM window. The customer must message before a teammate can reply.
  await simulate(page, "Can you help me?");
  await nav(page, "Conversations");
  await row.click();
  await expect(
    messages.getByText("Can you help me?", { exact: true }),
  ).toBeVisible({
    timeout: 30000,
  });
  // Human reply through the composer.
  await page.getByLabel("Reply").fill("Happy to help!");
  await page.getByRole("button", { name: "Send message" }).click();
  await expect(
    messages.getByText("Happy to help!", { exact: true }),
  ).toBeVisible();
  await page.getByLabel("Internal note").fill("Warm lead, follow up tomorrow");
  await page.getByRole("button", { name: "Add note" }).click();
  await expect(page.getByText("Warm lead, follow up tomorrow")).toBeVisible();
});

test("the AI agent answers with the local test provider", async ({ page }) => {
  test.skip(!testChannels, NO_TEST_CHANNELS);
  await signIn(page);
  await nav(page, "AI agent");
  await page.getByLabel("Use the local test provider (no API key)").check();
  await page.getByLabel("Agent enabled").check();
  await page.getByRole("button", { name: "Save agent settings" }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "Agent settings saved." }),
  ).toBeVisible();
  await page.getByLabel("Title").fill("Pricing FAQ");
  await page
    .getByLabel("Paste FAQ text")
    .fill("Our starter plan costs $49 per month.");
  await page.getByRole("button", { name: "Add to knowledge base" }).click();
  await expect(page.getByText("Pricing FAQ")).toBeVisible();
  await expect(page.getByText("ready", { exact: true })).toBeVisible({
    timeout: 30000,
  });
  await nav(page, "Conversations");
  await page.getByRole("button", { name: /lead[- .]one/i }).click();
  const aiActive = page
    .getByRole("group", { name: "Who replies" })
    .getByRole("button", { name: /^(AI active|Return to AI)$/ });
  if ((await aiActive.getAttribute("aria-pressed")) !== "true") {
    // The toggle is optimistic; wait for the save itself so the reload cannot abort it.
    const saved = page.waitForResponse(
      (response) =>
        response.request().method() === "PATCH" &&
        response.url().includes("/conversations/"),
    );
    await aiActive.click();
    expect((await saved).ok()).toBeTruthy();
  }
  // Reload so the assertion reflects the server, not the optimistic UI state.
  await page.reload();
  await page.getByRole("button", { name: /lead[- .]one/i }).click();
  await expect(aiActive).toHaveAttribute("aria-pressed", "true");
  await simulate(page, "Hello there");
  await nav(page, "Conversations");
  await page.getByRole("button", { name: /lead[- .]one/i }).click();
  await expect(
    page.locator(".bubble-text").filter({
      hasText: "[Local test] Thanks for reaching out.",
    }),
  ).toBeVisible({
    timeout: 30000,
  });
});

test("analytics, bio page, offers and invitations", async ({ page }) => {
  await signIn(page);
  await nav(page, "Analytics");
  await expect(page).toHaveURL(/\/analytics\//);
  // Automations appear in the funnel once they have fired, which needs a test channel.
  if (testChannels)
    await expect(
      page.getByRole("cell", { name: "Untitled automation", exact: true }),
    ).toBeVisible();
  await nav(page, "Link in bio");
  await page.getByRole("textbox", { name: /^Page address/ }).fill(slug);
  await page
    .getByRole("textbox", { name: "Title", exact: true })
    .fill("E2E Studio");
  await page
    .getByRole("textbox", { name: "Bio", exact: true })
    .fill("Book a call with us.");
  await page
    .getByRole("checkbox", {
      name: "Published (visible to anyone with the link)",
      exact: true,
    })
    .check();
  await page.getByRole("button", { name: "Save page" }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "Page saved." }),
  ).toBeVisible();
  await nav(page, "Payments");
  await page
    .getByRole("textbox", { name: "Name", exact: true })
    .fill("Starter pack");
  await page.getByRole("spinbutton", { name: /^Amount/ }).fill("49");
  await page.getByRole("button", { name: "Create offer" }).click();
  await expect(
    page.getByRole("cell", { name: "Starter pack", exact: true }),
  ).toBeVisible();
  await nav(page, "Team");
  await page
    .getByRole("textbox", { name: "Email address", exact: true })
    .fill("teammate@example.com");
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
  await expect(page.locator(".workspace-crumb")).toHaveText(
    "E2E Studio Updated",
  );
  await nav(page, "Home");
  if (testChannels)
    await expect(
      page.getByRole("region", { name: "Channel status" }),
    ).toContainText("Local test connection");
  await page.screenshot({
    path: "test-results/dashboard-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: "test-results/dashboard-mobile.png",
    fullPage: true,
  });
  // On phones the sidebar, and its sign-out button, sit in the navigation drawer.
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
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
  await Promise.race([
    heading.waitFor({ state: "visible", timeout: 15000 }),
    page.waitForURL(/\/w\/[0-9a-f-]+\//, { timeout: 15000 }),
  ]);
  const needsLogin = await heading.isVisible();
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
