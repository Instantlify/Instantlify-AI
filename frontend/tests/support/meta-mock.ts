import type { Page } from "@playwright/test";

/** Mocked API for a fully connected "Studio North" workspace (Instagram, Facebook
 * and WhatsApp), shared by specs that exercise workspace screens without a backend. */

export const id = "22222222-2222-4222-8222-222222222222";
const now = Date.now();
const iso = (offsetMs: number) => new Date(now + offsetMs).toISOString();
export const workspace = {
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
export const connections = [
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
export const leads = [
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
export const conversations = [
  conversation(0, "instagram", 2 * 3600e3),
  conversation(1, "whatsapp", 23.5 * 3600e3),
  conversation(2, "messenger", 30 * 3600e3),
];
export const messages = [
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
export const automations = [
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

export async function mockApi(page: Page) {
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
      if (path === `${p}/leads/` && request.method() === "POST")
        return route.fulfill({
          status: 201,
          json: {
            id: "l-new",
            tags: [],
            fields: {},
            opted_out: false,
            ...request.postDataJSON(),
            channels: [],
            conversation_id: null,
            assigned_to: null,
            message_count: 0,
            created_at: iso(0),
          },
        });
      if (path === `${p}/deeplinks/`)
        return route.fulfill({
          status: 201,
          json: {
            id: "dl-new",
            clicks: 0,
            active: true,
            created_at: iso(0),
            ...request.postDataJSON(),
          },
        });
      if (path === `${p}/shield/rules/`)
        return route.fulfill({
          status: 201,
          json: {
            id: "rule-new",
            enabled: true,
            created_at: iso(0),
            ...request.postDataJSON(),
          },
        });
      if (path === `${p}/webchat/`)
        return route.fulfill({
          json: { updated_at: iso(0), ...request.postDataJSON() },
        });
      // Automation updates echo the stored row with the change applied.
      const automation = automations.find(
        (item) => path === `${p}/automations/${item.id}/`,
      );
      if (automation && request.method() === "PATCH")
        return route.fulfill({
          json: { ...automation, ...request.postDataJSON() },
        });
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
    if (path.includes("/conversations/") && path.endsWith("/events/"))
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
    if (path === `${p}/deeplinks/`)
      return route.fulfill({
        json: [
          {
            id: "dl-1",
            title: "Profile link",
            platform: "instagram",
            target: "https://instagram.com/studio.north",
            code: "ig-profile",
            clicks: 42,
            active: true,
            created_at: iso(-864e5),
          },
        ],
      });
    if (path === `${p}/shield/rules/`)
      return route.fulfill({
        json: [
          {
            id: "rule-1",
            name: "Spam",
            keywords: ["dm me", "crypto"],
            action: "hide",
            enabled: true,
            created_at: iso(-864e5),
          },
        ],
      });
    if (path === `${p}/shield/events/`)
      return route.fulfill({
        json: [
          {
            id: "ev-1",
            rule_name: "Spam",
            provider: "instagram",
            comment_id: "c-1",
            author: "lead-9",
            text: "DM me for crypto",
            action_taken: "hidden",
            created_at: iso(-3600e3),
          },
        ],
      });
    if (path === `${p}/webchat/`)
      return route.fulfill({
        json: {
          title: "Studio North chat",
          greeting: "Hello from the mock",
          color: "#112233",
          bot_enabled: true,
          allowed_domains: ["example.com"],
        },
      });
    if (path.includes("/announcements/") || path.endsWith("/automation-runs/"))
      return route.fulfill({ json: [] });
    return route.fulfill({ json: { results: [], count: 0 } });
  });
  return patches;
}
