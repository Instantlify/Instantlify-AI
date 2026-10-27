"use client";

import {
  ValidatedForm,
  ValidatedInput,
  ValidatedTextarea,
} from "@/components/validated-form";

import { useEffect, useState } from "react";
import {
  Bot,
  Check,
  Code,
  Copy,
  MessageCircle,
  MessageSquareText,
  Palette,
  Send,
  Sparkles,
} from "lucide-react";
import { api, message, type WebChatSettings } from "@/lib/api";
import { useWorkspace } from "@/lib/workspace";
import {
  CopyField,
  ErrorNotice,
  PageHeading,
  Panel,
  SuccessNotice,
  useFeedback,
} from "@/components/ui";

export default function WebChatPage() {
  const { workspace, prefix } = useWorkspace();
  const [title, setTitle] = useState("");
  const [greeting, setGreeting] = useState("");
  const [color, setColor] = useState("#347359");
  const [botEnabled, setBotEnabled] = useState(true);
  const [allowedDomains, setAllowedDomains] = useState("");
  const [copied, setCopied] = useState(false);
  const feedback = useFeedback();

  useEffect(() => {
    const controller = new AbortController();
    queueMicrotask(() =>
      api<WebChatSettings>(`${prefix}/webchat/`, "GET", undefined, controller.signal)
        .then((saved) => {
          setTitle(saved.title);
          setGreeting(saved.greeting);
          setColor(saved.color);
          setBotEnabled(saved.bot_enabled);
          setAllowedDomains(saved.allowed_domains.join(", "));
        })
        .catch((err) => {
          if (!controller.signal.aborted) feedback.setError(message(err));
        }),
    );
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefix]);

  const embedScript = `<script\n  src="${typeof window !== "undefined" ? window.location.origin : "https://app.nemio.ai"}/widget.js"\n  data-workspace="${workspace.id}"\n  async>\n</script>`;

  function copyCode() {
    navigator.clipboard.writeText(embedScript);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    await feedback.run(async () => {
      const saved = await api<WebChatSettings>(`${prefix}/webchat/`, "PUT", {
        title: title.trim(),
        greeting: greeting.trim(),
        color,
        bot_enabled: botEnabled,
        allowed_domains: allowedDomains
          .split(",")
          .map((host) => host.trim())
          .filter(Boolean),
      });
      setAllowedDomains(saved.allowed_domains.join(", "));
    }, "Web chat settings saved. The widget picks them up on its next load.");
  }

  return (
    <>
      <PageHeading
        eyebrow="Web Chat Widget"
        title="Embeddable Omnichannel Live Chat"
        text="Install a live chat widget on your marketing site, shop, or portal. Inbound conversations sync instantly into your Nemio Inbox alongside Instagram, Messenger, and WhatsApp."
      />
      <ErrorNotice error={feedback.error} />
      <SuccessNotice notice={feedback.notice} />

      <div style={{ display: "grid", gridTemplateColumns: "1.2fr 0.8fr", gap: "24px", alignItems: "start" }}>
        <div>
          <Panel title="Widget Configuration">
            <ValidatedForm fieldErrors={feedback.fieldErrors} validationTarget={feedback.validationTarget} onEdit={() => feedback.setError("")} onSubmit={handleSave} style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
              <label>
                Widget Title
                <ValidatedInput
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="e.g. Chat with us"
                  required
                />
              </label>

              <label>
                Greeting Message
                <ValidatedTextarea
                  value={greeting}
                  onChange={(e) => setGreeting(e.target.value)}
                  rows={3}
                  required
                />
              </label>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "14px" }}>
                <label>
                  Brand Accent Color
                  <div style={{ display: "flex", gap: "10px", alignItems: "center", marginTop: "4px" }}>
                    <ValidatedInput
                      type="color"
                      value={color}
                      onChange={(e) => setColor(e.target.value)}
                      style={{ width: "42px", height: "36px", padding: "2px", cursor: "pointer", border: "1px solid var(--brand-line)", borderRadius: "6px" }}
                    />
                    <ValidatedInput
                      type="text"
                      value={color}
                      onChange={(e) => setColor(e.target.value)}
                      maxLength={7}
                      style={{ flex: 1 }}
                    />
                  </div>
                </label>

                <label>
                  AI Assistant Autoreply
                  <div style={{ marginTop: "8px" }}>
                    <label style={{ display: "flex", gap: "8px", alignItems: "center", cursor: "pointer", fontWeight: "normal" }}>
                      <ValidatedInput
                        type="checkbox"
                        checked={botEnabled}
                        onChange={(e) => setBotEnabled(e.target.checked)}
                      />
                      <span>Enable workspace AI agent</span>
                    </label>
                  </div>
                </label>
              </div>

              <label>
                Allowed Host Domains (comma separated)
                <ValidatedInput
                  value={allowedDomains}
                  onChange={(e) => setAllowedDomains(e.target.value)}
                  placeholder="e.g. acme.com, shop.acme.com"
                />
              </label>

              <button type="submit" className="button primary" style={{ alignSelf: "flex-start", marginTop: "6px" }}>
                Save Widget Settings
              </button>
            </ValidatedForm>
          </Panel>

          <div style={{ marginTop: "20px" }}>
            <Panel title="Embed Code" aside="One-line script installation">
            <p style={{ fontSize: "13px", color: "var(--brand-muted)", marginBottom: "12px" }}>
              Paste this snippet right before the closing <code>&lt;/body&gt;</code> tag of your website:
            </p>
            <div style={{ position: "relative" }}>
              <pre
                style={{
                  backgroundColor: "var(--brand-sidebar)",
                  color: "#e2e8f0",
                  padding: "16px",
                  borderRadius: "10px",
                  fontSize: "13px",
                  overflowX: "auto",
                  margin: 0,
                }}
              >
                <code>{embedScript}</code>
              </pre>
              <button
                className="button secondary small"
                onClick={copyCode}
                style={{ position: "absolute", top: "10px", right: "10px" }}
              >
                {copied ? <Check size={14} color="#10b981" /> : <Copy size={14} />}
                {copied ? "Copied" : "Copy snippet"}
              </button>
            </div>
          </Panel>
        </div>
      </div>

        {/* Live Widget Preview */}
        <Panel title="Live Widget Preview" aside="Interactive preview">
          <div
            style={{
              borderRadius: "16px",
              boxShadow: "0 8px 30px rgba(0,0,0,0.12)",
              border: "1px solid var(--brand-line)",
              overflow: "hidden",
              backgroundColor: "var(--brand-paper)",
              display: "flex",
              flexDirection: "column",
              height: "440px",
            }}
          >
            {/* Widget Header */}
            <div
              style={{
                backgroundColor: color,
                color: "#ffffff",
                padding: "16px",
                display: "flex",
                alignItems: "center",
                gap: "10px",
              }}
            >
              <span
                style={{
                  width: "10px",
                  height: "10px",
                  borderRadius: "50%",
                  backgroundColor: "#22c55e",
                  boxShadow: "0 0 0 2px rgba(255,255,255,0.4)",
                }}
              />
              <div>
                <strong style={{ display: "block", fontSize: "15px" }}>{title}</strong>
                <span style={{ fontSize: "12px", opacity: 0.9 }}>
                  {botEnabled ? "AI Agent + Team Online" : "Team Online"}
                </span>
              </div>
            </div>

            {/* Widget Messages */}
            <div
              style={{
                flex: 1,
                padding: "16px",
                display: "flex",
                flexDirection: "column",
                gap: "12px",
                overflowY: "auto",
                backgroundColor: "var(--brand-canvas)",
              }}
            >
              <div style={{ alignSelf: "flex-start", maxWidth: "85%" }}>
                <div
                  style={{
                    backgroundColor: "var(--brand-paper)",
                    padding: "12px 14px",
                    borderRadius: "14px 14px 14px 2px",
                    border: "1px solid var(--brand-line)",
                    fontSize: "13px",
                    lineHeight: "1.5",
                    color: "var(--brand-ink)",
                  }}
                >
                  {greeting}
                </div>
                <span style={{ fontSize: "10px", color: "var(--brand-muted)", marginLeft: "4px" }}>
                  Just now
                </span>
              </div>

              {botEnabled && (
                <div style={{ alignSelf: "center", padding: "4px 10px", borderRadius: "10px", backgroundColor: "rgba(0,0,0,0.04)", fontSize: "11px", color: "var(--brand-muted)", display: "flex", alignItems: "center", gap: "5px" }}>
                  <Sparkles size={12} /> Powered by Nemio AI
                </div>
              )}
            </div>

            {/* Widget Composer */}
            <div
              style={{
                padding: "12px",
                backgroundColor: "var(--brand-paper)",
                borderTop: "1px solid var(--brand-line)",
                display: "flex",
                gap: "8px",
              }}
            >
              <ValidatedInput
                placeholder="Ask a question…"
                disabled
                style={{
                  flex: 1,
                  padding: "8px 12px",
                  borderRadius: "20px",
                  border: "1px solid var(--brand-line)",
                  fontSize: "13px",
                }}
              />
              <button
                className="icon-button"
                style={{
                  backgroundColor: color,
                  color: "#fff",
                  borderRadius: "50%",
                  width: "36px",
                  height: "36px",
                }}
                disabled
              >
                <Send size={15} />
              </button>
            </div>
          </div>
        </Panel>
      </div>
    </>
  );
}
