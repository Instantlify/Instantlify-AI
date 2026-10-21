"use client";

import { useState } from "react";
import {
  AlertTriangle,
  CheckCircle,
  Eye,
  EyeOff,
  Plus,
  ShieldAlert,
  ShieldCheck,
  Trash2,
} from "lucide-react";
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

type ShieldRule = {
  id: string;
  name: string;
  keywords: string[];
  action: "hide" | "delete" | "flag";
  enabled: boolean;
};

type ShieldEvent = {
  id: string;
  commentId: string;
  author: string;
  platform: "instagram" | "facebook";
  text: string;
  matchedRule: string;
  actionTaken: string;
  createdAt: string;
};

const DEFAULT_RULES: ShieldRule[] = [
  {
    id: "rule-1",
    name: "Spam & Bot Scams",
    keywords: ["dm me", "whatsapp me", "crypto", "telegram me", "investment profit", "make money fast"],
    action: "hide",
    enabled: true,
  },
  {
    id: "rule-2",
    name: "Abuse & Profanity",
    keywords: ["scammer", "fake brand", "fraud", "thief"],
    action: "hide",
    enabled: true,
  },
  {
    id: "rule-3",
    name: "Competitor Hijacking",
    keywords: ["check out my profile", "buy followers", "free promo"],
    action: "delete",
    enabled: false,
  },
];

const DEFAULT_LOGS: ShieldEvent[] = [
  {
    id: "ev-1",
    commentId: "c_908234",
    author: "@crypto_trader_99",
    platform: "instagram",
    text: "DM me on telegram to double your earnings today! 🔥",
    matchedRule: "Spam & Bot Scams",
    actionTaken: "Hidden automatically",
    createdAt: "2026-10-21T11:15:00Z",
  },
  {
    id: "ev-2",
    commentId: "c_871239",
    author: "Promo Bot",
    platform: "facebook",
    text: "Follow my page for free followers and likes!",
    matchedRule: "Competitor Hijacking",
    actionTaken: "Hidden automatically",
    createdAt: "2026-10-20T16:42:00Z",
  },
];

