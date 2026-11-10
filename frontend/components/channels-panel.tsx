"use client";

import { useConfirmation } from "@/components/confirmation-provider";

import {
  ValidatedForm,
  ValidatedInput,
  ValidatedSelect,
} from "@/components/validated-form";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { Plug, Plus, Send } from "lucide-react";
import { api, message, when, type Connection, type Delivery, type Page } from "@/lib/api";
import { ChannelIcon, channelLabel } from "@/lib/channels";
import { WhatsAppConnect } from "@/components/whatsapp-connect";
import { TelegramConnect } from "@/components/telegram-connect";
import { useWorkspace } from "@/lib/workspace";
import {
  CopyField,
  Empty,
  ErrorNotice,
  Panel,
  Pill,
  statusTone,
  SuccessNotice,
  Table,
  useFeedback,
} from "@/components/ui";

/** Channels connected by hand (no OAuth) and what their account ID is. */
const CHANNEL_PROVIDERS = [
  { id: "whatsapp", label: "WhatsApp Business", account: "Phone number ID" },
  { id: "telegram", label: "Telegram Bot", account: "Bot user ID" },
  { id: "linkedin", label: "LinkedIn Company Page", account: "Organization URN" },
  { id: "instagram", label: "Instagram", account: "Instagram account ID" },
  { id: "messenger", label: "Facebook Messenger", account: "Facebook Page ID" },
];

/** Connected channels: one-click Meta and LinkedIn, manual and local test channels, a
 * test-message simulator, and the latest outbound deliveries. */
