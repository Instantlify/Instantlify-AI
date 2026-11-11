"use client";

import { useConfirmation } from "@/components/confirmation-provider";

import {
  ValidatedForm,
  ValidatedInput,
  ValidatedSelect,
  ValidatedTextarea,
} from "@/components/validated-form";
import { AgentPreview } from "@/components/agent-preview";

import Link from "next/link";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";
import { FileText, RefreshCw, Sparkles, Trash2, Upload } from "lucide-react";
import {
  AGENT_TOOLS,
  api,
  message,
  upload,
  when,
  type AgentAudit,
  type AgentConfig,
  type KnowledgeBase,
  type KnowledgeDocument,
  type Page,
  type PlatformModel,
} from "@/lib/api";
import { useWorkspace } from "@/lib/workspace";
import { asList } from "@/lib/as-list";
import {
  Empty,
  ErrorNotice,
  PageHeading,
  Panel,
  Pill,
  statusTone,
  SuccessNotice,
  Table,
  useFeedback,
} from "@/components/ui";
import { BrandIcon, type BrandName } from "@/lib/brand-icons";

const TOOL_HELP: Record<string, string> = {
  check_calendar_availability: "Check whether a time is free on your calendar",
  book_call: "Book a call — the customer confirms with a code first",
  update_crm_field: "Record interest, budget, timeline or company on the lead",
  send_voice_note: "Reply with an AI voice note (ElevenLabs)",
  create_payment_link: "Send a checkout link for one of your Offers",
  handoff_to_human: "Hand the conversation to a teammate",
};
const QUALIFYING = ["interest", "budget", "timeline", "company"];

/** Provider logos for the model cards; providers without one show no mark. */
const MODEL_BRANDS: Partial<Record<string, BrandName>> = {
  openai: "openai",
  anthropic: "claude",
  gemini: "gemini",
};

const DEFAULT_PLATFORM_MODELS: PlatformModel[] = [
  {
    id: "gpt-5.4-mini",
    provider: "openai",
    label: "GPT-5.4 Mini",
    badge: "Recommended · Fast",
    description:
      "High accuracy and low latency. Ideal for instant lead qualification, sales objection handling, and customer support.",
    input_rate: "$0.60",
    output_rate: "$2.40",
    rate_summary: "$0.60 in / $2.40 out per 1M tokens",
  },
  {
    id: "claude-sonnet-5",
    provider: "anthropic",
    label: "Claude Sonnet 5",
    badge: "Deep Reasoning",
    description:
      "State-of-the-art conversational nuance, empathetic tone, and complex multi-step reasoning for high-ticket sales.",
    input_rate: "$3.00",
    output_rate: "$15.00",
    rate_summary: "$3.00 in / $15.00 out per 1M tokens",
  },
  {
    id: "gemini-2.5-flash",
    provider: "gemini",
    label: "Gemini 2.5 Flash",
    badge: "Ultra Fast",
    description:
      "Google's high-speed multimodal powerhouse. Instantaneous replies keep customers hooked without lag.",
    input_rate: "$0.30",
    output_rate: "$1.20",
    rate_summary: "$0.30 in / $1.20 out per 1M tokens",
  },
  {
    id: "grok-beta",
    provider: "xai",
    label: "xAI Grok",
    badge: "Direct & Punchy",
    description:
      "Punchy, modern conversational style. Well suited for creator brands, direct response, and dynamic social DMs.",
    input_rate: "$0.80",
    output_rate: "$3.20",
    rate_summary: "$0.80 in / $3.20 out per 1M tokens",
  },
];

type FormState = {
  name: string;
  system_prompt: string;
  provider: string;
  model: string;
  api_key: string;
  embedding_model: string;
  embedding_api_key: string;
  fallback_provider: string;
  fallback_model: string;
  allowed_tools: string[];
  enabled: boolean;
  is_test: boolean;
  qualifying_fields: string[];
  triage_enabled: boolean;
  handoff_keywords: string;
  max_tool_rounds: number;
  reply_delay_seconds: number;
  mode: "agent" | "simple";
  billing_mode: "platform_credits" | "byo_key";
  input_cost_per_million: string;
  output_cost_per_million: string;
};