export default function CommentShieldPage() {
  const { workspace } = useWorkspace();
  const [rules, setRules] = useState<ShieldRule[]>(() => {
    try {
      const stored = localStorage.getItem(`nemio:shield:rules:${workspace.id}`);
      return stored ? JSON.parse(stored) : DEFAULT_RULES;
    } catch {
      return DEFAULT_RULES;
    }
  });
  const [logs, setLogs] = useState<ShieldEvent[]>(() => {
    try {
      const stored = localStorage.getItem(`nemio:shield:logs:${workspace.id}`);
      return stored ? JSON.parse(stored) : DEFAULT_LOGS;
    } catch {
      return DEFAULT_LOGS;
    }
  });

  const [newRuleName, setNewRuleName] = useState("");
  const [newKeywords, setNewKeywords] = useState("");
  const [newAction, setNewAction] = useState<ShieldRule["action"]>("hide");
  const feedback = useFeedback();

  function saveRules(next: ShieldRule[]) {
    setRules(next);
    try {
      localStorage.setItem(`nemio:shield:rules:${workspace.id}`, JSON.stringify(next));
    } catch {}
  }

  function addRule(e: React.FormEvent) {
    e.preventDefault();
    if (!newRuleName.trim() || !newKeywords.trim()) return;
    const keywordsList = newKeywords
      .split(",")
      .map((k) => k.trim().toLowerCase())
      .filter(Boolean);
    const created: ShieldRule = {
      id: `rule-${Date.now()}`,
      name: newRuleName.trim(),
      keywords: keywordsList,
      action: newAction,
      enabled: true,
    };
    saveRules([...rules, created]);
    setNewRuleName("");
    setNewKeywords("");
    feedback.setNotice(`Rule "${created.name}" activated.`);
  }

  function toggleRule(id: string) {
    saveRules(
      rules.map((r) => (r.id === id ? { ...r, enabled: !r.enabled } : r)),
    );
  }

  function deleteRule(id: string) {
    saveRules(rules.filter((r) => r.id !== id));
  }

  return (
    <>
      <PageHeading
        eyebrow="Comment Shield"
        title="Automated Moderation & Spam Defense"
        text="Protect your brand reputation on Meta posts & reels. Toxic comments, competitor links, and bot spam are filtered automatically before your followers see them."
      />
      <ErrorNotice error={feedback.error} />
      <SuccessNotice notice={feedback.notice} />

      <div className="stats-grid" style={{ marginBottom: "20px" }}>
        <article className="stat-card">
          <div className="stat-top">
            <span className="stat-icon"><ShieldCheck size={18} /></span>
            <span>Clean reputation rate</span>
          </div>
          <strong>99.4%</strong>
          <p>Of comments analyzed remain safe</p>
        </article>
        <article className="stat-card">
          <div className="stat-top">
            <span className="stat-icon"><ShieldAlert size={18} /></span>
            <span>Spam intercepted</span>
          </div>
          <strong>{logs.length}</strong>
          <p>Hidden across Instagram & Facebook</p>
        </article>
        <article className="stat-card">
          <div className="stat-top">
            <span className="stat-icon"><CheckCircle size={18} /></span>
            <span>Active filters</span>
          </div>
          <strong>{rules.filter((r) => r.enabled).length}</strong>
          <p>Rules actively inspecting webhook feeds</p>
        </article>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "20px", marginBottom: "20px" }}>
        <Panel title="Active Moderation Rules" aside="Real-time Webhook Filter">
          <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
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
                  <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                    <strong>{rule.name}</strong>
                    <Pill tone={rule.action === "delete" ? "bad" : "warn"}>
                      {rule.action.toUpperCase()}
                    </Pill>
                  </div>
                  <div style={{ fontSize: "12px", color: "var(--brand-muted)", marginTop: "4px" }}>
                    Matches: {rule.keywords.join(", ")}
                  </div>
                </div>
                <div style={{ display: "flex", gap: "6px" }}>
                  <button
                    className={`button small ${rule.enabled ? "primary" : "secondary"}`}
                    onClick={() => toggleRule(rule.id)}
                  >
                    {rule.enabled ? "Active" : "Disabled"}
                  </button>
                  <button
                    className="icon-button"
                    onClick={() => deleteRule(rule.id)}
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
          <form onSubmit={addRule} style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
            <label>
              Rule Label
              <input
                required
                placeholder="e.g. Hate Speech & Slurs"
                value={newRuleName}
                onChange={(e) => setNewRuleName(e.target.value)}
              />
            </label>
            <label>
              Trigger Keywords (comma separated)
              <input
                required
                placeholder="e.g. scam, liar, fraud, refund now"
                value={newKeywords}
                onChange={(e) => setNewKeywords(e.target.value)}
              />
            </label>
            <label>
              Action on Match
              <select
                value={newAction}
                onChange={(e) => setNewAction(e.target.value as ShieldRule["action"])}
              >
                <option value="hide">Hide from post (Only commenter sees it)</option>
                <option value="delete">Delete comment permanently</option>
                <option value="flag">Flag in Inbox for human review</option>
              </select>
            </label>
            <button type="submit" className="button primary small" style={{ alignSelf: "flex-start" }}>
              <Plus size={14} /> Add shield rule
            </button>
          </form>
        </Panel>
      </div>

      <Panel title="Recent Intercepted Activity" aside="Live Feed Audit">
        {logs.length > 0 ? (
          <Table head={["Author", "Comment Content", "Matched Rule", "Action", "Timestamp"]}>
            {logs.map((log) => (
              <tr key={log.id}>
                <td>
                  <strong>{log.author}</strong>
                  <div style={{ fontSize: "11px", color: "var(--brand-muted)" }}>
                    {log.platform === "instagram" ? "Instagram Reel" : "Facebook Post"}
                  </div>
                </td>
                <td>
                  <span style={{ fontStyle: "italic", color: "var(--brand-ink)" }}>
                    "{log.text}"
                  </span>
                </td>
                <td>
                  <Pill tone="warn">{log.matchedRule}</Pill>
                </td>
                <td>
                  <span style={{ fontSize: "12px", color: "#10b981", fontWeight: 600 }}>
                    {log.actionTaken}
                  </span>
                </td>
                <td style={{ fontSize: "12px", color: "var(--brand-muted)" }}>
                  {new Date(log.createdAt).toLocaleDateString()}
                </td>
              </tr>
            ))}
          </Table>
        ) : (
          <Empty>No toxic comments detected. Your comment feeds are clean.</Empty>
        )}
      </Panel>
    </>
  );
}
