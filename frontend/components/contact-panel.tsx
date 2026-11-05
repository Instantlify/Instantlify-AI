"use client";

import {
  ValidatedForm,
  ValidatedInput,
  ValidatedSelect,
} from "@/components/validated-form";

import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { contactSourceLabel } from "@/lib/contact-source";
import {
  ExternalLink,
  MessageSquare,
  RefreshCw,
  Trash2,
  UserCheck,
  X,
} from "lucide-react";
import {
  api,
  type Integration,
  type LeadRow,
  type Member,
  type Message,
  type Note,
  type Page,
} from "@/lib/api";
import { ChannelBadge, channelLabel } from "@/lib/channels";
import { ContactAvatar } from "@/components/contact-avatar";
import { ErrorNotice, Pill, SuccessNotice, useFeedback } from "@/components/ui";

export const STAGES = [
  { id: "new", label: "No stage" },
  { id: "qualified", label: "Qualified" },
  { id: "interested", label: "Interested" },
  { id: "booked", label: "Booked" },
  { id: "won", label: "Won" },
  { id: "lost", label: "Lost" },
];

const CRM_SYNC_TARGETS: Record<string, string> = {
  airtable: "Airtable",
  notion: "Notion",
  gohighlevel: "GoHighLevel",
  attio: "Attio",
  google_sheets: "Google Sheets",
  mailerlite: "MailerLite",
  klaviyo: "Klaviyo",
  systeme_io: "Systeme.io",
};

