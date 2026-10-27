"use client";

import {
  ValidatedForm,
  ValidatedInput,
  ValidatedSelect,
  ValidatedTextarea,
} from "@/components/validated-form";

import Link from "next/link";
import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import {
  Contact,
  ArrowUpRight,
  Bot,
  ChevronDown,
  Clock,
  CreditCard,
  ExternalLink,
  Hand,
  Info,
  MessageSquarePlus,
  Paperclip,
  Plus,
  RefreshCw,
  Search,
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
import { useSearchParams } from "next/navigation";
import { useWorkspace } from "@/lib/workspace";
import { useWorkspaceSocket } from "@/lib/ws";
import { ChannelBadge, ChannelIcon, META_CHANNELS } from "@/lib/channels";
import { initials } from "@/components/shell";
import { ContactAvatar } from "@/components/contact-avatar";
import {
  Empty,
  ErrorNotice,
  Pill,
  SuccessNotice,
  useFeedback,
} from "@/components/ui";
import { TourMarker } from "@/components/growth";
import { WhatsAppTemplateComposer } from "@/components/whatsapp-template-composer";

const STAGES = ["new", "qualified", "interested", "booked", "won", "lost"];
const TABS = [
  { id: "", label: "All channels" },
  { id: "instagram", label: "Instagram Direct" },
  { id: "messenger", label: "Facebook Messenger" },
  { id: "whatsapp", label: "WhatsApp" },
  { id: "telegram", label: "Telegram" },
  { id: "webchat", label: "Website chat" },
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
  // The CRM links here with ?conversation=<id>.
  const linked = useSearchParams().get("conversation");
  const [selected, setSelected] = useState<string | null>(linked);
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
  const [showChannelDropdown, setShowChannelDropdown] = useState(false);
  const [showInfo, setShowInfo] = useState(false);
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
          // A conversation linked from the CRM may sit on another account than the
          // switcher shows; widen to all accounts rather than silently opening another.
          if (
            linked &&
            activeAccount &&
            !list.some((item) => item.id === linked)
          ) {
            setActiveAccount(null);
            return;
          }
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

  const lastActive = current?.last_inbound_at
    ? `Last message ${new Date(current.last_inbound_at).toLocaleString()}`
    : "No customer messages yet";

  return (
    <div className="boosend-inbox-layout">
      <TourMarker workspaceId={workspace.id} step="crm" />
      {/* Left Column: Conversations Sidebar (Screenshot 9) */}
      <aside className="boosend-inbox-sidebar">
        {/* Channel selector dropdown pill */}
        <div className="boosend-inbox-channel-select-wrap">
          <div style={{ position: "relative" }}>
            <button
              type="button"
              className="boosend-inbox-channel-pill-btn"
              aria-haspopup="listbox"
              aria-expanded={showChannelDropdown}
              aria-label="Filter by channel"
              onClick={() => setShowChannelDropdown((v) => !v)}
            >
              <div
                style={{ display: "flex", alignItems: "center", gap: "8px" }}
              >
                {channel ? (
                  <ChannelIcon provider={channel} size={14} />
                ) : (
                  <span className="inbox-channel-all">All</span>
                )}
                <span>
                  {channel
                    ? TABS.find((t) => t.id === channel)?.label || "Channel"
                    : "All Channels"}
                </span>
              </div>
              <ChevronDown size={14} color="#94a3b8" />
            </button>

            {showChannelDropdown && (
              <div
                className="inbox-channel-menu"
                role="listbox"
                aria-label="Filter by channel"
              >
                {TABS.map((t) => (
                  <button
                    key={t.id || "all"}
                    type="button"
                    role="option"
                    aria-selected={channel === t.id}
                    className={channel === t.id ? "on" : ""}
                    onClick={() => {
                      setChannel(t.id);
                      setShowChannelDropdown(false);
                    }}
                  >
                    {t.id && <ChannelIcon provider={t.id} size={14} />}
                    {t.label}
                  </button>
                ))}
              </div>
            )}
          </div>
          {activeAccount && (
            <span className="account-chip">
              Account: {accountName || "selected account"}
              <button
                type="button"
                className="icon-button"
                aria-label="Show all accounts"
                onClick={() => setActiveAccount(null)}
              >
                <X size={13} />
              </button>
            </span>
          )}
        </div>

        {/* Search row with status filter */}
        <div className="boosend-inbox-search-row">
          <div className="boosend-inbox-search-box">
            <Search size={14} color="#94a3b8" />
            <ValidatedInput
              type="search"
              className="boosend-inbox-search-input"
              placeholder="Search conversations..."
              aria-label="Search conversations"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <ValidatedSelect
            className="inbox-filter-select"
            value={filter}
            onChange={(event) => setFilter(event.target.value)}
            aria-label="Filter"
          >
            <option value="all">All</option>
            <option value="mine">Assigned to me</option>
            <option value="unassigned">Unassigned</option>
            <option value="needs_human">Needs a human</option>
            <option value="open">Open</option>
            <option value="closed">Closed</option>
          </ValidatedSelect>
        </div>

        {/* Conversations list scroll */}
        <div className="boosend-inbox-list-scroll">
          {loading ? (
            <p className="inbox-list-empty">Loading conversations…</p>
          ) : visible.length > 0 ? (
            visible.map((item) => {
              const isActive = item.id === selected;
              const awaiting = item.last_message?.direction === "inbound";
              const lastText = item.last_message
                ? `${item.last_message.direction === "outbound" ? "You: " : ""}${
                    item.last_message.text ||
                    (item.last_message.kind === "voice"
                      ? "🎤 Voice note"
                      : "Attachment")
                  }`
                : "No messages yet";

              return (
                <button
                  key={item.id}
                  type="button"
                  className={`boosend-conv-item ${isActive ? "active" : ""}`}
                  onClick={() => setSelected(item.id)}
                >
                  <ContactAvatar
                    name={item.lead.name || "?"}
                    avatarUrl={item.lead.avatar_url}
                    className="boosend-conv-avatar"
                  >
                    <span className="conv-channel-mark" title={item.provider}>
                      <ChannelIcon provider={item.provider} size={10} />
                    </span>
                  </ContactAvatar>
                  <div className="boosend-conv-info">
                    <div className="boosend-conv-top">
                      <span className="boosend-conv-name">
                        {item.lead.name || "Unknown lead"}
                      </span>
                      <span className="boosend-conv-date">
                        {shortTime(
                          item.last_message?.created_at ?? item.updated_at,
                          now,
                        )}
                      </span>
                    </div>
                    <div className="boosend-conv-snippet">{lastText}</div>
                    {(item.status === "needs_human" || item.is_test) && (
                      <div className="boosend-conv-meta">
                        {item.is_test ? "Test" : ""}
                        {item.is_test && item.status === "needs_human"
                          ? " · "
                          : ""}
                        {item.status === "needs_human" ? "Needs a human" : ""}
                      </div>
                    )}
                  </div>
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
                </button>
              );
            })
          ) : (
            <p className="inbox-list-empty">
              {conversations.length
                ? "No conversations match."
                : channel || activeAccount
                  ? "No conversations on this channel or account yet."
                  : "No conversations yet. Connect a channel or simulate a test message under Integrations."}
            </p>
          )}
        </div>
      </aside>

      {/* Right Column: Chat Main View (Screenshot 9) */}
      <main className="boosend-chat-main">
        <ErrorNotice error={feedback.error} />
        <SuccessNotice notice={feedback.notice} />
        {current ? (
          <>
            {/* Header bar */}
            <div className="boosend-chat-header">
              <div className="boosend-chat-user-head">
                <ContactAvatar
                  name={current.lead.name || "?"}
                  avatarUrl={current.lead.avatar_url}
                  className="boosend-conv-avatar inbox-head-avatar"
                />
                <div>
                  <div className="boosend-chat-user-title">
                    {current.lead.name || "Unknown lead"}
                    {current.lead.handle && (
                      <span className="inbox-head-handle">
                        {current.lead.handle}
                      </span>
                    )}
                  </div>
                  <div className="boosend-chat-user-sub">
                    <ChannelBadge provider={current.provider} compact />
                    <span>{current.connection_name}</span>
                    <span aria-hidden="true">·</span>
                    <Clock size={11} />
                    <span>{lastActive}</span>
                  </div>
                </div>
              </div>

              <div className="boosend-chat-actions">
                <span
                  className={`inbox-live ${live ? "on" : ""}`}
                  title={live ? "Live updates" : "Refreshing every 10 seconds"}
                >
                  {live ? <Wifi size={12} /> : <WifiOff size={12} />}
                  {live ? "Live" : "Polling"}
                </span>
                {left !== null && (
                  <span
                    className={`window-chip ${windowClosed ? "closed" : left < 3600000 ? "soon" : ""}`}
                    title="Meta allows free-form replies for 24 hours after the customer's last message."
                  >
                    <Timer size={13} />
                    {windowClosed ? "24h window closed" : countdown(left)}
                  </span>
                )}
                <ValidatedSelect
                  className="inbox-head-select"
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
                </ValidatedSelect>
                <ValidatedSelect name="status"
                  className="inbox-head-select"
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
                </ValidatedSelect>
                <button
                  type="button"
                  className="boosend-chat-action-btn"
                  aria-label="Refresh"
                  title="Refresh"
                  onClick={refreshAll}
                >
                  <RefreshCw size={15} />
                </button>
                <button
                  type="button"
                  className={`boosend-chat-action-btn ${showInfo ? "on" : ""}`}
                  aria-label="Contact details"
                  aria-pressed={showInfo}
                  title="Contact details"
                  onClick={() => setShowInfo((value) => !value)}
                >
                  <Info size={16} />
                </button>
              </div>
            </div>

            {/* Message Thread */}
            <div className="boosend-chat-messages" ref={bodyRef}>
              {timeline.length ? (
                timeline.map((entry, index) => {
                  const day = new Date(entry.at).toDateString();
                  const newDay =
                    index === 0 ||
                    new Date(timeline[index - 1].at).toDateString() !== day;
                  return (
                    <Fragment key={`${entry.kind}-${entry.item.id}`}>
                      {newDay && (
                        <div className="boosend-date-divider">
                          <span className="boosend-date-divider-text">
                            {new Date(entry.at).toLocaleDateString(undefined, {
                              weekday: "long",
                              month: "long",
                              day: "numeric",
                            })}
                          </span>
                        </div>
                      )}
                      {entry.kind === "note" ? (
                        <div className="inbox-note">
                          <StickyNote size={12} /> {entry.item.text}
                          <time>
                            {new Date(entry.at).toLocaleString()} · internal
                            note
                          </time>
                        </div>
                      ) : entry.kind === "event" ? (
                        <div className="system-event">
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
                        <MessageBubble message={entry.item} />
                      )}
                    </Fragment>
                  );
                })
              ) : (
                <Empty>No messages yet.</Empty>
              )}
            </div>

            {/* Sticky Input Bar matching Screenshot 9 */}
            <div className="boosend-chat-input-bar">
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
                      type="button"
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
                      type="button"
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
                    <p className="inbox-window-note">
                      {current.provider === "whatsapp"
                        ? "The 24-hour reply window has closed. Send an approved message, or wait for the customer to reply."
                        : "The 24-hour messaging window has closed; wait for the customer to write again."}
                    </p>
                  )}
                  {current.provider === "whatsapp" && !current.is_test && (
                    <WhatsAppTemplateComposer key={`${prefix}:${current.id}`} prefix={prefix} conversation={current} onSent={async () => { await loadThread(current.id); await loadList(); }} />
                  )}
                  {attachedFile && (
                    <div className="inbox-attachment">
                      <Paperclip size={13} />
                      <strong>{attachedFile.name}</strong>
                      <span className="muted-text">
                        ({(attachedFile.size / 1024).toFixed(0)} KB)
                      </span>
                      <button
                        type="button"
                        className="icon-button"
                        onClick={() => setAttachedFile(null)}
                        aria-label="Remove attachment"
                      >
                        <X size={12} />
                      </button>
                    </div>
                  )}
                  <ValidatedForm fieldErrors={feedback.fieldErrors} validationTarget={feedback.validationTarget} onEdit={() => feedback.setError("")}
                    onSubmit={(e) => {
                      e.preventDefault();
                      send();
                    }}
                  >
                    <div className="boosend-chat-input-box">
                      <button
                        type="button"
                        className="icon-button"
                        style={{ color: "#94a3b8", padding: "4px" }}
                        aria-label="Attach file"
                        title="Attach file (images, PDFs, audio)"
                        disabled={windowClosed}
                        onClick={() => fileInputRef.current?.click()}
                      >
                        <Plus size={18} />
                      </button>
                      <ValidatedInput
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

                      <ValidatedTextarea
                        ref={composerRef}
                        rows={1}
                        className="boosend-chat-input-field"
                        placeholder={
                          windowClosed
                            ? "Messaging window closed"
                            : "Type a message..."
                        }
                        aria-label="Reply"
                        maxLength={2000}
                        disabled={windowClosed}
                        value={draft}
                        onChange={(e) => setDraft(e.target.value)}
                        onKeyDown={(event) => {
                          if (event.key === "Enter" && !event.shiftKey) {
                            event.preventDefault();
                            send();
                          }
                        }}
                      />

                      <button
                        type="submit"
                        className="boosend-chat-send-btn"
                        aria-label="Send message"
                        title="Send message"
                        disabled={
                          feedback.busy ||
                          (!draft.trim() && !attachedFile) ||
                          windowClosed
                        }
                      >
                        <ArrowUpRight size={16} />
                      </button>
                    </div>
                  </ValidatedForm>
                  <div className="composer-tools">
                    <div className="tool-anchor">
                      <button
                        type="button"
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
                              type="button"
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
                    <div className="tool-anchor">
                      <button
                        type="button"
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
                              <button
                                type="button"
                                onClick={() => insert(reply)}
                              >
                                {reply}
                              </button>
                              <button
                                type="button"
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
                            type="button"
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
                    {offers.length > 0 ? (
                      <ValidatedSelect
                        className="inbox-head-select"
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
                      </ValidatedSelect>
                    ) : (
                      <span className="muted-text inbox-offers-hint">
                        <CreditCard size={12} /> Create offers to send payment
                        links.
                      </span>
                    )}
                    <span className="spacer" />
                    <ValidatedInput
                      placeholder="Internal note (team only)"
                      value={note}
                      onChange={(event) => setNote(event.target.value)}
                      maxLength={5000}
                      aria-label="Internal note"
                      className="note-input"
                    />
                    <button
                      type="button"
                      className="button secondary small"
                      onClick={addNote}
                      disabled={feedback.busy || !note.trim()}
                    >
                      Add note
                    </button>
                  </div>
                </>
              )}
            </div>
          </>
        ) : (
          <div className="boosend-chat-messages">
            <Empty>
              {loading
                ? "Loading…"
                : "Select a conversation to read and reply."}
            </Empty>
          </div>
        )}
      </main>

      {current && showInfo && (
        <aside className="inbox-info-panel" aria-label="Contact details">
          <div className="inbox-info-head">
            <strong>Contact details</strong>
            <button
              type="button"
              className="icon-button"
              aria-label="Close contact details"
              onClick={() => setShowInfo(false)}
            >
              <X size={14} />
            </button>
          </div>
          <div className="inbox-info-profile">
            <ContactAvatar
              name={current.lead.name || "?"}
              avatarUrl={current.lead.avatar_url}
              size={48}
            />
            <div>
              <strong>{current.lead.name || "Unknown lead"}</strong>
              {current.lead.handle && <span>{current.lead.handle}</span>}
            </div>
          </div>
          <Link
            className="button secondary small"
            href={`/w/${workspace.id}/crm?contact=${current.lead.id}`}
          >
            <Contact size={13} /> View in CRM
          </Link>
          <dl className="lead-panel">
            <dt>Email</dt>
            <dd>
              <ValidatedInput
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
              <ValidatedSelect name="stage"
                value={current.lead.stage}
                aria-label="Lead stage"
                onChange={(event) => updateLead({ stage: event.target.value })}
              >
                {STAGES.map((stage) => (
                  <option key={stage} value={stage}>
                    {stage}
                  </option>
                ))}
              </ValidatedSelect>
            </dd>
            {current.lead.tags.length > 0 && (
              <>
                <dt>Tags</dt>
                <dd className="inbox-tags">
                  {current.lead.tags.map((tag) => (
                    <Pill key={tag} tone={tag === "hot" ? "warn" : "neutral"}>
                      {tag}
                    </Pill>
                  ))}
                </dd>
              </>
            )}
            {Object.entries(current.lead.fields).map(([key, value]) => (
              <FieldRow key={key} label={key} value={value} />
            ))}
          </dl>
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
        </aside>
      )}
    </div>
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
    <div className={`boosend-msg-row ${message.direction}`}>
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
          {message.kind === "public_reply" && (
            <small className="bubble-badge">Public comment reply</small>
          )}
          {message.media_url ? (
            <a href={message.media_url} target="_blank" rel="noreferrer">
              Open{" "}
              {message.kind === "image"
                ? "photo"
                : message.kind === "video"
                  ? "video"
                  : "audio"}
            </a>
          ) : (
            message.text || (message.kind === "voice" ? "Voice note" : "…")
          )}
        </span>
      </div>
      <time className="boosend-msg-time">
        {new Date(message.created_at).toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit",
        })}
        {message.provider_status || message.delivery_status ? ` · ${message.provider_status || message.delivery_status}` : ""}
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
