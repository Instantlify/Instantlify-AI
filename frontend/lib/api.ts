import {
  errorSummary,
  friendlyError,
  validationErrors,
  type FieldErrors,
} from "./form-errors";

export type User = {
  photo_url?: string;
  id: number;
  name: string;
  email: string;
  email_verified?: boolean;
};
export type Branding = {
  brand_name: string;
  logo_url: string;
  primary_color: string;
  sidebar_bg_color?: string;
  sidebar_text_color?: string;
  support_email: string;
  hide_platform_branding: boolean;
  custom_domain: string;
  custom_domain_status?: "pending" | "active" | "failed";
  verification_token?: string;
  verified_at?: string | null;
  tls_status?: "inactive" | "issuing" | "active" | "error";
};
export type Workspace = {
  checkout_pending?: boolean;
  id: string;
  name: string;
  role: "owner" | "admin" | "agent" | "viewer";
  created_at: string;
  parent: string | null;
  branding: Branding;
  /** App Store apps pinned to the sidebar dock, in order. */
  pinned_apps?: string[];
  /** Sections this member may use; empty means all. */
  allowed_sections?: string[];
};
export type Member = {
  id: string;
  user_id: number;
  name: string;
  email: string;
  role: string;
  allowed_sections?: string[];
  allowed_connections?: string[];
};
export type Invitation = {
  id: string;
  email: string;
  role: "admin" | "agent" | "viewer";
  expires_at: string;
  accept_url?: string;
  email_sent?: boolean;
};
export type Audit = {
  id: string;
  action: string;
  actor_id: number | null;
  target_id: string;
  created_at: string;
};
export type Connection = {
  id: string;
  provider: string;
  display_name: string;
  expires_at: string;
  is_test: boolean;
  status: string;
  locked: boolean;
  followers: number | null;
  last_refreshed_at: string | null;
};
export type Status = { checks: Record<string, boolean>; pending_jobs: number };
export type Page<T> = { results: T[]; count: number; next: string | null };

/** Follow page numbers on a known endpoint without trusting a returned remote URL. */
export async function apiPages<T>(
  path: string,
  signal?: AbortSignal,
): Promise<T[]> {
  const records: T[] = [];
  let page = 1;
  while (true) {
    const result = await api<Page<T>>(
      `${path}${path.includes("?") ? "&" : "?"}page=${page}`,
      "GET",
      undefined,
      signal,
    );
    records.push(...result.results);
    if (!result.next) return records;
    page += 1;
  }
}

export type Lead = {
  id: string;
  name: string;
  /** @username or phone number as the channel reports it. */
  handle: string;
  avatar_url: string;
  email: string;
  stage: string;
  tags: string[];
  fields: Record<string, string>;
  opted_out: boolean;
  profile_synced_at: string | null;
  created_at: string;
  /** Written on request by the workspace AI model; empty until then. */
  ai_summary?: string;
  ai_summary_at?: string | null;
};
/** One channel account the contact has written from. */
export type LeadIdentity = {
  id: string;
  provider: string;
  connection_id: string;
  connection_name: string;
  external_id: string;
  conversation_id: string | null;
  contact_link: string;
};
/** The contact as the inbox sees it on each conversation row. */
export type ConversationLead = Omit<Lead, "profile_synced_at" | "created_at">;
export type Conversation = {
  id: string;
  /** The current teammate has not opened it since the customer last wrote. */
  unread?: boolean;
  /** Other teammates who have read the latest message. */
  seen_by?: string[];
  lead: ConversationLead;
  provider: string;
  is_test: boolean;
  assigned_to: number | null;
  status: "open" | "closed" | "needs_human";
  ai_enabled: boolean;
  handoff_reason?: string;
  last_inbound_at: string | null;
  last_outbound_at: string | null;
  updated_at: string;
  connection_id: string;
  connection_name: string;
  /** Direct link to the contact on its channel, when the channel has one. */
  contact_link: string;
  last_message: {
    text: string;
    kind: string;
    direction: "inbound" | "outbound";
    created_at: string;
  } | null;
};
export type MessageSender = "customer" | "ai" | "human" | "automation" | "api";
export type Message = {
  sequence?: number | null;
  provider_status?: string;
  media_url?: string;
  id: string;
  direction: "inbound" | "outbound";
  text: string;
  kind: string;
  created_at: string;
  delivery_status: string | null;
  sender: MessageSender;
  author_name: string;
};
export type ConversationEvent = {
  id: number;
  kind: "triggered" | "handoff" | "link_click" | "booked" | "paid";
  automation_name: string;
  amount_cents: number;
  created_at: string;
};
/** A CRM row: the lead plus its channels and who is working it. */
export type LeadRow = Lead & {
  channels: string[];
  identities: LeadIdentity[];
  conversation_id: string | null;
  assigned_to: number | null;
  message_count: number;
  last_activity_at: string | null;
};
export type Note = {
  id: string;
  text: string;
  author_id: number | null;
  created_at: string;
};

