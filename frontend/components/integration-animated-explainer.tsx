"use client";

import { useEffect, useState } from "react";
import {
  Sparkles,
  MessageSquare,
  Workflow,
  Check,
  Send,
  ChevronLeft,
  Phone,
  Video,
  CheckCircle2,
  Zap,
  Users,
} from "lucide-react";
import { BrandIcon } from "@/lib/brand-icons";

export interface IntegrationAppInfo {
  providerKey?: string;
  name: string;
  iconBg: string;
  iconColor: string;
  logo: React.ReactNode;
  category?: string | string[];
  explainer?: {
    stepType?: string;
    description?: string;
    actionLabel?: string;
    actionDetail?: string;
  };
}

export function IntegrationAnimatedExplainer({ app }: { app: IntegrationAppInfo }) {
  // Loop cycle:
  // Phase 1 (Builder): 0ms -> 3800ms
  //   0ms: reset / start
  //   300ms: Box 1 appears
  //   1000ms: Box 2 appears
  //   1700ms: Line draws
  //   2300ms: Step Added badge pops
  //   3800ms: transition to Phase 2
  // Phase 2 (Execution): 3800ms -> 9200ms
  //   4000ms: Chat & Destination screens fade in
  //   4600ms: User typing begins
  //   5400ms: User message bubble sent
  //   6000ms: Data packet drops into destination
  //   6600ms: Destination row/card populates with "+ Done automatically"
  //   9200ms: Loop resets to Phase 1!

  const [tick, setTick] = useState(0);
  const [activeTab, setActiveTab] = useState<"auto" | "builder" | "execution">("auto");

  useEffect(() => {
    const interval = setInterval(() => {
      setTick((t) => (t + 100) % 9400);
    }, 100);
    return () => clearInterval(interval);
  }, []);

  const effectiveTime = activeTab === "builder" ? 2800 : activeTab === "execution" ? 7000 : tick;

  const isPhase1 = effectiveTime < 3800;
  const box1Visible = effectiveTime >= 300;
  const box2Visible = effectiveTime >= 1000;
  const lineDrawn = effectiveTime >= 1700;
  const badgeVisible = effectiveTime >= 2300;

  const isPhase2 = effectiveTime >= 3800;
  const chatTyping = effectiveTime >= 4400 && effectiveTime < 5300;
  const userMessageSent = effectiveTime >= 5300;
  const dataDropping = effectiveTime >= 5800 && effectiveTime < 6800;
  const destPopulated = effectiveTime >= 6500;

  const pk = (app.providerKey || "").toLowerCase();
  const name = (app.name || "").toLowerCase();

  // Determine category style for Phase 2
  const isSpreadsheet =
    pk.includes("sheet") ||
    pk.includes("excel") ||
    pk.includes("airtable") ||
    pk.includes("notion") ||
    name.includes("sheet") ||
    name.includes("excel");

  const isWorkflow =
    pk.includes("n8n") ||
    pk.includes("make") ||
    pk.includes("webhook") ||
    pk.includes("zapier");

  const isCommunication =
    pk.includes("slack") ||
    pk.includes("discord") ||
    pk.includes("telegram") ||
    pk.includes("teams");

  const isEmail =
    pk.includes("gmail") ||
    pk.includes("outlook") ||
    pk.includes("mail");

  const isScheduling =
    pk.includes("calendly") ||
    pk.includes("cal");

  return (
    <div className="explainer-interactive-wrapper">
      {/* Top Phase Switcher / Progress Indicators */}
      <div className="explainer-phase-tabs">
        <button
          type="button"
          className={`phase-tab-btn ${isPhase1 ? "active" : ""}`}
          onClick={() => setActiveTab(activeTab === "builder" ? "auto" : "builder")}
        >
          <span className="step-num">1</span>
          <span>Flow Setup</span>
          {isPhase1 && <span className="tab-pulse-dot" />}
        </button>
        <button
          type="button"
          className={`phase-tab-btn ${isPhase2 ? "active" : ""}`}
          onClick={() => setActiveTab(activeTab === "execution" ? "auto" : "execution")}
        >
          <span className="step-num">2</span>
          <span>Live Action</span>
          {isPhase2 && <span className="tab-pulse-dot" />}
        </button>
      </div>

      {/* Main Stage Container with fixed height for buttery smooth transitions */}
      <div className="explainer-stage-box">
        {/* FRAME 1: FLOW BUILDER (Matches Screenshot 1) */}
        {isPhase1 && (
          <div className="explainer-frame-builder">
            <div className="boosend-canvas-preview anim-canvas">
              {/* Box 1: When... Message Received */}
              <div
                className={`boosend-canvas-node node-trigger ${
                  box1Visible ? "node-visible" : "node-hidden"
                }`}
              >
                <div className="boosend-canvas-node-top">
                  <Sparkles size={11} color="#f43f5e" />
                  When...
                </div>
                <div className="boosend-canvas-node-title">
                  <BrandIcon name="instagram" size={13} />
                  Message Received
                </div>
                <div className="boosend-canvas-node-sub">any message</div>
              </div>

              {/* Connecting Line with Step Added Badge */}
              <div className="boosend-canvas-connector anim-connector">
                <div
                  className={`boosend-step-added-badge ${
                    badgeVisible ? "badge-visible" : "badge-hidden"
                  }`}
                >
                  Step added ✓
                </div>
                <div
                  className="boosend-canvas-line"
                  style={{
                    width: lineDrawn ? "100%" : "0%",
                    transition: "width 0.4s cubic-bezier(0.16, 1, 0.3, 1)",
                  }}
                />
              </div>

              {/* Box 2: Run Workflow / App Step */}
              <div
                className={`boosend-canvas-node node-action ${
                  box2Visible ? "node-visible" : "node-hidden"
                }`}
              >
                <div className="boosend-canvas-node-top">
                  <Workflow size={11} color="#3b82f6" />
                  {app.explainer?.actionLabel || "Run Workflow"}
                </div>
                <div className="boosend-canvas-node-title">
                  <div
                    style={{
                      width: "16px",
                      height: "16px",
                      borderRadius: "4px",
                      backgroundColor: app.iconBg,
                      color: app.iconColor,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      fontSize: "9px",
                      fontWeight: 700,
                      flexShrink: 0,
                    }}
                  >
                    {app.name.slice(0, 2).toUpperCase()}
                  </div>
                  <span style={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                    {app.name}
                  </span>
                </div>
                <div className="boosend-canvas-node-sub">
                  {app.explainer?.actionDetail || "custom action"}
                </div>
              </div>
            </div>

            <div className="explainer-frame-caption">
              <span>Step 1: In your automation, link the conversation trigger to <strong>{app.name}</strong></span>
            </div>
          </div>
        )}

        {/* FRAME 2: LIVE EXECUTION (Matches Screenshot 2) */}
        {isPhase2 && (
          <div className="explainer-frame-execution">
            <div className="execution-split-grid">
              {/* LEFT SIDE: Destination Platform Panel */}
              <div className="dest-app-panel">
                {/* Floating "Done automatically" Badge */}
                <div
                  className={`pill-done-auto ${
                    destPopulated ? "pill-pop-in" : "pill-hidden"
                  }`}
                >
                  <Sparkles size={11} /> + Done automatically
                </div>

                {/* Variant A: Spreadsheet (Google Sheets, Excel, Airtable) */}
                {isSpreadsheet && (
                  <div className="mock-spreadsheet">
                    <div className="mock-sheet-header">
                      <div
                        style={{
                          width: "18px",
                          height: "18px",
                          borderRadius: "4px",
                          background: app.iconBg,
                          color: app.iconColor,
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          fontSize: "10px",
                        }}
                      >
                        <span className="explainer-app-mark">{app.logo}</span>
                      </div>
                      <span className="sheet-doc-title">Leads</span>
                      <span className="sheet-menubar">File Edit View Insert Format</span>
                    </div>

                    <table className="sheet-table">
                      <thead>
                        <tr>
                          <th style={{ width: "32px" }}></th>
                          <th>A (Name)</th>
                          <th>B (Email)</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr>
                          <td className="row-num">1</td>
                          <td>Alex Rivera</td>
                          <td>alex@mail.com</td>
                        </tr>
                        <tr>
                          <td className="row-num">2</td>
                          <td>Mia Chen</td>
                          <td>mia@mail.com</td>
                        </tr>
                        <tr
                          className={`sheet-target-row ${
                            destPopulated ? "row-highlighted" : "row-empty"
                          }`}
                        >
                          <td className="row-num">3</td>
                          <td className="cell-filled">
                            {destPopulated ? "Jamie Doe" : ""}
                          </td>
                          <td className="cell-filled">
                            {destPopulated ? "jamie@mail.com" : ""}
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                )}

                {/* Variant B: Workflow Automation (N8N, Make, Webhooks) */}
                {isWorkflow && (
                  <div className="mock-workflow-panel">
                    <div className="mock-workflow-header">
                      <div className="wf-node-icon" style={{ background: app.iconBg, color: app.iconColor }}>
                        <Zap size={14} />
                      </div>
                      <div>
                        <strong>{app.name} Execution</strong>
                        <div style={{ fontSize: "11px", color: "#64748b" }}>POST /webhook/lead</div>
                      </div>
                      {destPopulated && (
                        <span className="wf-badge-success">
                          <Check size={11} /> 200 OK
                        </span>
                      )}
                    </div>
                    <div className="mock-json-box">
                      <pre>
                        {destPopulated
                          ? `{\n  "lead": "Jamie Doe",\n  "email": "jamie@mail.com",\n  "channel": "instagram_dm",\n  "status": "success"\n}`
                          : `{\n  "status": "waiting_trigger"\n}`}
                      </pre>
                    </div>
                  </div>
                )}

                {/* Variant C: Channel / Slack / Discord / Telegram */}
                {isCommunication && (
                  <div className="mock-slack-panel">
                    <div className="mock-slack-header">
                      <strong># new-leads</strong>
                      <span style={{ fontSize: "11px", color: "#94a3b8" }}>channel</span>
                    </div>
                    {destPopulated ? (
                      <div className="mock-slack-msg animate-pop">
                        <div className="slack-bot-avatar" style={{ background: app.iconBg, color: app.iconColor }}>
                          {app.name.slice(0, 1)}
                        </div>
                        <div className="slack-msg-body">
                          <div className="slack-msg-author">
                            Nemio Lead Bot <span className="slack-time">Just now</span>
                          </div>
                          <div className="slack-card-embed">
                            <strong>🎯 New Lead from Instagram</strong>
                            <div>Name: <b>Jamie Doe</b></div>
                            <div>Email: <b>jamie@mail.com</b></div>
                          </div>
                        </div>
                      </div>
                    ) : (
                      <div style={{ fontSize: "12px", color: "#94a3b8", padding: "16px 0", textAlign: "center" }}>
                        Waiting for new conversation lead…
                      </div>
                    )}
                  </div>
                )}

                {/* Variant D: Email / Outlook / Gmail */}
                {isEmail && (
                  <div className="mock-email-panel">
                    <div className="mock-email-header">
                      <span className="explainer-app-mark">{app.logo}</span>
                      <strong>Automated Email Sent</strong>
                    </div>
                    {destPopulated ? (
                      <div className="email-preview-card animate-pop">
                        <div className="email-row"><b>To:</b> jamie@mail.com</div>
                        <div className="email-row"><b>Subject:</b> Here is your free guide! 🎁</div>
                        <div className="email-snippet">
                          Hi Jamie, thank you for reaching out via Instagram! Here is the direct link you requested…
                        </div>
                      </div>
                    ) : (
                      <div style={{ fontSize: "12px", color: "#94a3b8", padding: "16px 0", textAlign: "center" }}>
                        Email queue ready…
                      </div>
                    )}
                  </div>
                )}

                {/* Variant E: Scheduling / Calendly / Cal */}
                {isScheduling && (
                  <div className="mock-cal-panel">
                    <div className="mock-cal-header">
                      <span className="explainer-app-mark">{app.logo}</span>
                      <strong>Calendar Booking</strong>
                    </div>
                    {destPopulated ? (
                      <div className="cal-event-card animate-pop">
                        <div style={{ fontWeight: 700, color: "#0f172a" }}>Strategy Call w/ Jamie Doe</div>
                        <div style={{ fontSize: "12px", color: "#0284c7", marginTop: "2px" }}>Thursday @ 2:30 PM (30 min)</div>
                        <div style={{ fontSize: "11px", color: "#64748b", marginTop: "4px" }}>Confirmed automatically via DM</div>
                      </div>
                    ) : (
                      <div style={{ fontSize: "12px", color: "#94a3b8", padding: "16px 0", textAlign: "center" }}>
                        Slot reserved…
                      </div>
                    )}
                  </div>
                )}

                {/* Variant F: Default CRM Record */}
                {!isSpreadsheet && !isWorkflow && !isCommunication && !isEmail && !isScheduling && (
                  <div className="mock-crm-card">
                    <div className="mock-crm-header">
                      <div className="crm-avatar">JD</div>
                      <div>
                        <strong>{destPopulated ? "Jamie Doe" : "Awaiting Lead..."}</strong>
                        <div style={{ fontSize: "11px", color: "#64748b" }}>
                          {destPopulated ? "jamie@mail.com" : "Synced via automation"}
                        </div>
                      </div>
                      {destPopulated && (
                        <span className="crm-tag-badge">Lead Captured</span>
                      )}
                    </div>
                    {destPopulated && (
                      <div className="crm-sub-details">
                        <div>Source: <b>Instagram DM</b></div>
                        <div>Status: <b style={{ color: "#10b981" }}>New Active Lead</b></div>
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* RIGHT SIDE: Mobile Chat Mockup (Matches Screenshot 2) */}
              <div className="mock-phone-screen">
                {/* Phone Header */}
                <div className="phone-header-bar">
                  <div className="phone-user-info">
                    <ChevronLeft size={16} className="phone-back-icon" />
                    <div className="phone-avatar-circle">
                      <span>J</span>
                    </div>
                    <div>
                      <div className="phone-username">jamie.doe</div>
                      <div className="phone-status">Active now</div>
                    </div>
                  </div>
                  <div className="phone-actions">
                    <Phone size={13} />
                    <Video size={14} />
                  </div>
                </div>

                {/* Messages Body */}
                <div className="phone-chat-body">
                  {/* Bot Prompt Message (Blue Bubble) */}
                  <div className="chat-bubble bot-bubble">
                    What&apos;s your name &amp; email? I&apos;ll send the guide 🎁
                  </div>

                  {/* User Reply Bubble (Gray Bubble) */}
                  {userMessageSent && (
                    <div className="chat-bubble user-bubble animate-message-pop">
                      Jamie Doe
                    </div>
                  )}

                  {/* Simulated Data Flying Packet */}
                  {dataDropping && (
                    <div className="flying-data-droplet">
                      <span>jamie@mail.com</span>
                    </div>
                  )}
                </div>

                {/* Phone Bottom Input */}
                <div className="phone-bottom-input">
                  <div className="input-photo-icon">
                    <MessageSquare size={13} />
                  </div>
                  <span className="input-placeholder-text">
                    {chatTyping ? "Jamie Doe| " : "Message..."}
                  </span>
                  <div className={`input-send-icon ${chatTyping ? "active-send" : ""}`}>
                    <Send size={12} />
                  </div>
                </div>
              </div>
            </div>

            <div className="explainer-frame-caption">
              <span>Step 2: Customer messages in chat ➔ Data is instantly dropped into <strong>{app.name}</strong></span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
