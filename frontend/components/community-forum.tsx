"use client";

import "./community-forum.css";
import { CommunityThread, type ThreadReply } from "./community-thread";
import {
  MessageSquare,
  Plus,
  Search,
  Sparkles,
  ThumbsUp,
  ThumbsDown,
  MoreHorizontal,
  Pin,
  ArrowLeft,
  ArrowRight,
  Download,
  RefreshCw,
  ArrowUpRight,
  ShieldCheck,
} from "lucide-react";
import { useConfirmation } from "@/components/confirmation-provider";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, message, when } from "@/lib/api";
import { ErrorNotice, SuccessNotice, Modal, useFeedback } from "./ui";
import {
  ValidatedForm,
  ValidatedInput,
  ValidatedTextarea,
} from "./validated-form";

type Post = {
  id: string;
  author: string;
  body: string;
  pinned: boolean;
  created_at: string;
  likes: number;
  dislikes: number;
  reply_count: number;
  my_vote: number;
  can_edit: boolean;
  can_delete: boolean;
  can_pin: boolean;
};
type Reply = ThreadReply;
type Source = { post_id: string; excerpt: string };
type Feed = { count: number; results: Post[] };

export function CommunityForum() {
  const confirm = useConfirmation();
  const feedback = useFeedback();
  const [feed, setFeed] = useState<Feed>({ count: 0, results: [] });
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [body, setBody] = useState("");
  const [composing, setComposing] = useState(false);
  const [search, setSearch] = useState("");
  const [edit, setEdit] = useState<Post | null>(null);
  const [thread, setThread] = useState<Post | null>(null);
  const [replies, setReplies] = useState<Reply[]>([]);
  const [replyCount, setReplyCount] = useState(0);
  const [replyPage, setReplyPage] = useState(1);
  const threadVersion = useRef(0);
  const [threadLoading, setThreadLoading] = useState(false);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [sources, setSources] = useState<Source[]>([]);
  const load = useCallback(
    (signal?: AbortSignal) =>
      api<Feed>(`/api/community/?page=${page}`, "GET", undefined, signal).then(
        setFeed,
      ),
    [page],
  );
  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal)
      .catch((error) => {
        if (!controller.signal.aborted) feedback.setError(message(error));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [load]);

  function replace(post: Post) {
    setFeed((current) => ({
      ...current,
      results: current.results.map((item) =>
        item.id === post.id ? post : item,
      ),
    }));
    if (thread?.id === post.id) setThread(post);
  }
  function closeThread() {
    threadVersion.current++;
    setThread(null);
    setReplies([]);
    setThreadLoading(false);
  }
  async function openThread(post: Post, number = 1) {
    const version = ++threadVersion.current;
    if (number === 1) {
      setThread(post);
      setReplies([]);
      setReplyPage(1);
      setReplyCount(post.reply_count);
      setSearch("");
      setFeed((current) =>
        current.results.some((item) => item.id === post.id)
          ? current
          : { ...current, results: [post, ...current.results] },
      );
    }
    setThreadLoading(true);
    try {
      const result = await api<{ count: number; results: Reply[] }>(
        `/api/community/${post.id}/replies/?page=${number}`,
      );
      if (version !== threadVersion.current) return;
      setReplies((current) =>
        number === 1
          ? result.results
          : [
              ...current,
              ...result.results.filter(
                (item) => !current.some((old) => old.id === item.id),
              ),
            ],
      );
      setReplyCount(result.count);
      setReplyPage(number);
    } finally {
      if (version === threadVersion.current) setThreadLoading(false);
    }
  }
  const posts = feed.results.filter((post) =>
    `${post.author} ${post.body}`.toLowerCase().includes(search.toLowerCase()),
  );
  return (
    <div className="community-page">
      <header className="community-heading">
        <div>
          <span className="community-eyebrow">INSTANTLIFY COMMUNITY</span>
          <h1>
            A little shared knowledge.
            <br />
            <span>A lot of possibility.</span>
          </h1>
          <p>
            Ask a question, share a workflow, and learn from other builders.
          </p>
        </div>
        <button
          type="button"
          className="button primary"
          onClick={() => setComposing(true)}
        >
          <Plus size={17} /> Start a discussion
        </button>
      </header>
      <ErrorNotice error={feedback.error} />
      <SuccessNotice notice={feedback.notice} />
      <div className="community-layout">
        <section className="community-feed" aria-label="Community discussions">
          <div className="community-feed-toolbar">
            <div className="community-feed-title">
              <MessageSquare size={18} />
              <h2>Discussions</h2>
              <span className="community-count">{feed.count}</span>
            </div>
            <div className="community-feed-tools">
              <label className="community-search">
                <Search size={16} aria-hidden="true" />
                <ValidatedInput
                  aria-label="Filter this page"
                  type="search"
                  placeholder="Search this page…"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                />
              </label>
              <button
                type="button"
                className="community-icon-button"
                aria-label="Refresh discussions"
                title="Refresh discussions"
                disabled={feedback.busy}
                onClick={() => void feedback.run(() => load())}
              >
                <RefreshCw size={16} />
              </button>
            </div>
          </div>
          {loading && (
            <div className="community-empty" role="status">
              <MessageSquare size={26} />
              <h3>Loading discussions…</h3>
            </div>
          )}
          {!loading && !posts.length && (
            <div className="community-empty">
              <MessageSquare size={28} />
              <h3>No discussions to show.</h3>
              <p>
                {search
                  ? "Try a different search on this page."
                  : "Be the first to share a question or something you have learned."}
              </p>
              {!search && (
                <button
                  type="button"
                  className="button secondary small"
                  onClick={() => setComposing(true)}
                >
                  Start a discussion <ArrowUpRight size={15} />
                </button>
              )}
            </div>
          )}
          <div className="community-posts">
            {posts.map((post) => (
              <article
                key={post.id}
                className={`community-post${post.pinned ? " is-pinned" : ""}`}
              >
                {post.pinned && (
                  <div className="community-pinned">
                    <Pin size={12} /> Pinned discussion
                  </div>
                )}
                <header className="community-post-header">
                  <span className="community-avatar" aria-hidden="true">
                    {post.author.trim().slice(0, 2).toUpperCase() || "M"}
                  </span>
                  <div className="community-author">
                    <strong>{post.author}</strong>
                    <time
                      dateTime={post.created_at}
                      title={when(post.created_at)}
                    >
                      {new Date(post.created_at).toLocaleDateString(undefined, {
                        month: "short",
                        day: "numeric",
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </time>
                  </div>
                  {(post.can_edit || post.can_pin || post.can_delete) && (
                    <details className="community-post-menu">
                      <summary
                        aria-label={`Discussion actions by ${post.author}`}
                      >
                        <MoreHorizontal size={19} />
                      </summary>
                      <div>
                        {post.can_edit && (
                          <button
                            type="button"
                            onClick={(event) => {
                              event.currentTarget
                                .closest("details")
                                ?.removeAttribute("open");
                              setEdit({ ...post });
                            }}
                          >
                            Edit post
                          </button>
                        )}
                        {post.can_pin && (
                          <button
                            type="button"
                            disabled={feedback.busy}
                            onClick={(event) => {
                              event.currentTarget
                                .closest("details")
                                ?.removeAttribute("open");
                              void feedback.run(async () =>
                                replace(
                                  await api<Post>(
                                    `/api/community/${post.id}/`,
                                    "PATCH",
                                    { pinned: !post.pinned },
                                  ),
                                ),
                              );
                            }}
                          >
                            {post.pinned ? "Unpin" : "Pin"}
                          </button>
                        )}
                        {post.can_delete && (
                          <button
                            type="button"
                            className="community-delete"
                            disabled={feedback.busy}
                            onClick={async (event) => {
                              event.currentTarget
                                .closest("details")
                                ?.removeAttribute("open");
                              if (
                                await confirm(
                                  "Delete this discussion and its replies?",
                                )
                              )
                                void feedback.run(async () => {
                                  await api(
                                    `/api/community/${post.id}/`,
                                    "DELETE",
                                  );
                                  await load();
                                }, "Discussion deleted.");
                            }}
                          >
                            Delete post
                          </button>
                        )}
                      </div>
                    </details>
                  )}
                </header>
                <p className="community-post-body">{post.body}</p>
                <footer className="community-post-footer">
                  <div className="community-reactions">
                    {([1, -1] as const).map((value) => (
                      <button
                        key={value}
                        type="button"
                        className="community-reaction"
                        disabled={feedback.busy}
                        aria-label={
                          value === 1
                            ? `Like (${post.likes})`
                            : `Dislike (${post.dislikes})`
                        }
                        aria-pressed={post.my_vote === value}
                        onClick={() =>
                          void feedback.run(async () =>
                            replace(
                              await api<Post>(
                                `/api/community/${post.id}/reaction/`,
                                "POST",
                                { value: post.my_vote === value ? 0 : value },
                              ),
                            ),
                          )
                        }
                      >
                        {value === 1 ? (
                          <ThumbsUp size={15} />
                        ) : (
                          <ThumbsDown size={15} />
                        )}
                        <span>{value === 1 ? post.likes : post.dislikes}</span>
                      </button>
                    ))}
                  </div>
                  <button
                    type="button"
                    className="community-replies"
                    disabled={feedback.busy}
                    aria-label={`Replies (${post.reply_count})`}
                    aria-expanded={thread?.id === post.id}
                    onClick={() =>
                      thread?.id === post.id
                        ? closeThread()
                        : void feedback.run(() => openThread(post))
                    }
                  >
                    <MessageSquare size={16} />
                    {post.reply_count}{" "}
                    {post.reply_count === 1 ? "reply" : "replies"}
                    <ArrowUpRight size={14} />
                  </button>
                </footer>
                {thread?.id === post.id && (
                  <CommunityThread
                    key={post.id}
                    replies={replies}
                    count={replyCount}
                    loading={threadLoading}
                    busy={feedback.busy}
                    hasMore={replyPage * 50 < replyCount}
                    onClose={closeThread}
                    onLoadMore={() =>
                      void feedback.run(() => openThread(post, replyPage + 1))
                    }
                    onSubmit={async (text, parentId) => {
                      const created = await feedback.run(
                        () =>
                          api<Reply>(
                            `/api/community/${post.id}/replies/`,
                            "POST",
                            {
                              body: text,
                              ...(parentId ? { parent_id: parentId } : {}),
                            },
                          ),
                        "Reply posted.",
                      );
                      if (!created) return false;
                      setReplies((rows) => [...rows, created]);
                      setReplyCount((count) => count + 1);
                      setFeed((current) => ({
                        ...current,
                        results: current.results.map((item) =>
                          item.id === post.id
                            ? { ...item, reply_count: item.reply_count + 1 }
                            : item,
                        ),
                      }));
                      return true;
                    }}
                    onDelete={async (reply) => {
                      if (
                        await confirm(
                          "Delete this reply? Replies from other members will remain.",
                        )
                      )
                        await feedback.run(async () => {
                          await api(
                            `/api/community/${post.id}/replies/${reply.id}/`,
                            "DELETE",
                          );
                          await openThread(post);
                          await load();
                        });
                    }}
                  />
                )}
              </article>
            ))}
          </div>
          <nav
            className="community-pagination"
            aria-label="Discussion pagination"
          >
            <span>
              Page {page} of {Math.max(1, Math.ceil(feed.count / 30))}
            </span>
            <div>
              <button
                type="button"
                className="community-page-button"
                aria-label="Previous discussions"
                disabled={page <= 1 || feedback.busy}
                onClick={() => setPage((value) => value - 1)}
              >
                <ArrowLeft size={15} /> Previous
              </button>
              <button
                type="button"
                className="community-page-button"
                aria-label="Next discussions"
                disabled={page * 30 >= feed.count || feedback.busy}
                onClick={() => setPage((value) => value + 1)}
              >
                Next <ArrowRight size={15} />
              </button>
            </div>
          </nav>
        </section>
        <aside className="community-sidebar" aria-label="Community resources">
          <section className="community-assistant">
            <span className="community-assistant-icon">
              <Sparkles size={21} />
            </span>
            <h2>Find your next answer.</h2>
            <p>Search shared discussions with the community assistant.</p>
            <ValidatedForm
              className="community-assistant-form"
              onSubmit={(event) => {
                event.preventDefault();
                void feedback.run(async () => {
                  const result = await api<{
                    answer: string;
                    sources: Source[];
                  }>("/api/community/assistant/", "POST", { question });
                  setAnswer(result.answer);
                  setSources(result.sources);
                });
              }}
            >
              <label>
                <span>Ask the community assistant</span>
                <ValidatedTextarea
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                  required
                  maxLength={1000}
                  rows={3}
                  placeholder="How do I set up my first workflow?"
                />
              </label>
              <button className="button secondary" disabled={feedback.busy}>
                <Search size={15} /> Search discussions
              </button>
            </ValidatedForm>
            {answer && (
              <div className="community-answer" role="status">
                <span>
                  <Sparkles size={13} /> From the community
                </span>
                <p>{answer}</p>
              </div>
            )}
            {sources.length > 0 && (
              <div className="community-sources">
                <h3>Source discussions</h3>
                {sources.map((source) => (
                  <button
                    key={source.post_id}
                    type="button"
                    onClick={() =>
                      void feedback.run(async () => {
                        const post = await api<Post>(
                          `/api/community/${source.post_id}/`,
                        );
                        await openThread(post);
                      })
                    }
                  >
                    <MessageSquare size={14} />
                    <span>{source.excerpt}</span>
                    <ArrowUpRight size={14} />
                  </button>
                ))}
              </div>
            )}
          </section>
          <section className="community-guidelines">
            <h2>A space to build together.</h2>
            <p>
              Share useful details, be generous with what you know, and keep
              customer information private.
            </p>
            <div>
              <ShieldCheck size={17} />
              <p>
                Posts and replies are shared with all signed-in Instantlify
                members, across workspaces.
              </p>
            </div>
          </section>
          <a href="/api/community/me/export/" className="community-export">
            <Download size={15} /> Export my community contributions
          </a>
        </aside>
      </div>
      {composing && (
        <Modal title="Start a discussion" onClose={() => setComposing(false)}>
          <ValidatedForm
            className="community-composer form-grid"
            onSubmit={(event) => {
              event.preventDefault();
              void feedback.run(async () => {
                await api("/api/community/", "POST", { body });
                setBody("");
                setComposing(false);
                if (page !== 1) setPage(1);
                else await load();
              }, "Discussion posted.");
            }}
          >
            <p>
              Ask a clear question or share something that helped you build.
            </p>
            <label>
              Your post
              <ValidatedTextarea
                value={body}
                onChange={(event) => setBody(event.target.value)}
                maxLength={8000}
                required
                rows={7}
                placeholder="What would you like to discuss?"
              />
            </label>
            <div className="community-composer-footer">
              <span>{body.length.toLocaleString()} / 8,000</span>
              <button
                className="button primary"
                disabled={feedback.busy || !body.trim()}
              >
                Post discussion <ArrowUpRight size={16} />
              </button>
            </div>
          </ValidatedForm>
        </Modal>
      )}
      {edit && (
        <Modal title="Edit discussion" onClose={() => setEdit(null)}>
          <ValidatedForm
            className="form-grid"
            onSubmit={(event) => {
              event.preventDefault();
              void feedback.run(async () => {
                replace(
                  await api<Post>(`/api/community/${edit.id}/`, "PATCH", {
                    body: edit.body,
                  }),
                );
                setEdit(null);
              }, "Discussion updated.");
            }}
          >
            <label>
              Post text
              <ValidatedTextarea
                value={edit.body}
                maxLength={8000}
                required
                rows={6}
                onChange={(event) =>
                  setEdit({ ...edit, body: event.target.value })
                }
              />
            </label>
            <button className="button primary" disabled={feedback.busy}>
              Save discussion
            </button>
          </ValidatedForm>
        </Modal>
      )}
    </div>
  );
}
