"use client";
import { contactSourceLabel } from "@/lib/contact-source";

import {
  ValidatedForm,
  ValidatedInput,
  ValidatedSelect,
} from "@/components/validated-form";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
} from "react";
import {
  Check,
  ChevronDown,
  Download,
  Filter,
  Kanban as KanbanIcon,
  List,
  MessageSquare,
  Plus,
  Rocket,
  Search,
  Upload,
  UserPlus,
} from "lucide-react";
import {
  api,
  message,
  upload,
  type Connection,
  type Integration,
  type Lead,
  type LeadRow,
  type Member,
  type Page,
} from "@/lib/api";
import { BrandIcon, isBrand } from "@/lib/brand-icons";
import { CHANNELS, ChannelIcon, channelLabel } from "@/lib/channels";
import { useWorkspace } from "@/lib/workspace";
import { CampaignsDialog } from "@/components/campaigns-dialog";
import { SegmentationDialog } from "@/components/segmentation-dialog";
import { ContactAvatar } from "@/components/contact-avatar";
import { ContactPanel, relativeTime } from "@/components/contact-panel";
import { PipelineStagesEditor } from "@/components/pipeline-stages-editor";
import { CustomFieldsEditor } from "@/components/custom-fields-editor";
import { useCustomFields } from "@/lib/custom-fields";
import { stageLabelFor, usePipelineStages } from "@/lib/stages";
import {
  ErrorNotice,
  Modal,
  SuccessNotice,
  useFeedback,
} from "@/components/ui";

const PAGE_SIZES = [25, 50, 100];

/** Brand-coloured channel mark for one identity. */
function ChannelMark({ provider, title }: { provider: string; title: string }) {
  const brand = CHANNELS[provider]?.brand;
  if (!brand || !isBrand(brand)) {
    return (
      <span className="crm-channel-mark generic" title={title}>
        <ChannelIcon provider={provider} size={13} />
      </span>
    );
  }
  return (
    <span className={`crm-channel-mark brand-${brand}`} title={title}>
      <BrandIcon name={brand} size={13} mono />
    </span>
  );
}

