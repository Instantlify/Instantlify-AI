"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { KeyRound, Plug, Plus, Send, Webhook } from "lucide-react";
import {
  api,
  when,
  WEBHOOK_EVENTS,
  type APIKey,
  type Connection,
  type Delivery,
  type Integration,
  type Page,
  type WebhookDelivery,
  type WebhookSubscription,
} from "@/lib/api";
import { useWorkspace } from "@/lib/workspace";
import {
  CopyField,
  Empty,
  ErrorNotice,
  Modal,
  PageHeading,
  Panel,
  Pill,
  statusTone,
  SuccessNotice,
  Table,
  useFeedback,
} from "@/components/ui";
import { TourMarker } from "@/components/growth";
import { tourStep } from "@/lib/growth";

type FieldSpec = { key: string; label: string; secret?: boolean };
type ProviderSpec = {
  label: string;
  blurb: string;
  /** Hosted sign-in button label; manual credentials stay available as a fallback. */
  oauth?: string;
  credentials: FieldSpec[];
  options: FieldSpec[];
};

const PROVIDERS: Record<string, ProviderSpec> = {
  google_calendar: {
    label: "Google Calendar",
    oauth: "Connect Google Calendar",
    blurb: "Availability checks and bookings on a Google calendar.",
    credentials: [
      { key: "access_token", label: "Access token", secret: true },
      { key: "refresh_token", label: "Refresh token", secret: true },
    ],
    options: [{ key: "calendar_id", label: "Calendar ID (default: primary)" }],
  },
  calcom: {
    label: "Cal.com",
    blurb: "Slots and bookings through a Cal.com event type.",
    credentials: [{ key: "api_key", label: "API key", secret: true }],
    options: [
      { key: "event_type_id", label: "Event type ID" },
      { key: "timezone", label: "Timezone (e.g. UTC)" },
    ],
  },
  airtable: {
    label: "Airtable",
    blurb: "Sync leads into an Airtable table.",
    credentials: [
      { key: "api_key", label: "Personal access token", secret: true },
    ],
    options: [
      { key: "base_id", label: "Base ID" },
      { key: "table_id", label: "Table ID" },
    ],
  },
  notion: {
    label: "Notion",
    blurb: "Create a page per lead in a Notion database.",
    credentials: [
      { key: "api_key", label: "Integration secret", secret: true },
    ],
    options: [{ key: "database_id", label: "Database ID" }],
  },
  gohighlevel: {
    label: "GoHighLevel",
    blurb: "Upsert contacts into a GoHighLevel location.",
    credentials: [{ key: "api_key", label: "API key", secret: true }],
    options: [{ key: "location_id", label: "Location ID" }],
  },
  attio: {
    label: "Attio",
    blurb: "Assert people records in Attio by email.",
    credentials: [{ key: "api_key", label: "API key", secret: true }],
    options: [],
  },
  slack: {
    label: "Slack",
    oauth: "Add to Slack",
    blurb: "Hot-lead and human-handoff notifications in a channel.",
    credentials: [{ key: "api_key", label: "Bot token", secret: true }],
    options: [{ key: "channel_id", label: "Channel ID" }],
  },
  elevenlabs: {
    label: "ElevenLabs",
    blurb:
      "Outbound AI voice notes. Powered by Nemio Voice credits by default, or provide your own key.",
    credentials: [
      {
        key: "api_key",
        label: "API key (leave blank to use platform credits)",
        secret: true,
      },
    ],
    options: [
      { key: "voice_id", label: "Voice ID (default: Rachel)" },
      { key: "model", label: "Model (default: eleven_multilingual_v2)" },
    ],
  },
  snapchat: {
    label: "Snapchat (Lead Ads & Bio)",
    blurb:
      "Sync Snapchat Lead Ads into CRM and link to your interactive Bio Concierge.",
    credentials: [],
    options: [
      { key: "ad_account_id", label: "Snapchat Ad Account ID (optional)" },
    ],
  },
  stripe: {
    label: "Stripe (your account)",
    blurb: "In-chat checkout links paid into your own Stripe account.",
    credentials: [
      { key: "secret_key", label: "Secret key", secret: true },
      { key: "webhook_secret", label: "Webhook signing secret", secret: true },
    ],
    options: [
      { key: "success_url", label: "Success URL (optional)" },
      { key: "cancel_url", label: "Cancel URL (optional)" },
    ],
  },
};

