"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { api, message } from "@/lib/api";
import { Brand } from "@/components/shell";
import { ErrorNotice, SuccessNotice } from "@/components/ui";

export default function PasswordRecovery() {
  const [credentials, setCredentials] = useState<{
    uid: string;
    token: string;
  } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [done, setDone] = useState(false);

  useEffect(() => {
    function readResetLink() {
      const query = new URLSearchParams(window.location.hash.slice(1));
      const uid = query.get("uid"),
        token = query.get("token");
      if (!uid || !token) return;
      queueMicrotask(() => {
        setCredentials({ uid, token });
        setDone(false);
        setNotice("");
        setError("");
      });
      window.history.replaceState(null, "", window.location.pathname);
    }
    readResetLink();
    window.addEventListener("hashchange", readResetLink);
    return () => window.removeEventListener("hashchange", readResetLink);
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    const values = Object.fromEntries(new FormData(event.currentTarget));
    if (credentials && values.password !== values.confirm) {
      setError("Passwords do not match.");
      setBusy(false);
      return;
    }
    try {
      const result = await api<{ detail: string }>(
        credentials
          ? "/api/auth/password-reset/confirm/"
          : "/api/auth/password-reset/",
        "POST",
        credentials
          ? { ...credentials, password: values.password }
          : { email: values.email },
      );
      setNotice(result.detail);
      setDone(true);
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="setup-screen">
      <Link href="/">
        <Brand />
      </Link>
      <section className="setup-card">
        <h1>{credentials ? "Choose a new password" : "Reset your password"}</h1>
        <p>
          {credentials
            ? "Use at least 12 characters."
            : "Enter your account email and we’ll send you a reset link."}
        </p>
        <ErrorNotice error={error} />
        <SuccessNotice notice={notice} />
        {!done && (
          <form onSubmit={submit}>
            {credentials ? (
              <>
                <label>
                  New password
                  <input
                    name="password"
                    type="password"
                    autoComplete="new-password"
                    minLength={12}
                    maxLength={128}
                    required
                  />
                </label>
                <label>
                  Confirm password
                  <input
                    name="confirm"
                    type="password"
                    autoComplete="new-password"
                    minLength={12}
                    maxLength={128}
                    required
                  />
                </label>
              </>
            ) : (
              <label>
                Email address
                <input
                  name="email"
                  type="email"
                  autoComplete="email"
                  required
                />
              </label>
            )}
            <button className="button primary" disabled={busy}>
              {busy
                ? "Please wait…"
                : credentials
                  ? "Save new password"
                  : "Send reset link"}
            </button>
          </form>
        )}
        <p>
          <Link href="/auth">Back to sign in</Link>
        </p>
        {credentials && !done && (
          <Link
            href="/auth/reset/"
            onClick={() => {
              setCredentials(null);
              setError("");
            }}
          >
            Request a new reset link
          </Link>
        )}
      </section>
    </main>
  );
}
