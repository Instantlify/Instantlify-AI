import { test, expect } from "@playwright/test";

const catalog = {
  trial_days: 10,
  plans: [
    {
      slug: "pro",
      name: "Pro",
      is_featured: true,
      limits: {
        max_instagram_accounts: 3,
        team_seats: 5,
        max_contacts: 5000,
        max_ai_messages: 1000,
        ai_agent_enabled: true,
        integrations_unlocked: true,
        content_scheduling_enabled: true,
        voice_notes_enabled: false,
      },
      prices: [
        { interval: "monthly", price_cents: 4900, configured: true },
        { interval: "annual", price_cents: 49000, configured: true },
      ],
    },
  ],
};

test.beforeEach(async ({ page }) => {
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/public/plans/") return route.fulfill({ json: catalog });
    if (path === "/api/auth/me/")
      return route.fulfill({
        status: 401,
        json: { detail: "Sign in required" },
      });
    if (path === "/api/public/branding/")
      return route.fulfill({
        json: { brand_name: "Nemio", primary_color: "#347359", logo_url: "" },
      });
    return route.fulfill({ json: {} });
  });
});

test("public homepage has metadata, live plan controls and signup navigation", async ({
  page,
}) => {
  await page.goto("/");
  await expect(page).toHaveTitle("Nemio · Turn conversations into customers");
  await expect(page.getByRole("heading", { level: 1 })).toContainText(
    "Turn enquiries into",
  );
  await expect(page.locator(".plan-price")).toContainText("$49");
  await page.getByRole("button", { name: "Annual", exact: true }).click();
  await expect(page.locator(".plan-price")).toContainText("$490");
  await expect(page.locator(".plan-trial")).toHaveText("10-day free trial");
  await page.screenshot({
    path: "test-results/nemio-home-desktop.png",
    fullPage: true,
  });
  await page
    .locator(".plan-card")
    .getByRole("button", { name: "Get started" })
    .click();
  await expect(page).toHaveURL(/auth\/\?mode=signup&plan=pro&interval=annual/);
  await expect(page.getByLabel("Your name")).toBeVisible();
});

test("mobile homepage fits and links to sign in", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.locator(".plan-card")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page
    .getByText("Do I need to know how to code?", { exact: true })
    .click();
  await expect(page.getByText(/No. Build automations visually/)).toBeVisible();
  await page.screenshot({
    path: "test-results/nemio-home-mobile.png",
    fullPage: true,
  });
  await page
    .getByRole("link", { name: "Sign in", exact: true })
    .first()
    .click();
  await expect(
    page.getByRole("heading", { name: "Welcome back." }),
  ).toBeVisible();
});

test("pricing outage recovers on retry", async ({ page }) => {
  let unavailable = true;
  await page.route("**/api/public/plans/", (route) =>
    unavailable
      ? route.fulfill({ status: 503, json: { detail: "Unavailable" } })
      : route.fulfill({ json: catalog }),
  );
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Try again" })).toBeVisible();
  unavailable = false;
  await page.getByRole("button", { name: "Try again" }).click();
  await expect(page.locator(".plan-price")).toContainText("$49");
});

test("legacy invitation and pricing links reach authentication", async ({
  page,
}) => {
  await page.goto("/?invite=sample-invitation");
  await expect(page).toHaveURL(/auth\/\?invite=sample-invitation/);
  await expect(
    page.getByRole("heading", { name: "Welcome back." }),
  ).toBeVisible();
  await page.goto("/?plan=pro&interval=annual");
  await expect(page.getByLabel("Your name")).toBeVisible();
  await expect(page).toHaveURL(/plan=pro&interval=annual&mode=signup/);
});

test("signup preserves the selected plan through onboarding", async ({
  page,
}) => {
  const user = { id: 1, name: "Alex", email: "alex@example.com" };
  const workspace = {
    id: "test-workspace",
    name: "My workspace",
    role: "owner",
  };
  let created = false;
  await page.route("**/api/workspaces/", (route) => {
    if (route.request().method() === "POST") {
      created = true;
      return route.fulfill({ json: workspace });
    }
    return route.fulfill({ json: { results: created ? [workspace] : [] } });
  });
  await page.route("**/api/auth/signup/", (route) =>
    route.fulfill({ json: user }),
  );
  await page.route("**/api/growth/wizard/", (route) =>
    route.fulfill({
      json: { step: "payment", completed: [], finished: false },
    }),
  );
  await page.goto("/auth?mode=signup&plan=pro&interval=annual");
  await page.getByLabel("Your name").fill(user.name);
  await page.getByLabel("Email address").fill(user.email);
  await page
    .getByLabel("Password", { exact: true })
    .fill("Testing-password-2026");
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await expect(page).toHaveURL(/onboarding\/\?plan=pro&interval=annual/);
  await expect(
    page.getByRole("heading", { name: "Name your workspace" }),
  ).toBeVisible();
  await page.route("**/api/workspaces/test-workspace/", (route) =>
    route.fulfill({ json: workspace }),
  );
  await page.getByRole("button", { name: "Open my workspace" }).click();
  await expect(page).toHaveURL(/payments\/\?plan=pro&interval=annual/);
});

