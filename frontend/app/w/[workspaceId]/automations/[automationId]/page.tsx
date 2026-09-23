"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  addEdge,
  Background,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  useEdgesState,
  useNodesState,
  type Connection as FlowConnection,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import {
  ArrowLeft,
  Clock,
  Flag,
  GitFork,
  Hourglass,
  MessageSquare,
  MousePointerClick,
  Plus,
  Rocket,
  Save,
  Trash2,
} from "lucide-react";
import {
  api,
  type Automation,
  type FlowButton,
  type FlowGraph,
  type FlowNodeData,
  type NodeKind,
} from "@/lib/api";
import { useWorkspace } from "@/lib/workspace";
import { ErrorNotice, Pill, SuccessNotice, useFeedback } from "@/components/ui";
import { TourMarker } from "@/components/growth";

type FlowNode = Node<
  FlowNodeData & { isStart?: boolean; label?: string },
  "flow"
>;

const KINDS: {
  kind: NodeKind;
  label: string;
  icon: typeof MessageSquare;
  hint: string;
}[] = [
  {
    kind: "send_message",
    label: "Send message",
    icon: MessageSquare,
    hint: "A text reply",
  },
  {
    kind: "send_buttons",
    label: "Send buttons",
    icon: MousePointerClick,
    hint: "Text + up to 3 link buttons",
  },
  {
    kind: "wait",
    label: "Wait for reply",
    icon: Hourglass,
    hint: "Pause until the lead answers",
  },
  {
    kind: "condition",
    label: "Condition",
    icon: GitFork,
    hint: "Branch on a saved answer",
  },
  {
    kind: "delay",
    label: "Delay",
    icon: Clock,
    hint: "Wait a number of seconds",
  },
  { kind: "end", label: "End", icon: Flag, hint: "Finish the flow" },
];
const TRIGGER_KINDS = ["comment", "dm", "story_reply", "live_comment"];

function summary(data: FlowNodeData) {
  switch (data.kind) {
    case "send_message":
    case "send_buttons":
      return data.text || "Empty message";
    case "wait":
      return `Saves the reply as {{${data.variable || "reply"}}}`;
    case "condition":
    case "branch":
      return `{{${data.variable || "last_text"}}} equals “${data.equals ?? ""}”`;
    case "delay":
      return `${data.seconds || 0} seconds`;
    default:
      return "Flow ends here";
  }
}

function FlowNodeView({ data, selected }: NodeProps<FlowNode>) {
  const meta = KINDS.find((item) => item.kind === data.kind) || KINDS[0];
  const Icon = meta.icon;
  const branching = data.kind === "condition" || data.kind === "branch";
  return (
    <div
      className={`flow-node ${selected ? "selected" : ""} ${data.isStart ? "start" : ""}`}
    >
      <Handle type="target" position={Position.Top} />
      <header>
        <Icon size={14} />
        {meta.label}
      </header>
      <p>{summary(data)}</p>
      {branching ? (
        <>
          <Handle
            type="source"
            position={Position.Bottom}
            id="true"
            style={{ left: "30%" }}
          />
          <span className="handle-label" style={{ left: "22%", bottom: -14 }}>
            yes
          </span>
          <Handle
            type="source"
            position={Position.Bottom}
            id="false"
            style={{ left: "70%" }}
          />
          <span className="handle-label" style={{ left: "66%", bottom: -14 }}>
            no
          </span>
        </>
      ) : (
        data.kind !== "end" && (
          <Handle type="source" position={Position.Bottom} />
        )
      )}
    </div>
  );
}
const nodeTypes = { flow: FlowNodeView };

/** Deterministic, readable IDs: send_message-1, send_message-2, … */
function newNodeId(kind: NodeKind, taken: string[]) {
  let index = taken.length + 1;
  while (taken.includes(`${kind}-${index}`)) index += 1;
  return `${kind}-${index}`;
}

function toFlow(graph: Partial<FlowGraph>) {
  const start = graph.start;
  const nodes: FlowNode[] = (graph.nodes || []).map((node, index) => ({
    id: node.id,
    type: "flow",
    position: node.position || {
      x: 80 + (index % 3) * 260,
      y: 80 + Math.floor(index / 3) * 170,
    },
    data: { ...node.data, isStart: node.id === start },
  }));
  const edges: Edge[] = (graph.edges || []).map((edge) => ({
    id: edge.id || `${edge.source}-${edge.target}-${edge.sourceHandle || ""}`,
    source: edge.source,
    target: edge.target,
    sourceHandle: edge.sourceHandle || undefined,
    label:
      edge.sourceHandle === "true"
        ? "yes"
        : edge.sourceHandle === "false"
          ? "no"
          : undefined,
  }));
  return { nodes, edges };
}

