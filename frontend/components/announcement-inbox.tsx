"use client";

import { useCallback, useEffect, useState } from "react";
import { api, message } from "@/lib/api";
import styles from "./assignment-notifications.module.css";

type Notice = {
  id: string;
  title: string;
  body: string;
  link_url: string;
  delivered_at: string;
  read_at: string | null;
  acknowledged_at: string | null;
  requires_acknowledgement: boolean;
  expired: boolean;
};
type Feed = {
  results: Notice[];
  unread_count: number;
  count: number;
  next: string | null;
  previous: string | null;
};
const empty: Feed = {
  results: [],
  unread_count: 0,
  count: 0,
  next: null,
  previous: null,
};

export function AnnouncementInbox({
  workspaceId,
  section,
  open,
  onCount,
}: {
  workspaceId: string;
  section: string;
  open: boolean;
  onCount: (count: number) => void;
}) {
  const [feed, setFeed] = useState<Feed>(empty);
  const [page, setPage] = useState(1);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const endpoint = `/api/notifications/?${new URLSearchParams({ workspace_id: workspaceId, section, page: String(page) })}`;
  const refresh = useCallback(async () => {
    const next = await api<Feed>(endpoint);
    if (!Array.isArray(next.results)) return;
    setFeed(next);
    onCount(next.unread_count);
    setError("");
  }, [endpoint, onCount]);
  useEffect(() => {
    let live = true;
    let pending = false;
    async function poll() {
      if (pending) return;
      pending = true;
      try {
        const next = await api<Feed>(endpoint);
        if (live && Array.isArray(next.results)) {
          setFeed(next);
          onCount(next.unread_count);
          setError("");
        }
      } catch (err) {
        if (live) setError(message(err));
      } finally {
        pending = false;
      }
    }
    void poll();
    const timer = window.setInterval(() => {
      if (!document.hidden) void poll();
    }, 15000);
    window.addEventListener("focus", poll);
    window.addEventListener("instantlify:notifications-changed", poll);
    return () => {
      live = false;
      window.clearInterval(timer);
      window.removeEventListener("focus", poll);
      window.removeEventListener("instantlify:notifications-changed", poll);
    };
  }, [endpoint, onCount]);
  async function update(item?: Notice, acknowledge = false) {
    if (busy) return;
    setBusy(true);
    try {
      await api(
        "/api/notifications/",
        "PATCH",
        item ? { id: item.id, acknowledge } : { all_read: true },
      );
      await refresh();
      window.dispatchEvent(new Event("instantlify:notifications-changed"));
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  }
  if (!open) return null;
  return (
    <div aria-label="Announcement history">
      <header>
        <strong>Announcements</strong>
        <button
          className="text-button"
          disabled={busy || !feed.unread_count}
          onClick={() => void update()}
        >
          Mark announcements read
        </button>
      </header>
      {error && <p role="alert">{error}</p>}
      {!feed.results.length && !error && <p>No announcements yet.</p>}
      {feed.results.map((item) => (
        <article
          key={item.id}
          className={`${styles.item} ${!item.read_at ? styles.unread : ""}`}
        >
          <strong>{item.title}</strong>
          <span>{item.body}</span>
          <span>
            {new Date(item.delivered_at).toLocaleString()} ·{" "}
            {item.read_at ? "Read" : "Unread"}
            {item.expired ? " · Expired" : ""}
          </span>
          {item.acknowledged_at && (
            <span>
              Acknowledged {new Date(item.acknowledged_at).toLocaleString()}
            </span>
          )}
          <div className={styles.actions}>
            {item.link_url && (
              <a href={item.link_url} target="_blank" rel="noopener noreferrer">
                Learn more
              </a>
            )}
            {!item.read_at && (
              <button
                className="text-button"
                disabled={busy}
                onClick={() => void update(item)}
              >
                Mark read
              </button>
            )}
            {item.requires_acknowledgement && !item.acknowledged_at && (
              <button
                className="button"
                disabled={busy}
                onClick={() => void update(item, true)}
              >
                Acknowledge
              </button>
            )}
          </div>
        </article>
      ))}
      {(feed.previous || feed.next) && (
        <nav className={styles.actions} aria-label="Notification history pages">
          <button
            className="text-button"
            disabled={!feed.previous || busy}
            onClick={() => setPage(page - 1)}
          >
            Previous
          </button>
          <span>Page {page}</span>
          <button
            className="text-button"
            disabled={!feed.next || busy}
            onClick={() => setPage(page + 1)}
          >
            Next
          </button>
        </nav>
      )}
    </div>
  );
}
