"use client";

import { useRef, useState } from "react";
import { CornerDownRight, Send, X } from "lucide-react";
import { when } from "@/lib/api";
import { ValidatedForm, ValidatedTextarea } from "./validated-form";

export type ThreadReply = {
  id: string;
  parent_id?: string | null;
  author: string;
  body: string;
  created_at: string;
  can_delete: boolean;
};
type Props = {
  replies: ThreadReply[];
  count: number;
  loading: boolean;
  busy: boolean;
  hasMore: boolean;
  onClose: () => void;
  onLoadMore: () => void;
  onSubmit: (body: string, parentId?: string) => Promise<boolean>;
  onDelete: (reply: ThreadReply) => Promise<void>;
};

export function CommunityThread({
  replies,
  count,
  loading,
  busy,
  hasMore,
  onClose,
  onLoadMore,
  onSubmit,
  onDelete,
}: Props) {
  const [text, setText] = useState("");
  const [target, setTarget] = useState<ThreadReply | null>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  function branch(parent: string | null, depth = 0): React.ReactNode {
    return replies
      .filter(
        (reply) =>
          (reply.parent_id || null) === parent ||
          (!parent &&
            reply.parent_id &&
            !replies.some((item) => item.id === reply.parent_id)),
      )
      .map((reply) => (
        <li key={reply.id} className="community-thread-item">
          <div className="community-thread-row">
            <span className="community-avatar" aria-hidden="true">
              {reply.author.trim().slice(0, 2).toUpperCase() || "M"}
            </span>
            <div className="community-thread-content">
              <div className="community-thread-meta">
                <strong>{reply.author}</strong>
                <time
                  dateTime={reply.created_at}
                  title={when(reply.created_at)}
                >
                  {new Date(reply.created_at).toLocaleDateString(undefined, {
                    month: "short",
                    day: "numeric",
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </time>
              </div>
              <p>{reply.body}</p>
              <div className="community-thread-actions">
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => {
                    setTarget(reply);
                    input.current?.focus();
                  }}
                  aria-label={`Reply to ${reply.author}`}
                >
                  <CornerDownRight size={13} /> Reply
                </button>
                {reply.can_delete && (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void onDelete(reply)}
                  >
                    Delete reply
                  </button>
                )}
              </div>
            </div>
          </div>
          {replies.some((item) => item.parent_id === reply.id) && (
            <ol
              className={`community-thread-branch${depth >= 3 ? " depth-limit" : ""}`}
            >
              {branch(reply.id, depth + 1)}
            </ol>
          )}
        </li>
      ));
  }
  return (
    <section className="community-thread" aria-label="Discussion replies">
      <header>
        <span>
          {count} {count === 1 ? "reply" : "replies"}
        </span>
        <button type="button" onClick={onClose} aria-label="Hide replies">
          <X size={15} /> Hide replies
        </button>
      </header>
      {loading && !replies.length && (
        <p role="status" className="community-thread-empty">
          Loading replies…
        </p>
      )}
      {!loading && !replies.length && (
        <p className="community-thread-empty">
          No replies yet. Start the conversation.
        </p>
      )}
      <ol className="community-thread-list">{branch(null)}</ol>
      {hasMore && (
        <button
          type="button"
          className="community-thread-more"
          disabled={busy || loading}
          onClick={onLoadMore}
        >
          {loading ? "Loading replies…" : "View more replies"}
        </button>
      )}
      <ValidatedForm
        className="community-thread-composer"
        onSubmit={(event) => {
          event.preventDefault();
          void onSubmit(text, target?.id).then((saved) => {
            if (saved) {
              setText("");
              setTarget(null);
            }
          });
        }}
      >
        {target && (
          <div className="community-reply-target">
            <CornerDownRight size={13} /> Replying to {target.author}
            <button
              type="button"
              aria-label="Cancel reply target"
              onClick={() => setTarget(null)}
            >
              <X size={13} />
            </button>
          </div>
        )}
        <ValidatedTextarea
          ref={input}
          aria-label="Your reply"
          required
          maxLength={8000}
          rows={2}
          value={text}
          placeholder={
            target ? `Reply to ${target.author}…` : "Add to the conversation…"
          }
          onChange={(event) => setText(event.target.value)}
        />
        <div>
          <span>Keep it helpful and respectful.</span>
          <button
            className="button primary small"
            disabled={busy || !text.trim()}
          >
            <Send size={14} /> Post reply
          </button>
        </div>
      </ValidatedForm>
    </section>
  );
}
