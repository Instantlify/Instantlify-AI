"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Bell, X } from "lucide-react";
import { api, message } from "@/lib/api";
import { useWorkspaceSocket } from "@/lib/ws";
import styles from "./assignment-notifications.module.css";

type Assignment = {
  id: string;
  contact_id: string;
  contact_name: string;
  assigned_by: string;
  read: boolean;
};
type Feed = { unread_count: number; results: Assignment[] };

export function AssignmentNotifications({
  workspaceId,
}: {
  workspaceId: string;
}) {
  const [feed, setFeed] = useState<Feed>({ unread_count: 0, results: [] });
  const [open, setOpen] = useState(false);
  const [toast, setToast] = useState<Assignment | null>(null);
  const [error, setError] = useState("");
  const known = useRef<Set<string> | null>(null);
  const root = useRef<HTMLDivElement>(null);
  const pending = useRef(false);
  const endpoint = `/api/workspaces/${workspaceId}/assignment-notifications/`;
  const refresh = useCallback(async () => {
    if (pending.current) return;
    pending.current = true;
    try {
      const next = await api<Feed>(endpoint);
      if (!Array.isArray(next.results)) return;
      const incoming = next.results.find(
        (item) => !item.read && known.current && !known.current.has(item.id),
      );
      if (incoming) setToast(incoming);
      known.current = new Set(next.results.map((item) => item.id));
      setFeed(next);
      setError("");
    } catch (err) {
      setError(message(err));
    } finally {
      pending.current = false;
    }
  }, [endpoint]);
  useWorkspaceSocket(workspaceId, refresh);
  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => {
      if (!document.hidden) void refresh();
    }, 15000);
    window.addEventListener("focus", refresh);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("focus", refresh);
    };
  }, [refresh]);
  useEffect(() => {
    if (!open) return;
    const outside = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);
  async function markRead(id?: string) {
    try {
      await api(endpoint, "PATCH", id ? { id } : { all_read: true });
      setToast(null);
      await refresh();
    } catch (err) {
      setError(message(err));
    }
  }
  async function view(item: Assignment) {
    await markRead(item.id);
    window.location.assign(
      new URL(
        `/w/${workspaceId}/crm?contact=${encodeURIComponent(item.contact_id)}`,
        window.location.origin,
      ).href,
    );
  }
  return (
    <div className={styles.root} ref={root}>
      <button
        type="button"
        className={`icon-button ${styles.bell}`}
        aria-label={`Assignments, ${feed.unread_count} unread`}
        aria-expanded={open}
        onClick={() => {
          setOpen(!open);
          void refresh();
        }}
      >
        <Bell size={19} />
        {feed.unread_count > 0 && (
          <span className={styles.count}>
            {feed.unread_count > 99 ? "99+" : feed.unread_count}
          </span>
        )}
      </button>
      {open && (
        <section className={styles.panel} aria-label="Assignment notifications">
          <header>
            <strong>Assignments</strong>
            <button
              type="button"
              className="text-button"
              disabled={!feed.unread_count}
              onClick={() => void markRead()}
            >
              Mark all read
            </button>
          </header>
          {error && <p role="alert">{error}</p>}
          {!feed.results.length && !error && <p>No assignments yet.</p>}
          {feed.results.map((item) => (
            <button
              type="button"
              className={`${styles.item} ${!item.read ? styles.unread : ""}`}
              key={item.id}
              onClick={() => void view(item)}
            >
              <strong>{item.contact_name}</strong>
              <span>{item.assigned_by} assigned this contact to you.</span>
            </button>
          ))}
        </section>
      )}
      {toast && (
        <div className={styles.toast} role="status">
          <button
            type="button"
            className={styles.toastLink}
            onClick={() => void view(toast)}
          >
            New assignment: <strong>{toast.contact_name}</strong>
          </button>
          <button
            type="button"
            className="icon-button"
            aria-label="Dismiss assignment alert"
            onClick={() => setToast(null)}
          >
            <X size={16} />
          </button>
        </div>
      )}
    </div>
  );
}
