"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { Mic, MicOff, WandSparkles } from "lucide-react";
import { api, message, type Automation } from "@/lib/api";
import { ErrorNotice } from "./ui";

/* The Web Speech API is not in TypeScript's DOM library; this is the slice we use. */
type Recognition = {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult:
    | ((event: {
        results: ArrayLike<ArrayLike<{ transcript: string }>>;
      }) => void)
    | null;
  onend: (() => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  start: () => void;
  stop: () => void;
};
type RecognitionClass = new () => Recognition;

function speechRecognition(): RecognitionClass | null {
  if (typeof window === "undefined") return null;
  const scope = window as unknown as {
    SpeechRecognition?: RecognitionClass;
    webkitSpeechRecognition?: RecognitionClass;
  };
  return scope.SpeechRecognition ?? scope.webkitSpeechRecognition ?? null;
}

const EXAMPLE =
  "Create an Instagram comment-to-DM workflow that asks for an email before sending a PDF guide";

/** Natural-language flow drafting with optional voice dictation. The server drafts
 * the flow with the workspace's AI model and saves it disabled for review. */
export function FlowGenerator({
  workspaceId,
  prefix,
}: {
  workspaceId: string;
  prefix: string;
}) {
  const router = useRouter();
  const [prompt, setPrompt] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [listening, setListening] = useState(false);
  const [voice, setVoice] = useState(false);
  const recognition = useRef<Recognition | null>(null);

  useEffect(() => {
    // Feature detection must wait for the browser; the server render has no window.
    queueMicrotask(() => setVoice(speechRecognition() !== null));
    return () => recognition.current?.stop();
  }, []);

  function toggleVoice() {
    if (listening) {
      recognition.current?.stop();
      return;
    }
    const Speech = speechRecognition();
    if (!Speech) return;
    const session = new Speech();
    session.lang = navigator.language || "en-US";
    session.interimResults = false;
    session.continuous = false;
    const before = prompt.trim();
    session.onresult = (event) => {
      const heard = Array.from(event.results)
        .map((result) => result[0]?.transcript ?? "")
        .join(" ")
        .trim();
      if (heard)
        setPrompt([before, heard].filter(Boolean).join(" ").slice(0, 1000));
    };
    session.onerror = (event) => {
      if (event.error !== "aborted" && event.error !== "no-speech")
        setError("Voice input is unavailable. Check microphone permission.");
    };
    session.onend = () => setListening(false);
    recognition.current = session;
    setError("");
    setListening(true);
    session.start();
  }

  async function generate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!prompt.trim()) return;
    recognition.current?.stop();
    setBusy(true);
    setError("");
    try {
      const item = await api<Automation>(
        `${prefix}/automations/generate/`,
        "POST",
        { prompt: prompt.trim() },
      );
      router.push(`/w/${workspaceId}/automations/${item.id}`);
    } catch (err) {
      setError(message(err));
      setBusy(false);
    }
  }

  return (
    <section className="flow-generator" aria-labelledby="flow-generator-title">
      <div>
        <span className="eyebrow">
          <WandSparkles size={13} /> AI FLOW GENERATOR
        </span>
        <h2 id="flow-generator-title">Describe the automation you want.</h2>
        <p>
          Nemio drafts the triggers and steps with your AI model. You review the
          draft in the builder before anything goes live.
        </p>
      </div>
      <form onSubmit={generate} className="generator-bar">
        <label className="sr-only" htmlFor="flow-prompt">
          Describe your automation
        </label>
        <textarea
          id="flow-prompt"
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          placeholder={EXAMPLE}
          maxLength={1000}
          rows={2}
          onKeyDown={(event) => {
            if (event.key === "Enter" && (event.metaKey || event.ctrlKey))
              event.currentTarget.form?.requestSubmit();
          }}
        />
        <div className="generator-actions">
          {voice && (
            <button
              type="button"
              className={`icon-button mic ${listening ? "live" : ""}`}
              aria-label={
                listening ? "Stop dictation" : "Dictate with your voice"
              }
              aria-pressed={listening}
              onClick={toggleVoice}
            >
              {listening ? <MicOff size={16} /> : <Mic size={16} />}
            </button>
          )}
          <button className="button primary" disabled={busy || !prompt.trim()}>
            {busy ? "Drafting…" : "Generate flow"}
            <WandSparkles size={15} />
          </button>
        </div>
      </form>
      {!prompt && (
        <button
          type="button"
          className="text-button generator-example"
          onClick={() => setPrompt(EXAMPLE)}
        >
          Try the example
        </button>
      )}
      <ErrorNotice error={error} />
    </section>
  );
}
