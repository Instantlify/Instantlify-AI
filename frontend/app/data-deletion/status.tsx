"use client";

import { useEffect, useState } from "react";
import { api, message } from "@/lib/api";

type Status = {
  confirmation_code: string;
  status: string;
  requested_at: string;
  completed_at: string | null;
  connections_disconnected: number;
  connections_deleted: number;
};
const labels: Record<string, string> = {
  pending: "Request received",
  processing: "Deletion in progress",
  needs_review: "Additional review in progress",
  completed: "Completed",
};

export function DeletionStatus() {
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const code = new URLSearchParams(window.location.search).get("code");
    if (!code) return;
    let live = true,
      pending = false,
      completed = false;
    const controller = new AbortController();
    async function refresh() {
      if (pending || completed) return;
      pending = true;
      try {
        const result = await api<Status>(
          `/api/public/data-deletion/${encodeURIComponent(code!)}/`,
          "GET",
          undefined,
          controller.signal,
        );
        if (live) {
          setStatus(result);
          setError("");
          completed = result.status === "completed";
        }
      } catch (err) {
        if (live) setError(message(err));
      } finally {
        pending = false;
      }
    }
    void refresh();
    const timer = window.setInterval(() => {
      if (!document.hidden) void refresh();
    }, 10000);
    window.addEventListener("focus", refresh);
    return () => {
      live = false;
      controller.abort();
      window.clearInterval(timer);
      window.removeEventListener("focus", refresh);
    };
  }, []);
  return (
    <>
      {status && (
        <section
          className="card stack"
          aria-label="Deletion request status"
          aria-live="polite"
        >
          <h2>{labels[status.status] || "Request under review"}</h2>
          <p>
            Confirmation code:{" "}
            <code style={{ overflowWrap: "anywhere" }}>
              {status.confirmation_code}
            </code>
          </p>
          <p>Received {new Date(status.requested_at).toLocaleString()}.</p>
          {status.completed_at && (
            <p>Completed {new Date(status.completed_at).toLocaleString()}.</p>
          )}
          <p>
            Connected accounts disconnected and access tokens removed:{" "}
            {status.connections_disconnected}. Connected account records erased:{" "}
            {status.connections_deleted}.
          </p>
          {status.status !== "completed" && (
            <p>
              This request has not been marked complete. Scope, shared records
              or lawful retention may require verification. Contact our privacy
              team with your confirmation code if you need an update.
            </p>
          )}
          {status.status === "completed" && (
            <p>
              The applicable erasure or verified review is complete. Limited
              records may remain where a lawful retention obligation applies;
              contact our privacy team for details.
            </p>
          )}
        </section>
      )}
      {error && (
        <p role="alert" className="error-notice">
          Unable to load this deletion request: {error}
        </p>
      )}
    </>
  );
}
