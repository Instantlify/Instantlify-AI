"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Bot,
  CreditCard,
  ExternalLink,
  Hand,
  MessageSquarePlus,
  Paperclip,
  RefreshCw,
  Send,
  Smile,
  StickyNote,
  Timer,
  Trash2,
  Wifi,
  WifiOff,
  Workflow,
  X,
  Zap,
} from "lucide-react";
import {
  api,
  idempotencyKey,
  money,
  type Conversation,
  type ConversationEvent,
  type Lead,
  type Member,
  type Message,
  type Note,
  type Offer,
  type Page,
} from "@/lib/api";
import { useWorkspace } from "@/lib/workspace";
import { useWorkspaceSocket } from "@/lib/ws";
import { ChannelBadge, META_CHANNELS } from "@/lib/channels";
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
const TABS = [
  { id: "", label: "All channels" },
  { id: "instagram", label: "Instagram Direct" },
  { id: "messenger", label: "Facebook Messenger" },
  { id: "whatsapp", label: "WhatsApp" },
];
const WINDOWED = new Set<string>(META_CHANNELS);
const WINDOW_MS = 24 * 3600 * 1000;
const EMOJI = [
  "😊",
  "😂",
  "😍",
  "🙏",
  "👍",
  "👋",
  "🎉",
  "🔥",
  "💯",
  "✨",
  "❤️",
  "🙌",
  "😉",
  "🤝",
  "📅",
  "✅",
  "📩",
  "🎁",
  "💬",
  "👀",
  "🚀",
  "💡",
  "⏰",
  "😅",
];
const DEFAULT_REPLIES = [
  "Thanks for reaching out! How can I help?",
  "Great question, let me check and get right back to you.",
  "Here's the link you asked for:",
];
const EVENT_LABELS: Record<ConversationEvent["kind"], string> = {
  triggered: "Automation triggered",
  handoff: "Handed to the team",
  link_click: "Link clicked",
  booked: "Call booked",
  paid: "Payment received",
};

const repliesKey = (workspaceId: string) =>
  `nemio:quick-replies:${workspaceId}`;
function loadReplies(workspaceId: string): string[] {
  try {
    const stored = JSON.parse(
      localStorage.getItem(repliesKey(workspaceId)) || "null",
    );
    return Array.isArray(stored) &&
      stored.every((item) => typeof item === "string")
      ? stored
      : DEFAULT_REPLIES;
  } catch {
    return DEFAULT_REPLIES;
  }
}

/** Remaining Meta customer-service window, or null for channels without one. */
function windowLeft(conversation: Conversation, now: number) {
  if (!WINDOWED.has(conversation.provider)) return null;
  if (!conversation.last_inbound_at) return 0;
  return Math.max(
    0,
    new Date(conversation.last_inbound_at).getTime() + WINDOW_MS - now,
  );
}

function countdown(ms: number) {
  const minutes = Math.ceil(ms / 60000);
  return minutes >= 60
    ? `${Math.floor(minutes / 60)}h ${minutes % 60}m left`
    : `${minutes}m left`;
}