export type NodeKind =
  | "ai_agent"
  | "avatar_video"
  | "ai_call"
  | "generate_voice"
  | "follow_gate"
  | "send_reminder"
  | "ai_generate"
  | "ai_extract"
  | "ai_condition"
  | "send_media"
  | "integration_action"
  | "start_agent"
  | "set_field"
  | "set_stage"
  | "randomizer"
  | "capture_email"
  | "add_tag"
  | "assign_member"
  | "transfer"
  | "send_message"
  | "send_buttons"
  | "delay"
  | "condition"
  | "branch"
  | "wait"
  | "end";
export type FlowButton = {
  type: "web_url" | "postback";
  title: string;
  url?: string;
  payload?: string;
};
export type ConditionRule = {
  subject: "variable" | "field" | "tag" | "stage" | "email" | "channel";
  name?: string;
  operator:
    | "equals"
    | "not_equals"
    | "contains"
    | "not_contains"
    | "starts_with"
    | "ends_with"
    | "is_set"
    | "is_not_set"
    | "greater_than"
    | "less_than";
  value?: string;
};
export type FlowNodeData = {
  kind: NodeKind;
  rules?: ConditionRule[];
  persona?: string;
  max_turns?: number;
  use_knowledge?: boolean;
  knowledge_base_id?: string;
  capture_fields?: string[];
  match?: "all" | "any";
  seconds_max?: number;
  timeout_seconds?: number;
  prompt?: string;
  fields?: string[];
  ai_provider?: string;
  ai_model?: string;
  track_clicks?: boolean;
  source_node?: string;
  button_title?: string;
  media_url?: string;
  media_type?: "image" | "video" | "audio";
  text?: string;
  buttons?: FlowButton[];
  seconds?: number;
  variable?: string;
  equals?: string;
  expected_reply?: string;
  retry_text?: string;
  tag?: string;
  user_id?: number;
  automation_id?: string;
  field?: string;
  value?: string;
  stage?: string;
  percentage?: number;
  integration_id?: string;
  operation?: "sync_lead" | "notify" | "send_email" | "webhook";
  wait_for_completion?: boolean;
  request_body?: string;
  response_map?: string | Record<string, string>;
  subject?: string;
  to?: string;
  phone_variable?: string;
  consent_reply?: string;
  agent_id?: string;
  timezone?: string;
  weekdays?: number[];
  call_start?: string;
  call_end?: string;
  avatar_id?: string;
  voice_id?: string;
  aspect_ratio?: string;
};
export type FlowTrigger = {
  kind: string;
  keyword: string;
  /** "keyword" (default): the word must appear. "intent": `keyword` describes a meaning. */
  match?: "keyword" | "intent";
  /** Provider the trigger listens on; blank or absent means every channel. */
  channel?: string;
};
export type FlowGraph = {
  connection_id?: string;
  comment_post_ids?: string[];
  comment_replies?: string[];
  comment_post_mode?: "all" | "specific" | "next";
  comment_since?: string;
  resolved_next_post_id?: string;
  start: string;
  triggers: FlowTrigger[];
  nodes: {
    id: string;
    data: FlowNodeData;
    position?: { x: number; y: number };
  }[];
  edges: {
    id?: string;
    source: string;
    target: string;
    sourceHandle?: string;
  }[];
};
export type Automation = {
  id: string;
  name: string;
  draft: Partial<FlowGraph>;
  published: Partial<FlowGraph>;
  revision: number;
  enabled: boolean;
  updated_at: string;
  installed_from: string | null;
  folder: string;
  created_at: string;
};
export type AutomationStats = Record<string, { runs: number; reach: number }>;
export type AutomationRun = {
  id: string;
  automation_id: string;
  conversation_id: string;
  status: string;
  steps: number;
  node_id: string;
  error_code: string;
  automation_name?: string;
  revision?: number;
  created_at?: string;
  finished_at?: string | null;
  trace?: { node_id: string; steps: number; status: string; at: string }[];
};

