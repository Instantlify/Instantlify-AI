"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Brand } from "@/components/shell";
import { TrackVisit } from "@/components/growth";
import { ApiError } from "@/lib/api";
import { blogBeacon, blogPost, type BlogPost } from "@/lib/growth";

/** One public post. Scroll depth and dwell time go to the first-party beacon when
 * the reader leaves or hides the tab — the moment a page-view counter can't see. */
export default function BlogPostPage() {
  const { slug } = useParams<{ slug: string }>();
  const [post, setPost] = useState<BlogPost | null>(null);
  const [missing, setMissing] = useState(false);
  const deepest = useRef(0);
  const opened = useRef(0);

  useEffect(() => {
    let live = true;
    blogPost(slug)
      .then((body) => {
        if (!live) return;
        setPost(body);
        document.title = body.title;
      })
      .catch((err) => {
        if (live && err instanceof ApiError && err.status === 404)
          setMissing(true);
      });
    return () => {
      live = false;
    };
  }, [slug]);

  useEffect(() => {
    if (!post) return;
    opened.current = Date.now();
    function measure() {
      const scrollable =
        document.documentElement.scrollHeight - window.innerHeight;
      const depth = scrollable <= 0 ? 100 : (window.scrollY / scrollable) * 100;
      deepest.current = Math.max(deepest.current, Math.min(100, depth));
    }
    function report() {
      if (document.visibilityState !== "hidden") return;
      blogBeacon(slug, deepest.current, (Date.now() - opened.current) / 1000);
    }
    measure();
    window.addEventListener("scroll", measure, { passive: true });
    document.addEventListener("visibilitychange", report);
    return () => {
      window.removeEventListener("scroll", measure);
      document.removeEventListener("visibilitychange", report);
    };
  }, [post, slug]);

  return (
    <div className="blog-page">
      <TrackVisit page={`/blog/${slug}`} />
      <header className="blog-header">
        <Link href="/blog">
          <Brand />
        </Link>
      </header>
      <main className="blog-main">
        {missing && <p className="muted">That post doesn&rsquo;t exist.</p>}
        {!missing && !post && <p className="muted">Loading…</p>}
        {post && (
          <article className="blog-article">
            {post.category && <span className="eyebrow">{post.category}</span>}
            <h1>{post.title}</h1>
            {post.excerpt && <p className="blog-lede">{post.excerpt}</p>}
            {/* Body is rendered as text paragraphs, never as HTML. */}
            {post.body
              .split(/\n{2,}/)
              .filter((part) => part.trim())
              .map((part, index) => (
                <p key={index}>{part}</p>
              ))}
          </article>
        )}
      </main>
    </div>
  );
}
