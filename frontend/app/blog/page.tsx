"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Brand } from "@/components/shell";
import { TrackVisit } from "@/components/growth";
import { blogPosts, type BlogSummary } from "@/lib/growth";

export default function BlogIndex() {
  const [posts, setPosts] = useState<BlogSummary[] | null>(null);

  useEffect(() => {
    let live = true;
    blogPosts()
      .then((rows) => {
        if (live) setPosts(rows);
      })
      .catch(() => {
        if (live) setPosts([]);
      });
    return () => {
      live = false;
    };
  }, []);

  return (
    <div className="blog-page">
      <TrackVisit page="/blog" />
      <header className="blog-header">
        <Link href="/">
          <Brand />
        </Link>
      </header>
      <main className="blog-main">
        <h1>Blog</h1>
        {posts === null && <p className="muted">Loading…</p>}
        {posts?.length === 0 && <p className="muted">No posts yet.</p>}
        <ul className="blog-list">
          {posts?.map((post) => (
            <li key={post.slug}>
              <Link href={`/blog/${post.slug}`}>
                {post.category && (
                  <span className="eyebrow">{post.category}</span>
                )}
                <h2>{post.title}</h2>
                {post.excerpt && <p>{post.excerpt}</p>}
              </Link>
            </li>
          ))}
        </ul>
      </main>
    </div>
  );
}