export type AgentConfig = {
  id: string;
  name: string;
  system_prompt: string;
  provider: string;
  model: string;
  has_key: boolean;
  embedding_model: string;
  has_embedding_key: boolean;
  fallback_provider: string;
  fallback_model: string;
  allowed_tools: string[];
  enabled: boolean;
  is_test: boolean;
  input_cost_per_million: string;
  output_cost_per_million: string;
  qualifying_fields: string[];
  triage_enabled: boolean;
  handoff_keywords: string[];
  max_tool_rounds: number;
  reply_delay_seconds?: number;
  mode: "agent" | "simple";
  billing_mode: "platform_credits" | "byo_key";
  available_models?: PlatformModel[];
};

export type PlatformModel = {
  id: string;
  provider: string;
  label: string;
  badge: string;
  description: string;
  input_rate: string;
  output_rate: string;
  rate_summary: string;
};
export type KnowledgeDocument = {
  id: string;
  title: string;
  status: string;
  error_code: string;
  embedding_model: string;
  created_at: string;
  knowledge_base?: string | null;
  file_type?: string;
};
export type KnowledgeBase = {
  id: string;
  name: string;
  description: string;
  document_count: number;
  created_at: string;
};
export type AgentAudit = {
  runs: {
    id: string;
    message_id: string;
    status: string;
    error_code: string;
    created_at: string;
  }[];
  tools: {
    id: string;
    name: string;
    status: string;
    input: unknown;
    output: unknown;
  }[];
  usage: {
    id: string;
    model: string;
    kind: string;
    input_tokens: number;
    output_tokens: number;
    cost: string;
    status: string;
    created_at: string;
  }[];
};

export type TelemetryDay = {
  date: string;
  instagram: number;
  messenger: number;
  whatsapp: number;
  other: number;
  contacts: number;
};
export type Telemetry = {
  since: string;
  days: TelemetryDay[];
  totals: {
    inbound: number;
    contacts: number;
    conversations: number;
    ai_rate: number | null;
  };
  channels: {
    provider: string;
    inbound: number;
    conversations: number;
    median_response_minutes: number | null;
    top_automation: { name: string; runs: number } | null;
  }[];
};

export type FunnelStep = {
  kind: string;
  leads: number;
  conversion: number | null;
};
export type Funnel = {
  unique_leads: number;
  period: string;
  since: string;
  steps: FunnelStep[];
  revenue_cents: number;
  automations: {
    automation_id: string;
    name: string;
    triggered: number;
    booked: number;
    paid: number;
    revenue_cents: number;
  }[];
  channels: {
    provider: string;
    leads: number;
    booked: number;
    paid: number;
  }[];
};
export type ArmResult = { leads: number; conversions: number; rate: number };
export type Experiment = {
  id: string;
  name: string;
  control: string;
  variant: string;
  split: number;
  goal: string;
  status: string;
  winner: string;
  auto_promote: boolean;
  min_leads: number;
  concluded_at: string | null;
  results: { control: ArmResult; variant: ArmResult };
  created_at: string;
};