const DEFAULTS: FormState = {
  name: "Sales assistant",
  system_prompt:
    "Help customers using the supplied knowledge. Never invent prices or availability.",
  provider: "openai",
  model: "gpt-5.4-mini",
  api_key: "",
  embedding_model: "text-embedding-3-small",
  embedding_api_key: "",
  fallback_provider: "",
  fallback_model: "",
  allowed_tools: [],
  enabled: false,
  is_test: false,
  qualifying_fields: [],
  triage_enabled: true,
  handoff_keywords: "",
  max_tool_rounds: 4,
  reply_delay_seconds: 5,
  mode: "agent",
  billing_mode: "platform_credits",
  input_cost_per_million: "0",
  output_cost_per_million: "0",
};

function toForm(config: AgentConfig): FormState {
  return {
    name: config.name,
    system_prompt: config.system_prompt,
    provider: config.provider,
    model: config.model,
    api_key: "",
    embedding_model: config.embedding_model,
    embedding_api_key: "",
    fallback_provider: config.fallback_provider || "",
    fallback_model: config.fallback_model || "",
    allowed_tools: config.allowed_tools,
    enabled: config.enabled,
    is_test: config.is_test,
    qualifying_fields: config.qualifying_fields,
    triage_enabled: config.triage_enabled,
    handoff_keywords: config.handoff_keywords.join(", "),
    max_tool_rounds: config.max_tool_rounds,
    reply_delay_seconds: config.reply_delay_seconds ?? 0,
    mode: config.mode || "agent",
    billing_mode: config.billing_mode || "platform_credits",
    input_cost_per_million: config.input_cost_per_million,
    output_cost_per_million: config.output_cost_per_million,
  };
}

function toggle(list: string[], value: string) {
  return list.includes(value)
    ? list.filter((item) => item !== value)
    : [...list, value];
}

