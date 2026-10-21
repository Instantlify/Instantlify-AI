"use client";

/** Short setup; team, integrations and billing remain available in the workspace. */

import { useRouter } from "next/navigation";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";
import { ArrowRight, Check, ShieldCheck } from "lucide-react";
import { BrandIcon } from "@/lib/brand-icons";
import { api, ApiError, message, type Workspace } from "@/lib/api";
import { Brand } from "@/components/shell";
import { ErrorNotice } from "@/components/ui";

const STEPS = [
  "connect-instagram",
  "workspace",
  "team",
  "integrations",
  "payment",
] as const;
type Step = (typeof STEPS)[number];

const TITLES: Record<Step, string> = {
  "connect-instagram": "Connect your Instagram",
  workspace: "Name your workspace",
  team: "Invite your team",
  integrations: "Connect an integration",
  payment: "Choose a plan",
};

type Progress = { step: Step | null; completed: string[]; finished: boolean };

export default function Onboarding() {
  const router = useRouter();
  const [step, setStep] = useState<Step | null>(null);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const reported = useRef<Set<string>>(new Set());

  /** Fire-and-forget: tracking must never block or fail a step. */
  const track = useCallback(
    (name: Step, status: "reached" | "completed" | "skipped", id?: string) => {
      const key = `${name}:${status}`;
      if (status === "reached" && reported.current.has(key)) return;
      reported.current.add(key);
      api("/api/growth/funnel/", "POST", {
        flow: "wizard",
        step: name,
        status,
        workspace_id: id ?? workspace?.id,
      }).catch(() => undefined);
    },
    [workspace],
  );

  // Resume where they left off, and make sure a workspace exists: step one connects
  // an account, which needs somewhere to attach it. Step two renames it.
  useEffect(() => {
    const controller = new AbortController();
    (async () => {
      try {
        const [progress, spaces] = await Promise.all([
          api<Progress>(
            "/api/growth/wizard/",
            "GET",
            undefined,
            controller.signal,
          ),
          api<{ results: Workspace[] }>(
            "/api/workspaces/",
            "GET",
            undefined,
            controller.signal,
          ),
        ]);
        let current = spaces.results[0] ?? null;
        if (!current) {
          current = await api<Workspace>("/api/workspaces/", "POST", {
            name: "My workspace",
          });
        }
        setWorkspace(current);
        const connection = new URLSearchParams(window.location.search).get(
          "connection",
        );
        if (connection === "cancelled")
          setError(
            "Instagram connection was cancelled. Try again or connect later.",
          );
        if (connection === "limit")
          setError(
            "Your plan's connected-account limit has been reached. You can connect later.",
          );
        if (progress.finished) {
          router.replace(`/w/${current.id}/overview`);
          return;
        }
        setStep(
          connection === "connected" || connection === "test-connected"
            ? "workspace"
            : progress.step === "connect-instagram"
              ? "connect-instagram"
              : "workspace",
        );
      } catch (err) {
        if (!controller.signal.aborted) setError(message(err));
      }
    })();
    return () => controller.abort();
  }, [router]);

  useEffect(() => {
    if (step) track(step, "reached");
  }, [step, track]);

  async function advance(from: Step, status: "completed" | "skipped") {
    setBusy(false);
    setError("");
    if (from !== "workspace") track(from, status);
    if (from === "workspace" && workspace) {
      setBusy(true);
      try {
        // Persist completion before navigating; retain legacy funnel compatibility.
        for (const name of [
          "workspace",
          "team",
          "integrations",
          "payment",
        ] as const) {
          await api("/api/growth/funnel/", "POST", {
            flow: "wizard",
            step: name,
            status: name === "workspace" ? "completed" : "skipped",
            workspace_id: workspace.id,
          });
        }
        const query = new URLSearchParams(window.location.search);
        const plan = query.get("plan");
        router.replace(
          plan
            ? `/w/${workspace.id}/payments?plan=${encodeURIComponent(plan)}&interval=${query.get("interval") === "annual" ? "annual" : "monthly"}`
            : `/w/${workspace.id}/overview`,
        );
      } catch (err) {
        setError(message(err));
        setBusy(false);
      }
      return;
    }
    const next = STEPS[STEPS.indexOf(from) + 1];
    if (next) {
      setStep(next);
      return;
    }
    if (workspace) router.replace(`/w/${workspace.id}/overview`);
  }

  if (error && !step)
    return (
      <div className="setup-screen">
        <Brand />
        <section className="setup-card">
          <ErrorNotice error={error} />
        </section>
      </div>
    );
  if (!step || !workspace)
    return (
      <div className="loading-screen">
        <Brand />
        <p>Setting things up…</p>
      </div>
    );

  const visibleSteps = STEPS.slice(0, 2);
  const index = visibleSteps.indexOf(step);
  return (
    <div className="setup-screen">
      <Brand />
      <section className="setup-card wizard">
        <ol className="wizard-rail" aria-label="Setup progress">
          {visibleSteps.map((name, position) => (
            <li
              key={name}
              className={
                position < index ? "done" : position === index ? "current" : ""
              }
            >
              <span className="dot">
                {position < index ? <Check size={11} /> : position + 1}
              </span>
              <span className="label">{TITLES[name]}</span>
            </li>
          ))}
        </ol>

        <ErrorNotice error={error} />

        {step === "connect-instagram" && (
          <ConnectStep
            workspaceId={workspace.id}
            busy={busy}
            setBusy={setBusy}
            setError={setError}
            onDone={() => advance("connect-instagram", "completed")}
            onSkip={() => advance("connect-instagram", "skipped")}
          />
        )}
        {step === "workspace" && (
          <WorkspaceStep
            workspace={workspace}
            busy={busy}
            setBusy={setBusy}
            setError={setError}
            onDone={async (saved) => {
              setWorkspace(saved);
              await advance("workspace", "completed");
            }}
          />
        )}
      </section>
    </div>
  );
}

