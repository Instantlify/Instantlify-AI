"use client";

import { ValidatedForm, ValidatedInput } from "@/components/validated-form";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  ArrowDownLeft,
  ArrowRight,
  Check,
  GitBranch,
  MessageCircle,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { api, ApiError, message, type Branding, type User } from "@/lib/api";
import type { FieldErrors } from "@/lib/form-errors";
import { lastWorkspaceId, loadWorkspaces } from "@/lib/workspace";
import { Brand, WorkspaceForm } from "@/components/shell";
import { ErrorNotice } from "@/components/ui";
import { TrackVisit } from "@/components/growth";

export default function AuthPage({ signup = false }: { signup?: boolean }) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [branding, setBranding] = useState<Branding | null>(null);
  const inviteHandled = useRef(false);

  useEffect(() => {
    const controller = new AbortController();
    api<Branding>("/api/public/branding/", "GET", undefined, controller.signal)
      .then(setBranding)
      .catch(() => undefined);
    api<User>("/api/auth/me/", "GET", undefined, controller.signal)
      .then(setUser)
      .catch((err) => {
        if (
          !controller.signal.aborted &&
          !(err instanceof ApiError && [401, 403].includes(err.status))
        )
          setError(message(err));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, []);

  // Once signed in: accept a pending invite, then go to the last (or first) workspace.
  useEffect(() => {
    if (!user) return;
    const controller = new AbortController();
    (async () => {
      try {
        const token = new URLSearchParams(window.location.search).get("invite");
        let target: string | null = null;
        if (token && !inviteHandled.current) {
          inviteHandled.current = true;
          const url = new URL(window.location.href);
          url.searchParams.delete("invite");
          window.history.replaceState(null, "", url.toString());
          try {
            const joined = await api<{ workspace_id: string }>(
              "/api/invitations/accept/",
              "POST",
              { token },
            );
            target = joined.workspace_id;
          } catch (err) {
            setError(message(err));
          }
        }
        const all = await loadWorkspaces(controller.signal);
        // Nobody lands on an empty product. A first-time account goes through the
        // setup wizard, which is also what produces the signup funnel.
        if (!all.length) {
          const query = new URLSearchParams(window.location.search);
          query.delete("mode");
          query.delete("invite");
          router.replace(`/onboarding?${query.toString()}`);
          return;
        }
        const remembered = lastWorkspaceId();
        const chosen =
          target ||
          (remembered && all.some((w) => w.id === remembered)
            ? remembered
            : all[0].id);
        const selected = new URLSearchParams(window.location.search);
        const plan = selected.get("plan");
        const destination = plan
          ? `settings?tab=subscription&plan=${encodeURIComponent(plan)}&interval=${selected.get("interval") === "annual" ? "annual" : "monthly"}`
          : "overview";
        router.replace(`/w/${chosen}/${destination}`);
      } catch (err) {
        if (!controller.signal.aborted) {
          setError(message(err));
          setLoading(false);
        }
      }
    })();
    return () => controller.abort();
  }, [user, router]);

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const created = await api<{ id: string }>(
        "/api/workspaces/",
        "POST",
        Object.fromEntries(new FormData(event.currentTarget)),
      );
      router.replace(`/w/${created.id}/overview`);
    } catch (err) {
      setError(message(err));
      setBusy(false);
    }
  }

  if (loading || (user && busy))
    return (
      <div className="loading-screen">
        <Brand name={branding?.brand_name} logo={branding?.logo_url} />
        <p>Opening your workspace…</p>
      </div>
    );
  if (user)
    return (
      <div className="setup-screen">
        <Brand name={branding?.brand_name} logo={branding?.logo_url} />
        <section className="setup-card">
          <span className="section-icon">
            <GitBranch size={26} />
          </span>
          <span className="eyebrow">LET’S MAKE IT YOURS</span>
          <h1>A home for your business.</h1>
          <p>
            Create a workspace to keep your team, connected accounts, and
            conversations together.
          </p>
          <ErrorNotice error={error} />
          <WorkspaceForm create={create} busy={busy} />
        </section>
      </div>
    );
  return (
    <Auth
      onSuccess={(me) => {
        setLoading(true);
        setUser(me);
      }}
      initialError={error}
      branding={branding}
      signupInitially={signup}
    />
  );
}

