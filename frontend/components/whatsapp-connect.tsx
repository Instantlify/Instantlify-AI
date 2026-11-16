"use client";

import { useEffect, useRef, useState } from "react";
import { Plug } from "lucide-react";
import { api, message, type Connection } from "@/lib/api";
import { CopyField, ErrorNotice, Modal, useFeedback } from "@/components/ui";
import { ValidatedForm, ValidatedInput } from "@/components/validated-form";

type Signup = {
  state: string;
  app_id: string;
  config_id: string;
  version: string;
};
type Facebook = {
  init: (options: Record<string, unknown>) => void;
  login: (
    callback: (response: { authResponse?: { code?: string } }) => void,
    options: Record<string, unknown>,
  ) => void;
};
type MetaWindow = Window & { FB?: Facebook };
let sdkPromise: Promise<Facebook> | undefined;
function facebookSdk(): Promise<Facebook> {
  const win = window as MetaWindow;
  if (win.FB) return Promise.resolve(win.FB);
  if (!sdkPromise) {
    sdkPromise = new Promise<Facebook>((resolve, reject) => {
      const script = document.createElement("script");
      script.src = "https://connect.facebook.net/en_US/sdk.js";
      script.async = true;
      script.onload = () =>
        win.FB
          ? resolve(win.FB)
          : reject(
              new Error("WhatsApp sign-in could not load. Please try again."),
            );
      script.onerror = () =>
        reject(
          new Error(
            "WhatsApp sign-in could not load. Check your connection and try again.",
          ),
        );
      document.head.appendChild(script);
    }).catch((error) => {
      sdkPromise = undefined;
      throw error;
    });
  }
  return sdkPromise;
}

export function WhatsAppConnect({
  prefix,
  connection,
  onConnected,
}: {
  prefix: string;
  connection?: Connection;
  onConnected: () => Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        className={`button ${connection ? "small secondary" : "primary"}`}
        onClick={() => setOpen(true)}
      >
        <Plug size={16} />{" "}
        {connection
          ? connection.status === "setup_required"
            ? "Finish WhatsApp setup"
            : "Reconnect WhatsApp"
          : "Connect WhatsApp"}
      </button>
      {open && (
        <WhatsAppSetup
          key={prefix}
          prefix={prefix}
          connection={connection}
          onConnected={onConnected}
          onClose={() => setOpen(false)}
        />
      )}
    </>
  );
}