export function relativeTime(iso: string | null | undefined, now = Date.now()) {
  if (!iso) return "";
  const diff = Math.max(0, now - new Date(iso).getTime());
  const minutes = Math.round(diff / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days} d ago`;
  return new Date(iso).toLocaleDateString();
}

/** Everything the team can learn or do about one contact: where they wrote from,
 * their conversation, stage, tags, details, notes and housekeeping. */
export function ContactPanel({
  lead,
  leads,
  members,
  integrations,
  prefix,
  workspaceId,
  manager,
  onClose,
  onChange,
  onDelete,
}: {
  lead: LeadRow;
  leads: LeadRow[];
  members: Member[];
  integrations: Integration[];
  prefix: string;
  workspaceId: string;
  manager: boolean;
  onClose: () => void;
  onChange: (lead: LeadRow) => void;
  onDelete: (id: string) => void;
}) {
  const feedback = useFeedback();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [recent, setRecent] = useState<Message[]>([]);
  const [notes, setNotes] = useState<Note[]>([]);
  const [note, setNote] = useState("");
  const [tag, setTag] = useState("");
  const [field, setField] = useState({ key: "", value: "" });
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [mergeSource, setMergeSource] = useState("");
  const [syncTarget, setSyncTarget] = useState("");
  const conversationId = lead.conversation_id;
  const linked = lead.identities.length > 0;

  useEffect(() => {
    const controller = new AbortController();
    const thread = conversationId
      ? api<Page<Message>>(
          `${prefix}/conversations/${conversationId}/messages/?page_size=5`,
          "GET",
          undefined,
          controller.signal,
        ).then((page) => [...page.results].reverse())
      : Promise.resolve([]);
    const internal = conversationId
      ? api<Note[]>(
          `${prefix}/conversations/${conversationId}/notes/`,
          "GET",
          undefined,
          controller.signal,
        )
      : Promise.resolve([]);
    thread.then(setRecent).catch(() => undefined);
    internal.then(setNotes).catch(() => undefined);
    return () => controller.abort();
  }, [prefix, conversationId]);

  // Native modality makes the background inert and restores the opening control.
  useEffect(() => {
    const dialog = dialogRef.current;
    const opener =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    const overflow = document.body.style.overflow;
    dialog?.showModal();
    document.body.style.overflow = "hidden";
    return () => {
      dialog?.close();
      document.body.style.overflow = overflow;
      if (opener?.isConnected) opener.focus();
    };
  }, []);

  const patch = async (data: Partial<LeadRow>, success?: string) => {
    const updated = await feedback.run(
      () => api<LeadRow>(`${prefix}/leads/${lead.id}/`, "PATCH", data),
      success,
    );
    if (updated) onChange(updated);
    return updated;
  };

  const addTag = async (event: FormEvent) => {
    event.preventDefault();
    const value = tag.trim();
    if (!value || lead.tags.includes(value)) return;
    const done = await patch({ tags: [...lead.tags, value] });
    if (done) setTag("");
  };

  const addField = async (event: FormEvent) => {
    event.preventDefault();
    const key = field.key.trim();
    if (!key) return;
    const done = await patch({
      fields: { ...lead.fields, [key]: field.value.trim() },
    });
    if (done) setField({ key: "", value: "" });
  };

  const removeField = (key: string) => {
    const rest = { ...lead.fields };
    delete rest[key];
    return patch({ fields: rest });
  };

  const assign = async (userId: number | null) => {
    await patch({ assigned_to: userId }, userId ? "Contact assigned." : "Contact unassigned.");
  };

  const addNote = async (event: FormEvent) => {
    event.preventDefault();
    if (!conversationId || !note.trim()) return;
    await feedback.run(async () => {
      await api(`${prefix}/conversations/${conversationId}/notes/`, "POST", {
        text: note.trim(),
      });
      setNote("");
      setNotes(
        await api<Note[]>(`${prefix}/conversations/${conversationId}/notes/`),
      );
    });
  };

  const refreshProfile = async () => {
    const updated = await feedback.run(
      () => api<LeadRow>(`${prefix}/leads/${lead.id}/refresh/`, "POST", {}),
      "Profile refreshed from the channel.",
    );
    if (updated) onChange(updated);
  };

  const remove = async () => {
    const done = await feedback.run(async () => {
      await api(`${prefix}/leads/${lead.id}/`, "DELETE");
      return true;
    });
    if (done) onDelete(lead.id);
  };

  const merge = async (event: FormEvent) => {
    event.preventDefault();
    if (!mergeSource) return;
    const updated = await feedback.run(
      () =>
        api<LeadRow>(`${prefix}/leads/${lead.id}/merge/`, "POST", {
          source_id: mergeSource,
        }),
      "Contacts merged.",
    );
    if (updated) {
      onDelete(mergeSource);
      onChange(updated);
      setMergeSource("");
    }
  };

  const sync = async (event: FormEvent) => {
    event.preventDefault();
    if (!syncTarget) return;
    await feedback.run(
      () =>
        api(`${prefix}/leads/${lead.id}/sync/`, "POST", {
          provider: syncTarget,
        }),
      `Sending to ${CRM_SYNC_TARGETS[syncTarget]}…`,
    );
  };

  const memberName = (userId: number | null) => {
    const member = members.find((item) => item.user_id === userId);
    return member ? member.name || member.email : "";
  };
  const syncTargets = integrations.filter(
    (item) =>
      item.enabled && item.configured && CRM_SYNC_TARGETS[item.provider],
  );
  const duplicates = leads.filter((item) => item.id !== lead.id);
  const name = lead.name || "Unknown contact";

  return (
    <>
      <dialog
        ref={dialogRef}
        className="contact-panel"
        role="dialog"
        aria-modal="true"
        aria-label={`Contact ${name}`}
        onCancel={(event) => {
          event.preventDefault();
          onClose();
        }}
        onClick={(event) => {
          if (event.target !== event.currentTarget) return;
          const bounds = event.currentTarget.getBoundingClientRect();
          if (
            event.clientX < bounds.left ||
            event.clientX > bounds.right ||
            event.clientY < bounds.top ||
            event.clientY > bounds.bottom
          )
            onClose();
        }}
        onKeyDown={(event) => {
          if (event.key !== "Tab") return;
          const controls = Array.from(
            event.currentTarget.querySelectorAll<HTMLElement>(
              "button, a[href], input, select, textarea, [tabindex]",
            ),
          ).filter(
            (element) =>
              element.tabIndex >= 0 &&
              !element.matches(":disabled") &&
              element.getClientRects().length > 0,
          );
          const first = controls[0];
          const last = controls[controls.length - 1];
          if (!first) {
            event.preventDefault();
            event.currentTarget.focus();
          } else if (
            event.shiftKey &&
            (document.activeElement === first ||
              document.activeElement === event.currentTarget)
          ) {
            event.preventDefault();
            last.focus();
          } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first.focus();
          }
        }}
      >
        <header className="contact-panel-head">
          <ContactAvatar name={name} avatarUrl={lead.avatar_url} size={56} />
          <div className="contact-panel-title">
            <ValidatedInput
              className="contact-name-input"
              aria-label="Contact name"
              defaultValue={lead.name}
              key={`${lead.id}-name`}
              maxLength={150}
              onBlur={(event) => {
                const value = event.target.value.trim();
                if (value && value !== lead.name) patch({ name: value });
              }}
            />
            <div className="contact-panel-sub">
              {lead.handle && <span>{lead.handle}</span>}
              {lead.opted_out && <Pill tone="bad">Opted out</Pill>}
              {(!linked || lead.fields?.source === "form") && (
                <Pill tone="neutral">{contactSourceLabel(lead)}</Pill>
              )}
            </div>
          </div>
          <button
            type="button"
            className="icon-button"
            aria-label="Close contact"
            onClick={onClose}
          >
            <X size={16} />
          </button>
        </header>

        <div className="contact-panel-actions">
          {conversationId ? (
            <Link
              className="button primary small"
              href={`/w/${workspaceId}/inbox?conversation=${conversationId}`}
            >
              <MessageSquare size={13} /> Open chat
            </Link>
          ) : (
            <span className="subtle">No conversation yet</span>
          )}
          {manager && linked && (
            <button
              type="button"
              className="button secondary small"
              onClick={refreshProfile}
              disabled={feedback.busy}
            >
              <RefreshCw size={13} /> Refresh profile
            </button>
          )}
          {manager && (
            <button
              type="button"
              className="button secondary small contact-delete"
              onClick={() => setConfirmDelete(true)}
              disabled={feedback.busy}
            >
              <Trash2 size={13} /> Delete
            </button>
          )}
        </div>
        {confirmDelete && (
          <div
            className="contact-confirm"
            role="alertdialog"
            aria-label="Delete contact"
          >
            <p>
              Delete <strong>{name}</strong> and their conversation history?
              This cannot be undone.
            </p>
            <div className="contact-confirm-actions">
              <button
                type="button"
                className="button secondary small"
                onClick={() => setConfirmDelete(false)}
              >
                Keep
              </button>
              <button
                type="button"
                className="button danger small"
                onClick={remove}
                disabled={feedback.busy}
              >
                Delete contact
              </button>
            </div>
          </div>
        )}

        <ErrorNotice error={feedback.error} />
        <SuccessNotice notice={feedback.notice} />

        <section className="contact-section">
          <h3>Channels</h3>
          {linked ? (
            <ul className="contact-channels">
              {lead.identities.map((identity) => (
                <li key={identity.id}>
                  <ChannelBadge provider={identity.provider} compact />
                  <div className="contact-channel-text">
                    <strong>{identity.connection_name}</strong>
                    <span>
                      {channelLabel(identity.provider)} · ID{" "}
                      {identity.external_id}
                    </span>
                  </div>
                  {identity.conversation_id && (
                    <Link
                      className="text-button"
                      href={`/w/${workspaceId}/inbox?conversation=${identity.conversation_id}`}
                    >
                      Chat
                    </Link>
                  )}
                  {identity.contact_link && (
                    <a
                      className="text-button"
                      href={identity.contact_link}
                      target="_blank"
                      rel="noreferrer"
                    >
                      WhatsApp <ExternalLink size={11} />
                    </a>
                  )}
                </li>
              ))}
            </ul>
          ) : (
            <p className="contact-hint">
              Not linked to a channel yet. When this person messages one of your
              connected accounts they appear as a new contact with their Meta
              profile. Merge that contact into this one to keep these notes and
              tags together.
            </p>
          )}
        </section>

        <section className="contact-section contact-grid">
          <label>
            Stage
            <ValidatedSelect
              value={lead.stage || "new"}
              onChange={(event) => patch({ stage: event.target.value })}
            >
              {STAGES.map((stage) => (
                <option key={stage.id} value={stage.id}>
                  {stage.label}
                </option>
              ))}
            </ValidatedSelect>
          </label>
          <label>
            Assigned to
            <ValidatedSelect
              value={lead.assigned_to ?? ""}
              disabled={!manager || feedback.busy}
              onChange={(event) =>
                assign(event.target.value ? Number(event.target.value) : null)
              }
            >
              <option value="">Unassigned</option>
              {members.map((member) => (
                <option key={member.id} value={member.user_id}>
                  {member.name || member.email}
                </option>
              ))}
            </ValidatedSelect>
          </label>
          <label>
            Email
            <ValidatedInput
              type="email"
              defaultValue={lead.email}
              key={`${lead.id}-email`}
              placeholder="name@example.com"
              maxLength={254}
              onBlur={(event) => {
                if (event.target.value !== lead.email)
                  patch({ email: event.target.value.trim() });
              }}
            />
          </label>
          <label>
            Opt-out
            <ValidatedSelect
              value={lead.opted_out ? "yes" : "no"}
              onChange={(event) =>
                patch({ opted_out: event.target.value === "yes" })
              }
            >
              <option value="no">Receives messages</option>
              <option value="yes">Opted out</option>
            </ValidatedSelect>
          </label>
        </section>

        <section className="contact-section">
          <h3>Tags</h3>
          <div className="contact-tags">
            {lead.tags.map((item) => (
              <span key={item} className="contact-tag">
                {item}
                <button
                  type="button"
                  aria-label={`Remove tag ${item}`}
                  onClick={() =>
                    patch({ tags: lead.tags.filter((t) => t !== item) })
                  }
                >
                  <X size={10} />
                </button>
              </span>
            ))}
            {!lead.tags.length && <span className="subtle">No tags yet</span>}
          </div>
          <ValidatedForm
            fieldErrors={feedback.fieldErrors}
            validationTarget={feedback.validationTarget}
            onEdit={() => feedback.setError("")}
            className="contact-inline-form"
            onSubmit={addTag}
          >
            <ValidatedInput
              aria-label="New tag"
              placeholder="Add a tag"
              maxLength={40}
              value={tag}
              onChange={(event) => setTag(event.target.value)}
            />
            <button className="button secondary small" disabled={!tag.trim()}>
              Add tag
            </button>
          </ValidatedForm>
        </section>

        <section className="contact-section">
          <h3>Details</h3>
          <dl className="contact-details">
            {Object.entries(lead.fields).map(([key, value]) => (
              <div key={key}>
                <dt>{key}</dt>
                <dd>
                  {String(value)}
                  <button
                    type="button"
                    className="icon-button"
                    aria-label={`Remove ${key}`}
                    onClick={() => removeField(key)}
                  >
                    <X size={11} />
                  </button>
                </dd>
              </div>
            ))}
            <div>
              <dt>Messages</dt>
              <dd>{lead.message_count}</dd>
            </div>
            <div>
              <dt>Last activity</dt>
              <dd>
                {lead.last_activity_at
                  ? relativeTime(lead.last_activity_at)
                  : "—"}
              </dd>
            </div>
            <div>
              <dt>Contact since</dt>
              <dd>{new Date(lead.created_at).toLocaleDateString()}</dd>
            </div>
            {lead.profile_synced_at && (
              <div>
                <dt>Profile synced</dt>
                <dd>{relativeTime(lead.profile_synced_at)}</dd>
              </div>
            )}
          </dl>
          <ValidatedForm
            fieldErrors={feedback.fieldErrors}
            validationTarget={feedback.validationTarget}
            onEdit={() => feedback.setError("")}
            className="contact-inline-form"
            onSubmit={addField}
          >
            <ValidatedInput
              name="key"
              aria-label="Field name"
              placeholder="Field, e.g. City"
              maxLength={60}
              value={field.key}
              onChange={(event) =>
                setField({ ...field, key: event.target.value })
              }
            />
            <ValidatedInput
              name="value"
              aria-label="Field value"
              placeholder="Value"
              maxLength={500}
              value={field.value}
              onChange={(event) =>
                setField({ ...field, value: event.target.value })
              }
            />
            <button
              className="button secondary small"
              disabled={!field.key.trim()}
            >
              Add field
            </button>
          </ValidatedForm>
        </section>

        {conversationId && (
          <section className="contact-section">
            <h3>Recent messages</h3>
            {recent.length ? (
              <ul className="contact-recent">
                {recent.map((item) => (
                  <li key={item.id} data-direction={item.direction}>
                    <span>
                      {item.direction === "inbound"
                        ? name
                        : item.author_name ||
                          (item.sender === "ai" ? "AI agent" : "You")}
                    </span>
                    <p>
                      {item.text ||
                        (item.kind === "voice" ? "Voice note" : "Attachment")}
                    </p>
                    <time>{relativeTime(item.created_at)}</time>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="subtle">No messages yet.</p>
            )}
          </section>
        )}

        {conversationId && (
          <section className="contact-section">
            <h3>Team notes</h3>
            {notes.length ? (
              <ul className="contact-notes">
                {notes.map((item) => (
                  <li key={item.id}>
                    <p>{item.text}</p>
                    <time>
                      {memberName(item.author_id) || "Team"} ·{" "}
                      {relativeTime(item.created_at)}
                    </time>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="subtle">Only your team sees notes.</p>
            )}
            <ValidatedForm
              fieldErrors={feedback.fieldErrors}
              validationTarget={feedback.validationTarget}
              onEdit={() => feedback.setError("")}
              className="contact-inline-form"
              onSubmit={addNote}
            >
              <ValidatedInput
                aria-label="New note"
                placeholder="Add a private note"
                maxLength={5000}
                value={note}
                onChange={(event) => setNote(event.target.value)}
              />
              <button
                className="button secondary small"
                disabled={!note.trim()}
              >
                Add note
              </button>
            </ValidatedForm>
          </section>
        )}

        {manager && (syncTargets.length > 0 || duplicates.length > 0) && (
          <section className="contact-section">
            <h3>Housekeeping</h3>
            {syncTargets.length > 0 && (
              <ValidatedForm
                fieldErrors={feedback.fieldErrors}
                validationTarget={feedback.validationTarget}
                onEdit={() => feedback.setError("")}
                className="contact-inline-form"
                onSubmit={sync}
              >
                <ValidatedSelect
                  aria-label="Send to CRM"
                  value={syncTarget}
                  onChange={(event) => setSyncTarget(event.target.value)}
                >
                  <option value="">Send to a connected CRM…</option>
                  {syncTargets.map((item) => (
                    <option key={item.id} value={item.provider}>
                      {CRM_SYNC_TARGETS[item.provider]}
                    </option>
                  ))}
                </ValidatedSelect>
                <button
                  className="button secondary small"
                  disabled={!syncTarget}
                >
                  Send
                </button>
              </ValidatedForm>
            )}
            {duplicates.length > 0 && (
              <ValidatedForm
                fieldErrors={feedback.fieldErrors}
                validationTarget={feedback.validationTarget}
                onEdit={() => feedback.setError("")}
                className="contact-inline-form"
                onSubmit={merge}
              >
                <ValidatedSelect
                  aria-label="Merge a duplicate into this contact"
                  value={mergeSource}
                  onChange={(event) => setMergeSource(event.target.value)}
                >
                  <option value="">Merge a duplicate into this contact…</option>
                  {duplicates.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name || "Unknown"}
                      {item.handle ? ` (${item.handle})` : ""}
                      {` · ${contactSourceLabel(item)}`}
                    </option>
                  ))}
                </ValidatedSelect>
                <button
                  className="button secondary small"
                  disabled={!mergeSource}
                >
                  <UserCheck size={13} /> Merge
                </button>
              </ValidatedForm>
            )}
          </section>
        )}
      </dialog>
    </>
  );
}