const CHANNEL_PROVIDERS = [
  { id: "whatsapp", label: "WhatsApp Business", account: "Phone number ID" },
  { id: "telegram", label: "Telegram Bot", account: "Bot user ID" },
  { id: "snapchat", label: "Snapchat Lead Ads", account: "Ad Account or Form ID" },
  { id: "linkedin", label: "LinkedIn Company Page", account: "Organization URN" },
  { id: "messenger", label: "Facebook Messenger", account: "Page ID" },
];

function integrationLabel(item: Integration) {
  if (item.status === "reconnect_required") return "reconnect";
  if (item.status === "disconnected") return "disconnected";
  if (item.is_test) return "test";
  if (!item.enabled) return "disabled";
  return item.configured ? "connected" : "no credentials";
}

function integrationTone(item: Integration): "good" | "warn" | "neutral" {
  if (item.status === "reconnect_required") return "warn";
  if (item.status === "disconnected" || item.is_test) return "neutral";
  return item.enabled && item.configured ? "good" : "warn";
}

const OAUTH_RESULTS: Record<string, string> = {
  connected: "connected.",
  "test-connected": "connected in local test mode.",
  cancelled: "sign-in was cancelled.",
  failed: "sign-in failed. Try again or enter credentials manually.",
};

export default function IntegrationsPage() {
  const { workspace, prefix, manager } = useWorkspace();
  const owner = workspace.role === "owner";
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [connections, setConnections] = useState<Connection[]>([]);
  const [deliveries, setDeliveries] = useState<Delivery[]>([]);
  const [keys, setKeys] = useState<APIKey[]>([]);
  const [subscriptions, setSubscriptions] = useState<WebhookSubscription[]>([]);
  const [hookLog, setHookLog] = useState<WebhookDelivery[]>([]);
  const [configuring, setConfiguring] = useState("");
  const [testMode, setTestMode] = useState(false);
  const [newKey, setNewKey] = useState("");
  const [newSecret, setNewSecret] = useState("");
  const [newToken, setNewToken] = useState("");
  const [origin] = useState(() =>
    typeof window === "undefined" ? "" : window.location.origin,
  );
  const [loading, setLoading] = useState(true);
  const feedback = useFeedback();

  const load = useCallback(
    async (signal?: AbortSignal) => {
      const channels = await api<Page<Connection>>(
        `${prefix}/connections/`,
        "GET",
        undefined,
        signal,
      );
      setConnections(channels.results);
      if (!manager) return;
      const [items, sent, keyPage, subs, log] = await Promise.all([
        api<Page<Integration>>(
          `${prefix}/integrations/`,
          "GET",
          undefined,
          signal,
        ),
        api<Delivery[]>(`${prefix}/deliveries/`, "GET", undefined, signal),
        api<Page<APIKey>>(`${prefix}/api-keys/`, "GET", undefined, signal),
        api<Page<WebhookSubscription>>(
          `${prefix}/webhooks/`,
          "GET",
          undefined,
          signal,
        ),
        api<WebhookDelivery[]>(
          `${prefix}/webhook-deliveries/`,
          "GET",
          undefined,
          signal,
        ),
      ]);
      setIntegrations(items.results);
      setDeliveries(sent);
      setKeys(keyPage.results);
      setSubscriptions(subs.results);
      setHookLog(log);
    },
    [prefix, manager],
  );

  useEffect(() => {
    const controller = new AbortController();
    // Deferred so state updates happen in response to the fetch, not the render.
    queueMicrotask(() => {
      load(controller.signal)
        .catch((err) => {
          if (!controller.signal.aborted)
            feedback.setError(String((err as Error).message));
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [load]);

  const integrationFor = (provider: string) =>
    integrations.find((item) => item.provider === provider);

  // Hosted sign-in returns here with ?integration=<result>&provider=<id> or ?connection=<result>.
  useEffect(() => {
    const url = new URL(window.location.href);
    const params = url.searchParams;
    const conn = params.get("connection");
    const result = params.get("integration");
    if (conn) {
      if (conn === "connected") feedback.setNotice("Channel connected successfully.");
      else if (conn === "test-connected")
        feedback.setNotice("Channel connected in local test mode (CHANNEL_ADAPTER_MODE=fake).");
      else if (conn === "limit")
        feedback.setError("Your plan's connected-account limit has been reached.");
      else if (conn === "cancelled")
        feedback.setError("Channel connection was cancelled.");
      url.searchParams.delete("connection");
      // The initial load above already refreshes connections after this redirect.
    }
    if (!result && !conn) return;
    if (result) {
      const label =
        PROVIDERS[params.get("provider") || ""]?.label || "Integration";
      const text = `${label} ${OAUTH_RESULTS[result] || "sign-in finished."}`;
      if (result === "cancelled" || result === "failed") feedback.setError(text);
      else feedback.setNotice(text);
      url.searchParams.delete("integration");
      url.searchParams.delete("provider");
    }
    window.history.replaceState(null, "", url.toString());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function connectOAuth(provider: string) {
    await feedback.run(async () => {
      const started = await api<{ authorization_url: string }>(
        `${prefix}/integrations/${provider}/oauth/`,
        "POST",
        {},
      );
      window.location.assign(started.authorization_url);
    });
  }

  async function disconnectIntegration(item: Integration) {
    const label = PROVIDERS[item.provider]?.label || item.provider;
    if (!window.confirm(`Disconnect ${label}? Stored credentials are removed.`))
      return;
    await feedback.run(async () => {
      const saved = await api<Integration>(
        `${prefix}/integrations/${item.id}/`,
        "DELETE",
      );
      setIntegrations((list) =>
        list.map((entry) => (entry.id === saved.id ? saved : entry)),
      );
    }, `${label} disconnected.`);
  }

  async function saveIntegration(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const spec = PROVIDERS[configuring];
    const data = new FormData(event.currentTarget);
    const credentials: Record<string, string> = {};
    const options: Record<string, string> = {};
    for (const field of spec.credentials) {
      const value = String(data.get(`cred_${field.key}`) || "");
      if (value) credentials[field.key] = value;
    }
    for (const field of spec.options) {
      const value = String(data.get(`opt_${field.key}`) || "");
      if (value) options[field.key] = value;
    }
    const isTest = data.get("is_test") === "on";
    await feedback.run(async () => {
      const saved = await api<Integration>(`${prefix}/integrations/`, "POST", {
        provider: configuring,
        credentials,
        options,
        enabled: data.get("enabled") === "on",
        is_test: isTest,
      });
      setIntegrations((list) => [
        ...list.filter((item) => item.provider !== saved.provider),
        saved,
      ]);
      setConfiguring("");
    }, `${spec.label} saved.`);
  }

  async function connectMeta() {
    await feedback.run(async () => {
      const result = await api<{ authorization_url: string }>(
        `${prefix}/meta/connect/`,
        "POST",
      );
      window.location.assign(result.authorization_url);
    });
  }

  async function connectLinkedIn() {
    await feedback.run(async () => {
      const result = await api<{ authorization_url: string }>(
        `${prefix}/linkedin/connect/`,
        "POST",
      );
      window.location.assign(result.authorization_url);
    });
  }

  async function connectChannel(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = Object.fromEntries(new FormData(form));
    await feedback.run(async () => {
      await api(`${prefix}/channels/connect/`, "POST", {
        provider: data.provider,
        external_account_id: data.external_account_id,
        display_name: data.display_name,
        access_token: data.access_token || "",
        is_test: data.is_test === "on",
      });
      await load();
      form.reset();
    }, "Connection requested. Verification runs in the background.");
  }

  async function disconnect(connection: Connection) {
    if (!window.confirm(`Disconnect ${connection.display_name}?`)) return;
    await feedback.run(async () => {
      await api(`${prefix}/channels/${connection.id}/disconnect/`, "POST", {});
      await load();
    }, "Channel disconnected.");
  }

  async function simulate(
    event: FormEvent<HTMLFormElement>,
    connection: Connection,
  ) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = Object.fromEntries(new FormData(form));
    await feedback.run(async () => {
      await api(`${prefix}/channels/${connection.id}/simulate/`, "POST", {
        text: data.text,
        kind: data.kind,
        sender_id: data.sender_id || "test-lead",
      });
      form.reset();
    }, "Test message queued. It appears in the inbox within seconds.");
  }

  async function createKey(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const scopes = ["read", "write"].filter(
      (scope) => data.get(scope) === "on",
    );
    await feedback.run(async () => {
      const created = await api<APIKey>(`${prefix}/api-keys/`, "POST", {
        name: data.get("name"),
        scopes,
      });
      // An API key is how an AI tool connector (Claude MCP and the like) plugs in,
      // so creating one is the tour's last step.
      tourStep(workspace.id, "claude-mcp", "completed");
      setKeys((list) => [created, ...list]);
      setNewKey(created.key || "");
      form.reset();
    }, "API key created. Copy it now; it will not be shown again.");
  }

  async function revokeKey(key: APIKey) {
    if (!window.confirm(`Revoke ${key.name}? Integrations using it will stop.`))
      return;
    await feedback.run(async () => {
      await api(`${prefix}/api-keys/${key.id}/`, "DELETE");
      setKeys((list) => list.filter((item) => item.id !== key.id));
      setNewKey("");
    }, "API key revoked.");
  }

  async function createSubscription(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const events = WEBHOOK_EVENTS.filter((name) => data.get(name) === "on");
    await feedback.run(async () => {
      const created = await api<WebhookSubscription>(
        `${prefix}/webhooks/`,
        "POST",
        { url: data.get("url"), events },
      );
      setSubscriptions((list) => [created, ...list]);
      setNewSecret(created.secret || "");
      setNewToken(created.token || "");
      form.reset();
    }, "Webhook subscribed. Copy the signing secret now.");
  }

  async function removeSubscription(subscription: WebhookSubscription) {
    if (!window.confirm("Remove this webhook subscription?")) return;
    await feedback.run(async () => {
      await api(`${prefix}/webhooks/${subscription.id}/`, "DELETE");
      setSubscriptions((list) =>
        list.filter((item) => item.id !== subscription.id),
      );
      setNewSecret("");
    }, "Webhook removed.");
  }

  const spec = configuring ? PROVIDERS[configuring] : null;
  const existing = configuring ? integrationFor(configuring) : undefined;

  return (
    <>
      <TourMarker workspaceId={workspace.id} step="apps" />
      <PageHeading
        eyebrow="Integrations"
        title="Plug into your stack."
        text="Calendars, CRMs, notifications, channels, and the public API."
      />
      <ErrorNotice error={feedback.error} />
      <SuccessNotice notice={feedback.notice} />
      {loading ? (
        <p className="loading-text">Loading integrations…</p>
      ) : !manager ? (
        <Panel title="Integrations">
          <Empty>Owners and admins manage integrations and channels.</Empty>
        </Panel>
      ) : (
        <div className="stack">
          <Panel title="Integrations" aside="Credentials are encrypted at rest">
            <div className="card-grid">
              {Object.entries(PROVIDERS).map(([provider, item]) => {
                const current = integrationFor(provider);
                return (
                  <div className="card" key={provider}>
                    <div className="row between">
                      <h3>{item.label}</h3>
                      {current ? (
                        <Pill tone={integrationTone(current)}>
                          {integrationLabel(current)}
                        </Pill>
                      ) : (
                        <Pill>not set up</Pill>
                      )}
                    </div>
                    <p className="muted-text">{item.blurb}</p>
                    <div className="form-actions">
                      {item.oauth && (
                        <button
                          className="button small primary"
                          disabled={feedback.busy}
                          onClick={() => connectOAuth(provider)}
                        >
                          {current?.status === "reconnect_required"
                            ? "Reconnect"
                            : item.oauth}
                          <Plug size={14} />
                        </button>
                      )}
                      <button
                        className="button small secondary"
                        onClick={() => {
                          setTestMode(Boolean(current?.is_test));
                          setConfiguring(provider);
                        }}
                      >
                        {current
                          ? "Update"
                          : item.oauth
                            ? "Enter manually"
                            : "Configure"}
                        {!item.oauth && <Plug size={14} />}
                      </button>
                      {current?.configured && (
                        <button
                          className="button small secondary"
                          disabled={feedback.busy}
                          onClick={() => disconnectIntegration(current)}
                        >
                          Disconnect
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </Panel>

          <div className="two-col">
            <Panel title="Channels" aside={`${connections.length} connected`}>
              {connections.length ? (
                <div className="card-list">
                  {connections.map((connection) => (
                    <div className="card" key={connection.id}>
                      <div className="row between">
                        <div>
                          <strong>{connection.display_name}</strong>
                          <div className="muted-text">
                            {connection.provider} · expires{" "}
                            {when(connection.expires_at)}
                            {connection.locked && (
                              <>
                                {" "}
                                · <Pill tone="warn">locked by plan</Pill>
                              </>
                            )}
                          </div>
                        </div>
                        <Pill
                          tone={
                            connection.is_test
                              ? "neutral"
                              : statusTone(connection.status)
                          }
                        >
                          {connection.is_test ? "test" : connection.status}
                        </Pill>
                      </div>
                      {connection.is_test && connection.status === "active" && (
                        <form
                          className="form-grid"
                          onSubmit={(event) => simulate(event, connection)}
                        >
                          <label>
                            Simulate an inbound message
                            <input
                              name="text"
                              maxLength={2000}
                              placeholder="e.g. What is the price?"
                              required
                            />
                          </label>
                          <div className="row">
                            <select
                              name="kind"
                              defaultValue="dm"
                              aria-label="Kind"
                            >
                              <option value="dm">DM</option>
                              <option value="comment">Comment</option>
                              <option value="story_reply">Story reply</option>
                              <option value="live_comment">Live comment</option>
                            </select>
                            <input
                              name="sender_id"
                              maxLength={100}
                              placeholder="Sender ID (test-lead)"
                              aria-label="Sender ID"
                            />
                            <button
                              className="button small primary"
                              disabled={feedback.busy}
                            >
                              Send
                              <Send size={14} />
                            </button>
                          </div>
                        </form>
                      )}
                      {connection.status !== "disconnected" && (
                        <div className="form-actions">
                          <button
                            className="button small danger"
                            disabled={feedback.busy}
                            onClick={() => disconnect(connection)}
                          >
                            Disconnect
                          </button>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <Empty>
                  No channels yet. Instagram connects from the Overview; other
                  channels are added here.
                </Empty>
              )}
              <details style={{ marginTop: 20 }}>
                <summary style={{ cursor: "pointer", fontWeight: 600, color: "var(--muted)", fontSize: "0.9rem" }}>
                  Advanced: Webhook URLs for Custom Apps & Verification
                </summary>
                <div style={{ marginTop: 12 }}>
                  <p className="muted-text">
                    For custom apps or developers hosting their own webhook subscriptions. Telegram and LinkedIn register webhooks automatically.
                  </p>
                  {["instagram", "whatsapp", "messenger", "linkedin", "snapchat"].map((provider) => (
                    <CopyField
                      key={provider}
                      label={`${provider} webhook URL`}
                      value={`${origin}/webhooks/${provider}/`}
                    />
                  ))}
                </div>
              </details>
            </Panel>
            <div className="stack">
              <Panel title="Connect a channel">
                <div style={{ marginBottom: 20 }}>
                  <p className="muted-text" style={{ marginBottom: 12 }}>
                    Connect your business accounts with one click. No developer tokens or technical setup required.
                  </p>
                  <div className="row wrap" style={{ gap: 10 }}>
                    <button
                      type="button"
                      className="button primary"
                      disabled={feedback.busy}
                      onClick={connectMeta}
                    >
                      <Plug size={16} />
                      Connect Instagram & Messenger
                    </button>
                    <button
                      type="button"
                      className="button primary"
                      disabled={feedback.busy}
                      onClick={connectLinkedIn}
                    >
                      <Plug size={16} />
                      Connect LinkedIn Page
                    </button>
                  </div>
                </div>

                <details style={{ marginTop: 16, borderTop: "1px solid var(--border)", paddingTop: 14 }}>
                  <summary style={{ cursor: "pointer", fontWeight: 600, color: "var(--muted)", fontSize: "0.9rem" }}>
                    Advanced: Manual Credentials & Developer Channels
                  </summary>
                  <form className="form-grid" onSubmit={connectChannel} style={{ marginTop: 14 }}>
                    <label>
                      Provider
                      <select name="provider" defaultValue="whatsapp">
                        {CHANNEL_PROVIDERS.map((item) => (
                          <option key={item.id} value={item.id}>
                            {item.label}
                          </option>
                        ))}
                      </select>
                      <span className="hint">
                        {CHANNEL_PROVIDERS.map(
                          (item) => `${item.label}: ${item.account}`,
                        ).join(" · ")}
                      </span>
                    </label>
                    <label>
                      Account ID
                      <input
                        name="external_account_id"
                        maxLength={200}
                        pattern="[A-Za-z0-9_\-]{1,200}"
                        required
                      />
                    </label>
                    <label>
                      Display name
                      <input name="display_name" maxLength={150} required />
                    </label>
                    <label>
                      Access token
                      <input
                        name="access_token"
                        type="password"
                        autoComplete="off"
                        maxLength={4000}
                      />
                      <span className="hint">
                        Required for live connections; leave empty for a test
                        channel.
                      </span>
                    </label>
                    <label className="inline">
                      <input type="checkbox" name="is_test" />
                      Create a local test channel (no provider calls)
                    </label>
                    <div className="form-actions">
                      <button className="button primary" disabled={feedback.busy}>
                        Connect
                        <Plus size={16} />
                      </button>
                    </div>
                  </form>
                </details>
              </Panel>
              <Panel title="Recent deliveries" aside={`${deliveries.length}`}>
                {deliveries.length ? (
                  <Table
                    head={["When", "Recipient", "Status", "Attempts", "Error"]}
                  >
                    {deliveries.slice(0, 20).map((delivery) => (
                      <tr key={delivery.id}>
                        <td>{when(delivery.created_at)}</td>
                        <td className="mono">{delivery.recipient_id}</td>
                        <td>
                          <Pill tone={statusTone(delivery.status)}>
                            {delivery.status}
                          </Pill>
                        </td>
                        <td>{delivery.attempts}</td>
                        <td className="mono">{delivery.error_code || "—"}</td>
                      </tr>
                    ))}
                  </Table>
                ) : (
                  <Empty>Nothing sent yet.</Empty>
                )}
              </Panel>
            </div>
          </div>

          <Panel title="Connectors" aside="Zapier · n8n · Make">
            <p className="small">
              Ready-made connectors live in the repository under{" "}
              <code>connectors/</code>. Each one needs this app&apos;s URL and
              an API key from below (instant triggers need the{" "}
              <code>write</code> scope).
            </p>
            <div>
              {[
                [
                  "Zapier",
                  "connectors/zapier",
                  "One instant trigger per event, plus send message, update lead and find lead. Verifies webhook signatures.",
                ],
                [
                  "n8n",
                  "connectors/n8n",
                  "Community node package: Nemio Trigger and a lead/conversation/message node. Verifies webhook signatures.",
                ],
                [
                  "Make",
                  "connectors/make",
                  "Custom app: Watch Events instant trigger, send message, update lead, search leads.",
                ],
              ].map(([name, path, text]) => (
                <div className="list-row" key={name}>
                  <strong>{name}</strong>
                  <code>{path}</code>
                  <span className="muted-text">{text}</span>
                </div>
              ))}
            </div>
          </Panel>

          <div className="two-col">
            <Panel title="API keys" aside="Header: X-API-Key">
              {keys.length ? (
                <Table head={["Name", "Prefix", "Scopes", "Last used", ""]}>
                  {keys.map((key) => (
                    <tr key={key.id}>
                      <td>
                        <strong>{key.name}</strong>
                        <div className="muted-text">
                          Created {when(key.created_at)}
                        </div>
                      </td>
                      <td className="mono">{key.prefix}…</td>
                      <td>
                        <span className="tag-list">
                          {key.scopes.map((scope) => (
                            <Pill key={scope}>{scope}</Pill>
                          ))}
                        </span>
                      </td>
                      <td>{when(key.last_used_at)}</td>
                      <td>
                        {owner && (
                          <button
                            className="text-button"
                            disabled={feedback.busy}
                            onClick={() => revokeKey(key)}
                          >
                            Revoke
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </Table>
              ) : (
                <Empty>No API keys yet.</Empty>
              )}
              {newKey && (
                <>
                  <CopyField label="New API key (shown once)" value={newKey} />
                  <p className="muted-text">
                    Store it now. Nemio keeps only a hash and cannot show it
                    again.
                  </p>
                </>
              )}
              {owner ? (
                <form
                  className="form-grid"
                  style={{ marginTop: 16 }}
                  onSubmit={createKey}
                >
                  <label>
                    Key name
                    <input
                      name="name"
                      maxLength={80}
                      placeholder="Zapier"
                      required
                    />
                  </label>
                  <div className="checkbox-grid">
                    <label>
                      <input type="checkbox" name="read" defaultChecked />
                      Read
                    </label>
                    <label>
                      <input type="checkbox" name="write" />
                      Write
                    </label>
                  </div>
                  <div className="form-actions">
                    <button className="button primary" disabled={feedback.busy}>
                      Create key
                      <KeyRound size={16} />
                    </button>
                  </div>
                </form>
              ) : (
                <p className="muted-text" style={{ marginTop: 14 }}>
                  Only the workspace owner can create or revoke keys.
                </p>
              )}
            </Panel>
            <Panel title="Outbound webhooks" aside="REST hooks">
              <p className="muted-text">
                Zapier, n8n and Make subscribe here (or through the API) and
                receive signed POSTs. Verify{" "}
                <code>
                  X-Nemio-Signature: t=…,v1=HMAC-SHA256(secret, t +
                  &quot;.&quot; + body)
                </code>
                .
              </p>
              {subscriptions.length ? (
                <div className="card-list" style={{ marginTop: 12 }}>
                  {subscriptions.map((subscription) => (
                    <div className="card" key={subscription.id}>
                      <div className="row between">
                        <strong className="mono">{subscription.url}</strong>
                        <Pill tone={subscription.active ? "good" : "bad"}>
                          {subscription.active ? "active" : "disabled"}
                        </Pill>
                      </div>
                      <span className="tag-list">
                        {subscription.events.map((name) => (
                          <Pill key={name}>{name}</Pill>
                        ))}
                      </span>
                      <span className="muted-text">
                        {subscription.failure_count} consecutive failures · last
                        delivered {when(subscription.last_delivered_at)}
                      </span>
                      <div className="form-actions">
                        <button
                          className="button small danger"
                          disabled={feedback.busy}
                          onClick={() => removeSubscription(subscription)}
                        >
                          Remove
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <Empty>No subscriptions yet.</Empty>
              )}
              {newSecret && (
                <CopyField
                  label="Signing secret (shown once)"
                  value={newSecret}
                />
              )}
              {newToken && (
                <CopyField
                  label="Shared token for receivers that cannot verify HMAC, e.g. Make (shown once)"
                  value={newToken}
                />
              )}
              <form
                className="form-grid"
                style={{ marginTop: 16 }}
                onSubmit={createSubscription}
              >
                <label>
                  Endpoint URL
                  <input
                    name="url"
                    type="url"
                    placeholder="https://hooks.zapier.com/…"
                    required
                  />
                  <span className="hint">Public HTTPS only.</span>
                </label>
                <div className="checkbox-grid">
                  {WEBHOOK_EVENTS.map((name) => (
                    <label key={name}>
                      <input type="checkbox" name={name} />
                      {name}
                    </label>
                  ))}
                </div>
                <div className="form-actions">
                  <button className="button primary" disabled={feedback.busy}>
                    Subscribe
                    <Webhook size={16} />
                  </button>
                </div>
              </form>
              {hookLog.length > 0 && (
                <div style={{ marginTop: 18 }}>
                  <Table head={["When", "Event", "Status", "Attempts", "Code"]}>
                    {hookLog.slice(0, 20).map((entry) => (
                      <tr key={entry.id}>
                        <td>{when(entry.created_at)}</td>
                        <td className="mono">{entry.event}</td>
                        <td>
                          <Pill tone={statusTone(entry.status)}>
                            {entry.status}
                          </Pill>
                        </td>
                        <td>{entry.attempts}</td>
                        <td>{entry.response_code ?? "—"}</td>
                      </tr>
                    ))}
                  </Table>
                </div>
              )}
            </Panel>
          </div>
        </div>
      )}

      {spec && (
        <Modal title={spec.label} onClose={() => setConfiguring("")}>
          <p className="muted-text">{spec.blurb}</p>
          <form className="form-grid" onSubmit={saveIntegration}>
            <label className="inline">
              <input
                type="checkbox"
                name="is_test"
                checked={testMode}
                onChange={(event) => setTestMode(event.target.checked)}
              />
              Use local test integration (no credentials)
            </label>
            {!testMode &&
              spec.credentials.map((field) => (
                <label key={field.key}>
                  {field.label}
                  <input
                    name={`cred_${field.key}`}
                    type={field.secret ? "password" : "text"}
                    autoComplete="off"
                    placeholder={
                      existing?.configured ? "Leave blank to keep current" : ""
                    }
                    required={!existing?.configured}
                  />
                </label>
              ))}
            {spec.options.map((field) => (
              <label key={field.key}>
                {field.label}
                <input
                  name={`opt_${field.key}`}
                  defaultValue={existing?.options?.[field.key] || ""}
                />
              </label>
            ))}
            <label className="inline">
              <input
                type="checkbox"
                name="enabled"
                defaultChecked={existing ? existing.enabled : true}
              />
              Enabled
            </label>
            <div className="form-actions">
              <button className="button primary" disabled={feedback.busy}>
                {feedback.busy ? "Saving…" : "Save"}
              </button>
              <button
                type="button"
                className="button secondary"
                onClick={() => setConfiguring("")}
              >
                Cancel
              </button>
            </div>
          </form>
        </Modal>
      )}
    </>
  );
}
