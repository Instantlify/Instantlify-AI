"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Check,
  ChevronDown,
  Instagram,
  Plus,
  RefreshCw,
  Facebook,
  MessageCircle,
} from "lucide-react";
import { api, message, type Connection, type Page } from "@/lib/api";
import {
  compactNumber,
  switchable,
  tokenHealth,
} from "@/lib/channels";
import { useWorkspace } from "@/lib/workspace";
import { initials } from "./shell";

/**
 * Meta Account Switcher matching BooSend Screenshots 3, 4, and 12:
 * Rounded dark card showing active Instagram/Facebook handle and follower count,
 * with popup dropdown to switch accounts, refresh tokens, or manage connections.
 */
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
      await api<{ queued: number }>(
        `${prefix}/connections/refresh/`,
        "POST",
      );
      await load();
      setNotice("Accounts refreshed.");
    } catch (err) {
      setNotice(message(err));
    } finally {
      setBusy(false);
    }
  }

  const list = connections || [];
  const active = list.find((item) => item.id === activeAccount) || list[0] || null;

  const renderChannelIcon = (provider: string) => {
    if (provider === "instagram") return <Instagram size={11} />;
    if (provider === "messenger" || provider === "facebook") return <Facebook size={11} />;
    return <MessageCircle size={11} />;
  };

  return (
    <div className="boosend-account-switcher" ref={root}>
      <button
        type="button"
        className="social-account-card-trigger"
        aria-expanded={open}
        onClick={() => {
          setOpen((val) => !val);
          if (!open) load().catch(() => undefined);
        }}
      >
        <div className="account-avatar-wrapper">
          <div className="account-avatar-circle">
            {active ? initials(active.display_name) : "@"}
          </div>
          <span
            className={`platform-badge-pill ${
              active?.provider === "instagram" ? "instagram" : "facebook"
            }`}
          >
            {renderChannelIcon(active?.provider || "instagram")}
          </span>
        </div>
        <div className="account-card-text">
          <span className="account-handle" title={active?.display_name || "Connect Instagram"}>
            {active ? active.display_name : "@censtd_nutech"}
          </span>
          <span className="account-followers-sub">
            {active
              ? active.followers !== null
                ? `${compactNumber(active.followers)} followers`
                : active.provider === "instagram"
                  ? "Instagram Business"
                  : "Facebook Page"
              : "193 followers"}
          </span>
        </div>
        <ChevronDown size={14} className={`dropdown-chevron ${open ? "flip" : ""}`} />
      </button>

      {/* Dropdown Menu matching BooSend Screenshot 4 */}
      {open && (
        <div className="social-account-menu-popover">
          <div className="menu-header-label">SWITCH ACCOUNT</div>
          <div className="account-list-scroll">
            {list.map((item) => {
              const selected = item.id === (activeAccount || active?.id);
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
                      className={`platform-badge-pill ${
                        item.provider === "instagram" ? "instagram" : "facebook"
                      }`}
                    >
                      {renderChannelIcon(item.provider)}
                    </span>
                  </div>
                  <div className="account-row-info">
                    <span className="row-handle" title={item.display_name}>
                      {item.display_name}
                    </span>
                    <span className="row-followers">
                      {item.followers !== null
                        ? `${compactNumber(item.followers)} followers`
                        : item.provider === "instagram"
                          ? "Instagram Business"
                          : "Facebook Page"}
                    </span>
                  </div>
                  {selected && <Check size={16} className="selected-check" />}
                </button>
              );
            })}

            {/* Default mock row for demo/onboarding preview if no live Meta account linked */}
            {!list.length && (
              <>
                <button
                  type="button"
                  className="account-switch-row selected"
                  onClick={() => setOpen(false)}
                >
                  <div className="account-avatar-wrapper">
                    <div className="account-avatar-circle">CN</div>
                    <span className="platform-badge-pill instagram">
                      <Instagram size={11} />
                    </span>
                  </div>
                  <div className="account-row-info">
                    <span className="row-handle">@censtd_nutech</span>
                    <span className="row-followers">193 followers</span>
                  </div>
                  <Check size={16} className="selected-check" />
                </button>
                <button
                  type="button"
                  className="account-switch-row"
                  onClick={() => setOpen(false)}
                >
                  <div className="account-avatar-wrapper">
                    <div className="account-avatar-circle">SH</div>
                    <span className="platform-badge-pill facebook">
                      <Facebook size={11} />
                    </span>
                  </div>
                  <div className="account-row-info">
                    <span className="row-handle">SHAMA - Lightening...</span>
                    <span className="row-followers">Facebook Page</span>
                  </div>
                </button>
              </>
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
