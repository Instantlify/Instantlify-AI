import { test, expect, type Page } from "@playwright/test";

/** Meta client surfaces against a mocked API: account switcher, app dock, overview
 * telemetry, automations hub, unified inbox, CRM pipeline and app store. */

const id = "22222222-2222-4222-8222-222222222222";
const now = Date.now();
const iso = (offsetMs: number) => new Date(now + offsetMs).toISOString();
const workspace = {
  id,
  name: "Studio North",
  role: "owner",
  parent: null,
  created_at: iso(-90 * 864e5),
  branding: {
    brand_name: "Nemio",
    primary_color: "#347359",
    logo_url: "",
    support_email: "",
    hide_platform_branding: false,
  },
  pinned_apps: ["bio", "calendar"],
};
const connections = [
  {
    id: "c-ig",
    provider: "instagram",
    display_name: "studio.north",
    expires_at: iso(40 * 864e5),
    is_test: false,
    status: "active",
    locked: false,
    followers: 12400,
    last_refreshed_at: null,
  },
  {
    id: "c-fb",
    provider: "messenger",
    display_name: "Studio North Page",
    expires_at: iso(3 * 864e5),
    is_test: false,
    status: "active",
    locked: false,
    followers: null,
    last_refreshed_at: null,
  },
  {
    id: "c-wa",
    provider: "whatsapp",
    display_name: "+1 555 0100",
    expires_at: iso(300 * 864e5),
    is_test: false,
    status: "active",
    locked: false,
    followers: null,
    last_refreshed_at: null,
  },
];
const days = Array.from({ length: 14 }, (_, index) => ({
  date: new Date(now - (13 - index) * 864e5).toISOString().slice(0, 10),
  instagram: 4 + (index % 5),
  messenger: index % 3,
  whatsapp: 2 + (index % 4),
  other: 0,
  contacts: 1 + (index % 3),
}));
const lead = (n: number, stage: string, channel: string) => ({
  id: `l-${n}`,
  name: ["Maya Chen", "Omar Haddad", "Lena Fischer", "Diego Ruiz"][n],
  email: n % 2 ? "" : `lead${n}@example.com`,
  stage,
  tags: n === 0 ? ["hot"] : [],
  fields: {},
  opted_out: false,
  channels: [channel],
  conversation_id: `v-${n}`,
  assigned_to: n === 1 ? 1 : null,
  message_count: 3 + n,
  created_at: iso(-n * 864e5),
});
const leads = [
  lead(0, "new", "instagram"),
  lead(1, "qualified", "whatsapp"),
  lead(2, "booked", "messenger"),
  lead(3, "new", "instagram"),
];
const conversation = (n: number, provider: string, inboundAgoMs: number) => ({
  id: `v-${n}`,
  lead: leads[n],
  provider,
  is_test: false,
  assigned_to: null,
  status: "open",
  ai_enabled: n === 0,
  last_inbound_at: iso(-inboundAgoMs),
  last_outbound_at: iso(-inboundAgoMs + 60000),
  updated_at: iso(-inboundAgoMs),
  connection_id: connections.find((c) => c.provider === provider)!.id,
  connection_name: connections.find((c) => c.provider === provider)!
    .display_name,
  contact_link: provider === "whatsapp" ? "https://wa.me/15550100" : "",
  last_message: {
    text: "Is the guide still available?",
    kind: "dm",
    direction: "inbound",
    created_at: iso(-inboundAgoMs),
  },
});
const conversations = [
  conversation(0, "instagram", 2 * 3600e3),
  conversation(1, "whatsapp", 23.5 * 3600e3),
  conversation(2, "messenger", 30 * 3600e3),
];
const messages = [
  {
    id: "m1",
    direction: "inbound",
    text: "SEND",
    kind: "comment",
    created_at: iso(-3 * 3600e3),
    delivery_status: null,
    sender: "customer",
    author_name: "",
  },
  {
    id: "m2",
    direction: "outbound",
    text: "Thanks! Reply with your email for the guide.",
    kind: "text",
    created_at: iso(-3 * 3600e3 + 5000),
    delivery_status: "sent",
    sender: "automation",
    author_name: "",
  },
  {
    id: "m3",
    direction: "outbound",
    text: "Happy to help with sizing too!",
    kind: "text",
    created_at: iso(-2.5 * 3600e3),
    delivery_status: "sent",
    sender: "ai",
    author_name: "",
  },
  {
    id: "m4",
    direction: "outbound",
    text: "I've added a discount code for you.",
    kind: "text",
    created_at: iso(-2.2 * 3600e3),
    delivery_status: "sent",
    sender: "human",
    author_name: "Alex Morgan",
  },
];
const automations = [
  {
    id: "a-1",
    name: "Comment → lead magnet",
    draft: {},
    published: {
      start: "a",
      triggers: [{ kind: "comment", keyword: "SEND", channel: "instagram" }],
    },
    revision: 2,
    enabled: true,
    updated_at: iso(-864e5),
    created_at: iso(-20 * 864e5),
    installed_from: null,
    folder: "Instagram comment leads",
  },
  {
    id: "a-2",
    name: "WhatsApp greeting",
    draft: { triggers: [{ kind: "dm", keyword: "hi", channel: "whatsapp" }] },
    published: {},
    revision: 0,
    enabled: false,
    updated_at: iso(-2 * 864e5),
    created_at: iso(-5 * 864e5),
    installed_from: null,
    folder: "",
  },
];

