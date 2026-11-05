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
  ImagePlus,
  Mic,
  Phone,
  Video,
  MessageSquare,
  MousePointerClick,
  Plus,
  Rocket,
  Save,
  Trash2,
  Undo2,
  Redo2,
  Copy,
  ClipboardPaste,
  Sparkles,
  Users,
} from "lucide-react";
import {
  api,
  apiPages,
  type Automation,
  type Connection,
  type Member,
  type Integration,
  type PlatformModel,
  type FlowButton,
  type FlowGraph,
  type FlowNodeData,
  type NodeKind,
} from "@/lib/api";
import { useWorkspace } from "@/lib/workspace";
import { channelLabel } from "@/lib/channels";
import { KIND_CHANNELS, TRIGGER_LABELS } from "@/lib/meta-templates";
import { ErrorNotice, Pill, SuccessNotice, useFeedback } from "@/components/ui";
import { TourMarker } from "@/components/growth";
import { firstReplyStep } from "@/lib/growth";
import { useGraphHistory } from "@/lib/use-graph-history";
import { FlowTools } from "@/components/flow-tools";

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
    kind: "avatar_video",
    label: "Avatar video",
    icon: Video,
    hint: "Generate a HeyGen avatar video, wait for rendering and send it privately",
  },
  {
    kind: "ai_call",
    label: "AI phone call",
    icon: Phone,
    hint: "Call with a saved Vapi or Retell agent after the customer privately requests a call",
  },
  {
    kind: "generate_voice",
    label: "Generate voice",
    icon: Mic,
    hint: "Synthesize a voice message with a connected voice provider",
  },
  {
    kind: "follow_gate",
    label: "Verify Instagram follow",
    icon: Users,
    hint: "Require a private reply and a provider-verified follow before continuing",
  },
  {
    kind: "send_reminder",
    label: "Click reminder",
    icon: Clock,
    hint: "Follow up only if a tracked resource has not been clicked; add a delay before this step",
  },
  {
    kind: "ai_generate",
    label: "Generate with AI",
    icon: Sparkles,
    hint: "Save an AI response for a later message or action",
  },
  {
    kind: "ai_extract",
    label: "Extract with AI",
    icon: Sparkles,
    hint: "Extract named fields from a conversation",
  },
  {
    kind: "ai_condition",
    label: "AI condition",
    icon: GitFork,
    hint: "Choose a path using AI instructions",
  },
  {
    kind: "send_media",
    label: "Send media",
    icon: ImagePlus,
    hint: "Send a photo, video or audio file",
  },
  {
    kind: "start_agent",
    label: "Start AI assistant",
    icon: MessageSquare,
    hint: "Hand the private conversation to your configured AI assistant",
  },
  {
    kind: "integration_action",
    label: "Run integration",
    icon: Rocket,
    hint: "Sync this contact to a CRM or send a Slack notification",
  },
  {
    kind: "set_field",
    label: "Set custom field",
    icon: Flag,
    hint: "Save a value or a captured reply on the contact",
  },
  {
    kind: "set_stage",
    label: "Set contact stage",
    icon: Flag,
    hint: "Move the contact through your pipeline",
  },
  {
    kind: "randomizer",
    label: "Random path",
    icon: GitFork,
    hint: "Split contacts between two weighted paths",
  },
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
  {
    kind: "capture_email",
    label: "Collect email",
    icon: MessageSquare,
    hint: "Wait for a valid email and save it to the contact",
  },
  {
    kind: "add_tag",
    label: "Add contact tag",
    icon: Flag,
    hint: "Apply a tag to the contact",
  },
  {
    kind: "assign_member",
    label: "Assign teammate",
    icon: Flag,
    hint: "Assign the conversation to a workspace member",
  },
  {
    kind: "transfer",
    label: "Continue automation",
    icon: GitFork,
    hint: "Continue in another enabled automation",
  },
  { kind: "end", label: "End", icon: Flag, hint: "Finish the flow" },
];
const TRIGGER_KINDS = ["comment", "dm", "story_reply", "live_comment"];

