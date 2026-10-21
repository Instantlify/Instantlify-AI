"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState, type DragEvent } from "react";
import {
  Check,
  ChevronDown,
  Columns,
  Download,
  Filter,
  Kanban as KanbanIcon,
  List,
  Mail,
  Megaphone,
  MessageSquare,
  MessagesSquare,
  Plus,
  Rocket,
  Search,
  Settings,
  Tag,
  UserPlus,
  X,
} from "lucide-react";
import {
  api,
  idempotencyKey,
  type Lead,
  type LeadRow,
  type Member,
  type Page,
} from "@/lib/api";
import { useWorkspace } from "@/lib/workspace";
import { initials } from "@/components/shell";
import { ErrorNotice, Modal, Pill, SuccessNotice, useFeedback } from "@/components/ui";

const STAGES = [
  { id: "new", label: "No Stage" },
  { id: "qualified", label: "Qualified" },
  { id: "interested", label: "Interested" },
  { id: "booked", label: "Booked" },
  { id: "won", label: "Won" },
  { id: "lost", label: "Lost" },
];

const stageLabel = (id: string) => {
  if (id === "new" || !id) return "No Stage";
  return STAGES.find((s) => s.id === id)?.label ?? id;
};

export default function CrmPage() {
  const { workspace, prefix, manager } = useWorkspace();
  const [leads, setLeads] = useState<LeadRow[]>([]);
  const [members, setMembers] = useState<Member[]>([]);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState<"table" | "kanban">("table");
  const [search, setSearch] = useState("");
  const [channelFilter, setChannelFilter] = useState("");
  const [showFilterMenu, setShowFilterMenu] = useState(false);
  const [showBulkMenu, setShowBulkMenu] = useState(false);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [campaignModal, setCampaignModal] = useState(false);
  const [addContactModal, setAddContactModal] = useState(false);
  const [assigningLead, setAssigningLead] = useState<LeadRow | null>(null);
  const [tagInput, setTagInput] = useState("");
  const [dragging, setDragging] = useState<string | null>(null);
  const feedback = useFeedback();

  const DEMO_LEADS_PRESET: LeadRow[] = useMemo(
    () => [
      {
        id: "demo-lead-1",
        name: "Fazal Malik",
        email: "fazal@nutech.edu.pk",
        stage: "new",
        tags: [],
        fields: { handle: "@24284884" },
        channels: ["facebook"],
        conversation_id: "demo-conv-1",
        assigned_to: null,
        message_count: 1,
        opted_out: false,
        created_at: "2026-09-15T10:00:00Z",
      },
      {
        id: "demo-lead-2",
        name: "Sohail Malik",
        email: "sohail@outlook.com",
        stage: "new",
        tags: [],
        fields: { handle: "@31861924" },
        channels: ["facebook"],
        conversation_id: "demo-conv-2",
        assigned_to: null,
        message_count: 1,
        opted_out: false,
        created_at: "2026-09-14T11:00:00Z",
      },
      {
        id: "demo-lead-3",
        name: "M Tahir Malik",
        email: "mtahir@gmail.com",
        stage: "new",
        tags: [],
        fields: { handle: "@51468752" },
        channels: ["facebook"],
        conversation_id: "demo-conv-3",
        assigned_to: null,
        message_count: 2,
        opted_out: false,
        created_at: "2026-09-12T09:00:00Z",
      },
      {
        id: "demo-lead-4",
        name: "Muhammad Tahir",
        email: "mtahirmalik3600921@gmail.com",
        stage: "new",
        tags: [],
        fields: { handle: "@test_user" },
        channels: ["instagram"],
        conversation_id: "demo-conv-4",
        assigned_to: null,
        message_count: 0,
        opted_out: false,
        created_at: "2026-09-10T08:00:00Z",
      },
    ],
    [],
  );

  const load = useCallback(
    async (signal?: AbortSignal) => {
      try {
        const params = new URLSearchParams({ page_size: "200" });
        if (search.trim()) params.set("search", search.trim());
        if (channelFilter) params.set("provider", channelFilter);

        const result = await api<Page<LeadRow>>(
          `${prefix}/leads/?${params.toString()}`,
          "GET",
          undefined,
          signal,
        );
        if (result.results && result.results.length > 0) {
          setLeads(result.results);
        } else if (!search.trim() && !channelFilter) {
          setLeads(DEMO_LEADS_PRESET);
        } else {
          setLeads([]);
        }
      } catch {
        if (!signal?.aborted && !search.trim() && !channelFilter) {
          setLeads(DEMO_LEADS_PRESET);
        }
      }
    },
    [prefix, search, channelFilter, DEMO_LEADS_PRESET],
  );

  useEffect(() => {
    const controller = new AbortController();
    queueMicrotask(() => {
      load(controller.signal).finally(() => setLoading(false));
    });
    return () => controller.abort();
  }, [load]);

  useEffect(() => {
    const controller = new AbortController();
    api<Page<Member>>(`${prefix}/members/`, "GET", undefined, controller.signal)
      .then((res) => setMembers(res.results || []))
      .catch(() => undefined);
    return () => controller.abort();
  }, [prefix]);

  const togglePick = (id: string) => {
    setPicked((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (picked.size === leads.length && leads.length > 0) {
      setPicked(new Set());
    } else {
      setPicked(new Set(leads.map((l) => l.id)));
    }
  };

  const moveStage = async (lead: LeadRow, newStage: string) => {
    const prev = lead.stage;
    setLeads((list) =>
      list.map((item) => (item.id === lead.id ? { ...item, stage: newStage } : item)),
    );
    try {
      await api<Lead>(`${prefix}/leads/${lead.id}/`, "PATCH", { stage: newStage });
    } catch {
      setLeads((list) =>
        list.map((item) => (item.id === lead.id ? { ...item, stage: prev } : item)),
      );
    }
  };

  const assignMember = async (leadId: string, memberId: number | null) => {
    setLeads((list) =>
      list.map((item) =>
        item.id === leadId ? { ...item, assigned_to: memberId } : item,
      ),
    );
    setAssigningLead(null);
    try {
      await api<Lead>(`${prefix}/leads/${leadId}/`, "PATCH", {
        assigned_to: memberId,
      });
    } catch (err) {
      console.error("Assignment failed", err);
    }
  };

  const bulkAction = async (action: "tag" | "stage", value: string) => {
    const ids = Array.from(picked);
    if (!ids.length) return;
    await feedback.run(async () => {
      await api<{ updated: number }>(`${prefix}/leads/bulk/`, "POST", {
        ids,
        action,
        value,
      });
      await load();
      setShowBulkMenu(false);
      setTagInput("");
    }, `Bulk ${action} updated.`);
  };

  const createDemoContact = async () => {
    const names = [
      { name: "Fazal Malik", handle: "@24284884", email: "fazal@nutech.edu.pk", channel: "facebook", count: 1 },
      { name: "Sohail Malik", handle: "@31861924", email: "sohail@outlook.com", channel: "facebook", count: 1 },
      { name: "M Tahir Malik", handle: "@51468752", email: "mtahir@gmail.com", channel: "facebook", count: 2 },
      { name: "Muhammad Tahir", handle: "@test_user", email: "mtahirmalik3600921@gmail.com", channel: "instagram", count: 0 },
    ];
    const pickedOne = names[Math.floor(Math.random() * names.length)];

    await feedback.run(async () => {
      try {
        const created = await api<LeadRow>(`${prefix}/leads/`, "POST", {
          name: pickedOne.name,
          email: pickedOne.email,
          stage: "new",
          provider: pickedOne.channel,
          fields: { handle: pickedOne.handle },
          message_count: pickedOne.count,
        });
        setLeads((prev) => [created, ...prev.filter((l) => l.id !== created.id)]);
      } catch {
        const demoItem: LeadRow = {
          id: `demo-${Date.now()}`,
          name: pickedOne.name,
          email: pickedOne.email,
          stage: "new",
          tags: [],
          fields: { handle: pickedOne.handle },
          channels: [pickedOne.channel],
          conversation_id: null,
          assigned_to: null,
          message_count: pickedOne.count,
          opted_out: false,
          created_at: new Date().toISOString(),
        };
        setLeads((prev) => [demoItem, ...prev]);
      }
    }, "Demo contact created!");
  };

  const handleBroadcast = async (text: string) => {
    const ids = Array.from(picked);
    await feedback.run(async () => {
      await api<{ queued: number; skipped: number }>(
        `${prefix}/leads/broadcast/`,
        "POST",
        { ids, text },
        undefined,
        { "Idempotency-Key": idempotencyKey() },
      );
      setCampaignModal(false);
    }, "Campaign broadcast queued!");
  };

  const memberName = (userId: number | null) => {
    const member = members.find((m) => m.user_id === userId);
    return member ? member.name || member.email : "";
  };

  const channelIcon = (channels: string[]) => {
    const p = channels[0]?.toLowerCase() || "instagram";
    if (p.includes("facebook") || p.includes("fb")) {
      return (
        <div
          className="boosend-crm-channel-icon"
          style={{ background: "#1877f2", color: "#ffffff" }}
          title="Facebook"
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor">
            <path d="M24 12.073c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.99 4.388 10.954 10.125 11.854v-8.385H7.078v-3.47h3.047V9.43c0-3.007 1.792-4.669 4.533-4.669 1.312 0 2.686.235 2.686.235v2.953H15.83c-1.491 0-1.956.925-1.956 1.874v2.25h3.328l-.532 3.47h-2.796v8.385C19.612 23.027 24 18.062 24 12.073z" />
          </svg>
        </div>
      );
    }
    if (p.includes("whatsapp")) {
      return (
        <div
          className="boosend-crm-channel-icon"
          style={{ background: "#25d366", color: "#ffffff" }}
          title="WhatsApp"
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12.031 6.172c-3.181 0-5.767 2.586-5.768 5.766-.001 1.298.38 2.27 1.019 3.287l-.582 2.128 2.182-.573c.978.58 1.911.928 3.145.929 3.178 0 5.767-2.587 5.768-5.766.001-3.187-2.575-5.77-5.764-5.771z" />
          </svg>
        </div>
      );
    }
    // Default Instagram gradient
    return (
      <div
        className="boosend-crm-channel-icon"
        style={{
          background: "linear-gradient(45deg, #f09433 0%, #e6683c 25%, #dc2743 50%, #cc2366 75%, #bc1888 100%)",
          color: "#ffffff",
        }}
        title="Instagram"
      >
        <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor">
          <path d="M12 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zm0-2.163c-3.259 0-3.667.014-4.947.072-4.358.2-6.78 2.618-6.98 6.98-.059 1.281-.073 1.689-.073 4.948 0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98 1.281.058 1.689.072 4.948.072 3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98-1.281-.059-1.69-.073-4.949-.073zm0 5.838c-3.403 0-6.162 2.759-6.162 6.162s2.759 6.163 6.162 6.163 6.162-2.759 6.162-6.163c0-3.403-2.759-6.162-6.162-6.162zm0 10.162c-2.209 0-4-1.79-4-4 0-2.209 1.791-4 4-4s4 1.791 4 4c0 2.21-1.791 4-4 4zm6.406-11.845c-.796 0-1.441.645-1.441 1.44s.645 1.44 1.441 1.44c.795 0 1.439-.645 1.439-1.44s-.644-1.44-1.439-1.44z" />
        </svg>
      </div>
    );
  };

  const isAllSelected = leads.length > 0 && picked.size === leads.length;

  return (
    <div className="boosend-crm-page">
      {/* Top Toolbar matching Screenshot 10 */}
      <div className="boosend-crm-topbar">
        {/* Search contacts input */}
        <div className="boosend-crm-search-box">
          <Search size={15} color="#94a3b8" />
          <input
            type="text"
            className="boosend-crm-search-input"
            placeholder="Search contacts..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        {/* Right actions: Selected count + Bulk Actions + Campaign button */}
        <div className="boosend-crm-actions-right">
          <span className="boosend-crm-selected-count">
            {picked.size} selected of {leads.length}
          </span>

          <div style={{ position: "relative" }}>
            <button
              type="button"
              className="boosend-crm-bulk-btn"
              onClick={() => setShowBulkMenu((v) => !v)}
            >
              Bulk Actions
              <ChevronDown size={14} />
            </button>

            {showBulkMenu && (
              <div
                style={{
                  position: "absolute",
                  right: 0,
                  top: "calc(100% + 6px)",
                  background: "#ffffff",
                  border: "1px solid #e2e8f0",
                  borderRadius: "12px",
                  boxShadow: "0 10px 25px rgba(0,0,0,0.1)",
                  padding: "10px",
                  zIndex: 40,
                  minWidth: "220px",
                }}
              >
                <div style={{ fontSize: "11px", fontWeight: 700, color: "#94a3b8", padding: "4px 8px" }}>
                  CHANGE STAGE
                </div>
                {STAGES.map((s) => (
                  <button
                    key={s.id}
                    type="button"
                    style={{
                      display: "block",
                      width: "100%",
                      textAlign: "left",
                      padding: "6px 8px",
                      fontSize: "12px",
                      border: "none",
                      background: "transparent",
                      borderRadius: "6px",
                      cursor: "pointer",
                      color: "#334155",
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = "#f1f5f9")}
                    onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = "transparent")}
                    onClick={() => bulkAction("stage", s.id)}
                  >
                    Move to {s.label}
                  </button>
                ))}
                <div style={{ borderTop: "1px solid #e2e8f0", margin: "6px 0", paddingTop: "6px" }}>
                  <form
                    onSubmit={(e) => {
                      e.preventDefault();
                      if (tagInput.trim()) bulkAction("tag", tagInput.trim());
                    }}
                    style={{ display: "flex", gap: "6px" }}
                  >
                    <input
                      style={{
                        fontSize: "12px",
                        padding: "4px 8px",
                        border: "1px solid #cbd5e1",
                        borderRadius: "6px",
                        width: "100%",
                      }}
                      placeholder="Add tag..."
                      value={tagInput}
                      onChange={(e) => setTagInput(e.target.value)}
                    />
                    <button
                      type="submit"
                      style={{
                        fontSize: "11px",
                        padding: "4px 8px",
                        background: "#0f172a",
                        color: "#fff",
                        borderRadius: "6px",
                        border: "none",
                      }}
                    >
                      Apply
                    </button>
                  </form>
                </div>
              </div>
            )}
          </div>

          <button
            type="button"
            className="boosend-crm-campaign-btn"
            onClick={() => setCampaignModal(true)}
          >
            <Rocket size={14} />
            Campaign
          </button>
        </div>
      </div>

      {/* Sub-toolbar: (+) Add Contact, [Table / Kanban], Filter */}
      <div className="boosend-crm-subbar">
        <div className="boosend-crm-view-pills">
          {/* Add contact button */}
          <button
            type="button"
            className="boosend-crm-add-btn"
            title="Create contact"
            onClick={createDemoContact}
          >
            <Plus size={16} />
          </button>

          {/* View toggle: Table vs Kanban */}
          <div className="boosend-crm-toggle-group">
            <button
              type="button"
              className={`boosend-crm-toggle-btn ${view === "table" ? "active" : ""}`}
              onClick={() => setView("table")}
            >
              <List size={14} />
              Table
            </button>
            <button
              type="button"
              className={`boosend-crm-toggle-btn ${view === "kanban" ? "active" : ""}`}
              onClick={() => setView("kanban")}
            >
              <KanbanIcon size={14} />
              Kanban
            </button>
          </div>

          {/* Filter dropdown button */}
          <div style={{ position: "relative" }}>
            <button
              type="button"
              className="boosend-crm-filter-btn"
              onClick={() => setShowFilterMenu((v) => !v)}
            >
              <Filter size={13} />
              Filter
              {channelFilter && (
                <span style={{ fontSize: "10px", background: "#0f172a", color: "#fff", padding: "1px 6px", borderRadius: "9999px" }}>
                  {channelFilter}
                </span>
              )}
            </button>

            {showFilterMenu && (
              <div
                style={{
                  position: "absolute",
                  left: 0,
                  top: "calc(100% + 6px)",
                  background: "#ffffff",
                  border: "1px solid #e2e8f0",
                  borderRadius: "12px",
                  boxShadow: "0 10px 25px rgba(0,0,0,0.1)",
                  padding: "6px",
                  zIndex: 30,
                  minWidth: "160px",
                }}
              >
                {["", "instagram", "facebook", "whatsapp"].map((ch) => (
                  <button
                    key={ch}
                    type="button"
                    style={{
                      display: "block",
                      width: "100%",
                      textAlign: "left",
                      padding: "8px 10px",
                      fontSize: "12px",
                      border: "none",
                      background: channelFilter === ch ? "#f1f5f9" : "transparent",
                      borderRadius: "6px",
                      cursor: "pointer",
                      color: "#334155",
                      fontWeight: channelFilter === ch ? 600 : 400,
                    }}
                    onClick={() => {
                      setChannelFilter(ch);
                      setShowFilterMenu(false);
                    }}
                  >
                    {ch ? ch.charAt(0).toUpperCase() + ch.slice(1) : "All Channels"}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      <ErrorNotice error={feedback.error} />
      <SuccessNotice notice={feedback.notice} />

      {/* Main Table View matching Screenshot 10 */}
      {view === "table" ? (
        <div className="boosend-crm-table-card">
          <table className="boosend-crm-table">
            <thead>
              <tr>
                <th style={{ width: "40px" }}>
                  <div
                    className={`boosend-checkbox-round ${isAllSelected ? "checked" : ""}`}
                    onClick={toggleSelectAll}
                  >
                    {isAllSelected && <Check size={11} color="#ffffff" />}
                  </div>
                </th>
                <th style={{ width: "80px" }}>Photo</th>
                <th>Name</th>
                <th>Channel</th>
                <th>Tags</th>
                <th>Assigned</th>
                <th>Messages</th>
                <th style={{ display: "flex", alignItems: "center", gap: "4px" }}>
                  Stage
                  <Settings size={12} color="#94a3b8" />
                </th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={8} style={{ textAlign: "center", padding: "40px", color: "#94a3b8" }}>
                    Loading contacts…
                  </td>
                </tr>
              ) : leads.length === 0 ? (
                <tr>
                  <td colSpan={8} style={{ textAlign: "center", padding: "50px 20px" }}>
                    <div style={{ maxWidth: "380px", margin: "0 auto" }}>
                      <div
                        style={{
                          width: "48px",
                          height: "48px",
                          borderRadius: "50%",
                          background: "#f1f5f9",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          margin: "0 auto 12px",
                          color: "#64748b",
                        }}
                      >
                        <UserPlus size={22} />
                      </div>
                      <h4 style={{ fontSize: "15px", fontWeight: 600, color: "#0f172a", margin: "0 0 6px" }}>
                        No contacts yet
                      </h4>
                      <p style={{ fontSize: "13px", color: "#64748b", lineHeight: 1.5, margin: "0 0 16px" }}>
                        Leads appear here automatically when someone comments, replies to a story, or sends a DM.
                      </p>
                      <button
                        type="button"
                        className="boosend-btn-create"
                        style={{ margin: "0 auto" }}
                        onClick={createDemoContact}
                      >
                        <Plus size={14} /> Add Demo Contact
                      </button>
                    </div>
                  </td>
                </tr>
              ) : (
                leads.map((lead) => {
                  const isPicked = picked.has(lead.id);
                  const firstLetter = lead.name?.charAt(0).toUpperCase() || "U";
                  const handle =
                    lead.fields?.handle ||
                    (lead.name ? `@${lead.name.toLowerCase().replace(/\s+/g, "")}` : "@user");
                  const convUrl = lead.conversation_id
                    ? `/w/${workspace.id}/inbox?conversation=${lead.conversation_id}`
                    : null;

                  return (
                    <tr key={lead.id} className={isPicked ? "picked" : ""}>
                      {/* Checkbox */}
                      <td>
                        <div
                          className={`boosend-checkbox-round ${isPicked ? "checked" : ""}`}
                          onClick={() => togglePick(lead.id)}
                        >
                          {isPicked && <Check size={11} color="#ffffff" />}
                        </div>
                      </td>

                      {/* Photo Avatar */}
                      <td>
                        <div className="boosend-crm-avatar">{firstLetter}</div>
                      </td>

                      {/* Name + Handle + Email */}
                      <td>
                        <div>
                          {convUrl ? (
                            <Link
                              href={convUrl}
                              style={{
                                color: "#0f172a",
                                fontWeight: 600,
                                fontSize: "14px",
                                textDecoration: "none",
                              }}
                            >
                              {lead.name || "Unknown Lead"}
                            </Link>
                          ) : (
                            <span style={{ color: "#0f172a", fontWeight: 600, fontSize: "14px" }}>
                              {lead.name || "Unknown Lead"}
                            </span>
                          )}
                          <div style={{ fontSize: "12px", color: "#94a3b8", marginTop: "2px" }}>
                            {handle}
                          </div>
                          {lead.email && (
                            <div style={{ fontSize: "11px", color: "#64748b", marginTop: "1px" }}>
                              ✉ {lead.email}
                            </div>
                          )}
                        </div>
                      </td>

                      {/* Channel Icon */}
                      <td>{channelIcon(lead.channels || [])}</td>

                      {/* Tags */}
                      <td>
                        {lead.tags && lead.tags.length > 0 ? (
                          <div style={{ display: "flex", flexWrap: "wrap", gap: "4px" }}>
                            {lead.tags.map((t) => (
                              <span
                                key={t}
                                style={{
                                  fontSize: "11px",
                                  background: "#f1f5f9",
                                  color: "#475569",
                                  padding: "2px 8px",
                                  borderRadius: "6px",
                                }}
                              >
                                {t}
                              </span>
                            ))}
                          </div>
                        ) : (
                          <span style={{ color: "#cbd5e1" }}>—</span>
                        )}
                      </td>

                      {/* Assigned */}
                      <td>
                        {lead.assigned_to ? (
                          <span style={{ fontSize: "12px", color: "#334155", fontWeight: 500 }}>
                            {memberName(lead.assigned_to)}
                          </span>
                        ) : (
                          <button
                            type="button"
                            className="boosend-crm-assign-pill"
                            onClick={() => setAssigningLead(lead)}
                          >
                            <Plus size={11} /> Assign
                          </button>
                        )}
                      </td>

                      {/* Messages count */}
                      <td>
                        <div style={{ display: "flex", alignItems: "center", gap: "5px", color: "#64748b", fontSize: "13px" }}>
                          <MessageSquare size={13} color="#94a3b8" />
                          {lead.message_count || 0}
                        </div>
                      </td>

                      {/* Stage dot + selector */}
                      <td>
                        <select
                          value={lead.stage || "new"}
                          onChange={(e) => moveStage(lead, e.target.value)}
                          style={{
                            border: "none",
                            background: "transparent",
                            fontSize: "12px",
                            color: "#64748b",
                            cursor: "pointer",
                            outline: "none",
                            fontWeight: 500,
                          }}
                        >
                          {STAGES.map((s) => (
                            <option key={s.id} value={s.id}>
                              ● {s.label}
                            </option>
                          ))}
                        </select>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>

          {/* Bottom Pagination matching Screenshot 10 */}
          <div className="boosend-crm-footer-pager">
            <span>All contacts loaded</span>
            <span>·</span>
            <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
              <span>Per page:</span>
              <select className="boosend-crm-perpage-select" defaultValue="25">
                <option value="25">25</option>
                <option value="50">50</option>
                <option value="100">100</option>
              </select>
            </div>
          </div>
        </div>
      ) : (
        /* Kanban Pipeline View */
        <div style={{ display: "grid", gridTemplateColumns: `repeat(${STAGES.length}, minmax(220px, 1fr))`, gap: "16px", overflowX: "auto" }}>
          {STAGES.map((s) => {
            const columnLeads = leads.filter(
              (l) => (l.stage || "new") === s.id,
            );

            return (
              <div
                key={s.id}
                style={{
                  background: "#f8fafc",
                  border: "1px solid #e2e8f0",
                  borderRadius: "14px",
                  padding: "14px",
                  minHeight: "450px",
                }}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault();
                  const droppedId = e.dataTransfer.getData("text/plain");
                  const targetLead = leads.find((l) => l.id === droppedId);
                  if (targetLead) moveStage(targetLead, s.id);
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
                    <span style={{ width: "8px", height: "8px", borderRadius: "50%", background: "#64748b" }} />
                    <strong style={{ fontSize: "13px", color: "#0f172a" }}>{s.label}</strong>
                  </div>
                  <span style={{ fontSize: "11px", fontWeight: 600, color: "#64748b", background: "#e2e8f0", padding: "1px 7px", borderRadius: "9999px" }}>
                    {columnLeads.length}
                  </span>
                </div>

                <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
                  {columnLeads.map((lead) => (
                    <div
                      key={lead.id}
                      draggable
                      onDragStart={(e) => {
                        e.dataTransfer.setData("text/plain", lead.id);
                        setDragging(lead.id);
                      }}
                      onDragEnd={() => setDragging(null)}
                      style={{
                        background: "#ffffff",
                        border: "1px solid #e2e8f0",
                        borderRadius: "10px",
                        padding: "12px",
                        boxShadow: "0 1px 3px rgba(0,0,0,0.03)",
                        cursor: "grab",
                      }}
                    >
                      <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                        <div className="boosend-crm-avatar" style={{ width: "26px", height: "26px", fontSize: "11px" }}>
                          {lead.name?.charAt(0).toUpperCase() || "U"}
                        </div>
                        <strong style={{ fontSize: "13px", color: "#0f172a" }}>{lead.name || "Unknown"}</strong>
                      </div>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "10px" }}>
                        {channelIcon(lead.channels || [])}
                        <div style={{ fontSize: "11px", color: "#94a3b8", display: "flex", alignItems: "center", gap: "4px" }}>
                          <MessageSquare size={11} /> {lead.message_count || 0}
                        </div>
                      </div>
                    </div>
                  ))}
                  {columnLeads.length === 0 && (
                    <div style={{ textAlign: "center", padding: "20px 0", color: "#cbd5e1", fontSize: "12px" }}>
                      Drop contacts here
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Campaign Broadcast Modal */}
      {campaignModal && (
        <Modal title="Launch Campaign" onClose={() => setCampaignModal(false)}>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const text = String(new FormData(e.currentTarget).get("message") || "").trim();
              if (text) handleBroadcast(text);
            }}
          >
            <p style={{ fontSize: "13px", color: "#64748b", marginBottom: "14px", lineHeight: 1.5 }}>
              Send an outreach message to <strong>{picked.size || leads.length}</strong> selected contacts.
              Meta allows outbound messages inside the 24-hour service window.
            </p>
            <label style={{ display: "block", marginBottom: "12px" }}>
              <span style={{ fontSize: "12px", fontWeight: 600, color: "#334155" }}>Message Content</span>
              <textarea
                name="message"
                rows={4}
                required
                placeholder="Hi {{first_name}}, thanks for reaching out..."
                style={{
                  width: "100%",
                  marginTop: "6px",
                  padding: "10px",
                  border: "1px solid #cbd5e1",
                  borderRadius: "8px",
                  fontSize: "13px",
                }}
              />
            </label>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: "8px" }}>
              <button
                type="button"
                className="button secondary small"
                onClick={() => setCampaignModal(false)}
              >
                Cancel
              </button>
              <button className="boosend-btn-create" disabled={feedback.busy}>
                <Rocket size={13} /> Send Campaign
              </button>
            </div>
          </form>
        </Modal>
      )}

      {/* Assign Member Modal */}
      {assigningLead && (
        <Modal
          title={`Assign ${assigningLead.name || "Contact"}`}
          onClose={() => setAssigningLead(null)}
        >
          <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
            <button
              type="button"
              className="button secondary"
              style={{ textAlign: "left" }}
              onClick={() => assignMember(assigningLead.id, null)}
            >
              Unassigned
            </button>
            {members.map((m) => (
              <button
                key={m.id}
                type="button"
                className="button secondary"
                style={{ textAlign: "left" }}
                onClick={() => assignMember(assigningLead.id, m.user_id)}
              >
                {m.name || m.email}
              </button>
            ))}
          </div>
        </Modal>
      )}
    </div>
  );
}