export type ScheduledPost = {
  id: string;
  connection: string;
  caption: string;
  media_url: string;
  media_type: "image" | "video";
  scheduled_at: string;
  status: string;
  attempts: number;
  provider_post_id: string;
  error_code: string;
  published_at: string | null;
  created_at: string;
};
export type BioLink = { title: string; url: string };
export type DeepLink = {
  id: string;
  title: string;
  platform: "instagram" | "whatsapp" | "youtube" | "telegram" | "custom";
  target: string;
  code: string;
  clicks: number;
  active: boolean;
  campaign?: string;
  source?: string;
  medium?: string;
  created_at: string;
};
export type ShieldRule = {
  id: string;
  name: string;
  keywords: string[];
  /** AI rule description; blank for a keyword rule. */
  prompt: string;
  /** Public reply posted when the rule matches; blank for none. */
  reply_text: string;
  action: "hide" | "delete" | "flag";
  enabled: boolean;
  created_at: string;
};
export type ShieldEvent = {
  id: string;
  rule_name: string;
  provider: string;
  comment_id: string;
  author: string;
  text: string;
  action_taken: "hidden" | "deleted" | "flagged" | "failed";
  created_at: string;
};
export type WebChatSettings = {
  title: string;
  greeting: string;
  color: string;
  bot_enabled: boolean;
  position?: "left" | "right";
  launcher_label?: string;
  logo_url?: string;
  quick_replies?: string[];
  allowed_domains: string[];
  updated_at?: string;
};
export type BioBlock = {
  type:
    | "link"
    | "heading"
    | "text"
    | "image"
    | "video"
    | "social"
    | "email_capture"
    | "divider";
  index?: number;
  title?: string;
  url?: string;
  highlight?: boolean;
  text?: string;
  alt?: string;
  link?: string;
  embed?: string;
  items?: { platform: string; url: string }[];
  button?: string;
  tag?: string;
};
export type BioPage = {
  id?: string;
  slug: string;
  title: string;
  bio: string;
  avatar_url: string;
  accent: string;
  links: BioLink[];
  blocks: BioBlock[];
  theme: string;
  published: boolean;
};
export type PublicBio = Omit<BioPage, "links" | "id"> & {
  links: (BioLink & { index: number })[];
  branding: Branding;
};

export type Template = {
  id: string;
  title: string;
  slug: string;
  description: string;
  category: string;
  author_name: string;
  price_cents: number;
  status: string;
  install_count: number;
  created_at: string;
  updated_at: string;
  graph?: FlowGraph;
};
export type SellerStatus = {
  connected: boolean;
  transfers_status: string;
  requirements_due: boolean;
  can_sell?: boolean;
  checked_at?: string | null;
  country?: string;
  url?: string;
};
export type TemplatePurchase = {
  id: string;
  template_id: string;
  title: string;
  amount_cents: number;
  currency: string;
  status: string;
  automation_id: string | null;
  paid_at: string | null;
  created_at: string;
};
export type InstallResult = {
  automation_id?: string;
  purchase_id?: string;
  status?: string;
  checkout_url?: string;
};

export type Offer = {
  id: string;
  name: string;
  description: string;
  amount_cents: number;
  currency: string;
  active: boolean;
  created_at: string;
};
export type Payment = {
  id: string;
  offer_id: string;
  conversation_id: string;
  lead_id: string;
  amount_cents: number;
  currency: string;
  status: string;
  paid_at: string | null;
  created_at: string;
};
export type Billing = {
  plan: string;
  status: string;
  interval: string;
  trial_ends_at: string | null;
  used: number;
  usage_limit: number | null;
  seat_limit: number | null;
  channel_limit: number | null;
  limits: PlanLimits;
  stripe_configured: boolean;
  trial_days: number;
  period_start: string;
  plans: Record<
    string,
    { seats: number | null; channels: number | null; messages: number | null }
  >;
  catalog: PlanCard[];
};
export type PlanLimits = {
  max_instagram_accounts: number | null;
  max_contacts: number | null;
  team_seats: number | null;
  max_ai_messages: number | null;
  ai_agent_enabled: boolean;
  integrations_unlocked: boolean;
  content_scheduling_enabled: boolean;
  voice_notes_enabled: boolean;
};
export type PlanCard = {
  slug: string;
  name: string;
  is_featured: boolean;
  limits: PlanLimits;
  prices: { interval: string; price_cents: number; configured: boolean }[];
};
/** Plan limits use null for unlimited. */
export const limit = (value: number | null | undefined) =>
  value === null || value === undefined ? "unlimited" : String(value);
