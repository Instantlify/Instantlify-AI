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
    "Every conversation.",
  );
  // Keep the overview concise; the full catalogue remains accessible in the tour.
  await expect(page.locator("main > section")).toHaveCount(7);
  await expect(page.locator(".nm-demo")).toHaveCount(1);
  await expect(
    page.getByRole("link", { name: "Explore the product", exact: true }),
  ).toHaveAttribute("href", /^\/features\/?$/);
  await expect(page.locator(".plan-price")).toContainText("$49");
  await page.getByRole("button", { name: "Annual", exact: true }).click();
  await expect(page.locator(".plan-price")).toContainText("$490");
  await expect(page.locator(".plan-trial")).toHaveText("10-day free trial");
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: "instant" }));
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
  await page
    .getByText("Which channels can I connect?", { exact: true })
    .click();
  await expect(page.locator(".nm-faq details[open]")).toHaveCount(1);
  await expect(page.getByText(/No. Build automations visually/)).toBeHidden();
  await expect(page.locator(".nm-faq details[open] summary")).toContainText(
    "Which channels can I connect?",
  );
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: "instant" }));
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

test("homepage motion can be paused and respects reduced motion", async ({
  page,
}) => {
  await page.goto("/");
  const root = page.locator(".nm-home");
  await expect(root).toHaveAttribute("data-motion", "running");
  await expect(page.locator(".nm-benefit-visual")).toHaveCount(3);
  await page
    .getByRole("button", { name: "Pause animations", exact: true })
    .click();
  await expect(root).toHaveAttribute("data-motion", "paused");
  await page
    .getByRole("button", { name: "Play animations", exact: true })
    .click();
  await expect(root).toHaveAttribute("data-motion", "running");
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect(root).toHaveAttribute("data-motion", "paused");
  await expect(page.getByText("Reduced motion", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { level: 1 })).toBeVisible();
  const animated = await root.evaluate(
    (element) =>
      element
        .getAnimations({ subtree: true })
        .filter((animation) => animation.playState === "running").length,
  );
  expect(animated).toBe(0);
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

test("conversation previews advance and switch without sending messages", async ({
  page,
}) => {
  await page.goto("/");
  const demo = page.locator("#interactive-demo .nm-demo");
  await demo.getByRole("button", { name: "Simulate customer reply" }).click();
  await expect(
    demo.getByText("Following up with people interested in my services."),
  ).toBeVisible();
  await demo.getByRole("button", { name: "Run the next step" }).click();
  await expect(
    demo.getByText("Resource delivered · Interest tagged"),
  ).toBeVisible();
  await page.getByRole("button", { name: /AI qualification/ }).click();
  await expect(
    demo.getByText("Can you help our team automate sales enquiries?"),
  ).toBeVisible();
  await expect(
    demo.getByRole("button", { name: "Simulate customer reply" }),
  ).toBeVisible();
  await expect(
    demo.getByText("Resource delivered · Interest tagged"),
  ).toHaveCount(0);
});

test("integration search combines with category and handles empty results", async ({
  page,
}) => {
  await page.goto("/features");
  const directory = page.locator("#integrations");
  await directory.getByRole("button", { name: "CRM", exact: true }).click();
  await expect(directory.locator("article")).toHaveCount(4);
  await page
    .getByRole("searchbox", { name: "Search integrations" })
    .fill("notion");
  await expect(directory.locator("article")).toHaveCount(1);
  await expect(
    directory.getByRole("heading", { name: "Notion" }),
  ).toBeVisible();
  await page
    .getByRole("searchbox", { name: "Search integrations" })
    .fill("no-such-tool");
  await expect(directory.getByText(/No matching integrations/)).toBeVisible();
  await page.getByRole("searchbox", { name: "Search integrations" }).fill("");
  await directory.getByRole("button", { name: "All", exact: true }).click();
  await expect(directory.locator("article")).toHaveCount(17);
});

test("mobile menu, audience examples and planned features are clear", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/features");
  await page.getByRole("button", { name: "Open navigation" }).click();
  await expect(
    page
      .getByRole("navigation", { name: "Main navigation" })
      .getByRole("link", { name: "Integrations" }),
  ).toBeVisible();
  await page
    .getByRole("navigation", { name: "Main navigation" })
    .getByRole("link", { name: "Integrations" })
    .click();
  await expect(
    page.getByRole("button", { name: "Open navigation" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Agencies", exact: true }).click();
  await expect(
    page.getByRole("heading", {
      name: "A workspace for every client relationship.",
    }),
  ).toBeVisible();
  const moderation = page
    .locator("#toolkit article")
    .filter({ hasText: "Comment moderation" });
  await expect(moderation.getByText("Planned", { exact: true })).toBeVisible();
  await expect(moderation.getByRole("link")).toHaveCount(0);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
});

test("detailed channel previews, builder and agent controls work", async ({
  page,
}) => {
  await page.goto("/features");
  const channels = page.getByRole("group", { name: "Channel details" });
  await channels.getByRole("button", { name: "WhatsApp", exact: true }).click();
  await expect(
    page.getByRole("heading", {
      name: "Keep the conversation close to your customer.",
    }),
  ).toBeVisible();
  await channels.getByRole("button", { name: "Telegram", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "A helpful assistant behind your bot." }),
  ).toBeVisible();
  const builder = page.locator("#flow-builder");
  await builder.getByRole("button", { name: "Run example flow" }).click();
  await expect(builder.locator(".nd-node.ran")).toHaveCount(1);
  for (let i = 0; i < 3; i++)
    await builder.getByRole("button", { name: "Continue example" }).click();
  await expect(builder.getByText("Example workflow complete")).toBeVisible();
  await builder.getByRole("button", { name: "Reset example" }).click();
  await expect(builder.locator(".nd-node.ran")).toHaveCount(0);
  await page
    .getByRole("group", { name: "Agent preview" })
    .getByRole("button", { name: "Actions", exact: true })
    .click();
  await expect(
    page.locator("#ai-agents").getByText("Check availability", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("group", { name: "Agent preview" })
    .getByRole("button", { name: "Oversight", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Your team decides where AI helps." }),
  ).toBeVisible();
});

test("feature catalogue filters current and planned capabilities", async ({
  page,
}) => {
  await page.goto("/features");
  const catalogue = page.locator("#feature-catalog");
  expect(await catalogue.locator("article").count()).toBeGreaterThan(50);
  await catalogue.getByRole("button", { name: "Roadmap", exact: true }).click();
  await expect(catalogue.locator("article")).toHaveCount(9);
  await expect(catalogue.locator(".nm-planned")).toHaveCount(9);
  await catalogue
    .getByRole("button", { name: "All features", exact: true })
    .click();
  await page
    .getByRole("searchbox", { name: "Search product features" })
    .fill("cooldown");
  await expect(catalogue.locator("article")).toHaveCount(1);
  await expect(
    catalogue.getByRole("heading", { name: "Lead cooldowns" }),
  ).toBeVisible();
  await page
    .getByRole("searchbox", { name: "Search product features" })
    .fill("not-a-feature");
  await expect(catalogue.getByText(/No matching features/)).toBeVisible();
});

test("inbox preview keeps contact details together and voice visual is labelled", async ({
  page,
}) => {
  await page.goto("/features");
  const inbox = page.locator("#inbox-crm");
  await inbox.getByRole("button", { name: /Alex Kim/ }).click();
  await expect(inbox.getByRole("heading", { name: "Alex Kim" })).toBeVisible();
  await expect(
    inbox.getByText("Confirm the appointment", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Preview voice-message visual" })
    .click();
  await expect(page.locator(".nd-wave.playing")).toBeVisible();
  await expect(
    page.getByText("This visual preview does not play or generate audio."),
  ).toBeVisible();
  await page.getByRole("button", { name: "Stop waveform preview" }).click();
  await expect(page.locator(".nd-wave.playing")).toHaveCount(0);
});

test("rich product menu works on mobile without overflowing", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page.locator(".nm-mega > summary").click();
  await expect(page.locator(".nd-mega-menu a")).toHaveCount(12);
  await page
    .locator(".nd-mega-menu")
    .getByRole("link", { name: /Flow builder/ })
    .click();
  await expect(page).toHaveURL(/features\/#flow-builder$/);
  await expect(
    page.getByRole("button", { name: "Open navigation" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
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
  let signedIn = false;
  await page.route("**/api/auth/signup/", (route) => {
    signedIn = true;
    return route.fulfill({ json: user });
  });
  await page.route("**/api/auth/me/", (route) =>
    signedIn
      ? route.fulfill({ json: user })
      : route.fulfill({ status: 401, json: { detail: "Sign in required" } }),
  );
  await page.route("**/api/growth/wizard/", (route) =>
    route.fulfill({
      json: { step: "workspace", completed: [], finished: false },
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
  let checkout: unknown;
  await page.route("**/api/growth/funnel/", (route) =>
    route.fulfill({ json: { recorded: true } }),
  );
  await page.route("**/api/workspaces/test-workspace/billing/**", (route) => {
    if (route.request().method() === "POST") {
      checkout = route.request().postDataJSON();
      return route.fulfill({
        status: 202,
        json: {
          id: "job-1",
          status: "complete",
          result: { url: "https://checkout.stripe.com/c/onboarding" },
        },
      });
    }
    return route.fulfill({
      json: {
        plan: "free",
        stripe_configured: true,
        trial_days: 7,
        catalog: [
          {
            slug: "free",
            name: "Free",
            is_featured: false,
            prices: [],
            limits: {
              max_instagram_accounts: 1,
              max_contacts: 500,
              team_seats: 1,
              max_ai_messages: 100,
              ai_agent_enabled: false,
              integrations_unlocked: false,
              content_scheduling_enabled: false,
              voice_notes_enabled: false,
            },
          },
          {
            slug: "pro",
            name: "Pro",
            is_featured: true,
            limits: {
              max_instagram_accounts: 1,
              max_contacts: 500,
              team_seats: 1,
              max_ai_messages: 100,
              ai_agent_enabled: false,
              integrations_unlocked: false,
              content_scheduling_enabled: false,
              voice_notes_enabled: false,
            },
            prices: [
              { interval: "monthly", price_cents: 2500, configured: true },
              { interval: "annual", price_cents: 24000, configured: true },
            ],
          },
        ],
      },
    });
  });
  await page.route("https://checkout.stripe.com/**", (route) =>
    route.fulfill({ contentType: "text/html", body: "<h1>Stripe</h1>" }),
  );
  await page.getByRole("button", { name: "Continue to plans" }).click();
  await expect(
    page.getByRole("heading", { name: "Choose a plan" }),
  ).toBeVisible();
  await expect(
    page.getByText("You picked Pro on the pricing page."),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Annual" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await page.getByRole("button", { name: "Choose plan" }).click();
  await expect(page).toHaveURL("https://checkout.stripe.com/c/onboarding");
  expect(checkout).toEqual({
    kind: "checkout",
    plan: "pro",
    interval: "annual",
    return_to: "onboarding",
  });
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
    pinned_apps: ["bio", "calendar"],
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
    if (path.endsWith("/telemetry/"))
      return route.fulfill({
        json: {
          since: "2026-10-08",
          days: [],
          totals: { inbound: 0, contacts: 0, conversations: 0, ai_rate: null },
          channels: [],
        },
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
    page.getByRole("heading", { name: "Your Statistics" }),
  ).toBeVisible();
  // No channel is connected yet, so the overview asks for one.
  await expect(page.getByText("Connect your Instagram account")).toBeVisible();
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
    parent: null,
    branding: { brand_name: "Nemio", primary_color: "", logo_url: "" },
    pinned_apps: [],
  };
  await page.route("**/api/workspaces/", (route) =>
    route.fulfill({ json: { results: [workspace] } }),
  );
  // The workspace shell loads the signed-in user; without it the page returns to sign-in.
  await page.route("**/api/auth/me/", (route) =>
    route.fulfill({
      json: {
        id: 1,
        name: "Alex",
        email: "alex@example.com",
        email_verified: true,
      },
    }),
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
    page.getByRole("button", { name: "Continue to plans", exact: true }),
  ).toBeEnabled();
  await page.getByLabel("Workspace name").fill("Connected Studio");
  await page
    .getByRole("button", { name: "Continue to plans", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "Choose a plan" }),
  ).toBeVisible();
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
    page.getByRole("button", { name: "Continue to plans", exact: true }),
  ).toBeEnabled();
});
