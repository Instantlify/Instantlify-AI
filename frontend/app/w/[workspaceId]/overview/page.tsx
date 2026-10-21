"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  GraduationCap,
  MessageCircle,
  RefreshCw,
  Send,
  Sparkles,
  Trophy,
  Users,
  Coins,
  ArrowRight,
} from "lucide-react";
import { api, type Connection, type Page } from "@/lib/api";
import { useWorkspace } from "@/lib/workspace";

// Demo leaderboard accounts matching BooSend Screenshot 1
const LEADERBOARD_USERS = [
  { rank: 1, name: "Sarah K.", dms: "90k", color: "#ec4899", initials: "SK" },
  { rank: 2, name: "David M.", dms: "58k", color: "#3b82f6", initials: "DM" },
  { rank: 3, name: "Elena R.", dms: "51k", color: "#eab308", initials: "ER" },
  { rank: 4, name: "Lucas P.", dms: "41k", color: "#10b981", initials: "LP" },
  { rank: 5, name: "Aria T.", dms: "37k", color: "#8b5cf6", initials: "AT" },
  { rank: 6, name: "Marcus", dms: "32k", color: "#06b6d4", initials: "MC" },
  { rank: 7, name: "Julian", dms: "30k", color: "#f97316", initials: "JL" },
  { rank: 8, name: "NAT Pro", dms: "27k", color: "#64748b", initials: "NP" },
];