export function ChannelsPanel({ prefix, manager }: { prefix: string; manager: boolean }) {
  const { workspace } = useWorkspace();
  const [connections, setConnections] = useState<Connection[]>([]);
  const [deliveries, setDeliveries] = useState<Delivery[]>([]);
  const [deliveryPage, setDeliveryPage] = useState(1);
  const [deliveryCount, setDeliveryCount] = useState(0);
  const [manualProvider, setManualProvider] = useState("whatsapp");
  const [queuedTest, setQueuedTest] = useState(false);
  const confirm = useConfirmation();
  const feedback = useFeedback();
  const origin = typeof window === "undefined" ? "" : window.location.origin;
  const [testChannelsEnabled, setTestChannelsEnabled] = useState(false);
  const [linkedinAvailable, setLinkedinAvailable] = useState(false);

  const loadDeliveries = useCallback(async (page: number, signal?: AbortSignal) => {
    const result = await api<Page<Delivery> | Delivery[]>(
      `${prefix}/deliveries/?page=${page}`, "GET", undefined, signal,
    );
    setDeliveries(Array.isArray(result) ? result.slice((page - 1) * 5, page * 5) : result.results);
    setDeliveryCount(Array.isArray(result) ? result.length : result.count);
    setDeliveryPage(page);
  }, [prefix]);

  const load = useCallback(
    async (signal?: AbortSignal) => {
      const [channels] = await Promise.all([
        api<Page<Connection>>(`${prefix}/connections/`, "GET", undefined, signal),
        manager
          ? loadDeliveries(1, signal)
          : Promise.resolve(),
      ]);
      setConnections(channels.results);
      const status = await api<{ test_channels_enabled?: boolean; linkedin_available?: boolean }>(`${prefix}/status/`, "GET", undefined, signal);
      setTestChannelsEnabled(status.test_channels_enabled === true);
      setLinkedinAvailable(status.linkedin_available === true);
    },
    [prefix, manager, loadDeliveries],
  );

  useEffect(() => {
    const controller = new AbortController();
    queueMicrotask(() =>
      load(controller.signal).catch((err) => {
        if (!controller.signal.aborted) feedback.setError(message(err));
      }),
    );
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [load]);

  async function connectOAuth(path: "meta" | "linkedin") {
    await feedback.run(async () => {
      const result = await api<{ authorization_url: string }>(
        `${prefix}/${path}/connect/`,
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
        ...(data.business_account_id ? { business_account_id: data.business_account_id } : {}),
        is_test: data.is_test === "on",
      });
      await load();
      form.reset();
    }, "Connection requested. Verification runs in the background.");
  }

  async function addTestChannel(provider: string) {
    await feedback.run(async () => {
      await api(`${prefix}/channels/connect/`, "POST", {
        provider,
        external_account_id: `test-${provider}-${crypto.randomUUID()}`,
        display_name: `${channelLabel(provider)} test account`,
        is_test: true,
      });
      await load();
    }, "Test account ready. Use its simulation form to send a message or comment.");
  }

  async function disconnect(connection: Connection) {
    if (!await confirm(`Disconnect ${connection.display_name}?`)) return;
    await feedback.run(async () => {
      await api(`${prefix}/channels/${connection.id}/disconnect/`, "POST", {});
      await load();
    }, "Channel disconnected.");
  }

  async function simulate(event: FormEvent<HTMLFormElement>, connection: Connection) {
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
      setQueuedTest(true);
    }, "Test message queued. It appears in the inbox within seconds.");
  }

  async function removeChannel(connection: Connection) {
    if (!await confirm(`Permanently remove ${connection.display_name}? This deletes its linked conversations, messages, delivery history, scheduled posts, and channel-specific records from Instantlify. Contacts remain. This cannot be undone.`)) return;
    await feedback.run(async () => {
      await api(`${prefix}/channels/${connection.id}/`, "DELETE", { confirm_delete: true });
      await load();
    }, "Channel permanently removed.");
  }

  return (
    <div className="channels-panel">
      <ErrorNotice error={feedback.error} />
      <SuccessNotice notice={feedback.notice} />
      {queuedTest && (
        <Link className="text-button" href={`/w/${workspace.id}/inbox`}>
          Open Conversations to check the test reply
        </Link>
      )}
      <div className="channels-panel-grid">
        <Panel title="Connected channels" aside={`${connections.length} connected`}>
          {connections.length ? (
            <div className="card-list">
              {connections.map((connection) => (
                <div className="card channel-card" key={connection.id}>
                  <div className="row between">
                    <div className="channel-card-title">
                      <ChannelIcon provider={connection.provider} size={20} />
                      <div>
                        <strong>{connection.display_name}</strong>
                        <div className="muted-text">
                          {channelLabel(connection.provider)} · expires{" "}
                          {when(connection.expires_at)}
                          {connection.locked && (
                            <>
                              {" "}
                              · <Pill tone="warn">locked by plan</Pill>
                            </>
                          )}
                        </div>
                      </div>
                    </div>
                    <Pill tone={statusTone(connection.status)}>
                      {connection.is_test ? "Test" : "Live"} ·{" "}
                      {connection.locked
                        ? "Locked"
                        : connection.status === "active"
                          ? "Connected"
                          : connection.status === "setup_required"
                            ? "Finish setup"
                            : connection.status.replaceAll("_", " ")}
                    </Pill>
                  </div>
                  {!connection.is_test && !connection.locked && connection.status !== "active" && (
                    <p className="muted-text">
                      {connection.status === "pending"
                        ? "Verification is pending. Refresh this page to check again."
                        : connection.provider === "whatsapp"
                          ? "Use WhatsApp setup below to finish or reconnect this account."
                          : "Reconnect this account from Connect a channel using the same account details."}
                    </p>
                  )}
                  {manager && connection.is_test && connection.status === "active" && !connection.locked && (
                    <ValidatedForm fieldErrors={feedback.fieldErrors} validationTarget={feedback.validationTarget} onEdit={() => feedback.setError("")}
                      className="channel-simulate"
                      onSubmit={(event) => simulate(event, connection)}
                    >
                      <label>
                        Simulate an inbound message
                        <ValidatedInput
                          name="text"
                          maxLength={2000}
                          placeholder="e.g. What is the price?"
                          required
                        />
                      </label>
                      <div className="row">
                        <ValidatedSelect name="kind" defaultValue="dm" aria-label="Kind">
                          <option value="dm">DM</option>
                          <option value="comment">Comment</option>
                          <option value="story_reply">Story reply</option>
                          <option value="live_comment">Live comment</option>
                        </ValidatedSelect>
                        <ValidatedInput
                          name="sender_id"
                          maxLength={100}
                          placeholder="Sender ID (test-lead)"
                          aria-label="Sender ID"
                        />
                        <button className="button small primary" disabled={feedback.busy}>
                          Send <Send size={14} />
                        </button>
                      </div>
                    </ValidatedForm>
                  )}
                  {workspace.role === "owner" && connection.status === "disconnected" && (
                    <div className="stack">
                      <p className="muted-text">You can permanently remove this channel and its linked conversation history.</p>
                      <button type="button" className="button small danger" disabled={feedback.busy} onClick={() => removeChannel(connection)}>Remove channel</button>
                    </div>
                  )}
                  {manager && (connection.status !== "disconnected" || connection.provider === "whatsapp") && (
                    <div className="form-actions">
                      {connection.provider === "whatsapp" && !connection.is_test && (
                        <WhatsAppConnect prefix={prefix} connection={connection} onConnected={load} />
                      )}
                      {connection.status !== "disconnected" && <button
                        type="button"
                        className="button small danger"
                        disabled={feedback.busy}
                        onClick={() => disconnect(connection)}
                      >
                        Disconnect
                      </button>}
                    </div>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <Empty>No channels yet. Connect one to start receiving conversations.</Empty>
          )}
        </Panel>

        {manager && (
          <div className="stack">
            {testChannelsEnabled && <Panel title="Test without platform credentials">
              <p className="muted-text">Create a simulated account, send a test DM or comment, then open Conversations to test replies and assignment. Messages stay inside Instantlify and are not delivered to a real platform.</p>
              <div className="row wrap channel-connect-buttons">
                {CHANNEL_PROVIDERS.map((provider) => <button key={provider.id} type="button" className="button secondary" disabled={feedback.busy} onClick={() => addTestChannel(provider.id)}>
                  <Plus size={16} /> Test {provider.label}
                </button>)}
              </div>
            </Panel>}
            <Panel title="Connect a channel">
              <p className="muted-text">
                Connect your business accounts. Telegram only needs your bot token from BotFather.
              </p>
              <div className="row wrap channel-connect-buttons">
                <WhatsAppConnect key={prefix} prefix={prefix} onConnected={load} />
                <TelegramConnect key={`telegram-${prefix}`} prefix={prefix} onConnected={load} />
                <button
                  type="button"
                  className="button primary"
                  disabled={feedback.busy}
                  onClick={() => connectOAuth("meta")}
                >
                  <Plug size={16} /> Connect Instagram &amp; Messenger
                </button>
                {linkedinAvailable && (
                  <button
                    type="button"
                    className="button secondary"
                    disabled={feedback.busy}
                    onClick={() => connectOAuth("linkedin")}
                  >
                    <Plug size={16} /> Connect LinkedIn Page
                  </button>
                )}
              </div>
              <details className="channel-advanced">
                <summary>Advanced: manual credentials and test channels</summary>
                <ValidatedForm fieldErrors={feedback.fieldErrors} validationTarget={feedback.validationTarget} onEdit={() => feedback.setError("")} className="form-grid" onSubmit={connectChannel}>
                  <label>
                    Provider
                    <ValidatedSelect name="provider" value={manualProvider} onChange={(event) => setManualProvider(event.target.value)}>
                      {CHANNEL_PROVIDERS.map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.label}
                        </option>
                      ))}
                    </ValidatedSelect>
                    <span className="hint">
                      {CHANNEL_PROVIDERS.map((item) => `${item.label}: ${item.account}`).join(
                        " · ",
                      )}
                    </span>
                  </label>
                  <label>
                    Account ID
                    <ValidatedInput
                      name="external_account_id"
                      maxLength={200}
                      pattern="[A-Za-z0-9_\-]{1,200}"
                      required
                    />
                  </label>
                  {manualProvider === "whatsapp" && <label>
                    WhatsApp business account ID
                    <ValidatedInput name="business_account_id" aria-label="WhatsApp business account ID" pattern="[0-9]{1,40}" maxLength={40} />
                    <span className="hint">From Meta’s WhatsApp API setup. Add this to load approved messages and enable notifications for your own account. This is different from your phone number ID.</span>
                  </label>}
                  <label>
                    Display name
                    <ValidatedInput name="display_name" maxLength={150} required />
                  </label>
                  <label>
                    Access token
                    <ValidatedInput
                      name="access_token"
                      type="password"
                      autoComplete="off"
                      maxLength={4000}
                    />
                    <span className="hint">
                      Required for live connections; leave empty for a test channel.
                    </span>
                  </label>
                  <label className="inline">
                    <ValidatedInput type="checkbox" name="is_test" />
                    Create a local test channel (no provider calls)
                  </label>
                  <div className="form-actions">
                    <button className="button primary" disabled={feedback.busy}>
                      Connect <Plus size={16} />
                    </button>
                  </div>
                </ValidatedForm>
                <div className="channel-webhooks">
                  <p className="muted-text">
                    Webhook URLs for custom apps. Telegram registers its webhook
                    automatically. LinkedIn webhook registration is not automatic.
                  </p>
                  {["instagram", "whatsapp", "messenger", ...(linkedinAvailable ? ["linkedin"] : [])].map(
                    (provider) => (
                      <CopyField
                        key={provider}
                        label={`${channelLabel(provider)} webhook URL`}
                        value={`${origin}/webhooks/${provider}/`}
                      />
                    ),
                  )}
                </div>
              </details>
            </Panel>

            <Panel title="Recent deliveries" aside={`${deliveryCount}`}>
              {deliveries.length ? (
                <Table head={["When", "Recipient", "Status", "Attempts", "Error"]}>
                  {deliveries.map((delivery) => (
                    <tr key={delivery.id}>
                      <td>{when(delivery.created_at)}</td>
                      <td className="mono">{delivery.recipient_id}</td>
                      <td>
                        <Pill tone={statusTone(delivery.status)}>{delivery.status}</Pill>
                      </td>
                      <td>{delivery.attempts}</td>
                      <td className="mono">{delivery.error_code || "—"}</td>
                    </tr>
                  ))}
                </Table>
              ) : (
                <Empty>Nothing sent yet.</Empty>
              )}
              {deliveryCount > 0 && (
                <nav aria-label="Delivery pagination" className="row" style={{ justifyContent: "space-between", flexWrap: "wrap", marginTop: 16 }}>
                  <button type="button" className="button secondary small" disabled={feedback.busy || deliveryPage === 1} onClick={() => void feedback.run(() => loadDeliveries(deliveryPage - 1))}>Previous</button>
                  <span className="muted-text" aria-live="polite">
                    {(deliveryPage - 1) * 5 + 1}–{Math.min(deliveryPage * 5, deliveryCount)} of {deliveryCount}
                  </span>
                  <button type="button" className="button secondary small" disabled={feedback.busy || deliveryPage * 5 >= deliveryCount} onClick={() => void feedback.run(() => loadDeliveries(deliveryPage + 1))}>Next</button>
                </nav>
              )}
            </Panel>
          </div>
        )}
      </div>
    </div>
  );
}
