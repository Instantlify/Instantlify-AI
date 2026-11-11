"use client";

import { useConfirmation } from "@/components/confirmation-provider";

import {
  ValidatedForm,
  ValidatedInput,
  ValidatedSelect,
} from "@/components/validated-form";

import { useEffect, useState } from "react";
import {
  ExternalLink,
  Plus,
  QrCode,
  Smartphone,
  Trash2,
  Copy,
  Check,
  Sparkles,
} from "lucide-react";
import { api, message, type DeepLink } from "@/lib/api";
import { useWorkspace } from "@/lib/workspace";
import {
  Empty,
  ErrorNotice,
  Modal,
  PageHeading,
  Panel,
  Pill,
  SuccessNotice,
  Table,
  useFeedback,
} from "@/components/ui";
import { BrandIcon, isBrand } from "@/lib/brand-icons";

export default function DeepLinksPage() {
  const { prefix, manager } = useWorkspace();
  const [links, setLinks] = useState<DeepLink[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [qrModal, setQrModal] = useState<DeepLink | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const confirm = useConfirmation();
  const feedback = useFeedback();
  const origin = typeof window === "undefined" ? "" : window.location.origin;
  const shortUrl = (link: DeepLink) => `${origin}/go/${link.code}/`;

  useEffect(() => {
    const controller = new AbortController();
    queueMicrotask(() =>
      api<DeepLink[]>(
        `${prefix}/deeplinks/`,
        "GET",
        undefined,
        controller.signal,
      )
        .then(setLinks)
        .catch((err) => {
          if (!controller.signal.aborted) feedback.setError(message(err));
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        }),
    );
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefix]);

  // Form state
  const [title, setTitle] = useState("");
  const [platform, setPlatform] = useState<DeepLink["platform"]>("instagram");
  const [target, setTarget] = useState("");
  const [customCode, setCustomCode] = useState("");
  const [campaign, setCampaign] = useState("");
  const [source, setSource] = useState("");
  const [medium, setMedium] = useState("");
  const [stats, setStats] = useState<{
    clicks: number;
    form_submissions: number;
    daily: { day: string; clicks: number }[];
  } | null>(null);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    const code = (
      customCode.trim() || title.toLowerCase().replace(/[^a-z0-9]+/g, "-")
    )
      .replace(/^-+|-+$/g, "")
      .slice(0, 40);
    const done = await feedback.run(async () => {
      const created = await api<DeepLink>(`${prefix}/deeplinks/`, "POST", {
        title: title.trim(),
        platform,
        target: target.trim(),
        code,
        campaign,
        source,
        medium,
      });
      setLinks((list) => [created, ...list]);
      return true;
    }, `Smart link "${title.trim()}" created.`);
    if (done) {
      setCreating(false);
      setTitle("");
      setTarget("");
      setCustomCode("");
      setCampaign("");
      setSource("");
      setMedium("");
    }
  }

  function copyLink(link: DeepLink) {
    navigator.clipboard.writeText(shortUrl(link));
    setCopiedId(link.id);
    setTimeout(() => setCopiedId(null), 2000);
  }

  async function toggleActive(link: DeepLink) {
    await feedback.run(async () => {
      const updated = await api<DeepLink>(
        `${prefix}/deeplinks/${link.id}/`,
        "PATCH",
        {
          active: !link.active,
        },
      );
      setLinks((list) =>
        list.map((item) => (item.id === link.id ? updated : item)),
      );
    });
  }

  async function remove(link: DeepLink) {
    if (
      !(await confirm(`Delete "${link.title}"? Its short link stops working.`))
    )
      return;
    await feedback.run(async () => {
      await api(`${prefix}/deeplinks/${link.id}/`, "DELETE");
      setLinks((list) => list.filter((item) => item.id !== link.id));
    }, "Link deleted.");
  }

  return (
    <>
      <PageHeading
        eyebrow="Apps / Tracking links"
        title="Know which links bring people in"
        text="Share short links with campaign tags and daily click counts. App destinations open according to the visitor’s device and browser settings."
        action={
          <button
            className="button primary small"
            disabled={!manager}
            onClick={() => {
              feedback.setError("");
              setCreating(true);
            }}
          >
            <Plus size={15} /> Create deep link
          </button>
        }
      />
      {!creating && <ErrorNotice error={feedback.error} />}
      <SuccessNotice notice={feedback.notice} />

      <div className="stats-grid" style={{ marginBottom: "20px" }}>
        <article className="stat-card">
          <div className="stat-top">
            <span className="stat-icon">
              <Smartphone size={18} />
            </span>
            <span>Total smart links</span>
          </div>
          <strong>{links.length}</strong>
          <p>Active and paused links</p>
        </article>
        <article className="stat-card">
          <div className="stat-top">
            <span className="stat-icon">
              <Sparkles size={18} />
            </span>
            <span>Total link clicks</span>
          </div>
          <strong>{links.reduce((acc, l) => acc + l.clicks, 0)}</strong>
          <p>Redirects across your shared links</p>
        </article>
      </div>

      <Panel
        title="Active Smart Links"
        aside={`${links.length} ${links.length === 1 ? "link" : "links"} configured`}
      >
        {loading ? (
          <p className="loading-text">Loading links…</p>
        ) : links.length > 0 ? (
          <Table
            head={[
              "Link Details",
              "Platform Target",
              "Clicks",
              "Status",
              "Actions",
            ]}
          >
            {links.map((link) => {
              const fullUrl = shortUrl(link);
              return (
                <tr key={link.id}>
                  <td>
                    <strong>{link.title}</strong>
                    <div
                      style={{ fontSize: "12px", color: "var(--brand-muted)" }}
                    >
                      <code>{fullUrl}</code>
                    </div>
                  </td>
                  <td>
                    <Pill tone="neutral">
                      <span
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: "6px",
                        }}
                      >
                        {isBrand(link.platform) && (
                          <BrandIcon name={link.platform} size={13} />
                        )}
                        {link.platform.toUpperCase()}
                      </span>
                    </Pill>
                  </td>
                  <td className="num">
                    <button
                      className="text-button"
                      onClick={() =>
                        void feedback.run(async () =>
                          setStats(
                            await api(`${prefix}/deeplinks/${link.id}/stats/`),
                          ),
                        )
                      }
                    >
                      {link.clicks} · View activity
                    </button>
                    {link.campaign && <small>{link.campaign}</small>}
                  </td>
                  <td>
                    <button
                      className={`pill ${link.active ? "pill-good" : "pill-warn"}`}
                      style={{ border: "none", cursor: "pointer" }}
                      disabled={!manager || feedback.busy}
                      onClick={() => toggleActive(link)}
                    >
                      {link.active ? "Active" : "Paused"}
                    </button>
                  </td>
                  <td>
                    <div
                      style={{
                        display: "flex",
                        gap: "6px",
                        alignItems: "center",
                      }}
                    >
                      <button
                        className="button secondary small"
                        onClick={() => copyLink(link)}
                        title="Copy Smart Link"
                      >
                        {copiedId === link.id ? (
                          <Check size={14} color="#10b981" />
                        ) : (
                          <Copy size={14} />
                        )}
                        {copiedId === link.id ? "Copied" : "Copy"}
                      </button>
                      <button
                        className="icon-button"
                        onClick={() => setQrModal(link)}
                        title="Show QR Code"
                      >
                        <QrCode size={16} />
                      </button>
                      <a
                        href={link.target}
                        target="_blank"
                        rel="noreferrer"
                        className="icon-button"
                        title="Open Destination"
                      >
                        <ExternalLink size={16} />
                      </a>
                      <button
                        className="icon-button"
                        disabled={!manager || feedback.busy}
                        onClick={() => remove(link)}
                        title="Delete link"
                      >
                        <Trash2 size={16} />
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </Table>
        ) : (
          <Empty>
            No smart links created yet. Click above to generate your first link.
          </Empty>
        )}
      </Panel>

      {creating && (
        <Modal
          title="Create Smart Deep Link"
          onClose={() => setCreating(false)}
        >
          <ValidatedForm
            fieldErrors={feedback.fieldErrors}
            validationTarget={feedback.validationTarget}
            onEdit={() => feedback.setError("")}
            validate={(): Record<string, string> =>
              target.trim().startsWith("https://")
                ? {}
                : { target: "Enter a destination starting with https://." }
            }
            onSubmit={handleCreate}
            style={{ display: "flex", flexDirection: "column", gap: "14px" }}
          >
            <ErrorNotice error={feedback.error} />
            <label>
              Link Title
              <ValidatedInput
                required
                name="title"
                placeholder="e.g. Instagram VIP Profile Link"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
            </label>
            <label>
              App Target
              <ValidatedSelect
                value={platform}
                onChange={(e) =>
                  setPlatform(e.target.value as DeepLink["platform"])
                }
              >
                <option value="instagram">Instagram (App Direct)</option>
                <option value="whatsapp">WhatsApp (Direct Chat)</option>
                <option value="youtube">YouTube (Native App)</option>
                <option value="telegram">Telegram (Direct App)</option>
                <option value="custom">Custom Web Fallback</option>
              </ValidatedSelect>
            </label>
            <label>
              Destination HTTPS URL
              <ValidatedInput
                required
                name="target"
                type="url"
                placeholder={
                  platform === "instagram"
                    ? "https://instagram.com/yourbrand"
                    : platform === "whatsapp"
                      ? "https://wa.me/15550100200"
                      : "https://youtube.com/@channel"
                }
                value={target}
                onChange={(e) => setTarget(e.target.value)}
              />
            </label>
            <label>
              Campaign (utm_campaign)
              <ValidatedInput
                name="campaign"
                maxLength={100}
                value={campaign}
                onChange={(e) => setCampaign(e.target.value)}
                placeholder="october-launch"
              />
            </label>
            <label>
              Source (utm_source)
              <ValidatedInput
                maxLength={100}
                value={source}
                onChange={(e) => setSource(e.target.value)}
                placeholder="instagram"
              />
            </label>
            <label>
              Medium (utm_medium)
              <ValidatedInput
                maxLength={100}
                value={medium}
                onChange={(e) => setMedium(e.target.value)}
                placeholder="dm"
              />
            </label>
            <label>
              Custom link ending (optional)
              <ValidatedInput
                placeholder="e.g. vip-chat"
                name="code"
                value={customCode}
                onChange={(e) => setCustomCode(e.target.value)}
              />
            </label>
            <div
              style={{
                display: "flex",
                justifyContent: "flex-end",
                gap: "10px",
                marginTop: "10px",
              }}
            >
              <button
                type="button"
                className="button secondary"
                onClick={() => setCreating(false)}
              >
                Cancel
              </button>
              <button type="submit" className="button primary">
                Generate Smart Link
              </button>
            </div>
          </ValidatedForm>
        </Modal>
      )}

      {qrModal && (
        <Modal
          title={`QR Code: ${qrModal.title}`}
          onClose={() => setQrModal(null)}
        >
          <div style={{ textAlign: "center", padding: "16px 0" }}>
            {/* QR code is a generated external image, without an optimization source. */}
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={`https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=${encodeURIComponent(shortUrl(qrModal))}`}
              alt="Deep Link QR Code"
              style={{
                width: "200px",
                height: "200px",
                borderRadius: "12px",
                border: "1px solid var(--brand-line)",
              }}
            />
            <p style={{ marginTop: "12px", fontSize: "13px" }}>
              Scan this code to open the destination link on your device.
            </p>
          </div>
        </Modal>
      )}
      {stats && (
        <Modal title="Link activity" onClose={() => setStats(null)}>
          <p>
            {stats.clicks} {stats.clicks === 1 ? "click" : "clicks"} ·{" "}
            {stats.form_submissions} attributed form{" "}
            {stats.form_submissions === 1 ? "submission" : "submissions"}
          </p>
          <p className="muted-text">
            To attribute a form submission, include ?ref=your-link-code in the
            public form URL. Counts are aggregate; no visitor IP addresses are
            stored.
          </p>
          <Table head={["Day", "Clicks"]}>
            {stats.daily.map((row) => (
              <tr key={row.day}>
                <td>{row.day}</td>
                <td>{row.clicks}</td>
              </tr>
            ))}
          </Table>
          {!stats.daily.length && <p>No daily activity yet.</p>}
        </Modal>
      )}
    </>
  );
}