export type CreditTransaction = {
  id: string;
  type: string;
  status: string;
  amount_cents: string;
  real_cost_cents: string;
  remaining_balance_cents: string;
  model: string;
  tokens_in: number;
  tokens_out: number;
  description: string;
  created_at: string;
};
export type Credits = {
  billing_mode: string;
  balance_cents: string;
  auto_topup_enabled: boolean;
  auto_topup_threshold_cents: number;
  auto_topup_amount_cents: number;
  has_payment_method: boolean;
  auto_topup_failed_at: string | null;
  topup_options: number[];
  stripe_configured: boolean;
  rate: {
    model: string;
    input_per_million_cents: string;
    output_per_million_cents: string;
  } | null;
  transactions: CreditTransaction[];
};
export type BillingJob = {
  id: string;
  status: string;
  result: { url?: string; error?: string };
};

export type Integration = {
  id: string;
  provider: string;
  options: Record<string, string>;
  enabled: boolean;
  is_test: boolean;
  configured: boolean;
  status: string;
};
export type APIKey = {
  id: string;
  name: string;
  prefix: string;
  scopes: string[];
  last_used_at: string | null;
  revoked_at: string | null;
  created_at: string;
  key?: string;
};
export type WebhookSubscription = {
  id: string;
  url: string;
  events: string[];
  active: boolean;
  failure_count: number;
  last_delivered_at: string | null;
  created_at: string;
  secret?: string;
  token?: string;
};
export type WebhookDelivery = {
  id: string;
  subscription_id: string;
  event: string;
  status: string;
  attempts: number;
  response_code: number | null;
  created_at: string;
};
export type Delivery = {
  id: string;
  recipient_id: string;
  status: string;
  attempts: number;
  error_code: string;
  created_at: string;
};
export type DataOperation = {
  id: string;
  kind: string;
  status: string;
  error_code: string;
  created_at: string;
};
export type ClientWorkspace = {
  id: string;
  name: string;
  created_at: string;
  members: number;
};

export const WEBHOOK_EVENTS = [
  "form.submitted",
  "lead.created",
  "lead.updated",
  "lead.hot",
  "message.received",
  "message.sent",
  "conversation.handoff",
  "call.booked",
  "payment.paid",
];
export const AGENT_TOOLS = [
  "check_calendar_availability",
  "book_call",
  "update_crm_field",
  "send_voice_note",
  "create_payment_link",
  "handoff_to_human",
];

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    /** Set on 402 plan-gate responses: the limit or feature that blocked the action. */
    public upgradeRequired?: string,
    public fieldErrors: FieldErrors = {},
  ) {
    super(message);
  }
}

/** Fired on the window whenever the API blocks an action on plan grounds, so the
 * shell can open the upgrade modal without every page wiring it up. */
export const UPGRADE_EVENT = "nemio:upgrade-required";

function failure(payload: unknown, status: number) {
  const upgrade =
    status === 402 && payload && typeof payload === "object"
      ? String(
          (payload as { upgrade_required?: string }).upgrade_required || "",
        )
      : "";
  if (upgrade && typeof window !== "undefined")
    window.dispatchEvent(new CustomEvent(UPGRADE_EVENT, { detail: upgrade }));
  const detail =
    upgrade && payload && typeof payload === "object"
      ? String((payload as { detail?: string }).detail || "Upgrade required.")
      : errorMessage(payload);
  return new ApiError(
    status >= 500
      ? "We couldn’t complete this request. Please try again in a moment."
      : detail,
    status,
    upgrade || undefined,
    status === 400 || status === 422 ? validationErrors(payload) : {},
  );
}