function csvEscape(value: unknown) {
  const text = String(value ?? "");
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

export default function CrmPage() {
  const { workspace, prefix, manager } = useWorkspace();
  const STAGES = usePipelineStages(prefix);
  const stageLabel = (id: string) => stageLabelFor(STAGES, id);
  const [stagesModal, setStagesModal] = useState(false);
  const fieldDefs = useCustomFields(prefix);
  const [fieldsModal, setFieldsModal] = useState(false);
  // The inbox links here with ?contact=<id> to open a person directly.
  const linkedContact = useSearchParams().get("contact");
  const [leads, setLeads] = useState<LeadRow[]>([]);
  const [total, setTotal] = useState(0);
  const [nextPage, setNextPage] = useState<string | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [connections, setConnections] = useState<Connection[] | null>(null);
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState<"table" | "kanban">("table");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [channelFilter, setChannelFilter] = useState("");
  const [pageSize, setPageSize] = useState(25);
  const [showFilterMenu, setShowFilterMenu] = useState(false);
  const [showBulkMenu, setShowBulkMenu] = useState(false);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [campaignModal, setCampaignModal] = useState(false);
  const [segmentationModal, setSegmentationModal] = useState(false);
  const [addContactModal, setAddContactModal] = useState(false);
  const [openId, setOpenId] = useState<string | null>(linkedContact);
  const [tagInput, setTagInput] = useState("");
  const feedback = useFeedback();
  const importInput = useRef<HTMLInputElement>(null);

  async function importCsv(file: File) {
    const form = new FormData();
    form.append("file", file);
    const result = await feedback.run(() =>
      upload<{
        created: number;
        updated: number;
        unchanged: number;
        skipped: number;
        errors: { row: number; reason: string }[];
      }>(`${prefix}/leads/import/`, form),
    );
    if (!result) return;
    const skipped = result.skipped
      ? ` ${result.skipped} skipped (${result.errors
          .slice(0, 3)
          .map((item) => `row ${item.row}: ${item.reason}`)
          .join("; ")}${result.skipped > 3 ? "; …" : ""}).`
      : "";
    feedback.setNotice(
      `Imported ${result.created} new and updated ${result.updated} existing contacts.${skipped}`,
    );
    await load();
  }

  // Debounce typing so the API is not hit on every keystroke.
  useEffect(() => {
    const timer = window.setTimeout(() => setQuery(search.trim()), 250);
    return () => window.clearTimeout(timer);
  }, [search]);

  const load = useCallback(
    async (signal?: AbortSignal) => {
      try {
        const params = new URLSearchParams({ page_size: String(pageSize) });
        if (query) params.set("search", query);
        if (channelFilter === "manual" || channelFilter === "form")
          params.set("source", channelFilter);
        else if (channelFilter) params.set("provider", channelFilter);
        const result = await api<Page<LeadRow>>(
          `${prefix}/leads/?${params.toString()}`,
          "GET",
          undefined,
          signal,
        );
        setLeads(result.results || []);
        setTotal(result.count);
        setNextPage(result.next);
        setPicked(
          (prev) =>
            new Set(
              result.results
                .filter((lead) => prev.has(lead.id))
                .map((lead) => lead.id),
            ),
        );
      } catch (err) {
        if (!signal?.aborted) feedback.setError(message(err));
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [prefix, query, channelFilter, pageSize],
  );

  useEffect(() => {
    const controller = new AbortController();
    queueMicrotask(() => {
      load(controller.signal).finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    });
    return () => controller.abort();
  }, [load]);

  useEffect(() => {
    const controller = new AbortController();
    api<Page<Member>>(`${prefix}/members/`, "GET", undefined, controller.signal)
      .then((res) => setMembers(res.results || []))
      .catch(() => undefined);
    api<Page<Connection>>(
      `${prefix}/connections/`,
      "GET",
      undefined,
      controller.signal,
    )
      .then((res) => setConnections(res.results || []))
      .catch(() => setConnections([]));
    if (manager)
      api<Integration[] | Page<Integration>>(
        `${prefix}/integrations/`,
        "GET",
        undefined,
        controller.signal,
      )
        .then((res) => setIntegrations(Array.isArray(res) ? res : res.results))
        .catch(() => undefined);
    return () => controller.abort();
  }, [prefix, manager]);

  // A contact linked from elsewhere may not be on the first page: fetch it alone.
  useEffect(() => {
    if (!linkedContact || leads.some((lead) => lead.id === linkedContact))
      return;
    const controller = new AbortController();
    api<LeadRow>(
      `${prefix}/leads/${linkedContact}/`,
      "GET",
      undefined,
      controller.signal,
    )
      .then((lead) =>
        setLeads((list) =>
          list.some((item) => item.id === lead.id) ? list : [lead, ...list],
        ),
      )
      .catch(() => undefined);
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [linkedContact, prefix]);

  const loadMore = async () => {
    if (!nextPage) return;
    try {
      const url = new URL(nextPage, window.location.origin);
      const result = await api<Page<LeadRow>>(
        `${prefix}/leads/?${url.searchParams.toString()}`,
      );
      setLeads((list) => [...list, ...result.results]);
      setNextPage(result.next);
    } catch (err) {
      feedback.setError(message(err));
    }
  };

  const togglePick = (id: string) =>
    setPicked((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const isAllSelected = leads.length > 0 && picked.size === leads.length;
  const toggleSelectAll = () =>
    setPicked(
      isAllSelected ? new Set() : new Set(leads.map((lead) => lead.id)),
    );

  const replaceLead = (lead: LeadRow) =>
    setLeads((list) => list.map((item) => (item.id === lead.id ? lead : item)));

  const moveStage = async (lead: LeadRow, newStage: string) => {
    const prev = lead.stage;
    replaceLead({ ...lead, stage: newStage });
    try {
      await api<Lead>(`${prefix}/leads/${lead.id}/`, "PATCH", {
        stage: newStage,
      });
    } catch (err) {
      replaceLead({ ...lead, stage: prev });
      feedback.setError(message(err));
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

  const createContact = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const created = await feedback.run(
      () =>
        api<LeadRow>(`${prefix}/leads/`, "POST", {
          name: String(data.get("name") || "").trim(),
          email: String(data.get("email") || "").trim(),
          stage: "new",
        }),
      "Contact created.",
    );
    if (created) {
      setLeads((prev) => [created, ...prev]);
      setTotal((count) => count + 1);
      setAddContactModal(false);
      setOpenId(created.id);
    }
  };

  const exportCsv = () => {
    const head = [
      "name",
      "handle",
      "email",
      "channels",
      "stage",
      "tags",
      "messages",
      "last_activity_at",
      "created_at",
    ];
    const rows = leads.map((lead) =>
      [
        lead.name,
        lead.handle,
        lead.email,
        lead.channels.join("|"),
        lead.stage,
        lead.tags.join("|"),
        lead.message_count,
        lead.last_activity_at ?? "",
        lead.created_at,
      ]
        .map(csvEscape)
        .join(","),
    );
    const blob = new Blob([[head.join(","), ...rows].join("\n")], {
      type: "text/csv",
    });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${workspace.name.replace(/[^a-z0-9]+/gi, "-")}-contacts.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  const memberName = (userId: number | null) => {
    const member = members.find((item) => item.user_id === userId);
    return member ? member.name || member.email : "";
  };

  const liveConnections = useMemo(
    () => (connections ?? []).filter((item) => item.status !== "disconnected"),
    [connections],
  );
  const filterOptions = useMemo(() => {
    const providers = Array.from(
      new Set([
        ...liveConnections.map((item) => item.provider),
        ...leads.flatMap((lead) => lead.channels),
      ]),
    );
    return providers.map((provider) => ({
      id: provider,
      label: channelLabel(provider),
    }));
  }, [liveConnections, leads]);
  const openLead = openId ? leads.find((lead) => lead.id === openId) : null;
  const noChannels = connections !== null && liveConnections.length === 0;

  const channelMarks = (lead: LeadRow) =>
    lead.identities.length ? (
      <div className="crm-channel-marks">
        {lead.identities.map((identity) => (
          <ChannelMark
            key={identity.id}
            provider={identity.provider}
            title={`${channelLabel(identity.provider)} · ${identity.connection_name}`}
          />
        ))}
      </div>
    ) : (
      <span
        className="subtle"
        title={`${contactSourceLabel(lead)}; not on a channel yet`}
      >
        {contactSourceLabel(lead)}
      </span>
    );

  return (
    <div className="boosend-crm-page">
      <div className="crm-heading">
        <div>
          <h1>Contacts</h1>
          <p>
            Everyone who messages or comments on your connected Instagram,
            Facebook and WhatsApp accounts lands here with the profile Meta
            reports. Open a contact to chat, tag, assign and take notes.
          </p>
        </div>
        <span className="crm-count" aria-live="polite">
          {total} contact{total === 1 ? "" : "s"}
        </span>
      </div>

      {noChannels && (
        <section className="connect-prompt" role="region" aria-label="Connect">
          <BrandIcon name="instagram" size={22} />
          <div>
            <strong>No channel connected yet</strong>
            <p>
              Contacts come from the people who message your Instagram, Facebook
              Page or WhatsApp number. Connect an account and they fill in here
              automatically.
            </p>
          </div>
          <Link
            className="button primary"
            href={`/w/${workspace.id}/integrations?tab=channels`}
          >
            Connect account
          </Link>
        </section>
      )}

      <div className="boosend-crm-topbar">
        <div className="boosend-crm-search-box">
          <Search size={15} color="#94a3b8" />
          <ValidatedInput
            type="text"
            className="boosend-crm-search-input"
            placeholder="Search by name, @handle or email…"
            aria-label="Search contacts"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

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
              <div className="crm-menu" role="menu">
                <div className="crm-menu-title">Change stage</div>
                {STAGES.map((stage) => (
                  <button
                    key={stage.id}
                    type="button"
                    role="menuitem"
                    className="crm-menu-item"
                    onClick={() => bulkAction("stage", stage.id)}
                  >
                    Move to {stage.label}
                  </button>
                ))}
                <ValidatedForm
                  fieldErrors={feedback.fieldErrors}
                  validationTarget={feedback.validationTarget}
                  onEdit={() => feedback.setError("")}
                  className="crm-menu-form"
                  onSubmit={(e) => {
                    e.preventDefault();
                    if (tagInput.trim()) bulkAction("tag", tagInput.trim());
                  }}
                >
                  <ValidatedInput
                    placeholder="Add tag..."
                    aria-label="Tag to apply"
                    maxLength={40}
                    value={tagInput}
                    onChange={(e) => setTagInput(e.target.value)}
                  />
                  <button type="submit" aria-label="Apply tag">
                    Apply
                  </button>
                </ValidatedForm>
              </div>
            )}
          </div>

          <button
            type="button"
            className="boosend-crm-filter-btn"
            onClick={exportCsv}
            disabled={!leads.length}
            title="Download the loaded contacts as CSV"
          >
            <Download size={13} />
            Export
          </button>

          {manager && (
            <>
              <button
                type="button"
                className="boosend-crm-filter-btn"
                onClick={() => importInput.current?.click()}
                disabled={feedback.busy}
                title="Import contacts from a CSV file (name, email, phone, tags, stage and any custom columns)"
              >
                <Upload size={13} />
                Import
              </button>
              <input
                ref={importInput}
                type="file"
                accept=".csv,text/csv"
                aria-label="Import contacts CSV"
                hidden
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  event.target.value = "";
                  if (file) void importCsv(file);
                }}
              />
            </>
          )}

          {manager && (
            <button
              className="boosend-crm-filter-btn"
              onClick={() => setSegmentationModal(true)}
            >
              AI segmentation
            </button>
          )}
          {manager && (
            <button
              type="button"
              className="boosend-crm-filter-btn"
              onClick={() => setStagesModal(true)}
            >
              Stages
            </button>
          )}
          {manager && (
            <button
              type="button"
              className="boosend-crm-filter-btn"
              onClick={() => setFieldsModal(true)}
            >
              Fields
            </button>
          )}
          {fieldsModal && (
            <CustomFieldsEditor
              prefix={prefix}
              fields={fieldDefs}
              onClose={() => setFieldsModal(false)}
              onSaved={() => feedback.setNotice("Contact fields saved.")}
            />
          )}
          {stagesModal && (
            <PipelineStagesEditor
              prefix={prefix}
              stages={STAGES}
              onClose={() => setStagesModal(false)}
              onSaved={() => {
                feedback.setNotice("Pipeline stages saved.");
                void load();
              }}
            />
          )}
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

      <div className="boosend-crm-subbar">
        <div className="boosend-crm-view-pills">
          <button
            type="button"
            className="boosend-crm-add-btn"
            title="Add a contact by hand"
            aria-label="Create contact"
            onClick={() => setAddContactModal(true)}
          >
            <Plus size={16} />
          </button>

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

          <div style={{ position: "relative" }}>
            <button
              type="button"
              className="boosend-crm-filter-btn"
              aria-expanded={showFilterMenu}
              onClick={() => setShowFilterMenu((v) => !v)}
            >
              <Filter size={13} />
              Filter
              {channelFilter && (
                <span className="crm-filter-chip">
                  {channelFilter === "manual"
                    ? "Added by hand"
                    : channelFilter === "form"
                      ? "Added via form"
                      : channelLabel(channelFilter)}
                </span>
              )}
            </button>

            {showFilterMenu && (
              <div className="crm-menu left" role="menu">
                {[
                  { id: "", label: "All contacts" },
                  ...filterOptions,
                  { id: "manual", label: "Added by hand" },
                  { id: "form", label: "Added via form" },
                ].map((option) => (
                  <button
                    key={option.id}
                    type="button"
                    role="menuitemradio"
                    aria-checked={channelFilter === option.id}
                    className={`crm-menu-item ${channelFilter === option.id ? "active" : ""}`}
                    onClick={() => {
                      setChannelFilter(option.id);
                      setShowFilterMenu(false);
                    }}
                  >
                    {option.id && option.id !== "manual" && (
                      <ChannelIcon provider={option.id} size={12} />
                    )}
                    {option.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      <ErrorNotice error={feedback.error} />
      <SuccessNotice notice={feedback.notice} />

      {view === "table" ? (
        <div className="boosend-crm-table-card">
          <table className="boosend-crm-table crm-table">
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
                <th>Contact</th>
                <th>Channels</th>
                <th>Tags</th>
                <th>Assigned</th>
                <th>Messages</th>
                <th>Last activity</th>
                <th>Stage</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={8} className="crm-empty">
                    Loading contacts…
                  </td>
                </tr>
              ) : leads.length === 0 ? (
                <tr>
                  <td colSpan={8} className="crm-empty">
                    <div className="crm-empty-card">
                      <span className="crm-empty-icon">
                        <UserPlus size={22} />
                      </span>
                      <h4>
                        {query || channelFilter
                          ? "No contacts match"
                          : "No contacts yet"}
                      </h4>
                      <p>
                        {query || channelFilter
                          ? "Try another name, handle or channel filter."
                          : noChannels
                            ? "Connect an Instagram, Facebook or WhatsApp account and every person who messages it shows up here."
                            : "The first person to DM, comment or reply to a story on a connected account appears here with their name and photo."}
                      </p>
                      {!query && !channelFilter && (
                        <div className="crm-empty-actions">
                          {noChannels ? (
                            <Link
                              className="button primary small"
                              href={`/w/${workspace.id}/integrations?tab=channels`}
                            >
                              Connect a channel
                            </Link>
                          ) : (
                            <Link
                              className="button primary small"
                              href={`/w/${workspace.id}/integrations?tab=channels`}
                            >
                              Send a test message
                            </Link>
                          )}
                          <button
                            type="button"
                            className="button secondary small"
                            onClick={() => setAddContactModal(true)}
                          >
                            <Plus size={13} /> Add by hand
                          </button>
                        </div>
                      )}
                    </div>
                  </td>
                </tr>
              ) : (
                leads.map((lead) => {
                  const isPicked = picked.has(lead.id);
                  const name = lead.name || "Unknown contact";
                  return (
                    <tr
                      key={lead.id}
                      className={`${isPicked ? "picked" : ""} ${openId === lead.id ? "open" : ""}`}
                    >
                      <td>
                        <button
                          type="button"
                          role="checkbox"
                          aria-checked={isPicked}
                          aria-label={`Select ${name}`}
                          className={`boosend-checkbox-round ${isPicked ? "checked" : ""}`}
                          onClick={() => togglePick(lead.id)}
                        >
                          {isPicked && <Check size={11} color="#ffffff" />}
                        </button>
                      </td>
                      <td>
                        <button
                          type="button"
                          className="crm-contact-cell"
                          aria-label={`Open ${name}`}
                          onClick={() => setOpenId(lead.id)}
                        >
                          <ContactAvatar
                            name={name}
                            avatarUrl={lead.avatar_url}
                          />
                          <span className="crm-contact-text">
                            <strong>{name}</strong>
                            {(lead.handle || lead.email) && (
                              <span>{lead.handle || lead.email}</span>
                            )}
                          </span>
                        </button>
                      </td>
                      <td>{channelMarks(lead)}</td>
                      <td>
                        {lead.tags.length ? (
                          <div className="crm-tags">
                            {lead.tags.slice(0, 3).map((tag) => (
                              <span key={tag} className="crm-tag">
                                {tag}
                              </span>
                            ))}
                            {lead.tags.length > 3 && (
                              <span className="crm-tag">
                                +{lead.tags.length - 3}
                              </span>
                            )}
                          </div>
                        ) : (
                          <span className="subtle">—</span>
                        )}
                      </td>
                      <td>
                        {lead.assigned_to ? (
                          <span className="crm-assignee">
                            {memberName(lead.assigned_to)}
                          </span>
                        ) : (
                          <button
                            type="button"
                            className="boosend-crm-assign-pill"
                            onClick={() => setOpenId(lead.id)}
                          >
                            <Plus size={11} /> Assign
                          </button>
                        )}
                      </td>
                      <td>
                        <span className="crm-messages">
                          <MessageSquare size={13} color="#94a3b8" />
                          {lead.message_count || 0}
                        </span>
                      </td>
                      <td>
                        <span className="subtle">
                          {lead.last_activity_at
                            ? relativeTime(lead.last_activity_at)
                            : "—"}
                        </span>
                      </td>
                      <td>
                        <ValidatedSelect
                          className="crm-stage-select"
                          aria-label={`Stage for ${name}`}
                          value={lead.stage || "new"}
                          onChange={(e) => moveStage(lead, e.target.value)}
                        >
                          {STAGES.map((stage) => (
                            <option key={stage.id} value={stage.id}>
                              ● {stage.label}
                            </option>
                          ))}
                        </ValidatedSelect>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>

          <div className="boosend-crm-footer-pager">
            <span>
              Showing {leads.length} of {total}
            </span>
            {nextPage && (
              <button type="button" className="text-button" onClick={loadMore}>
                Load more
              </button>
            )}
            <span>·</span>
            <label className="crm-perpage">
              Per page
              <ValidatedSelect
                className="boosend-crm-perpage-select"
                value={pageSize}
                onChange={(e) => setPageSize(Number(e.target.value))}
              >
                {PAGE_SIZES.map((size) => (
                  <option key={size} value={size}>
                    {size}
                  </option>
                ))}
              </ValidatedSelect>
            </label>
          </div>
        </div>
      ) : (
        <div className="crm-kanban">
          {STAGES.map((stage) => {
            const columnLeads = leads.filter(
              (l) => (l.stage || "new") === stage.id,
            );
            return (
              <div
                key={stage.id}
                className="crm-kanban-column"
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault();
                  const droppedId = e.dataTransfer.getData("text/plain");
                  const target = leads.find((l) => l.id === droppedId);
                  if (target && target.stage !== stage.id)
                    moveStage(target, stage.id);
                }}
              >
                <div
                  className="crm-kanban-head"
                  style={{ borderTop: `3px solid ${stage.color}` }}
                >
                  <strong>{stage.label}</strong>
                  <span>{columnLeads.length}</span>
                </div>
                <div className="crm-kanban-cards">
                  {columnLeads.map((lead) => {
                    const name = lead.name || "Unknown contact";
                    return (
                      <div
                        key={lead.id}
                        className="crm-kanban-card"
                        draggable
                        onDragStart={(e) =>
                          e.dataTransfer.setData("text/plain", lead.id)
                        }
                      >
                        <button
                          type="button"
                          className="crm-contact-cell"
                          aria-label={`Open ${name}`}
                          onClick={() => setOpenId(lead.id)}
                        >
                          <ContactAvatar
                            name={name}
                            avatarUrl={lead.avatar_url}
                            size={28}
                          />
                          <span className="crm-contact-text">
                            <strong>{name}</strong>
                            {lead.handle && <span>{lead.handle}</span>}
                          </span>
                        </button>
                        <ValidatedSelect
                          className="kanban-stage-select"
                          aria-label={`Move ${name} to stage`}
                          value={lead.stage || "new"}
                          onChange={(e) => moveStage(lead, e.target.value)}
                        >
                          {STAGES.map((item) => (
                            <option key={item.id} value={item.id}>
                              {item.label}
                            </option>
                          ))}
                        </ValidatedSelect>
                        <div className="crm-kanban-foot">
                          {channelMarks(lead)}
                          <span className="crm-messages">
                            <MessageSquare size={11} />{" "}
                            {lead.message_count || 0}
                          </span>
                        </div>
                      </div>
                    );
                  })}
                  {columnLeads.length === 0 && (
                    <div className="crm-kanban-empty">
                      {stage.id === "new"
                        ? "New contacts land here"
                        : `Drop contacts to mark ${stageLabel(stage.id).toLowerCase()}`}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {openLead && (
        <ContactPanel
          lead={openLead}
          leads={leads}
          members={members}
          integrations={integrations}
          prefix={prefix}
          workspaceId={workspace.id}
          manager={manager}
          onClose={() => setOpenId(null)}
          onChange={replaceLead}
          onDelete={(id) => {
            setLeads((list) => list.filter((item) => item.id !== id));
            setTotal((count) => Math.max(0, count - 1));
            if (openId === id) setOpenId(null);
          }}
        />
      )}

      {campaignModal && (
        <CampaignsDialog
          prefix={prefix}
          connections={connections || []}
          selectedLeadIds={Array.from(picked)}
          onClose={() => setCampaignModal(false)}
        />
      )}
      {segmentationModal && (
        <SegmentationDialog
          prefix={prefix}
          onClose={() => setSegmentationModal(false)}
        />
      )}

      {addContactModal && (
        <Modal title="Create contact" onClose={() => setAddContactModal(false)}>
          <ValidatedForm
            fieldErrors={feedback.fieldErrors}
            validationTarget={feedback.validationTarget}
            onEdit={() => feedback.setError("")}
            onSubmit={createContact}
          >
            <p className="modal-copy">
              Contacts normally arrive on their own when someone messages a
              connected account. Add one by hand to keep notes on a person
              before they write to you.
            </p>
            <ErrorNotice error={feedback.error} />
            <label>
              Name
              <ValidatedInput name="name" required maxLength={150} autoFocus />
            </label>
            <label>
              Email (optional)
              <ValidatedInput name="email" type="email" maxLength={254} />
            </label>
            <button className="button primary" disabled={feedback.busy}>
              Create contact
            </button>
          </ValidatedForm>
        </Modal>
      )}
    </div>
  );
}