export default function OverviewPage() {
  const { workspace, prefix, manager } = useWorkspace();
  const [connections, setConnections] = useState<Connection[]>([]);
  const [stats, setStats] = useState({
    conversations: 0,
    contacts: 0,
    aiUsageCents: 0,
  });
  const [refreshing, setRefreshing] = useState(false);

  const loadData = useCallback(
    async (signal?: AbortSignal) => {
      try {
        const [channels, funnelReport] = await Promise.all([
          api<Page<Connection>>(`${prefix}/connections/`, "GET", undefined, signal),
          api<{ leads: number; conversations: number }>(
            `${prefix}/analytics/funnel/?period=7d`,
            "GET",
            undefined,
            signal,
          ).catch(() => ({ leads: 0, conversations: 0 })),
        ]);
        setConnections(channels.results || []);
        setStats({
          conversations: funnelReport.conversations || 0,
          contacts: funnelReport.leads || 0,
          aiUsageCents: 0,
        });
      } catch {
        // Fallback gracefully for new workspaces
      }
    },
    [prefix],
  );

  useEffect(() => {
    const controller = new AbortController();
    loadData(controller.signal);
    return () => controller.abort();
  }, [loadData]);

  async function handleRefresh() {
    setRefreshing(true);
    await loadData();
    setTimeout(() => setRefreshing(false), 500);
  }

  return (
    <div className="overview-page-container">
      {/* 1. Leaderboard Bar (Matching Screenshot 1) */}
      <section className="boosend-leaderboard-bar">
        <div className="leaderboard-info">
          <span className="trophy-badge">
            <Trophy size={18} className="trophy-gold" />
          </span>
          <div className="leaderboard-text">
            <strong className="leaderboard-title">Leaderboard</strong>
            <span className="leaderboard-subtitle">
              Top Instagram accounts by DM Conversations this month
            </span>
          </div>
        </div>

        <div className="leaderboard-avatars-row">
          {LEADERBOARD_USERS.map((user) => (
            <div key={user.rank} className="leaderboard-avatar-item" title={`${user.name} (${user.dms} DMs)`}>
              <div
                className="avatar-circle"
                style={{ backgroundColor: user.color }}
              >
                {user.initials}
                {user.rank <= 3 && (
                  <span className={`rank-chip rank-${user.rank}`}>{user.rank}</span>
                )}
              </div>
              <span className="score-pill">{user.dms}</span>
            </div>
          ))}
        </div>

        <button className="your-place-button" type="button">
          <span className="dash">—</span>
          <span className="btn-label">YOUR PLACE</span>
        </button>
      </section>

      {/* 2. Hero Quick Action Cards (Matching Screenshot 1) */}
      <section className="boosend-quick-actions-row">
        {/* Left Card: Learn To Use Nemio */}
        <Link href={`/w/${workspace.id}/help`} className="quick-action-card learn-card">
          <div className="action-card-icon-cap">
            <GraduationCap size={32} />
          </div>
          <div className="action-card-content">
            <h2 className="action-card-heading">Learn To Use Nemio</h2>
            <p className="action-card-desc">
              Discover how to build Meta automated funnels, comment triggers, and human handoffs.
            </p>
          </div>
          <ArrowRight size={20} className="hover-arrow" />
        </Link>

        {/* Right Card: Connect Claude MCP with Dot-Matrix Pattern */}
        <div className="quick-action-card mcp-dark-card">
          <div className="mcp-starburst-icon">
            <Sparkles size={28} />
          </div>
          <div className="action-card-content">
            <h2 className="action-card-heading white-heading">Connect Claude MCP</h2>
            <p className="action-card-desc light-desc">
              Power external AI workflows with realtime Instagram conversations & lead triggers.
            </p>
          </div>
          <span className="mcp-status-pill">Active</span>
        </div>
      </section>

      {/* 3. Your Statistics Section (Matching Screenshot 1) */}
      <section className="boosend-statistics-section">
        <div className="section-title-row">
          <div>
            <h2 className="section-main-heading">Your Statistics</h2>
            <span className="section-sub-heading">Real-time performance metrics</span>
          </div>
          <button
            type="button"
            className="refresh-metrics-btn"
            onClick={handleRefresh}
            disabled={refreshing}
          >
            <RefreshCw size={14} className={refreshing ? "spin" : ""} />
            Refresh
          </button>
        </div>

        {/* 3 Metrics Cards */}
        <div className="metrics-cards-grid">
          {/* Card 1: Conversations */}
          <div className="metric-kpi-card cyan-tone">
            <div className="kpi-card-header">
              <span className="kpi-icon-wrap cyan">
                <Send size={15} />
              </span>
              <span className="kpi-label">Conversations</span>
            </div>
            <div className="kpi-value-row">
              <span className="kpi-number">{stats.conversations}</span>
            </div>
            <span className="kpi-period">JAN - DEC 2026</span>

            {/* Cyan Sparkline Area */}
            <div className="sparkline-wrapper">
              <svg className="sparkline-svg" viewBox="0 0 300 60" preserveAspectRatio="none">
                <path
                  d="M0,50 Q60,48 120,49 T240,48 T300,49"
                  fill="none"
                  stroke="#06b6d4"
                  strokeWidth="2.5"
                />
                <path
                  d="M0,50 Q60,48 120,49 T240,48 T300,49 L300,60 L0,60 Z"
                  fill="rgba(6, 182, 212, 0.08)"
                />
              </svg>
              <div className="sparkline-axis">
                <span>J</span>
                <span>F</span>
                <span>M</span>
                <span>A</span>
                <span>M</span>
                <span>J</span>
                <span>J</span>
                <span>A</span>
                <span>S</span>
                <span>O</span>
                <span>N</span>
                <span>D</span>
              </div>
            </div>

            <div className="kpi-footer-note">All connected accounts</div>
          </div>

          {/* Card 2: Contacts */}
          <div className="metric-kpi-card emerald-tone">
            <div className="kpi-card-header">
              <span className="kpi-icon-wrap emerald">
                <Users size={15} />
              </span>
              <span className="kpi-label">Contacts</span>
            </div>
            <div className="kpi-value-row">
              <span className="kpi-number">{stats.contacts}</span>
            </div>
            <span className="kpi-period">JAN - DEC 2026</span>

            {/* Emerald Peak Sparkline Area (Matching screenshot peak in Sep) */}
            <div className="sparkline-wrapper">
              <svg className="sparkline-svg" viewBox="0 0 300 60" preserveAspectRatio="none">
                <path
                  d="M0,55 L160,55 L190,15 L220,55 L300,55"
                  fill="none"
                  stroke="#10b981"
                  strokeWidth="2.5"
                />
                <path
                  d="M0,55 L160,55 L190,15 L220,55 L300,55 L300,60 L0,60 Z"
                  fill="rgba(16, 185, 129, 0.12)"
                />
              </svg>
              <div className="sparkline-axis">
                <span>J</span>
                <span>F</span>
                <span>M</span>
                <span>A</span>
                <span>M</span>
                <span>J</span>
                <span>J</span>
                <span>A</span>
                <span className="active-peak">S</span>
                <span>O</span>
                <span>N</span>
                <span>D</span>
              </div>
            </div>

            <div className="kpi-footer-note">Unique users reached</div>
          </div>

          {/* Card 3: AI Usage */}
          <div className="metric-kpi-card purple-tone">
            <div className="kpi-card-header">
              <span className="kpi-icon-wrap purple">
                <Coins size={15} />
              </span>
              <span className="kpi-label">AI Usage</span>
              <Link href={`/w/${workspace.id}/payments`} className="kpi-corner-link">
                Pricing
              </Link>
            </div>
            <div className="kpi-value-row">
              <span className="kpi-number">${(stats.aiUsageCents / 100).toFixed(2)}</span>
            </div>
            <span className="kpi-period">ENGINE COST · 2026</span>

            {/* Purple Flat Line Sparkline Area */}
            <div className="sparkline-wrapper">
              <svg className="sparkline-svg" viewBox="0 0 300 60" preserveAspectRatio="none">
                <path
                  d="M0,55 L300,55"
                  fill="none"
                  stroke="#8b5cf6"
                  strokeWidth="2.5"
                />
                <path
                  d="M0,55 L300,55 L300,60 L0,60 Z"
                  fill="rgba(139, 92, 246, 0.08)"
                />
              </svg>
              <div className="sparkline-axis">
                <span>J</span>
                <span>F</span>
                <span>M</span>
                <span>A</span>
                <span>M</span>
                <span>J</span>
                <span>J</span>
                <span>A</span>
                <span>S</span>
                <span>O</span>
                <span>N</span>
                <span>D</span>
              </div>
            </div>

            <div className="kpi-footer-note">Credits consumed</div>
          </div>
        </div>
      </section>
    </div>
  );
}
