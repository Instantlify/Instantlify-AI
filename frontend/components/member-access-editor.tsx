"use client";

import { useEffect, useState } from "react";
import { api, type Connection, type Member, type Page } from "@/lib/api";
import { channelLabel } from "@/lib/channels";
import { ErrorNotice, Modal, useFeedback } from "@/components/ui";

/** Mirrors backend tenants/access.py SECTIONS. */
const SECTIONS: { id: string; label: string }[] = [
  { id: "inbox", label: "Inbox" },
  { id: "crm", label: "CRM" },
  { id: "automations", label: "Automations" },
  { id: "agent", label: "AI agent" },
  { id: "analytics", label: "Analytics" },
  { id: "integrations", label: "Integrations" },
  { id: "payments", label: "Payments" },
  { id: "bio", label: "Link in bio" },
  { id: "forms", label: "Forms" },
  { id: "calendar", label: "Content calendar" },
  { id: "shield", label: "Comment shield" },
  { id: "deeplinks", label: "Tracking links" },
  { id: "webchat", label: "Web chat" },
  { id: "creator-kit", label: "Creator kit" },
];

/** Limit a teammate to some sections and channel accounts (empty = everything). */
export function MemberAccessEditor({
  prefix,
  member,
  onClose,
  onSaved,
}: {
  prefix: string;
  member: Member;
  onClose: () => void;
  onSaved: (member: Member) => void;
}) {
  const [sections, setSections] = useState<string[]>(
    member.allowed_sections || [],
  );
  const [accounts, setAccounts] = useState<string[]>(
    member.allowed_connections || [],
  );
  const [connections, setConnections] = useState<Connection[]>([]);
  const feedback = useFeedback();

  useEffect(() => {
    const controller = new AbortController();
    api<Page<Connection>>(
      `${prefix}/connections/`,
      "GET",
      undefined,
      controller.signal,
    )
      .then((page) => setConnections(page.results))
      .catch(() => undefined);
    return () => controller.abort();
  }, [prefix]);

  const toggle = (list: string[], set: (next: string[]) => void, id: string) =>
    set(list.includes(id) ? list.filter((item) => item !== id) : [...list, id]);

  async function save() {
    const updated = await feedback.run(() =>
      api<Member>(`${prefix}/members/${member.id}/`, "PATCH", {
        allowed_sections: sections,
        allowed_connections: accounts,
      }),
    );
    if (updated) {
      onSaved(updated);
      onClose();
    }
  }

  return (
    <Modal
      title={`Access for ${member.name || member.email}`}
      onClose={onClose}
    >
      <ErrorNotice error={feedback.error} />
      <div className="stack" style={{ gap: 12 }}>
        <fieldset className="stack" style={{ gap: 6, border: 0, padding: 0 }}>
          <legend>
            <strong>Sections</strong>{" "}
            <span className="muted-text">
              {sections.length ? `${sections.length} selected` : "All sections"}
            </span>
          </legend>
          <div
            style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 4 }}
          >
            {SECTIONS.map((item) => (
              <label key={item.id} className="inline">
                <input
                  type="checkbox"
                  checked={sections.includes(item.id)}
                  onChange={() => toggle(sections, setSections, item.id)}
                />
                {item.label}
              </label>
            ))}
          </div>
        </fieldset>
        <fieldset className="stack" style={{ gap: 6, border: 0, padding: 0 }}>
          <legend>
            <strong>Channel accounts</strong>{" "}
            <span className="muted-text">
              {accounts.length ? `${accounts.length} selected` : "All accounts"}
            </span>
          </legend>
          {connections.length ? (
            connections.map((connection) => (
              <label key={connection.id} className="inline">
                <input
                  type="checkbox"
                  checked={accounts.includes(connection.id)}
                  onChange={() => toggle(accounts, setAccounts, connection.id)}
                />
                {connection.display_name} · {channelLabel(connection.provider)}
              </label>
            ))
          ) : (
            <p className="muted-text">No channel accounts connected yet.</p>
          )}
        </fieldset>
        <p className="muted-text small">
          Leave everything unticked for full access. With accounts selected,
          this teammate only sees those accounts&rsquo; conversations and
          contacts.
        </p>
        <div className="row" style={{ gap: 8, justifyContent: "flex-end" }}>
          <button type="button" className="button secondary" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className="button primary"
            disabled={feedback.busy}
            onClick={save}
          >
            Save access
          </button>
        </div>
      </div>
    </Modal>
  );
}