test("workspace navigation remains usable on desktop and mobile", async ({
  page,
}) => {
  const workspace = {
    id: "design-review",
    name: "Studio North",
    role: "owner",
    parent: null,
    branding: {
      brand_name: "Nemio",
      primary_color: "#347359",
      logo_url: "",
      hide_platform_branding: false,
    },
  };
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/auth/me/")
      return route.fulfill({
        json: { id: 1, name: "Alex Morgan", email: "alex@example.com" },
      });
    if (path === "/api/workspaces/")
      return route.fulfill({ json: { results: [workspace] } });
    if (path.includes("/announcements/")) return route.fulfill({ json: [] });
    if (path.includes("/analytics/funnel/"))
      return route.fulfill({
        json: { unique_leads: 0, steps: [], revenue_cents: 0 },
      });
    if (path.endsWith("/status/"))
      return route.fulfill({
        json: {
          checks: { database: true, cache: true, worker: true },
          pending_jobs: 0,
        },
      });
    if (path.endsWith("/members/"))
      return route.fulfill({
        json: {
          results: [
            {
              id: "m1",
              user_id: 1,
              name: "Alex Morgan",
              email: "alex@example.com",
              role: "owner",
            },
          ],
          count: 1,
        },
      });
    return route.fulfill({ json: { results: [], count: 0 } });
  });
  await page.goto("/w/design-review/overview");
  await expect(
    page.getByRole("heading", { name: "Your business at a glance, Alex." }),
  ).toBeVisible();
  await expect(page.locator(".welcome-banner")).toBeVisible();
  await page.screenshot({
    path: "test-results/nemio-workspace-desktop.png",
    fullPage: true,
  });
  await page.locator(".nav-tools > summary").click();
  await page
    .getByRole("navigation", { name: "Workspace navigation" })
    .getByRole("link", { name: "Team", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "Create invite" }),
  ).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: "test-results/nemio-workspace-mobile.png",
    fullPage: true,
  });
});

test("plans without an annual price cannot start annual checkout", async ({
  page,
}) => {
  await page.route("**/api/public/plans/", (route) =>
    route.fulfill({
      json: {
        ...catalog,
        plans: [{ ...catalog.plans[0], prices: [catalog.plans[0].prices[0]] }],
      },
    }),
  );
  await page.goto("/");
  await page.getByRole("button", { name: "Annual", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "Unavailable for this interval" }),
  ).toBeDisabled();
});

test("Instagram connection follows the API redirect and workspace Continue stays enabled", async ({
  page,
}) => {
  let connected = false;
  const workspace = {
    id: "onboarding-check",
    name: "My workspace",
    role: "owner",
  };
  await page.route("**/api/workspaces/", (route) =>
    route.fulfill({ json: { results: [workspace] } }),
  );
  await page.route("**/api/growth/wizard/", (route) =>
    route.fulfill({
      json: {
        step: connected ? "team" : "connect-instagram",
        completed: connected ? ["connect-instagram"] : [],
        finished: false,
      },
    }),
  );
  await page.route("**/meta/connect/", (route) =>
    route.fulfill({
      json: {
        authorization_url: "/api/meta/callback/?state=test-state",
        mode: "fake",
      },
    }),
  );
  await page.route("**/api/meta/callback/**", (route) => {
    connected = true;
    return route.fulfill({
      status: 302,
      headers: { location: "/onboarding/?connection=test-connected" },
    });
  });
  await page.route("**/api/workspaces/onboarding-check/", (route) =>
    route.fulfill({
      json: { ...workspace, ...route.request().postDataJSON() },
    }),
  );
  await page.goto("/onboarding/");
  await page.getByRole("button", { name: "Add Instagram account" }).click();
  await expect(
    page.getByRole("heading", { name: "Name your workspace" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Open my workspace", exact: true }),
  ).toBeEnabled();
  await page.getByLabel("Workspace name").fill("Connected Studio");
  await page
    .getByRole("button", { name: "Open my workspace", exact: true })
    .click();
  await expect(page).toHaveURL(/onboarding-check\/overview/);
});

test("Instagram immediate completion clears busy state for the workspace step", async ({
  page,
}) => {
  await page.route("**/api/workspaces/", (route) =>
    route.fulfill({
      json: {
        results: [
          { id: "onboarding-check", name: "My workspace", role: "owner" },
        ],
      },
    }),
  );
  await page.route("**/api/growth/wizard/", (route) =>
    route.fulfill({
      json: { step: "connect-instagram", completed: [], finished: false },
    }),
  );
  await page.route("**/meta/connect/", (route) =>
    route.fulfill({ json: { connected: true } }),
  );
  await page.goto("/onboarding/");
  await page.getByRole("button", { name: "Add Instagram account" }).click();
  await expect(
    page.getByRole("heading", { name: "Name your workspace" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Open my workspace", exact: true }),
  ).toBeEnabled();
});
