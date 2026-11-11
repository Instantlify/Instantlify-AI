"use client";

import { ValidatedForm, ValidatedInput } from "@/components/validated-form";

import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, message } from "@/lib/api";
import { Brand } from "@/components/shell";
import { ErrorNotice, SuccessNotice } from "@/components/ui";

export default function VerifyEmail() {
  const [state, setState] = useState<"checking" | "done" | "resend">(
    "checking",
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  // The link is confirmed on arrival, so React's development double-effect must not
  // fire two requests for the same token.
  const claimed = useRef(false);

  useEffect(() => {
    const token = new URLSearchParams(window.location.hash.slice(1)).get(
      "token",
    );
    // Keep the token out of history and the referrer, as the reset link does.
    if (token) window.history.replaceState(null, "", window.location.pathname);
    if (!token) {
      // Deferred so the state change lands after this effect, not during it.
      queueMicrotask(() => setState("resend"));
      return;
    }
    if (claimed.current) return;
    claimed.current = true;
    api<{ detail: string }>("/api/auth/verify-email/", "POST", { token })
      .then((result) => {
        setNotice(result.detail);
        setState("done");
      })
      .catch((err) => {
        setError(message(err));
        setState("resend");
      });
  }, []);

  async function resend(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    const values = Object.fromEntries(new FormData(event.currentTarget));
    try {
      const result = await api<{ detail: string }>(
        "/api/auth/verify-email/resend/",
        "POST",
        { email: values.email },
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
      <Link href="/">
        <Brand />
      </Link>
      <section className="setup-card">
        <h1>
          {state === "done" ? "Email confirmed" : "Confirm your email address"}
        </h1>
        <p>
          {state === "checking"
            ? "Checking your link…"
            : state === "done"
              ? "Thanks — your address is confirmed and your welcome credits are ready."
              : "Enter your account email and we’ll send a new confirmation link."}
        </p>
        <ErrorNotice error={error} />
        <SuccessNotice notice={notice} />
        {state === "resend" && (
          <ValidatedForm onSubmit={resend}>
            <label>
              Email address
              <ValidatedInput
                name="email"
                type="email"
                autoComplete="email"
                required
              />
            </label>
            <button className="button primary" disabled={busy}>
              {busy ? "Please wait…" : "Send a new link"}
            </button>
          </ValidatedForm>
        )}
        <p>
          <Link href="/auth">Back to sign in</Link>
        </p>
      </section>
    </main>
  );
}
