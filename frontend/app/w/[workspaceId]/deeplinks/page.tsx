"use client";

import { useState } from "react";
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

type DeepLink = {
  id: string;
  title: string;
  platform: "instagram" | "whatsapp" | "youtube" | "telegram" | "custom";
  target: string;
  shortCode: string;
  clicks: number;
  active: boolean;
  createdAt: string;
};

const DEFAULT_LINKS: DeepLink[] = [
  {
    id: "dl-1",
    title: "Instagram Profile Direct",
    platform: "instagram",
    target: "https://instagram.com/censtd_nutech",
    shortCode: "ig-profile",
    clicks: 342,
    active: true,
    createdAt: "2026-10-18T10:00:00Z",
  },
  {
    id: "dl-2",
    title: "WhatsApp Order Concierge",
    platform: "whatsapp",
    target: "https://wa.me/15550100200?text=Hi%20Nemio",
    shortCode: "wa-order",
    clicks: 189,
    active: true,
    createdAt: "2026-10-19T14:30:00Z",
  },
];

export default function DeepLinksPage() {
  const { workspace } = useWorkspace();
  const [links, setLinks] = useState<DeepLink[]>(() => {
    try {
      const stored = localStorage.getItem(`nemio:deeplinks:${workspace.id}`);
      return stored ? JSON.parse(stored) : DEFAULT_LINKS;
    } catch {
      return DEFAULT_LINKS;
    }
  });
  const [creating, setCreating] = useState(false);
  const [qrModal, setQrModal] = useState<DeepLink | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const feedback = useFeedback();

  // Form state
  const [title, setTitle] = useState("");
  const [platform, setPlatform] = useState<DeepLink["platform"]>("instagram");
  const [target, setTarget] = useState("");
  const [customCode, setCustomCode] = useState("");

  function save(next: DeepLink[]) {
    setLinks(next);
    try {
      localStorage.setItem(`nemio:deeplinks:${workspace.id}`, JSON.stringify(next));
    } catch {
      // storage quota or disabled
    }
  }

  function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim() || !target.trim()) {
      feedback.setError("Please provide a title and target URL.");
      return;
    }
    const slug = (customCode.trim() || title.toLowerCase().replace(/[^a-z0-9]+/g, "-")).slice(0, 30);
    const newLink: DeepLink = {
      id: `dl-${Date.now()}`,
      title: title.trim(),
      platform,
      target: target.trim(),
      shortCode: slug,
      clicks: 0,
      active: true,
      createdAt: new Date().toISOString(),
    };
    save([newLink, ...links]);
    setCreating(false);
    setTitle("");
    setTarget("");
    setCustomCode("");
    feedback.setNotice(`Smart link "${newLink.title}" created!`);
  }

  function copyLink(link: DeepLink) {
    const fullUrl = `https://${window.location.host}/p/deep/${link.shortCode}`;
    navigator.clipboard.writeText(fullUrl);
    setCopiedId(link.id);
    setTimeout(() => setCopiedId(null), 2000);
  }

  function toggleActive(id: string) {
    save(
      links.map((link) =>
        link.id === id ? { ...link, active: !link.active } : link,
      ),
    );
  }

  function remove(id: string) {
    save(links.filter((link) => link.id !== id));
  }

  return (
    <>
      <PageHeading
        eyebrow="Smart Deep Links"
        title="Bypass In-App Browsers"
        text="Generate deep links that open natively inside Instagram, WhatsApp, or YouTube instead of getting trapped in slow webview browsers."
        action={
          <button className="button primary small" onClick={() => setCreating(true)}>
            <Plus size={15} /> Create deep link
          </button>
        }
      />
      <ErrorNotice error={feedback.error} />
      <SuccessNotice notice={feedback.notice} />

      <div className="stats-grid" style={{ marginBottom: "20px" }}>
        <article className="stat-card">
          <div className="stat-top">
            <span className="stat-icon"><Smartphone size={18} /></span>
            <span>Total smart links</span>
          </div>
          <strong>{links.length}</strong>
          <p>Routing to native mobile apps</p>
        </article>
        <article className="stat-card">
          <div className="stat-top">
            <span className="stat-icon"><Sparkles size={18} /></span>
            <span>Total direct hand-offs</span>
          </div>
          <strong>{links.reduce((acc, l) => acc + l.clicks, 0)}</strong>
          <p>Users diverted from in-app webview</p>
        </article>
      </div>

      <Panel title="Active Smart Links" aside={`${links.length} links configured`}>
        {links.length > 0 ? (
          <Table head={["Link Details", "Platform Target", "Clicks", "Status", "Actions"]}>
            {links.map((link) => {
              const fullUrl = typeof window !== "undefined" ? `https://${window.location.host}/p/deep/${link.shortCode}` : `.../p/deep/${link.shortCode}`;
              return (
                <tr key={link.id}>
                  <td>
                    <strong>{link.title}</strong>
                    <div style={{ fontSize: "12px", color: "var(--brand-muted)" }}>
                      <code>{fullUrl}</code>
                    </div>
                  </td>
                  <td>
                    <Pill tone="neutral">{link.platform.toUpperCase()}</Pill>
                  </td>
                  <td className="num">{link.clicks}</td>
                  <td>
                    <button
                      className={`pill ${link.active ? "pill-good" : "pill-warn"}`}
                      style={{ border: "none", cursor: "pointer" }}
                      onClick={() => toggleActive(link.id)}
                    >
                      {link.active ? "Active" : "Paused"}
                    </button>
                  </td>
                  <td>
                    <div style={{ display: "flex", gap: "6px", alignItems: "center" }}>
                      <button
                        className="button secondary small"
                        onClick={() => copyLink(link)}
                        title="Copy Smart Link"
                      >
                        {copiedId === link.id ? <Check size={14} color="#10b981" /> : <Copy size={14} />}
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
                        onClick={() => remove(link.id)}
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
          <Empty>No smart links created yet. Click above to generate your first link.</Empty>
        )}
      </Panel>

      {creating && (
        <Modal title="Create Smart Deep Link" onClose={() => setCreating(false)}>
          <form onSubmit={handleCreate} style={{ display: "flex", flexDirection: "column", gap: "14px" }}>
            <label>
              Link Title
              <input
                required
                placeholder="e.g. Instagram VIP Profile Link"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
            </label>
            <label>
              App Target
              <select
                value={platform}
                onChange={(e) => setPlatform(e.target.value as DeepLink["platform"])}
              >
                <option value="instagram">Instagram (App Direct)</option>
                <option value="whatsapp">WhatsApp (Direct Chat)</option>
                <option value="youtube">YouTube (Native App)</option>
                <option value="telegram">Telegram (Direct App)</option>
                <option value="custom">Custom Web Fallback</option>
              </select>
            </label>
            <label>
              Destination URL or Mobile Deep Link
              <input
                required
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
              Custom Slug (optional)
              <input
                placeholder="e.g. vip-chat"
                value={customCode}
                onChange={(e) => setCustomCode(e.target.value)}
              />
            </label>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: "10px", marginTop: "10px" }}>
              <button type="button" className="button secondary" onClick={() => setCreating(false)}>
                Cancel
              </button>
              <button type="submit" className="button primary">
                Generate Smart Link
              </button>
            </div>
          </form>
        </Modal>
      )}

      {qrModal && (
        <Modal title={`QR Code: ${qrModal.title}`} onClose={() => setQrModal(null)}>
          <div style={{ textAlign: "center", padding: "16px 0" }}>
            <img
              src={`https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=https://${typeof window !== "undefined" ? window.location.host : ""}/p/deep/${qrModal.shortCode}`}
              alt="Deep Link QR Code"
              style={{ width: "200px", height: "200px", borderRadius: "12px", border: "1px solid var(--brand-line)" }}
            />
            <p style={{ marginTop: "12px", fontSize: "13px" }}>
              Scan this code to launch the native app directly on iOS or Android.
            </p>
          </div>
        </Modal>
      )}
    </>
  );
}
