"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { Plug, X } from "lucide-react";
import { api, message } from "@/lib/api";
import { ValidatedForm, ValidatedInput } from "@/components/validated-form";
import { ErrorNotice } from "@/components/ui";

export function TelegramConnect({
  prefix,
  onConnected,
}: {
  prefix: string;
  onConnected: () => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [connected, setConnected] = useState("");
  const dialog = useRef<HTMLDialogElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (open) dialog.current?.showModal();
    else dialog.current?.close();
  }, [open]);
  function close() {
    if (!busy) {
      setOpen(false);
      setError("");
      trigger.current?.focus();
    }
  }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    setBusy(true);
    setError("");
    try {
      const result = await api<{ display_name: string; username: string }>(
        `${prefix}/telegram/connect/`,
        "POST",
        {
          access_token: String(
            new FormData(form).get("access_token") || "",
          ).trim(),
        },
      );
      form.reset();
      setConnected(
        result.username ? `@${result.username}` : result.display_name,
      );
      await onConnected();
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <button
        ref={trigger}
        type="button"
        className="button secondary"
        onClick={() => {
          setConnected("");
          setError("");
          setOpen(true);
        }}
      >
        <Plug size={16} /> Connect Telegram
      </button>
      <dialog
        ref={dialog}
        className="modal-backdrop"
        aria-labelledby="telegram-connect-title"
        onCancel={(event) => {
          event.preventDefault();
          close();
        }}
      >
        <section
        className="modal"
          style={{ width: "min(480px, calc(100vw - 32px))" }}
        >
          <div className="modal-header-row">
            <h2 id="telegram-connect-title">Connect Telegram</h2>
            <button
              type="button"
              className="icon-button"
              aria-label="Close Telegram setup"
              disabled={busy}
              onClick={close}
            >
              <X size={20} />
            </button>
          </div>
          {connected ? (
            <>
              <p role="status">
                <strong>{connected} is connected.</strong> Open your bot in
                Telegram and press Start, then send a message. It will appear in
                Conversations.
              </p>
              <p>Create a published automation to reply automatically.</p>
              <button type="button" className="button primary" onClick={close}>
                Done
              </button>
            </>
          ) : (
            <>
              <p>
                Connect your business bot. We’ll find its name and register
                messages automatically.
              </p>
              <ol>
                <li>
                  Open{" "}
                  <a
                    href="https://t.me/BotFather"
                    target="_blank"
                    rel="noreferrer"
                  >
                    @BotFather
                  </a>{" "}
                  in Telegram.
                </li>
                <li>
                  Send <code>/newbot</code> and follow the prompts.
                </li>
                <li>Copy the bot token and paste it below.</li>
              </ol>
              <ValidatedForm onSubmit={submit}>
                <ErrorNotice error={error} />
                <label>
                  Bot token
                  <ValidatedInput
                    name="access_token"
                    type="password"
                    autoComplete="off"
                    autoFocus
                    required
                    maxLength={4000}
                    placeholder="Paste your token from BotFather"
                    disabled={busy}
                  />
                </label>
                <p className="muted-text">
                  Your token is stored encrypted. This connects a Telegram bot,
                  not your personal Telegram inbox.
                </p>
                <button
                  type="submit"
                  className="button primary"
                  disabled={busy}
                >
                  {busy ? "Connecting…" : "Connect bot"}
                </button>
              </ValidatedForm>
            </>
          )}
        </section>
      </dialog>
    </>
  );
}
