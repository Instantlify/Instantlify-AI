"use client";

import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import type { BioBlock } from "@/lib/api";

const BLOCK_TYPES: {
  type: BioBlock["type"];
  label: string;
  make: () => BioBlock;
}[] = [
  {
    type: "link",
    label: "Link button",
    make: () => ({ type: "link", title: "", url: "https://" }),
  },
  {
    type: "heading",
    label: "Heading",
    make: () => ({ type: "heading", text: "" }),
  },
  { type: "text", label: "Text", make: () => ({ type: "text", text: "" }) },
  {
    type: "image",
    label: "Image",
    make: () => ({ type: "image", url: "https://", alt: "" }),
  },
  {
    type: "video",
    label: "Video (YouTube, Vimeo, Loom)",
    make: () => ({ type: "video", url: "https://" }),
  },
  {
    type: "social",
    label: "Social icons",
    make: () => ({
      type: "social",
      items: [{ platform: "instagram", url: "https://instagram.com/" }],
    }),
  },
  {
    type: "email_capture",
    label: "Email signup",
    make: () => ({
      type: "email_capture",
      title: "Join my list",
      button: "Subscribe",
      tag: "bio-signup",
    }),
  },
  { type: "divider", label: "Divider", make: () => ({ type: "divider" }) },
];
const PLATFORMS = [
  "instagram",
  "tiktok",
  "youtube",
  "x",
  "facebook",
  "linkedin",
  "whatsapp",
  "telegram",
  "email",
  "website",
];