function Auth({
  onSuccess,
  initialError,
  branding,
  signupInitially,
}: {
  onSuccess: (user: User) => void;
  initialError: string;
  branding: Branding | null;
  signupInitially: boolean;
}) {
  const [signup, setSignup] = useState(signupInitially);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(initialError);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const name = branding?.brand_name || "Nemio";
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setFieldErrors({});
    const data = Object.fromEntries(new FormData(event.currentTarget));
    try {
      onSuccess(
        await api<User>(
          `/api/auth/${signup ? "signup" : "login"}/`,
          "POST",
          data,
        ),
      );
    } catch (err) {
      setFieldErrors(err instanceof ApiError ? err.fieldErrors : {});
      setError(message(err));
    } finally {
      setBusy(false);
    }
  }
  return (
    <main
      className="auth-layout"
      style={{
        ["--green" as string]:
          branding?.primary_color && branding.primary_color !== "#347359"
            ? branding.primary_color
            : "var(--brand-action)",
      }}
    >
      <TrackVisit page="/auth" />
      <section className="auth-story">
        <Link href="/" aria-label="Back to home">
          <Brand name={name} logo={branding?.logo_url} />
        </Link>
        <div className="story-copy">
          <span className="eyebrow">
            A LITTLE LESS BUSYWORK. A LOT MORE CONNECTION.
          </span>
          <h1>
            Good conversations.
            <br />
            <em>Great possibilities.</em>
          </h1>
          <p>
            Give your team a home for every customer conversation. Automate the
            first hello, let the AI qualify and book, and step in when it
            matters.
          </p>
          <div className="conversation-art" aria-hidden="true">
            <div className="art-orbit" />
            <div className="art-bubble first">
              <MessageCircle size={22} />
              <span>A conversation starts.</span>
              <span className="small-dot" />
            </div>
            <div className="art-line" />
            <div className="art-bubble second">
              <span className="mini-brand">
                <Sparkles size={20} />
              </span>
              <span>Make it a meaningful one.</span>
              <Check size={18} />
            </div>
            <div className="art-chip">
              <ShieldCheck size={15} /> Your business. Your workspace.
            </div>
          </div>
        </div>
        <div className="story-footer">
          Built for teams. Designed for connection.
          {!branding?.hide_platform_branding && (
            <span>© {new Date().getFullYear()} Nemio</span>
          )}
        </div>
      </section>
      <section className="auth-form-wrap">
        <div className="auth-top">
          {signup ? "Already have an account?" : `New to ${name}?`}
          <button
            className="text-button"
            onClick={() => {
              setSignup(!signup);
              setError("");
            }}
          >
            {signup ? "Sign in" : "Create an account"}
            <ArrowRight size={15} />
          </button>
        </div>
        <div className="auth-form">
          <span className="section-icon">
            <ArrowDownLeft size={23} />
          </span>
          <h2>{signup ? "Make room for what’s next." : "Welcome back."}</h2>
          <p>
            {signup
              ? "Start with your account. Your workspace comes next."
              : "Sign in and pick up the conversation."}
          </p>
          <ValidatedForm
            onSubmit={submit}
            fieldErrors={fieldErrors}
            onEdit={() => setError("")}
          >
            <ErrorNotice error={error} />
            {signup && (
              <label>
                Your name
                <ValidatedInput
                  name="name"
                  autoComplete="name"
                  placeholder="Alex Morgan"
                  maxLength={150}
                  required
                />
              </label>
            )}
            <label>
              Email address
              <ValidatedInput
                name="email"
                type="email"
                autoComplete="email"
                placeholder="you@company.com"
                required
              />
            </label>
            <label>
              Password
              <ValidatedInput
                name="password"
                type="password"
                autoComplete={signup ? "new-password" : "current-password"}
                minLength={signup ? 12 : 1}
                maxLength={128}
                placeholder={
                  signup ? "At least 12 characters" : "Enter your password"
                }
                required
              />
            </label>
            <button className="button primary full" disabled={busy}>
              {busy ? "Please wait…" : signup ? "Create account" : "Sign in"}
              <ArrowRight size={17} />
            </button>
          </ValidatedForm>
          {!signup && (
            <p>
              <Link href="/auth/reset/">Forgot your password?</Link>
            </p>
          )}
          <div className="secure-note">
            <ShieldCheck size={15} /> A secure home for your team and
            conversations.
          </div>
        </div>
        <div className="auth-bottom">
          Your next great customer relationship starts here.
          {branding?.support_email && (
            <span>
              {" "}
              Need help?{" "}
              <a href={`mailto:${branding.support_email}`}>
                {branding.support_email}
              </a>
            </span>
          )}
        </div>
      </section>
    </main>
  );
}
