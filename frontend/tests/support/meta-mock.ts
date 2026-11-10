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
    brand_name: "Instantlify",
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
const HANDLES = ["@maya.chen", "+15550100", "", "@diego.ruiz"];
const lead = (n: number, stage: string, channel: string) => {
  const connection = connections.find((c) => c.provider === channel)!;
  return {
    id: `l-${n}`,
    name: ["Maya Chen", "Omar Haddad", "Lena Fischer", "Diego Ruiz"][n],
    handle: HANDLES[n],
    avatar_url: n === 0 ? "https://cdn.example.com/maya.jpg" : "",
    email: n % 2 ? "" : `lead${n}@example.com`,
    stage,
    tags: n === 0 ? ["hot"] : [],
    fields: n === 0 ? { City: "Lahore" } : {},
    opted_out: false,
    profile_synced_at: n === 2 ? null : iso(-3600e3),
    created_at: iso(-n * 864e5),
    channels: [channel],
    identities: [
      {
        id: `i-${n}`,
        provider: channel,
        connection_id: connection.id,
        connection_name: connection.display_name,
        external_id: `ext-${n}`,
        conversation_id: `v-${n}`,
        contact_link: channel === "whatsapp" ? "https://wa.me/15550100" : "",
      },
    ],
    conversation_id: `v-${n}`,
    assigned_to: n === 1 ? 1 : null,
    message_count: 3 + n,
    last_activity_at: iso(-(n + 1) * 3600e3),
  };
};
export const leads = [
  lead(0, "new", "instagram"),
  lead(1, "qualified", "whatsapp"),
  lead(2, "booked", "messenger"),
  lead(3, "new", "instagram"),
];
/** A contact added by hand: no channel, no conversation. */
export const manualLead = {
  ...lead(1, "new", "whatsapp"),
  id: "l-manual",
  name: "Priya Shah",
  handle: "",
  avatar_url: "",
  email: "priya@example.com",
  tags: [],
  profile_synced_at: null,
  channels: [],
  identities: [],
  conversation_id: null,
  assigned_to: null,
  message_count: 0,
  last_activity_at: null,
};
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

// A 1x1 PNG standing in for a contact's Meta profile photo.
const PIXEL = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
  "base64",
);

export async function mockApi(page: Page) {
  const patches: { path: string; body: unknown }[] = [];
  await page.route("https://cdn.example.com/**", (route) =>
    route.fulfill({ contentType: "image/png", body: PIXEL }),
  );
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
            ...manualLead,
            id: "l-new",
            created_at: iso(0),
            ...request.postDataJSON(),
          },
        });
      // Contact panel: edits echo the row, refresh fills the profile, merge keeps
      // the target, delete answers 204.
      const leadMatch = path.match(/\/leads\/([^/]+)\/(refresh\/|merge\/)?$/);
      if (path.startsWith(`${p}/leads/`) && leadMatch) {
        const row = [...leads, manualLead].find(
          (item) => item.id === leadMatch[1],
        );
        if (!row) return route.fulfill({ status: 404, json: {} });
        if (request.method() === "DELETE")
          return route.fulfill({ status: 204, body: "" });
        if (leadMatch[2] === "refresh/")
          return route.fulfill({
            json: {
              ...row,
              name: "Maya Chen",
              handle: "@maya.chen",
              avatar_url: "https://cdn.example.com/maya.jpg",
              profile_synced_at: iso(0),
            },
          });
        if (leadMatch[2] === "merge/")
          return route.fulfill({
            json: { ...row, email: row.email || manualLead.email },
          });
        return route.fulfill({ json: { ...row, ...request.postDataJSON() } });
      }
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
    if (path === `${p}/leads/`) {
      const source = new URL(request.url()).searchParams.get("source");
      const rows = source === "manual" ? [manualLead] : leads;
      return route.fulfill({
        json: { results: rows, count: rows.length, next: null },
      });
    }
    const leadRow = [...leads, manualLead].find(
      (item) => path === `${p}/leads/${item.id}/`,
    );
    if (leadRow) return route.fulfill({ json: leadRow });
    if (path === `${p}/integrations/`) return route.fulfill({ json: [] });
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
