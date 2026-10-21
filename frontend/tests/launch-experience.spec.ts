import { test, expect } from "@playwright/test";

const id = "11111111-1111-4111-8111-111111111111";
const workspace = {
  id,
  name: "Test Studio",
  role: "owner",
  parent: null,
  branding: {
    brand_name: "Nemio",
    primary_color: "#347359",
    logo_url: "",
    support_email: "",
    hide_platform_branding: false,
  },
  pinned_apps: ["bio", "calendar"],
};
const telemetry = {
  since: "2026-10-08",
  days: [],
  totals: { inbound: 0, contacts: 0, conversations: 0, ai_rate: null },
  channels: [],
};

test.beforeEach(async ({ page }) => {
  await page.route("**/api/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/auth/me/")
      return route.fulfill({
        json: {
          id: 1,
          name: "Alex",
          email: "alex@example.com",
          email_verified: true,
        },
      });
    if (path === "/api/workspaces/")
      return route.fulfill({ json: { results: [workspace], count: 1 } });
    if (path === `/api/workspaces/${id}/`)
      return route.fulfill({ json: workspace });
    if (path.endsWith("/csrf/"))
      return route.fulfill({ json: { csrfToken: "test" } });
    if (path.endsWith("/wizard/"))
      return route.fulfill({
        json: { step: "connect-instagram", completed: [], finished: false },
      });
    if (path.includes("/announcements/") || path.endsWith("/automation-runs/"))
      return route.fulfill({ json: [] });
    if (path.endsWith("/agent-audit/"))
      return route.fulfill({ json: { runs: [], tools: [], usage: [] } });
    if (path.endsWith("/agent/")) return route.fulfill({ json: {} });
    if (path.endsWith("/telemetry/")) return route.fulfill({ json: telemetry });
    if (path.endsWith("/automations/stats/"))
      return route.fulfill({ json: {} });
    if (path.includes("/analytics/funnel/"))
      return route.fulfill({
        json: {
          unique_leads: 1,
          steps: [
            { kind: "comment", leads: 1 },
            { kind: "dm", leads: 1 },
          ],
          automations: [],
          channels: [],
          revenue_cents: 0,
        },
      });
    return route.fulfill({ json: { results: [], count: 0 } });
  });
});

test("short onboarding skips optional setup and shows unique leads", async ({
  page,
}) => {
  const completed: string[] = [];
  await page.route("**/api/growth/funnel/", (route) => {
    const data = route.request().postDataJSON();
    if (data.status === "skipped") completed.push(data.step);
    return route.fulfill({ json: { recorded: true } });
  });
  await page.goto("/onboarding");
  await page
    .getByRole("button", { name: "I’ll connect my account later" })
    .click();
  await page.getByLabel("Workspace name").fill("Test Studio");
  await page.getByRole("button", { name: "Open my workspace" }).click();
  await expect(page).toHaveURL(new RegExp(`/w/${id}/overview`));
  expect(completed).toEqual(
    expect.arrayContaining(["team", "integrations", "payment"]),
  );
  await expect(
    page
      .locator(".stat-card")
      .filter({ hasText: "Leads this week" })
      .locator("strong"),
  ).toContainText("1");
  await expect(
    page.getByRole("link", { name: "Integrations", exact: true }),
  ).not.toBeVisible();
  await page.locator(".nav-tools > summary").click();
  await expect(
    page.getByRole("link", { name: "Integrations", exact: true }),
  ).toBeVisible();
});

test("password recovery handles email request and token confirmation", async ({
  page,
}) => {
  await page.route("**/api/auth/password-reset/", (route) =>
    route.fulfill({
      json: {
        detail:
          "If this email has an eligible account, a reset link is on its way.",
      },
    }),
  );
  await page.goto("/auth/reset/");
  await page.getByLabel("Email address").fill("alex@example.com");
  await page.getByRole("button", { name: "Send reset link" }).click();
  await expect(page.getByRole("status")).toContainText(
    "a reset link is on its way",
  );
  await page.goto("/auth/reset/#uid=MQ&token=example");
  await expect(page.getByLabel("New password", { exact: true })).toBeVisible();
  await expect(page).not.toHaveURL(/token=/);
  await page
    .getByLabel("New password", { exact: true })
    .fill("River-saffron-cloud42");
  await page.getByLabel("Confirm password").fill("Different-river-cloud42");
  await page.getByRole("button", { name: "Save new password" }).click();
  await expect(
    page.getByRole("alert").filter({ hasText: "Passwords do not match" }),
  ).toContainText("Passwords do not match");
  await page.getByLabel("Confirm password").fill("River-saffron-cloud42");
  await page.route("**/api/auth/password-reset/confirm/", (route) => {
    expect(route.request().postDataJSON().token).toBe("example");
    return route.fulfill({
      json: { detail: "Password updated. Sign in with your new password." },
    });
  });
  await page.getByRole("button", { name: "Save new password" }).click();
  await expect(page.getByRole("status")).toContainText("Password updated");
});

test("starter creates a reviewable booking draft without publishing", async ({
  page,
}) => {
  let payload: {
    draft: { nodes: { data: { buttons?: { url: string }[] } }[] };
  } | null = null;
  await page.route(`**/api/workspaces/${id}/automations/`, (route) => {
    if (route.request().method() !== "POST")
      return route.fulfill({ json: { results: [], count: 0 } });
    payload = route.request().postDataJSON();
    return route.fulfill({ json: { id: "new-draft" } });
  });
  await page.goto(`/w/${id}/automations`);
  await page.getByLabel("What should happen first?").selectOption("booking");
  await page
    .getByLabel("Your reply", { exact: true })
    .fill("Choose a time for your consultation.");
  await page.getByLabel("Booking page").fill("https://example.com/book");
  await page.getByRole("button", { name: "Create starter draft" }).click();
  await expect(page).toHaveURL(/automations\/new-draft/, { timeout: 15000 });
  expect(payload).toMatchObject({
    draft: {
      triggers: [{ keyword: "book", kind: "comment" }],
      nodes: [
        {
          id: "welcome",
          data: {
            kind: "send_buttons",
            buttons: [{ url: "https://example.com/book" }],
          },
        },
        { id: "done" },
      ],
    },
  });
});

test("preview presents an answer and knowledge without enabling the agent", async ({
  page,
}) => {
  await page.route(`**/api/workspaces/${id}/agent/preview/`, (route) =>
    route.fulfill({
      json: {
        answer: "Consultations cost $49.",
        handoff: false,
        sources: ["Services FAQ"],
        is_test: false,
      },
    }),
  );
  await page.goto(`/w/${id}/agent`);
  await page.getByRole("button", { name: "Preview answer" }).click();
  await expect(page.getByRole("status")).toContainText(
    "Consultations cost $49.",
  );
  await expect(
    page.getByText("Knowledge supplied: Services FAQ"),
  ).toBeVisible();
  await expect(page.getByLabel("Agent enabled")).not.toBeChecked();
});

test("mobile workspace tools stay inside the viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/w/${id}/automations`);
  // On phones the sidebar is an off-canvas drawer opened from the top bar.
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page.locator(".nav-tools > summary").click();
  await expect(
    page.getByRole("link", { name: "Integrations", exact: true }),
  ).toBeVisible();
  await page.getByRole("link", { name: "Integrations", exact: true }).click();
  await expect(page.locator(".sidebar")).not.toHaveClass(/open/);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: "test-results/launch-mobile.png",
    fullPage: true,
  });
});
