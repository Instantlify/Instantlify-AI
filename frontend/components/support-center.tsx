"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { MessageCircle, X, Send, Plus, RefreshCw } from "lucide-react";
import { api, message } from "@/lib/api";
import { SupportChat } from "@/components/growth";

export type Ticket = {
  id: number;
  ticket_number: string;
  subject: string;
  body: string;
  category: string;
  status: string;
  created_at: string;
  updated_at: string;
  messages: {
    id: number;
    body: string;
    from_staff: boolean;
    created_at: string;
  }[];
};

export function TicketForm({
  workspaceId,
  onCreated,
}: {
  workspaceId?: string;
  onCreated?: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [reference, setReference] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = Object.fromEntries(new FormData(form));
    setBusy(true);
    setError("");
    try {
      const result = await api<{ ticket_number: string }>(
        workspaceId
          ? `/api/workspaces/${workspaceId}/support/tickets/`
          : "/api/growth/tickets/",
        "POST",
        data,
      );
      setReference(result.ticket_number);
      form.reset();
      onCreated?.();
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  }
  if (reference)
    return (
      <div className="support-confirmation" role="status">
        <strong>Ticket {reference} created</strong>
        <p>
          {workspaceId
            ? "Follow its status and continue the conversation in My tickets."
            : "Your request is saved. Our support team can reply to the email you provided."}
        </p>
        {workspaceId && (
          <Link className="button primary" href={`/w/${workspaceId}/support/`}>
            View my tickets
          </Link>
        )}
        <button className="text-button" onClick={() => setReference("")}>
          Create another ticket
        </button>
      </div>
    );
  return (
    <form
      className="support-form"
      onSubmit={submit}
      aria-label="Raise a ticket"
    >
      <p>
        Tell us what happened and what you expected. Don’t include passwords or
        payment details.
      </p>
      {!workspaceId && (
        <>
          <label>
            Your name
            <input name="name" autoComplete="name" required maxLength={120} />
          </label>
          <label>
            Your email
            <input
              type="email"
              name="email"
              autoComplete="email"
              required
              maxLength={254}
            />
          </label>
        </>
      )}
      <label>
        Category
        <select name="category">
          <option value="support">General support</option>
          <option value="billing">Billing</option>
          <option value="bug">Report a bug</option>
        </select>
      </label>
      <label>
        Subject
        <input name="subject" required maxLength={200} />
      </label>
      <label>
        Describe the issue
        <textarea name="body" required maxLength={10000} rows={4} />
      </label>
      {error && (
        <p role="alert" className="error-notice">
          {error}
        </p>
      )}
      <button className="button primary" disabled={busy}>
        {busy ? "Submitting…" : "Submit ticket"}
      </button>
    </form>
  );
}

export function SupportWidget({
  workspaceId,
  name = "",
  email = "",
}: {
  workspaceId?: string;
  name?: string;
  email?: string;
}) {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<"chat" | "ticket">("chat");
  const trigger = useRef<HTMLButtonElement>(null);
  const close = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    close.current?.focus();
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        trigger.current?.focus();
      }
    };
    document.addEventListener("keydown", escape);
    return () => document.removeEventListener("keydown", escape);
  }, [open]);
  if (!workspaceId && pathname.startsWith("/w/")) return null;
  return (
    <div
      className={`support-widget${pathname.match(/\/w\/[^/]+\/inbox\/?$/) ? " inbox-support" : ""}`}
    >
      <aside
        hidden={!open}
        className="support-widget-panel"
        role="dialog"
        aria-label="Nemio help and support"
      >
        <header className="support-widget-header">
          <div>
            <strong>Nemio support</strong>
            <p>Questions, answers and a little help.</p>
          </div>
          <button
            ref={close}
            className="icon-button"
            aria-label="Close support"
            onClick={() => {
              setOpen(false);
              trigger.current?.focus();
            }}
          >
            <X size={19} />
          </button>
        </header>
        <div
          className="support-widget-tabs"
          role="group"
          aria-label="Support options"
        >
          <button aria-pressed={tab === "chat"} onClick={() => setTab("chat")}>
            Ask a question
          </button>
          <button
            aria-pressed={tab === "ticket"}
            onClick={() => setTab("ticket")}
          >
            Raise a ticket
          </button>
          {workspaceId && (
            <Link
              href={`/w/${workspaceId}/support/`}
              onClick={() => setOpen(false)}
            >
              My tickets ↗
            </Link>
          )}
        </div>
        <div className="support-widget-body">
          <div hidden={tab !== "chat"}>
            <SupportChat
              defaultName={name}
              defaultEmail={email}
              workspaceId={workspaceId}
            />
          </div>
          <div hidden={tab !== "ticket"}>
            <TicketForm workspaceId={workspaceId} />
          </div>
        </div>
      </aside>
      <button
        ref={trigger}
        className="support-launcher"
        aria-expanded={open}
        aria-label={open ? "Hide support" : "Chat with us"}
        onClick={() => setOpen(!open)}
      >
        <MessageCircle size={20} />
        <span>{open ? "Close" : "Need a hand?"}</span>
      </button>
    </div>
  );
}

