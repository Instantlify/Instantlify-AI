"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Bot,
  CreditCard,
  RefreshCw,
  Send,
  StickyNote,
  Wifi,
  WifiOff,
} from "lucide-react";
import {
  api,
  idempotencyKey,
  money,
  type Conversation,
  type Lead,
  type Member,
  type Message,
  type Note,
  type Offer,
  type Page,
} from "@/lib/api";
import { useWorkspace } from "@/lib/workspace";
import { useWorkspaceSocket } from "@/lib/ws";
import { initials } from "@/components/shell";
import {
  Empty,
  ErrorNotice,
  Pill,
  statusTone,
  SuccessNotice,
  useFeedback,
} from "@/components/ui";
import { TourMarker } from "@/components/growth";

const STAGES = ["new", "qualified", "interested", "booked", "won", "lost"];

export default function InboxPage() {
  const { workspace, user, prefix, manager } = useWorkspace();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [notes, setNotes] = useState<Note[]>([]);
  const [members, setMembers] = useState<Member[]>([]);
  const [offers, setOffers] = useState<Offer[]>([]);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("all");
  const [draft, setDraft] = useState("");
  const [note, setNote] = useState("");
  const [live, setLive] = useState(false);
  const [loading, setLoading] = useState(true);
  // Wall clock for the 24-hour window notice; refreshed with every poll.
  const [now, setNow] = useState(() => Date.now());
  const feedback = useFeedback();
  const bodyRef = useRef<HTMLDivElement>(null);

  const loadList = useCallback(
    async (signal?: AbortSignal) => {
      const page = await api<Page<Conversation>>(
        `${prefix}/conversations/?search=${encodeURIComponent(search)}`,
        "GET",
        undefined,
        signal,
      );
      setConversations(page.results);
      return page.results;
    },
    [prefix, search],
  );
  const loadThread = useCallback(
    async (id: string, signal?: AbortSignal) => {
      const [thread, internal] = await Promise.all([
        api<Page<Message>>(
          `${prefix}/conversations/${id}/messages/`,
          "GET",
          undefined,
          signal,
        ),
        api<Note[]>(
          `${prefix}/conversations/${id}/notes/`,
          "GET",
          undefined,
          signal,
        ),
      ]);
      setMessages([...thread.results].reverse());
      setNotes(internal);
    },
    [prefix],
  );
  const refreshAll = useCallback(() => {
    setNow(Date.now());
    loadList().catch(() => undefined);
    if (selected) loadThread(selected).catch(() => undefined);
  }, [loadList, loadThread, selected]);
  useWorkspaceSocket(workspace.id, refreshAll, setLive);

  useEffect(() => {
    const controller = new AbortController();
    queueMicrotask(() =>
      loadList(controller.signal)
        .then((list) => {
          setSelected((current) => current ?? list[0]?.id ?? null);
        })
        .catch((err) => {
          if (!controller.signal.aborted)
            feedback.setError((err as Error).message);
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        }),
    );
    api<Page<Member>>(`${prefix}/members/`, "GET", undefined, controller.signal)
      .then((page) => setMembers(page.results))
      .catch(() => undefined);
    api<Page<Offer>>(`${prefix}/offers/`, "GET", undefined, controller.signal)
      .then((page) => setOffers(page.results.filter((offer) => offer.active)))
      .catch(() => undefined);
    const timer = window.setInterval(refreshAll, 10000);
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadList]);
  useEffect(() => {
    if (!selected) return;
    const controller = new AbortController();
    queueMicrotask(() =>
      loadThread(selected, controller.signal).catch((err) => {
        if (!controller.signal.aborted)
          feedback.setError((err as Error).message);
      }),
    );
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected, loadThread]);
  useEffect(() => {
    bodyRef.current?.scrollTo({ top: bodyRef.current.scrollHeight });
  }, [messages, notes]);

  const current = conversations.find((item) => item.id === selected) || null;
  const visible = conversations.filter((item) =>
    filter === "all"
      ? true
      : filter === "mine"
        ? item.assigned_to === user.id
        : filter === "unassigned"
          ? item.assigned_to === null
          : item.status === filter,
  );

  async function patch(
    data: Partial<Pick<Conversation, "assigned_to" | "status" | "ai_enabled">>,
  ) {
    if (!current) return;
    const previous = current;
    // Optimistic: reflect the change at once, roll back if the server refuses it.
    setConversations((list) =>
      list.map((item) =>
        item.id === current.id ? { ...item, ...data } : item,
      ),
    );
    const updated = await feedback.run(() =>
      api<Conversation>(
        `${prefix}/conversations/${current.id}/`,
        "PATCH",
        data,
      ),
    );
    setConversations((list) =>
      list.map((item) =>
        item.id === current.id ? (updated ?? previous) : item,
      ),
    );
  }
  async function send() {
    if (!current || !draft.trim()) return;
    const text = draft.trim();
    await feedback.run(async () => {
      await api(
        `${prefix}/conversations/${current.id}/messages/`,
        "POST",
        { text },
        undefined,
        { "Idempotency-Key": idempotencyKey() },
      );
      setDraft("");
      await loadThread(current.id);
      await loadList();
    });
  }
  async function addNote() {
    if (!current || !note.trim()) return;
    await feedback.run(async () => {
      await api(`${prefix}/conversations/${current.id}/notes/`, "POST", {
        text: note.trim(),
      });
      setNote("");
      await loadThread(current.id);
    });
  }
  async function updateLead(data: Partial<Lead>) {
    if (!current) return;
    await feedback.run(async () => {
      const lead = await api<Lead>(
        `${prefix}/leads/${current.lead.id}/`,
        "PATCH",
        data,
      );
      setConversations((list) =>
        list.map((item) => (item.id === current.id ? { ...item, lead } : item)),
      );
    });
  }
  async function sendPaymentLink(offerId: string) {
    if (!current || !offerId) return;
    await feedback.run(async () => {
      await api(
        `${prefix}/conversations/${current.id}/payment-link/`,
        "POST",
        { offer: offerId },
        undefined,
        { "Idempotency-Key": idempotencyKey() },
      );
      await loadThread(current.id);
    }, "Payment link sent.");
  }

  const timeline = [
    ...messages.map((item) => ({
      kind: "message" as const,
      at: item.created_at,
      item,
    })),
    ...notes.map((item) => ({
      kind: "note" as const,
      at: item.created_at,
      item,
    })),
  ].sort((a, b) => a.at.localeCompare(b.at));
  const windowClosed =
    current &&
    ["instagram", "whatsapp", "messenger"].includes(current.provider) &&
    (!current.last_inbound_at ||
      now - new Date(current.last_inbound_at).getTime() > 24 * 3600 * 1000);

  return (
    <>
      <TourMarker workspaceId={workspace.id} step="crm" />
      <div className="page-heading">
        <div>
          <span className="eyebrow">INBOX</span>
          <h1>Every conversation, one place.</h1>
          <p>Instagram, WhatsApp, Messenger and Telegram, live.</p>
        </div>
        <span className={`pill ${live ? "pill-good" : "pill-warn"}`}>
          {live ? <Wifi size={12} /> : <WifiOff size={12} />}
          {live ? "Live" : "Polling"}
        </span>
      </div>
      <ErrorNotice error={feedback.error} />
      <SuccessNotice notice={feedback.notice} />
      <div className="inbox">
        <aside className="inbox-list">
          <header>
            <input
              type="search"
              placeholder="Search leads by name or email"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              aria-label="Search conversations"
            />
            <select
              value={filter}
              onChange={(event) => setFilter(event.target.value)}
              aria-label="Filter"
            >
              <option value="all">All conversations</option>
              <option value="mine">Assigned to me</option>
              <option value="unassigned">Unassigned</option>
              <option value="needs_human">Needs a human</option>
              <option value="open">Open</option>
              <option value="closed">Closed</option>
            </select>
          </header>
          <div className="inbox-scroll">
            {loading ? (
              <p className="loading-text" style={{ padding: 14 }}>
                Loading conversations…
              </p>
            ) : visible.length ? (
              visible.map((item) => (
                <button
                  key={item.id}
                  className={`conversation-row ${item.id === selected ? "active" : ""}`}
                  onClick={() => setSelected(item.id)}
                >
                  <span className="user-avatar">
                    {initials(item.lead.name || "?")}
                  </span>
                  <span>
                    <strong>{item.lead.name || "Unknown lead"}</strong>
                    <span>
                      {item.provider}
                      {item.is_test ? " · test" : ""} · {item.lead.stage}
                      {item.status === "needs_human" ? " · needs a human" : ""}
                    </span>
                  </span>
                  <time dateTime={item.updated_at}>
                    {new Date(item.updated_at).toLocaleDateString()}
                  </time>
                </button>
              ))
            ) : (
              <Empty>No conversations match.</Empty>
            )}
          </div>
        </aside>
        {current ? (
          <section className="thread">
            <div className="thread-head">
              <h2>{current.lead.name || "Unknown lead"}</h2>
              <Pill tone={statusTone(current.status)}>
                {current.status.replace("_", " ")}
              </Pill>
              <Pill>{current.provider}</Pill>
              <span className="spacer" />
              <label className="field inline small">
                <input
                  type="checkbox"
                  checked={current.ai_enabled}
                  onChange={(event) =>
                    patch({ ai_enabled: event.target.checked })
                  }
                  disabled={current.lead.opted_out}
                />
                <Bot size={14} /> AI replies
              </label>
              <select
                aria-label="Assign to"
                value={current.assigned_to ?? ""}
                onChange={(event) =>
                  patch({
                    assigned_to: event.target.value
                      ? Number(event.target.value)
                      : null,
                  })
                }
              >
                <option value="">Unassigned</option>
                {members
                  .filter((member) => manager || member.email === user.email)
                  .map((member) => (
                    <option key={member.id} value={member.user_id}>
                      {member.name || member.email}
                    </option>
                  ))}
              </select>
              <select
                aria-label="Status"
                value={current.status}
                onChange={(event) =>
                  patch({
                    status: event.target.value as Conversation["status"],
                  })
                }
              >
                <option value="open">Open</option>
                <option value="needs_human">Needs a human</option>
                <option value="closed">Closed</option>
              </select>
              <button
                className="icon-button"
                aria-label="Refresh"
                onClick={refreshAll}
              >
                <RefreshCw size={15} />
              </button>
            </div>
            <div className="thread-body" ref={bodyRef}>
              {timeline.length ? (
                timeline.map((entry) =>
                  entry.kind === "note" ? (
                    <div className="bubble note" key={`n-${entry.item.id}`}>
                      <StickyNote size={12} /> {entry.item.text}
                      <time>
                        {new Date(entry.at).toLocaleString()} · internal note
                      </time>
                    </div>
                  ) : (
                    <div
                      className={`bubble ${entry.item.direction}`}
                      key={entry.item.id}
                    >
                      {entry.item.text ||
                        (entry.item.kind === "voice" ? "🎤 Voice note" : "…")}
                      <time>
                        {new Date(entry.at).toLocaleString()}
                        {entry.item.delivery_status
                          ? ` · ${entry.item.delivery_status}`
                          : ""}
                      </time>
                    </div>
                  ),
                )
              ) : (
                <Empty>No messages yet.</Empty>
              )}
            </div>
            <div className="composer">
              {current.lead.opted_out ? (
                <Empty>This lead opted out. Messaging is disabled.</Empty>
              ) : (
                <>
                  {windowClosed && (
                    <p className="muted-text">
                      The 24-hour messaging window has closed; wait for the
                      customer to write again.
                    </p>
                  )}
                  <textarea
                    placeholder="Write a reply…"
                    value={draft}
                    onChange={(event) => setDraft(event.target.value)}
                    maxLength={2000}
                    aria-label="Reply"
                    onKeyDown={(event) => {
                      if (
                        event.key === "Enter" &&
                        (event.metaKey || event.ctrlKey)
                      )
                        send();
                    }}
                  />
                  <div className="row">
                    <button
                      className="button primary small"
                      onClick={send}
                      disabled={feedback.busy || !draft.trim()}
                    >
                      Send <Send size={14} />
                    </button>
                    {offers.length > 0 && (
                      <select
                        aria-label="Send payment link"
                        defaultValue=""
                        onChange={(event) => {
                          sendPaymentLink(event.target.value);
                          event.target.value = "";
                        }}
                      >
                        <option value="">Send payment link…</option>
                        {offers.map((offer) => (
                          <option key={offer.id} value={offer.id}>
                            {offer.name} ·{" "}
                            {money(offer.amount_cents, offer.currency)}
                          </option>
                        ))}
                      </select>
                    )}
                    {!offers.length && (
                      <span className="muted-text">
                        <CreditCard size={12} /> Create offers to send payment
                        links.
                      </span>
                    )}
                    <span className="spacer" />
                    <input
                      placeholder="Internal note (team only)"
                      value={note}
                      onChange={(event) => setNote(event.target.value)}
                      maxLength={5000}
                      aria-label="Internal note"
                      style={{
                        flex: "1 1 200px",
                        padding: "8px 10px",
                        border: "1px solid var(--line)",
                        borderRadius: 7,
                      }}
                    />
                    <button
                      className="button secondary small"
                      onClick={addNote}
                      disabled={feedback.busy || !note.trim()}
                    >
                      Add note
                    </button>
                  </div>
                </>
              )}
              <div className="lead-panel">
                <dl>
                  <dt>Email</dt>
                  <dd>
                    <input
                      defaultValue={current.lead.email}
                      key={`${current.id}-email`}
                      placeholder="lead@example.com"
                      aria-label="Lead email"
                      onBlur={(event) => {
                        if (event.target.value !== current.lead.email)
                          updateLead({ email: event.target.value });
                      }}
                      style={{
                        width: "100%",
                        padding: "6px 8px",
                        border: "1px solid var(--line)",
                        borderRadius: 6,
                      }}
                    />
                  </dd>
                  <dt>Stage</dt>
                  <dd>
                    <select
                      value={current.lead.stage}
                      aria-label="Lead stage"
                      onChange={(event) =>
                        updateLead({ stage: event.target.value })
                      }
                    >
                      {STAGES.map((stage) => (
                        <option key={stage} value={stage}>
                          {stage}
                        </option>
                      ))}
                    </select>
                  </dd>
                  <dt>Tags</dt>
                  <dd className="tag-list">
                    {current.lead.tags.length ? (
                      current.lead.tags.map((tag) => (
                        <Pill
                          key={tag}
                          tone={
                            tag === "hot"
                              ? "bad"
                              : tag === "warm"
                                ? "warn"
                                : "neutral"
                          }
                        >
                          {tag}
                        </Pill>
                      ))
                    ) : (
                      <span className="muted-text">none yet</span>
                    )}
                  </dd>
                  {Object.entries(current.lead.fields).map(([key, value]) => (
                    <FieldRow key={key} label={key} value={value} />
                  ))}
                </dl>
              </div>
            </div>
          </section>
        ) : (
          <section className="thread">
            <div className="thread-body">
              <Empty>
                {loading
                  ? "Loading…"
                  : "No conversations yet. Connect a channel or simulate a test message under Integrations."}
              </Empty>
            </div>
          </section>
        )}
      </div>
    </>
  );
}

function FieldRow({ label, value }: { label: string; value: string }) {
  return (
    <>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </>
  );
}
