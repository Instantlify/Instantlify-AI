"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { ValidatedForm, ValidatedInput } from "@/components/validated-form";
import { api, ApiError, message } from "@/lib/api";
import type { FieldErrors } from "@/lib/form-errors";
import { Brand } from "@/components/shell";
import { ErrorNotice, SuccessNotice } from "@/components/ui";

/** Passwordless sign-in: request a link, or redeem one from the URL fragment. */
export default function MagicLinkPage() {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [cooldown, setCooldown] = useState(0);
  const resendAt = useRef(0);
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

  useEffect(() => {
    if (cooldown <= 0) return;
    const timer = window.setTimeout(
      () =>
        setCooldown(
          Math.max(0, Math.ceil((resendAt.current - Date.now()) / 1000)),
        ),
      1000,
    );
    return () => window.clearTimeout(timer);
  }, [cooldown]);

  async function request(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || cooldown > 0) return;
    setBusy(true);
    setError("");
    setNotice("");
    setFieldErrors({});
    try {
      const result = await api<{ detail: string; resend_after: number }>(
        "/api/auth/magic-link/",
        "POST",
        {
          email: email.trim(),
        },
      );
      setNotice(result.detail);
      const seconds = result.resend_after || 60;
      resendAt.current = Date.now() + seconds * 1000;
      setCooldown(seconds);
    } catch (err) {
      setFieldErrors(err instanceof ApiError ? err.fieldErrors : {});
      setError(
        err instanceof ApiError && err.status === 503
          ? "Sign-in links are temporarily unavailable. Please try again shortly or sign in with your password."
          : message(err),
      );
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
            <ValidatedForm
              className="stack"
              onSubmit={request}
              fieldErrors={fieldErrors}
              onEdit={() => setError("")}
            >
              <label>
                Email
                <ValidatedInput
                  name="email"
                  type="email"
                  required
                  maxLength={254}
                  autoComplete="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                />
              </label>
              <button
                className="button primary full"
                disabled={busy || cooldown > 0}
              >
                {busy
                  ? "Sending..."
                  : cooldown > 0
                    ? `Resend in ${cooldown}s`
                    : notice
                      ? "Resend sign-in link"
                      : "Email me a sign-in link"}
              </button>
            </ValidatedForm>
            {notice && (
              <p className="muted-text">
                You can request another link after 60 seconds. Each link works
                once and expires after 15 minutes.
              </p>
            )}
          </>
        )}
        <p>
          <Link href="/auth/">Sign in with a password instead</Link>
        </p>
      </div>
    </main>
  );
}
