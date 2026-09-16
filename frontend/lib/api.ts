export type User = { id: number; name: string; email: string };
export type Branding = {
  brand_name: string;
  logo_url: string;
  primary_color: string;
  support_email: string;
  hide_platform_branding: boolean;
  custom_domain: string;
};
export type Workspace = {
  id: string;
  name: string;
  role: "owner" | "admin" | "agent";
  created_at: string;
  parent: string | null;
  branding: Branding;
};
export type Member = {
  id: string;
  user_id: number;
  name: string;
  email: string;
  role: string;
};
export type Invitation = {
  id: string;
  email: string;
  role: "admin" | "agent";
  expires_at: string;
  accept_url?: string;
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
};
export type Status = { checks: Record<string, boolean>; pending_jobs: number };
export type Page<T> = { results: T[]; count: number; next: string | null };

export type Lead = {
  id: string;
  name: string;
  email: string;
  stage: string;
  tags: string[];
  fields: Record<string, string>;
  opted_out: boolean;
};
export type Conversation = {
  id: string;
  lead: Lead;
  provider: string;
  is_test: boolean;
  assigned_to: number | null;
  status: "open" | "closed" | "needs_human";
  ai_enabled: boolean;
  last_inbound_at: string | null;
  updated_at: string;
};
export type Message = {
  id: string;
  direction: "inbound" | "outbound";
  text: string;
  kind: string;
  created_at: string;
  delivery_status: string | null;
};
export type Note = {
  id: string;
  text: string;
  author_id: number | null;
  created_at: string;
};

export type NodeKind =
  | "send_message"
  | "send_buttons"
  | "delay"
  | "condition"
  | "branch"
  | "wait"
  | "end";
export type FlowButton = { type: "web_url"; url: string; title: string };
export type FlowNodeData = {
  kind: NodeKind;
  text?: string;
  buttons?: FlowButton[];
  seconds?: number;
  variable?: string;
  equals?: string;
};
export type FlowGraph = {
  start: string;
  triggers: { kind: string; keyword: string }[];
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
};
export type AutomationRun = {
  id: string;
  automation_id: string;
  conversation_id: string;
  status: string;
  steps: number;
  node_id: string;
  error_code: string;
};

export type AgentConfig = {
  id: string;
  name: string;
  system_prompt: string;
  provider: string;
  model: string;
  has_key: boolean;
  embedding_model: string;
  allowed_tools: string[];
  enabled: boolean;
  is_test: boolean;
  input_cost_per_million: string;
  output_cost_per_million: string;
  qualifying_fields: string[];
  triage_enabled: boolean;
  handoff_keywords: string[];
  max_tool_rounds: number;
  mode: "agent" | "simple";
};
export type KnowledgeDocument = {
  id: string;
  title: string;
  status: string;
  error_code: string;
  embedding_model: string;
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

export type FunnelStep = { kind: string; leads: number; conversion: number };
export type Funnel = {
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
export type BioPage = {
  id?: string;
  slug: string;
  title: string;
  bio: string;
  avatar_url: string;
  accent: string;
  links: BioLink[];
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
  used: number;
  usage_limit: number;
  seat_limit: number;
  channel_limit: number;
  stripe_configured: boolean;
  period_start: string;
  plans: Record<string, { seats: number; channels: number; messages: number }>;
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
  ) {
    super(message);
  }
}

function errorMessage(data: unknown): string {
  if (!data || typeof data !== "object")
    return "Something went wrong. Please try again.";
  return Object.entries(data)
    .map(
      ([key, value]) =>
        `${key === "detail" || key === "non_field_errors" ? "" : `${key}: `}${Array.isArray(value) ? value.join(" ") : String(value)}`,
    )
    .join(" ");
}

export const message = (error: unknown) =>
  error instanceof Error
    ? error.message
    : "Something went wrong. Please try again.";

async function csrfToken(signal?: AbortSignal) {
  const csrf = await fetch("/api/auth/csrf/", {
    credentials: "same-origin",
    cache: "no-store",
    signal,
  });
  if (!csrf.ok)
    throw new ApiError(
      "Unable to establish a secure session. Please try again.",
      csrf.status,
    );
  return (await csrf.json()).csrfToken as string;
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
  if (response.status === 204) return undefined as T;
  const payload = await response.json().catch(() => ({
    detail: "The service is temporarily unavailable. Please try again.",
  }));
  if (!response.ok) throw new ApiError(errorMessage(payload), response.status);
  return payload as T;
}

/** Multipart upload (files) with the same CSRF and error handling as `api`. */
export async function upload<T>(path: string, form: FormData): Promise<T> {
  const response = await fetch(path, {
    method: "POST",
    headers: { "X-CSRFToken": await csrfToken() },
    credentials: "same-origin",
    cache: "no-store",
    body: form,
  });
  const payload = await response.json().catch(() => ({
    detail: "The service is temporarily unavailable. Please try again.",
  }));
  if (!response.ok) throw new ApiError(errorMessage(payload), response.status);
  return payload as T;
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
