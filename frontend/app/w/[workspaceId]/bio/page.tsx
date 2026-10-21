"use client";

import { useEffect, useState, type FormEvent } from "react";
import {
  ArrowDown,
  ArrowUp,
  ExternalLink,
  Plus,
  Save,
  Trash2,
} from "lucide-react";
import { api, message, type BioLink, type BioPage } from "@/lib/api";
import { useWorkspace } from "@/lib/workspace";
import {
  CopyField,
  Empty,
  ErrorNotice,
  PageHeading,
  Panel,
  SuccessNotice,
  useFeedback,
} from "@/components/ui";

const EMPTY: BioPage = {
  slug: "",
  title: "",
  bio: "",
  avatar_url: "",
  accent: "#313a34",
  links: [],
  published: false,
};

export default function BioPageEditor() {
  const { prefix, manager, workspace } = useWorkspace();
  const [page, setPage] = useState<BioPage>(EMPTY);
  const [saved, setSaved] = useState<BioPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [origin, setOrigin] = useState("");
  const feedback = useFeedback();

  useEffect(() => {
    const controller = new AbortController();
    api<BioPage | Record<string, never>>(
      `${prefix}/bio/`,
      "GET",
      undefined,
      controller.signal,
    )
      .then((data) => {
        setOrigin(window.location.origin);
        if ("slug" in data && data.slug) {
          setPage(data as BioPage);
          setSaved(data as BioPage);
        } else {
          setPage({
            ...EMPTY,
            title: workspace.name,
            accent:
              workspace.branding.primary_color &&
              workspace.branding.primary_color !== "#347359"
                ? workspace.branding.primary_color
                : EMPTY.accent,
          });
        }
      })
      .catch((err) => {
        if (!controller.signal.aborted) feedback.setError(message(err));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefix]);

  const update = <K extends keyof BioPage>(key: K, value: BioPage[K]) =>
    setPage((current) => ({ ...current, [key]: value }));

  const updateLink = (index: number, patch: Partial<BioLink>) =>
    update(
      "links",
      page.links.map((link, i) => (i === index ? { ...link, ...patch } : link)),
    );

  const moveLink = (index: number, direction: -1 | 1) => {
    const target = index + direction;
    if (target < 0 || target >= page.links.length) return;
    const links = [...page.links];
    [links[index], links[target]] = [links[target], links[index]];
    update("links", links);
  };

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const result = await feedback.run(
      () =>
        api<BioPage>(`${prefix}/bio/`, "PUT", {
          slug: page.slug,
          title: page.title,
          bio: page.bio,
          avatar_url: page.avatar_url,
          accent: page.accent,
          links: page.links,
          published: page.published,
        }),
      "Page saved.",
    );
    if (result) {
      setPage(result);
      setSaved(result);
    }
  }

  const publicUrl = page.slug ? `${origin}/p/${page.slug}/` : "";

  return (
    <>
      <PageHeading
        eyebrow="Link in bio"
        title="One link for everything."
        text="A hosted, branded page for your Instagram bio: booking, offers and socials in one place."
        action={
          saved?.published && saved.slug ? (
            <a
              className="button secondary small"
              href={`/p/${saved.slug}/`}
              target="_blank"
              rel="noreferrer noopener"
            >
              Open page
              <ExternalLink size={14} />
            </a>
          ) : undefined
        }
      />
      <ErrorNotice error={feedback.error} />
      <SuccessNotice notice={feedback.notice} />
      {loading ? (
        <p className="loading-text">Loading your page…</p>
      ) : (
        <div className="two-col">
          <Panel title="Page details">
            {!manager && (
              <Empty>Owners and admins edit the link-in-bio page.</Empty>
            )}
            <form className="form-grid" onSubmit={save}>
              <fieldset
                disabled={!manager}
                style={{
                  border: 0,
                  padding: 0,
                  margin: 0,
                  display: "contents",
                }}
              >
                <label>
                  Page address
                  <input
                    value={page.slug}
                    onChange={(event) =>
                      update("slug", event.target.value.toLowerCase())
                    }
                    pattern="[a-z0-9]([a-z0-9-]{1,58}[a-z0-9])?"
                    minLength={3}
                    maxLength={60}
                    placeholder="acme-studio"
                    required
                  />
                  <span className="hint">
                    3–60 lowercase letters, digits or dashes.
                  </span>
                </label>
                <label>
                  Title
                  <input
                    value={page.title}
                    onChange={(event) => update("title", event.target.value)}
                    maxLength={80}
                    required
                  />
                </label>
                <label>
                  Bio
                  <textarea
                    value={page.bio}
                    onChange={(event) => update("bio", event.target.value)}
                    maxLength={300}
                    placeholder="A sentence about what you do."
                  />
                </label>
                <label>
                  Avatar URL
                  <input
                    type="url"
                    pattern="https://.*"
                    value={page.avatar_url}
                    onChange={(event) =>
                      update("avatar_url", event.target.value)
                    }
                    placeholder="https://…/avatar.jpg"
                  />
                </label>
                <label>
                  Accent colour
                  <input
                    type="color"
                    value={page.accent}
                    onChange={(event) => update("accent", event.target.value)}
                  />
                </label>
                <div className="field">
                  <span>Links ({page.links.length}/20)</span>
                  <div className="card-list">
                    {page.links.map((link, index) => (
                      <div className="card" key={index}>
                        <div className="row">
                          <input
                            aria-label={`Link ${index + 1} title`}
                            value={link.title}
                            maxLength={60}
                            placeholder="Book a call"
                            onChange={(event) =>
                              updateLink(index, { title: event.target.value })
                            }
                            required
                            style={{ flex: "1 1 140px" }}
                          />
                          <input
                            aria-label={`Link ${index + 1} URL`}
                            type="url"
                            pattern="https://.*"
                            value={link.url}
                            placeholder="https://…"
                            onChange={(event) =>
                              updateLink(index, { url: event.target.value })
                            }
                            required
                            style={{ flex: "2 1 200px" }}
                          />
                        </div>
                        <div className="row">
                          <button
                            type="button"
                            className="icon-button"
                            aria-label="Move up"
                            disabled={index === 0}
                            onClick={() => moveLink(index, -1)}
                          >
                            <ArrowUp size={15} />
                          </button>
                          <button
                            type="button"
                            className="icon-button"
                            aria-label="Move down"
                            disabled={index === page.links.length - 1}
                            onClick={() => moveLink(index, 1)}
                          >
                            <ArrowDown size={15} />
                          </button>
                          <span className="spacer" />
                          <button
                            type="button"
                            className="text-button"
                            onClick={() =>
                              update(
                                "links",
                                page.links.filter((_, i) => i !== index),
                              )
                            }
                          >
                            <Trash2 size={14} /> Remove
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                  {page.links.length < 20 && (
                    <button
                      type="button"
                      className="button secondary small"
                      onClick={() =>
                        update("links", [...page.links, { title: "", url: "" }])
                      }
                    >
                      Add link
                      <Plus size={14} />
                    </button>
                  )}
                </div>
                <label className="inline">
                  <input
                    type="checkbox"
                    checked={page.published}
                    onChange={(event) =>
                      update("published", event.target.checked)
                    }
                  />
                  Published (visible to anyone with the link)
                </label>
                <div className="form-actions">
                  <button className="button primary" disabled={feedback.busy}>
                    {feedback.busy ? "Saving…" : "Save page"}
                    <Save size={16} />
                  </button>
                </div>
              </fieldset>
            </form>
            {publicUrl && <CopyField label="Public URL" value={publicUrl} />}
          </Panel>
          <Panel title="Preview" aside={page.published ? "Live" : "Draft"}>
            <div className="bio-preview">
              {page.avatar_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={page.avatar_url} alt="" />
              ) : (
                <span
                  className="user-avatar"
                  style={{
                    width: 84,
                    height: 84,
                    fontSize: 24,
                    margin: "0 auto",
                  }}
                >
                  {(page.title || workspace.name).slice(0, 2).toUpperCase()}
                </span>
              )}
              <h2>{page.title || "Your title"}</h2>
              {page.bio && <p>{page.bio}</p>}
              {page.links.length === 0 && (
                <p className="muted-text">Add links to see them here.</p>
              )}
              {page.links.map((link, index) => (
                <span
                  key={index}
                  className="bio-link"
                  style={{ background: page.accent }}
                >
                  {link.title || "Untitled link"}
                </span>
              ))}
            </div>
          </Panel>
        </div>
      )}
    </>
  );
}
