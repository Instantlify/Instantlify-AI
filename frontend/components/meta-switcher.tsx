"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Check,
  ChevronDown,
  Plus,
  RefreshCw,
  MessageCircle,
} from "lucide-react";
import { api, message, type Connection, type Page } from "@/lib/api";
import {
  channelLabel,
  compactNumber,
  TOKEN_LABELS,
  switchable,
  tokenHealth,
} from "@/lib/channels";
import { BrandIcon } from "@/lib/brand-icons";
import { useWorkspace } from "@/lib/workspace";
import { initials } from "./shell";

/**
 * Meta Account Switcher matching BooSend Screenshots 3, 4, and 12:
 * Rounded dark card showing active Instagram/Facebook handle and follower count,
 * with popup dropdown to switch accounts, refresh tokens, or manage connections.
 */
const ACCOUNT_KINDS: Record<string, string> = {
  instagram: "Instagram Business",
  messenger: "Facebook Page",
  whatsapp: "WhatsApp number",
  telegram: "Telegram bot",
  linkedin: "LinkedIn page",
};

/** Follower count when the channel reports one, otherwise what kind of account it is. */
const accountSubtitle = (connection: Connection) =>
  connection.followers !== null
    ? `${compactNumber(connection.followers)} followers`
    : (ACCOUNT_KINDS[connection.provider] ?? channelLabel(connection.provider));

export function MetaAccountSwitcher() {
  const { workspace, prefix, activeAccount, setActiveAccount } = useWorkspace();
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

  async function refreshTokens() {
    setBusy(true);
    setNotice("");
    try {
      await api<{ queued: number }>(`${prefix}/connections/refresh/`, "POST");
      await load();
      setNotice("Accounts refreshed.");
    } catch (err) {
      setNotice(message(err));
    } finally {
      setBusy(false);
    }
  }

  const list = connections || [];
  // No account chosen means every channel in the workspace is in scope.
  const active = list.find((item) => item.id === activeAccount) || null;
  const attention = list.filter(
    (item) => tokenHealth(item, now) !== "active",
  ).length;

  const pillClass = (provider?: string) =>
    provider === "instagram" ||
    provider === "whatsapp" ||
    provider === "telegram"
      ? provider
      : "facebook";

  const renderChannelIcon = (provider: string) => {
    if (provider === "instagram")
      return <BrandIcon name="instagram" size={10} mono />;
    if (provider === "messenger" || provider === "facebook")
      return <BrandIcon name="facebook" size={10} mono />;
    if (provider === "whatsapp")
      return <BrandIcon name="whatsapp" size={10} mono />;
    if (provider === "telegram")
      return <BrandIcon name="telegram" size={10} mono />;
    return <MessageCircle size={11} />;
  };

  return (
    <div className="boosend-account-switcher" ref={root}>
      <button
        type="button"
        className="social-account-card-trigger"
        aria-label={`Switch channel account, current: ${active?.display_name || "All accounts"}`}
        aria-expanded={open}
        onClick={() => {
          setOpen((val) => !val);
          if (!open) load().catch(() => undefined);
        }}
      >
        <div className="account-avatar-wrapper">
          <div className="account-avatar-circle">
            {active ? initials(active.display_name) : list.length}
          </div>
          {active && (
            <span
              className={`platform-badge-pill ${pillClass(active.provider)}`}
            >
              {renderChannelIcon(active.provider)}
            </span>
          )}
        </div>
        <div className="account-card-text">
          <span
            className="account-handle"
            title={active?.display_name || "All accounts"}
          >
            {active ? active.display_name : "All accounts"}
          </span>
          <span className="account-followers-sub">
            {active
              ? accountSubtitle(active)
              : list.length
                ? `${list.length} connected channel${list.length === 1 ? "" : "s"}`
                : "No channels connected"}
          </span>
        </div>
        {attention > 0 && (
          <span
            className="account-attention"
            title={`${attention} account${attention === 1 ? "" : "s"} need attention`}
          >
            {attention}
          </span>
        )}
        <ChevronDown
          size={14}
          className={`dropdown-chevron ${open ? "flip" : ""}`}
        />
      </button>

      {/* Dropdown Menu matching BooSend Screenshot 4 */}
      {open && (
        <div className="social-account-menu-popover">
          <div className="menu-header-label">SWITCH ACCOUNT</div>
          <div className="account-list-scroll">
            <button
              type="button"
              className={`account-switch-row ${active ? "" : "selected"}`}
              onClick={() => {
                setActiveAccount(null);
                setOpen(false);
              }}
            >
              <div className="account-avatar-wrapper">
                <div className="account-avatar-circle">{list.length}</div>
              </div>
              <div className="account-row-info">
                <span className="row-handle">All accounts</span>
                <span className="row-followers">
                  Every channel in {workspace.name}
                </span>
              </div>
              {!active && <Check size={16} className="selected-check" />}
            </button>
            {list.map((item) => {
              const selected = item.id === active?.id;
              const health = tokenHealth(item, now);
              return (
                <button
                  type="button"
                  key={item.id}
                  className={`account-switch-row ${selected ? "selected" : ""}`}
                  onClick={() => {
                    setActiveAccount(item.id);
                    setOpen(false);
                  }}
                >
                  <div className="account-avatar-wrapper">
                    <div className="account-avatar-circle">
                      {initials(item.display_name)}
                    </div>
                    <span
                      className={`platform-badge-pill ${pillClass(
                        item.provider,
                      )}`}
                    >
                      {renderChannelIcon(item.provider)}
                    </span>
                  </div>
                  <div className="account-row-info">
                    <span className="row-handle" title={item.display_name}>
                      {item.display_name}
                    </span>
                    <span className="row-followers">
                      {accountSubtitle(item)}
                      {item.is_test && " · test"}
                    </span>
                    <span className={`token-state token-${health}`}>
                      <i aria-hidden="true" /> {TOKEN_LABELS[health]}
                    </span>
                  </div>
                  {selected && <Check size={16} className="selected-check" />}
                </button>
              );
            })}

            {connections !== null && !list.length && (
              <p className="account-empty">No channels connected yet.</p>
            )}
          </div>

          <div className="menu-action-footer">
            <button
              type="button"
              className="menu-action-btn"
              onClick={refreshTokens}
              disabled={busy}
            >
              <RefreshCw size={13} className={busy ? "spin" : ""} />
              {busy ? "Refreshing…" : "Refresh Accounts"}
            </button>
            <Link
              href={`/w/${workspace.id}/integrations`}
              className="menu-action-btn primary-link"
              onClick={() => setOpen(false)}
            >
              <Plus size={13} />
              Manage Meta Accounts
            </Link>
          </div>
          {notice && <div className="notice-chip">{notice}</div>}
        </div>
      )}
    </div>
  );
}