type StepProps = {
  busy: boolean;
  setBusy: (value: boolean) => void;
  setError: (value: string) => void;
};

function ConnectStep({
  workspaceId,
  busy,
  setBusy,
  setError,
  onDone,
  onSkip,
}: StepProps & {
  workspaceId: string;
  onDone: () => void;
  onSkip: () => void;
}) {
  async function connect() {
    setBusy(true);
    setError("");
    try {
      const query = new URLSearchParams(window.location.search);
      const started = await api<{
        authorization_url?: string;
        connected?: boolean;
      }>(`/api/workspaces/${workspaceId}/meta/connect/`, "POST", {
        onboarding: true,
        plan: query.get("plan") || "",
        interval: query.get("interval") || "monthly",
      });
      if (started.authorization_url) {
        window.location.assign(started.authorization_url);
        return;
      }
      if (started.connected === true) {
        onDone();
        return;
      }
      throw new Error(
        "Instagram did not provide a connection link. Please try again or connect later.",
      );
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 503
          ? "Instagram connection is not configured on this deployment yet. You can skip this and connect later."
          : message(err),
      );
      setBusy(false);
    }
  }

  return (
    <div className="wizard-split">
      <div>
        <span className="section-icon">
          <BrandIcon name="instagram" size={24} />
        </span>
        <h1>{TITLES["connect-instagram"]}</h1>
        <p>
          Connect an Instagram business account so your automations have a
          channel for customer enquiries. You can also connect later and explore
          first.
        </p>
        <ol className="wizard-steps">
          <li>
            <span>1</span>
            <p>
              Make sure you are logged in on this device with the account you
              want to connect.
            </p>
          </li>
          <li>
            <span>2</span>
            <p>
              The account needs to be a Creator or Business account. A personal
              account can be switched over in Instagram&rsquo;s settings.
            </p>
          </li>
          <li>
            <span>3</span>
            <p>
              On a phone, the connection may hand off to the Instagram app. If
              that happens, come back and finish on a computer.
            </p>
          </li>
        </ol>
      </div>
      <div className="wizard-action">
        <h2>Connect when you&rsquo;re ready</h2>
        <button className="button primary" onClick={connect} disabled={busy}>
          {busy ? "Opening Instagram…" : "Add Instagram account"}
          <ArrowRight size={15} />
        </button>
        <p className="wizard-trust">
          <ShieldCheck size={14} /> You stay in control of your connected
          account and can disconnect it later.
        </p>
        <button className="button link" onClick={onSkip} disabled={busy}>
          I&rsquo;ll connect my account later
        </button>
      </div>
    </div>
  );
}

function WorkspaceStep({
  workspace,
  busy,
  setBusy,
  setError,
  onDone,
}: StepProps & {
  workspace: Workspace;
  onDone: (saved: Workspace) => Promise<void>;
}) {
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const name = String(new FormData(event.currentTarget).get("name") ?? "");
      const saved = await api<Workspace>(
        `/api/workspaces/${workspace.id}/`,
        "PATCH",
        { name },
      );
      await onDone(saved);
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <span className="section-icon">
        <Check size={24} />
      </span>
      <h1>{TITLES.workspace}</h1>
      <p>
        Name your business, then choose a starter workflow or test your AI
        assistant. Team invitations, integrations and plans can wait until you
        need them.
      </p>
      <form onSubmit={save}>
        <label>
          Workspace name
          <input
            name="name"
            defaultValue={workspace.name}
            placeholder="e.g. Acme Studio"
            maxLength={100}
            required
            autoFocus
          />
        </label>
        <button className="button primary" disabled={busy}>
          {busy ? "Saving…" : "Open my workspace"}
          <ArrowRight size={15} />
        </button>
      </form>
    </>
  );
}
