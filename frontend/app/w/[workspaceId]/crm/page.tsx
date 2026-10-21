"use client";

import Link from "next/link";
import { useCallback, useEffect, useState, type FormEvent } from "react";
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
  message,
  type Lead,
  type LeadRow,
  type Member,
  type Page,
} from "@/lib/api";
import { BrandIcon, type BrandName } from "@/lib/brand-icons";
import { ChannelIcon, channelLabel } from "@/lib/channels";
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

const CHANNEL_BADGES: Record<string, { brand: BrandName; background: string }> = {
  instagram: {
    brand: "instagram",
    background:
      "linear-gradient(45deg, #f09433 0%, #e6683c 25%, #dc2743 50%, #cc2366 75%, #bc1888 100%)",
  },
  messenger: { brand: "messenger", background: "#0084ff" },
  whatsapp: { brand: "whatsapp", background: "#25d366" },
  telegram: { brand: "telegram", background: "#26a5e4" },
  linkedin: { brand: "linkedin", background: "#0a66c2" },
};

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
        setLeads(result.results || []);
        setPicked(
          (prev) =>
            new Set(result.results.filter((lead) => prev.has(lead.id)).map((lead) => lead.id)),
        );
      } catch (err) {
        if (!signal?.aborted) feedback.setError(message(err));
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [prefix, search, channelFilter],
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
    } catch (err) {
      setLeads((list) =>
        list.map((item) => (item.id === lead.id ? { ...item, stage: prev } : item)),
      );
      feedback.setError(message(err));
    }
  };

  // Assignment belongs to the contact's latest conversation, not the lead itself.
  const assignMember = async (lead: LeadRow, memberId: number | null) => {
    if (!lead.conversation_id) return;
    const done = await feedback.run(async () => {
      await api(`${prefix}/conversations/${lead.conversation_id}/`, "PATCH", {
        assigned_to: memberId,
      });
      setLeads((list) =>
        list.map((item) =>
          item.id === lead.id ? { ...item, assigned_to: memberId } : item,
        ),
      );
      return true;
    });
    if (done) setAssigningLead(null);
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

  const createContact = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const done = await feedback.run(async () => {
      const created = await api<LeadRow>(`${prefix}/leads/`, "POST", {
        name: String(data.get("name") || "").trim(),
        email: String(data.get("email") || "").trim(),
        stage: "new",
      });
      setLeads((prev) => [created, ...prev]);
      return true;
    }, "Contact created.");
    if (done) setAddContactModal(false);
  };

  const handleBroadcast = async (text: string) => {
    const ids = picked.size ? Array.from(picked) : leads.map((lead) => lead.id);
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

  // The contact's first channel as a brand-coloured badge; hand-added contacts have none.
  const channelIcon = (channels: string[]) => {
    const provider = channels[0];
    const badge = provider ? CHANNEL_BADGES[provider] : undefined;
    if (!provider) return <span style={{ color: "#cbd5e1" }}>—</span>;
    if (!badge) return <ChannelIcon provider={provider} size={13} />;
    return (
      <div
        className="boosend-crm-channel-icon"
        style={{ background: badge.background, color: "#ffffff" }}
        title={channelLabel(provider)}
      >
        <BrandIcon name={badge.brand} size={13} mono />
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
              aria-expanded={showBulkMenu}
              disabled={!picked.size}
              title={picked.size ? undefined : "Select contacts first"}
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
                      aria-label="Tag to apply"
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
                      aria-label="Apply tag"
                    >
                      Apply
                    </button>
                  </form>
                </div>
              </div>
            )}
          </div>

          {manager && (
            <button
              type="button"
              className="boosend-crm-campaign-btn"
              onClick={() => setCampaignModal(true)}
            >
              <Rocket size={14} />
              Campaign
            </button>
          )}
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
            aria-label="Create contact"
            onClick={() => setAddContactModal(true)}
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
                  {channelLabel(channelFilter)}
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
                {["", "instagram", "messenger", "whatsapp"].map((ch) => (
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
                    {ch ? channelLabel(ch) : "All Channels"}
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
                  <button
                    type="button"
                    role="checkbox"
                    aria-checked={isAllSelected}
                    aria-label="Select all contacts"
                    className={`boosend-checkbox-round ${isAllSelected ? "checked" : ""}`}
                    onClick={toggleSelectAll}
                  >
                    {isAllSelected && <Check size={11} color="#ffffff" />}
                  </button>
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
                        onClick={() => setAddContactModal(true)}
                      >
                        <Plus size={14} /> Add a contact
                      </button>
                    </div>
                  </td>
                </tr>
              ) : (
                leads.map((lead) => {
                  const isPicked = picked.has(lead.id);
                  const firstLetter = lead.name?.charAt(0).toUpperCase() || "U";
                  const handle = lead.fields?.handle || "";
                  const convUrl = lead.conversation_id
                    ? `/w/${workspace.id}/inbox?conversation=${lead.conversation_id}`
                    : null;

                  return (
                    <tr key={lead.id} className={isPicked ? "picked" : ""}>
                      {/* Checkbox */}
                      <td>
                        <button
                          type="button"
                          role="checkbox"
                          aria-checked={isPicked}
                          aria-label={`Select ${lead.name || "contact"}`}
                          className={`boosend-checkbox-round ${isPicked ? "checked" : ""}`}
                          onClick={() => togglePick(lead.id)}
                        >
                          {isPicked && <Check size={11} color="#ffffff" />}
                        </button>
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
                          {handle && (
                            <div style={{ fontSize: "12px", color: "#94a3b8", marginTop: "2px" }}>
                              {handle}
                            </div>
                          )}
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
                        {!lead.conversation_id ? (
                          <span
                            style={{ color: "#cbd5e1" }}
                            title="Assign once the contact has a conversation"
                          >
                            —
                          </span>
                        ) : lead.assigned_to ? (
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
                          aria-label={`Stage for ${lead.name || "contact"}`}
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
                      <select
                        className="kanban-stage-select"
                        aria-label={`Move ${lead.name || "contact"} to stage`}
                        value={lead.stage || "new"}
                        onChange={(e) => moveStage(lead, e.target.value)}
                      >
                        {STAGES.map((stage) => (
                          <option key={stage.id} value={stage.id}>
                            {stage.label}
                          </option>
                        ))}
                      </select>
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

      {addContactModal && (
        <Modal title="Create contact" onClose={() => setAddContactModal(false)}>
          <form onSubmit={createContact}>
            <ErrorNotice error={feedback.error} />
            <label>
              Name
              <input name="name" required maxLength={150} autoFocus />
            </label>
            <label>
              Email (optional)
              <input name="email" type="email" maxLength={254} />
            </label>
            <button className="button primary" disabled={feedback.busy}>
              Create contact
            </button>
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
              onClick={() => assignMember(assigningLead, null)}
            >
              Unassigned
            </button>
            {members.map((m) => (
              <button
                key={m.id}
                type="button"
                className="button secondary"
                style={{ textAlign: "left" }}
                onClick={() => assignMember(assigningLead, m.user_id)}
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
