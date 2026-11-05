"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  ArrowRight,
  Bot,
  GraduationCap,
  MessageCircle,
  RefreshCw,
  UserPlus,
  Users,
} from "lucide-react";
import {
  api,
  message,
  type Connection,
  type Funnel,
  type Page,
  type Telemetry,
} from "@/lib/api";
import { useWorkspace } from "@/lib/workspace";
import { BrandIcon } from "@/lib/brand-icons";
import {
  ChannelBadge,
  ChannelIcon,
  channelLabel,
  META_CHANNELS,
  tokenHealth,
} from "@/lib/channels";
import { Sparkline } from "@/components/sparkline";
import { ConnectPrompt } from "@/components/growth";
import { firstReplyStep } from "@/lib/growth";
import {
  ErrorNotice,
  Panel,
  SuccessNotice,
  Table,
  useFeedback,
} from "@/components/ui";

const NOUNS: Record<string, [string, string]> = {
  instagram: ["account", "accounts"],
  messenger: ["Page", "Pages"],
  whatsapp: ["number", "numbers"],
};

const percent = (value: number) => `${Math.round(value * 100)}%`;

const duration = (minutes: number) =>
  minutes < 1
    ? "under 1 min"
    : minutes < 60
      ? `${Math.round(minutes)} min`
      : minutes < 60 * 24
        ? `${(minutes / 60).toFixed(1)} h`
        : `${(minutes / 60 / 24).toFixed(1)} days`;