export function MyTickets({ workspaceId }: { workspaceId: string }) {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);
  const [sending, setSending] = useState(false);
  const url = `/api/workspaces/${workspaceId}/support/tickets/`;
  async function load() {
    setLoading(true);
    setError("");
    try {
      setTickets(await api<Ticket[]>(url));
    } catch (err) {
      setError(message(err));
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    let active = true;
    api<Ticket[]>(url)
      .then((data) => {
        if (active) setTickets(data);
      })
      .catch((err) => {
        if (active) setError(message(err));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [url]);
  const ticket = tickets.find((t) => t.id === selected);
  async function reply(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!ticket) return;
    const form = event.currentTarget;
    setSending(true);
    setError("");
    try {
      const updated = await api<Ticket>(`${url}${ticket.id}/replies/`, "POST", {
        body: new FormData(form).get("body"),
      });
      setTickets((current) =>
        current.map((t) => (t.id === updated.id ? updated : t)),
      );
      form.reset();
    } catch (err) {
      setError(message(err));
    } finally {
      setSending(false);
    }
  }
  return (
    <section className="support-center">
      <div className="support-center-toolbar">
        <p>Track your requests and reply to the support team.</p>
        <div className="button-row">
          <button
            className="button secondary"
            onClick={load}
            disabled={loading}
          >
            <RefreshCw size={15} />
            Refresh
          </button>
          <button
            className="button primary"
            onClick={() => setCreating(!creating)}
          >
            <Plus size={15} />
            Raise a ticket
          </button>
        </div>
      </div>
      {creating && (
        <section className="panel">
          <h2>Raise a ticket</h2>
          <TicketForm workspaceId={workspaceId} onCreated={load} />
        </section>
      )}
      {error && (
        <p className="error-notice" role="alert">
          {error}
        </p>
      )}
      {loading ? (
        <p role="status">Loading your tickets…</p>
      ) : (
        <div className="support-ticket-layout">
          <div className="support-ticket-list">
            {tickets.length ? (
              tickets.map((t) => (
                <button
                  key={t.id}
                  className={`support-ticket-item ${t.id === selected ? "selected" : ""}`}
                  onClick={() => {
                    setSelected(t.id);
                    setCreating(false);
                  }}
                >
                  <span className="support-ticket-meta">
                    {t.ticket_number} · {t.category}
                    <span>{t.status === "resolved" ? "Resolved" : "Open"}</span>
                  </span>
                  <strong>{t.subject}</strong>
                  <small>
                    Updated {new Date(t.updated_at).toLocaleString()}
                  </small>
                </button>
              ))
            ) : (
              <div className="panel">
                <h2>No tickets yet</h2>
                <p>
                  Need help? Raise a ticket and follow the conversation here.
                </p>
              </div>
            )}
          </div>
          <div className="panel support-ticket-thread">
            {ticket ? (
              <>
                <div className="support-ticket-meta">
                  {ticket.ticket_number} ·{" "}
                  {ticket.status === "resolved" ? "Resolved" : "Open"}
                </div>
                <h2>{ticket.subject}</h2>
                <article className="support-thread-message">
                  <strong>You</strong>
                  <p>{ticket.body}</p>
                </article>
                {ticket.messages.map((m) => (
                  <article
                    key={m.id}
                    className={`support-thread-message ${m.from_staff ? "staff" : ""}`}
                  >
                    <strong>{m.from_staff ? "Nemio support" : "You"}</strong>
                    <small>{new Date(m.created_at).toLocaleString()}</small>
                    <p>{m.body}</p>
                  </article>
                ))}
                <form className="support-form" onSubmit={reply}>
                  <label>
                    Reply
                    <textarea name="body" required maxLength={10000} rows={4} />
                  </label>
                  {ticket.status === "resolved" && (
                    <p>Sending a reply reopens this ticket.</p>
                  )}
                  <button className="button primary" disabled={sending}>
                    <Send size={15} />
                    {sending ? "Sending…" : "Send reply"}
                  </button>
                </form>
              </>
            ) : (
              <p>Select a ticket to read its conversation.</p>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