function toGraph(
  nodes: FlowNode[],
  edges: Edge[],
  start: string,
  triggers: FlowGraph["triggers"],
): FlowGraph {
  return {
    start,
    triggers,
    nodes: nodes.map((node) => {
      const data = { ...node.data };
      delete data.isStart;
      delete data.label;
      return {
        id: node.id,
        position: node.position,
        data: data as FlowNodeData,
      };
    }),
    edges: edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      ...(edge.sourceHandle ? { sourceHandle: edge.sourceHandle } : {}),
    })),
  };
}

export default function BuilderPage() {
  const { workspace, prefix } = useWorkspace();
  const { automationId } = useParams<{ automationId: string }>();
  const [automation, setAutomation] = useState<Automation | null>(null);
  const [nodes, setNodes, onNodesChange] = useNodesState<FlowNode>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [start, setStart] = useState("");
  const [triggers, setTriggers] = useState<FlowGraph["triggers"]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const feedback = useFeedback();

  useEffect(() => {
    const controller = new AbortController();
    api<Automation>(
      `${prefix}/automations/${automationId}/`,
      "GET",
      undefined,
      controller.signal,
    )
      .then((item) => {
        setAutomation(item);
        const graph = item.draft?.nodes?.length ? item.draft : item.published;
        const flow = toFlow(graph || {});
        setNodes(flow.nodes);
        setEdges(flow.edges);
        setStart(graph?.start || flow.nodes[0]?.id || "");
        setTriggers(graph?.triggers || [{ kind: "comment", keyword: "" }]);
      })
      .catch((err) => {
        if (!controller.signal.aborted)
          feedback.setError((err as Error).message);
      });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefix, automationId]);

  useEffect(() => {
    setNodes((list) =>
      list.map((node) =>
        node.data.isStart === (node.id === start)
          ? node
          : { ...node, data: { ...node.data, isStart: node.id === start } },
      ),
    );
  }, [start, setNodes]);

  const selected = nodes.find((node) => node.id === selectedId) || null;
  const graph = useMemo(
    () => toGraph(nodes, edges, start, triggers),
    [nodes, edges, start, triggers],
  );

  const onConnect = useCallback(
    (connection: FlowConnection) => {
      setEdges((list) => {
        // One outgoing edge per handle keeps the graph valid for the engine.
        const filtered = list.filter(
          (edge) =>
            !(
              edge.source === connection.source &&
              (edge.sourceHandle || null) === (connection.sourceHandle || null)
            ),
        );
        return addEdge(
          {
            ...connection,
            id: `${connection.source}-${connection.target}-${connection.sourceHandle || ""}-${Date.now()}`,
            label:
              connection.sourceHandle === "true"
                ? "yes"
                : connection.sourceHandle === "false"
                  ? "no"
                  : undefined,
          },
          filtered,
        );
      });
      setDirty(true);
    },
    [setEdges],
  );

  function addNode(kind: NodeKind) {
    const id = newNodeId(
      kind,
      nodes.map((node) => node.id),
    );
    const data: FlowNodeData =
      kind === "send_message"
        ? { kind, text: "Hello! Thanks for reaching out." }
        : kind === "send_buttons"
          ? {
              kind,
              text: "Here you go:",
              buttons: [{ type: "web_url", url: "https://", title: "Open" }],
            }
          : kind === "wait"
            ? { kind, variable: "reply" }
            : kind === "condition"
              ? { kind, variable: "reply", equals: "yes" }
              : kind === "delay"
                ? { kind, seconds: 60 }
                : { kind };
    const last = nodes[nodes.length - 1];
    setNodes((list) => [
      ...list,
      {
        id,
        type: "flow",
        position: {
          x: (last?.position.x ?? 60) + 40,
          y: (last?.position.y ?? 40) + 150,
        },
        data: { ...data, isStart: !list.length },
      },
    ]);
    if (!nodes.length) setStart(id);
    setSelectedId(id);
    setDirty(true);
  }
  function updateSelected(patch: Partial<FlowNodeData>) {
    if (!selected) return;
    setNodes((list) =>
      list.map((node) =>
        node.id === selected.id
          ? { ...node, data: { ...node.data, ...patch } }
          : node,
      ),
    );
    setDirty(true);
  }
  function removeSelected() {
    if (!selected) return;
    setNodes((list) => list.filter((node) => node.id !== selected.id));
    setEdges((list) =>
      list.filter(
        (edge) => edge.source !== selected.id && edge.target !== selected.id,
      ),
    );
    if (start === selected.id)
      setStart(nodes.find((node) => node.id !== selected.id)?.id || "");
    setSelectedId(null);
    setDirty(true);
  }
  async function save() {
    await feedback.run(async () => {
      const updated = await api<Automation>(
        `${prefix}/automations/${automationId}/`,
        "PATCH",
        {
          draft: graph,
        },
      );
      setAutomation(updated);
      setDirty(false);
    }, "Draft saved.");
  }
  async function publish() {
    await feedback.run(async () => {
      await api<Automation>(`${prefix}/automations/${automationId}/`, "PATCH", {
        draft: graph,
      });
      const updated = await api<Automation>(
        `${prefix}/automations/${automationId}/publish/`,
        "POST",
        {
          graph,
        },
      );
      setAutomation(updated);
      setDirty(false);
    }, "Published. The flow is live on matching triggers.");
  }
  const buttons = selected?.data.buttons || [];
  function setButtons(next: FlowButton[]) {
    updateSelected({ buttons: next });
  }

  return (
    <>
      <TourMarker workspaceId={workspace.id} step="editor" />
      <div className="page-heading">
        <div>
          <span className="eyebrow">
            <Link
              href={`/w/${workspace.id}/automations`}
              className="text-button"
            >
              <ArrowLeft size={13} /> AUTOMATIONS
            </Link>
          </span>
          <h1>{automation?.name || "Flow builder"}</h1>
          <p>
            Drag nodes, connect them top-to-bottom, set the start node and
            keyword triggers, then publish.
          </p>
        </div>
        <div className="row">
          {automation && (
            <Pill
              tone={
                automation.enabled
                  ? "good"
                  : automation.published?.start
                    ? "warn"
                    : "neutral"
              }
            >
              {automation.enabled
                ? "live"
                : automation.published?.start
                  ? "paused"
                  : "draft"}
              {dirty ? " · unsaved" : ""}
            </Pill>
          )}
          <button
            className="button secondary small"
            onClick={save}
            disabled={feedback.busy}
          >
            <Save size={14} /> Save draft
          </button>
          <button
            className="button primary small"
            onClick={publish}
            disabled={feedback.busy}
          >
            <Rocket size={14} /> Publish
          </button>
        </div>
      </div>
      <ErrorNotice error={feedback.error} />
      <SuccessNotice notice={feedback.notice} />
      <div className="builder">
        <aside className="builder-side">
          <strong className="small">Add a step</strong>
          {KINDS.map(({ kind, label, icon: Icon, hint }) => (
            <button
              key={kind}
              className="palette-button"
              onClick={() => addNode(kind)}
              title={hint}
            >
              <Icon size={15} /> {label}
            </button>
          ))}
          <strong className="small" style={{ marginTop: 10 }}>
            Triggers
          </strong>
          {triggers.map((trigger, index) => (
            <div key={index} className="form-grid" style={{ gap: 6 }}>
              <select
                aria-label="Trigger kind"
                value={trigger.kind}
                onChange={(event) => {
                  const next = [...triggers];
                  next[index] = { ...trigger, kind: event.target.value };
                  setTriggers(next);
                  setDirty(true);
                }}
              >
                {TRIGGER_KINDS.map((kind) => (
                  <option key={kind} value={kind}>
                    {kind.replace("_", " ")}
                  </option>
                ))}
              </select>
              <div className="row" style={{ flexWrap: "nowrap" }}>
                <input
                  aria-label="Keyword"
                  placeholder="keyword"
                  maxLength={100}
                  value={trigger.keyword}
                  onChange={(event) => {
                    const next = [...triggers];
                    next[index] = { ...trigger, keyword: event.target.value };
                    setTriggers(next);
                    setDirty(true);
                  }}
                  style={{
                    width: "100%",
                    padding: "8px 10px",
                    border: "1px solid var(--line)",
                    borderRadius: 7,
                  }}
                />
                <button
                  className="icon-button"
                  aria-label="Remove trigger"
                  onClick={() => {
                    setTriggers(triggers.filter((_, i) => i !== index));
                    setDirty(true);
                  }}
                >
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
          ))}
          {triggers.length < 20 && (
            <button
              className="text-button"
              onClick={() => {
                setTriggers([...triggers, { kind: "comment", keyword: "" }]);
                setDirty(true);
              }}
            >
              <Plus size={14} /> Add trigger
            </button>
          )}
          <p className="muted-text">
            Keywords match whole words, case-insensitively. Comment triggers
            reply privately to the comment first.
          </p>
        </aside>
        <div className="builder-canvas">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            onNodesChange={(changes) => {
              onNodesChange(changes);
              if (
                changes.some(
                  (change) =>
                    change.type === "position" || change.type === "remove",
                )
              )
                setDirty(true);
            }}
            onEdgesChange={(changes) => {
              onEdgesChange(changes);
              setDirty(true);
            }}
            onConnect={onConnect}
            onNodeClick={(_, node) => setSelectedId(node.id)}
            onPaneClick={() => setSelectedId(null)}
            fitView
            deleteKeyCode={["Backspace", "Delete"]}
          >
            <Background gap={18} />
            <Controls />
            <MiniMap pannable zoomable />
          </ReactFlow>
        </div>
        <aside className="builder-side right">
          {selected ? (
            <>
              <div className="row between">
                <strong className="small">
                  {
                    KINDS.find((item) => item.kind === selected.data.kind)
                      ?.label
                  }
                </strong>
                <button
                  className="icon-button"
                  aria-label="Delete step"
                  onClick={removeSelected}
                >
                  <Trash2 size={15} />
                </button>
              </div>
              <label className="field inline">
                <input
                  type="radio"
                  name="start"
                  checked={start === selected.id}
                  onChange={() => {
                    setStart(selected.id);
                    setDirty(true);
                  }}
                />
                Start the flow here
              </label>
              {(selected.data.kind === "send_message" ||
                selected.data.kind === "send_buttons") && (
                <label className="field">
                  Message{" "}
                  <span className="hint">
                    Use {"{{reply}}"} or any saved variable; {"{{last_text}}"}{" "}
                    is the triggering message.
                  </span>
                  <textarea
                    value={selected.data.text || ""}
                    maxLength={2000}
                    onChange={(event) =>
                      updateSelected({ text: event.target.value })
                    }
                  />
                </label>
              )}
              {selected.data.kind === "send_buttons" && (
                <div className="field">
                  Buttons{" "}
                  <span className="hint">
                    1–3 HTTPS links, titles up to 20 characters
                  </span>
                  {buttons.map((button, index) => (
                    <div key={index} className="form-grid" style={{ gap: 6 }}>
                      <input
                        placeholder="Title"
                        maxLength={20}
                        value={button.title}
                        onChange={(event) => {
                          const next = [...buttons];
                          next[index] = {
                            ...button,
                            title: event.target.value,
                          };
                          setButtons(next);
                        }}
                      />
                      <input
                        placeholder="https://"
                        value={button.url}
                        onChange={(event) => {
                          const next = [...buttons];
                          next[index] = { ...button, url: event.target.value };
                          setButtons(next);
                        }}
                      />
                      {buttons.length > 1 && (
                        <button
                          className="text-button"
                          onClick={() =>
                            setButtons(buttons.filter((_, i) => i !== index))
                          }
                        >
                          Remove button
                        </button>
                      )}
                    </div>
                  ))}
                  {buttons.length < 3 && (
                    <button
                      className="text-button"
                      onClick={() =>
                        setButtons([
                          ...buttons,
                          { type: "web_url", url: "https://", title: "Open" },
                        ])
                      }
                    >
                      <Plus size={14} /> Add button
                    </button>
                  )}
                </div>
              )}
              {selected.data.kind === "wait" && (
                <label className="field">
                  Save the reply as{" "}
                  <span className="hint">
                    variable name, e.g. reply or answer
                  </span>
                  <input
                    value={selected.data.variable || ""}
                    maxLength={40}
                    onChange={(event) =>
                      updateSelected({ variable: event.target.value })
                    }
                  />
                </label>
              )}
              {(selected.data.kind === "condition" ||
                selected.data.kind === "branch") && (
                <>
                  <label className="field">
                    Variable to check
                    <input
                      value={selected.data.variable || ""}
                      maxLength={40}
                      onChange={(event) =>
                        updateSelected({ variable: event.target.value })
                      }
                    />
                  </label>
                  <label className="field">
                    Equals{" "}
                    <span className="hint">
                      case-insensitive; “yes” edge when it matches
                    </span>
                    <input
                      value={selected.data.equals || ""}
                      maxLength={200}
                      onChange={(event) =>
                        updateSelected({ equals: event.target.value })
                      }
                    />
                  </label>
                </>
              )}
              {selected.data.kind === "delay" && (
                <label className="field">
                  Seconds <span className="hint">1–86400</span>
                  <input
                    type="number"
                    min={1}
                    max={86400}
                    value={selected.data.seconds || 0}
                    onChange={(event) =>
                      updateSelected({ seconds: Number(event.target.value) })
                    }
                  />
                </label>
              )}
              <p className="muted-text">
                Step ID: <span className="mono">{selected.id}</span>
              </p>
            </>
          ) : (
            <>
              <strong className="small">Flow rules</strong>
              <p className="muted-text">
                Every step except End needs exactly one outgoing connection;
                conditions need a “yes” and a “no”. No loops — use “Wait for
                reply” to continue a conversation. Each lead runs a flow at most
                once per hour.
              </p>
              <p className="muted-text">
                {nodes.length} step(s) · {edges.length} connection(s) · start:{" "}
                <span className="mono">{start || "—"}</span>
              </p>
            </>
          )}
        </aside>
      </div>
    </>
  );
}
