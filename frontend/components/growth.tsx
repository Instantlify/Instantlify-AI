"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Gift, Instagram, MessageCircle, Send, X } from "lucide-react";
import { api, message, type Connection } from "@/lib/api";
import {
  announcements,
  chat,
  claimPromo,
  EMAIL_CARD,
  markSeen,
  NAME_CARD,
  promo,
  tourStep,
  trackVisit,
  type Announcement,
  type Campaign,
  type TourStep,
} from "@/lib/growth";

/** Strips repeat until dismissed for this browser session; popups are once per
 * viewer, and the server stops returning them after the first `seen`. */
export function Announcements({
  workspaceId,
  page,
}: {
  workspaceId: string;
  page: string;
}) {
  const [items, setItems] = useState<Announcement[]>([]);
  const [hidden, setHidden] = useState<number[]>([]);

  useEffect(() => {
    let live = true;
    announcements(page, workspaceId)
      .then((rows) => {
        if (live) setItems(rows);
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [page, workspaceId]);

  function dismiss(item: Announcement) {
    setHidden((current) => [...current, item.id]);
    markSeen(item.id).catch(() => undefined);
  }

  const visible = items.filter((item) => !hidden.includes(item.id));
  const strips = visible.filter((item) => item.type === "strip");
  const popup = visible.find((item) => item.type === "popup");
  return (
    <>
      {strips.map((item) => (
        <div
          key={item.id}
          className={`announcement-strip tone-${item.tone}`}
          role="status"
        >
          <span>
            <strong>{item.title || item.name}</strong>
            {item.body ? ` ${item.body}` : ""}
            {item.link_url && (
              <a href={item.link_url} target="_blank" rel="noopener noreferrer">
                Learn more
              </a>
            )}
          </span>
          <button
            className="icon-button"
            aria-label="Dismiss announcement"
            onClick={() => dismiss(item)}
          >
            <X size={15} />
          </button>
        </div>
      ))}
      {popup && (
        <div className="modal-backdrop" role="presentation">
          <div
            className="modal announcement-popup"
            role="dialog"
            aria-modal="true"
            aria-labelledby={`announcement-${popup.id}`}
          >
            <h2 id={`announcement-${popup.id}`}>{popup.title || popup.name}</h2>
            {popup.body && <p>{popup.body}</p>}
            <div className="modal-actions">
              {popup.link_url && (
                <a
                  className="button"
                  href={popup.link_url}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Learn more
                </a>
              )}
              <button className="button primary" onClick={() => dismiss(popup)}>
                Got it
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

/** The in-app gift box. Fetching counts as `shown`; claiming is a separate event,
 * and the discount landing on a real subscription is recorded server-side. */
export function PromoGift({ workspaceId }: { workspaceId: string }) {
  const [campaign, setCampaign] = useState<Campaign | null>(null);
  const [claimed, setClaimed] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    let live = true;
    promo(workspaceId)
      .then((body) => {
        if (live) setCampaign(body.campaign);
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [workspaceId]);

  if (!campaign) return null;
  async function claim() {
    if (!campaign) return;
    setError("");
    try {
      await claimPromo(workspaceId, campaign.slug);
      setClaimed(true);
    } catch (err) {
      setError(message(err));
    }
  }
  const interval =
    campaign.target_interval === "both"
      ? "any plan"
      : `${campaign.target_interval} plans`;
  return (
    <section className="promo-gift" aria-live="polite">
      <Gift size={20} />
      <div>
        <strong>
          {campaign.discount_percent}% off {interval}
        </strong>
        <p>
          {claimed
            ? "Claimed. The discount applies at your next checkout."
            : campaign.name}
        </p>
        {error && <p className="error-text">{error}</p>}
      </div>
      {!claimed && (
        <button className="button primary" onClick={claim}>
          Claim offer
        </button>
      )}
    </section>
  );
}

/** Persistent until an account is connected — it cannot be dismissed, so nobody
 * wanders into an empty automation builder with nothing to trigger on. */
export function ConnectPrompt({ workspaceId }: { workspaceId: string }) {
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    let live = true;
    api<{ results: Connection[] }>(
      `/api/workspaces/${workspaceId}/connections/`,
    )
      .then((body) => {
        if (live)
          setMissing(
            !body.results.some((item) => item.status !== "disconnected"),
          );
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, [workspaceId]);

  if (!missing) return null;
  return (
    <section className="connect-prompt" role="region" aria-label="Connect">
      <Instagram size={22} />
      <div>
        <strong>Connect your Instagram account</strong>
        <p>
          Your automations and AI agent need a connected account to listen to.
          It takes about a minute.
        </p>
      </div>
      <Link className="button primary" href={`/w/${workspaceId}/integrations`}>
        Connect account
      </Link>
    </section>
  );
}

/** Reports one product-tour step when the page it names is first opened. */
export function TourMarker({
  workspaceId,
  step,
}: {
  workspaceId: string;
  step: TourStep;
}) {
  const sent = useRef(false);
  useEffect(() => {
    if (sent.current) return;
    sent.current = true;
    tourStep(workspaceId, step);
  }, [workspaceId, step]);
  return null;
}

/** First-party page-visit beacon for public marketing pages. */
export function TrackVisit({ page }: { page: string }) {
  const sent = useRef(false);
  useEffect(() => {
    if (sent.current) return;
    sent.current = true;
    trackVisit(page);
  }, [page]);
  return null;
}

type Line = { from: "you" | "bot"; text: string };

/** Nemio's support assistant. A sentinel reply renders a real input field instead
 * of the bot asking in prose and hoping the answer comes back parseable. */
export function SupportChat({
  defaultName = "",
  defaultEmail = "",
}: {
  defaultName?: string;
  defaultEmail?: string;
}) {
  const [lines, setLines] = useState<Line[]>([
    {
      from: "bot",
      text: "Hi! Ask me anything about Nemio, or ask for a ticket and a teammate will follow up.",
    },
  ]);
  const [name, setName] = useState(defaultName);
  const [email, setEmail] = useState(defaultEmail);
  const [card, setCard] = useState<string | null>(null);
  const [pending, setPending] = useState("");
  const [busy, setBusy] = useState(false);
  const [ticket, setTicket] = useState("");

  async function send(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const text = String(new FormData(form).get("message") ?? "").trim();
    if (!text) return;
    form.reset();
    setLines((current) => [...current, { from: "you", text }]);
    const wantsTicket = /\b(ticket|human|agent|someone|support)\b/i.test(text);
    await turn(text, wantsTicket);
  }

  async function turn(
    text: string,
    wantsTicket: boolean,
    who = name,
    address = email,
  ) {
    setBusy(true);
    try {
      if (wantsTicket && who && address) {
        const opened = await chat({
          create_ticket: true,
          name: who,
          email: address,
          subject: text.slice(0, 200),
          body: text,
        });
        if (opened.ticket_number) {
          setTicket(opened.ticket_number);
          setLines((current) => [
            ...current,
            {
              from: "bot",
              text: `Ticket ${opened.ticket_number} is open. We'll reply by email.`,
            },
          ]);
          return;
        }
      }
      const reply = await chat({
        message: text,
        name: who,
        email: address,
        wants_ticket: wantsTicket,
      });
      if (reply.sentinel === NAME_CARD || reply.sentinel === EMAIL_CARD) {
        setPending(text);
        setCard(reply.sentinel);
        return;
      }
      setLines((current) => [...current, { from: "bot", text: reply.reply }]);
    } catch (err) {
      setLines((current) => [...current, { from: "bot", text: message(err) }]);
    } finally {
      setBusy(false);
    }
  }

  /** A card was answered: store the detail, ask for the next one if still missing,
   * then resume the request that asked for it. */
  async function submitCard(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = String(
      new FormData(event.currentTarget).get("value") ?? "",
    ).trim();
    if (!value) return;
    const who = card === NAME_CARD ? value : name;
    const address = card === EMAIL_CARD ? value : email;
    setName(who);
    setEmail(address);
    if (!address) {
      setCard(EMAIL_CARD);
      return;
    }
    setCard(null);
    const text = pending;
    setPending("");
    if (text) await turn(text, true, who, address);
  }

  return (
    <section className="support-chat" aria-label="Support chat">
      <header>
        <MessageCircle size={17} /> Nemio support
      </header>
      <ol className="chat-log" aria-live="polite">
        {lines.map((line, index) => (
          <li key={index} className={line.from}>
            {line.text}
          </li>
        ))}
      </ol>
      {card ? (
        <form className="chat-card" onSubmit={submitCard}>
          <label>
            {card === NAME_CARD ? "Your name" : "Your email"}
            <input
              name="value"
              type={card === NAME_CARD ? "text" : "email"}
              autoComplete={card === NAME_CARD ? "name" : "email"}
              required
              autoFocus
            />
          </label>
          <button className="button primary">Continue</button>
        </form>
      ) : (
        <form className="chat-input" onSubmit={send}>
          <input
            name="message"
            placeholder={ticket ? "Anything else?" : "Type your question…"}
            aria-label="Message"
            maxLength={2000}
            disabled={busy}
          />
          <button
            className="icon-button"
            aria-label="Send message"
            disabled={busy}
          >
            <Send size={16} />
          </button>
        </form>
      )}
    </section>
  );
}
