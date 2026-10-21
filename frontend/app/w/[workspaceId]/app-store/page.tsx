"use client";

import Link from "next/link";
import { ArrowRight, Check, Pin, PinOff } from "lucide-react";
import { api } from "@/lib/api";
import { APPS } from "@/lib/apps";
import { useWorkspace } from "@/lib/workspace";
import {
  ErrorNotice,
  PageHeading,
  SuccessNotice,
  useFeedback,
} from "@/components/ui";

export default function AppStorePage() {
  const { workspace, prefix, manager, refresh } = useWorkspace();
  const feedback = useFeedback();
  const pinned = workspace.pinned_apps || [];

  async function togglePin(id: string, label: string) {
    const next = pinned.includes(id)
      ? pinned.filter((item) => item !== id)
      : [...pinned, id];
    await feedback.run(
      async () => {
        await api(`${prefix}/`, "PATCH", { pinned_apps: next });
        await refresh();
      },
      pinned.includes(id)
        ? `${label} removed from the sidebar.`
        : `${label} pinned to the sidebar.`,
    );
  }

  return (
    <>
      <PageHeading
        eyebrow="App store"
        title="Tools that sit next to your conversations."
        text="Open an app, or pin it to the Apps section of the sidebar for everyone in this workspace."
      />
      <ErrorNotice error={feedback.error} />
      <SuccessNotice notice={feedback.notice} />
      <div className="app-grid">
        {APPS.map((app) => {
          const Icon = app.icon;
          const available = Boolean(app.section);
          const openable = available && (manager || app.agents);
          const isPinned = pinned.includes(app.id);
          return (
            <article
              key={app.id}
              className={`app-card ${available ? "" : "soon"}`}
            >
              <header>
                <span className="app-icon">
                  <Icon size={20} />
                </span>
                <div>
                  <h2>{app.label}</h2>
                  {available ? (
                    isPinned && (
                      <span className="app-state">
                        <Check size={12} /> Pinned
                      </span>
                    )
                  ) : (
                    <span className="app-state soon">Coming soon</span>
                  )}
                </div>
              </header>
              <p>{app.description}</p>
              <ul>
                {app.highlights.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
              {available && (
                <footer>
                  {openable ? (
                    <Link
                      href={`/w/${workspace.id}/${app.section}`}
                      className="button primary small"
                    >
                      Open <ArrowRight size={14} />
                    </Link>
                  ) : (
                    <span className="muted-text">
                      Available to owners and admins.
                    </span>
                  )}
                  {manager && (
                    <button
                      className="button secondary small"
                      disabled={feedback.busy}
                      aria-pressed={isPinned}
                      onClick={() => togglePin(app.id, app.label)}
                    >
                      {isPinned ? (
                        <>
                          <PinOff size={14} /> Unpin
                        </>
                      ) : (
                        <>
                          <Pin size={14} /> Pin to sidebar
                        </>
                      )}
                    </button>
                  )}
                </footer>
              )}
            </article>
          );
        })}
      </div>
    </>
  );
}
