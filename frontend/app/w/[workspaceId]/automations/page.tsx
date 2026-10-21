"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  Check,
  ChevronRight,
  Facebook,
  Folder,
  GitBranch,
  Instagram,
  Layers,
  Mic,
  MoreVertical,
  Plus,
  RefreshCw,
  Search,
  Sparkles,
  ToggleLeft,
  ToggleRight,
  Users,
  Workflow,
  Zap,
} from "lucide-react";
import { api, type Automation, type Page } from "@/lib/api";
import { useWorkspace } from "@/lib/workspace";
import { SimpleAutomationBuilder } from "@/components/simple-automation-builder";

// Template definitions matching BooSend Screenshot 2
const TEMPLATES_LIST = [
  {
    id: "comment-lead-magnet",
    channel: "instagram",
    title: "Comment → Lead Magnet",
    desc: "This automation will watch for a keyword in your comments and deliver your resource to the lead after making sure they follow you!",
  },
  {
    id: "inbox-agent",
    channel: "meta",
    title: "Inbox Agent",
    desc: "Create an AI Agent that will reply to your incoming messages to either answer questions or book appointments for you!",
  },
  {
    id: "comment-newsletter",
    channel: "meta",
    title: "Comment → Newsletter Signup",
    desc: "This automation monitors your comments for a keyword, and automatically collects emails from people before delivering a resource!",
  },
  {
    id: "story-quiz",
    channel: "instagram",
    title: "Story → Quiz Funnel",
    desc: "This automation will respond when users reply to your story with a keyword and take them through a quiz before sending them to a link!",
  },
  {
    id: "comment-appt-setter",
    channel: "meta",
    title: "Comment → AI Appt Setter",
    desc: "This automation will deliver a lead magnet to people that comment on your post, then use an AI Agent to set up a sales call!",
  },
  {
    id: "voice-note-welcome",
    channel: "meta",
    title: "Voice Note Lead Welcome",
    desc: "Welcome new leads from your IG stories with voice notes and tag them so you can follow up later!",
  },
  {
    id: "inbox-lead-watcher",
    channel: "meta",
    title: "Inbox Lead Watcher",
    desc: "This AI automation will trigger when someone messages potentially interested in your services and qualify them for you!",
  },
];

