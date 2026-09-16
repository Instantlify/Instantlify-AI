"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";
import { Plus } from "lucide-react";
import { api, type Automation, type AutomationRun, type Page } from "@/lib/api";
import { useWorkspace } from "@/lib/workspace";
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

export default function AutomationsPage() {
  const { workspace, prefix, manager } = useWorkspace();
  const router = useRouter();
  const [items, setItems] = useState<Automation[]>([]);
  const [runs, setRuns] = useState<AutomationRun[]>([]);
  const [loading, setLoading] = useState(true);
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
    ])
      .then(([page, states]) => {
        setItems(page.results);
        setRuns(states);
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

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const name = String(
      new FormData(event.currentTarget).get("name") || "",
    ).trim();
    await feedback.run(async () => {
      const created = await api<Automation>(`${prefix}/automations/`, "POST", {
        name,
        draft: STARTER_GRAPH,
      });
      router.push(`/w/${workspace.id}/automations/${created.id}`);
    });
  }
  async function toggle(item: Automation) {
    await feedback.run(
      async () => {
        const updated = await api<Automation>(
          `${prefix}/automations/${item.id}/`,
          "PATCH",
          {
            enabled: !item.enabled,
          },
        );
        setItems((list) =>
          list.map((row) => (row.id === updated.id ? updated : row)),
        );
      },
      item.enabled ? "Automation paused." : "Automation enabled.",
    );
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
  const names = Object.fromEntries(items.map((item) => [item.id, item.name]));
  return (
    <>
      <PageHeading
        eyebrow="Automations"
        title="Reply to every comment, automatically."
        text="Keyword triggers on comments, story replies and DMs run a visual flow: messages, buttons, waits, conditions."
      />
      <ErrorNotice error={feedback.error} />
      <SuccessNotice notice={feedback.notice} />
      <div className="stack">
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
          {loading ? (
            <p className="loading-text">Loading automations…</p>
          ) : items.length ? (
            <Table
              head={["Name", "Triggers", "Status", "Revision", "Updated", ""]}
            >
              {items.map((item) => {
                const graph = item.published?.triggers?.length
                  ? item.published
                  : item.draft;
                return (
                  <tr key={item.id}>
                    <td>
                      <Link href={`/w/${workspace.id}/automations/${item.id}`}>
                        <strong>{item.name}</strong>
                      </Link>
                      {item.installed_from && (
                        <span className="muted-text"> · from template</span>
                      )}
                    </td>
                    <td className="small">
                      {(graph?.triggers || [])
                        .map(
                          (trigger) => `${trigger.kind}: “${trigger.keyword}”`,
                        )
                        .join(", ") || "—"}
                    </td>
                    <td>
                      <Pill
                        tone={
                          item.enabled
                            ? "good"
                            : item.published?.start
                              ? "warn"
                              : "neutral"
                        }
                      >
                        {item.enabled
                          ? "live"
                          : item.published?.start
                            ? "paused"
                            : "draft"}
                      </Pill>
                    </td>
                    <td>{item.revision}</td>
                    <td className="small">
                      {new Date(item.updated_at).toLocaleString()}
                    </td>
                    <td>
                      {item.published?.start && (
                        <button
                          className="text-button"
                          disabled={feedback.busy}
                          onClick={() => toggle(item)}
                        >
                          {item.enabled ? "Pause" : "Enable"}
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </Table>
          ) : (
            <Empty>
              No automations yet. Create one above or install a template from
              the <Link href={`/w/${workspace.id}/templates`}>marketplace</Link>
              .
            </Empty>
          )}
        </Panel>
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
    </>
  );
}
