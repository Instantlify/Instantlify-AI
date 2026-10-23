import { test, expect } from "@playwright/test";
import { id, mockApi } from "./support/meta-mock";

/** Plans live in Settings > Subscription under AI credits, and choosing one opens
 * Stripe with that plan, instead of a portal with nothing to switch to. */

const limits = (messages: number, flags: boolean) => ({
  max_instagram_accounts: 3,
  max_contacts: null,
  team_seats: 5,
  max_ai_messages: messages,
  ai_agent_enabled: flags,
  integrations_unlocked: flags,
  content_scheduling_enabled: flags,
  voice_notes_enabled: false,
});
const plan = (slug: string, name: string, monthly: number, flags = true) => ({
  slug,
  name,
  is_featured: slug === "pro",
  limits: limits(monthly * 10, flags),
  prices: [
    { interval: "monthly", price_cents: monthly, configured: true },
    { interval: "annual", price_cents: monthly * 10, configured: true },
  ],
});

test("subscription tab lists the plans and opens Stripe for the chosen one", async ({
  page,
}) => {
  await mockApi(page);
  const p = `/api/workspaces/${id}`;
  let checkout: unknown;
  await page.route(`**${p}/billing/**`, (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === `${p}/billing/` && request.method() === "POST") {
      checkout = request.postDataJSON();
      return route.fulfill({
        status: 202,
        json: {
          id: "job-1",
          status: "complete",
          result: { url: "https://checkout.stripe.com/c/test" },
        },
      });
    }
    if (path === `${p}/billing/`)
      return route.fulfill({
        json: {
          plan: "pro",
          status: "active",
          interval: "monthly",
          trial_ends_at: null,
          used: 12,
          usage_limit: 1000,
          seat_limit: 5,
          channel_limit: 3,
          stripe_configured: true,
          trial_days: 0,
          period_start: new Date().toISOString(),
          plans: {},
          limits: limits(1000, true),
          catalog: [
            plan("free", "Free", 0, false),
            plan("starter", "Starter", 900, false),
            plan("pro", "Pro", 2500),
            plan("scale", "Scale", 9900),
          ],
        },
      });
    if (path === `${p}/billing/credits/`)
      return route.fulfill({
        json: {
          balance_cents: "1250",
          billing_mode: "platform",
          auto_topup_enabled: false,
          auto_topup_threshold_cents: 200,
          auto_topup_amount_cents: 1000,
          has_payment_method: false,
          stripe_configured: true,
          topup_options: [1000, 2500],
          transactions: [],
        },
      });
    return route.fallback();
  });
  await page.route("https://checkout.stripe.com/**", (route) =>
    route.fulfill({
      contentType: "text/html",
      body: "<h1>Stripe checkout</h1>",
    }),
  );

  await page.goto(`/w/${id}/settings?tab=subscription`);
  await expect(page.getByRole("heading", { name: "AI Credits" })).toBeVisible();
  const plans = page.locator("#plans");
  await expect(plans.getByRole("heading", { name: "Plans" })).toBeVisible();
  await expect(plans.getByRole("heading", { name: "Free" })).toHaveCount(0);
  await expect(
    plans.getByRole("button", { name: "Current plan" }),
  ).toBeDisabled();

  await page.getByRole("button", { name: "Upgrade Plan" }).click();
  await expect(plans).toBeInViewport();

  const scale = plans.locator("article").filter({ hasText: "Scale" });
  await scale.getByRole("button", { name: "Choose plan" }).click();
  await expect(page).toHaveURL("https://checkout.stripe.com/c/test");
  expect(checkout).toEqual({
    kind: "checkout",
    plan: "scale",
    interval: "monthly",
  });
});

test("payments no longer carries the plan and points to the subscription tab", async ({
  page,
}) => {
  await mockApi(page);
  await page.goto(`/w/${id}/payments`);
  await expect(page.getByText("Your plan", { exact: true })).toHaveCount(0);
  await expect(
    page.getByRole("link", { name: "Settings → Subscription" }),
  ).toHaveAttribute("href", /\/settings\/?\?tab=subscription$/);
});
