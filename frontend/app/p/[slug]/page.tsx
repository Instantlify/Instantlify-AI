"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api, ApiError, message, type PublicBio } from "@/lib/api";
import { BioRenderer } from "@/components/bio-renderer";

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
  async function open(block: number, item?: number) {
    // Negative numbers address legacy links (pages saved before blocks existed).
    const body = block < 0 ? { index: -1 - block } : { block, item };
    try {
      const { url } = await api<{ url: string }>(
        `/api/public/bio/${slug}/`,
        "POST",
        body,
      );
      window.location.assign(url);
    } catch {
      // The server validates every target; without it there is nowhere safe to go.
    }
  }
  async function subscribe(block: number, email: string, name: string) {
    try {
      await api(`/api/public/bio/${slug}/`, "POST", { block, email, name });
      return "Thanks, you're on the list.";
    } catch (err) {
      return message(err);
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
    <main style={{ minHeight: "100vh" }}>
      <BioRenderer
        page={page}
        onOpen={open}
        onSubscribe={subscribe}
        footer={
          !page.branding.hide_platform_branding && (
            <p style={{ marginTop: 10, fontSize: 12, opacity: 0.7 }}>
              Made with {page.branding.brand_name}
            </p>
          )
        }
      />
    </main>
  );
}
