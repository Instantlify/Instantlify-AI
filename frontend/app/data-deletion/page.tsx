"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, message } from "@/lib/api";

type Status = {
  confirmation_code: string;
  status: string;
  requested_at: string;
  connections_disconnected: number;
};

/** Public status page for Meta data-deletion requests, plus deletion instructions. */
export default function DataDeletionPage() {
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    const code = new URLSearchParams(window.location.search).get("code");
    if (!code) return;
    api<Status>(`/api/public/data-deletion/${encodeURIComponent(code)}/`)
      .then(setStatus)
      .catch((err) => setError(message(err)));
  }, []);

  return (
    <main className="setup-screen">
      <div
        className="stack"
        style={{ maxWidth: 640, margin: "0 auto", padding: 24 }}
      >
        <h1>Data deletion</h1>
        {status && (
          <div className="card stack">
            <strong>
              Request {status.confirmation_code}: {status.status}
            </strong>
            <span className="muted-text">
              Received {new Date(status.requested_at).toLocaleString()}.
              Connected accounts disconnected and their access tokens deleted:{" "}
              {status.connections_disconnected}.
            </span>
          </div>
        )}
        {error && <p className="error-notice">{error}</p>}
        <h2>How to delete your data</h2>
        <ul>
          <li>
            <strong>Removing the app from Instagram or Facebook</strong>{" "}
            disconnects your account in Nemio and deletes its access tokens
            automatically.
          </li>
          <li>
            <strong>Workspace owners</strong> can export or permanently delete
            all workspace data in Settings → Data &amp; privacy.
          </li>
          <li>
            <strong>Customers of a business</strong> who messaged it through
            Nemio can ask that business to delete their conversation and contact
            record.
          </li>
        </ul>
        <p>
          See our <Link href="/privacy/">privacy policy</Link> for details.
        </p>
      </div>
    </main>
  );
}
