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
  Users,
} from "lucide-react";
import {
  api,
  type Audit,
  type Connection,
  type Funnel,
  type Page,
  type Status,
} from "@/lib/api";
import { useWorkspace } from "@/lib/workspace";
import {
  Empty,
  ErrorNotice,
  Panel,
  Pill,
  Stat,
  statusTone,
  SuccessNotice,
  useFeedback,
} from "@/components/ui";
import { ActivityList } from "@/components/activity";

export default function OverviewPage() {
  const { workspace, user, prefix, manager } = useWorkspace();
  const [connections, setConnections] = useState<Connection[]>([]);
  const [status, setStatus] = useState<Status | null>(null);
  const [events, setEvents] = useState<Audit[]>([]);
  const [members, setMembers] = useState(0);
  const [funnel, setFunnel] = useState<Funnel | null>(null);
  const [loading, setLoading] = useState(true);
  const feedback = useFeedback();
  const load = useCallback(
    async (signal?: AbortSignal) => {
      const [channels, health, team] = await Promise.all([
        api<Page<Connection>>(
          `${prefix}/connections/`,
          "GET",
          undefined,
          signal,
        ),
        api<Status>(`${prefix}/status/`, "GET", undefined, signal),
        api<Page<{ id: string }>>(
          `${prefix}/members/`,
          "GET",
          undefined,
          signal,
        ),
      ]);
      setConnections(channels.results);
      setStatus(health);
      setMembers(team.count);
      if (manager) {
        const [audit, report] = await Promise.all([
          api<Page<Audit>>(`${prefix}/audit/`, "GET", undefined, signal),
          api<Funnel>(
            `${prefix}/analytics/funnel/?period=7d`,
            "GET",
            undefined,
            signal,
          ),
        ]);
        setEvents(audit.results);
        setFunnel(report);
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
      <div className="page-heading">
        <div>
          <span className="eyebrow">{workspace.name.toUpperCase()}</span>
          <h1>A fresh start, {user.name.split(" ")[0] || "welcome"}.</h1>
          <p>
            Your business has a new home. Let’s get it ready for conversation.
          </p>
        </div>
        <span className="role-pill">{workspace.role}</span>
      </div>
      <ErrorNotice error={feedback.error} />
      <SuccessNotice notice={feedback.notice} />
      {loading ? (
        <p className="loading-text">Loading workspace details…</p>
      ) : (
        <>
          <section className="welcome-banner">
            <div>
              <span className="banner-kicker">
                <span className="small-dot" /> YOUR WORKSPACE IS READY
              </span>
              <h2>
                Big things start with
                <br />a simple hello.
              </h2>
              <p>
                Connect a channel, build your first automation, then let the AI
                agent qualify and book while your team handles the rest.
              </p>
              <Link
                href={`/w/${workspace.id}/automations`}
                className="button dark"
              >
                Build an automation
                <ArrowRight size={16} />
              </Link>
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
          <div className="stats-grid">
            <Stat
              icon={<Users size={19} />}
              value={String(members)}
              label="Workspace members"
              detail="A shared home for your team"
            />
            <Stat
              icon={<MessageCircle size={19} />}
              value={String(live.length)}
              label="Live channels"
              detail={`${connections.length - live.length} test or pending`}
            />
            <Stat
              icon={<ShieldCheck size={19} />}
              value={funnel ? String(step("dm") + step("comment")) : "Private"}
              label={funnel ? "Leads this week" : "Workspace access"}
              detail={
                funnel
                  ? `${step("booked")} booked · ${step("paid")} paid`
                  : "Only your members can enter"
              }
            />
          </div>
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
                  Live messaging needs Meta app credentials and review. Other
                  channels are connected under Settings → Channels.
                </p>
                {manager && (
                  <button
                    className="text-button"
                    onClick={connect}
                    disabled={feedback.busy}
                  >
                    {feedback.busy ? "Connecting…" : "Test connection setup"}
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
            <Panel
              title="Workspace pulse"
              aside={
                <span className="pulse-icon">
                  <Activity size={17} />
                </span>
              }
              className="health-panel"
            >
              <p className="panel-subtitle">A live check on the essentials.</p>
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
          </div>
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
