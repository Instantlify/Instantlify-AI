"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { api, message } from "@/lib/api";
import { Brand } from "@/components/shell";
import { ErrorNotice, SuccessNotice } from "@/components/ui";

/** Passwordless sign-in: request a link, or redeem one from the URL fragment. */
export default function MagicLinkPage() {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [redeeming, setRedeeming] = useState(false);
  const router = useRouter();

  useEffect(() => {
    const token = new URLSearchParams(window.location.hash.slice(1)).get(
      "token",
    );
    if (!token) return;
    // Drop the token from the address bar and history before using it.
    window.history.replaceState(null, "", window.location.pathname);
    queueMicrotask(() => setRedeeming(true));
    api("/api/auth/magic-link/verify/", "POST", { token })
      .then(() => router.replace("/auth/"))
      .catch((err) => {
        setRedeeming(false);
        setError(message(err));
      });
  }, [router]);

  async function request(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const result = await api<{ detail: string }>(
        "/api/auth/magic-link/",
        "POST",
        {
          email: email.trim(),
        },
      );
      setNotice(result.detail);
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="setup-screen">
      <div
        className="auth-card stack"
        style={{ maxWidth: 420, margin: "0 auto" }}
      >
        <Brand />
        <h1>Sign in with a link</h1>
        {redeeming ? (
          <p className="muted-text">Signing you in…</p>
        ) : (
          <>
            <p className="muted-text">
              We&rsquo;ll email you a link that signs you in. It works once and
              expires after 15 minutes.
            </p>
            <ErrorNotice error={error} />
            <SuccessNotice notice={notice} />
            <form className="stack" onSubmit={request}>
              <label>
                Email
                <input
                  type="email"
                  required
                  maxLength={254}
                  autoComplete="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                />
              </label>
              <button className="button primary full" disabled={busy}>
                {busy ? "Sending…" : "Email me a sign-in link"}
              </button>
            </form>
          </>
        )}
        <p>
          <Link href="/auth/">Sign in with a password instead</Link>
        </p>
      </div>
    </main>
  );
}
