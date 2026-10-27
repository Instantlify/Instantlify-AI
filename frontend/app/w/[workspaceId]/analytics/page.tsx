"use client";

import {
  ValidatedForm,
  ValidatedInput,
  ValidatedSelect,
} from "@/components/validated-form";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  FlaskConical,
  Trophy,
  Users,
  CalendarCheck,
  CreditCard,
  Coins,
} from "lucide-react";
import {
  api,
  message,
  money,
  when,
  type Automation,
  type Experiment,
  type Funnel,
  type Page,
} from "@/lib/api";
import { useWorkspace } from "@/lib/workspace";
import {
  Empty,
  ErrorNotice,
  PageHeading,
  Panel,
  Pill,
  Stat,
  statusTone,
  SuccessNotice,
  Table,
  useFeedback,
} from "@/components/ui";

const STEP_LABELS: Record<string, string> = {
  comment: "Comments",
  dm: "Direct messages",
  triggered: "Automation fired",
  replied: "Replied",
  booked: "Call booked",
  paid: "Paid",
};
const PROVIDERS = ["instagram", "whatsapp", "messenger", "telegram"];
const percent = (value: number) => `${Math.round(value * 100)}%`;

export default function AnalyticsPage() {
  const { prefix, manager } = useWorkspace();
  const [period, setPeriod] = useState("30d");
  // "View analytics" on an automation links here with ?automation=<id>. The workspace
  // layout renders pages only in the browser, so the URL is readable on first render.
  const [automation, setAutomation] = useState(() =>
    typeof window === "undefined"
      ? ""
      : new URLSearchParams(window.location.search).get("automation") || "",
  );
  const [provider, setProvider] = useState("");
  const [automations, setAutomations] = useState<Automation[]>([]);
  const [funnel, setFunnel] = useState<Funnel | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!manager) return;
    const controller = new AbortController();
    api<Page<Automation>>(
      `${prefix}/automations/`,
      "GET",
      undefined,
      controller.signal,
    )
      .then((page) => setAutomations(page.results))
      .catch((err) => {
        if (!controller.signal.aborted) setError(message(err));
      });
    return () => controller.abort();
  }, [prefix, manager]);

  useEffect(() => {
    if (!manager) return;
    const controller = new AbortController();
    const params = new URLSearchParams({ period });
    if (automation) params.set("automation", automation);
    if (provider) params.set("provider", provider);
    api<Funnel>(
      `${prefix}/analytics/funnel/?${params.toString()}`,
      "GET",
      undefined,
      controller.signal,
    )
      .then((data) => {
        if (!controller.signal.aborted) {
          setFunnel(data);
          setError("");
        }
      })
      .catch((err) => {
        if (!controller.signal.aborted) setError(message(err));
      });
    return () => controller.abort();
  }, [prefix, manager, period, automation, provider]);

  if (!manager)
    return (
      <>
        <PageHeading
          eyebrow="Analytics"
          title="Every conversation, measured."
        />
        <Panel>
          <Empty>Analytics are visible to workspace owners and admins.</Empty>
        </Panel>
      </>
    );

  const step = (kind: string) => funnel?.steps.find((s) => s.kind === kind);
  const leads = funnel?.unique_leads ?? 0;
  const maxLeads = Math.max(1, ...(funnel?.steps.map((s) => s.leads) ?? [1]));

  return (
    <>
      <PageHeading
        eyebrow="Analytics"
        title="Every conversation, measured."
        text="Comment → DM → booked → paid, per automation and per channel. Counts are distinct leads."
      />
      <ErrorNotice error={error} />
      <div className="toolbar">
        <ValidatedSelect
          aria-label="Period"
          value={period}
          onChange={(e) => setPeriod(e.target.value)}
        >
          <option value="7d">Last 7 days</option>
          <option value="30d">Last 30 days</option>
          <option value="90d">Last 90 days</option>
        </ValidatedSelect>
        <ValidatedSelect
          aria-label="Automation"
          value={automation}
          onChange={(e) => setAutomation(e.target.value)}
        >
          <option value="">All automations</option>
          {automations.map((item) => (
            <option key={item.id} value={item.id}>
              {item.name}
            </option>
          ))}
        </ValidatedSelect>
        <ValidatedSelect
          aria-label="Channel"
          value={provider}
          onChange={(e) => setProvider(e.target.value)}
        >
          <option value="">All channels</option>
          {PROVIDERS.map((item) => (
            <option key={item} value={item}>
              {item}
            </option>
          ))}
        </ValidatedSelect>
      </div>
      {!funnel ? (
        <p className="loading-text">Loading analytics…</p>
      ) : (
        <div className="stack">
          <div className="stats-grid">
            <Stat
              icon={<Users size={19} />}
              value={String(leads)}
              label="Leads"
              detail="Unique people across comments and DMs"
            />
            <Stat
              icon={<CalendarCheck size={19} />}
              value={String(step("booked")?.leads ?? 0)}
              label="Calls booked"
              detail={
                step("booked")?.conversion == null
                  ? "No earlier replied leads in this period"
                  : `${percent(step("booked")!.conversion!)} of replied leads later booked`
              }
            />
            <Stat
              icon={<CreditCard size={19} />}
              value={String(step("paid")?.leads ?? 0)}
              label="Paid"
              detail={
                step("paid")?.conversion == null
                  ? "No earlier booked leads in this period"
                  : `${percent(step("paid")!.conversion!)} of booked leads later paid`
              }
            />
            <Stat
              icon={<Coins size={19} />}
              value={money(funnel.revenue_cents)}
              label="Revenue"
              detail={`Since ${when(funnel.since)}`}
            />
          </div>
          <Panel title="Funnel" aside={`Period: ${funnel.period}`}>
            <p className="panel-subtitle">
              Counts show unique people at each stage. Percentages track people
              who reached the preceding stage first, within this period.
              Comments and DMs are separate entry points.
            </p>
            <div className="funnel">
              {funnel.steps.map((item) => (
                <div className="funnel-step" key={item.kind}>
                  <span>{STEP_LABELS[item.kind] || item.kind}</span>
                  <div className="funnel-bar" aria-hidden="true">
                    <i style={{ width: `${(item.leads / maxLeads) * 100}%` }} />
                  </div>
                  <strong>
                    {item.leads}
                    <span className="muted-text">
                      {" "}
                      {item.conversion == null
                        ? ""
                        : `· ${percent(item.conversion)}`}
                    </span>
                  </strong>
                </div>
              ))}
            </div>
          </Panel>
          <div className="two-col">
            <Panel title="By automation">
              {funnel.automations.length === 0 ? (
                <Empty>No automation activity in this period.</Empty>
              ) : (
                <Table
                  head={["Automation", "Fired", "Booked", "Paid", "Revenue"]}
                >
                  {funnel.automations.map((row) => (
                    <tr key={row.automation_id}>
                      <td>{row.name}</td>
                      <td>{row.triggered}</td>
                      <td>{row.booked}</td>
                      <td>{row.paid}</td>
                      <td>{money(row.revenue_cents)}</td>
                    </tr>
                  ))}
                </Table>
              )}
            </Panel>
            <Panel title="By channel">
              {funnel.channels.length === 0 ? (
                <Empty>No channel activity in this period.</Empty>
              ) : (
                <Table head={["Channel", "Leads", "Booked", "Paid"]}>
                  {funnel.channels.map((row) => (
                    <tr key={row.provider}>
                      <td>{row.provider}</td>
                      <td>{row.leads}</td>
                      <td>{row.booked}</td>
                      <td>{row.paid}</td>
                    </tr>
                  ))}
                </Table>
              )}
            </Panel>
          </div>
          <Experiments automations={automations} />
        </div>
      )}
    </>
  );
}

