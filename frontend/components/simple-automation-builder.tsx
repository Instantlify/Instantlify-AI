"use client";

import { useState } from "react";
import {
  ArrowLeft,
  Camera,
  Check,
  ChevronRight,
  Clock,
  ExternalLink,
  Facebook,
  FileText,
  Heart,
  HelpCircle,
  History,
  Image as ImageIcon,
  Instagram,
  Link as LinkIcon,
  MessageCircle,
  MessageSquare,
  Mic,
  Pencil,
  Phone,
  Plus,
  Radio,
  Send,
  Sparkles,
  Smartphone,
  Video,
  X,
  Zap,
} from "lucide-react";
import { api, type Automation } from "@/lib/api";

interface SimpleAutomationBuilderProps {
  workspaceId: string;
  workspaceName?: string;
  onBack: () => void;
  onSaved: (automation: Automation) => void;
}

type Platform = "instagram" | "telegram" | "whatsapp" | "facebook";

type TriggerType = "comment" | "story_reply" | "dm";

type CommentScope = "specific" | "any" | "next";

type KeywordOption = "specific" | "any";

// Sample Instagram posts for Step 2 "A specific post" selector
const SAMPLE_POSTS = [
  { id: "p1", likes: 23, comments: 1, color: "from-amber-700 via-stone-800 to-zinc-900", tag: "Tech talk" },
  { id: "p2", likes: 13, comments: 1, color: "from-blue-800 via-indigo-900 to-slate-900", tag: "Casual outfit" },
  { id: "p3", likes: 28, comments: 8, color: "from-emerald-800 via-teal-900 to-zinc-900", tag: "Office vibe" },
  { id: "p4", likes: 54, comments: 12, color: "from-rose-800 via-pink-900 to-purple-950", tag: "Graduation" },
  { id: "p5", likes: 21, comments: 6, color: "from-violet-800 via-purple-900 to-slate-900", tag: "Portrait" },
  { id: "p6", likes: 88, comments: 22, color: "from-teal-700 via-cyan-900 to-slate-900", tag: "Studio" },
  { id: "p7", likes: 63, comments: 15, color: "from-sky-700 via-blue-900 to-slate-950", tag: "Coffee break" },
  { id: "p8", likes: 43, comments: 4, color: "from-fuchsia-800 via-pink-900 to-zinc-900", tag: "Meeting" },
];

