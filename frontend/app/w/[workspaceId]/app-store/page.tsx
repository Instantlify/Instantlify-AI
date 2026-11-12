"use client";

import Link from "next/link";
import { type ReactNode } from "react";
import {
  ArrowUpRight,
  Calendar,
  FileText,
  Link2,
  MessageCircle,
  MessageSquare,
  Minus,
  MousePointerClick,
  Plus,
  ShieldAlert,
  Star,
  Trash2,
  TrendingUp,
  GraduationCap,
} from "lucide-react";
import { api } from "@/lib/api";
import { useWorkspace } from "@/lib/workspace";
import { ErrorNotice, SuccessNotice, useFeedback } from "@/components/ui";

interface StoreApp {
  id: string;
  name: string;
  description: string;
  section?: string;
  status?: "available" | "coming_soon" | "subscription";
  price?: string;
  icon: ReactNode;
  banner: ReactNode;
}

export default function AppStorePage() {
  const { workspace, prefix, refresh } = useWorkspace();
  const feedback = useFeedback();
  const pinned = workspace.pinned_apps || [];

  async function togglePin(id: string, name: string) {
    const isPinned = pinned.includes(id);
    const next = isPinned
      ? pinned.filter((item) => item !== id)
      : [...pinned, id];

    await feedback.run(
      async () => {
        await api(`${prefix}/`, "PATCH", { pinned_apps: next });
        await refresh();
      },
      isPinned ? `${name} removed from menu.` : `${name} added to menu.`,
    );
  }

  const STORE_APPS: StoreApp[] = [
    {
      id: "tutorials",
      name: "Tutorials",
      description: "Setup guides that tick off as you complete each step.",
      section: "tutorials",
      status: "available",
      icon: <GraduationCap size={18} />,
      banner: (
        <div style={{ padding: 24 }}>
          <GraduationCap size={36} />
          <p>A live checklist for getting set up</p>
        </div>
      ),
    },
    {
      id: "forum",
      name: "Community",
      description: "Share questions and answers with Instantlify members.",
      section: "forum",
      status: "available",
      icon: <MessageSquare size={18} />,
      banner: (
        <div style={{ padding: 24 }}>
          <MessageSquare size={36} />
          <p>Discussions, replies and community answers</p>
        </div>
      ),
    },
    {
      id: "forms",
      name: "Forms",
      description:
        "Build embedded forms, share them anywhere, and collect responses into your CRM.",
      section: "forms",
      icon: <FileText size={18} color="#ffffff" />,
      banner: (
        <div
          style={{
            width: "100%",
            height: "100%",
            background: "linear-gradient(135deg, #1e1b4b 0%, #312e81 100%)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: "20px",
          }}
        >
          <div
            style={{
              background: "#ffffff",
              borderRadius: "12px",
              padding: "12px 18px",
              boxShadow: "0 10px 25px rgba(0,0,0,0.25)",
              display: "flex",
              flexDirection: "column",
              gap: "6px",
              width: "200px",
            }}
          >
            <div style={{ display: "flex", gap: "3px" }}>
              {[1, 2, 3, 4, 5].map((i) => (
                <Star key={i} size={14} fill="#eab308" color="#eab308" />
              ))}
            </div>
            <div
              style={{ fontSize: "11px", fontWeight: 700, color: "#0f172a" }}
            >
              Customer Intake Form
            </div>
            <div
              style={{
                height: "6px",
                background: "#f1f5f9",
                borderRadius: "3px",
                width: "80%",
              }}
            />
          </div>
        </div>
      ),
    },
    {
      id: "bio",
      name: "Link In Bio",
      description:
        "Create a Link-In-Bio website to promote your products & services",
      section: "bio",
      icon: <Link2 size={18} color="#ffffff" />,
      banner: (
        <div
          style={{
            width: "100%",
            height: "100%",
            background: "linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            position: "relative",
          }}
        >
          {/* Mini mobile bio mockup */}
          <div
            style={{
              width: "170px",
              height: "120px",
              background: "#ffffff",
              borderRadius: "14px 14px 0 0",
              border: "2px solid #cbd5e1",
              borderBottom: "none",
              padding: "10px",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              boxShadow: "0 8px 20px rgba(0,0,0,0.06)",
            }}
          >
            <div
              style={{
                width: "24px",
                height: "24px",
                borderRadius: "50%",
                background: "#0f172a",
                color: "#fff",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: "10px",
                fontWeight: 700,
                marginBottom: "4px",
              }}
            >
              N
            </div>
            <div
              style={{ fontSize: "10px", fontWeight: 700, color: "#0f172a" }}
            >
              @{workspace.name.toLowerCase().replace(/[^a-z0-9]+/g, "_")}
            </div>
            <div
              style={{
                width: "100%",
                padding: "4px",
                background: "#0f172a",
                color: "#fff",
                borderRadius: "6px",
                fontSize: "8px",
                textAlign: "center",
                fontWeight: 600,
                marginTop: "6px",
              }}
            >
              Book Consultation ↗
            </div>
          </div>
        </div>
      ),
    },
    {
      id: "calendar",
      name: "Content Calendar",
      description: "Schedule Instagram posts and publish them on time",
      section: "calendar",
      icon: <Calendar size={18} color="#ffffff" />,
      banner: (
        <div
          style={{
            width: "100%",
            height: "100%",
            background: "linear-gradient(135deg, #ede9fe 0%, #ddd6fe 100%)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: "16px",
          }}
        >
          <div
            style={{
              background: "#ffffff",
              borderRadius: "12px",
              padding: "10px 14px",
              boxShadow: "0 8px 20px rgba(0,0,0,0.06)",
              display: "grid",
              gridTemplateColumns: "repeat(3, 1fr)",
              gap: "6px",
              width: "190px",
            }}
          >
            {["Mon", "Tue", "Wed"].map((day, idx) => (
              <div
                key={day}
                style={{
                  background: idx === 1 ? "#0f172a" : "#f8fafc",
                  color: idx === 1 ? "#ffffff" : "#64748b",
                  padding: "6px 4px",
                  borderRadius: "6px",
                  textAlign: "center",
                  fontSize: "9px",
                  fontWeight: 600,
                }}
              >
                {day}
                <div
                  style={{
                    fontSize: "11px",
                    fontWeight: 700,
                    marginTop: "2px",
                  }}
                >
                  {14 + idx}
                </div>
              </div>
            ))}
          </div>
        </div>
      ),
    },
    {
      id: "shield",
      name: "Hate Detection",
      description:
        "Hide or reply to abusive comments with keyword or AI rules.",
      section: "shield",
      icon: <ShieldAlert size={18} color="#ffffff" />,
      banner: (
        <div
          style={{
            width: "100%",
            height: "100%",
            background: "linear-gradient(135deg, #881337 0%, #4c0519 100%)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: "12px",
          }}
        >
          {/* Red warning stickers into trash */}
          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            <div
              style={{
                background: "#ffffff",
                color: "#e11d48",
                fontSize: "10px",
                fontWeight: 800,
                padding: "4px 8px",
                borderRadius: "9999px",
                boxShadow: "0 4px 10px rgba(0,0,0,0.2)",
                transform: "rotate(-6deg)",
              }}
            >
              🚫 SPAM / SCAM
            </div>
            <div
              style={{
                background: "#ffffff",
                color: "#e11d48",
                fontSize: "10px",
                fontWeight: 800,
                padding: "4px 8px",
                borderRadius: "9999px",
                boxShadow: "0 4px 10px rgba(0,0,0,0.2)",
                transform: "rotate(4deg)",
              }}
            >
              ⚠️ HATE SPEECH
            </div>
          </div>
          <div
            style={{
              width: "38px",
              height: "44px",
              borderRadius: "4px 4px 10px 10px",
              background: "#e2e8f0",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              boxShadow: "0 8px 16px rgba(0,0,0,0.3)",
            }}
          >
            <Trash2 size={20} color="#64748b" />
          </div>
        </div>
      ),
    },
    {
      id: "creator-kit",
      name: "Creator Kit",
      description:
        "Promote yourself as a content creator by showcasing your stats",
      section: "creator-kit",
      icon: <TrendingUp size={18} color="#ffffff" />,
      banner: (
        <div
          style={{
            width: "100%",
            height: "100%",
            background: "linear-gradient(135deg, #0284c7 0%, #0369a1 100%)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <div
            style={{
              background: "#ffffff",
              borderRadius: "12px",
              padding: "10px 14px",
              width: "180px",
              boxShadow: "0 10px 25px rgba(0,0,0,0.2)",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
            }}
          >
            <div>
              <div
                style={{ fontSize: "9px", color: "#64748b", fontWeight: 600 }}
              >
                Reach
              </div>
              <div
                style={{ fontSize: "14px", fontWeight: 800, color: "#0f172a" }}
              >
                71.4K
              </div>
            </div>
            <div style={{ textAlign: "right" }}>
              <div
                style={{ fontSize: "9px", color: "#64748b", fontWeight: 600 }}
              >
                Engagement
              </div>
              <div
                style={{ fontSize: "14px", fontWeight: 800, color: "#10b981" }}
              >
                10.4%
              </div>
            </div>
          </div>
        </div>
      ),
    },
    {
      id: "deeplinks",
      name: "Tracking Links",
      description:
        "Trackable short links with UTM tags, QR codes and click counts",
      section: "deeplinks",
      icon: <MousePointerClick size={18} color="#ffffff" />,
      banner: (
        <div
          style={{
            width: "100%",
            height: "100%",
            background: "linear-gradient(135deg, #0f766e 0%, #115e59 100%)",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            gap: "8px",
          }}
        >
          <div
            style={{
              background: "#ffffff",
              borderRadius: "9999px",
              padding: "4px 12px",
              display: "flex",
              alignItems: "center",
              gap: "8px",
              fontSize: "10px",
              fontWeight: 600,
              boxShadow: "0 4px 12px rgba(0,0,0,0.15)",
            }}
          >
            <span style={{ color: "#0f172a" }}>instantlify.com/offer</span>
            <span
              style={{
                background: "#f0fdf4",
                color: "#16a34a",
                fontSize: "9px",
                padding: "1px 6px",
                borderRadius: "9999px",
                fontWeight: 700,
              }}
            >
              5,998 clicks
            </span>
          </div>
          <div
            style={{
              background: "#ffffff",
              borderRadius: "9999px",
              padding: "4px 12px",
              display: "flex",
              alignItems: "center",
              gap: "8px",
              fontSize: "10px",
              fontWeight: 600,
              boxShadow: "0 4px 12px rgba(0,0,0,0.15)",
            }}
          >
            <span style={{ color: "#0f172a" }}>instantlify.com/community</span>
            <span
              style={{
                background: "#f0fdf4",
                color: "#16a34a",
                fontSize: "9px",
                padding: "1px 6px",
                borderRadius: "9999px",
                fontWeight: 700,
              }}
            >
              14,896 clicks
            </span>
          </div>
        </div>
      ),
    },
    {
      id: "webchat",
      name: "Web Support",
      description:
        "Embed a chat widget on your site. Build AI-powered customer support with workflows.",
      section: "webchat",
      status: "subscription",
      price: "$9/mo",
      icon: <MessageSquare size={18} color="#ffffff" />,
      banner: (
        <div
          style={{
            width: "100%",
            height: "100%",
            background: "linear-gradient(135deg, #c2410c 0%, #9a3412 100%)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          <div
            style={{
              background: "#ffffff",
              borderRadius: "14px",
              padding: "12px 16px",
              width: "190px",
              boxShadow: "0 10px 25px rgba(0,0,0,0.25)",
              display: "flex",
              alignItems: "center",
              gap: "10px",
            }}
          >
            <div
              style={{
                width: "32px",
                height: "32px",
                borderRadius: "50%",
                background: "#0f172a",
                color: "#fff",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <MessageCircle size={16} />
            </div>
            <div>
              <div
                style={{ fontSize: "11px", fontWeight: 700, color: "#0f172a" }}
              >
                Live Support
              </div>
              <div
                style={{ fontSize: "9px", color: "#10b981", fontWeight: 600 }}
              >
                ● Active Now
              </div>
            </div>
          </div>
        </div>
      ),
    },
  ];

  return (
    <div className="boosend-appstore-page">
      {/* Header */}
      <div style={{ marginBottom: "24px" }}>
        <h1
          style={{
            fontSize: "26px",
            fontWeight: 700,
            color: "#0f172a",
            margin: 0,
            letterSpacing: "-0.5px",
          }}
        >
          App Store
        </h1>
        <p style={{ fontSize: "14px", color: "#64748b", marginTop: "4px" }}>
          Tools that sit next to your conversations. Add them to your sidebar
          menu.
        </p>
      </div>

      <ErrorNotice error={feedback.error} />
      <SuccessNotice notice={feedback.notice} />

      {/* 3-Column Visual Grid matching Screenshot 11 */}
      <div className="boosend-appstore-grid">
        {STORE_APPS.map((app) => {
          const pinId = app.id;
          const isPinned = pinned.includes(pinId);
          const isComingSoon = app.status === "coming_soon";
          const openUrl = app.section
            ? `/w/${workspace.id}/${app.section}`
            : null;

          return (
            <div key={app.id} className="boosend-appstore-card">
              {/* Visual Banner */}
              <div className="boosend-appstore-banner">{app.banner}</div>

              {/* Info Content */}
              <div className="boosend-appstore-content">
                <div>
                  <div className="boosend-appstore-head">
                    <div className="boosend-appstore-icon">{app.icon}</div>
                    <span className="boosend-appstore-title">{app.name}</span>
                  </div>

                  <p className="boosend-appstore-desc">{app.description}</p>
                </div>

                {/* Footer Actions */}
                <div className="boosend-appstore-actions">
                  {isComingSoon ? (
                    <div className="boosend-appstore-btn-soon">Coming soon</div>
                  ) : (
                    <>
                      {openUrl ? (
                        <Link
                          href={openUrl}
                          className="boosend-appstore-btn-open"
                        >
                          <ArrowUpRight size={14} /> Open
                        </Link>
                      ) : (
                        <button
                          type="button"
                          className="boosend-appstore-btn-open"
                        >
                          <ArrowUpRight size={14} /> Open
                        </button>
                      )}

                      <button
                        type="button"
                        className="boosend-appstore-btn-pin"
                        disabled={feedback.busy}
                        onClick={() => togglePin(pinId, app.name)}
                      >
                        {isPinned ? (
                          <>
                            <Minus size={13} /> Remove From Menu
                          </>
                        ) : (
                          <>
                            <Plus size={13} /> Add To Menu
                          </>
                        )}
                      </button>
                    </>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