export default function OverviewPage() {
  const { workspace, prefix, manager } = useWorkspace();
  const [connections, setConnections] = useState<Connection[]>([]);
  const [funnel, setFunnel] = useState<Funnel | null>(null);
  const [telemetry, setTelemetry] = useState<Telemetry | null>(null);
  const [checkedAt, setCheckedAt] = useState(() => Date.now());
  const [refreshing, setRefreshing] = useState(false);
  const [setup, setSetup] = useState({ tested: false, published: false, replied: false });
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
      setCheckedAt(Date.now());
      // Funnel and telemetry are owner/admin reports.
      if (manager) {
        const [report, metrics] = await Promise.all([
          api<Funnel>(`${prefix}/analytics/funnel/?period=7d`, "GET", undefined, signal),
          api<Telemetry>(`${prefix}/telemetry/`, "GET", undefined, signal),
        ]);
        setFunnel(report);
        setTelemetry(metrics);
        const tested = firstReplyStep(workspace.id, "tested");
        const published = firstReplyStep(workspace.id, "published");
        const hasReply = Boolean(report.steps?.some((step) => step.kind === "replied" && step.leads > 0));
        const replied = firstReplyStep(workspace.id, "replied", published && hasReply);
        setSetup({ tested, published, replied });
      }
    },
    [prefix, manager, workspace.id],
  );

  useEffect(() => {
    const controller = new AbortController();
    queueMicrotask(() =>
      load(controller.signal).catch((err) => {
        if (!controller.signal.aborted) feedback.setError(message(err));
      }),
    );
    const timer = window.setInterval(() => load().catch(() => undefined), 15000);
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [load]);

  async function handleRefresh() {
    setRefreshing(true);
    await load().catch((err) => feedback.setError(message(err)));
    setRefreshing(false);
  }

  const live = connections.filter((item) => item.status !== "disconnected");
  const channelReady = live.some((item) => !item.locked && tokenHealth(item, checkedAt) !== "reconnect");
  const setupSteps = [
    { label: "Connect a channel", done: channelReady, path: "integrations?tab=channels" },
    { label: "Preview a reply", done: setup.tested, path: "automations" },
    { label: "Publish an automation", done: setup.published, path: "automations" },
    { label: "Check for a reply in Conversations", done: setup.replied, path: "inbox" },
  ];
  const nextStep = setupSteps.find((step) => !step.done);
  const reconnect = live.filter((item) => tokenHealth(item, checkedAt) === "reconnect").length;
  const expiring = live.filter((item) => tokenHealth(item, checkedAt) === "expiring").length;
  const inbound = (telemetry?.days || []).map((day) => ({
    date: day.date,
    value: day.instagram + day.messenger + day.whatsapp + day.other,
  }));
  const contacts = (telemetry?.days || []).map((day) => ({
    date: day.date,
    value: day.contacts,
  }));

  return (
    <div className="overview-page-container">
      <ConnectPrompt workspaceId={workspace.id} />
      <ErrorNotice error={feedback.error} />
      <SuccessNotice notice={feedback.notice} />
      {manager && funnel && nextStep && (
        <section className="connect-prompt" aria-label="First reply checklist">
          <div>
            <strong>Your first automated reply</strong>
            <ol>
              {setupSteps.map((step) => (
                <li key={step.label}>{step.label} <span className="muted-text">· {step.done ? "Done" : "To do"}</span></li>
              ))}
            </ol>
          </div>
          {live.length > 0 && (
            <Link className="button primary" href={`/w/${workspace.id}/${nextStep.path}`}>
              {nextStep.label}
            </Link>
          )}
        </section>
      )}

      {/* 1. Channel status: which accounts are connected and which need attention */}
      <section className="boosend-leaderboard-bar overview-channel-bar" aria-label="Channel status">
        {META_CHANNELS.map((provider) => {
          const items = live.filter((item) => item.provider === provider);
          const [one, many] = NOUNS[provider];
          return (
            <span key={provider} className={`channel-status-item ${items.length ? "" : "off"}`}>
              <ChannelIcon provider={provider} size={18} />
              <strong>{channelLabel(provider)}</strong>
              <span>
                {!items.length
                  ? "Not connected"
                  : items.every((item) => item.is_test)
                    ? "Local test connection"
                    : provider === "instagram" && items.length === 1
                    ? items[0].display_name
                    : `${items.length} ${items.length === 1 ? one : many}`}
              </span>
            </span>
          );
        })}
        <Link
          href={`/w/${workspace.id}/integrations?tab=channels`}
          className={`channel-status-link ${reconnect || expiring ? "warn" : ""}`}
        >
          {reconnect
            ? `${reconnect} need${reconnect === 1 ? "s" : ""} reconnecting`
            : expiring
              ? `${expiring} token${expiring === 1 ? "" : "s"} expiring soon`
              : "Manage channels"}
          <ArrowRight size={13} />
        </Link>
      </section>

      {/* 2. Hero Quick Action Cards (Matching Screenshot 1) */}
      <section className="boosend-quick-actions-row">
        <Link href={`/w/${workspace.id}/help`} className="quick-action-card learn-card">
          <div className="action-card-icon-cap">
            <GraduationCap size={32} />
          </div>
          <div className="action-card-content">
            <h2 className="action-card-heading">Learn To Use Nemio</h2>
            <p className="action-card-desc">
              Discover how to build Meta automated funnels, comment triggers, and human handoffs.
            </p>
          </div>
          <ArrowRight size={20} className="hover-arrow" />
        </Link>

        <Link href={`/w/${workspace.id}/integrations`} className="quick-action-card mcp-dark-card">
          <div className="mcp-starburst-icon">
            <BrandIcon name="claude" size={28} />
          </div>
          <div className="action-card-content">
            <h2 className="action-card-heading white-heading">Connect Claude MCP</h2>
            <p className="action-card-desc light-desc">
              Create an API key under Integrations to give Claude your conversations and lead
              triggers.
            </p>
          </div>
          <ArrowRight size={20} className="hover-arrow" />
        </Link>
      </section>

      {/* 3. Your Statistics */}
      <section className="boosend-statistics-section">
        <div className="section-title-row">
          <div>
            <h2 className="section-main-heading">Your Statistics</h2>
            <span className="section-sub-heading">
              {manager ? "Last 14 days across every connected account" : "Visible to owners and admins"}
            </span>
          </div>
          <button
            type="button"
            className="refresh-metrics-btn"
            onClick={handleRefresh}
            disabled={refreshing}
          >
            <RefreshCw size={14} className={refreshing ? "spin" : ""} />
            Refresh
          </button>
        </div>

        {manager && (
          <div className="metrics-cards-grid overview-metrics">
            <article className="metric-kpi-card cyan-tone">
              <div className="kpi-card-header">
                <span className="kpi-icon-wrap cyan">
                  <MessageCircle size={15} />
                </span>
                <span className="kpi-label">Inbound messages</span>
              </div>
              <div className="kpi-value-row">
                <span className="kpi-number">{telemetry ? telemetry.totals.inbound : "—"}</span>
              </div>
              <p className="kpi-split">
                {META_CHANNELS.map((provider) => (
                  <span key={provider}>
                    <ChannelBadge provider={provider} compact />{" "}
                    {(telemetry?.days || []).reduce((sum, day) => sum + day[provider], 0)}
                  </span>
                ))}
              </p>
              <Sparkline points={inbound} label="Inbound messages per day" />
            </article>

            <article className="metric-kpi-card emerald-tone">
              <div className="kpi-card-header">
                <span className="kpi-icon-wrap emerald">
                  <Users size={15} />
                </span>
                <span className="kpi-label">Contacts captured</span>
              </div>
              <div className="kpi-value-row">
                <span className="kpi-number">{telemetry ? telemetry.totals.contacts : "—"}</span>
              </div>
              <p className="kpi-split">New leads from comments, story replies and DMs.</p>
              <Sparkline points={contacts} label="New contacts per day" />
            </article>

            <article className="metric-kpi-card stat-card">
              <div className="kpi-card-header">
                <span className="kpi-icon-wrap cyan">
                  <UserPlus size={15} />
                </span>
                <span className="kpi-label">Leads this week</span>
              </div>
              <div className="kpi-value-row">
                <strong className="kpi-number">{funnel ? funnel.unique_leads : "—"}</strong>
              </div>
              <p className="kpi-split">
                Unique people who reached an automation in the last 7 days.
              </p>
              <Link href={`/w/${workspace.id}/analytics`} className="kpi-corner-link">
                View funnel
              </Link>
            </article>

            <article className="metric-kpi-card purple-tone">
              <div className="kpi-card-header">
                <span className="kpi-icon-wrap purple">
                  <Bot size={15} />
                </span>
                <span className="kpi-label">AI engagement</span>
              </div>
              <div className="kpi-value-row">
                <span className="kpi-number">
                  {telemetry?.totals.ai_rate == null ? "—" : percent(telemetry.totals.ai_rate)}
                </span>
              </div>
              <p className="kpi-split">
                {!telemetry || telemetry.totals.ai_rate == null
                  ? "No inbound conversations yet."
                  : `Share of ${telemetry.totals.conversations} conversation${telemetry.totals.conversations === 1 ? "" : "s"} the AI agent answered.`}
              </p>
              {telemetry?.totals.ai_rate != null && (
                <div
                  className="meter"
                  role="meter"
                  aria-label="AI engagement rate"
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={Math.round(telemetry.totals.ai_rate * 100)}
                >
                  <span style={{ width: percent(telemetry.totals.ai_rate) }} />
                </div>
              )}
            </article>
          </div>
        )}
      </section>

      {telemetry && telemetry.channels.length > 0 && (
        <Panel title="Channel performance" aside="Last 14 days" className="channel-matrix">
          <Table
            head={["Channel", "Inbound messages", "Conversations", "Median first reply", "Top trigger"]}
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
                      <span className="muted-text">· {row.top_automation.runs} runs</span>
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
    </div>
  );
}
