"use client";

import { useState, type CSSProperties, type FormEvent } from "react";
import type { BioBlock } from "@/lib/api";
import { useT } from "@/lib/i18n";

export const BIO_THEMES: { id: string; label: string }[] = [
  { id: "light", label: "Light" },
  { id: "dark", label: "Dark" },
  { id: "gradient", label: "Gradient" },
  { id: "minimal", label: "Minimal" },
  { id: "bold", label: "Bold" },
];

const SOCIAL_LABELS: Record<string, string> = {
  instagram: "Instagram",
  tiktok: "TikTok",
  youtube: "YouTube",
  x: "X",
  facebook: "Facebook",
  linkedin: "LinkedIn",
  whatsapp: "WhatsApp",
  telegram: "Telegram",
  email: "Email",
  website: "Website",
};

type Palette = {
  page: CSSProperties;
  text: string;
  muted: string;
  card: string;
  button: (accent: string, highlight?: boolean) => CSSProperties;
};

function palette(theme: string, accent: string): Palette {
  const solid = (highlight?: boolean): CSSProperties => ({
    background: accent,
    color: "#fff",
    border: "none",
    boxShadow: highlight ? `0 0 0 3px ${accent}55` : undefined,
  });
  switch (theme) {
    case "dark":
      return {
        page: { background: "#0f1115" },
        text: "#f5f5f5",
        muted: "#a3a3a3",
        card: "#1b1e24",
        button: (_a, highlight) => ({
          background: highlight ? accent : "#1b1e24",
          color: "#f5f5f5",
          border: `1px solid ${highlight ? accent : "#2c313a"}`,
        }),
      };
    case "gradient":
      return {
        page: {
          background: `linear-gradient(160deg, ${accent} 0%, #111827 100%)`,
        },
        text: "#ffffff",
        muted: "rgba(255,255,255,0.75)",
        card: "rgba(255,255,255,0.12)",
        button: (_a, highlight) => ({
          background: highlight ? "#ffffff" : "rgba(255,255,255,0.14)",
          color: highlight ? "#111827" : "#ffffff",
          border: "1px solid rgba(255,255,255,0.35)",
        }),
      };
    case "minimal":
      return {
        page: { background: "#ffffff" },
        text: "#111827",
        muted: "#6b7280",
        card: "#f9fafb",
        button: (_a, highlight) => ({
          background: "transparent",
          color: "#111827",
          border: `1.5px solid ${highlight ? accent : "#111827"}`,
        }),
      };
    case "bold":
      return {
        page: { background: accent },
        text: "#ffffff",
        muted: "rgba(255,255,255,0.8)",
        card: "rgba(0,0,0,0.15)",
        button: (_a, highlight) => ({
          background: highlight ? "#111827" : "#ffffff",
          color: highlight ? "#ffffff" : "#111827",
          border: "none",
          fontWeight: 700,
        }),
      };
    default:
      return {
        page: { background: "#f6f7f9" },
        text: "#111827",
        muted: "#6b7280",
        card: "#ffffff",
        button: (_a, highlight) => solid(highlight),
      };
  }
}

export type BioView = {
  title: string;
  bio: string;
  avatar_url: string;
  accent: string;
  theme?: string;
  blocks?: BioBlock[];
  links?: { title: string; url: string }[];
};

function Signup({
  block,
  pal,
  accent,
  onSubscribe,
}: {
  block: BioBlock;
  pal: Palette;
  accent: string;
  onSubscribe?: (email: string, name: string) => Promise<string>;
}) {
  const t = useT();
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [status, setStatus] = useState("");
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!onSubscribe) return;
    setStatus(await onSubscribe(email, name));
  }
  return (
    <form
      onSubmit={submit}
      style={{
        background: pal.card,
        borderRadius: 14,
        padding: 14,
        display: "grid",
        gap: 8,
      }}
    >
      <strong style={{ color: pal.text }}>{block.title}</strong>
      <input
        aria-label="Your name"
        placeholder={t("bio.name")}
        maxLength={150}
        value={name}
        onChange={(event) => setName(event.target.value)}
        style={{ padding: 10, borderRadius: 10, border: "1px solid #d1d5db" }}
      />
      <input
        aria-label="Your email"
        type="email"
        required
        placeholder={t("bio.email")}
        maxLength={254}
        value={email}
        onChange={(event) => setEmail(event.target.value)}
        style={{ padding: 10, borderRadius: 10, border: "1px solid #d1d5db" }}
      />
      <button
        type="submit"
        disabled={!onSubscribe}
        style={{
          ...pal.button(accent, true),
          padding: 11,
          borderRadius: 10,
          cursor: "pointer",
        }}
      >
        {block.button}
      </button>
      {status && (
        <span style={{ color: pal.muted, fontSize: 13 }}>{status}</span>
      )}
    </form>
  );
}

