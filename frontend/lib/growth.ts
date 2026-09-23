import { api } from "./api";

/** Typed clients for the platform growth APIs (`/api/growth/*`, `/api/blog/*`). */

export type Announcement = {
  id: number;
  type: "popup" | "strip";
  name: string;
  title: string;
  body: string;
  tone: string;
  link_url: string;
};

export type Campaign = {
  slug: string;
  name: string;
  discount_percent: number;
  target_interval: string;
};

export type ChatReply = {
  reply: string;
  sentinel: string | null;
  sources: string[];
};

export type BlogSummary = {
  title: string;
  slug: string;
  excerpt: string;
  category: string;
  thumbnail_url: string;
  published_at: string | null;
};

export type BlogPost = BlogSummary & { body: string };

export const NAME_CARD = "[[REQUEST_NAME_CARD]]";
export const EMAIL_CARD = "[[REQUEST_EMAIL_CARD]]";

export type TourStep = "editor" | "crm" | "apps" | "claude-mcp";

export function announcements(page: string, workspaceId: string) {
  const query = new URLSearchParams({ page, workspace_id: workspaceId });
  return api<Announcement[]>(`/api/growth/announcements/?${query}`);
}

export function markSeen(id: number) {
  return api(`/api/growth/announcements/${id}/seen/`, "POST");
}

export function promo(workspaceId: string) {
  return api<{ campaign: Campaign | null }>(
    `/api/growth/promo/?workspace_id=${encodeURIComponent(workspaceId)}`,
  );
}

export function claimPromo(workspaceId: string, slug: string) {
  return api("/api/growth/promo/", "POST", {
    workspace_id: workspaceId,
    slug,
  });
}

export function chat(body: {
  message?: string;
  name?: string;
  email?: string;
  wants_ticket?: boolean;
  create_ticket?: boolean;
  subject?: string;
  body?: string;
  category?: string;
}) {
  return api<ChatReply & { ok?: boolean; ticket_number?: string }>(
    "/api/growth/support-chat/",
    "POST",
    body,
  );
}

/** Fire-and-forget: tracking must never block or break a page. */
export function tourStep(
  workspaceId: string,
  step: TourStep,
  status: "reached" | "completed" = "reached",
) {
  api("/api/growth/funnel/", "POST", {
    flow: "tour",
    step,
    status,
    workspace_id: workspaceId,
  }).catch(() => undefined);
}

/** Anonymous and write-only, so it needs no CSRF token — and must not fetch one,
 * or it would race the page's own first POST for the csrftoken cookie. */
export function trackVisit(page: string) {
  const params = new URLSearchParams(window.location.search);
  fetch("/api/growth/visit/", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      page,
      source: params.get("utm_source") || params.get("ref") || "",
      referrer: document.referrer,
    }),
    keepalive: true,
  }).catch(() => undefined);
}

export function blogBeacon(
  slug: string,
  scrollDepth: number,
  seconds: number,
): void {
  const body = JSON.stringify({
    slug,
    scroll_depth_pct: Math.round(scrollDepth),
    time_spent_seconds: Math.round(seconds),
  });
  // sendBeacon survives the page being closed, which is exactly when this fires.
  if (navigator.sendBeacon) {
    navigator.sendBeacon(
      "/api/growth/blog-view/",
      new Blob([body], { type: "application/json" }),
    );
    return;
  }
  fetch("/api/growth/blog-view/", {
    method: "POST",
    body,
    headers: { "Content-Type": "application/json" },
    keepalive: true,
  }).catch(() => undefined);
}

export function blogPosts() {
  return api<BlogSummary[]>("/api/blog/");
}

export function blogPost(slug: string) {
  return api<BlogPost>(`/api/blog/${encodeURIComponent(slug)}/`);
}