async function mockApi(page: Page) {
  const patches: { path: string; body: unknown }[] = [];
  await page.route("**/api/**", (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const p = `/api/workspaces/${id}`;
    if (request.method() !== "GET") {
      patches.push({ path, body: request.postDataJSON() });
      if (path.endsWith("/csrf/"))
        return route.fulfill({ json: { csrfToken: "t" } });
      if (path === `${p}/`) {
        Object.assign(workspace, request.postDataJSON());
        return route.fulfill({ json: workspace });
      }
      if (path.endsWith("/leads/bulk/"))
        return route.fulfill({ json: { updated: 2 } });
      return route.fulfill({ json: {} });
    }
    if (path.endsWith("/csrf/"))
      return route.fulfill({ json: { csrfToken: "t" } });
    if (path === "/api/auth/me/")
      return route.fulfill({
        json: {
          id: 1,
          name: "Alex Morgan",
          email: "alex@example.com",
          email_verified: true,
        },
      });
    if (path === "/api/workspaces/")
      return route.fulfill({ json: { results: [workspace], count: 1 } });
    if (path === `${p}/billing/`)
      return route.fulfill({
        json: {
          plan: "pro",
          status: "active",
          catalog: [{ slug: "pro", name: "Pro" }],
        },
      });
    if (path === `${p}/connections/`)
      return route.fulfill({ json: { results: connections, count: 3 } });
    if (path === `${p}/telemetry/`)
      return route.fulfill({
        json: {
          since: days[0].date,
          days,
          totals: {
            inbound: 120,
            contacts: 28,
            conversations: 40,
            ai_rate: 0.62,
          },
          channels: [
            {
              provider: "instagram",
              inbound: 80,
              conversations: 25,
              median_response_minutes: 3.4,
              top_automation: { name: "Comment → lead magnet", runs: 41 },
            },
            {
              provider: "whatsapp",
              inbound: 40,
              conversations: 15,
              median_response_minutes: 75,
              top_automation: null,
            },
          ],
        },
      });
    if (path.includes("/analytics/funnel/"))
      return route.fulfill({
        json: {
          unique_leads: 9,
          steps: [],
          automations: [],
          channels: [],
          revenue_cents: 0,
        },
      });
    if (path === `${p}/status/`)
      return route.fulfill({
        json: { checks: { database: true }, pending_jobs: 0 },
      });
    if (path === `${p}/automations/`)
      return route.fulfill({ json: { results: automations, count: 2 } });
    if (path === `${p}/automations/stats/`)
      return route.fulfill({ json: { "a-1": { runs: 41, reach: 37 } } });
    if (path === `${p}/conversations/`)
      return route.fulfill({ json: { results: conversations, count: 3 } });
    if (path.endsWith("/messages/"))
      return route.fulfill({
        json: { results: [...messages].reverse(), count: 4 },
      });
    if (path.endsWith("/events/"))
      return route.fulfill({
        json: [
          {
            id: 1,
            kind: "triggered",
            automation_name: "Comment → lead magnet",
            amount_cents: 0,
            created_at: iso(-3 * 3600e3 + 1000),
          },
        ],
      });
    if (path.endsWith("/notes/")) return route.fulfill({ json: [] });
    if (path === `${p}/leads/`)
      return route.fulfill({ json: { results: leads, count: 4, next: null } });
    if (path.endsWith("/members/"))
      return route.fulfill({
        json: {
          results: [
            {
              id: "m",
              user_id: 1,
              name: "Alex Morgan",
              email: "alex@example.com",
              role: "owner",
            },
          ],
          count: 1,
        },
      });
    if (path.includes("/announcements/") || path.endsWith("/automation-runs/"))
      return route.fulfill({ json: [] });
    return route.fulfill({ json: { results: [], count: 0 } });
  });
  return patches;
}

