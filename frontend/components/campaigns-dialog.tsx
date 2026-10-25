"use client";

import { useEffect, useState } from "react";
import { Plus, RefreshCw, Send, Trash2 } from "lucide-react";
import { api, message, type Connection, type FlowButton } from "@/lib/api";
import {
  ErrorNotice,
  Modal,
  Pill,
  SuccessNotice,
  useFeedback,
} from "@/components/ui";

type Audience = {
  mode: "all" | "filtered" | "selected";
  lead_ids?: string[];
  tags?: string[];
  stages?: string[];
  search?: string;
};
type Draft = {
  id?: string;
  name: string;
  connection_id: string | null;
  text: string;
  buttons: FlowButton[];
  media_url: string;
  media_type: "image" | "video";
  tag: string;
  audience: Audience;
  scheduled_at: string | null;
};
type Campaign = Draft & {
  id: string;
  status: string;
  expected_count: number;
  counts: Record<string, number>;
  created_at: string;
};
type AudiencePreview = {
  eligible: number;
  sample: { name: string; lead_id: string }[];
};
type Recipient = {
  id: string;
  lead_id: string | null;
  name: string;
  status: string;
  error_code: string;
};

function localTime(iso: string | null) {
  if (!iso) return "";
  const date = new Date(iso);
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function CampaignsDialog({
  prefix,
  connections,
  selectedLeadIds,
  onClose,
}: {
  prefix: string;
  connections: Connection[];
  selectedLeadIds: string[];
  onClose: () => void;
}) {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [step, setStep] = useState(0);
  const [tagsInput, setTagsInput] = useState("");
  const [showMedia, setShowMedia] = useState(false);
  const [preview, setPreview] = useState<AudiencePreview | null>(null);
  const [recipients, setRecipients] = useState<Recipient[] | null>(null);
  const [loading, setLoading] = useState(true);
  const feedback = useFeedback();
  const accounts = connections.filter(
    (item) =>
      item.status === "active" &&
      !item.locked &&
      ["instagram", "messenger", "whatsapp", "telegram"].includes(
        item.provider,
      ),
  );

  useEffect(() => {
    if (draft) return;
    const controller = new AbortController();
    const load = () =>
      api<Campaign[]>(
        `${prefix}/campaigns/`,
        "GET",
        undefined,
        controller.signal,
      )
        .then(setCampaigns)
        .catch((err) => {
          if (!controller.signal.aborted) feedback.setError(message(err));
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    void load();
    const timer = window.setInterval(load, 5000);
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefix, draft]);

  function edit(item?: Campaign) {
    setDraft(
      item
        ? structuredClone(item)
        : {
            name: "New campaign",
            connection_id: accounts.length === 1 ? accounts[0].id : null,
            text: "",
            buttons: [],
            media_url: "",
            media_type: "image",
            tag: "",
            audience: selectedLeadIds.length
              ? { mode: "selected", lead_ids: selectedLeadIds }
              : { mode: "all" },
            scheduled_at: null,
          },
    );
    setTagsInput(item?.audience.tags?.join(", ") || "");
    setShowMedia(Boolean(item?.media_url));
    setPreview(null);
    setStep(0);
    feedback.setError("");
  }
  function patch(values: Partial<Draft>) {
    setDraft((value) => (value ? { ...value, ...values } : value));
    setPreview(null);
  }
  function audience(values: Partial<Audience>) {
    if (draft) patch({ audience: { ...draft.audience, ...values } });
  }
  function payload() {
    if (!draft) throw new Error("Open a campaign draft first.");
    return {
      name: draft.name,
      connection_id: draft.connection_id,
      text: draft.text,
      buttons: draft.buttons,
      media_url: draft.media_url,
      media_type: draft.media_type,
      tag: draft.tag,
      scheduled_at: draft.scheduled_at,
      audience: {
        ...draft.audience,
        tags: tagsInput
          .split(",")
          .map((value) => value.trim())
          .filter(Boolean),
      },
    };
  }
  async function persist() {
    const saved = await api<Campaign>(
      `${prefix}/campaigns/${draft?.id ? `${draft.id}/` : ""}`,
      draft?.id ? "PATCH" : "POST",
      payload(),
    );
    setDraft(saved);
    return saved;
  }
  async function review() {
    await feedback.run(async () => {
      if (!draft?.name.trim() || !draft.connection_id)
        throw new Error("Name the campaign and choose a sending account.");
      if (
        (!draft.text.trim() && !draft.media_url) ||
        (draft.buttons.length && !draft.text.trim())
      )
        throw new Error(
          "Write a message or add media. Link buttons need message text.",
        );
      setPreview(
        await api<AudiencePreview>(
          `${prefix}/campaigns/audience/`,
          "POST",
          payload(),
        ),
      );
      setStep(2);
    });
  }

  return (
    <Modal
      title={
        draft
          ? `Campaign · ${["Compose", "Audience", "Review"][step]}`
          : "Campaigns"
      }
      onClose={onClose}
    >
      <ErrorNotice error={feedback.error} />
      <SuccessNotice notice={feedback.notice} />
      {!draft ? (
        <>
          <div className="row between">
            <button className="button primary small" onClick={() => edit()}>
              <Plus size={14} /> New campaign
            </button>
            <button
              className="icon-button"
              aria-label="Refresh campaigns"
              onClick={() =>
                void feedback.run(async () =>
                  setCampaigns(await api<Campaign[]>(`${prefix}/campaigns/`)),
                )
              }
            >
              <RefreshCw size={15} />
            </button>
          </div>
          {recipients ? (
            <>
              <button
                className="text-button"
                onClick={() => setRecipients(null)}
              >
                Back to campaigns
              </button>
              <p>Latest {recipients.length} recipients (up to 1000).</p>
              {recipients.map((row) => (
                <div
                  key={row.id}
                  className="card"
                  style={{ padding: 12, marginTop: 8 }}
                >
                  <strong>{row.name}</strong> <Pill>{row.status}</Pill>
                  {row.error_code && (
                    <p>{row.error_code.replaceAll("_", " ")}</p>
                  )}
                </div>
              ))}
            </>
          ) : (
            <>
              <p>
                Message contacts with a private conversation in the last 24
                hours. Every delivery is checked again before sending.
              </p>
              {loading && <p>Loading campaigns…</p>}
              {!loading && !campaigns.length && (
                <p>Your saved drafts and delivery results will appear here.</p>
              )}
              {campaigns.map((item) => (
                <article
                  key={item.id}
                  className="card"
                  style={{ padding: 16, marginTop: 12 }}
                >
                  <div className="row between">
                    <strong>{item.name}</strong>
                    <Pill>{item.status}</Pill>
                  </div>
                  <p>
                    {item.expected_count} recipients · {item.counts.sent || 0}{" "}
                    sent · {item.counts.queued || 0} queued ·{" "}
                    {(item.counts.failed || 0) + (item.counts.unknown || 0)}{" "}
                    need attention · {item.counts.skipped || 0} skipped
                  </p>
                  <div className="row" style={{ flexWrap: "wrap" }}>
                    {item.status === "draft" ? (
                      <>
                        <button
                          className="button secondary small"
                          onClick={() => edit(item)}
                        >
                          Edit draft
                        </button>
                        <button
                          className="icon-button"
                          aria-label={`Delete draft ${item.name}`}
                          onClick={() =>
                            void feedback.run(async () => {
                              await api(
                                `${prefix}/campaigns/${item.id}/`,
                                "DELETE",
                              );
                              setCampaigns((rows) =>
                                rows.filter((row) => row.id !== item.id),
                              );
                            })
                          }
                        >
                          <Trash2 size={14} />
                        </button>
                      </>
                    ) : (
                      <button
                        className="button secondary small"
                        onClick={() =>
                          void feedback.run(async () =>
                            setRecipients(
                              await api<Recipient[]>(
                                `${prefix}/campaigns/${item.id}/recipients/`,
                              ),
                            ),
                          )
                        }
                      >
                        Delivery results
                      </button>
                    )}
                    {["queued", "sending"].includes(item.status) && (
                      <button
                        className="button secondary small"
                        onClick={() =>
                          void feedback.run(async () => {
                            const updated = await api<Campaign>(
                              `${prefix}/campaigns/${item.id}/cancel/`,
                              "POST",
                              {},
                            );
                            setCampaigns((rows) =>
                              rows.map((row) =>
                                row.id === item.id ? updated : row,
                              ),
                            );
                          }, "Unqueued recipients cancelled. Messages already queued may still be delivered.")
                        }
                      >
                        Stop unqueued recipients
                      </button>
                    )}
                  </div>
                </article>
              ))}
            </>
          )}
        </>
      ) : (
        <div className="form-grid">
          <div className="row">
            <Pill>{step + 1} of 3</Pill>
            <span>{draft.id ? "Saved draft" : "New draft"}</span>
          </div>
          {step === 0 && (
            <>
              <label>
                Campaign name
                <input
                  maxLength={100}
                  value={draft.name}
                  onChange={(e) => patch({ name: e.target.value })}
                />
              </label>
              <label>
                Sending account
                <select
                  aria-label="Sending account"
                  value={draft.connection_id || ""}
                  onChange={(e) =>
                    patch({ connection_id: e.target.value || null })
                  }
                >
                  <option value="">Choose an account</option>
                  {accounts.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.display_name} · {item.provider}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Campaign message
                <textarea
                  rows={5}
                  maxLength={1000}
                  value={draft.text}
                  onChange={(e) => patch({ text: e.target.value })}
                />
                <small>
                  {draft.text.length}/1000 · Use {"{{name}}"} to include the
                  contact’s name.
                </small>
              </label>
              {draft.buttons.map((button, index) => (
                <fieldset className="form-grid" key={index}>
                  <legend>Button {index + 1}</legend>
                  <label>
                    Button title
                    <input
                      maxLength={20}
                      value={button.title}
                      onChange={(e) =>
                        patch({
                          buttons: draft.buttons.map((item, i) =>
                            i === index
                              ? { ...item, title: e.target.value }
                              : item,
                          ),
                        })
                      }
                    />
                  </label>
                  <label>
                    Button HTTPS URL
                    <input
                      type="url"
                      value={button.url || ""}
                      onChange={(e) =>
                        patch({
                          buttons: draft.buttons.map((item, i) =>
                            i === index
                              ? { ...item, url: e.target.value }
                              : item,
                          ),
                        })
                      }
                    />
                  </label>
                  <button
                    className="text-button"
                    onClick={() =>
                      patch({
                        buttons: draft.buttons.filter((_, i) => i !== index),
                      })
                    }
                  >
                    Remove button
                  </button>
                </fieldset>
              ))}
              <button
                className="button secondary small"
                disabled={draft.buttons.length >= 3}
                onClick={() =>
                  patch({
                    buttons: [
                      ...draft.buttons,
                      { type: "web_url", title: "Open", url: "https://" },
                    ],
                  })
                }
              >
                Add link button
              </button>
              <label className="inline">
                <input
                  type="checkbox"
                  checked={showMedia}
                  onChange={(e) => {
                    setShowMedia(e.target.checked);
                    if (!e.target.checked) patch({ media_url: "" });
                  }}
                />{" "}
                Include a photo or video
              </label>
              {showMedia && (
                <>
                  <label>
                    Media type
                    <select
                      aria-label="Media type"
                      value={draft.media_type}
                      onChange={(e) =>
                        patch({
                          media_type: e.target.value as "image" | "video",
                        })
                      }
                    >
                      <option value="image">Photo</option>
                      <option value="video">Video</option>
                    </select>
                  </label>
                  <label>
                    Public HTTPS media URL
                    <input
                      type="url"
                      value={draft.media_url}
                      onChange={(e) => patch({ media_url: e.target.value })}
                    />
                    <small>
                      Use a direct image or video file URL. Media is sent as a
                      separate message after any text.
                    </small>
                  </label>
                </>
              )}
              <label>
                Tag delivered recipients
                <input
                  maxLength={40}
                  value={draft.tag}
                  onChange={(e) => patch({ tag: e.target.value })}
                />
              </label>
            </>
          )}
          {step === 1 && (
            <>
              <label>
                Audience
                <select
                  aria-label="Campaign audience"
                  value={draft.audience.mode}
                  onChange={(e) =>
                    audience({
                      mode: e.target.value as Audience["mode"],
                      lead_ids:
                        e.target.value === "selected" ? selectedLeadIds : [],
                    })
                  }
                >
                  <option value="all">
                    All eligible contacts on this account
                  </option>
                  <option value="filtered">Filter eligible contacts</option>
                  <option
                    value="selected"
                    disabled={
                      !selectedLeadIds.length &&
                      !draft.audience.lead_ids?.length
                    }
                  >
                    Selected CRM contacts
                  </option>
                </select>
              </label>
              {draft.audience.mode === "selected" && (
                <p>
                  {draft.audience.lead_ids?.length || 0} selected contacts.
                  Contacts on other accounts or outside the service window are
                  excluded.
                </p>
              )}
              {draft.audience.mode === "filtered" && (
                <>
                  <label>
                    Contact search
                    <input
                      maxLength={150}
                      value={draft.audience.search || ""}
                      onChange={(e) => audience({ search: e.target.value })}
                    />
                  </label>
                  <label>
                    Required tags, separated by commas
                    <input
                      value={tagsInput}
                      onChange={(e) => {
                        setTagsInput(e.target.value);
                        setPreview(null);
                      }}
                    />
                  </label>
                  <fieldset>
                    <legend>Contact stages (leave empty for all)</legend>
                    {[
                      "new",
                      "qualified",
                      "interested",
                      "booked",
                      "won",
                      "lost",
                    ].map((stage) => (
                      <label className="inline" key={stage}>
                        <input
                          type="checkbox"
                          checked={
                            draft.audience.stages?.includes(stage) || false
                          }
                          onChange={(e) =>
                            audience({
                              stages: e.target.checked
                                ? [...(draft.audience.stages || []), stage]
                                : (draft.audience.stages || []).filter(
                                    (value) => value !== stage,
                                  ),
                            })
                          }
                        />
                        {stage}
                      </label>
                    ))}
                  </fieldset>
                </>
              )}
              <label>
                Optional scheduled time
                <input
                  type="datetime-local"
                  value={localTime(draft.scheduled_at)}
                  onChange={(e) =>
                    patch({
                      scheduled_at: e.target.value
                        ? new Date(e.target.value).toISOString()
                        : null,
                    })
                  }
                />
                <small>
                  Your browser’s local time. Eligibility is checked again when
                  the campaign runs, so a contact’s messaging window may expire
                  before a scheduled send.
                </small>
              </label>
            </>
          )}
          {step === 2 && preview && (
            <>
              <h3>{draft.name}</h3>
              <p>
                Sending from{" "}
                {
                  accounts.find((item) => item.id === draft.connection_id)
                    ?.display_name
                }{" "}
                to <strong>{preview.eligible} eligible contacts</strong>.
              </p>
              <div
                className="card"
                style={{ padding: 18, whiteSpace: "pre-wrap" }}
              >
                {draft.text || "Media message"}
                {draft.buttons.map((button, index) => (
                  <p key={index}>
                    {button.title} → {button.url}
                  </p>
                ))}
                {draft.media_url && (
                  <p>
                    {draft.media_type === "image" ? "Photo" : "Video"}:{" "}
                    {draft.media_url}
                  </p>
                )}
              </div>
              {draft.tag && <p>Tag after delivery: {draft.tag}</p>}
              {draft.scheduled_at && (
                <p>
                  Scheduled for {new Date(draft.scheduled_at).toLocaleString()}
                </p>
              )}
              {!!preview.sample.length && (
                <p>
                  Audience sample:{" "}
                  {preview.sample.map((item) => item.name).join(", ")}
                </p>
              )}
              {!preview.eligible && (
                <p>
                  No contacts currently match. Adjust the audience or save this
                  as a draft.
                </p>
              )}
            </>
          )}
          <div className="row" style={{ flexWrap: "wrap" }}>
            <button
              className="button secondary small"
              disabled={feedback.busy}
              onClick={() =>
                void feedback.run(async () => {
                  await persist();
                  setDraft(null);
                }, "Campaign draft saved.")
              }
            >
              Save draft
            </button>
            {step > 0 && (
              <button
                className="button secondary small"
                onClick={() => setStep(step - 1)}
              >
                Back
              </button>
            )}
            {step === 0 && (
              <button
                className="button primary small"
                onClick={() => setStep(1)}
              >
                Choose audience
              </button>
            )}
            {step === 1 && (
              <button
                className="button primary small"
                disabled={feedback.busy}
                onClick={() => void review()}
              >
                Review audience
              </button>
            )}
            {step === 2 && (
              <button
                className="button primary small"
                disabled={feedback.busy || !preview?.eligible}
                onClick={() =>
                  void feedback.run(async () => {
                    const saved = await persist();
                    await api(
                      `${prefix}/campaigns/${saved.id}/launch/`,
                      "POST",
                      {},
                    );
                    setDraft(null);
                  }, "Campaign queued. Delivery progress appears below.")
                }
              >
                <Send size={13} />
                {draft.scheduled_at ? "Schedule campaign" : "Send campaign"}
              </button>
            )}
            <button
              className="text-button"
              disabled={feedback.busy}
              onClick={() => setDraft(null)}
            >
              Back to campaigns
            </button>
          </div>
        </div>
      )}
    </Modal>
  );
}
