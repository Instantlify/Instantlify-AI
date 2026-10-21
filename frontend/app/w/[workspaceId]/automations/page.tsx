"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import {
  ArrowRightLeft,
  BarChart3,
  Check,
  ChevronDown,
  ChevronRight,
  Copy,
  Ellipsis,
  Folder,
  FolderInput,
  Layers,
  List,
  Mic,
  Pencil,
  Plus,
  Search,
  Sparkles,
  Trash2,
  Users,
  Workflow,
  Zap,
} from "lucide-react";
import {
  api,
  message,
  type Automation,
  type AutomationRun,
  type AutomationStats,
  type Page,
} from "@/lib/api";
import { useWorkspace } from "@/lib/workspace";
import { ChannelIcon, channelLabel, META_CHANNELS } from "@/lib/channels";
import {
  META_TEMPLATES,
  TRIGGER_LABELS,
  triggerChannels,
} from "@/lib/meta-templates";
import { AutomationStarter } from "@/components/automation-starter";
import { SimpleAutomationBuilder } from "@/components/simple-automation-builder";
import {
  Empty,
  ErrorNotice,
  Modal,
  PageHeading,
  Panel,
  Pill,
  statusTone,
  SuccessNotice,
  Table,
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

type Status = "live" | "paused" | "draft";
const STATUSES: { id: "all" | Status; label: string }[] = [
  { id: "all", label: "All" },
  { id: "live", label: "Live" },
  { id: "paused", label: "Paused" },
  { id: "draft", label: "Draft" },
];

const statusOf = (item: Automation): Status =>
  item.enabled ? "live" : item.published?.start ? "paused" : "draft";

/** The graph that describes what the automation does today. */
const graphOf = (item: Automation) =>
  item.published?.triggers?.length ? item.published : item.draft;

type Dialog =
  | { kind: "folder"; item: Automation }
  | { kind: "transfer"; item: Automation }
  | { kind: "delete"; item: Automation }
  | null;

export default function AutomationsPage() {
  const { workspace, workspaces, prefix, manager } = useWorkspace();
  const router = useRouter();
  const [tab, setTab] = useState<"list" | "templates">("list");
  const [items, setItems] = useState<Automation[]>([]);
  const [stats, setStats] = useState<AutomationStats>({});
  const [runs, setRuns] = useState<AutomationRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState<"list" | "folders">("list");
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<"all" | Status>("all");
  const [channel, setChannel] = useState("all");
  const [menu, setMenu] = useState<string | null>(null);
  const [dialog, setDialog] = useState<Dialog>(null);
  const [aiPrompt, setAiPrompt] = useState("");
  const [builderMode, setBuilderMode] = useState<"simple" | null>(null);
  const [showCreateMenu, setShowCreateMenu] = useState(false);
  const createMenuRef = useRef<HTMLDivElement>(null);
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

  const load = useCallback(
    async (signal?: AbortSignal) => {
      const [page, states, counts] = await Promise.all([
        api<Page<Automation>>(`${prefix}/automations/`, "GET", undefined, signal),
        api<AutomationRun[]>(
          `${prefix}/automation-runs/`,
          "GET",
          undefined,
          signal,
        ),
        api<AutomationStats>(
          `${prefix}/automations/stats/`,
          "GET",
          undefined,
          signal,
        ),
      ]);
      setItems(page.results);
      setRuns(states);
      setStats(counts);
    },
    [prefix],
  );

  useEffect(() => {
    if (!manager) {
      queueMicrotask(() => setLoading(false));
      return;
    }
    const controller = new AbortController();
    queueMicrotask(() =>
      load(controller.signal)
        .catch((err) => {
          if (!controller.signal.aborted)
            feedback.setError((err as Error).message);
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        }),
    );
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [load, manager]);

  async function createFrom(name: string, draft: object) {
    await feedback.run(async () => {
      const created = await api<Automation>(`${prefix}/automations/`, "POST", {
        name,
        draft,
      });
      router.push(`/w/${workspace.id}/automations/${created.id}`);
    });
  }
  async function generate(event: React.FormEvent) {
    event.preventDefault();
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
  const replace = (updated: Automation) =>
    setItems((list) =>
      list.map((row) => (row.id === updated.id ? updated : row)),
    );
  async function toggle(item: Automation) {
    await feedback.run(
      async () => {
        replace(
          await api<Automation>(`${prefix}/automations/${item.id}/`, "PATCH", {
            enabled: !item.enabled,
          }),
        );
      },
      item.enabled ? "Automation paused." : "Automation enabled.",
    );
  }
  async function duplicate(item: Automation) {
    await feedback.run(async () => {
      const copy = await api<Automation>(
        `${prefix}/automations/${item.id}/duplicate/`,
        "POST",
      );
      setItems((list) => [copy, ...list]);
    }, `Duplicated as “${item.name} (copy)”. The copy is a disabled draft.`);
  }
  async function moveToFolder(item: Automation, folder: string) {
    const done = await feedback.run(
      async () => {
        replace(
          await api<Automation>(`${prefix}/automations/${item.id}/`, "PATCH", {
            folder,
          }),
        );
        return true;
      },
      folder ? `Moved to “${folder}”.` : "Removed from its folder.",
    );
    if (done) setDialog(null);
  }
  async function transfer(item: Automation, target: string, reason: string) {
    const done = await feedback.run(
      async () => {
        await api(`${prefix}/automations/${item.id}/transfer/`, "POST", {
          workspace: target,
          reason,
        });
        setItems((list) => list.filter((row) => row.id !== item.id));
        return true;
      },
      `Moved “${item.name}” to ${workspaces.find((w) => w.id === target)?.name ?? "the other workspace"}. It arrives paused.`,
    );
    if (done) setDialog(null);
  }
  async function remove(item: Automation) {
    const done = await feedback.run(async () => {
      await api(`${prefix}/automations/${item.id}/`, "DELETE");
      setItems((list) => list.filter((row) => row.id !== item.id));
      return true;
    }, `Deleted “${item.name}”.`);
    if (done) setDialog(null);
  }

  if (!manager)
    return (
      <>
        <PageHeading
          eyebrow="Automations"
          title="Flows are managed by owners and admins."
        />
        <Empty>Ask a workspace admin for access to the flow builder.</Empty>
      </>
    );

  if (builderMode === "simple") {
    return (
      <SimpleAutomationBuilder
        workspaceId={workspace.id}
        workspaceName={workspace.name}
        onBack={() => setBuilderMode(null)}
        onSaved={() => {
          setBuilderMode(null);
          load().catch((err) => feedback.setError(message(err)));
        }}
      />
    );
  }

  const query = search.trim().toLowerCase();
  const visible = items.filter((item) => {
    const graph = graphOf(item);
    return (
      (status === "all" || statusOf(item) === status) &&
      (channel === "all" ||
        triggerChannels(graph?.triggers).includes(channel)) &&
      (!query ||
        item.name.toLowerCase().includes(query) ||
        item.folder.toLowerCase().includes(query) ||
        (graph?.triggers || []).some((t) =>
          t.keyword.toLowerCase().includes(query),
        ))
    );
  });
  const folders = [
    ...new Set(items.map((item) => item.folder).filter(Boolean)),
  ].sort((a, b) => a.localeCompare(b));
  const groups =
    view === "folders"
      ? [
          ...folders.map((name) => ({
            name,
            rows: visible.filter((item) => item.folder === name),
          })),
          { name: "", rows: visible.filter((item) => !item.folder) },
        ].filter((group) => group.rows.length)
      : [{ name: "", rows: visible }];
  const names = Object.fromEntries(items.map((item) => [item.id, item.name]));
  const destinations = workspaces.filter(
    (item) => item.id !== workspace.id && item.role !== "agent",
  );

  const row = (item: Automation) => {
    const graph = graphOf(item);
    const state = statusOf(item);
    const channels = triggerChannels(graph?.triggers);
    const counts = stats[item.id];
    const triggers =
      (graph?.triggers || [])
        .map(
          (trigger) =>
            `${TRIGGER_LABELS[trigger.kind] ?? trigger.kind}: “${trigger.keyword}”`,
        )
        .join(" · ") || "No trigger yet";
    return (
      <div key={item.id} className="boosend-automation-row-card">
        <span
          className="row-channel-stack"
          aria-label={channels.map(channelLabel).join(", ") || "No trigger yet"}
        >
          {channels.length ? (
            channels.map((provider) => (
              <ChannelIcon key={provider} provider={provider} size={18} />
            ))
          ) : (
            <Workflow size={18} aria-hidden="true" />
          )}
        </span>
        <div className="row-info-col">
          <Link
            href={`/w/${workspace.id}/automations/${item.id}`}
            className="row-automation-name"
          >
            {item.name}
          </Link>
          <div className="row-meta-sub">
            <span className="created-date">
              {triggers}
              {item.installed_from && " · from template"} · Created{" "}
              {new Date(item.created_at).toLocaleDateString()}
            </span>
            <span className={`status-pill ${state}`}>{state}</span>
          </div>
        </div>

        <div className="row-metrics-col">
          <div className="metric-tag" title="Runs">
            <Check size={14} aria-hidden="true" />
            <span className="metric-runs" aria-label={`${counts?.runs ?? 0} runs`}>
              {counts?.runs ?? 0}
            </span>
          </div>
          <div className="metric-tag" title="People reached">
            <Users size={14} aria-hidden="true" />
            <span
              className="metric-reach"
              aria-label={`${counts?.reach ?? 0} people reached`}
            >
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
          disabled={feedback.busy || !item.published?.start}
          title={item.published?.start ? undefined : "Publish the flow first"}
          onClick={() => toggle(item)}
        >
          <span className="switch-thumb" />
        </button>

        <div className="row-menu">
          <button
            type="button"
            className="icon-button-dots"
            aria-label={`Actions for ${item.name}`}
            aria-expanded={menu === item.id}
            onClick={() => setMenu(menu === item.id ? null : item.id)}
          >
            <Ellipsis size={16} />
          </button>
          {menu === item.id && (
            <RowMenu onClose={() => setMenu(null)}>
              <Link href={`/w/${workspace.id}/automations/${item.id}`}>
                <Pencil size={14} /> Edit flow
              </Link>
              <button type="button" onClick={() => duplicate(item)}>
                <Copy size={14} /> Duplicate
              </button>
              <button
                type="button"
                onClick={() => setDialog({ kind: "folder", item })}
              >
                <FolderInput size={14} /> Move to folder
              </button>
              <button
                type="button"
                onClick={() => setDialog({ kind: "transfer", item })}
                disabled={!destinations.length}
                title={
                  destinations.length
                    ? undefined
                    : "You manage no other workspace"
                }
              >
                <ArrowRightLeft size={14} /> Transfer
              </button>
              <Link href={`/w/${workspace.id}/analytics?automation=${item.id}`}>
                <BarChart3 size={14} /> View analytics
              </Link>
              <button
                type="button"
                className="danger"
                onClick={() => setDialog({ kind: "delete", item })}
              >
                <Trash2 size={14} /> Delete
              </button>
            </RowMenu>
          )}
        </div>
      </div>
    );
  };

  return (
    <div className="automations-page-container">
      {/* Page Header with List vs Templates Toggle */}
      <div className="automations-header-row">
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

        <div className="tab-pill-toggle" role="group" aria-label="Section">
          <button
            type="button"
            aria-pressed={tab === "list"}
            className={`pill-toggle-btn ${tab === "list" ? "active" : ""}`}
            onClick={() => setTab("list")}
          >
            List
          </button>
          <button
            type="button"
            aria-pressed={tab === "templates"}
            className={`pill-toggle-btn ${tab === "templates" ? "active" : ""}`}
            onClick={() => setTab("templates")}
          >
            Templates
          </button>
        </div>
      </div>

      <ErrorNotice error={feedback.error} />
      <SuccessNotice notice={feedback.notice} />

      {/* VIEW 1: AUTOMATIONS LIST (Matching Screenshot 5) */}
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
                  Upload and manage files, documents, and content that your AI agents can reference to provide accurate, context-aware responses to your customers.
                </p>
              </div>
            </Link>

            <Link href={`/w/${workspace.id}/integrations`} className="resource-card">
              <span className="resource-icon-wrap dark-grid">
                <Layers size={20} />
              </span>
              <div className="resource-card-text">
                <strong className="resource-title">Integrations</strong>
                <p className="resource-desc">
                  Connect your favorite tools and platforms to Nemio. Sync contacts, automate workflows, and extend your automation capabilities with powerful integrations.
                </p>
              </div>
            </Link>
          </div>

          {/* Search, filters, view & Create New */}
          <div className="automations-toolbar-row">
            <div className="search-input-wrapper">
              <Search size={16} className="search-icon" />
              <input
                type="search"
                placeholder="Search name, folder or keyword..."
                aria-label="Search automations"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="search-input-field"
              />
            </div>

            <div className="status-filter-pills" role="group" aria-label="Status">
              {STATUSES.map((option) => (
                <button
                  key={option.id}
                  type="button"
                  aria-pressed={status === option.id}
                  className={`filter-pill ${status === option.id ? "active" : ""}`}
                  onClick={() => setStatus(option.id)}
                >
                  {option.id === "live" && <span className="dot-green" />}
                  {option.id !== "all" && option.id !== "live" && (
                    <span className="dot-gray" />
                  )}
                  {option.label}
                </button>
              ))}
            </div>

            <select
              className="automations-channel-select"
              aria-label="Channel"
              value={channel}
              onChange={(event) => setChannel(event.target.value)}
            >
              <option value="all">All channels</option>
              {META_CHANNELS.map((provider) => (
                <option key={provider} value={provider}>
                  {channelLabel(provider)}
                </option>
              ))}
            </select>

            <div className="status-filter-pills" role="group" aria-label="View">
              <button
                type="button"
                aria-pressed={view === "list"}
                className={`filter-pill ${view === "list" ? "active" : ""}`}
                onClick={() => setView("list")}
              >
                <List size={14} /> List
              </button>
              <button
                type="button"
                aria-pressed={view === "folders"}
                className={`filter-pill ${view === "folders" ? "active" : ""}`}
                onClick={() => setView("folders")}
              >
                <Folder size={14} /> Folders
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
                  aria-expanded={showCreateMenu}
                  onClick={() => setShowCreateMenu(!showCreateMenu)}
                >
                  <Plus size={16} /> Create New
                </button>

                {showCreateMenu && (
                  <div className="choose-builder-popover">
                    <div className="choose-builder-header">CHOOSE HOW TO BUILD</div>

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
                          <span className="builder-option-name">Simple automation</span>
                          <span className="builder-easiest-pill">EASIEST</span>
                        </div>
                        <div className="builder-option-desc">
                          Guided, step-by-step. Perfect if you just want comment-to-DM.
                        </div>
                      </div>
                      <ChevronRight size={16} className="builder-option-chevron" />
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
                          <span className="builder-option-name">Advanced builder</span>
                        </div>
                        <div className="builder-option-desc">
                          Full canvas with triggers, branching and every node type.
                        </div>
                      </div>
                      <ChevronRight size={16} className="builder-option-chevron" />
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Automations Cards List (Matching Screenshot 5) */}
          <div className="automations-cards-stack">
            {loading ? (
              <p className="loading-text">Loading automations…</p>
            ) : !items.length ? (
              <Empty>
                No automations yet. Create one, start from a template or install
                one from the{" "}
                <Link href={`/w/${workspace.id}/templates`}>marketplace</Link>.
              </Empty>
            ) : !visible.length ? (
              <Empty>No automations match these filters.</Empty>
            ) : view === "folders" ? (
              groups.map((group) => (
                <details key={group.name || "unfiled"} className="folder-group" open>
                  <summary>
                    <Folder size={15} />
                    {group.name || "Unfiled"}
                    <span className="nav-count">{group.rows.length}</span>
                    <ChevronDown size={14} />
                  </summary>
                  <div className="automations-cards-stack">
                    {group.rows.map(row)}
                  </div>
                </details>
              ))
            ) : (
              visible.map(row)
            )}
          </div>

          <AutomationStarter workspaceId={workspace.id} prefix={prefix} />

          <Panel title="Recent runs" aside="Latest 100 conversation states">
            {runs.length ? (
              <Table head={["Automation", "Status", "Node", "Steps", "Error"]}>
                {runs.map((run) => (
                  <tr key={run.id}>
                    <td>{names[run.automation_id] || "Deleted"}</td>
                    <td>
                      <Pill tone={statusTone(run.status)}>{run.status}</Pill>
                    </td>
                    <td className="mono">{run.node_id}</td>
                    <td>{run.steps}</td>
                    <td className="muted-text">{run.error_code || "—"}</td>
                  </tr>
                ))}
              </Table>
            ) : (
              <Empty>Runs appear here once a flow fires.</Empty>
            )}
          </Panel>
        </div>
      )}

      {/* VIEW 2: TEMPLATES (Matching Screenshot 2) */}
      {tab === "templates" && (
        <div className="templates-catalog-view">
          {/* Top Hero Card: Speak To Generate A Workflow */}
          <div className="speak-to-generate-hero-card">
            <div className="hero-ghost-icon">
              <Sparkles size={34} />
            </div>
            <h2 className="hero-title">Speak to generate a workflow</h2>
            <p className="hero-desc">
              You describe the automation you want to build, and our AI will do it!
            </p>
            <form onSubmit={generate} className="voice-prompt-input-row">
              <span className="mic-round-btn" aria-hidden="true">
                <Mic size={16} />
              </span>
              <input
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
            </form>
          </div>

          {/* Ready-to-use templates: each opens in the builder as a disabled draft. */}
          <div className="templates-catalog-grid">
            {META_TEMPLATES.map((template) => (
              <div key={template.id} className="template-import-card">
                <div className="template-card-header">
                  <span className={`channel-badge-icon ${template.channel}`}>
                    <ChannelIcon provider={template.channel} size={18} />
                  </span>
                  <h3 className="template-card-title">{template.name}</h3>
                </div>
                <p className="template-card-desc">{template.summary}</p>
                <ol className="template-card-steps">
                  {template.steps.map((label) => (
                    <li key={label}>{label}</li>
                  ))}
                </ol>
                <button
                  type="button"
                  className="import-template-btn"
                  disabled={feedback.busy}
                  onClick={() => createFrom(template.name, template.graph)}
                >
                  Use template
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {dialog?.kind === "folder" && (
        <FolderDialog
          item={dialog.item}
          folders={folders}
          busy={feedback.busy}
          error={feedback.error}
          onSave={(folder) => moveToFolder(dialog.item, folder)}
          onClose={() => setDialog(null)}
        />
      )}
      {dialog?.kind === "transfer" && (
        <Modal title="Transfer automation" onClose={() => setDialog(null)}>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              const data = new FormData(event.currentTarget);
              transfer(
                dialog.item,
                String(data.get("workspace")),
                String(data.get("reason") || "").trim(),
              );
            }}
          >
            <p>
              “{dialog.item.name}” moves with its triggers and steps. It arrives
              paused, and conversations it is running here stop.
            </p>
            <ErrorNotice error={feedback.error} />
            <label>
              Destination workspace
              <select name="workspace" required>
                {destinations.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Reason
              <input
                name="reason"
                maxLength={300}
                required
                placeholder="e.g. Handing over to the client workspace"
              />
            </label>
            <button className="button primary" disabled={feedback.busy}>
              Transfer <ArrowRightLeft size={15} />
            </button>
          </form>
        </Modal>
      )}
      {dialog?.kind === "delete" && (
        <Modal title="Delete automation" onClose={() => setDialog(null)}>
          <p>
            Delete “{dialog.item.name}”? Its triggers stop at once and
            conversations it is running end. Analytics history is kept.
          </p>
          <ErrorNotice error={feedback.error} />
          <div className="button-row">
            <button
              className="button danger"
              disabled={feedback.busy}
              onClick={() => remove(dialog.item)}
            >
              Delete <Trash2 size={15} />
            </button>
            <button
              className="button secondary"
              onClick={() => setDialog(null)}
            >
              Cancel
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}

/** Row action menu: closes on outside click, Escape, or after choosing an item. */
function RowMenu({
  onClose,
  children,
}: {
  onClose: () => void;
  children: ReactNode;
}) {
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const close = (event: MouseEvent | KeyboardEvent) => {
      if (
        event instanceof KeyboardEvent
          ? event.key === "Escape"
          : !root.current?.parentElement?.contains(event.target as Node)
      )
        onClose();
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [onClose]);
  return (
    <div className="row-menu-list" ref={root} onClick={onClose}>
      {children}
    </div>
  );
}

function FolderDialog({
  item,
  folders,
  busy,
  error,
  onSave,
  onClose,
}: {
  item: Automation;
  folders: string[];
  busy: boolean;
  error: string;
  onSave: (folder: string) => void;
  onClose: () => void;
}) {
  return (
    <Modal title="Move to folder" onClose={onClose}>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          onSave(
            String(
              new FormData(event.currentTarget).get("folder") || "",
            ).trim(),
          );
        }}
      >
        <ErrorNotice error={error} />
        <label>
          Folder for “{item.name}”
          <input
            name="folder"
            list="automation-folders"
            defaultValue={item.folder}
            maxLength={60}
            placeholder="e.g. Instagram comment leads"
            autoFocus
          />
          <datalist id="automation-folders">
            {folders.map((name) => (
              <option key={name} value={name} />
            ))}
          </datalist>
          <small>Leave empty to remove it from its folder.</small>
        </label>
        <button className="button primary" disabled={busy}>
          Save
        </button>
      </form>
    </Modal>
  );
}
