"use client";

import {
  ValidatedForm,
  ValidatedInput,
  ValidatedTextarea,
} from "@/components/validated-form";

import { useEffect, useState, type FormEvent } from "react";
import { ExternalLink, Save } from "lucide-react";
import { api, message, type BioPage } from "@/lib/api";
import { BioBlockEditor } from "@/components/bio-block-editor";
import { BIO_THEMES, BioRenderer } from "@/components/bio-renderer";
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
  blocks: [],
  theme: "light",
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
          const loaded = data as BioPage;
          // Pages made before blocks existed open with their links as link blocks.
          const blocks = loaded.blocks?.length
            ? loaded.blocks
            : loaded.links.map((link) => ({ type: "link" as const, ...link }));
          setPage({ ...loaded, blocks, theme: loaded.theme || "light" });
          setSaved(loaded);
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
          blocks: page.blocks,
          theme: page.theme,
          published: page.published,
        }),
      "Page saved.",
    );
    if (result) {
      setPage({ ...result, blocks: result.blocks });
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
            <ValidatedForm
              fieldErrors={feedback.fieldErrors}
              validationTarget={feedback.validationTarget}
              onEdit={() => feedback.setError("")}
              className="form-grid"
              onSubmit={save}
            >
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
                  <ValidatedInput
                    name="slug"
                    value={page.slug}
                    onChange={(event) =>
                      update("slug", event.target.value.toLowerCase())
                    }
                    pattern="[a-z0-9]([a-z0-9\-]{1,58}[a-z0-9])?"
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
                  <ValidatedInput
                    name="title"
                    value={page.title}
                    onChange={(event) => update("title", event.target.value)}
                    maxLength={80}
                    required
                  />
                </label>
                <label>
                  Bio
                  <ValidatedTextarea
                    name="bio"
                    value={page.bio}
                    onChange={(event) => update("bio", event.target.value)}
                    maxLength={300}
                    placeholder="A sentence about what you do."
                  />
                </label>
                <label>
                  Avatar URL
                  <ValidatedInput
                    name="avatar_url"
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
                  <ValidatedInput
                    name="accent"
                    type="color"
                    value={page.accent}
                    onChange={(event) => update("accent", event.target.value)}
                  />
                </label>
                <label>
                  Theme
                  <select
                    aria-label="Theme"
                    value={page.theme}
                    onChange={(event) => update("theme", event.target.value)}
                  >
                    {BIO_THEMES.map((theme) => (
                      <option key={theme.id} value={theme.id}>
                        {theme.label}
                      </option>
                    ))}
                  </select>
                </label>
                <BioBlockEditor
                  blocks={page.blocks}
                  onChange={(blocks) => update("blocks", blocks)}
                />
                <label className="inline">
                  <ValidatedInput
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
            </ValidatedForm>
            {publicUrl && <CopyField label="Public URL" value={publicUrl} />}
          </Panel>
          <Panel title="Preview" aside={page.published ? "Live" : "Draft"}>
            <div
              style={{ borderRadius: 16, overflow: "hidden", minHeight: 420 }}
            >
              <BioRenderer page={page} />
            </div>
          </Panel>
        </div>
      )}
    </>
  );
}