function Experiments({ automations }: { automations: Automation[] }) {
  const { prefix } = useWorkspace();
  const [experiments, setExperiments] = useState<Experiment[]>([]);
  const [form, setForm] = useState({
    name: "",
    control: "",
    variant: "",
    split: 50,
    goal: "booked",
    auto_promote: false,
    min_leads: 100,
  });
  const feedback = useFeedback();
  const published = automations.filter(
    (item) => item.published && Object.keys(item.published).length > 0,
  );
  const nameOf = (id: string) =>
    automations.find((item) => item.id === id)?.name || "Deleted";

  const load = useCallback(
    async (signal?: AbortSignal) => {
      const page = await api<Page<Experiment>>(
        `${prefix}/experiments/`,
        "GET",
        undefined,
        signal,
      );
      setExperiments(page.results);
    },
    [prefix],
  );

  useEffect(() => {
    const controller = new AbortController();
    api<Page<Experiment>>(
      `${prefix}/experiments/`,
      "GET",
      undefined,
      controller.signal,
    )
      .then((page) => setExperiments(page.results))
      .catch((err) => {
        if (!controller.signal.aborted) feedback.setError(message(err));
      });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefix]);

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await feedback.run(async () => {
      await api(`${prefix}/experiments/`, "POST", {
        ...form,
        split: Number(form.split),
        min_leads: Number(form.min_leads),
      });
      setForm((current) => ({
        ...current,
        name: "",
        control: "",
        variant: "",
      }));
      await load();
    }, "Experiment started.");
  }

  async function promote(
    experiment: Experiment,
    winner: "control" | "variant",
  ) {
    const label =
      winner === "variant"
        ? nameOf(experiment.variant)
        : nameOf(experiment.control);
    if (
      !window.confirm(
        `Promote “${label}” as the winner? ${
          winner === "variant"
            ? "Its flow will be republished under the control automation."
            : "The variant will be disabled."
        }`,
      )
    )
      return;
    await feedback.run(async () => {
      await api(`${prefix}/experiments/${experiment.id}/promote/`, "POST", {
        winner,
      });
      await load();
    }, "Experiment concluded.");
  }

  return (
    <Panel title="A/B experiments" aside={`${experiments.length} total`}>
      <ErrorNotice error={feedback.error} />
      <SuccessNotice notice={feedback.notice} />
      <p className="muted-text" style={{ marginBottom: 14 }}>
        Leads matching the control’s triggers are split deterministically
        between two flows — the same lead always sees the same variant. When the
        variant wins, it is republished under the control automation so links
        and reports keep working.
      </p>
      <div className="card-grid" style={{ marginBottom: 20 }}>
        {experiments.length === 0 ? (
          <Empty>No experiments yet.</Empty>
        ) : (
          experiments.map((experiment) => (
            <article className="card" key={experiment.id}>
              <div className="row between">
                <h3>
                  <FlaskConical size={14} /> {experiment.name}
                </h3>
                <Pill tone={statusTone(experiment.status)}>
                  {experiment.status}
                </Pill>
              </div>
              <span className="muted-text">
                {nameOf(experiment.control)} vs {nameOf(experiment.variant)} ·{" "}
                {100 - experiment.split}/{experiment.split} split · goal:{" "}
                {experiment.goal}
                {experiment.auto_promote
                  ? ` · auto-promote at ${experiment.min_leads} leads`
                  : ""}
              </span>
              {(["control", "variant"] as const).map((arm) => (
                <div className="list-row" key={arm}>
                  <strong>
                    {arm === "control" ? "Control" : "Variant"}
                    {experiment.winner === arm && (
                      <>
                        {" "}
                        <Trophy size={13} />
                      </>
                    )}
                  </strong>
                  <span className="muted-text">
                    {experiment.results[arm].leads} leads ·{" "}
                    {experiment.results[arm].conversions} conversions ·{" "}
                    {percent(experiment.results[arm].rate)}
                  </span>
                  <span className="spacer" />
                  {experiment.status === "running" && (
                    <button
                      className="text-button"
                      disabled={feedback.busy}
                      onClick={() => promote(experiment, arm)}
                    >
                      Promote {arm}
                    </button>
                  )}
                </div>
              ))}
              {experiment.concluded_at && (
                <span className="muted-text">
                  Concluded {when(experiment.concluded_at)}
                </span>
              )}
            </article>
          ))
        )}
      </div>
      <h3 className="small" style={{ marginBottom: 10 }}>
        Start an experiment
      </h3>
      <ValidatedForm fieldErrors={feedback.fieldErrors} validationTarget={feedback.validationTarget} onEdit={() => feedback.setError("")} className="form-grid" onSubmit={create}>
        <div className="three-col">
          <label>
            Name
            <ValidatedInput name="name"
              value={form.name}
              maxLength={100}
              required
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </label>
          <label>
            Control (published)
            <ValidatedSelect name="control"
              value={form.control}
              required
              onChange={(e) => setForm({ ...form, control: e.target.value })}
            >
              <option value="">Choose…</option>
              {published.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </ValidatedSelect>
          </label>
          <label>
            Variant (published)
            <ValidatedSelect name="variant"
              value={form.variant}
              required
              onChange={(e) => setForm({ ...form, variant: e.target.value })}
            >
              <option value="">Choose…</option>
              {published
                .filter((item) => item.id !== form.control)
                .map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
            </ValidatedSelect>
          </label>
        </div>
        <div className="three-col">
          <label>
            Variant share (%)
            <ValidatedInput name="split"
              type="number"
              min={1}
              max={99}
              value={form.split}
              onChange={(e) =>
                setForm({ ...form, split: Number(e.target.value) })
              }
            />
          </label>
          <label>
            Goal
            <ValidatedSelect name="goal"
              value={form.goal}
              onChange={(e) => setForm({ ...form, goal: e.target.value })}
            >
              <option value="replied">Replied</option>
              <option value="booked">Booked</option>
              <option value="paid">Paid</option>
            </ValidatedSelect>
          </label>
          <label>
            Minimum leads per arm
            <ValidatedInput name="min_leads"
              type="number"
              min={1}
              value={form.min_leads}
              onChange={(e) =>
                setForm({ ...form, min_leads: Number(e.target.value) })
              }
            />
          </label>
        </div>
        <label className="inline">
          <ValidatedInput
            type="checkbox"
            checked={form.auto_promote}
            onChange={(e) =>
              setForm({ ...form, auto_promote: e.target.checked })
            }
          />
          Automatically promote the better arm once both reach the minimum
        </label>
        <div className="form-actions">
          <button
            className="button primary small"
            disabled={feedback.busy || published.length < 2}
          >
            {feedback.busy ? "Starting…" : "Start experiment"}
            <FlaskConical size={14} />
          </button>
          {published.length < 2 && (
            <span className="muted-text">
              Publish at least two automations first.
            </span>
          )}
        </div>
      </ValidatedForm>
    </Panel>
  );
}
