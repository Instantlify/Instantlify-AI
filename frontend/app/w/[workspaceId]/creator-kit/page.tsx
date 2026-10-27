"use client";

import {
  ValidatedForm,
  ValidatedInput,
  ValidatedTextarea,
} from "@/components/validated-form";

import { useEffect, useState } from "react";
import { ExternalLink, Plus, Save, Trash2 } from "lucide-react";
import { api, apiPages, message, when, type Connection } from "@/lib/api";
import type { CreatorKit } from "@/lib/portal-tools";
import { useWorkspace } from "@/lib/workspace";
import {
  ErrorNotice,
  PageHeading,
  Panel,
  SuccessNotice,
  useFeedback,
} from "@/components/ui";

export default function CreatorKitPage() {
  const { prefix, workspace, manager } = useWorkspace();
  const [kit, setKit] = useState<CreatorKit>({
    slug: "",
    name: workspace.name,
    headline: "",
    bio: "",
    contact_email: "",
    published: false,
    links: [],
    statistics: [],
    services: [],
  });
  const [loaded, setLoaded] = useState(false);
  const [connections, setConnections] = useState<Connection[]>([]);
  const feedback = useFeedback();
  useEffect(() => {
    const controller = new AbortController();
    apiPages<Connection>(`${prefix}/connections/`, controller.signal)
      .then(setConnections)
      .catch((error) => {
        if (!controller.signal.aborted) feedback.setError(message(error));
      });
    api<CreatorKit | null>(
      `${prefix}/creator-kit/`,
      "GET",
      undefined,
      controller.signal,
    )
      .then((value) => {
        if (value) setKit(value);
      })
      .catch((e) => {
        if (!controller.signal.aborted) feedback.setError(message(e));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoaded(true);
      });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefix]);
  const liveEnabled = Boolean(kit.live_connection_ids?.length);
  useEffect(() => {
    if (!liveEnabled) return;
    const controller = new AbortController();
    const timer = window.setInterval(() => {
      api<CreatorKit | null>(
        `${prefix}/creator-kit/`,
        "GET",
        undefined,
        controller.signal,
      )
        .then((data) => {
          if (data)
            setKit((current) => ({
              ...current,
              live_statistics: data.live_statistics,
              live_stats_error: data.live_stats_error,
              live_stats_checked_at: data.live_stats_checked_at,
            }));
        })
        .catch(() => {});
    }, 30000);
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, [prefix, liveEnabled]);
  return (
    <>
      <PageHeading
        eyebrow="Apps / Creator kit"
        title="Your next collaboration starts here"
        text="Publish a concise media kit with your work, audience figures and collaboration offers."
        action={
          kit.published ? (
            <a
              className="button secondary"
              href={`/c/${kit.slug}`}
              target="_blank"
              rel="noreferrer"
            >
              <ExternalLink size={15} /> Open public kit
            </a>
          ) : undefined
        }
      />
      <ErrorNotice error={feedback.error} />
      <SuccessNotice notice={feedback.notice} />
      {!loaded ? (
        <p>Loading creator kit…</p>
      ) : (
        <ValidatedForm fieldErrors={feedback.fieldErrors} validationTarget={feedback.validationTarget} onEdit={() => feedback.setError("")}
          className="form-grid"
          style={{ maxWidth: 760 }}
          onSubmit={(e) => {
            e.preventDefault();
            void feedback.run(async () => {
              setKit(
                await api<CreatorKit>(`${prefix}/creator-kit/`, "PUT", kit),
              );
            }, "Creator kit saved.");
          }}
        >
          <Panel title="Introduce yourself">
            <div className="form-grid">
              <label>
                Public address
                <ValidatedInput name="slug"
                  required
                  pattern="[a-z0-9_\-]+"
                  maxLength={80}
                  value={kit.slug}
                  onChange={(e) => setKit({ ...kit, slug: e.target.value })}
                  placeholder="your-name"
                />
              </label>
              <label>
                Name
                <ValidatedInput name="name"
                  required
                  maxLength={120}
                  value={kit.name}
                  onChange={(e) => setKit({ ...kit, name: e.target.value })}
                />
              </label>
              <label>
                Headline
                <ValidatedInput name="headline"
                  maxLength={200}
                  value={kit.headline}
                  onChange={(e) => setKit({ ...kit, headline: e.target.value })}
                  placeholder="Food creator and storyteller"
                />
              </label>
              <label>
                About you
                <ValidatedTextarea name="bio"
                  rows={5}
                  maxLength={2000}
                  value={kit.bio}
                  onChange={(e) => setKit({ ...kit, bio: e.target.value })}
                />
              </label>
              <label>
                Public contact email
                <ValidatedInput name="contact_email"
                  type="email"
                  maxLength={254}
                  value={kit.contact_email}
                  onChange={(e) =>
                    setKit({ ...kit, contact_email: e.target.value })
                  }
                />
                <small>This address appears on your published kit.</small>
              </label>
            </div>
          </Panel>
          <Panel title="Connected account statistics" aside="Provider-sourced">
            <p>
              Select Instagram accounts to automatically refresh follower counts
              every hour. Selected account names and counts appear on your
              published kit. Save the kit to apply changes.
            </p>
            <div className="form-grid">
              {connections
                .filter(
                  (connection) =>
                    connection.provider === "instagram" && !connection.is_test,
                )
                .map((connection) => {
                  const selected = (kit.live_connection_ids || []).includes(
                    connection.id,
                  );
                  return (
                    <label className="inline" key={connection.id}>
                      <ValidatedInput
                        type="checkbox"
                        checked={selected}
                        disabled={
                          !manager ||
                          (!selected &&
                            (connection.status !== "active" ||
                              connection.locked))
                        }
                        onChange={(event) =>
                          setKit({
                            ...kit,
                            live_connection_ids: event.target.checked
                              ? [
                                  ...(kit.live_connection_ids || []),
                                  connection.id,
                                ]
                              : (kit.live_connection_ids || []).filter(
                                  (id) => id !== connection.id,
                                ),
                          })
                        }
                      />{" "}
                      {connection.display_name}
                      {connection.status !== "active"
                        ? " · Reconnect required"
                        : ""}
                    </label>
                  );
                })}
              {!connections.some(
                (connection) =>
                  connection.provider === "instagram" && !connection.is_test,
              ) && (
                <p>
                  Connect an Instagram account in Integrations to use automatic
                  follower statistics.
                </p>
              )}
              {liveEnabled && (
                <button
                  type="button"
                  className="button secondary small"
                  disabled={!manager}
                  onClick={() => setKit({ ...kit, live_connection_ids: [] })}
                >
                  Stop publishing connected statistics
                </button>
              )}
              {kit.live_statistics?.map((row, index) => (
                <p key={index}>
                  <strong>{row.account}</strong> · {row.value} {row.label} · As
                  of {when(row.as_of)}
                </p>
              ))}
              {kit.live_stats_error && (
                <p role="alert">
                  The last statistics refresh could not finish. Check your
                  account connection and plan. Previously fetched values keep
                  their original timestamp.
                </p>
              )}
            </div>
          </Panel>
          <Panel title="Additional audience figures" aside="Entered by you">
            <p className="muted-text">
              Use current figures from your channel analytics. These are
              labelled as creator-provided on the public page.
            </p>
            <div className="form-grid">
              {kit.statistics.map((row, index) => (
                <div key={index} className="row">
                  <label>
                    Metric
                    <ValidatedInput name="label"
                      required
                      maxLength={250}
                      value={row.label}
                      onChange={(e) =>
                        setKit({
                          ...kit,
                          statistics: kit.statistics.map((item, i) =>
                            i === index
                              ? { ...item, label: e.target.value }
                              : item,
                          ),
                        })
                      }
                      placeholder="Monthly reach"
                    />
                  </label>
                  <label>
                    Value
                    <ValidatedInput name="value"
                      required
                      maxLength={250}
                      value={row.value}
                      onChange={(e) =>
                        setKit({
                          ...kit,
                          statistics: kit.statistics.map((item, i) =>
                            i === index
                              ? { ...item, value: e.target.value }
                              : item,
                          ),
                        })
                      }
                      placeholder="120,000"
                    />
                  </label>
                  <button
                    type="button"
                    className="icon-button"
                    aria-label="Remove metric"
                    onClick={() =>
                      setKit({
                        ...kit,
                        statistics: kit.statistics.filter(
                          (_, i) => i !== index,
                        ),
                      })
                    }
                  >
                    <Trash2 size={15} />
                  </button>
                </div>
              ))}
              <button
                type="button"
                className="button secondary"
                disabled={kit.statistics.length >= 12}
                onClick={() =>
                  setKit({
                    ...kit,
                    statistics: [...kit.statistics, { label: "", value: "" }],
                  })
                }
              >
                <Plus size={14} /> Add metric
              </button>
            </div>
          </Panel>
          <Panel title="Work and social profiles">
            <div className="form-grid">
              {kit.links.map((row, index) => (
                <div key={index} className="form-grid">
                  <label>
                    Link label
                    <ValidatedInput name="label"
                      required
                      maxLength={250}
                      value={row.label}
                      onChange={(e) =>
                        setKit({
                          ...kit,
                          links: kit.links.map((item, i) =>
                            i === index
                              ? { ...item, label: e.target.value }
                              : item,
                          ),
                        })
                      }
                    />
                  </label>
                  <label>
                    HTTPS link
                    <ValidatedInput name="url"
                      type="url"
                      required
                      maxLength={2000}
                      value={row.url}
                      onChange={(e) =>
                        setKit({
                          ...kit,
                          links: kit.links.map((item, i) =>
                            i === index
                              ? { ...item, url: e.target.value }
                              : item,
                          ),
                        })
                      }
                    />
                  </label>
                  <button
                    type="button"
                    className="text-button"
                    onClick={() =>
                      setKit({
                        ...kit,
                        links: kit.links.filter((_, i) => i !== index),
                      })
                    }
                  >
                    Remove link
                  </button>
                </div>
              ))}
              <button
                type="button"
                className="button secondary"
                disabled={kit.links.length >= 12}
                onClick={() =>
                  setKit({
                    ...kit,
                    links: [...kit.links, { label: "", url: "https://" }],
                  })
                }
              >
                <Plus size={14} /> Add link
              </button>
            </div>
          </Panel>
          <Panel title="Collaboration offers">
            <div className="form-grid">
              {kit.services.map((row, index) => (
                <div className="form-grid" key={index}>
                  <label>
                    Offer title
                    <ValidatedInput name="title"
                      required
                      maxLength={250}
                      value={row.title}
                      onChange={(e) =>
                        setKit({
                          ...kit,
                          services: kit.services.map((item, i) =>
                            i === index
                              ? { ...item, title: e.target.value }
                              : item,
                          ),
                        })
                      }
                    />
                  </label>
                  <label>
                    Description
                    <ValidatedTextarea name="description"
                      required
                      maxLength={250}
                      value={row.description}
                      onChange={(e) =>
                        setKit({
                          ...kit,
                          services: kit.services.map((item, i) =>
                            i === index
                              ? { ...item, description: e.target.value }
                              : item,
                          ),
                        })
                      }
                    />
                  </label>
                  <button
                    type="button"
                    className="text-button"
                    onClick={() =>
                      setKit({
                        ...kit,
                        services: kit.services.filter((_, i) => i !== index),
                      })
                    }
                  >
                    Remove offer
                  </button>
                </div>
              ))}
              <button
                type="button"
                className="button secondary"
                disabled={kit.services.length >= 12}
                onClick={() =>
                  setKit({
                    ...kit,
                    services: [...kit.services, { title: "", description: "" }],
                  })
                }
              >
                <Plus size={14} /> Add offer
              </button>
            </div>
          </Panel>
          <label className="inline">
            <ValidatedInput
              type="checkbox"
              checked={kit.published}
              onChange={(e) => setKit({ ...kit, published: e.target.checked })}
            />{" "}
            Publish creator kit
          </label>
          <button
            className="button primary"
            disabled={!manager || feedback.busy}
          >
            <Save size={15} /> Save creator kit
          </button>
        </ValidatedForm>
      )}
    </>
  );
}
