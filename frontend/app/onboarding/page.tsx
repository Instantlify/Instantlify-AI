"use client";

/**
 * The five-step signup wizard: connect-instagram → workspace → team → integrations
 * → payment.
 *
 * Two things here are deliberate rather than incidental:
 *
 * 1. Every step transition reports itself to the funnel the console reads, from the
 *    same STEPS list the backend validates against — so the wizard and its funnel
 *    can never quietly drift apart.
 * 2. Progress is resumed from the server, not from local state. A wizard that
 *    restarts at step one whenever someone closes the tab reports worse funnel
 *    numbers than the product actually deserves.
 */

import { useRouter } from "next/navigation";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";
import {
  ArrowRight,
  Check,
  CreditCard,
  Instagram,
  Plug,
  ShieldCheck,
  Users,
} from "lucide-react";
import {
  api,
  ApiError,
  message,
  type PlanCard,
  type Workspace,
} from "@/lib/api";
import { startCheckout } from "@/lib/billing";
import { PlanCards, type Interval } from "@/components/plans";
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
        if (progress.finished) {
          router.replace(`/w/${current.id}/overview`);
          return;
        }
        setStep(progress.step ?? STEPS[0]);
      } catch (err) {
        if (!controller.signal.aborted) setError(message(err));
      }
    })();
    return () => controller.abort();
  }, [router]);

  useEffect(() => {
    if (step) track(step, "reached");
  }, [step, track]);

  function advance(from: Step, status: "completed" | "skipped") {
    track(from, status);
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

  const index = STEPS.indexOf(step);
  return (
    <div className="setup-screen">
      <Brand />
      <section className="setup-card wizard">
        <ol className="wizard-rail" aria-label="Setup progress">
          {STEPS.map((name, position) => (
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
            onDone={(saved) => {
              setWorkspace(saved);
              advance("workspace", "completed");
            }}
          />
        )}
        {step === "team" && (
          <TeamStep
            workspaceId={workspace.id}
            busy={busy}
            setBusy={setBusy}
            setError={setError}
            onDone={() => advance("team", "completed")}
            onSkip={() => advance("team", "skipped")}
          />
        )}
        {step === "integrations" && (
          <IntegrationsStep
            workspaceId={workspace.id}
            onSkip={() => advance("integrations", "skipped")}
          />
        )}
        {step === "payment" && (
          <PaymentStep
            workspaceId={workspace.id}
            busy={busy}
            setBusy={setBusy}
            setError={setError}
            onSkip={() => advance("payment", "skipped")}
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
      const started = await api<{ url?: string; connected?: boolean }>(
        `/api/workspaces/${workspaceId}/meta/connect/`,
        "POST",
      );
      if (started.url) {
        window.location.href = started.url;
        return;
      }
      onDone();
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
          <Instagram size={24} />
        </span>
        <h1>{TITLES["connect-instagram"]}</h1>
        <p>
          Connect an Instagram business account so your automations have
          something to listen to.
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
        <h2>One click and you&rsquo;re listening</h2>
        <button className="button primary" onClick={connect} disabled={busy}>
          {busy ? "Opening Instagram…" : "Add Instagram account"}
          <ArrowRight size={15} />
        </button>
        <p className="wizard-trust">
          <ShieldCheck size={14} /> Your tokens are encrypted at rest and never
          shown again after connecting.
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
  onDone: (saved: Workspace) => void;
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
      onDone(saved);
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
        This is where your team, connected accounts and conversations live. You
        can rename it at any time.
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
          {busy ? "Saving…" : "Continue"}
          <ArrowRight size={15} />
        </button>
      </form>
    </>
  );
}

function TeamStep({
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
  const [invited, setInvited] = useState<string[]>([]);

  async function invite(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const email = String(new FormData(form).get("email") ?? "");
    setBusy(true);
    setError("");
    try {
      await api(`/api/workspaces/${workspaceId}/invitations/`, "POST", {
        email,
        role: "agent",
      });
      setInvited((current) => [...current, email]);
      form.reset();
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <span className="section-icon">
        <Users size={24} />
      </span>
      <h1>{TITLES.team}</h1>
      <p>
        Teammates share this workspace&rsquo;s subscription and connected
        accounts. Most people skip this and come back later.
      </p>
      <form onSubmit={invite}>
        <label>
          Teammate email
          <input name="email" type="email" placeholder="teammate@company.com" />
        </label>
        <button className="button" disabled={busy}>
          {busy ? "Sending…" : "Send invite"}
        </button>
      </form>
      {invited.length > 0 && (
        <ul className="wizard-invited">
          {invited.map((email) => (
            <li key={email}>
              <Check size={13} /> {email}
            </li>
          ))}
        </ul>
      )}
      <div className="wizard-footer">
        <button className="button link" onClick={onSkip} disabled={busy}>
          Skip for now
        </button>
        <button className="button primary" onClick={onDone} disabled={busy}>
          Continue
          <ArrowRight size={15} />
        </button>
      </div>
    </>
  );
}

function IntegrationsStep({
  workspaceId,
  onSkip,
}: {
  workspaceId: string;
  onSkip: () => void;
}) {
  return (
    <>
      <span className="section-icon">
        <Plug size={24} />
      </span>
      <h1>{TITLES.integrations}</h1>
      <p>
        Calendars, CRMs and Slack let your automations book calls and record
        what happened. You can add these whenever you need them.
      </p>
      <div className="wizard-footer">
        <button className="button link" onClick={onSkip}>
          Skip for now
        </button>
        <a
          className="button primary"
          href={`/w/${workspaceId}/integrations`}
          onClick={onSkip}
        >
          Browse integrations
          <ArrowRight size={15} />
        </a>
      </div>
    </>
  );
}

function PaymentStep({
  workspaceId,
  busy,
  setBusy,
  setError,
  onSkip,
}: StepProps & { workspaceId: string; onSkip: () => void }) {
  const [plans, setPlans] = useState<PlanCard[]>([]);
  const [interval, setInterval] = useState<Interval>("monthly");
  const [chosen, setChosen] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    api<{ plans: PlanCard[] }>(
      "/api/public/plans/",
      "GET",
      undefined,
      controller.signal,
    )
      .then((body) => setPlans(body.plans))
      .catch(() => undefined);
    return () => controller.abort();
  }, []);

  async function choose(slug: string, chosenInterval: Interval) {
    setBusy(true);
    setChosen(slug);
    setError("");
    try {
      const url = await startCheckout(`/api/workspaces/${workspaceId}`, {
        kind: "checkout",
        plan: slug,
        interval: chosenInterval,
      });
      window.location.href = url;
    } catch (err) {
      setError(message(err));
      setBusy(false);
      setChosen("");
    }
  }

  return (
    <>
      <span className="section-icon">
        <CreditCard size={24} />
      </span>
      <h1>{TITLES.payment}</h1>
      <p>Every plan starts with a 7-day free trial. Cancel any time.</p>
      <PlanCards
        plans={plans}
        interval={interval}
        onInterval={setInterval}
        onChoose={choose}
        busySlug={chosen}
        cta="Start free trial"
        trialDays={7}
      />
      <div className="wizard-footer">
        <button className="button link" onClick={onSkip} disabled={busy}>
          I&rsquo;ll decide later
        </button>
      </div>
    </>
  );
}