test.beforeEach(async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
});

test("account switcher lists Meta accounts with token health and scopes the inbox", async ({
  page,
}) => {
  await mockApi(page);
  await page.goto(`/w/${id}/overview`);
  await expect(page.locator(".channel-ribbon")).toContainText(
    "Instagram: Connected (studio.north)",
  );
  await expect(page.locator(".channel-ribbon")).toContainText("1 Page");
  await expect(page.locator(".channel-ribbon")).toContainText("1 number");
  await expect(page.locator(".telemetry-card").first()).toContainText("120");
  await expect(page.locator(".channel-matrix")).toContainText("3 min");
  await expect(page.locator(".tier-badge")).toHaveText("Pro");
  await page.screenshot({
    path: "test-results/meta-overview.png",
    fullPage: true,
  });

  await page.getByRole("button", { name: /CHANNEL ACCOUNT/ }).click();
  const menu = page.locator("#account-menu");
  await expect(menu).toContainText("12.4K followers");
  await expect(menu).toContainText("Expiring soon");
  await page.screenshot({ path: "test-results/meta-switcher.png" });
  await menu.getByRole("button", { name: /\+1 555 0100/ }).click();
  await expect(page.locator(".account-trigger")).toContainText("+1 555 0100");

  const requested = page.waitForRequest((request) =>
    request.url().includes("connection=c-wa"),
  );
  await page
    .getByRole("navigation", { name: "Workspace navigation" })
    .getByRole("link", { name: "Inbox", exact: true })
    .click();
  await requested;
  await expect(page.locator(".account-chip")).toBeVisible();
});

test("inbox shows channel tabs, window countdown and distinct bubbles", async ({
  page,
}) => {
  await mockApi(page);
  await page.goto(`/w/${id}/inbox`);
  await expect(page.getByRole("tab", { name: /WhatsApp/ })).toBeVisible();
  await expect(page.locator(".window-chip")).toContainText(/h \d+m left/);
  await expect(page.locator(".bubble.sender-ai")).toContainText("AI Agent");
  await expect(page.locator(".bubble.sender-automation")).toContainText(
    "Automation",
  );
  await expect(page.locator(".bubble.sender-human .bubble-author")).toHaveText(
    "AL",
  );
  await expect(page.locator(".system-event")).toContainText(
    "Automation triggered: Comment → lead magnet",
  );
  await page.getByRole("button", { name: "Insert emoji" }).click();
  await page.getByRole("button", { name: "Insert 👋" }).click();
  await expect(page.getByLabel("Reply")).toHaveValue("👋");
  await page.screenshot({
    path: "test-results/meta-inbox.png",
    fullPage: true,
  });

  const filtered = page.waitForRequest((request) =>
    request.url().includes("provider=whatsapp"),
  );
  await page.getByRole("tab", { name: /WhatsApp/ }).click();
  await filtered;
});