function errorMessage(data: unknown): string {
  return errorSummary(data);
}

export const message = (error: unknown) =>
  error instanceof Error
    ? /Failed to fetch|NetworkError|Load failed/i.test(error.message)
      ? "We couldn’t connect. Check your internet connection and try again."
      : friendlyError(error.message)
    : "Something went wrong. Please try again.";

/* Concurrent first requests must share one token fetch. With no csrftoken cookie yet,
 * two parallel fetches are each issued a different secret; whichever cookie lands
 * last wins, and the other request's token is then rejected as incorrect. */
let pendingToken: Promise<string> | null = null;

async function fetchCsrfToken() {
  const csrf = await fetch("/api/auth/csrf/", {
    credentials: "same-origin",
    cache: "no-store",
  });
  if (!csrf.ok)
    throw new ApiError(
      "Unable to establish a secure session. Please try again.",
      csrf.status,
    );
  return (await csrf.json()).csrfToken as string;
}

async function csrfToken(signal?: AbortSignal) {
  // The shared fetch ignores any one caller's signal, so aborting one request cannot
  // fail the others waiting on the same token.
  pendingToken ??= fetchCsrfToken().finally(() => {
    pendingToken = null;
  });
  const token = await pendingToken;
  signal?.throwIfAborted();
  return token;
}

export async function api<T>(
  path: string,
  method = "GET",
  data?: unknown,
  signal?: AbortSignal,
  extraHeaders: Record<string, string> = {},
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...extraHeaders,
  };
  if (method !== "GET") headers["X-CSRFToken"] = await csrfToken(signal);
  const response = await fetch(path, {
    method,
    headers,
    credentials: "same-origin",
    cache: "no-store",
    body: data === undefined ? undefined : JSON.stringify(data),
    signal,
  });
  if (
    typeof window !== "undefined" &&
    response.ok &&
    [
      "/api/auth/login/",
      "/api/auth/logout/",
      "/api/auth/magic-link/verify/",
    ].includes(path)
  ) {
    window.dispatchEvent(
      new CustomEvent("instantlify:session-changed", {
        detail: { action: path === "/api/auth/logout/" ? "logout" : "login" },
      }),
    );
  }
  if (response.status === 204) return undefined as T;
  const payload = await response.json().catch(() => ({
    detail: "The service is temporarily unavailable. Please try again.",
  }));
  if (!response.ok) throw failure(payload, response.status);
  return payload as T;
}

/** Multipart upload (files) with the same CSRF and error handling as `api`. */
export async function upload<T>(
  path: string,
  form: FormData,
  method = "POST",
  extraHeaders: Record<string, string> = {},
): Promise<T> {
  const response = await fetch(path, {
    method,
    headers: { ...extraHeaders, "X-CSRFToken": await csrfToken() },
    credentials: "same-origin",
    cache: "no-store",
    body: form,
  });
  const payload = await response.json().catch(() => ({
    detail: "The service is temporarily unavailable. Please try again.",
  }));
  if (!response.ok) throw failure(payload, response.status);
  return payload as T;
}

export async function apiBlob(path: string): Promise<Blob> {
  const response = await fetch(path, {
    credentials: "same-origin",
    cache: "no-store",
  });
  if (!response.ok)
    throw failure(
      await response
        .json()
        .catch(() => ({ detail: "The download could not be completed." })),
      response.status,
    );
  return response.blob();
}

export const idempotencyKey = () =>
  typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`;

export const money = (cents: number, currency = "usd") =>
  new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: currency.toUpperCase(),
  }).format(cents / 100);

export const when = (value: string | null | undefined) =>
  value ? new Date(value).toLocaleString() : "—";
