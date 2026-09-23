"use client";

import { useState } from "react";
import { api, message, type User } from "@/lib/api";

/** An unconfirmed address gets no welcome credits and no password recovery, and the
 * signup is released after a couple of weeks. Nobody goes looking in their inbox
 * unprompted, so say so where the work happens. */
export function VerifyBanner({ user }: { user: User }) {
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  if (user.email_verified) return null;

  async function resend() {
    setBusy(true);
    setError("");
    try {
      await api("/api/auth/verify-email/resend/", "POST", {
        email: user.email,
      });
      setSent(true);
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="notice-card" role="status">
      <p>
        <strong>Confirm your email address.</strong> We sent a link to{" "}
        {user.email}. Confirming unlocks your welcome AI credits and lets you
        recover the account if you lose the password.
      </p>
      {error && <p className="error-text">{error}</p>}
      {sent ? (
        <p className="muted-text">A new link is on its way.</p>
      ) : (
        <button
          type="button"
          className="button"
          disabled={busy}
          onClick={resend}
        >
          {busy ? "Sending…" : "Resend the link"}
        </button>
      )}
    </div>
  );
}