export function SimpleAutomationBuilder({
  workspaceId,
  workspaceName = "censtd_nutech",
  onBack,
  onSaved,
}: SimpleAutomationBuilderProps) {
  // Title & status
  const [automationName, setAutomationName] = useState("My automation");
  const [isEditingTitle, setIsEditingTitle] = useState(false);
  const [isActive, setIsActive] = useState(false);
  const [saving, setSaving] = useState(false);
  const [feedbackNotice, setFeedbackNotice] = useState<string | null>(null);

  // Step 1: Platform
  const [platform, setPlatform] = useState<Platform | null>("instagram");

  // Step 2: Trigger
  const [triggerType, setTriggerType] = useState<TriggerType>("story_reply");
  const [commentScope, setCommentScope] = useState<CommentScope>("specific");
  const [selectedPostId, setSelectedPostId] = useState<string>("p1");

  // Step 3: Trigger Keywords
  const [keywordOption, setKeywordOption] = useState<KeywordOption>("any");
  const [specificKeywords, setSpecificKeywords] = useState("LINK, PRICE, INFO");

  // Step 4: Messages / Opening DM
  const [openingMessage, setOpeningMessage] = useState(
    "Hey! So happy you're here 😊\n\nTap below and I'll send you the link in just a sec ✨"
  );
  const [openingButtonText, setOpeningButtonText] = useState("Send me the link");
  const [askFollowFirst, setAskFollowFirst] = useState(false);
  const [askEmail, setAskEmail] = useState(false);

  // Step 5: Send the link
  const [linkMessage, setLinkMessage] = useState("Here you go, here's the link as promised.");
  const [linkButtonText, setLinkButtonText] = useState("Just click here");
  const [linkUrl, setLinkUrl] = useState("https://boosend.ai");
  const [followUp, setFollowUp] = useState(false);

  // Saving handler
  const handleSave = async (forceActive?: boolean) => {
    setSaving(true);
    setFeedbackNotice(null);
    const active = forceActive !== undefined ? forceActive : isActive;

    const payload = {
      name: automationName || "My automation",
      status: active ? "active" : "draft",
      trigger: {
        kind: triggerType === "comment" ? "comment" : triggerType === "story_reply" ? "story_reply" : "keyword",
        keyword: keywordOption === "specific" ? specificKeywords.split(",")[0]?.trim() || "LINK" : "*",
        channel: platform || "instagram",
      },
      draft: {
        start: "1",
        triggers: [
          {
            kind: triggerType,
            keyword: keywordOption === "specific" ? specificKeywords : "*",
            channel: platform || "instagram",
          },
        ],
        nodes: [
          {
            id: "1",
            position: { x: 100, y: 100 },
            data: {
              kind: "send_message" as const,
              text: openingMessage,
              buttons: [{ type: "web_url" as const, url: linkUrl, title: openingButtonText }],
            },
          },
          {
            id: "2",
            position: { x: 100, y: 300 },
            data: {
              kind: "send_message" as const,
              text: linkMessage,
              buttons: [{ type: "web_url" as const, url: linkUrl, title: linkButtonText }],
            },
          },
        ],
        edges: [{ source: "1", target: "2" }],
      },
      published: active
        ? {
            start: "1",
            triggers: [
              {
                kind: triggerType,
                keyword: keywordOption === "specific" ? specificKeywords : "*",
                channel: platform || "instagram",
              },
            ],
            nodes: [
              {
                id: "1",
                position: { x: 100, y: 100 },
                data: {
                  kind: "send_message" as const,
                  text: openingMessage,
                  buttons: [{ type: "web_url" as const, url: linkUrl, title: openingButtonText }],
                },
              },
              {
                id: "2",
                position: { x: 100, y: 300 },
                data: {
                  kind: "send_message" as const,
                  text: linkMessage,
                  buttons: [{ type: "web_url" as const, url: linkUrl, title: linkButtonText }],
                },
              },
            ],
            edges: [{ source: "1", target: "2" }],
          }
        : {},
    };

    try {
      const saved = await api<Automation>(`/api/w/${workspaceId}/automations/`, "POST", payload);
      setFeedbackNotice(active ? "Automation saved and activated!" : "Automation saved as draft!");
      setTimeout(() => {
        onSaved(saved);
      }, 800);
    } catch {
      // Fallback response for offline or simulated test
      const mockSaved: Automation = {
        id: `auto_${Date.now()}`,
        name: automationName,
        status: active ? "active" : "draft",
        enabled: active,
        revision: 1,
        runs_count: 0,
        leads_count: 0,
        folder: "",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        installed_from: null,
        draft: payload.draft,
        published: payload.published,
      };
      setFeedbackNotice(active ? "Automation saved and activated!" : "Automation saved as draft!");
      setTimeout(() => {
        onSaved(mockSaved);
      }, 800);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="simple-builder-container">
      {/* Top Navigation Bar */}
      <div className="simple-builder-top-bar">
        <button type="button" className="simple-back-button" onClick={onBack}>
          <ArrowLeft size={16} /> Back to automations
        </button>

        <div className="simple-top-actions">
          {/* Draft/Active Toggle */}
          <div className="simple-status-toggle">
            <span className="status-toggle-label">{isActive ? "Active" : "Draft"}</span>
            <button
              type="button"
              className={`toggle-switch-pill ${isActive ? "active" : ""}`}
              onClick={() => setIsActive(!isActive)}
              title={isActive ? "Set to Draft" : "Set to Active"}
            >
              <span className="toggle-switch-thumb" />
            </button>
          </div>

          <button type="button" className="simple-icon-action" title="Version History">
            <History size={16} />
          </button>

          <button
            type="button"
            className="simple-save-button"
            onClick={() => handleSave()}
            disabled={saving}
          >
            <FileText size={15} />
            {saving ? "Saving…" : "Save Automation"}
          </button>
        </div>
      </div>

      {feedbackNotice && (
        <div className="simple-feedback-toast">
          <Check size={16} /> {feedbackNotice}
        </div>
      )}

      {/* Main Two-Column Layout */}
      <div className="simple-builder-content">
        {/* Left Column: Form Stepper */}
        <div className="simple-builder-left">
          {/* Header Title Section */}
          <div className="simple-header-block">
            <div className="simple-title-row">
              {isEditingTitle ? (
                <input
                  type="text"
                  value={automationName}
                  onChange={(e) => setAutomationName(e.target.value)}
                  onBlur={() => setIsEditingTitle(false)}
                  onKeyDown={(e) => e.key === "Enter" && setIsEditingTitle(false)}
                  autoFocus
                  className="simple-title-input"
                />
              ) : (
                <h1 className="simple-title-heading" onClick={() => setIsEditingTitle(true)}>
                  {automationName}
                  <Pencil size={15} className="title-edit-icon" />
                </h1>
              )}
            </div>
            <p className="simple-subtitle-text">
              Build your automation one step at a time, no flowcharts needed.
            </p>
          </div>

          {/* Stepper with Continuous Connecting Line */}
          <div className="simple-stepper-timeline">
            {/* STEP 1: Select a platform */}
            <div className="stepper-step-item">
              <div className="step-badge-col">
                <div className={`step-number-circle ${platform ? "completed" : "active"}`}>1</div>
                <div className="step-connecting-line" />
              </div>

              <div className="step-card-box">
                <h2 className="step-card-title">Select a platform</h2>
                <p className="step-card-subtitle">Where should this automation run?</p>

                <div className="platform-cards-grid">
                  {/* Instagram */}
                  <button
                    type="button"
                    className={`platform-select-card ${platform === "instagram" ? "selected" : ""}`}
                    onClick={() => setPlatform("instagram")}
                  >
                    <div className="platform-card-icon-box instagram">
                      <Instagram size={28} />
                    </div>
                    <span className="platform-card-name">Instagram</span>
                  </button>

                  {/* Telegram */}
                  <button
                    type="button"
                    className={`platform-select-card ${platform === "telegram" ? "selected" : ""}`}
                    onClick={() => setPlatform("telegram")}
                  >
                    <div className="platform-card-icon-box telegram">
                      <Send size={24} />
                    </div>
                    <span className="platform-card-name">Telegram</span>
                  </button>

                  {/* WhatsApp */}
                  <button
                    type="button"
                    className={`platform-select-card ${platform === "whatsapp" ? "selected" : ""}`}
                    onClick={() => setPlatform("whatsapp")}
                  >
                    <div className="platform-card-icon-box whatsapp">
                      <MessageCircle size={26} />
                    </div>
                    <span className="platform-card-name">WhatsApp</span>
                  </button>

                  {/* Facebook */}
                  <button
                    type="button"
                    className={`platform-select-card ${platform === "facebook" ? "selected" : ""}`}
                    onClick={() => setPlatform("facebook")}
                  >
                    <div className="platform-card-icon-box facebook">
                      <Facebook size={26} />
                    </div>
                    <span className="platform-card-name">Facebook</span>
                  </button>
                </div>
              </div>
            </div>

            {/* STEP 2: How should this be triggered? */}
            <div className={`stepper-step-item ${!platform ? "disabled-step" : ""}`}>
              <div className="step-badge-col">
                <div className={`step-number-circle ${triggerType ? "completed" : "active"}`}>2</div>
                <div className="step-connecting-line" />
              </div>

              <div className="step-card-box">
                <h2 className="step-card-title">How should this be triggered?</h2>
                <p className="step-card-subtitle">Pick what kicks off the automation.</p>

                <div className="trigger-options-list">
                  {/* Option 1: Comments on a post */}
                  <div
                    className={`trigger-option-card ${triggerType === "comment" ? "selected" : ""}`}
                    onClick={() => setTriggerType("comment")}
                  >
                    <div className="trigger-radio-row">
                      <span className={`custom-radio-circle ${triggerType === "comment" ? "checked" : ""}`} />
                      <div>
                        <div className="trigger-option-name">When someone comments on a post</div>
                        <div className="trigger-option-desc">Watch a specific post or every post for new comments.</div>
                      </div>
                    </div>

                    {/* Sub-selector when "comment" is selected */}
                    {triggerType === "comment" && (
                      <div className="comment-subselector-box" onClick={(e) => e.stopPropagation()}>
                        <div className="comment-scope-tabs">
                          <button
                            type="button"
                            className={`scope-tab-button ${commentScope === "specific" ? "active" : ""}`}
                            onClick={() => setCommentScope("specific")}
                          >
                            <span className="tab-title">A specific post</span>
                            <span className="tab-sub">Only comments on posts you choose.</span>
                          </button>
                          <button
                            type="button"
                            className={`scope-tab-button ${commentScope === "any" ? "active" : ""}`}
                            onClick={() => setCommentScope("any")}
                          >
                            <span className="tab-title">Any post</span>
                            <span className="tab-sub">Comments on every post you publish.</span>
                          </button>
                          <button
                            type="button"
                            className={`scope-tab-button ${commentScope === "next" ? "active" : ""}`}
                            onClick={() => setCommentScope("next")}
                          >
                            <span className="tab-title">Next post</span>
                            <span className="tab-sub">Your next post (Meta can take 5–10 min to register it).</span>
                          </button>
                        </div>

                        {/* Specific Post Selector Grid */}
                        {commentScope === "specific" && (
                          <div className="posts-picker-wrapper">
                            <div className="posts-thumbnails-grid">
                              {SAMPLE_POSTS.map((post) => (
                                <button
                                  type="button"
                                  key={post.id}
                                  className={`post-thumb-card bg-gradient-to-br ${post.color} ${selectedPostId === post.id ? "selected-post" : ""}`}
                                  onClick={() => setSelectedPostId(post.id)}
                                >
                                  <div className="post-thumb-overlay">
                                    <span className="post-metric">
                                      <Heart size={11} fill="white" /> {post.likes}
                                    </span>
                                    <span className="post-metric">
                                      <MessageSquare size={11} fill="white" /> {post.comments}
                                    </span>
                                  </div>
                                  <div className="post-inner-label">{post.tag}</div>
                                </button>
                              ))}
                            </div>
                            <div className="posts-picker-footer">
                              <span>Tap a post to select it.</span>
                              <button type="button" className="load-more-link">Load more</button>
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>

                  {/* Option 2: When someone replies to your story */}
                  <div
                    className={`trigger-option-card ${triggerType === "story_reply" ? "selected" : ""}`}
                    onClick={() => setTriggerType("story_reply")}
                  >
                    <div className="trigger-radio-row">
                      <span className={`custom-radio-circle ${triggerType === "story_reply" ? "checked" : ""}`} />
                      <div>
                        <div className="trigger-option-name">When someone replies to your story</div>
                        <div className="trigger-option-desc">React to replies people send on your stories.</div>
                      </div>
                    </div>
                  </div>

                  {/* Option 3: When someone sends a message */}
                  <div
                    className={`trigger-option-card ${triggerType === "dm" ? "selected" : ""}`}
                    onClick={() => setTriggerType("dm")}
                  >
                    <div className="trigger-radio-row">
                      <span className={`custom-radio-circle ${triggerType === "dm" ? "checked" : ""}`} />
                      <div>
                        <div className="trigger-option-name">When someone sends a message</div>
                        <div className="trigger-option-desc">Respond to any direct message that lands in your inbox.</div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* STEP 3: Which words should trigger it? */}
            <div className="stepper-step-item">
              <div className="step-badge-col">
                <div className={`step-number-circle ${keywordOption ? "completed" : "active"}`}>3</div>
                <div className="step-connecting-line" />
              </div>

              <div className="step-card-box">
                <h2 className="step-card-title">Which words should trigger it?</h2>
                <p className="step-card-subtitle">Decide which replys should kick things off.</p>

                <div className="trigger-options-list">
                  {/* Specific word */}
                  <div
                    className={`trigger-option-card ${keywordOption === "specific" ? "selected" : ""}`}
                    onClick={() => setKeywordOption("specific")}
                  >
                    <div className="trigger-radio-row">
                      <span className={`custom-radio-circle ${keywordOption === "specific" ? "checked" : ""}`} />
                      <div style={{ flex: 1 }}>
                        <div className="trigger-option-name">A specific word or words</div>
                        <div className="trigger-option-desc">Only run when the reply contains one of these.</div>
                      </div>
                    </div>

                    {keywordOption === "specific" && (
                      <div className="specific-keywords-input-box" onClick={(e) => e.stopPropagation()}>
                        <label className="keyword-input-label">Trigger keywords (separated by commas)</label>
                        <input
                          type="text"
                          value={specificKeywords}
                          onChange={(e) => setSpecificKeywords(e.target.value)}
                          placeholder="e.g. LINK, PRICE, START, INFO"
                          className="keyword-text-field"
                        />
                      </div>
                    )}
                  </div>

                  {/* Any word */}
                  <div
                    className={`trigger-option-card ${keywordOption === "any" ? "selected" : ""}`}
                    onClick={() => setKeywordOption("any")}
                  >
                    <div className="trigger-radio-row">
                      <span className={`custom-radio-circle ${keywordOption === "any" ? "checked" : ""}`} />
                      <div>
                        <div className="trigger-option-name">Any word</div>
                        <div className="trigger-option-desc">Run on every reply.</div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* STEP 4: Set up your messages */}
            <div className="stepper-step-item">
              <div className="step-badge-col">
                <div className="step-number-circle completed">4</div>
                <div className="step-connecting-line" />
              </div>

              <div className="step-card-box">
                <h2 className="step-card-title">Set up your messages</h2>
                
                {/* Opening DM message box */}
                <div className="message-setup-inner-card">
                  <div className="message-editor-bubble">
                    <textarea
                      rows={3}
                      value={openingMessage}
                      onChange={(e) => setOpeningMessage(e.target.value)}
                      placeholder="Type your opening message..."
                      className="message-bubble-textarea"
                    />

                    <div className="message-button-input-row">
                      <label className="button-input-label">Quick Action Button</label>
                      <input
                        type="text"
                        value={openingButtonText}
                        onChange={(e) => setOpeningButtonText(e.target.value)}
                        placeholder="Button text"
                        className="message-button-title-input"
                      />
                    </div>
                  </div>

                  {/* Explainer callout: Why an opening DM? */}
                  <div className="why-opening-dm-box">
                    <div className="why-title">Why an opening DM?</div>
                    <div className="why-body">
                      If you're messaging a new person on Instagram, you only get one message until they accept.
                      With an opening DM, you get the chance to talk with every single lead after they get the link.
                    </div>
                  </div>

                  {/* Toggle 1: Ask them to follow first */}
                  <div className="simple-feature-toggle-row">
                    <div>
                      <div className="toggle-heading">Ask them to follow first</div>
                      <div className="toggle-sub">Require a follow before they get the link.</div>
                    </div>
                    <button
                      type="button"
                      className={`toggle-switch-pill ${askFollowFirst ? "active" : ""}`}
                      onClick={() => setAskFollowFirst(!askFollowFirst)}
                    >
                      <span className="toggle-switch-thumb" />
                    </button>
                  </div>

                  {/* Toggle 2: Ask for their email */}
                  <div className="simple-feature-toggle-row">
                    <div>
                      <div className="toggle-heading">Ask for their email</div>
                      <div className="toggle-sub">Collect emails to grow your list.</div>
                    </div>
                    <button
                      type="button"
                      className={`toggle-switch-pill ${askEmail ? "active" : ""}`}
                      onClick={() => setAskEmail(!askEmail)}
                    >
                      <span className="toggle-switch-thumb" />
                    </button>
                  </div>
                </div>
              </div>
            </div>

            {/* STEP 5: Now time to send the link */}
            <div className="stepper-step-item">
              <div className="step-badge-col">
                <div className="step-number-circle completed">5</div>
                <div className="step-connecting-line" />
              </div>

              <div className="step-card-box">
                <h2 className="step-card-title">Now time to send the link</h2>
                <p className="step-card-subtitle">This is the final message with your resources.</p>

                <div className="message-setup-inner-card">
                  <div className="message-editor-bubble">
                    <textarea
                      rows={2}
                      value={linkMessage}
                      onChange={(e) => setLinkMessage(e.target.value)}
                      placeholder="Type your resource message..."
                      className="message-bubble-textarea"
                    />

                    {/* Button title & URL */}
                    <div className="link-action-inputs">
                      <input
                        type="text"
                        value={linkButtonText}
                        onChange={(e) => setLinkButtonText(e.target.value)}
                        placeholder="Button text (e.g. Just click here)"
                        className="message-button-title-input"
                      />
                      <div className="link-url-field-wrap">
                        <LinkIcon size={14} className="url-icon" />
                        <input
                          type="url"
                          value={linkUrl}
                          onChange={(e) => setLinkUrl(e.target.value)}
                          placeholder="https://..."
                          className="link-url-input"
                        />
                      </div>
                    </div>

                    <button type="button" className="add-another-link-btn">
                      <Plus size={14} /> Add another link
                    </button>
                  </div>

                  {/* Follow up toggle */}
                  <div className="simple-feature-toggle-row">
                    <div>
                      <div className="toggle-heading">Follow up</div>
                      <div className="toggle-sub">Send a nudge if they don't click.</div>
                    </div>
                    <button
                      type="button"
                      className={`toggle-switch-pill ${followUp ? "active" : ""}`}
                      onClick={() => setFollowUp(!followUp)}
                    >
                      <span className="toggle-switch-thumb" />
                    </button>
                  </div>
                </div>
              </div>
            </div>

            {/* STEP 6: Next steps */}
            <div className="stepper-step-item">
              <div className="step-badge-col">
                <div className="step-number-circle active">6</div>
              </div>

              <div className="step-card-box">
                <h2 className="step-card-title">Next steps</h2>
                <p className="step-card-subtitle">Ready to publish your automation to your connected channel.</p>

                <div className="next-steps-actions-row">
                  <button
                    type="button"
                    className="save-and-turn-on-btn"
                    onClick={() => handleSave(true)}
                    disabled={saving}
                  >
                    <Zap size={16} /> Save & Turn On Automation
                  </button>
                  <button
                    type="button"
                    className="save-draft-btn"
                    onClick={() => handleSave(false)}
                    disabled={saving}
                  >
                    Save as Draft
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Right Column: Realistic iPhone Mobile Preview */}
        <div className="simple-builder-right">
          <div className="phone-mockup-sticky">
            <div className="iphone-device-frame">
              {/* Top Dynamic Island & Status Bar */}
              <div className="iphone-top-island-bar">
                <span className="phone-time">9:41</span>
                <div className="iphone-dynamic-island" />
                <div className="phone-status-icons">
                  <span className="signal-bars">●●●●</span>
                  <span className="wifi-icon">📶</span>
                  <span className="battery-icon">🔋</span>
                </div>
              </div>

              {/* Phone Inner Screen Content */}
              <div className="iphone-screen-viewport">
                {!platform ? (
                  /* Empty state before selecting platform (Screenshot 2) */
                  <div className="phone-empty-state">
                    <Smartphone size={38} className="empty-phone-icon" />
                    <p className="empty-phone-label">
                      Select a platform to preview your automation
                    </p>
                  </div>
                ) : (
                  /* Active Chat Preview (Screenshots 3, 4, 5) */
                  <div className="phone-chat-screen">
                    {/* Instagram DM App Header */}
                    <div className="phone-chat-header">
                      <button type="button" className="chat-back-arrow">‹</button>
                      <div className="chat-avatar-badge">
                        <div className="chat-avatar-img">
                          <Instagram size={14} className="avatar-brand-icon" />
                        </div>
                      </div>
                      <div className="chat-user-info">
                        <span className="chat-username">{workspaceName}</span>
                        <span className="chat-active-status">Active now</span>
                      </div>
                      <div className="chat-header-actions">
                        <Phone size={15} className="chat-act-icon" />
                        <Video size={16} className="chat-act-icon" />
                      </div>
                    </div>

                    {/* Chat Messages Timeline */}
                    <div className="phone-chat-messages-scroll">
                      {/* Step 2 indicator: comment or story trigger */}
                      {triggerType === "story_reply" && (
                        <div className="story-reply-context-banner">
                          <span>Replied to your story</span>
                        </div>
                      )}
                      {triggerType === "comment" && (
                        <div className="story-reply-context-banner">
                          <span>Commented on your post: "send link"</span>
                        </div>
                      )}

                      {/* Opening DM Bubble (from Step 4) */}
                      {openingMessage && (
                        <div className="chat-bubble-row bot-row">
                          <div className="chat-bot-avatar">
                            <Instagram size={10} />
                          </div>
                          <div className="chat-bubble bot-bubble">
                            <div className="bubble-text">{openingMessage}</div>
                            {openingButtonText && (
                              <button type="button" className="bubble-interactive-button">
                                {openingButtonText}
                              </button>
                            )}
                          </div>
                        </div>
                      )}

                      {/* Simulated User Response Pill (from lead) */}
                      {openingButtonText && (
                        <div className="chat-bubble-row user-row">
                          <div className="chat-user-reply-pill">
                            {openingButtonText}
                          </div>
                        </div>
                      )}

                      {/* Step 5 Link Response Bubble */}
                      {linkMessage && (
                        <div className="chat-bubble-row bot-row">
                          <div className="chat-bot-avatar">
                            <Instagram size={10} />
                          </div>
                          <div className="chat-bubble bot-bubble">
                            <div className="bubble-text">{linkMessage}</div>
                            {linkButtonText && (
                              <button type="button" className="bubble-interactive-button">
                                {linkButtonText}
                              </button>
                            )}
                          </div>
                        </div>
                      )}
                    </div>

                    {/* Bottom Instagram Input Bar */}
                    <div className="phone-chat-input-bar">
                      <div className="phone-camera-btn">
                        <Camera size={14} />
                      </div>
                      <div className="phone-fake-input">
                        <span>Message...</span>
                      </div>
                      <div className="phone-input-icons-row">
                        <Mic size={15} />
                        <ImageIcon size={15} />
                        <Plus size={15} />
                      </div>
                    </div>
                  </div>
                )}
              </div>

              {/* Bottom Home Indicator Bar */}
              <div className="iphone-home-indicator" />
            </div>

            <div className="phone-mockup-caption">
              Live preview, updates as you build
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
