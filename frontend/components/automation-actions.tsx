"use client";

import Link from "next/link";
import { useEffect, useRef } from "react";
import { Copy, MoreVertical, Pencil, Trash2 } from "lucide-react";
import type { Automation } from "@/lib/api";
import "./automation-actions.css";

export function AutomationActions({
  item,
  href,
  busy,
  onDuplicate,
  onDelete,
}: {
  item: Automation;
  href: string;
  busy: boolean;
  onDuplicate: () => void;
  onDelete: () => void;
}) {
  const root = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    const closeOutside = (event: MouseEvent) => {
      if (root.current && !root.current.contains(event.target as Node))
        root.current.open = false;
    };
    document.addEventListener("mousedown", closeOutside);
    return () => document.removeEventListener("mousedown", closeOutside);
  }, []);
  const close = () => {
    if (root.current) root.current.open = false;
  };
  return (
    <details
      ref={root}
      className="nm-automation-actions"
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          close();
          root.current?.querySelector("summary")?.focus();
        }
      }}
    >
      <summary
        className="icon-button-dots"
        aria-label={`Actions for ${item.name}`}
      >
        <MoreVertical size={18} />
      </summary>
      <div
        className="nm-automation-actions-popover"
        role="group"
        aria-label={`Manage ${item.name}`}
      >
        <Link href={href} onClick={close}>
          <Pencil size={15} /> Edit automation
        </Link>
        <button
          type="button"
          disabled={busy}
          onClick={() => {
            close();
            onDuplicate();
          }}
        >
          <Copy size={15} /> Duplicate
        </button>
        <button
          type="button"
          className="nm-automation-delete"
          disabled={busy}
          onClick={() => {
            close();
            onDelete();
          }}
        >
          <Trash2 size={15} /> Delete automation
        </button>
      </div>
    </details>
  );
}