function shortTime(value: string, now: number) {
  const date = new Date(value);
  return now - date.getTime() < 24 * 3600 * 1000
    ? date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })
    : date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export default function InboxPage() {
  const { workspace, user, prefix, manager, activeAccount, setActiveAccount } =
    useWorkspace();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  // The CRM links here with ?conversation=<id>; the workspace layout renders pages
  // only in the browser, so the URL is readable on first render.
  const [selected, setSelected] = useState<string | null>(() =>
    typeof window === "undefined"
      ? null
      : new URLSearchParams(window.location.search).get("conversation"),
  );
  const [messages, setMessages] = useState<Message[]>([]);
  const [notes, setNotes] = useState<Note[]>([]);
  const [events, setEvents] = useState<ConversationEvent[]>([]);
  const [members, setMembers] = useState<Member[]>([]);
  const [offers, setOffers] = useState<Offer[]>([]);
  const [search, setSearch] = useState("");
  const [channel, setChannel] = useState("");
  const [filter, setFilter] = useState("all");
  const [draft, setDraft] = useState("");
  const [note, setNote] = useState("");
  const [live, setLive] = useState(false);
  const [loading, setLoading] = useState(true);
  const [picker, setPicker] = useState<"emoji" | "replies" | null>(null);
  const [replies, setReplies] = useState<string[]>(() =>
    loadReplies(workspace.id),
  );
  // Wall clock for the 24-hour window countdown; ticks every 30 seconds.
  const [now, setNow] = useState(() => Date.now());
  const [attachedFile, setAttachedFile] = useState<{
    name: string;
    size: number;
    url: string;
    type: string;
  } | null>(null);
  const feedback = useFeedback();
  const bodyRef = useRef<HTMLDivElement>(null);
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadList = useCallback(
    async (signal?: AbortSignal) => {
      const params = new URLSearchParams({ search });
      if (channel) params.set("provider", channel);
      if (activeAccount) params.set("connection", activeAccount);
      const page = await api<Page<Conversation>>(
        `${prefix}/conversations/?${params.toString()}`,
        "GET",
        undefined,
        signal,
      );
      setConversations(page.results);
      return page.results;
    },
    [prefix, search, channel, activeAccount],
  );
  const loadThread = useCallback(
    async (id: string, signal?: AbortSignal) => {
      const [thread, internal, milestones] = await Promise.all([
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
        api<ConversationEvent[]>(
          `${prefix}/conversations/${id}/events/`,
          "GET",
          undefined,
          signal,
        ),
      ]);
      setMessages([...thread.results].reverse());
      setNotes(internal);
      setEvents(milestones);
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
          setSelected((current) =>
            current && list.some((item) => item.id === current)
              ? current
              : (list[0]?.id ?? null),
          );
        })
        .catch((err) => {
          if (!controller.signal.aborted)
            feedback.setError((err as Error).message);
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        }),
    );
    const timer = window.setInterval(refreshAll, 10000);
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadList]);
  useEffect(() => {
    const controller = new AbortController();
    api<Page<Member>>(`${prefix}/members/`, "GET", undefined, controller.signal)
      .then((page) => setMembers(page.results))
      .catch(() => undefined);
    api<Page<Offer>>(`${prefix}/offers/`, "GET", undefined, controller.signal)
      .then((page) => setOffers(page.results.filter((offer) => offer.active)))
      .catch(() => undefined);
    const clock = window.setInterval(() => setNow(Date.now()), 30000);
    return () => {
      controller.abort();
      window.clearInterval(clock);
    };
  }, [prefix]);
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
  }, [messages, notes, events]);
  useEffect(() => {
    if (!picker) return;
    const close = (event: MouseEvent | KeyboardEvent) => {
      if (
        event instanceof KeyboardEvent
          ? event.key === "Escape"
          : !(event.target as HTMLElement).closest(".tool-anchor")
      )
        setPicker(null);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [picker]);

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
  const accountName = activeAccount
    ? conversations.find((item) => item.connection_id === activeAccount)
        ?.connection_name
    : null;

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
        item.id === current.id
          ? updated
            ? { ...item, ...updated }
            : previous
          : item,
      ),
    );
  }
  async function send() {
    if (!current || (!draft.trim() && !attachedFile)) return;
    const text = attachedFile
      ? `[${attachedFile.type}: ${attachedFile.name}] ${draft.trim()}`.trim()
      : draft.trim();
    await feedback.run(async () => {
      await api(
        `${prefix}/conversations/${current.id}/messages/`,
        "POST",
        { text },
        undefined,
        { "Idempotency-Key": idempotencyKey() },
      );
      setDraft("");
      setAttachedFile(null);
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
  function insert(text: string) {
    const field = composerRef.current;
    const start = field?.selectionStart ?? draft.length;
    const end = field?.selectionEnd ?? draft.length;
    const next = (draft.slice(0, start) + text + draft.slice(end)).slice(
      0,
      2000,
    );
    setDraft(next);
    setPicker(null);
    requestAnimationFrame(() => {
      field?.focus();
      field?.setSelectionRange(start + text.length, start + text.length);
    });
  }
  function saveReplies(next: string[]) {
    setReplies(next);
    try {
      localStorage.setItem(repliesKey(workspace.id), JSON.stringify(next));
    } catch {
      // Storage unavailable: the replies last for this visit only.
    }
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
    ...events.map((item) => ({
      kind: "event" as const,
      at: item.created_at,
      item,
    })),
  ].sort((a, b) => a.at.localeCompare(b.at));
  const left = current ? windowLeft(current, now) : null;
  const windowClosed = left === 0;
  const assignee = current
    ? members.find((member) => member.user_id === current.assigned_to)
    : undefined;

  return (
    <>
      <TourMarker workspaceId={workspace.id} step="crm" />
      <div className="page-heading">
        <div>
          <span className="eyebrow">INBOX</span>
          <h1>Every conversation, one place.</h1>
          <p>Instagram, Facebook Messenger and WhatsApp, live.</p>
        </div>
        <span className={`pill ${live ? "pill-good" : "pill-warn"}`}>
          {live ? <Wifi size={12} /> : <WifiOff size={12} />}
          {live ? "Live" : "Polling"}
        </span>
      </div>
      <ErrorNotice error={feedback.error} />
      <SuccessNotice notice={feedback.notice} />
      <div className="channel-tabs" role="tablist" aria-label="Channel">
        {TABS.map((tab) => (
          <button
            key={tab.id || "all"}
            role="tab"
            aria-selected={channel === tab.id}
            className={channel === tab.id ? "on" : ""}
            onClick={() => setChannel(tab.id)}
          >
            {tab.id && <ChannelBadge provider={tab.id} compact />}
            {tab.label}
          </button>
        ))}
        {activeAccount && (
          <span className="account-chip">
            Account: {accountName || "selected account"}
            <button
              className="icon-button"
              aria-label="Show all accounts"
              onClick={() => setActiveAccount(null)}
            >
              <X size={13} />
            </button>
          </span>
        )}
      </div>
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
              visible.map((item) => {
                const awaiting = item.last_message?.direction === "inbound";
                return (
                  <button
                    key={item.id}
                    className={`conversation-row ${item.id === selected ? "active" : ""}`}
                    onClick={() => setSelected(item.id)}
                  >
                    <span className="user-avatar">
                      {initials(item.lead.name || "?")}
                    </span>
                    <span className="conversation-copy">
                      <span className="conversation-top">
                        <strong>{item.lead.name || "Unknown lead"}</strong>
                        <ChannelBadge provider={item.provider} compact />
                      </span>
                      <span className="conversation-snippet">
                        {item.last_message
                          ? `${item.last_message.direction === "outbound" ? "You: " : ""}${
                              item.last_message.text ||
                              (item.last_message.kind === "voice"
                                ? "🎤 Voice note"
                                : "Attachment")
                            }`
                          : "No messages yet"}
                      </span>
                      <span className="conversation-meta">
                        {item.lead.stage}
                        {item.is_test ? " · test" : ""}
                        {item.status === "needs_human"
                          ? " · needs a human"
                          : ""}
                      </span>
                    </span>
                    <span className="conversation-side">
                      <time dateTime={item.updated_at}>
                        {shortTime(
                          item.last_message?.created_at ?? item.updated_at,
                          now,
                        )}
                      </time>
                      {awaiting && (
                        <>
                          <i
                            className="unread-dot"
                            title="Awaiting a reply"
                            aria-hidden="true"
                          />
                          <span className="sr-only">Awaiting a reply</span>
                        </>
                      )}
                    </span>
                  </button>
                );
              })
            ) : (
              <Empty>No conversations match.</Empty>
            )}
          </div>
        </aside>
        {current ? (
          <section className="thread">
            <div className="thread-head">
              <span className="user-avatar">
                {initials(current.lead.name || "?")}
              </span>
              <div className="thread-title">
                <h2>{current.lead.name || "Unknown lead"}</h2>
                <span className="thread-sub">
                  <ChannelBadge provider={current.provider} />
                  <span className="muted-text">{current.connection_name}</span>
                  {current.contact_link && (
                    <a
                      href={current.contact_link}
                      target="_blank"
                      rel="noreferrer"
                      className="text-button"
                    >
                      Open chat <ExternalLink size={12} />
                    </a>
                  )}
                </span>
                {current.lead.tags.length > 0 && (
                  <span className="tag-list">
                    {current.lead.tags.map((tag) => (
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
                    ))}
                  </span>
                )}
              </div>
              <span className="spacer" />
              {left !== null && (
                <span
                  className={`window-chip ${windowClosed ? "closed" : left < 3600000 ? "soon" : ""}`}
                  title="Meta allows free-form replies for 24 hours after the customer's last message."
                >
                  <Timer size={13} />
                  {windowClosed ? "24h window closed" : countdown(left)}
                </span>
              )}
              <Pill tone={statusTone(current.status)}>
                {current.status.replace("_", " ")}
              </Pill>
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
                  .filter(
                    (member) =>
                      manager ||
                      member.user_id === user.id ||
                      member.user_id === current.assigned_to,
                  )
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
                  ) : entry.kind === "event" ? (
                    <div className="system-event" key={`e-${entry.item.id}`}>
                      <Zap size={12} />
                      <span>
                        {EVENT_LABELS[entry.item.kind]}
                        {entry.item.automation_name &&
                          entry.item.kind === "triggered" &&
                          `: ${entry.item.automation_name}`}
                      </span>
                      <time>{new Date(entry.at).toLocaleString()}</time>
                    </div>
                  ) : (
                    <MessageBubble key={entry.item.id} message={entry.item} />
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
                  <div
                    className="handoff-toggle"
                    role="group"
                    aria-label="Who replies"
                  >
                    <button
                      className={current.ai_enabled ? "on" : ""}
                      aria-pressed={current.ai_enabled}
                      disabled={feedback.busy}
                      onClick={() =>
                        !current.ai_enabled &&
                        patch({ ai_enabled: true, status: "open" })
                      }
                    >
                      <Bot size={14} /> AI active
                    </button>
                    <button
                      className={!current.ai_enabled ? "on human" : ""}
                      aria-pressed={!current.ai_enabled}
                      disabled={feedback.busy}
                      onClick={() =>
                        current.ai_enabled &&
                        patch({ ai_enabled: false, assigned_to: user.id })
                      }
                    >
                      <Hand size={14} /> Human takeover
                    </button>
                    <span className="muted-text">
                      {current.ai_enabled
                        ? "The AI agent answers new messages."
                        : assignee
                          ? `${assignee.name || assignee.email} is handling this conversation.`
                          : "Your team answers this conversation."}
                    </span>
                  </div>
                  {windowClosed && (
                    <p className="muted-text">
                      The 24-hour messaging window has closed; wait for the
                      customer to write again.
                    </p>
                  )}
                  {attachedFile && (
                    <div
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: "8px",
                        padding: "4px 10px",
                        borderRadius: "8px",
                        backgroundColor: "var(--brand-soft)",
                        fontSize: "12px",
                        marginBottom: "8px",
                        border: "1px solid var(--brand-line)",
                      }}
                    >
                      <Paperclip size={13} />
                      <strong>{attachedFile.name}</strong>
                      <span className="muted-text">
                        ({(attachedFile.size / 1024).toFixed(0)} KB)
                      </span>
                      <button
                        type="button"
                        className="icon-button"
                        style={{ width: "20px", height: "20px", padding: 0 }}
                        onClick={() => setAttachedFile(null)}
                        aria-label="Remove attachment"
                      >
                        <X size={12} />
                      </button>
                    </div>
                  )}
                  <textarea
                    ref={composerRef}
                    placeholder="Write a reply…"
                    value={draft}
                    onChange={(event) => setDraft(event.target.value)}
                    maxLength={2000}
                    aria-label="Reply"
                    disabled={windowClosed}
                    onKeyDown={(event) => {
                      if (
                        event.key === "Enter" &&
                        (event.metaKey || event.ctrlKey)
                      )
                        send();
                    }}
                  />
                  <div className="row composer-tools">
                    <button
                      className="button primary small"
                      onClick={send}
                      disabled={
                        feedback.busy ||
                        (!draft.trim() && !attachedFile) ||
                        windowClosed
                      }
                    >
                      Send <Send size={14} />
                    </button>
                    <button
                      type="button"
                      className="icon-button"
                      aria-label="Attach file"
                      title="Attach file (images, PDFs, audio)"
                      disabled={windowClosed}
                      onClick={() => fileInputRef.current?.click()}
                    >
                      <Paperclip size={16} />
                    </button>
                    <input
                      type="file"
                      ref={fileInputRef}
                      style={{ display: "none" }}
                      accept="image/*,.pdf,audio/*"
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file) {
                          setAttachedFile({
                            name: file.name,
                            size: file.size,
                            type: file.type.startsWith("image/")
                              ? "Image"
                              : file.type.startsWith("audio/")
                                ? "Audio"
                                : "Document",
                            url: URL.createObjectURL(file),
                          });
                        }
                        e.target.value = "";
                      }}
                    />
                    <div className="tool-anchor">
                      <button
                        className="icon-button"
                        aria-label="Quick replies"
                        aria-expanded={picker === "replies"}
                        onClick={() =>
                          setPicker(picker === "replies" ? null : "replies")
                        }
                      >
                        <MessageSquarePlus size={16} />
                      </button>
                      {picker === "replies" && (
                        <div className="tool-pop replies-pop">
                          <strong className="small">Quick replies</strong>
                          {replies.map((reply, index) => (
                            <div
                              className="reply-row"
                              key={`${index}-${reply}`}
                            >
                              <button onClick={() => insert(reply)}>
                                {reply}
                              </button>
                              <button
                                className="icon-button"
                                aria-label="Delete quick reply"
                                onClick={() =>
                                  saveReplies(
                                    replies.filter((_, i) => i !== index),
                                  )
                                }
                              >
                                <Trash2 size={13} />
                              </button>
                            </div>
                          ))}
                          {!replies.length && (
                            <p className="muted-text">
                              No quick replies saved.
                            </p>
                          )}
                          <button
                            className="text-button"
                            disabled={
                              !draft.trim() || replies.includes(draft.trim())
                            }
                            onClick={() =>
                              saveReplies([...replies, draft.trim()].slice(-20))
                            }
                          >
                            Save current reply
                          </button>
                          <small className="muted-text">
                            Saved in this browser.
                          </small>
                        </div>
                      )}
                    </div>
                    <div className="tool-anchor">
                      <button
                        className="icon-button"
                        aria-label="Insert emoji"
                        aria-expanded={picker === "emoji"}
                        onClick={() =>
                          setPicker(picker === "emoji" ? null : "emoji")
                        }
                      >
                        <Smile size={16} />
                      </button>
                      {picker === "emoji" && (
                        <div
                          className="tool-pop emoji-pop"
                          role="group"
                          aria-label="Emoji"
                        >
                          {EMOJI.map((emoji) => (
                            <button
                              key={emoji}
                              onClick={() => insert(emoji)}
                              aria-label={`Insert ${emoji}`}
                            >
                              {emoji}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
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
                      className="note-input"
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
                      className="lead-email"
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
                  : channel || activeAccount
                    ? "No conversations on this channel or account yet."
                    : "No conversations yet. Connect a channel or simulate a test message under Integrations."}
              </Empty>
            </div>
          </section>
        )}
      </div>
    </>
  );
}

const SENDER_BADGES: Record<
  Exclude<Message["sender"], "customer" | "human">,
  { label: string; icon: typeof Bot }
> = {
  ai: { label: "AI Agent", icon: Bot },
  automation: { label: "Automation", icon: Workflow },
  api: { label: "API", icon: Zap },
};

/** Customer on the left in alabaster; AI and automations in deep forest on the
 * right; teammates in slate with their initials. */
function MessageBubble({ message }: { message: Message }) {
  const badge =
    message.sender === "customer" || message.sender === "human"
      ? null
      : SENDER_BADGES[message.sender];
  return (
    <div className={`bubble ${message.direction} sender-${message.sender}`}>
      {message.sender === "human" && (
        <span
          className="bubble-author"
          title={message.author_name || "Teammate"}
        >
          {initials(message.author_name || "Team")}
        </span>
      )}
      {badge && (
        <span className="bubble-badge">
          <badge.icon size={11} /> {badge.label}
        </span>
      )}
      <span className="bubble-text">
        {message.text || (message.kind === "voice" ? "🎤 Voice note" : "…")}
      </span>
      <time>
        {new Date(message.created_at).toLocaleString()}
        {message.delivery_status ? ` · ${message.delivery_status}` : ""}
      </time>
    </div>
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