export default function AgentPage() {
  const { workspace, prefix, manager } = useWorkspace();
  const [form, setForm] = useState<FormState>(DEFAULTS);
  const [platformModels, setPlatformModels] = useState<PlatformModel[]>(
    DEFAULT_PLATFORM_MODELS,
  );
  const [configured, setConfigured] = useState(false);
  const [savedConfig, setSavedConfig] = useState<AgentConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const settings = useFeedback();

  useEffect(() => {
    const controller = new AbortController();
    api<AgentConfig | Record<string, never>>(
      `${prefix}/agent/`,
      "GET",
      undefined,
      controller.signal,
    )
      .then((data) => {
        if (controller.signal.aborted) return;
        const config = data as Partial<AgentConfig>;
        if (config.available_models?.length) {
          setPlatformModels(config.available_models);
        }
        if (config.id) {
          setForm(toForm(config as AgentConfig));
          setSavedConfig(config as AgentConfig);
          setConfigured(true);
        }
      })
      .catch((err) => {
        if (!controller.signal.aborted) settings.setError(message(err));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefix]);

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((current) => ({ ...current, [key]: value }));

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await settings.run(async () => {
      const payload: Record<string, unknown> = {
        ...form,
        handoff_keywords: form.handoff_keywords
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean),
        max_tool_rounds: Number(form.max_tool_rounds),
        reply_delay_seconds: Number(form.reply_delay_seconds),
        mode: form.mode,
        billing_mode: form.billing_mode,
        input_cost_per_million: form.input_cost_per_million || "0",
        output_cost_per_million: form.output_cost_per_million || "0",
      };
      if (!form.api_key) delete payload.api_key;
      if (!form.embedding_api_key) delete payload.embedding_api_key;
      const saved = await api<AgentConfig>(`${prefix}/agent/`, "PUT", payload);
      setForm(toForm(saved));
      setSavedConfig(saved);
      setConfigured(true);
    }, "Agent settings saved.");
  }

  return (
    <>
      <PageHeading
        eyebrow="AI agent"
        title="A sales rep that never sleeps."
        text="Grounded in your knowledge, bounded by your rules. You decide which tools it may use."
        action={
          <Pill tone={form.enabled ? "good" : "neutral"}>
            {form.enabled ? "Enabled" : "Off"}
          </Pill>
        }
      />
      <ErrorNotice error={settings.error} />
      <SuccessNotice notice={settings.notice} />
      {loading ? (
        <p className="loading-text">Loading agent settings…</p>
      ) : (
        <div className="stack">
          <Panel
            title="Agent settings"
            aside={configured ? "Configured" : "Not configured yet"}
          >
            <ValidatedForm
              fieldErrors={settings.fieldErrors}
              validationTarget={settings.validationTarget}
              onEdit={() => settings.setError("")}
              className="form-grid"
              onSubmit={save}
            >
              <label>
                Agent name
                <ValidatedInput
                  name="name"
                  value={form.name}
                  maxLength={100}
                  required
                  disabled={!manager}
                  onChange={(e) => set("name", e.target.value)}
                />
              </label>
              <label>
                System prompt
                <ValidatedTextarea
                  name="system_prompt"
                  value={form.system_prompt}
                  required
                  disabled={!manager}
                  onChange={(e) => set("system_prompt", e.target.value)}
                />
                <span className="hint">
                  Describe your business, tone and what the agent must never
                  promise. Knowledge and customer text are treated as data, not
                  instructions.
                </span>
              </label>

              <div style={{ marginTop: 8, marginBottom: 8 }}>
                <span
                  className="field"
                  style={{ marginBottom: 6, display: "block" }}
                >
                  Select AI Model & Rate
                </span>
                <p className="hint" style={{ marginTop: 0, marginBottom: 14 }}>
                  All models are hosted and executed by Instantlify. Usage is
                  charged per token directly to your prepaid Instantlify credit
                  balance. No API keys or external developer accounts required.
                </p>
                <div
                  className="card-grid"
                  style={{
                    gridTemplateColumns:
                      "repeat(auto-fill, minmax(270px, 1fr))",
                    gap: 14,
                  }}
                >
                  {platformModels.map((m) => {
                    const isSelected = form.model === m.id;
                    return (
                      <div
                        key={m.id}
                        className="card"
                        onClick={() =>
                          manager &&
                          setForm((cur) => ({
                            ...cur,
                            model: m.id,
                            provider: m.provider,
                            fallback_model:
                              cur.fallback_model === m.id
                                ? ""
                                : cur.fallback_model,
                            fallback_provider:
                              cur.fallback_model === m.id
                                ? ""
                                : cur.fallback_provider,
                          }))
                        }
                        style={{
                          cursor: manager ? "pointer" : "default",
                          border: isSelected
                            ? "2px solid var(--green)"
                            : "1px solid var(--border)",
                          background: isSelected
                            ? "var(--active-card-bg, rgba(99, 102, 241, 0.08))"
                            : "var(--card-bg)",
                          padding: 16,
                          display: "flex",
                          flexDirection: "column",
                          justifyContent: "space-between",
                          transition: "all 0.15s ease",
                        }}
                      >
                        <div>
                          <div
                            className="row between"
                            style={{
                              alignItems: "flex-start",
                              marginBottom: 8,
                            }}
                          >
                            <div>
                              <strong
                                style={{
                                  fontSize: "1rem",
                                  display: "flex",
                                  alignItems: "center",
                                  gap: 8,
                                }}
                              >
                                {MODEL_BRANDS[m.provider] && (
                                  <BrandIcon
                                    name={MODEL_BRANDS[m.provider]!}
                                    size={18}
                                  />
                                )}
                                {m.label}
                              </strong>
                              <div style={{ marginTop: 2 }}>
                                <Pill tone="neutral">{m.provider}</Pill>
                              </div>
                            </div>
                            {isSelected ? (
                              <Pill tone="good">Selected</Pill>
                            ) : (
                              <Pill tone="neutral">{m.badge}</Pill>
                            )}
                          </div>
                          <p
                            className="muted-text"
                            style={{
                              fontSize: "0.85rem",
                              lineHeight: 1.4,
                              margin: "8px 0 14px",
                            }}
                          >
                            {m.description}
                          </p>
                        </div>
                        <div
                          style={{
                            padding: "8px 10px",
                            borderRadius: 6,
                            background:
                              "var(--muted-bg, rgba(255,255,255,0.04))",
                            border: "1px solid var(--border)",
                            fontSize: "0.8rem",
                            fontWeight: 500,
                          }}
                        >
                          <span style={{ color: "var(--muted)" }}>Rate: </span>
                          <strong>{m.rate_summary}</strong>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              <div className="two-col" style={{ marginTop: 10 }}>
                <label>
                  Fallback model (optional)
                  <ValidatedSelect
                    name="fallback_model"
                    value={form.fallback_model}
                    disabled={!manager}
                    onChange={(e) => {
                      const selected = platformModels.find(
                        (m) => m.id === e.target.value,
                      );
                      setForm((cur) => ({
                        ...cur,
                        fallback_model: selected ? selected.id : "",
                        fallback_provider: selected ? selected.provider : "",
                      }));
                    }}
                  >
                    <option value="">None (no fallback)</option>
                    {platformModels
                      .filter((m) => m.id !== form.model)
                      .map((m) => (
                        <option key={m.id} value={m.id}>
                          {m.label} ({m.provider}) — {m.rate_summary}
                        </option>
                      ))}
                  </ValidatedSelect>
                  <span className="hint">
                    Automatic failover if the primary vendor is temporarily
                    rate-limited or unavailable.
                  </span>
                </label>
                <label>
                  Reply mode
                  <ValidatedSelect
                    name="mode"
                    value={form.mode}
                    disabled={!manager}
                    onChange={(e) =>
                      set("mode", e.target.value as "agent" | "simple")
                    }
                  >
                    <option value="agent">
                      Sales agent: stages, tools, triage, bookings and payments
                    </option>
                    <option value="simple">
                      Simple replies: one grounded answer per message, no tools
                    </option>
                  </ValidatedSelect>
                </label>
              </div>
              <div>
                <span className="field" style={{ marginBottom: 8 }}>
                  Allowed tools
                </span>
                <div className="checkbox-grid">
                  {AGENT_TOOLS.map((tool) => (
                    <label key={tool}>
                      <ValidatedInput
                        type="checkbox"
                        checked={form.allowed_tools.includes(tool)}
                        disabled={!manager}
                        onChange={() =>
                          set("allowed_tools", toggle(form.allowed_tools, tool))
                        }
                      />
                      <span>
                        <strong>{tool.replace(/_/g, " ")}</strong>
                        <br />
                        <span className="muted-text">{TOOL_HELP[tool]}</span>
                      </span>
                    </label>
                  ))}
                </div>
                <p className="hint" style={{ marginTop: 8 }}>
                  Booking always requires the customer to reply with a
                  confirmation code. Payment links can only use offers you
                  configure under{" "}
                  <Link href={`/w/${workspace.id}/payments`}>Payments</Link>.
                </p>
              </div>
              <div>
                <span className="field" style={{ marginBottom: 8 }}>
                  Qualifying fields
                </span>
                <div className="checkbox-grid">
                  {QUALIFYING.map((field) => (
                    <label key={field}>
                      <ValidatedInput
                        type="checkbox"
                        checked={form.qualifying_fields.includes(field)}
                        disabled={!manager}
                        onChange={() =>
                          set(
                            "qualifying_fields",
                            toggle(form.qualifying_fields, field),
                          )
                        }
                      />
                      {field}
                    </label>
                  ))}
                </div>
                <p className="hint" style={{ marginTop: 8 }}>
                  The agent stays in the qualify stage until it has recorded
                  these fields, then moves on to pitching.
                </p>
              </div>
              <div className="two-col">
                <label>
                  Handoff keywords
                  <ValidatedInput
                    name="handoff_keywords"
                    value={form.handoff_keywords}
                    placeholder="human, refund, lawyer, complaint"
                    disabled={!manager}
                    onChange={(e) => set("handoff_keywords", e.target.value)}
                  />
                  <span className="hint">
                    Comma-separated. A message containing any of these goes
                    straight to a human, before the model is called.
                  </span>
                </label>
                <label>
                  Max tool rounds per reply
                  <ValidatedInput
                    name="max_tool_rounds"
                    type="number"
                    min={1}
                    max={8}
                    value={form.max_tool_rounds}
                    disabled={!manager}
                    onChange={(e) =>
                      set("max_tool_rounds", Number(e.target.value))
                    }
                  />
                </label>
                <label>
                  Wait before replying (seconds)
                  <ValidatedInput
                    name="reply_delay_seconds"
                    type="number"
                    min={0}
                    max={30}
                    value={form.reply_delay_seconds}
                    disabled={!manager}
                    onChange={(e) =>
                      set("reply_delay_seconds", Number(e.target.value))
                    }
                  />
                  <span className="hint">
                    When a customer sends several messages in a row, the agent
                    waits this long after the last one and answers them
                    together. 0 replies to each message at once.
                  </span>
                </label>
              </div>

              <div className="checkbox-grid">
                <label>
                  <ValidatedInput
                    type="checkbox"
                    checked={form.triage_enabled}
                    disabled={!manager}
                    onChange={(e) => set("triage_enabled", e.target.checked)}
                  />
                  Triage sentiment and urgency; hand off angry or urgent leads
                </label>
                <label>
                  <ValidatedInput
                    type="checkbox"
                    checked={form.is_test}
                    disabled={!manager}
                    onChange={(e) => set("is_test", e.target.checked)}
                  />
                  Use the local test provider (no API key)
                </label>
                <label>
                  <ValidatedInput
                    type="checkbox"
                    checked={form.enabled}
                    disabled={!manager}
                    onChange={(e) => set("enabled", e.target.checked)}
                  />
                  Agent enabled
                </label>
              </div>
              {manager && (
                <div className="form-actions">
                  <button className="button primary" disabled={settings.busy}>
                    {settings.busy ? "Saving…" : "Save agent settings"}
                    <Sparkles size={16} />
                  </button>
                </div>
              )}
            </ValidatedForm>
          </Panel>
          <Knowledge config={savedConfig} />
          {manager && <AgentPreview prefix={prefix} />}
          <AuditPanel />
        </div>
      )}
    </>
  );
}

function Knowledge({ config }: { config: AgentConfig | null }) {
  const { prefix, manager } = useWorkspace();
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [title, setTitle] = useState("");
  const [source, setSource] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [pageUrl, setPageUrl] = useState("");
  const [bases, setBases] = useState<KnowledgeBase[]>([]);
  // "" shows every document; "general" the ones outside any base.
  const [baseFilter, setBaseFilter] = useState("");
  const [newBase, setNewBase] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);
  const confirm = useConfirmation();
  const feedback = useFeedback();

  const loadBases = useCallback(
    async (signal?: AbortSignal) =>
      setBases(
        asList(
          await api<KnowledgeBase[] | { results?: KnowledgeBase[] }>(
            `${prefix}/knowledge-bases/`,
            "GET",
            undefined,
            signal,
          ),
        ),
      ),
    [prefix],
  );
  useEffect(() => {
    const controller = new AbortController();
    queueMicrotask(() => {
      loadBases(controller.signal).catch(() => undefined);
    });
    return () => controller.abort();
  }, [loadBases]);
  const targetBase =
    baseFilter && baseFilter !== "general" ? baseFilter : undefined;
  const shown = documents.filter((doc) =>
    !baseFilter
      ? true
      : baseFilter === "general"
        ? !doc.knowledge_base
        : doc.knowledge_base === baseFilter,
  );

  async function createBase(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const name = newBase.trim();
    if (!name) return;
    const created = await feedback.run(
      () => api<KnowledgeBase>(`${prefix}/knowledge-bases/`, "POST", { name }),
      "Knowledge base created.",
    );
    if (created) {
      setNewBase("");
      setBaseFilter(created.id);
      await loadBases();
    }
  }

  async function removeBase(base: KnowledgeBase) {
    if (
      !(await confirm(
        `Delete the knowledge base “${base.name}”? Its documents move to General knowledge.`,
      ))
    )
      return;
    await feedback.run(async () => {
      await api(`${prefix}/knowledge-bases/${base.id}/`, "DELETE");
      setBaseFilter("");
      await Promise.all([loadBases(), load()]);
    }, "Knowledge base deleted.");
  }

  const load = useCallback(
    async (signal?: AbortSignal) => {
      const page = await api<Page<KnowledgeDocument>>(
        `${prefix}/documents/`,
        "GET",
        undefined,
        signal,
      );
      setDocuments(page.results);
      return page.results;
    },
    [prefix],
  );

  useEffect(() => {
    const controller = new AbortController();
    api<Page<KnowledgeDocument>>(
      `${prefix}/documents/`,
      "GET",
      undefined,
      controller.signal,
    )
      .then((page) => setDocuments(page.results))
      .catch((err) => {
        if (!controller.signal.aborted) feedback.setError(message(err));
      });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefix]);

  const busyDocs = documents.some((doc) =>
    ["pending", "processing"].includes(doc.status),
  );
  useEffect(() => {
    if (!busyDocs) return;
    const timer = window.setInterval(
      () => load().catch(() => undefined),
      10000,
    );
    return () => window.clearInterval(timer);
  }, [busyDocs, load]);

  async function add(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await feedback.run(async () => {
      if (file) {
        if (file.size > 2 * 1024 * 1024)
          throw new Error("Upload a document up to 2 MB.");
        const form = new FormData();
        form.append("title", title || file.name);
        form.append("file", file);
        if (targetBase) form.append("knowledge_base", targetBase);
        await upload(`${prefix}/documents/`, form);
      } else if (pageUrl.trim()) {
        await api(`${prefix}/documents/`, "POST", {
          title: title || pageUrl.trim(),
          url: pageUrl.trim(),
          ...(targetBase ? { knowledge_base: targetBase } : {}),
        });
      } else {
        if (!source.trim())
          throw new Error("Paste some text or choose a file.");
        await api(`${prefix}/documents/`, "POST", {
          title: title || "Knowledge document",
          source,
          ...(targetBase ? { knowledge_base: targetBase } : {}),
        });
      }
      setTitle("");
      setSource("");
      setPageUrl("");
      setFile(null);
      if (fileInput.current) fileInput.current.value = "";
      await load();
    }, "Document queued for indexing.");
  }

  async function remove(doc: KnowledgeDocument) {
    if (!(await confirm(`Remove “${doc.title}” from the knowledge base?`)))
      return;
    await feedback.run(async () => {
      await api(`${prefix}/documents/${doc.id}/`, "DELETE");
      await load();
    }, "Document removed.");
  }

  return (
    <>
      <Panel title="Agent readiness">
        <ul>
          <li>
            {config?.enabled
              ? "Agent enabled"
              : "Enable the agent and save settings"}
          </li>
          <li>
            {config?.is_test
              ? "Local test provider selected"
              : config?.billing_mode === "platform_credits"
                ? "Platform credits selected"
                : config?.has_key
                  ? "Provider key saved"
                  : "Save a provider key or select platform credits"}
          </li>
          <li>
            {documents.some(
              (doc) =>
                doc.status === "ready" &&
                doc.embedding_model === config?.embedding_model,
            )
              ? "Knowledge is indexed"
              : busyDocs
                ? "Knowledge indexing is in progress"
                : "Add a knowledge document for grounded replies"}
          </li>
          <li>
            Use Agent preview to check a sample response, then enable AI in a
            conversation.
          </li>
        </ul>
      </Panel>
      <Panel title="Knowledge base" aside={`${documents.length} document(s)`}>
        <ErrorNotice error={feedback.error} />
        <SuccessNotice notice={feedback.notice} />
        <p className="muted-text" style={{ marginBottom: 14 }}>
          FAQs, pricing and policies are chunked, embedded and retrieved on
          every reply. Documents index in the background after you add them.
          Group documents into knowledge bases so each flow AI agent answers
          from the right one; the workspace assistant uses all of them.
        </p>
        <div className="row wrap" style={{ gap: 8, marginBottom: 14 }}>
          <select
            aria-label="Knowledge base"
            value={baseFilter}
            onChange={(event) => setBaseFilter(event.target.value)}
          >
            <option value="">All documents</option>
            <option value="general">General knowledge</option>
            {bases.map((base) => (
              <option key={base.id} value={base.id}>
                {base.name} ({base.document_count})
              </option>
            ))}
          </select>
          {manager && targetBase && (
            <button
              type="button"
              className="text-button"
              onClick={() => {
                const base = bases.find((item) => item.id === targetBase);
                if (base) void removeBase(base);
              }}
            >
              <Trash2 size={14} /> Delete this base
            </button>
          )}
          {manager && (
            <form className="row" style={{ gap: 6 }} onSubmit={createBase}>
              <input
                aria-label="New knowledge base name"
                placeholder="New knowledge base"
                maxLength={80}
                value={newBase}
                onChange={(event) => setNewBase(event.target.value)}
              />
              <button type="submit" className="button small secondary">
                Create
              </button>
            </form>
          )}
        </div>
        {manager && targetBase && (
          <p className="muted-text small">
            New documents are added to{" "}
            <strong>
              {bases.find((base) => base.id === targetBase)?.name}
            </strong>
            .
          </p>
        )}
        {manager && (
          <ValidatedForm
            fieldErrors={feedback.fieldErrors}
            validationTarget={feedback.validationTarget}
            onEdit={() => feedback.setError("")}
            className="form-grid"
            onSubmit={add}
          >
            <div className="two-col">
              <label>
                Title
                <ValidatedInput
                  value={title}
                  maxLength={200}
                  placeholder="Pricing FAQ"
                  onChange={(e) => setTitle(e.target.value)}
                />
              </label>
              <label>
                Upload a file (PDF, DOCX, TXT or Markdown, up to 2 MB)
                <ValidatedInput
                  ref={fileInput}
                  type="file"
                  accept=".pdf,.docx,.txt,.md"
                  onChange={(e) => setFile(e.target.files?.[0] || null)}
                />
              </label>
            </div>
            <label>
              Or import a web page
              <ValidatedInput
                type="url"
                value={pageUrl}
                maxLength={2000}
                placeholder="https://yoursite.com/faq"
                disabled={!!file}
                onChange={(e) => setPageUrl(e.target.value)}
              />
            </label>
            <label>
              Paste FAQ text
              <ValidatedTextarea
                value={source}
                maxLength={250000}
                placeholder="Or paste the text directly…"
                disabled={!!file || !!pageUrl.trim()}
                onChange={(e) => setSource(e.target.value)}
              />
            </label>
            <div className="form-actions">
              <button className="button primary small" disabled={feedback.busy}>
                {feedback.busy ? "Adding…" : "Add to knowledge base"}
                <Upload size={14} />
              </button>
            </div>
          </ValidatedForm>
        )}
        <div className="card-list" style={{ marginTop: 18 }}>
          {shown.length === 0 ? (
            <Empty>No documents yet. Add your FAQ to ground the agent.</Empty>
          ) : (
            shown.map((doc) => (
              <div className="list-row" key={doc.id}>
                <FileText size={16} className="subtle" />
                <strong>{doc.title}</strong>
                <Pill tone={statusTone(doc.status)}>{doc.status}</Pill>
                {doc.error_code && (
                  <span className="muted-text mono">{doc.error_code}</span>
                )}
                <span className="spacer" />
                <span className="muted-text">{when(doc.created_at)}</span>
                {manager && (
                  <button
                    className="text-button"
                    disabled={feedback.busy}
                    onClick={() => remove(doc)}
                  >
                    <Trash2 size={14} /> Remove
                  </button>
                )}
              </div>
            ))
          )}
        </div>
      </Panel>
    </>
  );
}

function AuditPanel() {
  const { prefix } = useWorkspace();
  const [audit, setAudit] = useState<AgentAudit | null>(null);
  const feedback = useFeedback();

  const load = useCallback(
    async (signal?: AbortSignal) => {
      setAudit(
        await api<AgentAudit>(
          `${prefix}/agent-audit/`,
          "GET",
          undefined,
          signal,
        ),
      );
    },
    [prefix],
  );

  useEffect(() => {
    const controller = new AbortController();
    api<AgentAudit>(
      `${prefix}/agent-audit/`,
      "GET",
      undefined,
      controller.signal,
    )
      .then(setAudit)
      .catch((err) => {
        if (!controller.signal.aborted) feedback.setError(message(err));
      });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefix]);

  const pretty = (value: unknown) => JSON.stringify(value);

  return (
    <Panel
      title="Audit trail"
      aside={
        <button
          className="text-button"
          disabled={feedback.busy}
          onClick={() => feedback.run(() => load())}
        >
          <RefreshCw size={14} /> Refresh
        </button>
      }
    >
      <ErrorNotice error={feedback.error} />
      {!audit ? (
        <p className="loading-text">Loading audit trail…</p>
      ) : (
        <div className="stack">
          <div>
            <h3 className="small" style={{ marginBottom: 8 }}>
              Runs
            </h3>
            {audit.runs.length === 0 ? (
              <Empty>No agent runs yet.</Empty>
            ) : (
              <Table head={["Status", "Error", "Started"]}>
                {audit.runs.map((run) => (
                  <tr key={run.id}>
                    <td>
                      <Pill tone={statusTone(run.status)}>{run.status}</Pill>
                    </td>
                    <td className="mono">{run.error_code || "—"}</td>
                    <td>{when(run.created_at)}</td>
                  </tr>
                ))}
              </Table>
            )}
          </div>
          <div>
            <h3 className="small" style={{ marginBottom: 8 }}>
              Tool calls
            </h3>
            {audit.tools.length === 0 ? (
              <Empty>No tool calls yet.</Empty>
            ) : (
              <Table head={["Tool", "Status", "Input", "Output"]}>
                {audit.tools.map((call) => (
                  <tr key={call.id}>
                    <td>{call.name}</td>
                    <td>
                      <Pill tone={statusTone(call.status)}>{call.status}</Pill>
                    </td>
                    <td>
                      <code className="mono">{pretty(call.input)}</code>
                    </td>
                    <td>
                      <code className="mono">{pretty(call.output)}</code>
                    </td>
                  </tr>
                ))}
              </Table>
            )}
          </div>
          <div>
            <h3 className="small" style={{ marginBottom: 8 }}>
              Usage
            </h3>
            {audit.usage.length === 0 ? (
              <Empty>No usage recorded yet.</Empty>
            ) : (
              <Table
                head={["Model", "Kind", "Tokens in / out", "Cost", "When"]}
              >
                {audit.usage.map((row) => (
                  <tr key={row.id}>
                    <td>{row.model}</td>
                    <td>{row.kind}</td>
                    <td>
                      {row.input_tokens} / {row.output_tokens}
                    </td>
                    <td>{Number(row.cost).toFixed(6)}</td>
                    <td>{when(row.created_at)}</td>
                  </tr>
                ))}
              </Table>
            )}
          </div>
        </div>
      )}
    </Panel>
  );
}
