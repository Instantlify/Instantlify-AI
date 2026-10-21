"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { Check, ChevronDown, Layers, Plus, RefreshCw } from "lucide-react";
import { api, message, type Connection, type Page } from "@/lib/api";
import {
  ChannelBadge,
  channelLabel,
  compactNumber,
  switchable,
  TOKEN_LABELS,
  tokenHealth,
} from "@/lib/channels";
import { useWorkspace } from "@/lib/workspace";
import { initials } from "./shell";

/** Sidebar profile badge that picks the active Instagram account, Facebook Page or
 * WhatsApp number. The choice scopes the inbox; it never changes server data. */
export function MetaAccountSwitcher() {
  const { workspace, prefix, manager, activeAccount, setActiveAccount } =
    useWorkspace();
  const [connections, setConnections] = useState<Connection[] | null>(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [now, setNow] = useState(() => Date.now());
  const root = useRef<HTMLDivElement>(null);

  const load = useCallback(
    async (signal?: AbortSignal) => {
      const page = await api<Page<Connection>>(
        `${prefix}/connections/`,
        "GET",
        undefined,
        signal,
      );
      setConnections(switchable(page.results));
      setNow(Date.now());
    },
    [prefix],
  );
  useEffect(() => {
    const controller = new AbortController();
    queueMicrotask(() =>
      load(controller.signal).catch(() => {
        if (!controller.signal.aborted) setConnections([]);
      }),
    );
    return () => controller.abort();
  }, [load]);
  // A remembered account that has since been disconnected falls back to "all".
  useEffect(() => {
    if (
      connections &&
      activeAccount &&
      !connections.some((item) => item.id === activeAccount)
    )
      setActiveAccount(null);
  }, [connections, activeAccount, setActiveAccount]);
  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent | KeyboardEvent) => {
      if (
        event instanceof KeyboardEvent
          ? event.key === "Escape"
          : !root.current?.contains(event.target as Node)
      )
        setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);

  async function connect() {
    setBusy(true);
    setNotice("");
    try {
      const result = await api<{ authorization_url: string }>(
        `${prefix}/meta/connect/`,
        "POST",
      );
      window.location.assign(result.authorization_url);
    } catch (err) {
      setNotice(message(err));
      setBusy(false);
    }
  }
  async function refreshTokens() {
    setBusy(true);
    setNotice("");
    try {
      const result = await api<{ queued: number }>(
        `${prefix}/connections/refresh/`,
        "POST",
      );
      setNotice(
        result.queued
          ? `Refreshing ${result.queued} Instagram token${result.queued === 1 ? "" : "s"}.`
          : "No Instagram tokens need refreshing. Pages and WhatsApp numbers use long-lived tokens.",
      );
      await load();
    } catch (err) {
      setNotice(message(err));
    } finally {
      setBusy(false);
    }
  }

  const list = connections ?? [];
  const active = list.find((item) => item.id === activeAccount) ?? null;
  const attention = list.filter(
    (item) => tokenHealth(item, now) !== "active",
  ).length;
  return (
    <div className="account-switcher" ref={root}>
      <button
        type="button"
        className="account-trigger"
        aria-expanded={open}
        aria-controls="account-menu"
        onClick={() => {
          setOpen((value) => !value);
          if (!open) load().catch(() => undefined);
        }}
      >
        <span
          className={`account-avatar ${active ? `ring-${active.provider}` : ""}`}
        >
          {active ? initials(active.display_name) : <Layers size={15} />}
          {attention > 0 && <i className="account-alert" aria-hidden="true" />}
        </span>
        <span className="account-copy">
          <span className="tiny-label">CHANNEL ACCOUNT</span>
          <strong>{active ? active.display_name : "All accounts"}</strong>
          <span>
            {active
              ? active.followers !== null
                ? `${compactNumber(active.followers)} followers`
                : channelLabel(active.provider)
              : connections === null
                ? "Loading…"
                : `${list.length} connected`}
          </span>
        </span>
        <ChevronDown size={15} className={open ? "flip" : ""} />
      </button>
      {open && (
        <div className="account-menu" id="account-menu">
          <button
            type="button"
            className={`account-option ${!active ? "selected" : ""}`}
            onClick={() => {
              setActiveAccount(null);
              setOpen(false);
            }}
          >
            <span className="account-avatar">
              <Layers size={14} />
            </span>
            <span className="account-copy">
              <strong>All accounts</strong>
              <span>Every channel in {workspace.name}</span>
            </span>
            {!active && <Check size={15} />}
          </button>
          {list.map((item) => {
            const health = tokenHealth(item, now);
            return (
              <button
                type="button"
                key={item.id}
                className={`account-option ${item.id === activeAccount ? "selected" : ""}`}
                onClick={() => {
                  setActiveAccount(item.id);
                  setOpen(false);
                }}
              >
                <span className={`account-avatar ring-${item.provider}`}>
                  {initials(item.display_name)}
                </span>
                <span className="account-copy">
                  <strong title={item.display_name}>{item.display_name}</strong>
                  <span>
                    <ChannelBadge provider={item.provider} compact />
                    {item.followers !== null &&
                      ` ${compactNumber(item.followers)} followers`}
                    {item.is_test && " · test"}
                  </span>
                  <span className={`token-state token-${health}`}>
                    <i aria-hidden="true" /> {TOKEN_LABELS[health]}
                  </span>
                </span>
                {item.id === activeAccount && <Check size={15} />}
              </button>
            );
          })}
          {connections !== null && !list.length && (
            <p className="account-empty">No channels connected yet.</p>
          )}
          {manager && (
            <div className="account-actions">
              <button
                type="button"
                className="account-action"
                onClick={connect}
                disabled={busy}
              >
                <Plus size={14} /> Connect Instagram account
              </button>
              <Link
                className="account-action"
                href={`/w/${workspace.id}/integrations`}
                onClick={() => setOpen(false)}
              >
                <Plus size={14} /> Add a Facebook Page or WhatsApp number
              </Link>
              <button
                type="button"
                className="account-action"
                onClick={refreshTokens}
                disabled={busy}
              >
                <RefreshCw size={14} className={busy ? "spin" : ""} /> Refresh
                tokens
              </button>
            </div>
          )}
          {notice && (
            <p className="account-notice" role="status">
              {notice}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
