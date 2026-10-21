"use client";

import Link from "next/link";
import { useCallback, useEffect, useState, type DragEvent } from "react";
import {
  Download,
  Kanban,
  List,
  Megaphone,
  MessagesSquare,
  Tag,
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
import { ChannelBadge, channelLabel, META_CHANNELS } from "@/lib/channels";
import { initials } from "@/components/shell";
import {
  Empty,
  ErrorNotice,
  Modal,
  PageHeading,
  SuccessNotice,
  useFeedback,
} from "@/components/ui";

/** The pipeline, in order; the backend accepts exactly these stages. */
const STAGES = [
  { id: "new", label: "New lead" },
  { id: "qualified", label: "Qualified" },
  { id: "interested", label: "Interested" },
  { id: "booked", label: "Booked" },
  { id: "won", label: "Won" },
  { id: "lost", label: "Lost" },
];
const stageLabel = (id: string) =>
  STAGES.find((stage) => stage.id === id)?.label ?? id;
const PAGE_SIZE = 200;

/** Quote a CSV cell, neutralising spreadsheet formulas in user-supplied text. */
function csvCell(value: string | number) {
  let text = String(value);
  if (/^[=+\-@\t\r]/.test(text)) text = `'${text}`;
  return `"${text.replace(/"/g, '""')}"`;
}

export default function CrmPage() {
  const { workspace, prefix, manager } = useWorkspace();
  const [leads, setLeads] = useState<LeadRow[]>([]);
  const [members, setMembers] = useState<Member[]>([]);
  const [page, setPage] = useState(1);
  const [more, setMore] = useState(false);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState<"table" | "kanban">("table");
  const [search, setSearch] = useState("");
  const [channel, setChannel] = useState("");
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [tag, setTag] = useState("");
  const [dragging, setDragging] = useState<string | null>(null);
  const [broadcast, setBroadcast] = useState(false);
  const feedback = useFeedback();

  const load = useCallback(
    async (pageNumber: number, signal?: AbortSignal) => {
      const params = new URLSearchParams({
        page: String(pageNumber),
        page_size: String(PAGE_SIZE),
      });
      if (search.trim()) params.set("search", search.trim());
      if (channel) params.set("provider", channel);
      const result = await api<Page<LeadRow>>(
        `${prefix}/leads/?${params.toString()}`,
        "GET",
        undefined,
        signal,
      );
      setLeads((list) =>
        pageNumber === 1 ? result.results : [...list, ...result.results],
      );
      setPage(pageNumber);
      setMore(Boolean(result.next));
      setTotal(result.count);
    },
    [prefix, search, channel],
  );
  useEffect(() => {
    const controller = new AbortController();
    queueMicrotask(() => {
      setPicked(new Set());
      load(1, controller.signal)
        .catch((err) => {
          if (!controller.signal.aborted)
            feedback.setError((err as Error).message);
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [load]);
  useEffect(() => {
    const controller = new AbortController();
    api<Page<Member>>(`${prefix}/members/`, "GET", undefined, controller.signal)
      .then((result) => setMembers(result.results))
      .catch(() => undefined);
    return () => controller.abort();
  }, [prefix]);

  const memberName = (userId: number | null) => {
    const member = members.find((item) => item.user_id === userId);
    return member ? member.name || member.email : "";
  };
  const merge = (updated: Partial<Lead> & { id: string }) =>
    setLeads((list) =>
      list.map((lead) =>
        lead.id === updated.id ? { ...lead, ...updated } : lead,
      ),
    );

  async function moveStage(lead: LeadRow, stage: string) {
    if (lead.stage === stage) return;
    const previous = lead.stage;
    merge({ id: lead.id, stage });
    const saved = await feedback.run(() =>
      api<Lead>(`${prefix}/leads/${lead.id}/`, "PATCH", { stage }),
    );
    merge(saved ?? { id: lead.id, stage: previous });
  }
  async function bulk(action: "tag" | "stage", value: string) {
    const ids = [...picked];
    const done = await feedback.run(
      async () => {
        const result = await api<{ updated: number }>(
          `${prefix}/leads/bulk/`,
          "POST",
          { ids, action, value },
        );
        await load(1);
        return result;
      },
      action === "tag"
        ? `Tagged “${value}”.`
        : `Moved to ${stageLabel(value)}.`,
    );
    if (done && action === "tag") setTag("");
  }
  async function sendBroadcast(text: string) {
    const result = await feedback.run(() =>
      api<{ queued: number; skipped: number }>(
        `${prefix}/leads/broadcast/`,
        "POST",
        { ids: [...picked], text },
        undefined,
        { "Idempotency-Key": idempotencyKey() },
      ),
    );
    if (result) {
      setBroadcast(false);
      feedback.setNotice(
        `Queued ${result.queued} message${result.queued === 1 ? "" : "s"}.` +
          (result.skipped
            ? ` Skipped ${result.skipped}: outside Meta's 24-hour window or opted out.`
            : ""),
      );
    }
  }
  function exportCsv() {
    const rows = leads.filter((lead) => !picked.size || picked.has(lead.id));
    const lines = [
      [
        "Name",
        "Email",
        "Stage",
        "Channels",
        "Tags",
        "Assigned to",
        "Messages",
        "Created",
      ],
      ...rows.map((lead) => [
        lead.name,
        lead.email,
        stageLabel(lead.stage),
        lead.channels.map(channelLabel).join("; "),
        lead.tags.join("; "),
        memberName(lead.assigned_to),
        lead.message_count,
        new Date(lead.created_at).toISOString(),
      ]),
    ].map((row) => row.map(csvCell).join(","));
    const url = URL.createObjectURL(
      new Blob([`﻿${lines.join("\r\n")}`], { type: "text/csv;charset=utf-8" }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = `${workspace.name.replace(/[^\w-]+/g, "-")}-contacts.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }
  const toggle = (id: string) =>
    setPicked((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const allPicked =
    leads.length > 0 && leads.every((lead) => picked.has(lead.id));

  function drop(event: DragEvent<HTMLElement>, stage: string) {
    event.preventDefault();
    const lead = leads.find(
      (item) => item.id === event.dataTransfer.getData("text/plain"),
    );
    setDragging(null);
    if (lead) moveStage(lead, stage);
  }

  const inboxLink = (lead: LeadRow) =>
    lead.conversation_id
      ? `/w/${workspace.id}/inbox?conversation=${lead.conversation_id}`
      : null;

  return (
    <>
      <PageHeading
        eyebrow="CRM & contacts"
        title="Every lead, from first comment to closed."
        text="Contacts captured on Instagram, Facebook and WhatsApp, with their stage, tags and owner."
        action={
          <button
            className="button secondary small"
            onClick={exportCsv}
            disabled={!leads.length}
          >
            <Download size={14} /> Export CSV
            {picked.size ? ` (${picked.size})` : ""}
          </button>
        }
      />
      <ErrorNotice error={feedback.error} />
      <SuccessNotice notice={feedback.notice} />
      <div className="list-toolbar">
        <input
          type="search"
          placeholder="Search name or email"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          aria-label="Search contacts"
        />
        <div className="chip-row" role="group" aria-label="Channel">
          <button
            className={`chip ${!channel ? "on" : ""}`}
            aria-pressed={!channel}
            onClick={() => setChannel("")}
          >
            All channels
          </button>
          {META_CHANNELS.map((provider) => (
            <button
              key={provider}
              className={`chip ${channel === provider ? "on" : ""}`}
              aria-pressed={channel === provider}
              onClick={() => setChannel(provider)}
            >
              {channelLabel(provider)}
            </button>
          ))}
        </div>
        <div className="segmented" role="group" aria-label="View">
          <button
            className={view === "table" ? "on" : ""}
            aria-pressed={view === "table"}
            onClick={() => setView("table")}
          >
            <List size={14} /> Table
          </button>
          <button
            className={view === "kanban" ? "on" : ""}
            aria-pressed={view === "kanban"}
            onClick={() => setView("kanban")}
          >
            <Kanban size={14} /> Pipeline
          </button>
        </div>
      </div>
      {picked.size > 0 && (
        <div className="bulk-bar" role="region" aria-label="Bulk actions">
          <strong>{picked.size} selected</strong>
          <form
            className="bulk-tag"
            onSubmit={(event) => {
              event.preventDefault();
              if (tag.trim()) bulk("tag", tag.trim());
            }}
          >
            <input
              value={tag}
              onChange={(event) => setTag(event.target.value)}
              placeholder="Tag name"
              maxLength={40}
              aria-label="Tag to apply"
            />
            <button
              className="button secondary small"
              disabled={feedback.busy || !tag.trim()}
            >
              <Tag size={13} /> Apply tag
            </button>
          </form>
          <select
            aria-label="Change stage"
            value=""
            disabled={feedback.busy}
            onChange={(event) =>
              event.target.value && bulk("stage", event.target.value)
            }
          >
            <option value="">Change stage…</option>
            {STAGES.map((stage) => (
              <option key={stage.id} value={stage.id}>
                {stage.label}
              </option>
            ))}
          </select>
          {manager && (
            <button
              className="button secondary small"
              onClick={() => setBroadcast(true)}
              disabled={feedback.busy}
            >
              <Megaphone size={13} /> Send broadcast
            </button>
          )}
          <button
            className="icon-button"
            aria-label="Clear selection"
            onClick={() => setPicked(new Set())}
          >
            <X size={15} />
          </button>
        </div>
      )}
      {loading ? (
        <p className="loading-text">Loading contacts…</p>
      ) : !leads.length ? (
        <Empty>
          {search || channel
            ? "No contacts match these filters."
            : "No contacts yet. Leads appear here when someone comments, replies to a story or sends a message."}
        </Empty>
      ) : view === "table" ? (
        <div className="table-scroll crm-table">
          <table>
            <thead>
              <tr>
                <th>
                  <input
                    type="checkbox"
                    aria-label="Select all contacts"
                    checked={allPicked}
                    onChange={() =>
                      setPicked(
                        allPicked
                          ? new Set()
                          : new Set(leads.map((lead) => lead.id)),
                      )
                    }
                  />
                </th>
                <th>Contact</th>
                <th>Source</th>
                <th>Tags</th>
                <th>Assigned</th>
                <th>Messages</th>
                <th>Stage</th>
              </tr>
            </thead>
            <tbody>
              {leads.map((lead) => {
                const link = inboxLink(lead);
                return (
                  <tr
                    key={lead.id}
                    className={picked.has(lead.id) ? "picked" : ""}
                  >
                    <td>
                      <input
                        type="checkbox"
                        aria-label={`Select ${lead.name || "contact"}`}
                        checked={picked.has(lead.id)}
                        onChange={() => toggle(lead.id)}
                      />
                    </td>
                    <td>
                      <span className="contact-cell">
                        <span className="user-avatar">
                          {initials(lead.name || "?")}
                        </span>
                        <span>
                          {link ? (
                            <Link href={link}>
                              <strong>{lead.name || "Unknown lead"}</strong>
                            </Link>
                          ) : (
                            <strong>{lead.name || "Unknown lead"}</strong>
                          )}
                          <span className="row-sub">
                            {lead.email || "No email yet"}
                          </span>
                        </span>
                      </span>
                    </td>
                    <td>
                      <span className="badge-row">
                        {lead.channels.length
                          ? lead.channels.map((provider) => (
                              <ChannelBadge
                                key={provider}
                                provider={provider}
                              />
                            ))
                          : "—"}
                      </span>
                    </td>
                    <td>
                      <span className="badge-row">
                        {lead.tags.length ? (
                          lead.tags.map((item) => (
                            <span key={item} className="tag-chip">
                              {item}
                            </span>
                          ))
                        ) : (
                          <span className="muted-text">—</span>
                        )}
                      </span>
                    </td>
                    <td className="small">
                      {memberName(lead.assigned_to) || "—"}
                    </td>
                    <td className="num">{lead.message_count}</td>
                    <td>
                      <select
                        className={`stage-pill stage-${lead.stage}`}
                        aria-label={`Stage for ${lead.name || "contact"}`}
                        value={lead.stage}
                        onChange={(event) =>
                          moveStage(lead, event.target.value)
                        }
                      >
                        {STAGES.map((stage) => (
                          <option key={stage.id} value={stage.id}>
                            {stage.label}
                          </option>
                        ))}
                      </select>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="kanban" aria-label="Pipeline">
          {STAGES.map((stage) => {
            const cards = leads.filter((lead) => lead.stage === stage.id);
            return (
              <section
                key={stage.id}
                className={`kanban-column ${dragging ? "droppable" : ""}`}
                aria-label={`${stage.label}: ${cards.length}`}
                onDragOver={(event) => event.preventDefault()}
                onDrop={(event) => drop(event, stage.id)}
              >
                <header>
                  <span className={`stage-dot stage-${stage.id}`} />
                  {stage.label}
                  <span className="nav-count">{cards.length}</span>
                </header>
                {cards.map((lead) => {
                  const link = inboxLink(lead);
                  return (
                    <article
                      key={lead.id}
                      className={`kanban-card ${dragging === lead.id ? "dragging" : ""}`}
                      draggable
                      onDragStart={(event) => {
                        event.dataTransfer.setData("text/plain", lead.id);
                        event.dataTransfer.effectAllowed = "move";
                        setDragging(lead.id);
                      }}
                      onDragEnd={() => setDragging(null)}
                    >
                      <div className="kanban-card-top">
                        <input
                          type="checkbox"
                          aria-label={`Select ${lead.name || "contact"}`}
                          checked={picked.has(lead.id)}
                          onChange={() => toggle(lead.id)}
                        />
                        <strong>{lead.name || "Unknown lead"}</strong>
                      </div>
                      <span className="badge-row">
                        {lead.channels.map((provider) => (
                          <ChannelBadge
                            key={provider}
                            provider={provider}
                            compact
                          />
                        ))}
                        {lead.tags.slice(0, 3).map((item) => (
                          <span key={item} className="tag-chip">
                            {item}
                          </span>
                        ))}
                      </span>
                      <footer>
                        <span className="muted-text">
                          {memberName(lead.assigned_to) || "Unassigned"}
                        </span>
                        {link && (
                          <Link
                            href={link}
                            aria-label={`Open conversation with ${lead.name || "contact"}`}
                          >
                            <MessagesSquare size={14} /> {lead.message_count}
                          </Link>
                        )}
                      </footer>
                      {/* Keyboard and touch alternative to dragging. */}
                      <select
                        className="kanban-move"
                        aria-label={`Move ${lead.name || "contact"} to stage`}
                        value={lead.stage}
                        onChange={(event) =>
                          moveStage(lead, event.target.value)
                        }
                      >
                        {STAGES.map((option) => (
                          <option key={option.id} value={option.id}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                    </article>
                  );
                })}
                {!cards.length && (
                  <p className="kanban-empty">Drop contacts here</p>
                )}
              </section>
            );
          })}
        </div>
      )}
      {more && (
        <div className="load-more">
          <button
            className="button secondary small"
            disabled={feedback.busy}
            onClick={() => feedback.run(() => load(page + 1))}
          >
            Load more ({leads.length} of {total})
          </button>
        </div>
      )}
      {broadcast && (
        <Modal title="Send broadcast" onClose={() => setBroadcast(false)}>
          <form
            onSubmit={(event) => {
              event.preventDefault();
              const text = String(
                new FormData(event.currentTarget).get("text") || "",
              ).trim();
              if (text) sendBroadcast(text);
            }}
          >
            <p>
              Sends to {picked.size} selected contact
              {picked.size === 1 ? "" : "s"}. Meta only allows free-form
              messages within 24 hours of a customer&apos;s last message, so
              anyone outside that window is skipped.
            </p>
            <ErrorNotice error={feedback.error} />
            <label>
              Message
              <textarea name="text" maxLength={2000} required rows={4} />
            </label>
            <button className="button primary" disabled={feedback.busy}>
              <Megaphone size={15} /> Send
            </button>
          </form>
        </Modal>
      )}
    </>
  );
}
