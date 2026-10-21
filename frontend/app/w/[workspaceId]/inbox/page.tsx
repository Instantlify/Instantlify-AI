"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowUpRight,
  Bookmark,
  Bot,
  ChevronDown,
  Clock,
  CreditCard,
  ExternalLink,
  Filter,
  Hand,
  MessageSquarePlus,
  Paperclip,
  Plus,
  RefreshCw,
  Search,
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
  const [showChannelDropdown, setShowChannelDropdown] = useState(false);
  const feedback = useFeedback();
  const bodyRef = useRef<HTMLDivElement>(null);
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const chatInputRef = useRef<HTMLInputElement>(null);
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

  // Demo messages matching Screenshot 9 if no messages in database yet
  const demoMessages = [
    { id: "d1", direction: "outbound" as const, text: "Hi,\nOur team will get back to you as soon as possible", created_at: "2026-09-24T16:20:00Z", sender: "human" as const, author_name: "Team", kind: "text", delivery_status: null },
    { id: "d2", direction: "outbound" as const, text: "What type of event you wanna host debating or career counseling?", created_at: "2026-09-24T16:31:00Z", sender: "ai" as const, author_name: "AI", kind: "text", delivery_status: null },
    { id: "d3", direction: "inbound" as const, text: "I want to host a debating event on 25 Sept 2026", created_at: "2026-09-24T16:32:00Z", sender: "customer" as const, author_name: "Customer", kind: "text", delivery_status: null },
    { id: "d4", direction: "inbound" as const, text: "How much the debating event cost for 300 participants?", created_at: "2026-09-24T16:38:00Z", sender: "customer" as const, author_name: "Customer", kind: "text", delivery_status: null },
    { id: "d5", direction: "outbound" as const, text: "Hi,\nOur team will get back to you as soon as possible", created_at: "2026-09-24T16:32:00Z", sender: "human" as const, author_name: "Team", kind: "text", delivery_status: null },
    { id: "d6", direction: "outbound" as const, text: "Thanks! Just sent you the details in the message", created_at: "2026-09-24T16:38:00Z", sender: "human" as const, author_name: "Team", kind: "text", delivery_status: null },
    { id: "d7", direction: "outbound" as const, text: "Thanks for your interest! How can we help you?", created_at: "2026-09-24T16:38:00Z", sender: "ai" as const, author_name: "AI", kind: "text", delivery_status: null },
    { id: "d8", direction: "inbound" as const, text: "Hello how are you?", created_at: "2026-09-24T17:41:00Z", sender: "customer" as const, author_name: "Customer", kind: "text", delivery_status: null },
    { id: "d9", direction: "outbound" as const, text: "Hi,\nOur team will get back to you as soon as possible", created_at: "2026-09-24T17:41:00Z", sender: "human" as const, author_name: "Team", kind: "text", delivery_status: null },
  ];

  const activeMessages = timeline.length ? timeline : demoMessages.map(m => ({ kind: "message" as const, at: m.created_at, item: m }));

  return (
    <div className="boosend-inbox-layout">
      {/* Left Column: Conversations Sidebar (Screenshot 9) */}
      <aside className="boosend-inbox-sidebar">
        {/* Channel selector dropdown pill */}
        <div className="boosend-inbox-channel-select-wrap">
          <div style={{ position: "relative" }}>
            <button
              type="button"
              className="boosend-inbox-channel-pill-btn"
              onClick={() => setShowChannelDropdown((v) => !v)}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                <span
                  style={{
                    fontSize: "10px",
                    fontWeight: 700,
                    background: "#f1f5f9",
                    color: "#475569",
                    padding: "2px 6px",
                    borderRadius: "6px",
                  }}
                >
                  All
                </span>
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
                style={{
                  position: "absolute",
                  left: 0,
                  top: "calc(100% + 4px)",
                  width: "100%",
                  background: "#ffffff",
                  border: "1px solid #e2e8f0",
                  borderRadius: "12px",
                  boxShadow: "0 10px 25px rgba(0,0,0,0.1)",
                  padding: "6px",
                  zIndex: 50,
                }}
              >
                {TABS.map((t) => (
                  <button
                    key={t.id}
                    type="button"
                    style={{
                      display: "block",
                      width: "100%",
                      textAlign: "left",
                      padding: "8px 10px",
                      fontSize: "12px",
                      border: "none",
                      background: channel === t.id ? "#f1f5f9" : "transparent",
                      borderRadius: "6px",
                      cursor: "pointer",
                      color: "#0f172a",
                      fontWeight: channel === t.id ? 600 : 400,
                    }}
                    onClick={() => {
                      setChannel(t.id);
                      setShowChannelDropdown(false);
                    }}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Search row with filter icon */}
        <div className="boosend-inbox-search-row">
          <div className="boosend-inbox-search-box">
            <Search size={14} color="#94a3b8" />
            <input
              type="text"
              className="boosend-inbox-search-input"
              placeholder="Search conversations..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <button
            type="button"
            className="boosend-chat-action-btn"
            title="Filter by status"
            onClick={() =>
              setFilter((f) => (f === "all" ? "needs_human" : "all"))
            }
          >
            <Filter size={15} color={filter !== "all" ? "#0f172a" : "#94a3b8"} />
          </button>
        </div>

        {/* Conversations list scroll */}
        <div className="boosend-inbox-list-scroll">
          {visible.length > 0 ? (
            visible.map((item) => {
              const isActive = item.id === selected;
              const firstLetter = item.lead.name?.charAt(0).toUpperCase() || "F";
              const lastText = item.last_message?.text || "No messages yet";

              return (
                <button
                  key={item.id}
                  type="button"
                  className={`boosend-conv-item ${isActive ? "active" : ""}`}
                  onClick={() => setSelected(item.id)}
                >
                  <div className="boosend-conv-avatar">{firstLetter}</div>
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
                  </div>
                </button>
              );
            })
          ) : (
            /* Demo conversation matching Screenshot 9 */
            <button
              type="button"
              className="boosend-conv-item active"
              onClick={() => setSelected("demo-1")}
            >
              <div className="boosend-conv-avatar">F</div>
              <div className="boosend-conv-info">
                <div className="boosend-conv-top">
                  <span className="boosend-conv-name">Facebook user 468752</span>
                  <span className="boosend-conv-date">9/24/2026</span>
                </div>
                <div className="boosend-conv-snippet">
                  Hi, Our team will get back to you as soon...
                </div>
              </div>
            </button>
          )}
        </div>
      </aside>

      {/* Right Column: Chat Main View (Screenshot 9) */}
      <main className="boosend-chat-main">
        {/* Header bar */}
        <div className="boosend-chat-header">
          <div className="boosend-chat-user-head">
            <div className="boosend-conv-avatar" style={{ background: "#0f172a", color: "#ffffff", border: "none" }}>
              {current?.lead.name?.charAt(0).toUpperCase() || "F"}
            </div>
            <div>
              <div className="boosend-chat-user-title">
                {current?.lead.name || "Facebook user 468752"}
              </div>
              <div className="boosend-chat-user-sub">
                <Clock size={11} />
                <span>Last active 9/24/2026</span>
              </div>
            </div>
          </div>

          <div className="boosend-chat-actions">
            <button
              type="button"
              className="boosend-chat-action-btn"
              title="Bookmark / Flag"
            >
              <Bookmark size={16} />
            </button>
            <button
              type="button"
              className="boosend-chat-action-btn"
              title="Toggle Info"
              onClick={() => {
                if (current) {
                  patch({ ai_enabled: !current.ai_enabled });
                }
              }}
            >
              <Bot size={16} color={current?.ai_enabled ? "#10b981" : "#94a3b8"} />
            </button>
          </div>
        </div>

        {/* Message Thread */}
        <div className="boosend-chat-messages" ref={bodyRef}>
          {/* Date Divider */}
          <div className="boosend-date-divider">
            <span className="boosend-date-divider-text">
              Thursday, September 24
            </span>
          </div>

          {activeMessages.map((entry, idx) => {
            const isMsg = entry.kind === "message";
            if (!isMsg) return null;
            const msg = entry.item;
            const isInbound = msg.direction === "inbound";
            const timeStr = new Date(msg.created_at).toLocaleTimeString([], {
              hour: "2-digit",
              minute: "2-digit",
            });

            return (
              <div
                key={`msg-${idx}`}
                className={`boosend-msg-row ${isInbound ? "inbound" : "outbound"}`}
              >
                <div className="boosend-msg-bubble">{msg.text}</div>
                <span className="boosend-msg-time">{timeStr}</span>
              </div>
            );
          })}
        </div>

        {/* Sticky Input Bar matching Screenshot 9 */}
        <div className="boosend-chat-input-bar">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (draft.trim()) {
                if (current) send();
                else {
                  // Fallback demo echo
                  setDraft("");
                }
              }
            }}
          >
            <div className="boosend-chat-input-box">
              <button
                type="button"
                className="icon-button"
                style={{ color: "#94a3b8", padding: "4px" }}
                onClick={() => fileInputRef.current?.click()}
                title="Add attachment"
              >
                <Plus size={18} />
              </button>

              <input
                ref={chatInputRef}
                type="text"
                className="boosend-chat-input-field"
                placeholder="Type a message..."
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
              />

              <button
                type="submit"
                className="boosend-chat-send-btn"
                title="Send message"
              >
                <ArrowUpRight size={16} />
              </button>
            </div>
          </form>
        </div>
      </main>
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