/** Add, edit, reorder and remove link-in-bio blocks. */
export function BioBlockEditor({
  blocks,
  onChange,
}: {
  blocks: BioBlock[];
  onChange: (blocks: BioBlock[]) => void;
}) {
  const [adding, setAdding] = useState<BioBlock["type"]>("link");
  const update = (index: number, patch: Partial<BioBlock>) =>
    onChange(
      blocks.map((block, i) => (i === index ? { ...block, ...patch } : block)),
    );
  const move = (index: number, by: number) => {
    const next = [...blocks];
    const [item] = next.splice(index, 1);
    next.splice(index + by, 0, item);
    onChange(next);
  };

  return (
    <div className="field">
      <span>Blocks ({blocks.length}/40)</span>
      <div className="card-list">
        {blocks.map((block, index) => (
          <div className="card stack" key={index} style={{ gap: 6 }}>
            <div className="row" style={{ gap: 6 }}>
              <strong className="small" style={{ flex: 1 }}>
                {BLOCK_TYPES.find((item) => item.type === block.type)?.label}
              </strong>
              <button
                type="button"
                className="icon-button"
                aria-label="Move block up"
                disabled={index === 0}
                onClick={() => move(index, -1)}
              >
                <ArrowUp size={14} />
              </button>
              <button
                type="button"
                className="icon-button"
                aria-label="Move block down"
                disabled={index === blocks.length - 1}
                onClick={() => move(index, 1)}
              >
                <ArrowDown size={14} />
              </button>
              <button
                type="button"
                className="icon-button"
                aria-label="Remove block"
                onClick={() => onChange(blocks.filter((_, i) => i !== index))}
              >
                <Trash2 size={14} />
              </button>
            </div>
            {block.type === "link" && (
              <>
                <input
                  aria-label="Button text"
                  maxLength={60}
                  placeholder="Book a call"
                  value={block.title || ""}
                  onChange={(e) => update(index, { title: e.target.value })}
                />
                <input
                  aria-label="Button link"
                  type="url"
                  maxLength={2000}
                  value={block.url || ""}
                  onChange={(e) => update(index, { url: e.target.value })}
                />
                <label className="inline">
                  <input
                    type="checkbox"
                    checked={Boolean(block.highlight)}
                    onChange={(e) =>
                      update(index, {
                        highlight: e.target.checked || undefined,
                      })
                    }
                  />
                  Highlight this button
                </label>
              </>
            )}
            {(block.type === "heading" || block.type === "text") &&
              (block.type === "heading" ? (
                <input
                  aria-label="Heading text"
                  maxLength={80}
                  value={block.text || ""}
                  onChange={(e) => update(index, { text: e.target.value })}
                />
              ) : (
                <textarea
                  aria-label="Text"
                  rows={3}
                  maxLength={1000}
                  value={block.text || ""}
                  onChange={(e) => update(index, { text: e.target.value })}
                />
              ))}
            {block.type === "image" && (
              <>
                <input
                  aria-label="Image address"
                  type="url"
                  placeholder="https://…/photo.jpg"
                  value={block.url || ""}
                  onChange={(e) => update(index, { url: e.target.value })}
                />
                <input
                  aria-label="Image description"
                  maxLength={150}
                  placeholder="Describe the image"
                  value={block.alt || ""}
                  onChange={(e) => update(index, { alt: e.target.value })}
                />
                <input
                  aria-label="Image link (optional)"
                  type="url"
                  placeholder="Link when tapped (optional)"
                  value={block.link || ""}
                  onChange={(e) =>
                    update(index, { link: e.target.value || undefined })
                  }
                />
              </>
            )}
            {block.type === "video" && (
              <input
                aria-label="Video link"
                type="url"
                placeholder="https://www.youtube.com/watch?v=…"
                value={block.url || ""}
                onChange={(e) =>
                  update(index, { url: e.target.value, embed: undefined })
                }
              />
            )}
            {block.type === "social" && (
              <>
                {(block.items || []).map((item, itemIndex) => (
                  <div
                    className="row"
                    key={itemIndex}
                    style={{ gap: 6, flexWrap: "nowrap" }}
                  >
                    <select
                      aria-label="Social network"
                      value={item.platform}
                      onChange={(e) =>
                        update(index, {
                          items: (block.items || []).map((entry, i) =>
                            i === itemIndex
                              ? { ...entry, platform: e.target.value }
                              : entry,
                          ),
                        })
                      }
                    >
                      {PLATFORMS.map((platform) => (
                        <option key={platform} value={platform}>
                          {platform}
                        </option>
                      ))}
                    </select>
                    <input
                      aria-label="Profile link"
                      placeholder={
                        item.platform === "email"
                          ? "mailto:you@example.com"
                          : "https://…"
                      }
                      value={item.url}
                      onChange={(e) =>
                        update(index, {
                          items: (block.items || []).map((entry, i) =>
                            i === itemIndex
                              ? { ...entry, url: e.target.value }
                              : entry,
                          ),
                        })
                      }
                      style={{ flex: 1 }}
                    />
                    <button
                      type="button"
                      className="icon-button"
                      aria-label="Remove profile"
                      onClick={() =>
                        update(index, {
                          items: (block.items || []).filter(
                            (_, i) => i !== itemIndex,
                          ),
                        })
                      }
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                ))}
                {(block.items || []).length < 10 && (
                  <button
                    type="button"
                    className="text-button"
                    onClick={() =>
                      update(index, {
                        items: [
                          ...(block.items || []),
                          { platform: "website", url: "https://" },
                        ],
                      })
                    }
                  >
                    <Plus size={13} /> Add profile
                  </button>
                )}
              </>
            )}
            {block.type === "email_capture" && (
              <>
                <input
                  aria-label="Signup title"
                  maxLength={80}
                  value={block.title || ""}
                  onChange={(e) => update(index, { title: e.target.value })}
                />
                <input
                  aria-label="Signup button text"
                  maxLength={30}
                  value={block.button || ""}
                  onChange={(e) => update(index, { button: e.target.value })}
                />
                <input
                  aria-label="Tag for new contacts"
                  maxLength={40}
                  value={block.tag || ""}
                  onChange={(e) => update(index, { tag: e.target.value })}
                />
                <small className="muted-text">
                  Signups become CRM contacts with this tag. No message is sent.
                </small>
              </>
            )}
          </div>
        ))}
      </div>
      {blocks.length < 40 && (
        <div className="row" style={{ gap: 6 }}>
          <select
            aria-label="Block type to add"
            value={adding}
            onChange={(e) => setAdding(e.target.value as BioBlock["type"])}
          >
            {BLOCK_TYPES.map((item) => (
              <option key={item.type} value={item.type}>
                {item.label}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="button secondary small"
            onClick={() =>
              onChange([
                ...blocks,
                BLOCK_TYPES.find((item) => item.type === adding)!.make(),
              ])
            }
          >
            Add block <Plus size={14} />
          </button>
        </div>
      )}
    </div>
  );
}
