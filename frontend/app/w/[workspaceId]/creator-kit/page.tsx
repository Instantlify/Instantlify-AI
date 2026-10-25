"use client";

import { useEffect, useState } from "react";
import { ExternalLink, Plus, Save, Trash2 } from "lucide-react";
import { api, message } from "@/lib/api";
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
  const feedback = useFeedback();
  useEffect(() => {
    const controller = new AbortController();
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
        <form
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
                <input
                  required
                  pattern="[a-z0-9_-]+"
                  maxLength={80}
                  value={kit.slug}
                  onChange={(e) => setKit({ ...kit, slug: e.target.value })}
                  placeholder="your-name"
                />
              </label>
              <label>
                Name
                <input
                  required
                  maxLength={120}
                  value={kit.name}
                  onChange={(e) => setKit({ ...kit, name: e.target.value })}
                />
              </label>
              <label>
                Headline
                <input
                  maxLength={200}
                  value={kit.headline}
                  onChange={(e) => setKit({ ...kit, headline: e.target.value })}
                  placeholder="Food creator and storyteller"
                />
              </label>
              <label>
                About you
                <textarea
                  rows={5}
                  maxLength={2000}
                  value={kit.bio}
                  onChange={(e) => setKit({ ...kit, bio: e.target.value })}
                />
              </label>
              <label>
                Public contact email
                <input
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
          <Panel title="Audience figures" aside="Entered by you">
            <p className="muted-text">
              Use current figures from your channel analytics. These are
              labelled as creator-provided on the public page.
            </p>
            <div className="form-grid">
              {kit.statistics.map((row, index) => (
                <div key={index} className="row">
                  <label>
                    Metric
                    <input
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
                    <input
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
                    <input
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
                    <input
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
                    <input
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
                    <textarea
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
            <input
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
        </form>
      )}
    </>
  );
}
