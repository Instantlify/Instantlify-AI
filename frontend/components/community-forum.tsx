"use client";

import { useConfirmation } from "@/components/confirmation-provider";

import { useCallback, useEffect, useState } from "react";
import { api, message, when } from "@/lib/api";
import {
  ErrorNotice,
  SuccessNotice,
  Modal,
  PageHeading,
  Panel,
  Pill,
  useFeedback,
} from "./ui";
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
type Reply = {
  id: string;
  author: string;
  body: string;
  created_at: string;
  can_delete: boolean;
};
type Source = { post_id: string; excerpt: string };
type Feed = { count: number; results: Post[] };

export function CommunityForum() {
  const confirm = useConfirmation();
  const feedback = useFeedback();
  const [feed, setFeed] = useState<Feed>({ count: 0, results: [] });
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [body, setBody] = useState("");
  const [search, setSearch] = useState("");
  const [edit, setEdit] = useState<Post | null>(null);
  const [thread, setThread] = useState<Post | null>(null);
  const [replies, setReplies] = useState<Reply[]>([]);
  const [replyCount, setReplyCount] = useState(0);
  const [replyPage, setReplyPage] = useState(1);
  const [replyText, setReplyText] = useState("");
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
  async function openThread(post: Post, number = 1) {
    const result = await api<{ count: number; results: Reply[] }>(
      `/api/community/${post.id}/replies/?page=${number}`,
    );
    setThread(post);
    setReplies(result.results);
    setReplyCount(result.count);
    setReplyPage(number);
    setReplyText("");
  }
  const posts = feed.results.filter((post) =>
    `${post.author} ${post.body}`.toLowerCase().includes(search.toLowerCase()),
  );
  return (
    <>
      <PageHeading
        eyebrow="Apps / Community"
        title="Learn together"
        text="Posts and replies are shared with all signed-in Instantlify members, across workspaces."
      />
      <ErrorNotice error={feedback.error} />
      <SuccessNotice notice={feedback.notice} />
      <Panel title="Start a discussion">
        <ValidatedForm
          className="form-grid"
          onSubmit={(event) => {
            event.preventDefault();
            void feedback.run(async () => {
              await api("/api/community/", "POST", { body });
              setBody("");
              if (page !== 1) setPage(1);
              else await load();
            }, "Discussion posted.");
          }}
        >
          <label>
            Your post
            <ValidatedTextarea
              value={body}
              onChange={(event) => setBody(event.target.value)}
              maxLength={8000}
              required
              rows={4}
            />
          </label>
          <button className="button primary" disabled={feedback.busy}>
            Post discussion
          </button>
        </ValidatedForm>
      </Panel>
      <Panel title="Find an answer in the community">
        <ValidatedForm
          className="form-grid"
          onSubmit={(event) => {
            event.preventDefault();
            void feedback.run(async () => {
              const result = await api<{ answer: string; sources: Source[] }>(
                "/api/community/assistant/",
                "POST",
                { question },
              );
              setAnswer(result.answer);
              setSources(result.sources);
            });
          }}
        >
          <label>
            Ask the community assistant
            <ValidatedInput
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              required
              maxLength={1000}
            />
          </label>
          <button className="button secondary" disabled={feedback.busy}>
            Search discussions
          </button>
        </ValidatedForm>
        {answer && (
          <p role="status" style={{ whiteSpace: "pre-wrap" }}>
            {answer}
          </p>
        )}
        {sources.map((source) => (
          <button
            key={source.post_id}
            className="text-button"
            onClick={() =>
              void feedback.run(async () => {
                const post = await api<Post>(
                  `/api/community/${source.post_id}/`,
                );
                await openThread(post);
              })
            }
          >
            {source.excerpt}
          </button>
        ))}
      </Panel>
      <label>
        Filter this page
        <ValidatedInput
          type="search"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
      </label>
      {loading && <p role="status">Loading discussions…</p>}
      {!loading && !posts.length && <p>No discussions to show.</p>}
      {posts.map((post) => (
        <Panel
          key={post.id}
          title={post.author}
          aside={
            <span>
              {post.pinned && <Pill>Pinned</Pill>} {when(post.created_at)}
            </span>
          }
        >
          <p style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
            {post.body}
          </p>
          <div className="row" style={{ flexWrap: "wrap" }}>
            {([1, -1] as const).map((value) => (
              <button
                key={value}
                className="button secondary small"
                disabled={feedback.busy}
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
                {value === 1
                  ? `Like (${post.likes})`
                  : `Dislike (${post.dislikes})`}
              </button>
            ))}
            <button
              className="button secondary small"
              disabled={feedback.busy}
              onClick={() => void feedback.run(() => openThread(post))}
            >
              Replies ({post.reply_count})
            </button>
            {post.can_edit && (
              <button
                className="text-button"
                onClick={() => setEdit({ ...post })}
              >
                Edit post
              </button>
            )}
            {post.can_pin && (
              <button
                className="text-button"
                disabled={feedback.busy}
                onClick={() =>
                  void feedback.run(async () =>
                    replace(
                      await api<Post>(`/api/community/${post.id}/`, "PATCH", {
                        pinned: !post.pinned,
                      }),
                    ),
                  )
                }
              >
                {post.pinned ? "Unpin" : "Pin"}
              </button>
            )}
            {post.can_delete && (
              <button
                className="text-button"
                disabled={feedback.busy}
                onClick={async () => {
                  if (await confirm("Delete this discussion and its replies?"))
                    void feedback.run(async () => {
                      await api(`/api/community/${post.id}/`, "DELETE");
                      await load();
                    }, "Discussion deleted.");
                }}
              >
                Delete post
              </button>
            )}
          </div>
        </Panel>
      ))}
      <div className="row">
        <button
          className="button secondary"
          disabled={page <= 1}
          onClick={() => setPage((value) => value - 1)}
        >
          Previous discussions
        </button>
        <span>Page {page}</span>
        <button
          className="button secondary"
          disabled={page * 30 >= feed.count}
          onClick={() => setPage((value) => value + 1)}
        >
          Next discussions
        </button>
      </div>
      <a href="/api/community/me/export/" className="text-button">
        Export my community contributions
      </a>
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
      {thread && (
        <Modal title="Discussion replies" onClose={() => setThread(null)}>
          <p style={{ whiteSpace: "pre-wrap" }}>{thread.body}</p>
          {replies.map((reply) => (
            <article
              key={reply.id}
              className="card"
              style={{ padding: 12, marginBottom: 10 }}
            >
              <strong>{reply.author}</strong>
              <small> · {when(reply.created_at)}</small>
              <p style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
                {reply.body}
              </p>
              {reply.can_delete && (
                <button
                  className="text-button"
                  disabled={feedback.busy}
                  onClick={async () => {
                    if (await confirm("Delete this reply?"))
                      void feedback.run(async () => {
                        await api(
                          `/api/community/${thread.id}/replies/${reply.id}/`,
                          "DELETE",
                        );
                        await openThread(thread, replyPage);
                        await load();
                      });
                  }}
                >
                  Delete reply
                </button>
              )}
            </article>
          ))}
          <div className="row">
            <button
              className="text-button"
              disabled={replyPage <= 1}
              onClick={() =>
                void feedback.run(() => openThread(thread, replyPage - 1))
              }
            >
              Previous replies
            </button>
            <span>Page {replyPage}</span>
            <button
              className="text-button"
              disabled={replyPage * 50 >= replyCount}
              onClick={() =>
                void feedback.run(() => openThread(thread, replyPage + 1))
              }
            >
              Next replies
            </button>
          </div>
          <ValidatedForm
            className="form-grid"
            onSubmit={(event) => {
              event.preventDefault();
              void feedback.run(async () => {
                await api(`/api/community/${thread.id}/replies/`, "POST", {
                  body: replyText,
                });
                await openThread(thread, Math.floor(replyCount / 50) + 1);
                await load();
              }, "Reply posted.");
            }}
          >
            <label>
              Your reply
              <ValidatedTextarea
                required
                maxLength={8000}
                value={replyText}
                rows={3}
                onChange={(event) => setReplyText(event.target.value)}
              />
            </label>
            <button className="button primary" disabled={feedback.busy}>
              Post reply
            </button>
          </ValidatedForm>
        </Modal>
      )}
    </>
  );
}