function WhatsAppSetup({
  prefix,
  connection,
  onConnected,
  onClose,
}: {
  prefix: string;
  connection?: Connection;
  onConnected: () => Promise<void>;
  onClose: () => void;
}) {
  const [config, setConfig] = useState<Signup | null>(null);
  const [steps, setSteps] = useState<string[]>([]);
  const [webhook, setWebhook] = useState("");
  const resuming = connection?.status === "setup_required";
  const [pending, setPending] = useState(resuming ? connection.id : "");
  const [alreadyRegistered, setAlreadyRegistered] = useState(false);
  const [starting, setStarting] = useState(!resuming);
  const [signingIn, setSigningIn] = useState(false);
  const feedback = useFeedback();
  const active = useRef(true);
  const signup = useRef<{
    code?: string;
    waba_id?: string;
    phone_number_id?: string;
    submitted?: boolean;
  }>({});
  const sdk = useRef<Facebook | null>(null);
  const configRef = useRef<Signup | null>(null);
  const signingRef = useRef(false);
  const callbacks = useRef({ onConnected, onClose });
  useEffect(() => {
    callbacks.current = { onConnected, onClose };
  }, [onConnected, onClose]);

  useEffect(() => {
    active.current = true;
    const controller = new AbortController();
    async function prepare() {
      const info = await api<{
        ready: boolean;
        steps: string[];
        webhook_url: string;
      }>(`${prefix}/whatsapp/connect/`, "GET", undefined, controller.signal);
      if (!active.current) return;
      setSteps(info.steps);
      setWebhook(info.webhook_url);
      if (!info.ready) return;
      const prepared = await api<Signup>(
        `${prefix}/whatsapp/connect/`,
        "POST",
        connection ? { connection_id: connection.id } : {},
        controller.signal,
      );
      const fb = await facebookSdk();
      if (!active.current) return;
      fb.init({
        appId: prepared.app_id,
        version: prepared.version,
        xfbml: false,
        autoLogAppEvents: false,
      });
      sdk.current = fb;
      configRef.current = prepared;
      setConfig(prepared);
    }
    if (!resuming)
      prepare()
        .catch((error) => {
          if (active.current && !controller.signal.aborted)
            feedback.setError(message(error));
        })
        .finally(() => {
          if (active.current) setStarting(false);
        });

    async function complete() {
      const data = signup.current;
      const prepared = configRef.current;
      if (
        !signingRef.current ||
        !prepared ||
        !data.code ||
        !data.waba_id ||
        !data.phone_number_id ||
        data.submitted
      )
        return;
      data.submitted = true;
      try {
        const result = await api<{ id: string }>(
          `${prefix}/whatsapp/complete/`,
          "POST",
          {
            state: prepared.state,
            code: data.code,
            waba_id: data.waba_id,
            phone_number_id: data.phone_number_id,
          },
          controller.signal,
        );
        if (active.current) {
          setPending(result.id);
          setSigningIn(false);
        }
      } catch (error) {
        if (active.current && !controller.signal.aborted) {
          feedback.setError(message(error));
          setSigningIn(false);
          setConfig(null);
        }
      } finally {
        signup.current = {};
        signingRef.current = false;
      }
    }
    const receive = (event: MessageEvent) => {
      if (
        !signingRef.current ||
        !["https://www.facebook.com", "https://web.facebook.com"].includes(
          event.origin,
        )
      )
        return;
      try {
        const data =
          typeof event.data === "string" ? JSON.parse(event.data) : event.data;
        if (data?.type !== "WA_EMBEDDED_SIGNUP") return;
        if (data.event === "FINISH") {
          if (
            !/^\d{1,40}$/.test(data.data?.waba_id) ||
            !/^\d{1,40}$/.test(data.data?.phone_number_id)
          )
            return;
          Object.assign(signup.current, {
            waba_id: data.data.waba_id,
            phone_number_id: data.data.phone_number_id,
          });
          void complete();
        } else if (["CANCEL", "ERROR"].includes(data.event)) {
          signingRef.current = false;
          signup.current = {};
          setSigningIn(false);
          feedback.setError(
            "WhatsApp setup was not completed. You can try again when ready.",
          );
        }
      } catch {
        /* Ignore unrelated SDK messages. */
      }
    };
    const codeReady = (event: Event) => {
      if (event.target === window) void complete();
    };
    window.addEventListener("message", receive);
    window.addEventListener("instantlify-whatsapp-code", codeReady);
    return () => {
      active.current = false;
      signingRef.current = false;
      signup.current = {};
      controller.abort();
      window.removeEventListener("message", receive);
      window.removeEventListener("instantlify-whatsapp-code", codeReady);
    };
    // Feedback methods are stable; prepare only once per workspace/dialog.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefix, connection]);

  function launch() {
    if (!sdk.current || !config || signingRef.current) return;
    feedback.setError("");
    signingRef.current = true;
    const attempt = {};
    signup.current = attempt;
    setSigningIn(true);
    sdk.current.login(
      (response) => {
        if (
          !active.current ||
          !signingRef.current ||
          signup.current !== attempt
        )
          return;
        if (response.authResponse?.code) {
          signup.current.code = response.authResponse.code;
          window.dispatchEvent(new Event("instantlify-whatsapp-code"));
        } else {
          signingRef.current = false;
          signup.current = {};
          setSigningIn(false);
          feedback.setError(
            "WhatsApp sign-in was cancelled. You can try again.",
          );
        }
      },
      {
        config_id: config.config_id,
        response_type: "code",
        override_default_response_type: true,
        extras: { setup: {}, sessionInfoVersion: "3" },
      },
    );
  }

  return (
    <Modal title="Connect WhatsApp Business" onClose={onClose}>
      <ErrorNotice error={feedback.error} />
      <p>
        Connect your business number to receive customer messages, let your AI
        reply, and take over conversations from the inbox.
      </p>
      {starting ? (
        <p role="status">Preparing WhatsApp sign-in…</p>
      ) : pending ? (
        <ValidatedForm
          className="stack"
          fieldErrors={feedback.fieldErrors}
          validationTarget={feedback.validationTarget}
          onEdit={() => feedback.setError("")}
          onSubmit={async (event) => {
            event.preventDefault();
            const data = new FormData(event.currentTarget);
            await feedback.run(async () => {
              await api(
                `${prefix}/whatsapp/${pending}/activate/`,
                "POST",
                alreadyRegistered
                  ? { already_registered: true }
                  : { pin: data.get("pin") },
              );
              await callbacks.current.onConnected();
              callbacks.current.onClose();
            });
          }}
        >
          <p>
            Your business is authorized. Finish registering the number and
            enabling message notifications.
          </p>
          <label className="inline">
            <ValidatedInput
              name="already_registered"
              type="checkbox"
              checked={alreadyRegistered}
              onChange={(event) => setAlreadyRegistered(event.target.checked)}
            />{" "}
            This number is already registered with WhatsApp Cloud API
          </label>
          {!alreadyRegistered && (
            <label>
              WhatsApp security PIN
              <ValidatedInput
                name="pin"
                aria-label="WhatsApp security PIN"
                type="password"
                inputMode="numeric"
                autoComplete="off"
                pattern="[0-9]{6}"
                minLength={6}
                maxLength={6}
                required
                data-validation-hint="Enter a six-digit security PIN."
              />
              <span className="hint">
                Use your existing six-digit PIN, or choose one for a new number.
                Keep it safe for future reconnections.
              </span>
            </label>
          )}
          <button className="button primary" disabled={feedback.busy}>
            {feedback.busy ? "Finishing setup…" : "Finish connection"}
          </button>
        </ValidatedForm>
      ) : steps.length ? (
        <div className="stack">
          <p>
            Your administrator needs to finish the connection setup before you
            can sign in.
          </p>
          <ul>
            {steps.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ul>
          <details>
            <summary>Administrator setup details</summary>
            <p>
              Use a Meta app configured for WhatsApp and Facebook Login for
              Business. Add the app credentials and signup configuration to the
              local environment. A public HTTPS tunnel is needed while Instantlify
              runs locally.
            </p>
            <CopyField label="WhatsApp notification address" value={webhook} />
            <p>
              Register this address in Meta, use the configured verification
              token, and subscribe to messages.
            </p>
            <a
              href="https://developers.facebook.com/documentation/business-messaging/whatsapp/embedded-signup/overview/"
              target="_blank"
              rel="noreferrer"
            >
              Meta setup guide
            </a>
          </details>
        </div>
      ) : (
        <div className="stack">
          <ol>
            <li>Sign in to Meta and choose your business.</li>
            <li>Select or add your WhatsApp number and verify it with Meta.</li>
            <li>Return here to finish connecting.</li>
          </ol>
          <button
            type="button"
            className="button primary"
            disabled={!config || signingIn}
            onClick={launch}
          >
            {signingIn
              ? "Complete setup in the Meta window…"
              : "Continue with Meta"}
          </button>
          {signingIn && (
            <button
              type="button"
              className="button secondary"
              onClick={() => {
                signingRef.current = false;
                signup.current = {};
                setSigningIn(false);
              }}
            >
              Cancel connection attempt
            </button>
          )}
        </div>
      )}
      <p className="muted-text">
        New messages appear after connection. Existing WhatsApp chat history is
        not imported.
      </p>
    </Modal>
  );
}
