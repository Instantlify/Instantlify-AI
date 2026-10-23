"use client";

/** Short setup: connect an account, name the workspace, choose a plan. Team and
 * integrations remain available in the workspace. */

import { useRouter } from "next/navigation";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";
import { ArrowRight, Check, Crown, ShieldCheck } from "lucide-react";
import { BrandIcon } from "@/lib/brand-icons";
import {
  api,
  ApiError,
  message,
  type Billing,
  type Workspace,
} from "@/lib/api";
import { startCheckout } from "@/lib/billing";
import { FEATURE_ROWS, PlanCards, type Interval } from "@/components/plans";
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

/** Steps shown on the rail; team and integrations are recorded as skipped. */
const VISIBLE_STEPS: Step[] = ["connect-instagram", "workspace", "payment"];

const recordStep = (
  step: Step,
  status: "completed" | "skipped",
  workspaceId: string,
) =>
  api("/api/growth/funnel/", "POST", {
    flow: "wizard",
    step,
    status,
    workspace_id: workspaceId,
  });

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
        // Back from Stripe: a paid plan is chosen, so the wizard is done.
        const billing = new URLSearchParams(window.location.search).get(
          "billing",
        );
        if (billing === "success") {
          await recordStep("payment", "completed", current.id);
          router.replace(`/w/${current.id}/overview`);
          return;
        }
        if (billing === "cancelled")
          setError(
            "Checkout was cancelled. Choose a plan to finish setting up.",
          );
        setStep(
          connection === "connected" || connection === "test-connected"
            ? "workspace"
            : progress.step === "connect-instagram" ||
                progress.step === "workspace"
              ? progress.step
              : "payment",
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
        // Persist before moving on; team and integrations wait for the workspace.
        await recordStep("workspace", "completed", workspace.id);
        await Promise.all([
          recordStep("team", "skipped", workspace.id),
          recordStep("integrations", "skipped", workspace.id),
        ]);
        setStep("payment");
      } catch (err) {
        setError(message(err));
      } finally {
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

  const visibleSteps = VISIBLE_STEPS;
  const index = visibleSteps.indexOf(step);
  return (
    <div className="setup-screen">
      <Brand />
      <section
        className={`setup-card wizard${step === "payment" ? " wizard-wide" : ""}`}
      >
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
        {step === "payment" && (
          <PlanStep
            workspaceId={workspace.id}
            busy={busy}
            setBusy={setBusy}
            setError={setError}
            onFree={async () => {
              await recordStep("payment", "completed", workspace.id);
              router.replace(`/w/${workspace.id}/overview`);
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
        Name your business. Next you&rsquo;ll choose a plan; team invitations
        and integrations can wait until you need them.
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
          {busy ? "Saving…" : "Continue to plans"}
          <ArrowRight size={15} />
        </button>
      </form>
    </>
  );
}

/** Everyone leaves the wizard on a plan: Free continues straight in, a paid plan
 * goes through Stripe Checkout and comes back here to finish. */
function PlanStep({
  workspaceId,
  busy,
  setBusy,
  setError,
  onFree,
}: StepProps & {
  workspaceId: string;
  onFree: () => Promise<void>;
}) {
  const [billing, setBilling] = useState<Billing | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [pending, setPending] = useState("");
  const [preferred, setPreferred] = useState("");
  const [interval, setInterval] = useState<Interval>("monthly");

  useEffect(() => {
    const controller = new AbortController();
    const query = new URLSearchParams(window.location.search);
    api<Billing>(
      `/api/workspaces/${workspaceId}/billing/`,
      "GET",
      undefined,
      controller.signal,
    )
      .then((data) => {
        setBilling(data);
        setPreferred(query.get("plan") || "");
        if (query.get("interval") === "annual") setInterval("annual");
      })
      .catch((err) => {
        if (!controller.signal.aborted) setError(message(err));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoaded(true);
      });
    return () => controller.abort();
  }, [workspaceId, setError]);

  async function chooseFree() {
    setBusy(true);
    setError("");
    try {
      await onFree();
    } catch (err) {
      setError(message(err));
      setBusy(false);
    }
  }

  async function choosePaid(slug: string, chosen: Interval) {
    setBusy(true);
    setPending(slug);
    setError("");
    try {
      window.location.assign(
        await startCheckout(`/api/workspaces/${workspaceId}`, {
          kind: "checkout",
          plan: slug,
          interval: chosen,
          return_to: "onboarding",
        }),
      );
    } catch (err) {
      setError(message(err));
      setBusy(false);
      setPending("");
    }
  }

  const catalog = billing?.catalog ?? [];
  const free = catalog.find((plan) => plan.slug === "free");
  const paid = catalog.filter((plan) => plan.slug !== "free");
  const preferredName = paid.find((plan) => plan.slug === preferred)?.name;
  const freeSummary = free
    ? FEATURE_ROWS.filter(
        (row) => row.kind === "count" && free.limits[row.key] !== null,
      )
        .map(
          (row) =>
            `${(free.limits[row.key] as number).toLocaleString()} ${row.label.toLowerCase()}`,
        )
        .join(" · ")
    : "Start free and upgrade when you need more.";

  return (
    <>
      <span className="section-icon">
        <Crown size={24} />
      </span>
      <h1>{TITLES.payment}</h1>
      <p>
        Pick the plan this workspace starts on. Paid plans check out securely
        with Stripe, and you can change plans any time in Settings.
      </p>
      {!loaded ? (
        <p className="muted-text">Loading plans…</p>
      ) : (
        <div className="onboarding-plans">
          {preferredName && (
            <p className="onboarding-plan-hint">
              You picked <strong>{preferredName}</strong> on the pricing page.
            </p>
          )}
          {(free || !billing) && (
            <div className="onboarding-free-plan">
              <div>
                <strong>{free?.name || "Free"}</strong>
                <span>{freeSummary}</span>
              </div>
              <button
                type="button"
                className="button secondary"
                disabled={busy}
                onClick={chooseFree}
              >
                {busy && !pending ? "Opening…" : "Continue with Free"}
              </button>
            </div>
          )}
          {billing && paid.length > 0 && billing.stripe_configured && (
            <PlanCards
              plans={paid}
              interval={interval}
              onInterval={setInterval}
              busySlug={pending}
              trialDays={billing.trial_days}
              onChoose={choosePaid}
            />
          )}
          {billing && paid.length > 0 && !billing.stripe_configured && (
            <p className="muted-text">
              Paid plans open once Stripe is configured for this deployment.
            </p>
          )}
          {billing && !free && !billing.stripe_configured && (
            <button
              type="button"
              className="button primary"
              disabled={busy}
              onClick={chooseFree}
            >
              Continue
              <ArrowRight size={15} />
            </button>
          )}
        </div>
      )}
    </>
  );
}
