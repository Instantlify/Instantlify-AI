"use client";

import { useConfirmation } from "@/components/confirmation-provider";

import { Download, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { api, apiBlob, message, when } from "@/lib/api";
import {
  ErrorNotice,
  Pill,
  SuccessNotice,
  statusTone,
  useFeedback,
} from "@/components/ui";
import { asList } from "@/lib/as-list";

type DataOperation = {
  id: string;
  kind: "export" | "delete";
  status: string;
  error_code: string;
  created_at: string;
};

/** Owner-only workspace export (GDPR access) and deletion (GDPR erasure). */
export function DataPrivacyPanel({
  prefix,
  workspaceName,
}: {
  prefix: string;
  workspaceName: string;
}) {
  const [operations, setOperations] = useState<DataOperation[]>([]);
  const [exportPassword, setExportPassword] = useState("");
  const [deletePassword, setDeletePassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const confirm = useConfirmation();
  const feedback = useFeedback();

  const load = useCallback(
    async (signal?: AbortSignal) =>
      setOperations(
        asList(
          await api<DataOperation[]>(
            `${prefix}/data-operations/`,
            "GET",
            undefined,
            signal,
          ),
        ),
      ),
    [prefix],
  );
  useEffect(() => {
    const controller = new AbortController();
    queueMicrotask(() => {
      load(controller.signal).catch((err) => {
        if (!controller.signal.aborted) feedback.setError(message(err));
      });
    });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [load]);
  const pending = operations.some((op) =>
    ["pending", "processing"].includes(op.status),
  );
  useEffect(() => {
    if (!pending) return;
    const timer = window.setInterval(() => load().catch(() => undefined), 5000);
    return () => window.clearInterval(timer);
  }, [pending, load]);

  async function requestExport(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const done = await feedback.run(async () => {
      await api(`${prefix}/data-operations/`, "POST", {
        kind: "export",
        password: exportPassword,
      });
      await load();
      return true;
    }, "Export requested. It will be ready to download shortly.");
    if (done) setExportPassword("");
  }

  async function download(op: DataOperation) {
    await feedback.run(async () => {
      const blob = await apiBlob(
        `${prefix}/data-operations/${op.id}/download/?format=xlsx`,
      );
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = `instantlify-export-${op.created_at.slice(0, 10)}.xlsx`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.setTimeout(() => URL.revokeObjectURL(link.href), 1000);
    });
  }

  async function requestDelete(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (
      !(await confirm(
        `Permanently delete “${workspaceName}” and all of its contacts, conversations and automations? This cannot be undone.`,
      ))
    )
      return;
    const done = await feedback.run(async () => {
      await api(`${prefix}/data-operations/`, "POST", {
        kind: "delete",
        password: deletePassword,
        confirmation,
      });
      await load();
      return true;
    }, "Deletion requested. The workspace will be removed shortly.");
    if (done) {
      setDeletePassword("");
      setConfirmation("");
    }
  }

  return (
    <div className="settings-tab-content stack-cards">
      <ErrorNotice error={feedback.error} />
      <SuccessNotice notice={feedback.notice} />
      <section className="card stack">
        <h3>Export workspace data</h3>
        <p className="muted-text">
          An Excel workbook with separate sheets for contacts, conversations,
          messages, automations, form responses and workspace settings.
          Passwords, API keys and provider tokens are never included.
        </p>
        <form className="row wrap" style={{ gap: 8 }} onSubmit={requestExport}>
          <input
            type="password"
            aria-label="Your password (export)"
            placeholder="Your password"
            autoComplete="current-password"
            required
            value={exportPassword}
            onChange={(event) => setExportPassword(event.target.value)}
          />
          <button className="button primary small" disabled={feedback.busy}>
            <Download size={14} /> Request export
          </button>
        </form>
        {operations.length > 0 && (
          <ul
            className="stack"
            style={{ gap: 6, listStyle: "none", padding: 0 }}
          >
            {operations.map((op) => (
              <li
                key={op.id}
                className="row"
                style={{ gap: 8, alignItems: "center" }}
              >
                <Pill tone={statusTone(op.status)}>{op.status}</Pill>
                <span>{op.kind === "export" ? "Export" : "Deletion"}</span>
                <span className="muted-text">{when(op.created_at)}</span>
                {op.error_code && (
                  <span className="muted-text mono">{op.error_code}</span>
                )}
                {op.kind === "export" && op.status === "complete" && (
                  <button
                    type="button"
                    className="text-button"
                    disabled={feedback.busy}
                    onClick={() => void download(op)}
                  >
                    Download Excel
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
      <section
        className="card stack"
        style={{ borderColor: "var(--bad, #dc2626)" }}
      >
        <h3>Delete this workspace</h3>
        <p className="muted-text">
          Permanently removes the workspace and everything in it. Export your
          data first if you may need it.
        </p>
        <form className="stack" style={{ gap: 8 }} onSubmit={requestDelete}>
          <label>
            <span>
              Type <strong>{workspaceName}</strong> to confirm
            </span>
            <input
              aria-label="Workspace name confirmation"
              required
              value={confirmation}
              onChange={(event) => setConfirmation(event.target.value)}
            />
          </label>
          <input
            type="password"
            aria-label="Your password (delete)"
            placeholder="Your password"
            autoComplete="current-password"
            required
            value={deletePassword}
            onChange={(event) => setDeletePassword(event.target.value)}
          />
          <button
            className="button danger small"
            style={{ alignSelf: "flex-start" }}
            disabled={feedback.busy || confirmation !== workspaceName}
          >
            <Trash2 size={14} /> Delete workspace permanently
          </button>
        </form>
      </section>
    </div>
  );
}
