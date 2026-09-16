"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api, ApiError, type PublicBio } from "@/lib/api";

export default function PublicBioPage() {
  const { slug } = useParams<{ slug: string }>();
  const [page, setPage] = useState<PublicBio | null>(null);
  const [state, setState] = useState<"loading" | "missing" | "ready">(
    "loading",
  );
  useEffect(() => {
    const controller = new AbortController();
    api<PublicBio>(
      `/api/public/bio/${slug}/`,
      "GET",
      undefined,
      controller.signal,
    )
      .then((data) => {
        setPage(data);
        setState("ready");
        document.title = data.title;
      })
      .catch((err) => {
        if (!controller.signal.aborted)
          setState(
            err instanceof ApiError && err.status === 404
              ? "missing"
              : "missing",
          );
      });
    return () => controller.abort();
  }, [slug]);
  async function open(index: number, fallback: string) {
    try {
      const { url } = await api<{ url: string }>(
        `/api/public/bio/${slug}/`,
        "POST",
        { index },
      );
      window.location.assign(url);
    } catch {
      window.location.assign(fallback);
    }
  }
  if (state === "loading")
    return (
      <div className="loading-screen">
        <p>Loading…</p>
      </div>
    );
  if (state === "missing" || !page)
    return (
      <div className="loading-screen">
        <p>This page isn’t available.</p>
      </div>
    );
  return (
    <main
      className="setup-screen"
      style={{ ["--green" as string]: page.accent }}
    >
      <div className="bio-preview">
        {page.avatar_url && (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={page.avatar_url} alt="" />
        )}
        <h1 style={{ fontSize: 24 }}>{page.title}</h1>
        {page.bio && <p>{page.bio}</p>}
        {page.links.map((link) => (
          <button
            key={link.index}
            className="bio-link"
            style={{ background: page.accent }}
            onClick={() => open(link.index, link.url)}
          >
            {link.title}
          </button>
        ))}
        {!page.branding.hide_platform_branding && (
          <p className="muted-text" style={{ marginTop: 10 }}>
            Made with {page.branding.brand_name}
          </p>
        )}
      </div>
    </main>
  );
}