/** Renders a link-in-bio page; the editor passes no handlers, so nothing navigates. */
export function BioRenderer({
  page,
  onOpen,
  onSubscribe,
  footer,
}: {
  page: BioView;
  onOpen?: (block: number, item?: number) => void;
  onSubscribe?: (block: number, email: string, name: string) => Promise<string>;
  footer?: React.ReactNode;
}) {
  const pal = palette(page.theme || "light", page.accent);
  const blocks: BioBlock[] = page.blocks?.length
    ? page.blocks
    : (page.links || []).map((link) => ({ type: "link", ...link }));
  const legacy = !page.blocks?.length;
  const linkStyle = (highlight?: boolean): CSSProperties => ({
    ...pal.button(page.accent, highlight),
    display: "block",
    width: "100%",
    padding: "13px 16px",
    borderRadius: 14,
    fontSize: 15,
    fontWeight: 600,
    textAlign: "center",
    cursor: onOpen ? "pointer" : "default",
  });
  return (
    <div style={{ ...pal.page, minHeight: "100%", padding: "32px 16px" }}>
      <div
        style={{
          maxWidth: 460,
          margin: "0 auto",
          display: "grid",
          gap: 12,
          textAlign: "center",
        }}
      >
        {page.avatar_url && (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={page.avatar_url}
            alt=""
            style={{
              width: 88,
              height: 88,
              borderRadius: "50%",
              objectFit: "cover",
              margin: "0 auto",
            }}
          />
        )}
        <h1 style={{ fontSize: 24, margin: 0, color: pal.text }}>
          {page.title || "Your title"}
        </h1>
        {page.bio && <p style={{ margin: 0, color: pal.muted }}>{page.bio}</p>}
        {blocks.map((block, index) => {
          const key = `${block.type}-${index}`;
          const open = () => onOpen?.(legacy ? -1 - index : index);
          switch (block.type) {
            case "link":
              return (
                <button
                  key={key}
                  type="button"
                  style={linkStyle(block.highlight)}
                  onClick={open}
                >
                  {block.title || "Untitled link"}
                </button>
              );
            case "heading":
              return (
                <h2
                  key={key}
                  style={{ fontSize: 18, margin: "10px 0 0", color: pal.text }}
                >
                  {block.text}
                </h2>
              );
            case "text":
              return (
                <p
                  key={key}
                  style={{
                    margin: 0,
                    color: pal.muted,
                    whiteSpace: "pre-line",
                  }}
                >
                  {block.text}
                </p>
              );
            case "image": {
              const image = (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={block.url}
                  alt={block.alt || ""}
                  style={{ width: "100%", borderRadius: 14, display: "block" }}
                />
              );
              return block.link ? (
                <button
                  key={key}
                  type="button"
                  onClick={open}
                  style={{
                    padding: 0,
                    border: 0,
                    background: "none",
                    cursor: onOpen ? "pointer" : "default",
                  }}
                >
                  {image}
                </button>
              ) : (
                <div key={key}>{image}</div>
              );
            }
            case "video":
              return block.embed ? (
                <div
                  key={key}
                  style={{
                    position: "relative",
                    paddingTop: "56.25%",
                    borderRadius: 14,
                    overflow: "hidden",
                  }}
                >
                  <iframe
                    src={block.embed}
                    title="Video"
                    allow="encrypted-media; picture-in-picture; fullscreen"
                    sandbox="allow-scripts allow-same-origin allow-presentation"
                    style={{
                      position: "absolute",
                      inset: 0,
                      width: "100%",
                      height: "100%",
                      border: 0,
                    }}
                  />
                </div>
              ) : (
                <div key={key} style={{ color: pal.muted, fontSize: 13 }}>
                  Video preview appears after saving.
                </div>
              );
            case "social":
              return (
                <div
                  key={key}
                  style={{
                    display: "flex",
                    flexWrap: "wrap",
                    gap: 8,
                    justifyContent: "center",
                  }}
                >
                  {(block.items || []).map((item, itemIndex) => (
                    <button
                      key={`${item.platform}-${itemIndex}`}
                      type="button"
                      onClick={() => onOpen?.(index, itemIndex)}
                      style={{
                        ...pal.button(page.accent),
                        padding: "8px 12px",
                        borderRadius: 999,
                        fontSize: 13,
                        cursor: onOpen ? "pointer" : "default",
                      }}
                    >
                      {SOCIAL_LABELS[item.platform] || item.platform}
                    </button>
                  ))}
                </div>
              );
            case "email_capture":
              return (
                <Signup
                  key={key}
                  block={block}
                  pal={pal}
                  accent={page.accent}
                  onSubscribe={
                    onSubscribe
                      ? (email, name) => onSubscribe(index, email, name)
                      : undefined
                  }
                />
              );
            case "divider":
              return (
                <hr
                  key={key}
                  style={{
                    border: 0,
                    borderTop: `1px solid ${pal.muted}55`,
                    width: "100%",
                  }}
                />
              );
            default:
              return null;
          }
        })}
        {footer}
      </div>
    </div>
  );
}