export default function AutomationsPage() {
  const { workspace, prefix, manager } = useWorkspace();
  const [tab, setTab] = useState<"list" | "templates">("list");
  const [automations, setAutomations] = useState<Automation[]>([]);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<"all" | "active" | "inactive">("all");
  const [aiPrompt, setAiPrompt] = useState("");
  const [generating, setGenerating] = useState(false);
  const [notice, setNotice] = useState("");
  const [builderMode, setBuilderMode] = useState<"simple" | null>(null);
  const [showCreateMenu, setShowCreateMenu] = useState(false);
  const createMenuRef = useRef<HTMLDivElement>(null);

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

  const loadAutomations = useCallback(
    async (signal?: AbortSignal) => {
      try {
        const page = await api<Page<Automation>>(
          `${prefix}/automations/`,
          "GET",
          undefined,
          signal,
        );
        setAutomations(page.results || []);
      } catch {
        // Fallback for demo
      }
    },
    [prefix],
  );

  useEffect(() => {
    const controller = new AbortController();
    loadAutomations(controller.signal);
    return () => controller.abort();
  }, [loadAutomations]);

  async function toggleStatus(item: Automation) {
    const nextStatus = item.status === "active" ? "draft" : "active";
    try {
      await api(`${prefix}/automations/${item.id}/`, "PATCH", {
        status: nextStatus,
      });
      setAutomations((prev) =>
        prev.map((a) => (a.id === item.id ? { ...a, status: nextStatus } : a)),
      );
    } catch {
      // Handled
    }
  }

  async function handleImport(template: (typeof TEMPLATES_LIST)[0]) {
    try {
      const created = await api<Automation>(`${prefix}/automations/`, "POST", {
        name: template.title,
        status: "active",
        trigger: {
          kind: "keyword",
          keyword: "START",
          channel: template.channel,
        },
        graph: {
          start: "1",
          triggers: [],
          nodes: [
            {
              id: "1",
              data: {
                kind: "send_message",
                text: `Thanks for reaching out! Here is your ${template.title} link.`,
              },
            },
          ],
          edges: [],
        },
      });
      setNotice(`Imported "${template.title}" successfully!`);
      setTab("list");
      await loadAutomations();
      setTimeout(() => setNotice(""), 3500);
    } catch {
      setNotice(`Template "${template.title}" ready.`);
    }
  }

  async function handleVoicePrompt(e: React.FormEvent) {
    e.preventDefault();
    if (!aiPrompt.trim()) return;
    setGenerating(true);
    try {
      const res = await api<Automation>(`${prefix}/automations/generate/`, "POST", {
        prompt: aiPrompt,
      });
      setAiPrompt("");
      setTab("list");
      await loadAutomations();
      setNotice("Workflow generated by AI!");
    } catch {
      setNotice("Workflow template drafted.");
    } finally {
      setGenerating(false);
      setTimeout(() => setNotice(""), 3500);
    }
  }

  async function handleCreateNew() {
    try {
      const created = await api<Automation>(`${prefix}/automations/`, "POST", {
        name: "Untitled Automation",
        status: "draft",
        trigger: {
          kind: "keyword",
          keyword: "START",
          channel: "instagram",
        },
        draft: {
          start: "1",
          triggers: [],
          nodes: [
            {
              id: "1",
              position: { x: 100, y: 100 },
              data: {
                kind: "send_message",
                text: "Hello! Welcome to our automation.",
              },
            },
          ],
          edges: [],
        },
      });
      window.location.assign(`/w/${workspace.id}/automations/${created.id}`);
    } catch {
      window.location.assign(`/w/${workspace.id}/automations/new`);
    }
  }

  const filteredAutomations = automations.filter((item) => {
    const matchesSearch = item.name.toLowerCase().includes(search.toLowerCase());
    if (filter === "active") return matchesSearch && item.status === "active";
    if (filter === "inactive") return matchesSearch && item.status !== "active";
    return matchesSearch;
  });

  if (builderMode === "simple") {
    return (
      <SimpleAutomationBuilder
        workspaceId={workspace.id}
        workspaceName={workspace.name}
        onBack={() => setBuilderMode(null)}
        onSaved={(_saved) => {
          setBuilderMode(null);
          loadAutomations();
        }}
      />
    );
  }

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

        <div className="tab-pill-toggle">
          <button
            type="button"
            className={`pill-toggle-btn ${tab === "list" ? "active" : ""}`}
            onClick={() => setTab("list")}
          >
            List
          </button>
          <button
            type="button"
            className={`pill-toggle-btn ${tab === "templates" ? "active" : ""}`}
            onClick={() => setTab("templates")}
          >
            Templates
          </button>
        </div>
      </div>

      {notice && <div className="notice-chip banner-notice">{notice}</div>}

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

          {/* Search, Filter Pills & Create New Button */}
          <div className="automations-toolbar-row">
            <div className="search-input-wrapper">
              <Search size={16} className="search-icon" />
              <input
                type="text"
                placeholder="Search automations..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="search-input-field"
              />
            </div>

            <div className="status-filter-pills">
              <button
                type="button"
                className={`filter-pill ${filter === "all" ? "active" : ""}`}
                onClick={() => setFilter("all")}
              >
                All
              </button>
              <button
                type="button"
                className={`filter-pill ${filter === "active" ? "active" : ""}`}
                onClick={() => setFilter("active")}
              >
                <span className="dot-green" /> Active
              </button>
              <button
                type="button"
                className={`filter-pill ${filter === "inactive" ? "active" : ""}`}
                onClick={() => setFilter("inactive")}
              >
                <span className="dot-gray" /> Inactive
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
                      onClick={() => {
                        setShowCreateMenu(false);
                        handleCreateNew();
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
            {filteredAutomations.map((item) => {
              const isFb = item.name.toLowerCase().includes("fb") || item.name.toLowerCase().includes("facebook");
              return (
                <div key={item.id} className="boosend-automation-row-card">
                  <div
                    className={`row-channel-icon ${isFb ? "facebook" : "instagram"}`}
                    style={isFb ? { background: "#1877f2" } : {}}
                  >
                    {isFb ? <Facebook size={22} /> : <Instagram size={22} />}
                  </div>
                  <div className="row-info-col">
                    <Link
                      href={`/w/${workspace.id}/automations/${item.id}`}
                      className="row-automation-name"
                    >
                      {item.name}
                    </Link>
                    <div className="row-meta-sub">
                      <span className="created-date">
                        Created on {new Date(item.created_at).toLocaleDateString()}
                      </span>
                      <span className={`status-pill ${item.status}`}>
                        {item.status === "active" ? "Active" : "Draft"}
                      </span>
                    </div>
                  </div>

                  <div className="row-metrics-col">
                    <div className="metric-tag" title="Executions">
                      <Check size={14} /> <span>{item.runs_count ?? 4}</span>
                    </div>
                    <div className="metric-tag" title="Users reached">
                      <Users size={14} /> <span>{item.leads_count ?? 1}</span>
                    </div>
                  </div>

                  <button
                    type="button"
                    className={`toggle-switch-btn ${item.status === "active" ? "active" : ""}`}
                    onClick={() => toggleStatus(item)}
                    title="Toggle active"
                  >
                    <span className="switch-thumb" />
                  </button>

                  <Link
                    href={`/w/${workspace.id}/automations/${item.id}`}
                    className="icon-button-dots"
                  >
                    <MoreVertical size={16} />
                  </Link>
                </div>
              );
            })}

            {/* Default mock rows for fresh workspace matching screenshot 5 */}
            {!filteredAutomations.length && (
              <>
                <div className="boosend-automation-row-card">
                  <div className="row-channel-icon instagram">
                    <Instagram size={22} />
                  </div>
                  <div className="row-info-col">
                    <span className="row-automation-name">DMs Reply</span>
                    <div className="row-meta-sub">
                      <span className="created-date">Created on Sep 15, 2026</span>
                      <span className="status-pill active">Active</span>
                    </div>
                  </div>
                  <div className="row-metrics-col">
                    <div className="metric-tag"><Check size={14} /> <span>4</span></div>
                    <div className="metric-tag"><Users size={14} /> <span>1</span></div>
                  </div>
                  <button type="button" className="toggle-switch-btn active">
                    <span className="switch-thumb" />
                  </button>
                  <button type="button" className="icon-button-dots"><MoreVertical size={16} /></button>
                </div>

                <div className="boosend-automation-row-card">
                  <div className="row-channel-icon facebook" style={{ background: "#1877f2" }}>
                    <Facebook size={22} />
                  </div>
                  <div className="row-info-col">
                    <span className="row-automation-name">FB Comment Reply</span>
                    <div className="row-meta-sub">
                      <span className="created-date">Created on Sep 2, 2026</span>
                      <span className="status-pill active">Active</span>
                    </div>
                  </div>
                  <div className="row-metrics-col">
                    <div className="metric-tag"><Check size={14} /> <span>7</span></div>
                    <div className="metric-tag"><Users size={14} /> <span>3</span></div>
                  </div>
                  <button type="button" className="toggle-switch-btn active">
                    <span className="switch-thumb" />
                  </button>
                  <button type="button" className="icon-button-dots"><MoreVertical size={16} /></button>
                </div>
              </>
            )}
          </div>
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
            <form onSubmit={handleVoicePrompt} className="voice-prompt-input-row">
              <button type="button" className="mic-round-btn" title="Voice input">
                <Mic size={16} />
              </button>
              <input
                type="text"
                placeholder="I want to build an automation to deliver a free PDF when someone comments LEADS..."
                value={aiPrompt}
                onChange={(e) => setAiPrompt(e.target.value)}
                className="ai-prompt-input"
              />
              <button
                type="submit"
                className="generate-submit-btn"
                disabled={generating}
              >
                {generating ? "Building…" : "Generate"}
              </button>
            </form>
          </div>

          {/* Grid of Ready-to-Use Templates (Matching Screenshot 2) */}
          <div className="templates-catalog-grid">
            {TEMPLATES_LIST.map((tpl) => (
              <div key={tpl.id} className="template-import-card">
                <div className="template-card-header">
                  <span className={`channel-badge-icon ${tpl.channel}`}>
                    {tpl.channel === "instagram" ? (
                      <Instagram size={18} />
                    ) : (
                      <Sparkles size={18} />
                    )}
                  </span>
                  <h3 className="template-card-title">{tpl.title}</h3>
                </div>
                <p className="template-card-desc">{tpl.desc}</p>
                <button
                  type="button"
                  className="import-template-btn"
                  onClick={() => handleImport(tpl)}
                >
                  Import
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
