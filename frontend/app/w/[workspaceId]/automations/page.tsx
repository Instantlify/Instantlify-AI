"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import {
  ArrowRightLeft,
  BarChart3,
  ChevronDown,
  Copy,
  Ellipsis,
  Folder,
  FolderInput,
  List,
  Pencil,
  Plus,
  Trash2,
} from "lucide-react";
import {
  api,
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
import { FlowGenerator } from "@/components/flow-generator";
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
  const feedback = useFeedback();

  useEffect(() => {
    if (!manager) {
      queueMicrotask(() => setLoading(false));
      return;
    }
    const controller = new AbortController();
    Promise.all([
      api<Page<Automation>>(
        `${prefix}/automations/`,
        "GET",
        undefined,
        controller.signal,
      ),
      api<AutomationRun[]>(
        `${prefix}/automation-runs/`,
        "GET",
        undefined,
        controller.signal,
      ),
      api<AutomationStats>(
        `${prefix}/automations/stats/`,
        "GET",
        undefined,
        controller.signal,
      ),
    ])
      .then(([page, states, counts]) => {
        setItems(page.results);
        setRuns(states);
        setStats(counts);
      })
      .catch((err) => {
        if (!controller.signal.aborted)
          feedback.setError((err as Error).message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefix, manager]);

  async function createFrom(name: string, draft: object) {
    await feedback.run(async () => {
      const created = await api<Automation>(`${prefix}/automations/`, "POST", {
        name,
        draft,
      });
      router.push(`/w/${workspace.id}/automations/${created.id}`);
    });
  }
  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const name = String(
      new FormData(event.currentTarget).get("name") || "",
    ).trim();
    await createFrom(name, STARTER_GRAPH);
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
    return (
      <tr key={item.id}>
        <td>
          <span
            className="platform-stack"
            aria-label={
              channels.map(channelLabel).join(", ") || "No trigger yet"
            }
          >
            {channels.length ? (
              channels.map((provider) => (
                <ChannelIcon key={provider} provider={provider} />
              ))
            ) : (
              <span className="muted-text">—</span>
            )}
          </span>
        </td>
        <td>
          <Link href={`/w/${workspace.id}/automations/${item.id}`}>
            <strong>{item.name}</strong>
          </Link>
          <span className="row-sub">
            {(graph?.triggers || [])
              .map(
                (trigger) =>
                  `${TRIGGER_LABELS[trigger.kind] ?? trigger.kind}: “${trigger.keyword}”`,
              )
              .join(" · ") || "No trigger yet"}
            {item.installed_from && " · from template"}
          </span>
        </td>
        <td className="small">
          {new Date(item.created_at).toLocaleDateString()}
        </td>
        <td className="num">{counts?.runs ?? 0}</td>
        <td className="num">{counts?.reach ?? 0}</td>
        <td>
          <label
            className="switch"
            title={item.published?.start ? undefined : "Publish the flow first"}
          >
            <input
              type="checkbox"
              role="switch"
              checked={item.enabled}
              disabled={feedback.busy || !item.published?.start}
              onChange={() => toggle(item)}
              aria-label={`${item.name} active`}
            />
            <span aria-hidden="true" />
          </label>
          <Pill
            tone={
              state === "live"
                ? "good"
                : state === "paused"
                  ? "warn"
                  : "neutral"
            }
          >
            {state}
          </Pill>
        </td>
        <td className="row-menu">
          <button
            className="icon-button"
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
              <button onClick={() => duplicate(item)}>
                <Copy size={14} /> Duplicate
              </button>
              <button onClick={() => setDialog({ kind: "folder", item })}>
                <FolderInput size={14} /> Move to folder
              </button>
              <button
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
                className="danger"
                onClick={() => setDialog({ kind: "delete", item })}
              >
                <Trash2 size={14} /> Delete
              </button>
            </RowMenu>
          )}
        </td>
      </tr>
    );
  };

  return (
    <>
      <PageHeading
        eyebrow="Automations"
        title="Reply to every comment, automatically."
        text="Keyword triggers on Instagram comments, story replies, Facebook Page comments and WhatsApp messages run a visual flow."
      />
      <ErrorNotice error={feedback.error} />
      <SuccessNotice notice={feedback.notice} />
      <div className="stack">
        <FlowGenerator workspaceId={workspace.id} prefix={prefix} />
        <Panel title="Meta workflow templates" aside="Opens as a draft">
          <div className="template-grid">
            {META_TEMPLATES.map((template) => (
              <article key={template.id} className="template-card">
                <header>
                  <ChannelIcon provider={template.channel} size={16} />
                  <strong>{template.name}</strong>
                </header>
                <p>{template.summary}</p>
                <ol>
                  {template.steps.map((label) => (
                    <li key={label}>{label}</li>
                  ))}
                </ol>
                <button
                  className="button secondary small"
                  disabled={feedback.busy}
                  onClick={() => createFrom(template.name, template.graph)}
                >
                  Use template <Plus size={14} />
                </button>
              </article>
            ))}
          </div>
        </Panel>
        <Panel title="Your flows" aside={`${items.length} automation(s)`}>
          <form
            onSubmit={create}
            className="invite-form"
            style={{ marginBottom: 18 }}
          >
            <label>
              New automation
              <input
                name="name"
                placeholder="e.g. Pricing comment → DM"
                maxLength={100}
                required
              />
            </label>
            <button className="button primary" disabled={feedback.busy}>
              Create <Plus size={16} />
            </button>
          </form>
          <div className="list-toolbar">
            <input
              type="search"
              placeholder="Search name, folder or keyword"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              aria-label="Search automations"
            />
            <div className="chip-row" role="group" aria-label="Status">
              {STATUSES.map((option) => (
                <button
                  key={option.id}
                  className={`chip ${status === option.id ? "on" : ""}`}
                  aria-pressed={status === option.id}
                  onClick={() => setStatus(option.id)}
                >
                  {option.label}
                </button>
              ))}
            </div>
            <div className="chip-row" role="group" aria-label="Channel">
              <button
                className={`chip ${channel === "all" ? "on" : ""}`}
                aria-pressed={channel === "all"}
                onClick={() => setChannel("all")}
              >
                All channels
              </button>
              {META_CHANNELS.map((provider) => (
                <button
                  key={provider}
                  className={`chip ${channel === provider ? "on" : ""}`}
                  aria-pressed={channel === provider}
                  onClick={() => setChannel(provider)}
                >
                  <ChannelIcon provider={provider} size={12} />
                  {channelLabel(provider)}
                </button>
              ))}
            </div>
            <div className="segmented" role="group" aria-label="View">
              <button
                aria-pressed={view === "list"}
                className={view === "list" ? "on" : ""}
                onClick={() => setView("list")}
              >
                <List size={14} /> List
              </button>
              <button
                aria-pressed={view === "folders"}
                className={view === "folders" ? "on" : ""}
                onClick={() => setView("folders")}
              >
                <Folder size={14} /> Folders
              </button>
            </div>
          </div>
          {loading ? (
            <p className="loading-text">Loading automations…</p>
          ) : !items.length ? (
            <Empty>
              No automations yet. Generate one, start from a template or install
              one from the{" "}
              <Link href={`/w/${workspace.id}/templates`}>marketplace</Link>.
            </Empty>
          ) : !visible.length ? (
            <Empty>No automations match these filters.</Empty>
          ) : (
            groups.map((group) => (
              <details
                key={group.name || "unfiled"}
                className={view === "folders" ? "folder-group" : "folder-flat"}
                open
              >
                {view === "folders" && (
                  <summary>
                    <Folder size={15} />
                    {group.name || "Unfiled"}
                    <span className="nav-count">{group.rows.length}</span>
                    <ChevronDown size={14} />
                  </summary>
                )}
                <Table
                  head={[
                    "Channel",
                    "Automation",
                    "Created",
                    "Runs",
                    "Reach",
                    "Active",
                    "",
                  ]}
                >
                  {group.rows.map(row)}
                </Table>
              </details>
            ))
          )}
        </Panel>
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
    </>
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
