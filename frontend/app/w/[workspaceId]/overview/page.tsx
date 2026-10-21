"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  Activity,
  ArrowRight,
  Check,
  Instagram,
  MessageCircle,
  ShieldCheck,
  Sparkles,
  CalendarCheck,
  CreditCard,
} from "lucide-react";
import {
  api,
  type Audit,
  type Connection,
  type Funnel,
  type Page,
  type Status,
  type Telemetry,
} from "@/lib/api";
import {
  ChannelBadge,
  channelLabel,
  META_CHANNELS,
  switchable,
  tokenHealth,
} from "@/lib/channels";
import { Sparkline } from "@/components/sparkline";
import { useWorkspace } from "@/lib/workspace";
import {
  Empty,
  ErrorNotice,
  Panel,
  Pill,
  Stat,
  statusTone,
  SuccessNotice,
  Table,
  useFeedback,
} from "@/components/ui";
import { ActivityList } from "@/components/activity";
import { ConnectPrompt } from "@/components/growth";

export default function OverviewPage() {
  const { workspace, user, prefix, manager } = useWorkspace();
  const [connections, setConnections] = useState<Connection[]>([]);
  const [status, setStatus] = useState<Status | null>(null);
  const [events, setEvents] = useState<Audit[]>([]);
  const [funnel, setFunnel] = useState<Funnel | null>(null);
  const [telemetry, setTelemetry] = useState<Telemetry | null>(null);
  const [checkedAt, setCheckedAt] = useState(() => Date.now());
  const [loading, setLoading] = useState(true);
  const feedback = useFeedback();
  const load = useCallback(
    async (signal?: AbortSignal) => {
      const [channels, health] = await Promise.all([
        api<Page<Connection>>(
          `${prefix}/connections/`,
          "GET",
          undefined,
          signal,
        ),
        api<Status>(`${prefix}/status/`, "GET", undefined, signal),
      ]);
      setConnections(channels.results);
      setStatus(health);
      setCheckedAt(Date.now());
      if (manager) {
        const [audit, report, metrics] = await Promise.all([
          api<Page<Audit>>(`${prefix}/audit/`, "GET", undefined, signal),
          api<Funnel>(
            `${prefix}/analytics/funnel/?period=7d`,
            "GET",
            undefined,
            signal,
          ),
          api<Telemetry>(`${prefix}/telemetry/`, "GET", undefined, signal),
        ]);
        setEvents(audit.results);
        setFunnel(report);
        setTelemetry(metrics);
      }
    },
    [prefix, manager],
  );
  useEffect(() => {
    const controller = new AbortController();
    queueMicrotask(() =>
      load(controller.signal)
        .catch((err) => {
          if (!controller.signal.aborted)
            feedback.setError(String((err as Error).message));
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        }),
    );
    const timer = window.setInterval(
      () => load().catch(() => undefined),
      15000,
    );
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [load]);
  useEffect(() => {
    const flag = new URLSearchParams(window.location.search).get("connection");
    if (flag === "limit")
      feedback.setError(
        "Your plan's connected-account limit has been reached.",
      );
    else if (flag) feedback.setNotice("Channel connection updated.");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  async function connect() {
    await feedback.run(async () => {
      const result = await api<{ authorization_url: string }>(
        `${prefix}/meta/connect/`,
        "POST",
      );
      window.location.assign(result.authorization_url);
    });
  }
  const live = connections.filter(
    (item) => !item.is_test && item.status === "active",
  );
  const step = (kind: string) =>
    funnel?.steps.find((s) => s.kind === kind)?.leads ?? 0;
  return (
    <>
      <ConnectPrompt workspaceId={workspace.id} />
      <div className="page-heading">
        <div>
          <span className="eyebrow">{workspace.name.toUpperCase()}</span>
          <h1>
            Your business at a glance, {user.name.split(" ")[0] || "welcome"}.
          </h1>
          <p>Track new enquiries, see results and keep conversations moving.</p>
        </div>
        <span className="role-pill">{workspace.role}</span>
      </div>
      <ErrorNotice error={feedback.error} />
      <SuccessNotice notice={feedback.notice} />
      {loading ? (
        <p className="loading-text">Loading workspace details…</p>
      ) : (
        <>
          <ChannelRibbon
            connections={switchable(connections)}
            now={checkedAt}
            href={`/w/${workspace.id}/integrations`}
          />
          {manager && !funnel?.unique_leads && (
            <section className="welcome-banner">
              <div>
                <span className="banner-kicker">
                  <span className="small-dot" /> YOUR NEXT STEP
                </span>
                <h2>
                  Make your first
                  <br />
                  enquiry count.
                </h2>
                <p>
                  Start with a pricing reply, a qualifying question or your
                  booking link. Add your business knowledge and preview AI
                  answers before turning them on.
                </p>
                <Link
                  href={`/w/${workspace.id}/automations`}
                  className="button dark"
                >
                  Choose a starter workflow
                  <ArrowRight size={16} />
                </Link>
                <p>
                  <Link href={`/w/${workspace.id}/agent`}>
                    Set up and test your AI assistant →
                  </Link>
                </p>
              </div>
              <div className="banner-art" aria-hidden="true">
                <div className="orbit orbit-one" />
                <div className="orbit orbit-two" />
                <span className="floating-icon ig">
                  <Instagram size={30} />
                </span>
                <span className="floating-icon msg">
                  <MessageCircle size={28} />
                </span>
                <span className="floating-icon sparkle">
                  <Sparkles size={34} />
                </span>
                <span className="hello-card">
                  <span className="hello-dot" />
                  <span>Hello, possibilities.</span>
                  <Check size={16} />
                </span>
                <span className="art-star">✳</span>
              </div>
            </section>
          )}
          <div className="stats-grid">
            <Stat
              icon={<CalendarCheck size={19} />}
              value={funnel ? String(step("booked")) : "—"}
              label="Leads booked"
              detail={manager ? "This week" : "Visible to workspace admins"}
            />
            <Stat
              icon={<CreditCard size={19} />}
              value={funnel ? String(step("paid")) : "—"}
              label="Paying leads"
              detail={manager ? "This week" : "Visible to workspace admins"}
            />
            <Stat
              icon={<ShieldCheck size={19} />}
              value={funnel ? String(funnel.unique_leads ?? "—") : "Private"}
              label={funnel ? "Leads this week" : "Workspace access"}
              detail={
                funnel
                  ? `${step("booked")} booked · ${step("paid")} paid`
                  : "Only your members can enter"
              }
            />
          </div>
          {telemetry && <MetaTelemetry data={telemetry} />}
          <div className="overview-grid">
            <Panel
              title="Make yourself at home"
              aside="Getting started"
              id="channels"
            >
              <div className="checklist-row">
                <span className="step-check">
                  <Check size={17} />
                </span>
                <div>
                  <strong>Create your workspace</strong>
                  <p>{workspace.name} is ready for your team.</p>
                </div>
                <span className="done-tag">Done</span>
              </div>
              <div className="checklist-row">
                <span
                  className={connections.length ? "step-check" : "step-number"}
                >
                  {connections.length ? <Check size={17} /> : "2"}
                </span>
                <div>
                  <strong>Connect a channel</strong>
                  <p>Instagram, WhatsApp, Messenger or Telegram.</p>
                </div>
                <Instagram size={20} className="subtle" />
              </div>
              <div className="channel-box">
                <div className="channel-logo">
                  <Instagram size={23} />
                </div>
                <div>
                  <strong>Instagram</strong>
                  <p>
                    {connections.length
                      ? connections.some((c) => c.is_test)
                        ? "Local connection test completed"
                        : `${live.length} live account(s) connected`
                      : "Connect where conversations happen"}
                  </p>
                </div>
                <Pill tone={live.length ? "good" : "neutral"}>
                  {live.length ? "Live" : "Ready"}
                </Pill>
              </div>
              <div className="channel-note">
                <p>
                  Connect your Instagram account to receive enquiries. Manage
                  other channels and reconnect accounts under Business tools →
                  Integrations.
                </p>
                {manager && (
                  <button
                    className="text-button"
                    onClick={connect}
                    disabled={feedback.busy}
                  >
                    {feedback.busy ? "Connecting…" : "Connect Instagram"}
                    <ArrowRight size={15} />
                  </button>
                )}
              </div>
              {connections.length > 0 && (
                <div className="card-list" style={{ marginTop: 14 }}>
                  {connections.map((item) => (
                    <div className="list-row" key={item.id}>
                      <strong>{item.display_name}</strong>
                      <span className="muted-text">{item.provider}</span>
                      <span className="spacer" />
                      <Pill
                        tone={
                          item.is_test ? "neutral" : statusTone(item.status)
                        }
                      >
                        {item.is_test ? "test" : item.status}
                      </Pill>
                    </div>
                  ))}
                </div>
              )}
            </Panel>
            <details className="panel" style={{ alignSelf: "start" }}>
              <summary>Connection and service status</summary>
              <Panel
                title="Workspace pulse"
                aside={
                  <span className="pulse-icon">
                    <Activity size={17} />
                  </span>
                }
                className="health-panel"
              >
                <p className="panel-subtitle">
                  A live check on the essentials.
                </p>
                {Object.entries(status?.checks || {}).map(([name, ok]) => (
                  <div className="health-row" key={name}>
                    <span>
                      {name === "database"
                        ? "Data storage"
                        : name === "redis"
                          ? "Queue connection"
                          : "Background worker"}
                    </span>
                    <span className={ok ? "health-ok" : "health-wait"}>
                      <i />
                      {ok ? "Connected" : "Waiting"}
                    </span>
                  </div>
                ))}
                <div className="health-foot">
                  {status?.pending_jobs
                    ? `${status.pending_jobs} background job(s) pending`
                    : "No pending setup jobs"}
                  <span>Refreshes every 15 seconds</span>
                </div>
              </Panel>
            </details>
          </div>
          {telemetry && telemetry.channels.length > 0 && (
            <Panel
              title="Channel performance"
              aside="Last 14 days"
              className="channel-matrix"
            >
              <Table
                head={[
                  "Channel",
                  "Inbound messages",
                  "Conversations",
                  "Median first reply",
                  "Top trigger",
                ]}
              >
                {telemetry.channels.map((row) => (
                  <tr key={row.provider}>
                    <td>
                      <ChannelBadge provider={row.provider} />
                    </td>
                    <td className="num">{row.inbound}</td>
                    <td className="num">{row.conversations}</td>
                    <td className="num">
                      {row.median_response_minutes === null
                        ? "—"
                        : duration(row.median_response_minutes)}
                    </td>
                    <td>
                      {row.top_automation ? (
                        <>
                          {row.top_automation.name}{" "}
                          <span className="muted-text">
                            · {row.top_automation.runs} runs
                          </span>
                        </>
                      ) : (
                        <span className="muted-text">No triggers yet</span>
                      )}
                    </td>
                  </tr>
                ))}
              </Table>
            </Panel>
          )}
          <Panel
            title="Recent activity"
            aside={
              manager ? (
                <Link href={`/w/${workspace.id}/activity`}>View all</Link>
              ) : undefined
            }
            className="activity-preview"
          >
            {manager ? (
              events.length ? (
                <ActivityList events={events.slice(0, 5)} />
              ) : (
                <Empty>
                  Nothing yet. Activity appears here as your team works.
                </Empty>
              )
            ) : (
              <Empty>Workspace activity is visible to owners and admins.</Empty>
            )}
          </Panel>
        </>
      )}
    </>
  );
}

const duration = (minutes: number) =>
  minutes < 1
    ? "under 1 min"
    : minutes < 60
      ? `${Math.round(minutes)} min`
      : minutes < 60 * 24
        ? `${(minutes / 60).toFixed(1)} h`
        : `${(minutes / 60 / 24).toFixed(1)} days`;

const NOUNS: Record<string, [string, string]> = {
  instagram: ["account", "accounts"],
  messenger: ["Page", "Pages"],
  whatsapp: ["number", "numbers"],
};

/** Compact health ribbon: which Meta assets are connected and whether any need attention. */
function ChannelRibbon({
  connections,
  now,
  href,
}: {
  connections: Connection[];
  now: number;
  href: string;
}) {
  const reconnect = connections.filter(
    (item) => tokenHealth(item, now) === "reconnect",
  ).length;
  const expiring = connections.filter(
    (item) => tokenHealth(item, now) === "expiring",
  ).length;
  return (
    <section className="channel-ribbon" aria-label="Meta channel status">
      {META_CHANNELS.map((provider) => {
        const items = connections.filter((item) => item.provider === provider);
        const [one, many] = NOUNS[provider];
        return (
          <span
            key={provider}
            className={`ribbon-item ${items.length ? "" : "off"}`}
          >
            <ChannelBadge provider={provider} compact />
            <strong>{channelLabel(provider)}:</strong>{" "}
            {!items.length
              ? "Not connected"
              : provider === "instagram" && items.length === 1
                ? `Connected (${items[0].display_name})`
                : `${items.length} ${items.length === 1 ? one : many}`}
          </span>
        );
      })}
      <Link
        href={href}
        className={`ribbon-link ${reconnect || expiring ? "warn" : ""}`}
      >
        {reconnect
          ? `${reconnect} need${reconnect === 1 ? "s" : ""} reconnecting`
          : expiring
            ? `${expiring} token${expiring === 1 ? "" : "s"} expiring soon`
            : "Manage channels"}
        <ArrowRight size={13} />
      </Link>
    </section>
  );
}

const percent = (value: number) => `${Math.round(value * 100)}%`;

function MetaTelemetry({ data }: { data: Telemetry }) {
  const inbound = data.days.map((day) => ({
    date: day.date,
    value: day.instagram + day.messenger + day.whatsapp + day.other,
  }));
  const contacts = data.days.map((day) => ({
    date: day.date,
    value: day.contacts,
  }));
  return (
    <div className="telemetry-grid">
      <article className="telemetry-card">
        <span className="telemetry-label">Inbound messages · 14 days</span>
        <strong className="num">{data.totals.inbound}</strong>
        <p className="telemetry-split">
          {META_CHANNELS.map((provider) => (
            <span key={provider}>
              <ChannelBadge provider={provider} compact />{" "}
              <span className="num">
                {data.days.reduce((sum, day) => sum + day[provider], 0)}
              </span>
            </span>
          ))}
        </p>
        <Sparkline points={inbound} label="Inbound messages per day" />
      </article>
      <article className="telemetry-card">
        <span className="telemetry-label">Contacts captured · 14 days</span>
        <strong className="num">{data.totals.contacts}</strong>
        <p className="telemetry-split">
          New leads from comments, story replies and DMs.
        </p>
        <Sparkline points={contacts} label="New contacts per day" />
      </article>
      <article className="telemetry-card">
        <span className="telemetry-label">AI engagement rate · 14 days</span>
        <strong className="num">
          {data.totals.ai_rate === null ? "—" : percent(data.totals.ai_rate)}
        </strong>
        <p className="telemetry-split">
          {data.totals.ai_rate === null
            ? "No inbound conversations yet."
            : `Share of ${data.totals.conversations} conversation${data.totals.conversations === 1 ? "" : "s"} the AI agent answered.`}
        </p>
        {data.totals.ai_rate !== null && (
          <div
            className="meter"
            role="meter"
            aria-label="AI engagement rate"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.round(data.totals.ai_rate * 100)}
          >
            <span style={{ width: percent(data.totals.ai_rate) }} />
          </div>
        )}
      </article>
    </div>
  );
}