test("automations hub filters, groups into folders and offers row actions", async ({
  page,
}) => {
  await mockApi(page);
  await page.goto(`/w/${id}/automations`);
  await expect(page.getByText("Comment → lead magnet").first()).toBeVisible();
  await expect(page.locator("td.num").first()).toHaveText("41");
  await page.getByRole("button", { name: "Draft", exact: true }).click();
  await expect(
    page.getByRole("link", { name: "WhatsApp greeting" }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Comment → lead magnet" }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "All", exact: true }).click();
  await page.getByRole("button", { name: "Folders" }).click();
  await expect(page.locator(".folder-group summary").first()).toContainText(
    "Instagram comment leads",
  );
  await page
    .getByRole("button", { name: "Actions for WhatsApp greeting" })
    .click();
  for (const action of [
    "Edit flow",
    "Duplicate",
    "Move to folder",
    "Transfer",
    "View analytics",
    "Delete",
  ])
    await expect(page.locator(".row-menu-list")).toContainText(action);
  await page.screenshot({
    path: "test-results/meta-automations.png",
    fullPage: true,
  });
});

test("CRM table, pipeline and bulk actions", async ({ page }) => {
  const calls = await mockApi(page);
  await page.goto(`/w/${id}/crm`);
  await expect(page.getByText("Maya Chen")).toBeVisible();
  await page.getByLabel("Select all contacts").check();
  await expect(page.locator(".bulk-bar")).toContainText("4 selected");
  await page.getByLabel("Tag to apply").fill("vip");
  await page.getByRole("button", { name: "Apply tag" }).click();
  await expect
    .poll(() => calls.find((call) => call.path.endsWith("/leads/bulk/"))?.body)
    .toEqual({
      ids: ["l-0", "l-1", "l-2", "l-3"],
      action: "tag",
      value: "vip",
    });
  await page.screenshot({
    path: "test-results/meta-crm-table.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "Pipeline" }).click();
  await expect(page.locator(".kanban-column").first()).toContainText(
    "New lead",
  );
  await page.getByLabel("Move Maya Chen to stage").selectOption("won");
  await expect
    .poll(() => calls.find((call) => call.path.endsWith("/leads/l-0/"))?.body)
    .toEqual({ stage: "won" });
  await page.screenshot({
    path: "test-results/meta-crm-pipeline.png",
    fullPage: true,
  });
});

test("app store pins apps to the sidebar dock", async ({ page }) => {
  await mockApi(page);
  await page.goto(`/w/${id}/app-store`);
  const nav = page.getByRole("navigation", { name: "Workspace navigation" });
  await expect(
    nav.getByRole("link", { name: "Content calendar" }),
  ).toBeVisible();
  await page
    .locator(".app-card", { hasText: "Content calendar" })
    .getByRole("button", { name: "Unpin" })
    .click();
  await expect(nav.getByRole("link", { name: "Content calendar" })).toHaveCount(
    0,
  );
  await expect(page.locator(".app-card.soon")).toHaveCount(3);
  await page.screenshot({
    path: "test-results/meta-app-store.png",
    fullPage: true,
  });
});

test("mobile drawer opens, navigates and closes", async ({ page }) => {
  await mockApi(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`/w/${id}/overview`);
  await expect(page.locator(".sidebar")).not.toBeInViewport();
  await page.getByRole("button", { name: "Open navigation" }).click();
  // Wait for the slide-in transition to finish before capturing it.
  await expect(page.locator(".sidebar")).toHaveCSS("transform", "none");
  await expect(page.locator(".sidebar")).toBeInViewport({ ratio: 1 });
  await page.screenshot({ path: "test-results/meta-mobile-drawer.png" });
  await page
    .getByRole("navigation", { name: "Workspace navigation" })
    .getByRole("link", { name: "CRM & contacts" })
    .click();
  await expect(page).toHaveURL(/\/crm\/$/);
  await expect(page.locator(".sidebar")).not.toHaveClass(/open/);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBeTruthy();
});
