"use client";

import { ValidatedForm, ValidatedInput } from "@/components/validated-form";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Check,
  ChevronRight,
  Folder,
  Layers,
  Mic,
  Plus,
  Search,
  Sparkles,
  Users,
  Workflow,
  Zap,
} from "lucide-react";
import {
  api,
  message,
  type Automation,
  type AutomationStats,
  type Page,
} from "@/lib/api";
import { useWorkspace } from "@/lib/workspace";
import { BrandIcon, type BrandName } from "@/lib/brand-icons";
import { channelLabel } from "@/lib/channels";
import { META_TEMPLATES, triggerChannels } from "@/lib/meta-templates";
import { SimpleAutomationBuilder } from "@/components/simple-automation-builder";
import { AutomationActions } from "@/components/automation-actions";
import {
  ErrorNotice,
  Modal,
  SuccessNotice,
  useFeedback,
} from "@/components/ui";

/** The advanced builder opens on this draft: a comment trigger and one reply. */
const STARTER_GRAPH = {
  start: "welcome",
  triggers: [{ kind: "comment", keyword: "price" }],
  nodes: [
    {
      id: "welcome",
      position: { x: 80, y: 80 },
      data: {
        kind: "send_buttons",
        text: "Thanks for asking! Here is everything you need.",
        buttons: [
          {
            type: "web_url",
            url: "https://example.com/pricing",
            title: "See pricing",
          },
        ],
      },
    },
    { id: "done", position: { x: 80, y: 260 }, data: { kind: "end" } },
  ],
  edges: [{ id: "welcome-done", source: "welcome", target: "done" }],
};

/** Square channel tile on each row: the platform's logo on its brand colour. */
const CHANNEL_TILES: Record<string, { brand: BrandName; background?: string }> =
  {
    instagram: { brand: "instagram" },
    messenger: { brand: "facebook", background: "#1877f2" },
    whatsapp: { brand: "whatsapp", background: "#25d366" },
    telegram: { brand: "telegram", background: "#26a5e4" },
    linkedin: { brand: "linkedin", background: "#0a66c2" },
  };

/** The graph that describes what the automation does today. */
const graphOf = (item: Automation) =>
  item.published?.triggers?.length ? item.published : item.draft;

