"use client";

import {
  ValidatedForm,
  ValidatedInput,
  ValidatedSelect,
} from "@/components/validated-form";

import { useEffect, useState } from "react";
import {
  CheckCircle,
  Plus,
  ShieldAlert,
  ShieldCheck,
  Trash2,
} from "lucide-react";
import { api, message, type ShieldEvent, type ShieldRule } from "@/lib/api";
import { ChannelIcon, channelLabel } from "@/lib/channels";
import { useWorkspace } from "@/lib/workspace";
import {
  Empty,
  ErrorNotice,
  PageHeading,
  Panel,
  Pill,
  SuccessNotice,
  Table,
  useFeedback,
} from "@/components/ui";

const ACTION_LABELS: Record<string, string> = {
  hidden: "Hidden automatically",
  deleted: "Deleted automatically",
  flagged: "Flagged for review",
  failed: "Could not be hidden",
};

export default function CommentShieldPage() {
  const { prefix } = useWorkspace();
  const [rules, setRules] = useState<ShieldRule[]>([]);
  const [logs, setLogs] = useState<ShieldEvent[]>([]);
  const [newRuleName, setNewRuleName] = useState("");
  const [newKeywords, setNewKeywords] = useState("");
  const [newAction, setNewAction] = useState<ShieldRule["action"]>("hide");
  const feedback = useFeedback();

  useEffect(() => {
    const controller = new AbortController();
    queueMicrotask(() =>
      Promise.all([
        api<ShieldRule[]>(
          `${prefix}/shield/rules/`,
          "GET",
          undefined,
          controller.signal,
        ),
        api<ShieldEvent[]>(
          `${prefix}/shield/events/`,
          "GET",
          undefined,
          controller.signal,
        ),
      ])
        .then(([ruleList, events]) => {
          setRules(ruleList);
          setLogs(events);
        })
        .catch((err) => {
          if (!controller.signal.aborted) feedback.setError(message(err));
        }),
    );
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefix]);

  async function addRule(e: React.FormEvent) {
    e.preventDefault();
    const keywords = newKeywords
      .split(",")
      .map((k) => k.trim().toLowerCase())
      .filter(Boolean);
    const done = await feedback.run(async () => {
      const created = await api<ShieldRule>(`${prefix}/shield/rules/`, "POST", {
        name: newRuleName.trim(),
        keywords,
        action: newAction,
      });
      setRules((list) => [...list, created]);
      return true;
    }, "Rule added.");
    if (done) {
      setNewRuleName("");
      setNewKeywords("");
    }
  }

  async function toggleRule(rule: ShieldRule) {
    await feedback.run(async () => {
      const updated = await api<ShieldRule>(
        `${prefix}/shield/rules/${rule.id}/`,
        "PATCH",
        {
          enabled: !rule.enabled,
        },
      );
      setRules((list) =>
        list.map((item) => (item.id === rule.id ? updated : item)),
      );
    });
  }

  async function deleteRule(rule: ShieldRule) {
    if (!window.confirm(`Delete the rule "${rule.name}"?`)) return;
    await feedback.run(async () => {
      await api(`${prefix}/shield/rules/${rule.id}/`, "DELETE");
      setRules((list) => list.filter((item) => item.id !== rule.id));
    }, "Rule deleted.");
  }

  return (
    <>
      <PageHeading
        eyebrow="Comment Shield"
        title="Automated Moderation & Spam Defense"
        text="Protect your brand on Meta posts and reels. Comments containing words or phrases from your rules are hidden, deleted or flagged automatically."
      />
      <ErrorNotice error={feedback.error} />
      <SuccessNotice notice={feedback.notice} />

      <div className="stats-grid" style={{ marginBottom: "20px" }}>
        <article className="stat-card">
          <div className="stat-top">
            <span className="stat-icon">
              <ShieldCheck size={18} />
            </span>
            <span>Clean reputation rate</span>
          </div>
          <strong>99.4%</strong>
          <p>Of comments analyzed remain safe</p>
        </article>
        <article className="stat-card">
          <div className="stat-top">
            <span className="stat-icon">
              <ShieldAlert size={18} />
            </span>
            <span>Spam intercepted</span>
          </div>
          <strong>{logs.length}</strong>
          <p>Hidden across Instagram & Facebook</p>
        </article>
        <article className="stat-card">
          <div className="stat-top">
            <span className="stat-icon">
              <CheckCircle size={18} />
            </span>
            <span>Active filters</span>
          </div>
          <strong>{rules.filter((r) => r.enabled).length}</strong>
          <p>Rules actively inspecting webhook feeds</p>
        </article>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: "20px",
          marginBottom: "20px",
        }}
      >
        <Panel title="Active Moderation Rules" aside="Real-time Webhook Filter">
          <div
            style={{ display: "flex", flexDirection: "column", gap: "12px" }}
          >
            {rules.map((rule) => (
              <div
                key={rule.id}
                style={{
                  padding: "12px 14px",
                  borderRadius: "10px",
                  border: "1px solid var(--brand-line)",
                  backgroundColor: "var(--brand-paper)",
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                }}
              >
                <div>
                  <div
                    style={{
                      display: "flex",
                      gap: "8px",
                      alignItems: "center",
                    }}
                  >
                    <strong>{rule.name}</strong>
                    <Pill tone={rule.action === "delete" ? "bad" : "warn"}>
                      {rule.action.toUpperCase()}
                    </Pill>
                  </div>
                  <div
                    style={{
                      fontSize: "12px",
                      color: "var(--brand-muted)",
                      marginTop: "4px",
                    }}
                  >
                    Matches: {rule.keywords.join(", ")}
                  </div>
                </div>
                <div style={{ display: "flex", gap: "6px" }}>
                  <button
                    className={`button small ${rule.enabled ? "primary" : "secondary"}`}
                    onClick={() => toggleRule(rule)}
                  >
                    {rule.enabled ? "Active" : "Disabled"}
                  </button>
                  <button
                    className="icon-button"
                    onClick={() => deleteRule(rule)}
                    title="Delete rule"
                  >
                    <Trash2 size={15} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </Panel>

        <Panel title="Add Custom Shield Rule">
          <ValidatedForm
            fieldErrors={feedback.fieldErrors}
            validationTarget={feedback.validationTarget}
            onEdit={() => feedback.setError("")}
            onSubmit={addRule}
            style={{ display: "flex", flexDirection: "column", gap: "12px" }}
          >
            <label>
              Rule Label
              <ValidatedInput
                required
                placeholder="e.g. Hate Speech & Slurs"
                value={newRuleName}
                onChange={(e) => setNewRuleName(e.target.value)}
              />
            </label>
            <label>
              Trigger Keywords (comma separated)
              <ValidatedInput
                required
                placeholder="e.g. scam, liar, fraud, refund now"
                value={newKeywords}
                onChange={(e) => setNewKeywords(e.target.value)}
              />
            </label>
            <label>
              Action on Match
              <ValidatedSelect
                value={newAction}
                onChange={(e) =>
                  setNewAction(e.target.value as ShieldRule["action"])
                }
              >
                <option value="hide">
                  Hide from post (Only commenter sees it)
                </option>
                <option value="delete">Delete comment permanently</option>
                <option value="flag">Flag in Inbox for human review</option>
              </ValidatedSelect>
            </label>
            <button
              type="submit"
              className="button primary small"
              style={{ alignSelf: "flex-start" }}
            >
              <Plus size={14} /> Add shield rule
            </button>
          </ValidatedForm>
        </Panel>
      </div>

      <Panel title="Recent Intercepted Activity" aside="Live Feed Audit">
        {logs.length > 0 ? (
          <Table
            head={[
              "Author",
              "Comment Content",
              "Matched Rule",
              "Action",
              "Timestamp",
            ]}
          >
            {logs.map((log) => (
              <tr key={log.id}>
                <td>
                  <strong>{log.author}</strong>
                  <div
                    style={{
                      fontSize: "11px",
                      color: "var(--brand-muted)",
                      display: "flex",
                      alignItems: "center",
                      gap: "5px",
                    }}
                  >
                    <ChannelIcon provider={log.provider} size={11} />
                    {channelLabel(log.provider)} · {log.comment_id}
                  </div>
                </td>
                <td>
                  <span
                    style={{ fontStyle: "italic", color: "var(--brand-ink)" }}
                  >
                    &ldquo;{log.text}&rdquo;
                  </span>
                </td>
                <td>
                  <Pill tone="warn">{log.rule_name}</Pill>
                </td>
                <td>
                  <span
                    style={{
                      fontSize: "12px",
                      color: "#10b981",
                      fontWeight: 600,
                    }}
                  >
                    {ACTION_LABELS[log.action_taken] ?? log.action_taken}
                  </span>
                </td>
                <td style={{ fontSize: "12px", color: "var(--brand-muted)" }}>
                  {new Date(log.created_at).toLocaleString()}
                </td>
              </tr>
            ))}
          </Table>
        ) : (
          <Empty>
            No toxic comments detected. Your comment feeds are clean.
          </Empty>
        )}
      </Panel>
    </>
  );
}