function summary(data: FlowNodeData) {
  switch (data.kind) {
    case "follow_gate":
      return data.text || "Wait for a verified Instagram follow";
    case "send_reminder":
      return data.text || "Remind only if the resource has not been clicked";
    case "ai_generate":
    case "ai_extract":
    case "ai_condition":
      return data.prompt || "Add AI instructions";
    case "send_media":
      return `${data.media_type || "image"}: ${data.media_url || "Choose a media URL"}`;
    case "start_agent":
      return "Continue with the workspace AI assistant";
    case "integration_action":
      return data.operation === "notify"
        ? "Send a Slack notification"
        : "Sync the contact to a connected CRM";
    case "set_field":
      return data.field
        ? `${data.field}: ${data.value || "(empty)"}`
        : "Choose a custom field";
    case "set_stage":
      return `Move to ${data.stage || "new"}`;
    case "randomizer":
      return `Path A: ${data.percentage ?? 50}% · Path B: ${100 - (data.percentage ?? 50)}%`;
    case "send_message":
    case "send_buttons":
      return data.text || "Empty message";
    case "capture_email":
      return "Wait for a valid email address";
    case "add_tag":
      return data.tag ? `Tag: ${data.tag}` : "Choose a tag";
    case "assign_member":
      return data.user_id
        ? `Assign to member ${data.user_id}`
        : "Choose a teammate";
    case "transfer":
      return "Continue in the selected automation";
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
  const branching = [
    "condition",
    "branch",
    "randomizer",
    "ai_condition",
  ].includes(data.kind);
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
            {data.kind === "randomizer" ? "A" : "yes"}
          </span>
          <Handle
            type="source"
            position={Position.Bottom}
            id="false"
            style={{ left: "70%" }}
          />
          <span className="handle-label" style={{ left: "66%", bottom: -14 }}>
            {data.kind === "randomizer" ? "B" : "no"}
          </span>
        </>
      ) : (
        data.kind !== "end" &&
        data.kind !== "transfer" &&
        data.kind !== "start_agent" && (
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
      if (data.kind === "ai_extract")
        data.fields = (data.fields || [])
          .map((field) => field.trim())
          .filter(Boolean);
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
  const [connectionId, setConnectionId] = useState("");
  const [commentPostIds, setCommentPostIds] = useState<string[]>([]);
  const [commentReplies, setCommentReplies] = useState<string[]>([]);
  const [commentTarget, setCommentTarget] = useState<
    Pick<
      FlowGraph,
      "comment_post_mode" | "comment_since" | "resolved_next_post_id"
    >
  >({});
  const [connections, setConnections] = useState<Connection[]>([]);
  const [members, setMembers] = useState<Member[]>([]);
  const [otherFlows, setOtherFlows] = useState<Automation[]>([]);
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [aiModels, setAiModels] = useState<PlatformModel[]>([]);
  const [triggers, setTriggers] = useState<FlowGraph["triggers"]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [copiedStep, setCopiedStep] = useState<FlowNodeData | null>(null);
  const feedback = useFeedback();

  useEffect(() => {
    const controller = new AbortController();
    Promise.allSettled([
      api<PlatformModel[]>(
        `${prefix}/agent/models/`,
        "GET",
        undefined,
        controller.signal,
      ).then((value) => setAiModels(Array.isArray(value) ? value : [])),
      apiPages<Integration>(`${prefix}/integrations/`, controller.signal).then(
        setIntegrations,
      ),
      apiPages<Connection>(`${prefix}/connections/`, controller.signal).then(
        setConnections,
      ),
      apiPages<Member>(`${prefix}/members/`, controller.signal).then(
        setMembers,
      ),
      apiPages<Automation>(`${prefix}/automations/`, controller.signal).then(
        setOtherFlows,
      ),
    ]);
    return () => controller.abort();
  }, [prefix]);

  useEffect(() => {
    if (automationId === "new") {
      const defaultFlow: FlowGraph = {
        start: "1",
        triggers: [{ kind: "comment", keyword: "START" }],
        nodes: [
          {
            id: "1",
            position: { x: 100, y: 100 },
            data: {
              kind: "send_message",
              text: "Welcome! Here is your requested info.",
            },
          },
          { id: "done", position: { x: 100, y: 280 }, data: { kind: "end" } },
        ],
        edges: [{ source: "1", target: "done" }],
      };
      let active = true;
      queueMicrotask(() => {
        if (!active) return;
        setAutomation({
          id: "new",
          workspace: workspace.id,
          name: "New Automation",
          enabled: false,
          status: "draft",
          trigger: { kind: "keyword", keyword: "START", channel: "instagram" },
          draft: defaultFlow,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        } as unknown as Automation);
        const flow = toFlow(defaultFlow);
        setNodes(flow.nodes);
        setEdges(flow.edges);
        setStart("1");
        setConnectionId("");
        setCommentPostIds([]);
        setCommentReplies([]);
        setCommentTarget({});
        setTriggers(defaultFlow.triggers);
      });
      return () => {
        active = false;
      };
    }
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
        setConnectionId(graph?.connection_id || "");
        setCommentPostIds(graph?.comment_post_ids || []);
        setCommentReplies(graph?.comment_replies || []);
        setCommentTarget({
          comment_post_mode: graph?.comment_post_mode,
          comment_since: graph?.comment_since,
          resolved_next_post_id: item.published?.resolved_next_post_id,
        });
        setTriggers(graph?.triggers || [{ kind: "comment", keyword: "" }]);
      })
      .catch((err) => {
        if (!controller.signal.aborted)
          feedback.setError((err as Error).message);
      });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefix, automationId, workspace.id]);

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
    () => ({
      ...toGraph(nodes, edges, start, triggers),
      ...(connectionId ? { connection_id: connectionId } : {}),
      ...commentTarget,
      ...(commentPostIds.some((id) => id.trim())
        ? {
            comment_post_ids: commentPostIds
              .map((id) => id.trim())
              .filter(Boolean),
          }
        : {}),
      ...(commentReplies.length ? { comment_replies: commentReplies } : {}),
    }),
    [
      nodes,
      edges,
      start,
      triggers,
      connectionId,
      commentPostIds,
      commentReplies,
      commentTarget,
    ],
  );

  const restoreGraph = useCallback(
    (value: FlowGraph) => {
      const flow = toFlow(value);
      setNodes(flow.nodes);
      setEdges(flow.edges);
      setStart(value.start);
      setTriggers(value.triggers);
      setConnectionId(value.connection_id || "");
      setCommentPostIds(value.comment_post_ids || []);
      setCommentReplies(value.comment_replies || []);
      setCommentTarget({
        comment_post_mode: value.comment_post_mode,
        comment_since: value.comment_since,
        resolved_next_post_id: value.resolved_next_post_id,
      });
      setSelectedId(null);
      setDirty(true);
    },
    [setNodes, setEdges],
  );
  const history = useGraphHistory(automation?.id || "", graph, restoreGraph);

  function pasteStep(data = copiedStep) {
    if (!data || nodes.length >= 100) return;
    const id = newNodeId(
      data.kind,
      nodes.map((node) => node.id),
    );
    const last = selected || nodes[nodes.length - 1];
    const clean = structuredClone(data);
    delete (clean as FlowNode["data"]).isStart;
    delete (clean as FlowNode["data"]).label;
    setNodes((list) => [
      ...list,
      {
        id,
        type: "flow",
        position: {
          x: (last?.position.x || 80) + 50,
          y: (last?.position.y || 80) + 100,
        },
        data: clean,
      },
    ]);
    setSelectedId(id);
    setDirty(true);
  }

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
      kind === "avatar_video"
        ? { kind, integration_id: "", text: "", aspect_ratio: "auto" }
        : kind === "ai_call"
          ? {
              kind,
              integration_id: "",
              phone_variable: "phone",
              consent_reply: "Yes, call me",
              variable: "call_result",
              timezone: "UTC",
              weekdays: [0, 1, 2, 3, 4],
              call_start: "09:00",
              call_end: "18:00",
            }
          : kind === "generate_voice"
            ? { kind, text: "", integration_id: "" }
            : kind === "follow_gate"
              ? {
                  kind,
                  text: "Please follow this Instagram account, then tap below to continue.",
                  button_title: "I'm following",
                  expected_reply: `nemio:${automationId}:${id}`.slice(0, 64),
                }
              : ["ai_generate", "ai_extract", "ai_condition"].includes(kind)
                ? {
                    kind,
                    prompt: "",
                    variable: "ai_result",
                    ...(kind === "ai_extract"
                      ? { fields: ["name", "email"] }
                      : {}),
                  }
                : kind === "send_media"
                  ? { kind, media_type: "image", media_url: "" }
                  : kind === "integration_action"
                    ? {
                        kind,
                        operation: "sync_lead",
                        integration_id: "",
                        variable: "integration_result",
                      }
                    : kind === "set_field"
                      ? { kind, field: "", value: "" }
                      : kind === "set_stage"
                        ? { kind, stage: "new" }
                        : kind === "randomizer"
                          ? { kind, percentage: 50 }
                          : kind === "add_tag"
                            ? { kind, tag: "" }
                            : kind === "capture_email"
                              ? {
                                  kind,
                                  variable: "email",
                                  retry_text:
                                    "Please reply with a valid email address.",
                                }
                              : kind === "assign_member"
                                ? { kind, user_id: undefined }
                                : kind === "transfer"
                                  ? { kind, automation_id: "" }
                                  : kind === "send_message"
                                    ? {
                                        kind,
                                        text: "Hello! Thanks for reaching out.",
                                      }
                                    : kind === "send_buttons"
                                      ? {
                                          kind,
                                          text: "Here you go:",
                                          buttons: [
                                            {
                                              type: "web_url",
                                              url: "https://",
                                              title: "Open",
                                            },
                                          ],
                                        }
                                      : kind === "wait"
                                        ? { kind, variable: "reply" }
                                        : kind === "condition"
                                          ? {
                                              kind,
                                              variable: "reply",
                                              equals: "yes",
                                            }
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
      if (automationId === "new") {
        const created = await api<Automation>(
          `${prefix}/automations/`,
          "POST",
          {
            name: automation?.name || "New Automation",
            status: "draft",
            trigger: triggers?.[0] || {
              kind: "keyword",
              keyword: "START",
              channel: "instagram",
            },
            draft: graph,
          },
        );
        window.location.replace(`/w/${workspace.id}/automations/${created.id}`);
        return;
      }
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
      firstReplyStep(workspace.id, "published", true);
    }, "Published. The flow is live on matching triggers.");
  }
  async function pause() {
    await feedback.run(async () => {
      const updated = await api<Automation>(
        `${prefix}/automations/${automationId}/`,
        "PATCH",
        { enabled: false },
      );
      setAutomation(updated);
    }, "Automation paused.");
  }
  const boundConnection = connections.find((item) => item.id === graph.connection_id);
  const startStep = graph.nodes.find((node) => node.id === graph.start)?.data;
  const buttons = selected?.data.buttons || [];
  function setButtons(next: FlowButton[]) {
    updateSelected({ buttons: next });
  }

  return (
    <>
      <TourMarker workspaceId={workspace.id} step="editor" />
      <div className="page-heading workflow-heading">
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
            {graph.triggers.length
              ? `When ${TRIGGER_LABELS[graph.triggers[0].kind]?.toLowerCase() ?? graph.triggers[0].kind} matches ${graph.triggers[0].keyword === "*" ? "any text" : `“${graph.triggers[0].keyword}”`}, start with ${startStep?.kind.replaceAll("_", " ") || "the selected start step"}.`
              : "Add a trigger and choose the step that runs first."}
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
                ? "Live"
                : automation.published?.start
                  ? "Paused"
                  : "Draft"}
              {dirty ? " · unsaved" : ""}
            </Pill>
          )}
          {automation?.enabled && (
            <button className="button secondary small" onClick={pause} disabled={feedback.busy}>
              Pause automation
            </button>
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
      <details className="card" open style={{ padding: 14, marginBottom: 12 }}>
        <summary>Review before publishing</summary>
        <p>
          <strong>Account:</strong>{" "}
          {boundConnection
            ? `${boundConnection.display_name} · ${boundConnection.is_test ? "Test" : "Live"} · ${boundConnection.status.replaceAll("_", " ")}`
            : graph.connection_id
              ? "Selected account unavailable"
              : "Any connected account that matches a trigger"}
        </p>
        <ul>
          {graph.triggers.map((trigger, index) => (
            <li key={index}>
              {TRIGGER_LABELS[trigger.kind] ?? trigger.kind} ·{" "}
              {trigger.channel ? channelLabel(trigger.channel) : "Any supported channel"} ·{" "}
              {trigger.keyword === "*" ? "Any text" : `Keyword “${trigger.keyword}”`}
            </li>
          ))}
        </ul>
        <p>
          <strong>First step:</strong>{" "}
          {startStep?.text || startStep?.kind.replaceAll("_", " ") || "Choose a start step"}
        </p>
      </details>
      <div
        className="row"
        role="toolbar"
        aria-label="Workflow editing"
        style={{ gap: 8, flexWrap: "wrap", marginBottom: 12 }}
      >
        <FlowTools
          prefix={prefix}
          workspaceId={workspace.id}
          automationId={automationId}
          graph={graph}
          name={automation?.name || "Automation"}
          boundProvider={boundConnection?.provider}
        />
        <button
          className="button secondary small"
          disabled={!history.canUndo}
          onClick={history.undo}
        >
          <Undo2 size={14} /> Undo
        </button>
        <button
          className="button secondary small"
          disabled={!history.canRedo}
          onClick={history.redo}
        >
          <Redo2 size={14} /> Redo
        </button>
        <button
          className="button secondary small"
          disabled={!selected}
          onClick={() =>
            selected && setCopiedStep(structuredClone(selected.data))
          }
        >
          <Copy size={14} /> Copy step
        </button>
        <button
          className="button secondary small"
          disabled={!copiedStep || nodes.length >= 100}
          onClick={() => pasteStep()}
        >
          <ClipboardPaste size={14} /> Paste step
        </button>
        <button
          className="button secondary small"
          disabled={!selected || nodes.length >= 100}
          onClick={() => selected && pasteStep(selected.data)}
        >
          <Copy size={14} /> Duplicate step
        </button>
      </div>
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
                  const kind = event.target.value;
                  const next = [...triggers];
                  // A channel that cannot carry the new kind falls back to "any".
                  next[index] = {
                    ...trigger,
                    kind,
                    channel: KIND_CHANNELS[kind].includes(trigger.channel || "")
                      ? trigger.channel
                      : "",
                  };
                  setTriggers(next);
                  setDirty(true);
                }}
              >
                {TRIGGER_KINDS.map((kind) => (
                  <option key={kind} value={kind}>
                    {TRIGGER_LABELS[kind]}
                  </option>
                ))}
              </select>
              <select
                aria-label="Trigger channel"
                value={trigger.channel || ""}
                onChange={(event) => {
                  const next = [...triggers];
                  next[index] = { ...trigger, channel: event.target.value };
                  setTriggers(next);
                  setDirty(true);
                }}
              >
                <option value="">
                  {KIND_CHANNELS[trigger.kind]?.length > 1
                    ? "Any channel"
                    : `${channelLabel(KIND_CHANNELS[trigger.kind]?.[0] ?? "")} (only channel)`}
                </option>
                {KIND_CHANNELS[trigger.kind]?.length > 1 &&
                  KIND_CHANNELS[trigger.kind].map((provider) => (
                    <option key={provider} value={provider}>
                      {channelLabel(provider)} only
                    </option>
                  ))}
                {/* A channel set through the API (Telegram, LinkedIn) stays selectable. */}
                {trigger.channel &&
                  !(
                    KIND_CHANNELS[trigger.kind]?.length > 1 &&
                    KIND_CHANNELS[trigger.kind].includes(trigger.channel)
                  ) && (
                    <option value={trigger.channel}>
                      {channelLabel(trigger.channel)} only
                    </option>
                  )}
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
            Keywords match whole words, case-insensitively. Comment triggers on
            Instagram posts and Facebook Page posts reply privately to the
            comment first. WhatsApp supports message triggers only.
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
              {(selected.data.kind === "avatar_video" ||
                selected.data.kind === "generate_voice" ||
                selected.data.kind === "follow_gate" ||
                selected.data.kind === "send_reminder" ||
                selected.data.kind === "send_message" ||
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
              {selected.data.kind === "avatar_video" && (
                <div className="form-grid">
                  <label>
                    HeyGen integration
                    <select
                      aria-label="HeyGen integration"
                      value={selected.data.integration_id || ""}
                      onChange={(e) =>
                        updateSelected({ integration_id: e.target.value })
                      }
                    >
                      <option value="">
                        Choose a connected HeyGen account
                      </option>
                      {integrations
                        .filter(
                          (item) => item.enabled && item.provider === "heygen",
                        )
                        .map((item) => (
                          <option key={item.id} value={item.id}>
                            HeyGen{item.is_test ? " (local test)" : ""}
                          </option>
                        ))}
                    </select>
                  </label>
                  <label>
                    Avatar look ID (optional override)
                    <input
                      maxLength={200}
                      value={selected.data.avatar_id || ""}
                      onChange={(e) =>
                        updateSelected({ avatar_id: e.target.value })
                      }
                    />
                  </label>
                  <label>
                    Voice ID (optional override)
                    <input
                      maxLength={200}
                      value={selected.data.voice_id || ""}
                      onChange={(e) =>
                        updateSelected({ voice_id: e.target.value })
                      }
                    />
                  </label>
                  <label>
                    Aspect ratio
                    <select
                      aria-label="Aspect ratio"
                      value={selected.data.aspect_ratio || "auto"}
                      onChange={(e) =>
                        updateSelected({ aspect_ratio: e.target.value })
                      }
                    >
                      {["auto", "9:16", "16:9", "1:1"].map((value) => (
                        <option key={value}>{value}</option>
                      ))}
                    </select>
                  </label>
                  <small>
                    Requires a private reply and an open messaging window. Uses
                    the configured Digital Twin and voice; rendering stops for
                    review after 30 minutes.
                  </small>
                </div>
              )}
              {selected.data.kind === "ai_call" && (
                <div className="form-grid">
                  <label>
                    Calling integration
                    <select
                      aria-label="Calling integration"
                      value={selected.data.integration_id || ""}
                      onChange={(e) =>
                        updateSelected({ integration_id: e.target.value })
                      }
                    >
                      <option value="">Choose Vapi or Retell</option>
                      {integrations
                        .filter(
                          (item) =>
                            item.enabled &&
                            ["vapi", "retell"].includes(item.provider),
                        )
                        .map((item) => (
                          <option key={item.id} value={item.id}>
                            {item.provider}
                            {item.is_test ? " (local test)" : ""}
                          </option>
                        ))}
                    </select>
                  </label>
                  <label>
                    Phone variable
                    <input
                      value={selected.data.phone_variable || "phone"}
                      onChange={(e) =>
                        updateSelected({ phone_variable: e.target.value })
                      }
                    />
                    <small>
                      Capture a phone number such as +15550100200 in an earlier
                      reply step.
                    </small>
                  </label>
                  <label className="inline">
                    <input
                      type="checkbox"
                      checked={selected.data.wait_for_completion || false}
                      onChange={(e) =>
                        updateSelected({
                          wait_for_completion: e.target.checked,
                        })
                      }
                    />
                    Wait for call outcome before continuing
                  </label>
                  <small>
                    Stores the provider’s final status and summary in the call
                    result. Calls are created once; Nemio checks the outcome for
                    up to two hours.
                  </small>
                  <label>
                    Exact customer call request
                    <input
                      maxLength={64}
                      value={selected.data.consent_reply || ""}
                      onChange={(e) =>
                        updateSelected({ consent_reply: e.target.value })
                      }
                    />
                    <small>
                      Ask the customer to send this private reply immediately
                      before the call step.
                    </small>
                  </label>
                  <label>
                    Provider agent ID (optional override)
                    <input
                      maxLength={150}
                      value={selected.data.agent_id || ""}
                      onChange={(e) =>
                        updateSelected({ agent_id: e.target.value })
                      }
                    />
                  </label>
                  <label>
                    Timezone
                    <input
                      value={selected.data.timezone || "UTC"}
                      onChange={(e) =>
                        updateSelected({ timezone: e.target.value })
                      }
                      placeholder="Asia/Karachi"
                    />
                  </label>
                  <label>
                    Calling window starts
                    <input
                      type="time"
                      value={selected.data.call_start || "09:00"}
                      onChange={(e) =>
                        updateSelected({ call_start: e.target.value })
                      }
                    />
                  </label>
                  <label>
                    Calling window ends
                    <input
                      type="time"
                      value={selected.data.call_end || "18:00"}
                      onChange={(e) =>
                        updateSelected({ call_end: e.target.value })
                      }
                    />
                  </label>
                  <fieldset>
                    <legend>Allowed weekdays</legend>
                    {["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map(
                      (day, index) => (
                        <label key={day} className="row">
                          <input
                            type="checkbox"
                            checked={(
                              selected.data.weekdays || [0, 1, 2, 3, 4]
                            ).includes(index)}
                            onChange={(e) =>
                              updateSelected({
                                weekdays: e.target.checked
                                  ? [
                                      ...(selected.data.weekdays || [
                                        0, 1, 2, 3, 4,
                                      ]),
                                      index,
                                    ]
                                  : (
                                      selected.data.weekdays || [0, 1, 2, 3, 4]
                                    ).filter((value) => value !== index),
                              })
                            }
                          />
                          {day}
                        </label>
                      ),
                    )}
                  </fieldset>
                  <label>
                    Save acceptance result as
                    <input
                      value={selected.data.variable || "call_result"}
                      onChange={(e) =>
                        updateSelected({ variable: e.target.value })
                      }
                    />
                  </label>
                  <small>
                    The flow continues when the provider accepts the call.
                    Acceptance does not mean the call was answered or completed.
                    Failed or interrupted requests require review.
                  </small>
                </div>
              )}
              {selected.data.kind === "generate_voice" && (
                <>
                  <label>
                    Voice integration
                    <select
                      aria-label="Voice integration"
                      value={selected.data.integration_id || ""}
                      onChange={(event) =>
                        updateSelected({ integration_id: event.target.value })
                      }
                    >
                      <option value="">Choose a connected provider</option>
                      {integrations
                        .filter(
                          (item) =>
                            item.enabled &&
                            ["elevenlabs", "inworld", "minimax"].includes(
                              item.provider,
                            ),
                        )
                        .map((item) => (
                          <option key={item.id} value={item.id}>
                            {item.provider}
                            {item.is_test ? " (local test)" : ""}
                          </option>
                        ))}
                    </select>
                  </label>
                  <small>
                    Requires a private reply and an open messaging window. Usage
                    is charged by your connected voice provider. Review failed
                    jobs before trying again.
                  </small>
                </>
              )}
              {selected.data.kind === "follow_gate" && (
                <>
                  <label>
                    Follow confirmation button
                    <input
                      aria-label="Follow confirmation button"
                      maxLength={20}
                      value={selected.data.button_title || ""}
                      onChange={(event) =>
                        updateSelected({ button_title: event.target.value })
                      }
                    />
                  </label>
                  <p className="muted-text">
                    Instagram only. The flow waits for a private reply, then
                    checks follow status with the connected account. Unknown or
                    unavailable status stops for review.
                  </p>
                </>
              )}
              {selected.data.kind === "send_reminder" && (
                <label>
                  Tracked resource message
                  <select
                    aria-label="Reminder resource message"
                    value={selected.data.source_node || ""}
                    onChange={(event) =>
                      updateSelected({ source_node: event.target.value })
                    }
                  >
                    <option value="">Choose a previous tracked message</option>
                    {nodes
                      .filter(
                        (node) =>
                          node.data.kind === "send_buttons" &&
                          node.data.track_clicks,
                      )
                      .map((node) => (
                        <option key={node.id} value={node.id}>
                          {node.id}
                        </option>
                      ))}
                  </select>
                  <small>
                    Add a Delay step before this reminder. A click on any link
                    from the selected message cancels it.
                  </small>
                </label>
              )}
              {selected.data.kind === "send_buttons" && (
                <label className="field inline">
                  <input
                    type="checkbox"
                    checked={selected.data.track_clicks || false}
                    onChange={(event) =>
                      updateSelected({ track_clicks: event.target.checked })
                    }
                  />
                  Track resource link clicks
                </label>
              )}
              {selected.data.kind === "send_media" && (
                <>
                  <label className="field">
                    Media type
                    <select
                      aria-label="Media type"
                      value={selected.data.media_type || "image"}
                      onChange={(event) =>
                        updateSelected({
                          media_type: event.target
                            .value as FlowNodeData["media_type"],
                        })
                      }
                    >
                      <option value="image">Photo</option>
                      <option value="video">Video</option>
                      <option value="audio">Audio</option>
                    </select>
                  </label>
                  <label className="field">
                    Media URL
                    <input
                      aria-label="Media URL"
                      type="url"
                      maxLength={2000}
                      value={selected.data.media_url || ""}
                      onChange={(event) =>
                        updateSelected({ media_url: event.target.value })
                      }
                      placeholder="https://example.com/file.jpg"
                    />
                  </label>
                  <p className="muted-text">
                    Use a public, direct file URL. For comment automations, wait
                    for the customer to reply privately before sending media.
                    Add a separate message step for a caption.
                  </p>
                </>
              )}
              {selected.data.kind === "send_buttons" && (
                <div className="field">
                  Buttons{" "}
                  <span className="hint">
                    1–3 link or reply buttons, titles up to 20 characters
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
                      <select
                        aria-label={`Button ${index + 1} action`}
                        value={button.type}
                        onChange={(event) => {
                          const next = [...buttons];
                          next[index] = {
                            ...button,
                            type: event.target.value as FlowButton["type"],
                          };
                          setButtons(next);
                        }}
                      >
                        <option value="web_url">Open HTTPS link</option>
                        <option value="postback">Reply to automation</option>
                      </select>
                      <input
                        placeholder={
                          button.type === "postback"
                            ? "Reply payload"
                            : "https://"
                        }
                        value={
                          (button.type === "postback"
                            ? button.payload
                            : button.url) || ""
                        }
                        onChange={(event) => {
                          const next = [...buttons];
                          next[index] = {
                            ...button,
                            [button.type === "postback" ? "payload" : "url"]:
                              event.target.value,
                          };
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
              {selected.data.kind === "wait" && (
                <label className="field">
                  Required reply payload (optional)
                  <input
                    value={selected.data.expected_reply || ""}
                    maxLength={64}
                    onChange={(event) =>
                      updateSelected({
                        expected_reply: event.target.value || undefined,
                      })
                    }
                  />
                  <span className="hint">
                    When set, only this reply button can continue the flow.
                  </span>
                </label>
              )}
              {selected.data.kind === "capture_email" && (
                <label className="field">
                  Invalid email reply
                  <textarea
                    value={selected.data.retry_text || ""}
                    maxLength={2000}
                    onChange={(event) =>
                      updateSelected({ retry_text: event.target.value })
                    }
                  />
                  <span className="hint">
                    The flow waits here until the lead replies with a valid
                    email.
                  </span>
                </label>
              )}
              {["ai_generate", "ai_extract", "ai_condition"].includes(
                selected.data.kind,
              ) && (
                <>
                  <label>
                    AI model
                    <select
                      aria-label="Workflow AI model"
                      value={
                        selected.data.ai_provider && selected.data.ai_model
                          ? `${selected.data.ai_provider}:${selected.data.ai_model}`
                          : ""
                      }
                      onChange={(event) => {
                        const [ai_provider, ai_model] =
                          event.target.value.split(":");
                        updateSelected({
                          ai_provider: ai_provider || "",
                          ai_model: ai_model || "",
                        });
                      }}
                    >
                      <option value="">Use workspace AI settings</option>
                      {aiModels.map((model) => (
                        <option
                          key={`${model.provider}:${model.id}`}
                          value={`${model.provider}:${model.id}`}
                        >
                          {model.label} · {model.rate_summary}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    AI instructions
                    <textarea
                      aria-label="Workflow AI instructions"
                      rows={6}
                      maxLength={4000}
                      value={selected.data.prompt || ""}
                      onChange={(event) =>
                        updateSelected({ prompt: event.target.value })
                      }
                      placeholder={
                        selected.data.kind === "ai_condition"
                          ? "Does this enquiry ask for an appointment? Message: {{last_text}}"
                          : "Use this customer's message: {{last_text}}"
                      }
                    />
                  </label>
                  {selected.data.kind === "ai_extract" && (
                    <label>
                      Fields to extract
                      <input
                        aria-label="AI extraction fields"
                        value={(selected.data.fields || []).join(",")}
                        onChange={(event) =>
                          updateSelected({
                            fields: event.target.value.split(","),
                          })
                        }
                        placeholder="name,email,budget"
                      />
                      <small>
                        Separate field names with commas. Unknown values are
                        saved as null.
                      </small>
                    </label>
                  )}
                  <label>
                    Save AI result as
                    <input
                      aria-label="AI result variable"
                      maxLength={60}
                      value={selected.data.variable || "ai_result"}
                      onChange={(event) =>
                        updateSelected({ variable: event.target.value })
                      }
                    />
                  </label>
                  <small>
                    {selected.data.kind === "ai_condition"
                      ? "Connect both yes and no paths. The step waits for the model's decision."
                      : selected.data.kind === "ai_extract"
                        ? "Extracted fields become flow variables. Add Set custom field steps to save them to the contact."
                        : "This step saves text without sending it. Use {{ai_result}} in a Send message step."}{" "}
                    AI usage follows your workspace billing settings.
                    Bring-your-own keys use the model saved in AI settings.
                  </small>
                </>
              )}
              {selected.data.kind === "start_agent" && (
                <p className="muted-text">
                  This is the final step. After the contact sends a private
                  reply, your enabled{" "}
                  <Link href={`/w/${workspace.id}/agent`}>AI assistant</Link>{" "}
                  continues the conversation using its knowledge and tools.
                </p>
              )}
              {selected.data.kind === "integration_action" && (
                <>
                  <label>
                    Operation
                    <select
                      aria-label="Operation"
                      value={selected.data.operation || "sync_lead"}
                      onChange={(event) =>
                        updateSelected({
                          operation: event.target.value as
                            "sync_lead" | "notify" | "send_email" | "webhook",
                          integration_id: "",
                        })
                      }
                    >
                      <option value="sync_lead">Sync contact to CRM</option>
                      <option value="notify">Send Slack notification</option>
                      <option value="webhook">
                        Send webhook / n8n / Make request
                      </option>
                      <option value="send_email">
                        Send email through Gmail or Outlook
                      </option>
                    </select>
                  </label>
                  <label>
                    Connected integration
                    <select
                      aria-label="Connected integration"
                      value={selected.data.integration_id || ""}
                      onChange={(event) =>
                        updateSelected({ integration_id: event.target.value })
                      }
                    >
                      <option value="">Choose an integration</option>
                      {integrations
                        .filter(
                          (config) =>
                            config.enabled &&
                            config.status === "active" &&
                            (selected.data.operation === "webhook"
                              ? ["n8n", "make", "discord", "webhook"].includes(
                                  config.provider,
                                )
                              : selected.data.operation === "send_email"
                                ? ["gmail", "outlook", "zorromail"].includes(
                                    config.provider,
                                  )
                                : selected.data.operation === "notify"
                                  ? config.provider === "slack"
                                  : [
                                      "airtable",
                                      "notion",
                                      "attio",
                                      "gohighlevel",
                                      "google_sheets",
                                      "mailerlite",
                                      "klaviyo",
                                      "systeme_io",
                                    ].includes(config.provider)),
                        )
                        .map((config) => (
                          <option key={config.id} value={config.id}>
                            {config.provider}
                          </option>
                        ))}
                    </select>
                  </label>
                  {selected.data.operation === "send_email" && (
                    <>
                      <label>
                        Recipient
                        <input
                          value={selected.data.to || ""}
                          onChange={(event) =>
                            updateSelected({ to: event.target.value })
                          }
                          placeholder="Leave blank to use the contact's email"
                        />
                      </label>
                      <label>
                        Subject
                        <input
                          value={selected.data.subject || ""}
                          maxLength={200}
                          onChange={(event) =>
                            updateSelected({ subject: event.target.value })
                          }
                        />
                      </label>
                    </>
                  )}
                  {["notify", "send_email"].includes(
                    selected.data.operation || "",
                  ) && (
                    <label>
                      Notification
                      <textarea
                        value={selected.data.text || ""}
                        maxLength={2000}
                        onChange={(event) =>
                          updateSelected({ text: event.target.value })
                        }
                        placeholder="Lead asked about {{last_text}}"
                      />
                    </label>
                  )}
                  <label>
                    Save result as
                    <input
                      value={selected.data.variable || "integration_result"}
                      onChange={(event) =>
                        updateSelected({ variable: event.target.value })
                      }
                    />
                  </label>
                  {selected.data.operation === "webhook" && (
                    <>
                      <label>
                        Request body (JSON)
                        <textarea
                          aria-label="Webhook request body"
                          rows={6}
                          maxLength={10000}
                          value={selected.data.request_body ?? "{}"}
                          onChange={(event) =>
                            updateSelected({ request_body: event.target.value })
                          }
                        />
                      </label>
                      <label>
                        Response fields (JSON)
                        <textarea
                          aria-label="Webhook response fields"
                          rows={4}
                          maxLength={10000}
                          value={
                            typeof selected.data.response_map === "string"
                              ? selected.data.response_map
                              : JSON.stringify(
                                  selected.data.response_map || {},
                                  null,
                                  2,
                                )
                          }
                          onChange={(event) =>
                            updateSelected({ response_map: event.target.value })
                          }
                        />
                      </label>
                      <small>
                        Send a JSON POST to the connected webhook. Use saved
                        variables such as {"{{reply}}"} in string values. Map
                        responses with{" "}
                        {JSON.stringify({ order_id: "order.id" })} to use{" "}
                        {"{{order_id}}"} in later steps.
                      </small>
                    </>
                  )}
                  <small>
                    The next step runs after the integration completes. An
                    uncertain result stops for review.
                  </small>
                </>
              )}
              {selected.data.kind === "set_field" && (
                <>
                  <label>
                    Field name
                    <input
                      value={selected.data.field || ""}
                      maxLength={60}
                      onChange={(event) =>
                        updateSelected({ field: event.target.value })
                      }
                    />
                  </label>
                  <label>
                    Field value
                    <textarea
                      value={selected.data.value || ""}
                      maxLength={500}
                      onChange={(event) =>
                        updateSelected({ value: event.target.value })
                      }
                      placeholder="A fixed value or {{reply}}"
                    />
                  </label>
                </>
              )}
              {selected.data.kind === "set_stage" && (
                <label>
                  Contact stage
                  <select
                    value={selected.data.stage || "new"}
                    onChange={(event) =>
                      updateSelected({ stage: event.target.value })
                    }
                  >
                    {[
                      "new",
                      "qualified",
                      "interested",
                      "booked",
                      "won",
                      "lost",
                    ].map((stage) => (
                      <option key={stage} value={stage}>
                        {stage[0].toUpperCase() + stage.slice(1)}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              {selected.data.kind === "randomizer" && (
                <label>
                  Path A percentage
                  <input
                    type="number"
                    min={0}
                    max={100}
                    step={1}
                    value={selected.data.percentage ?? 50}
                    onChange={(event) =>
                      updateSelected({ percentage: Number(event.target.value) })
                    }
                  />
                  <small>
                    Path B receives {100 - (selected.data.percentage ?? 50)}%.
                    The chosen path stays the same on retries.
                  </small>
                </label>
              )}
              {selected.data.kind === "add_tag" && (
                <label className="field">
                  Contact tag
                  <input
                    value={selected.data.tag || ""}
                    maxLength={40}
                    onChange={(event) =>
                      updateSelected({ tag: event.target.value })
                    }
                  />
                </label>
              )}
              {selected.data.kind === "assign_member" && (
                <label className="field">
                  Workspace teammate
                  <select
                    value={selected.data.user_id || ""}
                    onChange={(event) =>
                      updateSelected({
                        user_id: Number(event.target.value) || undefined,
                      })
                    }
                  >
                    <option value="">Choose a teammate</option>
                    {members.map((member) => (
                      <option key={member.id} value={member.user_id}>
                        {member.name || member.email}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              {selected.data.kind === "transfer" && (
                <label className="field">
                  Continue in automation
                  <select
                    value={selected.data.automation_id || ""}
                    onChange={(event) =>
                      updateSelected({ automation_id: event.target.value })
                    }
                  >
                    <option value="">Choose an enabled automation</option>
                    {otherFlows
                      .filter(
                        (item) => item.id !== automationId && item.enabled,
                      )
                      .map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.name}
                        </option>
                      ))}
                  </select>
                  <span className="hint">
                    This step ends this graph and continues in the selected
                    flow.
                  </span>
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
              <label className="field">
                Connected account
                <select
                  value={connectionId}
                  onChange={(event) => {
                    setConnectionId(event.target.value);
                    setDirty(true);
                  }}
                >
                  <option value="">All matching accounts</option>
                  {connectionId &&
                    !connections.some((c) => c.id === connectionId) && (
                      <option value={connectionId}>
                        Unavailable account — choose another
                      </option>
                    )}
                  {connections
                    .filter((c) => c.id === connectionId || (c.status === "active" && !c.locked))
                    .map((c) => (
                      <option value={c.id} key={c.id}>
                        {c.display_name} · {c.is_test ? "Test" : "Live"} ·{" "}
                        {c.locked ? "Locked" : c.status === "active" ? "Connected" : c.status.replaceAll("_", " ")}
                      </option>
                    ))}
                </select>
              </label>
              {((connectionId &&
                triggers.every(
                  (t) =>
                    t.kind === "comment" &&
                    ["instagram", "messenger"].includes(t.channel || ""),
                )) ||
                commentPostIds.length > 0 ||
                commentReplies.length > 0 ||
                commentTarget.comment_post_mode) && (
                <>
                  <label>
                    Comment post scope
                    <select
                      value={
                        commentTarget.comment_post_mode ||
                        (commentPostIds.length ? "specific" : "all")
                      }
                      onChange={(event) => {
                        setCommentTarget({
                          comment_post_mode: event.target.value as
                            "all" | "specific" | "next",
                        });
                        setCommentPostIds([]);
                        setDirty(true);
                      }}
                    >
                      <option value="all">All posts</option>
                      <option value="specific">Specific posts</option>
                      <option value="next">The next post I publish</option>
                    </select>
                  </label>
                  {commentTarget.comment_post_mode === "next" && (
                    <p className="muted-text">
                      Publishing arms this flow for the first new post.{" "}
                      {commentTarget.resolved_next_post_id
                        ? `Current published target: ${commentTarget.resolved_next_post_id}.`
                        : "Waiting for a new post."}{" "}
                      Republishing resets the target.
                    </p>
                  )}
                  <label>
                    Comment post IDs
                    <input
                      disabled={commentTarget.comment_post_mode === "next"}
                      value={commentPostIds.join(",")}
                      onChange={(event) => {
                        setCommentPostIds(event.target.value.split(","));
                        setCommentTarget({
                          comment_post_mode: event.target.value.trim()
                            ? "specific"
                            : "all",
                        });
                        setDirty(true);
                      }}
                      placeholder="Leave blank for all posts"
                    />
                    <small>
                      Separate post IDs with commas. Selected posts must belong
                      to the connected account.
                    </small>
                  </label>
                  <label>
                    Public comment replies
                    <textarea
                      value={commentReplies.join("\n")}
                      onChange={(event) => {
                        setCommentReplies(
                          event.target.value
                            ? event.target.value.split("\n")
                            : [],
                        );
                        setDirty(true);
                      }}
                      placeholder="One variation per line; leave blank to disable"
                      rows={4}
                    />
                    <small>
                      One reply is sent for a matching comment. Use up to 10
                      variations.
                    </small>
                  </label>
                </>
              )}
              <p className="muted-text">
                Every step except End and Continue automation needs exactly one
                outgoing connection; conditions need a “yes” and a “no”. No
                loops — use “Wait for reply” to continue a conversation. Each
                lead runs a flow at most once per hour.
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
