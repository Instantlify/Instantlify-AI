"use client";

import { useConfirmation } from "@/components/confirmation-provider";

import {
  ValidatedForm,
  ValidatedInput,
  ValidatedSelect,
  ValidatedTextarea,
} from "@/components/validated-form";

import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type FormEvent,
} from "react";
import { CalendarDays, ChevronLeft, ChevronRight, Plus } from "lucide-react";
import {
  api,
  when,
  type Connection,
  type Page,
  type ScheduledPost,
} from "@/lib/api";
import { useWorkspace } from "@/lib/workspace";
import {
  Empty,
  ErrorNotice,
  Modal,
  PageHeading,
  Panel,
  Pill,
  statusTone,
  SuccessNotice,
  useFeedback,
} from "@/components/ui";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

/** Local wall-clock value for a datetime-local input. */
function toLocalInput(value: string | Date) {
  const date = typeof value === "string" ? new Date(value) : value;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

const sameDay = (a: Date, b: Date) =>
  a.getFullYear() === b.getFullYear() &&
  a.getMonth() === b.getMonth() &&
  a.getDate() === b.getDate();

export default function CalendarPage() {
  const { prefix, manager } = useWorkspace();
  const [posts, setPosts] = useState<ScheduledPost[]>([]);
  const [connections, setConnections] = useState<Connection[]>([]);
  const [loading, setLoading] = useState(true);
  const [month, setMonth] = useState(() => {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), 1);
  });
  const [selected, setSelected] = useState<ScheduledPost | null>(null);
  const confirm = useConfirmation();
  const feedback = useFeedback();

  const load = useCallback(
    async (signal?: AbortSignal) => {
      const [postPage, connectionPage] = await Promise.all([
        api<Page<ScheduledPost>>(`${prefix}/posts/`, "GET", undefined, signal),
        api<Page<Connection>>(
          `${prefix}/connections/`,
          "GET",
          undefined,
          signal,
        ),
      ]);
      setPosts(postPage.results);
      setConnections(
        connectionPage.results.filter(
          (item) => item.provider === "instagram" && item.status === "active",
        ),
      );
    },
    [prefix],
  );

  useEffect(() => {
    const controller = new AbortController();
    // Deferred so state updates happen in a callback, not the effect body.
    const initial = window.setTimeout(() => {
      load(controller.signal)
        .catch((err) => {
          if (!controller.signal.aborted)
            feedback.setError(String((err as Error).message));
        })
        .finally(() => {
          if (!controller.signal.aborted) setLoading(false);
        });
    }, 0);
    const timer = window.setInterval(
      () => load().catch(() => undefined),
      30000,
    );
    return () => {
      controller.abort();
      window.clearTimeout(initial);
      window.clearInterval(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [load]);

  const days = useMemo(() => {
    const first = new Date(month.getFullYear(), month.getMonth(), 1);
    const offset = (first.getDay() + 6) % 7; // Monday-first grid
    const count = new Date(
      month.getFullYear(),
      month.getMonth() + 1,
      0,
    ).getDate();
    const cells: (Date | null)[] = [];
    for (let i = 0; i < offset; i += 1) cells.push(null);
    for (let day = 1; day <= count; day += 1)
      cells.push(new Date(month.getFullYear(), month.getMonth(), day));
    while (cells.length % 7) cells.push(null);
    return cells;
  }, [month]);

  const upcoming = useMemo(
    () =>
      posts
        .filter((post) => new Date(post.scheduled_at) >= new Date())
        .sort(
          (a, b) =>
            new Date(a.scheduled_at).getTime() -
            new Date(b.scheduled_at).getTime(),
        )
        .slice(0, 20),
    [posts],
  );

  async function schedule(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = Object.fromEntries(new FormData(form)) as Record<
      string,
      string
    >;
    const created = await feedback.run(
      () =>
        api<ScheduledPost>(`${prefix}/posts/`, "POST", {
          connection: data.connection,
          caption: data.caption,
          media_url: data.media_url,
          media_type: data.media_type,
          scheduled_at: new Date(data.scheduled_at).toISOString(),
        }),
      "Post scheduled.",
    );
    if (created) {
      form.reset();
      setPosts((list) => [...list, created]);
    }
  }

  async function edit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    const data = Object.fromEntries(
      new FormData(event.currentTarget),
    ) as Record<string, string>;
    const updated = await feedback.run(
      () =>
        api<ScheduledPost>(`${prefix}/posts/${selected.id}/`, "PATCH", {
          caption: data.caption,
          media_url: data.media_url,
          media_type: data.media_type,
          scheduled_at: new Date(data.scheduled_at).toISOString(),
        }),
      "Post updated.",
    );
    if (updated) {
      setPosts((list) =>
        list.map((item) => (item.id === updated.id ? updated : item)),
      );
      setSelected(null);
    }
  }

  async function cancel() {
    if (!selected || !await confirm("Cancel this scheduled post?")) return;
    const id = selected.id;
    const done = await feedback.run(
      () => api(`${prefix}/posts/${id}/`, "DELETE"),
      "Post cancelled.",
    );
    if (done !== undefined || !feedback.error) {
      setPosts((list) =>
        list.map((item) =>
          item.id === id ? { ...item, status: "cancelled" } : item,
        ),
      );
      setSelected(null);
    }
  }

  const today = new Date();
  const monthLabel = month.toLocaleDateString(undefined, {
    month: "long",
    year: "numeric",
  });

  return (
    <>
      <PageHeading
        eyebrow="Content calendar"
        title="Plan what you post."
        text="Schedule your own Instagram feed posts. Instantlify publishes them for you at the chosen time."
      />
      <ErrorNotice error={feedback.error} />
      <SuccessNotice notice={feedback.notice} />
      {loading ? (
        <p className="loading-text">Loading your calendar…</p>
      ) : (
        <div className="stack">
          <Panel
            title={monthLabel}
            aside={
              <span className="row">
                <button
                  className="icon-button"
                  aria-label="Previous month"
                  onClick={() =>
                    setMonth(
                      new Date(month.getFullYear(), month.getMonth() - 1, 1),
                    )
                  }
                >
                  <ChevronLeft size={16} />
                </button>
                <button
                  className="text-button"
                  onClick={() =>
                    setMonth(new Date(today.getFullYear(), today.getMonth(), 1))
                  }
                >
                  Today
                </button>
                <button
                  className="icon-button"
                  aria-label="Next month"
                  onClick={() =>
                    setMonth(
                      new Date(month.getFullYear(), month.getMonth() + 1, 1),
                    )
                  }
                >
                  <ChevronRight size={16} />
                </button>
              </span>
            }
          >
            <div className="calendar-grid" role="grid" aria-label={monthLabel}>
              {DAYS.map((day) => (
                <span key={day} className="muted-text small">
                  {day}
                </span>
              ))}
              {days.map((day, index) =>
                day ? (
                  <div
                    key={day.toISOString()}
                    className={`calendar-day ${sameDay(day, today) ? "today" : ""}`}
                    role="gridcell"
                  >
                    <strong>{day.getDate()}</strong>
                    {posts
                      .filter((post) =>
                        sameDay(new Date(post.scheduled_at), day),
                      )
                      .map((post) => (
                        <button
                          key={post.id}
                          className={`calendar-post pill-${statusTone(post.status)}`}
                          onClick={() => setSelected(post)}
                          title={post.caption || "Post"}
                        >
                          {new Date(post.scheduled_at).toLocaleTimeString([], {
                            hour: "2-digit",
                            minute: "2-digit",
                          })}{" "}
                          {post.caption || "Post"}
                        </button>
                      ))}
                  </div>
                ) : (
                  <div key={`empty-${index}`} aria-hidden="true" />
                ),
              )}
            </div>
          </Panel>

          <div className="two-col">
            <Panel title="Schedule a post">
              {connections.length === 0 ? (
                <Empty>
                  Connect a live Instagram account first. Scheduling needs an
                  active Instagram connection.
                </Empty>
              ) : !manager ? (
                <Empty>Owners and admins schedule posts.</Empty>
              ) : (
                <ValidatedForm fieldErrors={feedback.fieldErrors} validationTarget={feedback.validationTarget} onEdit={() => feedback.setError("")} className="form-grid" onSubmit={schedule}>
                  <label>
                    Account
                    <ValidatedSelect name="connection" required>
                      {connections.map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.display_name}
                        </option>
                      ))}
                    </ValidatedSelect>
                  </label>
                  <label>
                    Caption
                    <ValidatedTextarea
                      name="caption"
                      maxLength={2200}
                      placeholder="What do you want to say?"
                    />
                    <span className="hint">Up to 2,200 characters.</span>
                  </label>
                  <label>
                    Media URL
                    <ValidatedInput
                      name="media_url"
                      type="url"
                      pattern="https://.*"
                      placeholder="https://cdn.example.com/photo.jpg"
                      required
                    />
                    <span className="hint">
                      A public HTTPS link to the image or video.
                    </span>
                  </label>
                  <label>
                    Media type
                    <ValidatedSelect name="media_type" defaultValue="image">
                      <option value="image">Image</option>
                      <option value="video">Video (Reel)</option>
                    </ValidatedSelect>
                  </label>
                  <label>
                    Publish at
                    <ValidatedInput
                      name="scheduled_at"
                      type="datetime-local"
                      min={toLocalInput(new Date())}
                      required
                    />
                  </label>
                  <div className="form-actions">
                    <button className="button primary" disabled={feedback.busy}>
                      {feedback.busy ? "Scheduling…" : "Schedule post"}
                      <Plus size={16} />
                    </button>
                  </div>
                </ValidatedForm>
              )}
            </Panel>
            <Panel title="Upcoming" aside={`${upcoming.length} scheduled`}>
              {upcoming.length === 0 ? (
                <Empty>Nothing scheduled yet.</Empty>
              ) : (
                <div>
                  {upcoming.map((post) => (
                    <div className="list-row" key={post.id}>
                      <CalendarDays size={15} className="subtle" />
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <strong>{post.caption || "Post"}</strong>
                        <div className="muted-text">
                          {when(post.scheduled_at)} · {post.media_type}
                        </div>
                      </div>
                      <Pill tone={statusTone(post.status)}>{post.status}</Pill>
                      <button
                        className="text-button"
                        onClick={() => setSelected(post)}
                      >
                        Details
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </Panel>
          </div>
        </div>
      )}

      {selected && (
        <Modal title="Scheduled post" onClose={() => setSelected(null)}>
          <div className="lead-panel">
            <div className="row">
              <Pill tone={statusTone(selected.status)}>{selected.status}</Pill>
              <span className="muted-text">
                {selected.attempts} attempt{selected.attempts === 1 ? "" : "s"}
              </span>
            </div>
            <dl>
              <dt>Media</dt>
              <dd>
                <a
                  href={selected.media_url}
                  target="_blank"
                  rel="noreferrer noopener"
                  className="mono"
                >
                  {selected.media_url}
                </a>
              </dd>
              <dt>Type</dt>
              <dd>{selected.media_type}</dd>
              <dt>Scheduled</dt>
              <dd>{when(selected.scheduled_at)}</dd>
              {selected.published_at && (
                <>
                  <dt>Published</dt>
                  <dd>{when(selected.published_at)}</dd>
                </>
              )}
              {selected.provider_post_id && (
                <>
                  <dt>Post ID</dt>
                  <dd className="mono">{selected.provider_post_id}</dd>
                </>
              )}
              {selected.error_code && (
                <>
                  <dt>Error</dt>
                  <dd className="mono">{selected.error_code}</dd>
                </>
              )}
            </dl>
          </div>
          {selected.status === "scheduled" && manager ? (
            <ValidatedForm fieldErrors={feedback.fieldErrors} validationTarget={feedback.validationTarget} onEdit={() => feedback.setError("")}
              className="form-grid"
              onSubmit={edit}
              style={{ marginTop: 18 }}
            >
              <label>
                Caption
                <ValidatedTextarea
                  name="caption"
                  maxLength={2200}
                  defaultValue={selected.caption}
                />
              </label>
              <label>
                Media URL
                <ValidatedInput
                  name="media_url"
                  type="url"
                  pattern="https://.*"
                  defaultValue={selected.media_url}
                  required
                />
              </label>
              <label>
                Media type
                <ValidatedSelect name="media_type" defaultValue={selected.media_type}>
                  <option value="image">Image</option>
                  <option value="video">Video (Reel)</option>
                </ValidatedSelect>
              </label>
              <label>
                Publish at
                <ValidatedInput
                  name="scheduled_at"
                  type="datetime-local"
                  defaultValue={toLocalInput(selected.scheduled_at)}
                  required
                />
              </label>
              <div className="form-actions">
                <button className="button primary" disabled={feedback.busy}>
                  {feedback.busy ? "Saving…" : "Save changes"}
                </button>
                <button
                  type="button"
                  className="button danger"
                  disabled={feedback.busy}
                  onClick={cancel}
                >
                  Cancel post
                </button>
              </div>
            </ValidatedForm>
          ) : (
            <p className="muted-text" style={{ marginTop: 14 }}>
              {selected.caption || "No caption."}
            </p>
          )}
        </Modal>
      )}
    </>
  );
}
