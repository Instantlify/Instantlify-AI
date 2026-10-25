"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { ArrowUpRight, Mail } from "lucide-react";
import { api } from "@/lib/api";
import type { CreatorKit } from "@/lib/portal-tools";

export default function PublicCreatorPage() {
  const { slug } = useParams<{ slug: string }>();
  const [kit, setKit] = useState<CreatorKit | null>(null);
  const [loaded, setLoaded] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    api<CreatorKit>(
      `/api/public/creator/${slug}/`,
      "GET",
      undefined,
      controller.signal,
    )
      .then(setKit)
      .catch(() => {})
      .finally(() => {
        if (!controller.signal.aborted) setLoaded(true);
      });
    return () => controller.abort();
  }, [slug]);
  return (
    <main style={{ maxWidth: 880, padding: "56px 24px", margin: "0 auto" }}>
      {!loaded ? (
        <p>Loading…</p>
      ) : !kit ? (
        <p>This creator kit is unavailable.</p>
      ) : (
        <>
          <header
            style={{ padding: "40px 0", borderBottom: "1px solid var(--line)" }}
          >
            <span className="eyebrow">Creator & collaborator</span>
            <h1
              style={{
                fontSize: "clamp(36px, 6vw, 64px)",
                lineHeight: 1.08,
                margin: "18px 0",
              }}
            >
              {kit.name}
            </h1>
            <p style={{ fontSize: 21 }}>{kit.headline}</p>
            <p style={{ maxWidth: 640, whiteSpace: "pre-wrap" }}>{kit.bio}</p>
            {kit.contact_email && (
              <a
                className="button primary"
                href={`mailto:${kit.contact_email}`}
              >
                <Mail size={16} /> Let’s collaborate
              </a>
            )}
          </header>
          {!!kit.statistics.length && (
            <section style={{ margin: "32px 0" }}>
              <div className="stats-grid">
                {kit.statistics.map((row, index) => (
                  <article className="stat-card" key={index}>
                    <strong>{row.value}</strong>
                    <p>{row.label}</p>
                  </article>
                ))}
              </div>
              <small>Audience figures provided by the creator.</small>
            </section>
          )}
          {!!kit.services.length && (
            <section style={{ margin: "36px 0" }}>
              <h2>Ways to work together</h2>
              <div className="stats-grid">
                {kit.services.map((row, index) => (
                  <article key={index} className="card" style={{ padding: 24 }}>
                    <h3>{row.title}</h3>
                    <p>{row.description}</p>
                  </article>
                ))}
              </div>
            </section>
          )}
          {!!kit.links.length && (
            <section>
              <h2>Explore my work</h2>
              <div className="form-grid">
                {kit.links.map((row, index) => (
                  <a
                    className="button secondary"
                    key={index}
                    href={row.url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {row.label}
                    <ArrowUpRight size={15} />
                  </a>
                ))}
              </div>
            </section>
          )}
        </>
      )}
    </main>
  );
}