export default function AutomationsPage() {
  const { workspace, prefix } = useWorkspace();
  const router = useRouter();
  const [tab, setTab] = useState<"list" | "templates">("list");
  const [automations, setAutomations] = useState<Automation[]>([]);
  const [stats, setStats] = useState<AutomationStats>({});
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<"all" | "active" | "inactive">("all");
  const [aiPrompt, setAiPrompt] = useState("");
  const [builderMode, setBuilderMode] = useState<"simple" | null>(null);
  const [showCreateMenu, setShowCreateMenu] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Automation | null>(null);
  const createMenuRef = useRef<HTMLDivElement>(null);
  const importFile = useRef<HTMLInputElement>(null);
  const feedback = useFeedback();

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        createMenuRef.current &&
        !createMenuRef.current.contains(event.target as Node)
      ) {
        setShowCreateMenu(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const loadAutomations = useCallback(
    async (signal?: AbortSignal) => {
      const [page, counts] = await Promise.all([
        api<Page<Automation>>(
          `${prefix}/automations/`,
          "GET",
          undefined,
          signal,
        ),
        api<AutomationStats>(
          `${prefix}/automations/stats/`,
          "GET",
          undefined,
          signal,
        ).catch(() => ({}) as AutomationStats),
      ]);
      setAutomations(page.results || []);
      setStats(counts);
    },
    [prefix],
  );

  useEffect(() => {
    const controller = new AbortController();
    queueMicrotask(() =>
      loadAutomations(controller.signal)
        .catch((err) => {
          if (!controller.signal.aborted) feedback.setError(message(err));
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        }),
    );
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loadAutomations]);

  async function createFrom(name: string, draft: object) {
    await feedback.run(async () => {
      const created = await api<Automation>(`${prefix}/automations/`, "POST", {
        name,
        draft,
      });
      router.push(`/w/${workspace.id}/automations/${created.id}`);
    });
  }

  async function toggleStatus(item: Automation) {
    await feedback.run(async () => {
      const updated = await api<Automation>(
        `${prefix}/automations/${item.id}/`,
        "PATCH",
        { enabled: !item.enabled },
      );
      setAutomations((prev) =>
        prev.map((a) => (a.id === item.id ? { ...a, ...updated } : a)),
      );
    });
  }

  async function handleVoicePrompt(e: React.FormEvent) {
    e.preventDefault();
    const prompt = aiPrompt.trim();
    if (!prompt) return;
    await feedback.run(async () => {
      const created = await api<Automation>(
        `${prefix}/automations/generate/`,
        "POST",
        { prompt },
      );
      setAiPrompt("");
      router.push(`/w/${workspace.id}/automations/${created.id}`);
    });
  }

  const query = search.trim().toLowerCase();
  const filteredAutomations = automations.filter((item) => {
    const matchesSearch = item.name.toLowerCase().includes(query);
    if (filter === "active") return matchesSearch && item.enabled;
    if (filter === "inactive") return matchesSearch && !item.enabled;
    return matchesSearch;
  });

  if (builderMode === "simple") {
    return (
      <SimpleAutomationBuilder
        workspaceId={workspace.id}
        workspaceName={workspace.name}
        onBack={() => setBuilderMode(null)}
        onSaved={() => {
          setBuilderMode(null);
          loadAutomations().catch((err) => feedback.setError(message(err)));
        }}
      />
    );
  }

  return (
    <div className="automations-page-container">
      {/* Page Header with List vs Templates Toggle */}
      <div className="automations-header-row">
        <ValidatedInput
          ref={importFile}
          hidden
          type="file"
          accept=".json,application/json"
          onChange={(event) => {
            const file = event.target.files?.[0];
            event.target.value = "";
            if (!file) return;
            void feedback.run(async () => {
              if (file.size > 200000)
                throw new Error("Template files must be under 200 KB.");
              const created = await api<Automation>(
                `${prefix}/automations/import/`,
                "POST",
                { template: await file.text() },
              );
              router.push(`/w/${workspace.id}/automations/${created.id}`);
            });
          }}
        />
        <button
          className="button secondary small"
          disabled={feedback.busy}
          onClick={() => importFile.current?.click()}
        >
          Import JSON template
        </button>
        <div>
          <h1 className="page-heading-title">
            {tab === "list" ? "Automations" : "Templates"}
          </h1>
          <p className="page-heading-subtitle">
            {tab === "list"
              ? "Here you are able to view and manage your automations"
              : "Ready-to-use automation workflows"}
          </p>
        </div>

        <div className="tab-pill-toggle">
          <button
            type="button"
            className={`pill-toggle-btn ${tab === "list" ? "active" : ""}`}
            onClick={() => setTab("list")}
          >
            List
          </button>
          <button
            type="button"
            className={`pill-toggle-btn ${tab === "templates" ? "active" : ""}`}
            onClick={() => setTab("templates")}
          >
            Templates
          </button>
        </div>
      </div>

      <ErrorNotice error={feedback.error} />
      <SuccessNotice notice={feedback.notice} />
      {deleteTarget && (
        <Modal
          title="Delete automation"
          onClose={() => {
            if (!feedback.busy) setDeleteTarget(null);
          }}
        >
          <p>
            Delete <strong>{deleteTarget.name}</strong>? This permanently
            removes the automation and its execution history.
          </p>
          <ErrorNotice error={feedback.error} />
          <div className="row" style={{ marginTop: 24, gap: 12 }}>
            <button
              type="button"
              className="button secondary"
              disabled={feedback.busy}
              onClick={() => setDeleteTarget(null)}
            >
              Cancel
            </button>
            <button
              type="button"
              className="button primary"
              disabled={feedback.busy}
              onClick={() =>
                void feedback.run(async () => {
                  await api(
                    `${prefix}/automations/${deleteTarget.id}/`,
                    "DELETE",
                  );
                  setAutomations((rows) =>
                    rows.filter((row) => row.id !== deleteTarget.id),
                  );
                  setDeleteTarget(null);
                }, "Automation deleted.")
              }
            >
              {feedback.busy ? "Deleting…" : "Delete automation"}
            </button>
          </div>
        </Modal>
      )}

      {/* VIEW 1: AUTOMATIONS LIST */}
      {tab === "list" && (
        <div className="automations-list-view">
          {/* Top 2 Cards: AI Knowledgebases & Integrations */}
          <div className="boosend-resource-cards-grid">
            <Link href={`/w/${workspace.id}/agent`} className="resource-card">
              <span className="resource-icon-wrap dark-folder">
                <Folder size={20} />
              </span>
              <div className="resource-card-text">
                <strong className="resource-title">AI Knowledgebases</strong>
                <p className="resource-desc">
                  Upload and manage files, documents, and content that your AI
                  agents can reference to provide accurate, context-aware
                  responses to your customers.
                </p>
              </div>
            </Link>

            <Link
              href={`/w/${workspace.id}/integrations`}
              className="resource-card"
            >
              <span className="resource-icon-wrap dark-grid">
                <Layers size={20} />
              </span>
              <div className="resource-card-text">
                <strong className="resource-title">Integrations</strong>
                <p className="resource-desc">
                  Connect your favorite tools and platforms to Instantlify. Sync
                  contacts, automate workflows, and extend your automation
                  capabilities with powerful integrations.
                </p>
              </div>
            </Link>
          </div>

          {/* Search, Filter Pills & Create New Button */}
          <div className="automations-toolbar-row">
            <div className="search-input-wrapper">
              <Search size={16} className="search-icon" />
              <ValidatedInput
                type="text"
                placeholder="Search automations..."
                aria-label="Search automations"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="search-input-field"
              />
            </div>

            <div className="status-filter-pills">
              <button
                type="button"
                className={`filter-pill ${filter === "all" ? "active" : ""}`}
                onClick={() => setFilter("all")}
              >
                All
              </button>
              <button
                type="button"
                className={`filter-pill ${filter === "active" ? "active" : ""}`}
                onClick={() => setFilter("active")}
              >
                <span className="dot-green" /> Active
              </button>
              <button
                type="button"
                className={`filter-pill ${filter === "inactive" ? "active" : ""}`}
                onClick={() => setFilter("inactive")}
              >
                <span className="dot-gray" /> Inactive
              </button>
            </div>

            <div className="toolbar-actions-right">
              <button
                type="button"
                className="button-transfer"
                onClick={() => setTab("templates")}
              >
                Browse Templates
              </button>
              <div className="create-new-button-wrapper" ref={createMenuRef}>
                <button
                  type="button"
                  className="button-create-new"
                  onClick={() => setShowCreateMenu(!showCreateMenu)}
                >
                  <Plus size={16} /> Create New
                </button>

                {showCreateMenu && (
                  <div className="choose-builder-popover">
                    <div className="choose-builder-header">
                      CHOOSE HOW TO BUILD
                    </div>

                    {/* Option 1: Simple automation */}
                    <button
                      type="button"
                      className="builder-option-item"
                      onClick={() => {
                        setShowCreateMenu(false);
                        setBuilderMode("simple");
                      }}
                    >
                      <div className="builder-option-icon simple">
                        <Zap size={18} />
                      </div>
                      <div className="builder-option-text">
                        <div className="builder-option-title-row">
                          <span className="builder-option-name">
                            Simple automation
                          </span>
                          <span className="builder-easiest-pill">EASIEST</span>
                        </div>
                        <div className="builder-option-desc">
                          Guided, step-by-step. Perfect if you just want
                          comment-to-DM.
                        </div>
                      </div>
                      <ChevronRight
                        size={16}
                        className="builder-option-chevron"
                      />
                    </button>

                    {/* Option 2: Advanced builder */}
                    <button
                      type="button"
                      className="builder-option-item"
                      disabled={feedback.busy}
                      onClick={() => {
                        setShowCreateMenu(false);
                        createFrom("Untitled automation", STARTER_GRAPH);
                      }}
                    >
                      <div className="builder-option-icon advanced">
                        <Workflow size={18} />
                      </div>
                      <div className="builder-option-text">
                        <div className="builder-option-title-row">
                          <span className="builder-option-name">
                            Advanced builder
                          </span>
                        </div>
                        <div className="builder-option-desc">
                          Full canvas with triggers, branching and every node
                          type.
                        </div>
                      </div>
                      <ChevronRight
                        size={16}
                        className="builder-option-chevron"
                      />
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Automations Cards List */}
          <div className="automations-cards-stack">
            {loading ? (
              <p className="loading-text">Loading automations…</p>
            ) : !automations.length ? (
              <div className="boosend-automation-row-card automations-empty-row">
                <div className="row-channel-icon automations-empty-icon">
                  <Workflow size={20} />
                </div>
                <div className="row-info-col">
                  <span className="row-automation-name">
                    No automations yet
                  </span>
                  <div className="row-meta-sub">
                    <span className="created-date">
                      Click Create New or pick one from Templates to start.
                    </span>
                  </div>
                </div>
              </div>
            ) : !filteredAutomations.length ? (
              <p className="loading-text">No automations match.</p>
            ) : (
              filteredAutomations.map((item) => {
                const provider = triggerChannels(graphOf(item)?.triggers)[0];
                const tile = provider ? CHANNEL_TILES[provider] : undefined;
                const published = Boolean(item.published?.start);
                const counts = stats[item.id];
                return (
                  <div key={item.id} className="boosend-automation-row-card">
                    <div
                      className={`row-channel-icon ${provider ?? ""}`}
                      style={
                        tile?.background
                          ? { background: tile.background }
                          : !tile
                            ? { background: "#0f172a" }
                            : undefined
                      }
                      title={
                        provider ? channelLabel(provider) : "No trigger yet"
                      }
                    >
                      {tile ? (
                        <BrandIcon name={tile.brand} size={20} mono />
                      ) : (
                        <Workflow size={20} />
                      )}
                    </div>
                    <div className="row-info-col">
                      <Link
                        href={`/w/${workspace.id}/automations/${item.id}`}
                        className="row-automation-name"
                      >
                        {item.name}
                      </Link>
                      <div className="row-meta-sub">
                        <span className="created-date">
                          Created on{" "}
                          {new Date(item.created_at).toLocaleDateString()}
                        </span>
                        <span
                          className={`status-pill ${item.enabled ? "active" : "draft"}`}
                        >
                          {item.enabled
                            ? "Active"
                            : published
                              ? "Paused"
                              : "Draft"}
                        </span>
                      </div>
                    </div>

                    <div className="row-metrics-col">
                      <div className="metric-tag" title="Executions">
                        <Check size={14} />{" "}
                        <span className="metric-runs">{counts?.runs ?? 0}</span>
                      </div>
                      <div className="metric-tag" title="Users reached">
                        <Users size={14} />{" "}
                        <span className="metric-reach">
                          {counts?.reach ?? 0}
                        </span>
                      </div>
                    </div>

                    <button
                      type="button"
                      role="switch"
                      aria-checked={item.enabled}
                      aria-label={`${item.name} active`}
                      className={`toggle-switch-btn ${item.enabled ? "active" : ""}`}
                      disabled={feedback.busy || !published}
                      onClick={() => toggleStatus(item)}
                      title={
                        published ? "Toggle active" : "Publish the flow first"
                      }
                    >
                      <span className="switch-thumb" />
                    </button>

                    <AutomationActions
                      item={item}
                      href={`/w/${workspace.id}/automations/${item.id}`}
                      busy={feedback.busy}
                      onDelete={() => {
                        feedback.setError("");
                        setDeleteTarget(item);
                      }}
                      onDuplicate={() =>
                        void feedback.run(async () => {
                          const copy = await api<Automation>(
                            `${prefix}/automations/${item.id}/duplicate/`,
                            "POST",
                          );
                          setAutomations((rows) => [copy, ...rows]);
                        }, "Automation duplicated as a draft.")
                      }
                    />
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}

      {/* VIEW 2: TEMPLATES */}
      {tab === "templates" && (
        <div className="templates-catalog-view">
          {/* Top Hero Card: Speak To Generate A Workflow */}
          <div className="speak-to-generate-hero-card">
            <div className="hero-ghost-icon">
              <Sparkles size={34} />
            </div>
            <h2 className="hero-title">Speak to generate a workflow</h2>
            <p className="hero-desc">
              You describe the automation you want to build, and our AI will do
              it!
            </p>
            <ValidatedForm
              fieldErrors={feedback.fieldErrors}
              validationTarget={feedback.validationTarget}
              onEdit={() => feedback.setError("")}
              onSubmit={handleVoicePrompt}
              className="voice-prompt-input-row"
            >
              <button
                type="button"
                className="mic-round-btn"
                title="Voice input"
                tabIndex={-1}
              >
                <Mic size={16} />
              </button>
              <ValidatedInput
                type="text"
                placeholder="I want to build an automation to deliver a free PDF when someone comments LEADS..."
                aria-label="Describe the automation"
                value={aiPrompt}
                maxLength={2000}
                onChange={(e) => setAiPrompt(e.target.value)}
                className="ai-prompt-input"
              />
              <button
                type="submit"
                className="generate-submit-btn"
                disabled={feedback.busy || !aiPrompt.trim()}
              >
                {feedback.busy ? "Building…" : "Generate"}
              </button>
            </ValidatedForm>
          </div>

          {/* Grid of Ready-to-Use Templates */}
          <div className="templates-catalog-grid">
            {META_TEMPLATES.map((tpl) => {
              const tile = CHANNEL_TILES[tpl.channel];
              return (
                <div key={tpl.id} className="template-import-card">
                  <div className="template-card-header">
                    <span className={`channel-badge-icon ${tpl.channel}`}>
                      {tile ? (
                        <BrandIcon name={tile.brand} size={18} />
                      ) : (
                        <Sparkles size={18} />
                      )}
                    </span>
                    <h3 className="template-card-title">{tpl.name}</h3>
                  </div>
                  <p className="template-card-desc">{tpl.summary}</p>
                  <button
                    type="button"
                    className="import-template-btn"
                    disabled={feedback.busy}
                    onClick={() => createFrom(tpl.name, tpl.graph)}
                  >
                    Import
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
