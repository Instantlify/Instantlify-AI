import { test, expect, type Page } from "@playwright/test";

const HOUR = 3_600_000;

async function sessionServer(page: Page) {
  const start = new Date("2026-11-12T08:00:00Z").getTime();
  await page.clock.install({ time: start });
  const state = { now: start, expiresAt: start + HOUR, reads: 0, renewals: 0 };
  await page.context().route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/auth/session/") {
      if (route.request().method() === "POST") {
        if (state.now >= state.expiresAt)
          return route.fulfill({ status: 403, json: {} });
        state.renewals++;
        state.expiresAt =
          state.now + HOUR - route.request().postDataJSON().inactive_for * 1000;
      } else state.reads++;
      return route.fulfill({
        json: {
          authenticated: state.now < state.expiresAt,
          idle_timeout: HOUR / 1000,
          remaining: Math.max(0, (state.expiresAt - state.now) / 1000),
        },
      });
    }
    if (path === "/api/auth/me/")
      return route.fulfill({
        status: 401,
        json: { detail: "Sign in required" },
      });
    if (path === "/api/auth/csrf/")
      return route.fulfill({ json: { csrfToken: "test-csrf" } });
    return route.fulfill({ json: {} });
  });
  await page.goto("/help/");
  await expect.poll(() => state.reads).toBeGreaterThan(0);
  return state;
}

test("an unattended page signs out after one hour even while APIs poll", async ({
  page,
}) => {
  const state = await sessionServer(page);
  await page.evaluate(async () => {
    for (let n = 0; n < 3; n++) await fetch("/api/auth/me/");
  });
  expect(state.renewals).toBe(0);
  state.now += HOUR + 1;
  await page.clock.fastForward(HOUR + 1);
  await expect(page).toHaveURL(/\/auth\/\?session=expired$/);
  await expect(page.getByRole("status")).toContainText("1 hour of inactivity");
  expect(state.renewals).toBe(0);
});

test("manual sign-out reaches the landing page and allows signing in again", async ({
  page,
}) => {
  const state = await sessionServer(page);
  const id = "11111111-1111-4111-8111-111111111111";
  const user = { id: 1, name: "Alex", email: "alex@example.com" };
  const workspace = {
    id,
    name: "Studio",
    role: "owner",
    checkout_pending: false,
    branding: { brand_name: "Instantlify" },
  };
  await page.route("**/api/auth/me/", (route) =>
    state.now < state.expiresAt
      ? route.fulfill({ json: user })
      : route.fulfill({ status: 401, json: { detail: "Sign in required" } }),
  );
  await page.route("**/api/workspaces/", (route) =>
    route.fulfill({ json: { results: [workspace] } }),
  );
  await page.route(`**/api/workspaces/${id}/`, (route) =>
    route.fulfill({ json: workspace }),
  );
  await page.route(`**/api/workspaces/${id}/connections/`, (route) =>
    route.fulfill({ json: { results: [] } }),
  );
  await page.route(`**/api/workspaces/${id}/telemetry/`, (route) =>
    route.fulfill({
      json: {
        totals: { inbound: 0, contacts: 0, conversations: 0, ai_rate: null },
        channels: [],
        days: [],
      },
    }),
  );
  await page.route(`**/api/workspaces/${id}/analytics/funnel/**`, (route) =>
    route.fulfill({ json: { steps: [], unique_leads: 0 } }),
  );
  await page.route("**/api/growth/announcements/**", (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route("**/api/public/plans/", (route) =>
    route.fulfill({ json: { plans: [], trial_days: 0 } }),
  );
  await page.route("**/api/auth/logout/", (route) => {
    state.expiresAt = state.now;
    return route.fulfill({ status: 204 });
  });
  await page.goto(`/w/${id}/overview/`);
  await expect.poll(() => state.reads).toBeGreaterThan(1);
  await page.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(page).toHaveURL(/^https?:\/\/[^/]+\/$/);
  await page
    .getByRole("link", { name: "Sign in", exact: true })
    .first()
    .click();
  await expect(
    page.getByRole("heading", { name: "Welcome back." }),
  ).toBeVisible();
  await expect(page).not.toHaveURL(/session=expired/);
});

test("activity in one tab extends the shared session for other tabs", async ({
  page,
}) => {
  const state = await sessionServer(page);
  const other = await page.context().newPage();
  await other.goto("/help/");
  await expect.poll(() => state.reads).toBe(2);
  await page.bringToFront();
  state.now += 50 * 60_000;
  await page.clock.fastForward(50 * 60_000);
  await page.keyboard.press("ArrowDown");
  await expect.poll(() => state.renewals).toBe(1);
  state.now += 11 * 60_000;
  await page.clock.fastForward(11 * 60_000);
  await expect(page).toHaveURL(/\/help\/$/);
  await expect(other).toHaveURL(/\/help\/$/);
  state.now += 49 * 60_000 + 1;
  await page.clock.fastForward(49 * 60_000 + 1);
  await expect(page).toHaveURL(/\/auth\/\?session=expired$/);
  await expect(other).toHaveURL(/\/auth\/\?session=expired$/);
});

test("user interaction extends the hour and expiry follows the last interaction", async ({
  page,
}) => {
  const state = await sessionServer(page);
  state.now += 59 * 60_000;
  await page.clock.fastForward(59 * 60_000);
  await page.keyboard.press("ArrowDown");
  await expect.poll(() => state.renewals).toBe(1);
  state.now += 2 * 60_000;
  await page.clock.fastForward(2 * 60_000);
  await expect(page).toHaveURL(/\/help\/$/);
  state.now += 58 * 60_000 + 1;
  await page.clock.fastForward(58 * 60_000 + 1);
  await expect(page).toHaveURL(/\/auth\/\?session=expired$/);
});

test("background focus checks do not renew and bursts of activity are throttled", async ({
  page,
}) => {
  const state = await sessionServer(page);
  await page.evaluate(() =>
    document.dispatchEvent(new Event("visibilitychange")),
  );
  await expect.poll(() => state.reads).toBeGreaterThan(1);
  expect(state.renewals).toBe(0);
  await page.keyboard.press("ArrowDown");
  await expect.poll(() => state.renewals).toBe(1);
  state.now += 5_000;
  await page.clock.fastForward(5_000);
  await page.keyboard.press("ArrowDown");
  await page.keyboard.press("ArrowUp");
  expect(state.renewals).toBe(1);
  state.now += 25_000;
  await page.clock.fastForward(25_000);
  await expect.poll(() => state.renewals).toBe(2);
  expect(Math.abs(state.expiresAt - (state.now + HOUR - 25_000))).toBeLessThan(
    1000,
  );
});
