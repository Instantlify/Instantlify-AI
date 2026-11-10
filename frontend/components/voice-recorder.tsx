"use client";

import { Mic, Square } from "lucide-react";
import { useEffect, useRef, useState } from "react";

const MAX_SECONDS = 300;

/** Formats the browser can record, best first. The server converts WebM/OGG to M4A,
 * so whichever the browser picks works on every channel. */
function pickType() {
  if (typeof MediaRecorder === "undefined") return "";
  return (
    [
      "audio/mp4",
      "audio/webm;codecs=opus",
      "audio/webm",
      "audio/ogg;codecs=opus",
    ].find((type) => MediaRecorder.isTypeSupported(type)) || ""
  );
}

/** Mic button that records a voice note and hands back an audio File. */
export function VoiceRecorder({
  disabled,
  onRecorded,
  onError,
}: {
  disabled?: boolean;
  onRecorded: (file: File) => void;
  onError: (message: string) => void;
}) {
  const [seconds, setSeconds] = useState<number | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const timer = useRef<number | null>(null);

  useEffect(
    () => () => {
      if (timer.current) window.clearInterval(timer.current);
      recorder.current?.stream.getTracks().forEach((track) => track.stop());
    },
    [],
  );

  function stop() {
    if (timer.current) window.clearInterval(timer.current);
    timer.current = null;
    if (recorder.current?.state === "recording") recorder.current.stop();
  }

  async function start() {
    const type = pickType();
    if (
      !navigator.mediaDevices?.getUserMedia ||
      typeof MediaRecorder === "undefined"
    ) {
      onError("This browser cannot record audio.");
      return;
    }
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      onError("Allow microphone access to record a voice note.");
      return;
    }
    const chunks: Blob[] = [];
    const media = new MediaRecorder(
      stream,
      type ? { mimeType: type } : undefined,
    );
    media.ondataavailable = (event) => {
      if (event.data.size) chunks.push(event.data);
    };
    media.onstop = () => {
      stream.getTracks().forEach((track) => track.stop());
      setSeconds(null);
      const mime = (media.mimeType || type || "audio/webm").split(";")[0];
      const extension = mime.includes("mp4")
        ? "m4a"
        : mime.includes("ogg")
          ? "ogg"
          : "webm";
      const blob = new Blob(chunks, { type: mime });
      if (!blob.size) return;
      if (blob.size > 5 * 1024 * 1024) {
        onError("That recording is over 5 MB. Keep voice notes shorter.");
        return;
      }
      onRecorded(new File([blob], `voice-note.${extension}`, { type: mime }));
    };
    recorder.current = media;
    media.start();
    setSeconds(0);
    timer.current = window.setInterval(() => {
      setSeconds((value) => {
        const next = (value ?? 0) + 1;
        if (next >= MAX_SECONDS) stop();
        return next;
      });
    }, 1000);
  }

  const recording = seconds !== null;
  return (
    <button
      type="button"
      className="icon-button"
      style={{ color: recording ? "#dc2626" : "#94a3b8", padding: "4px" }}
      aria-label={recording ? "Stop recording" : "Record a voice note"}
      title={recording ? "Stop recording" : "Record a voice note"}
      disabled={disabled && !recording}
      onClick={() => (recording ? stop() : void start())}
    >
      {recording ? (
        <>
          <Square size={14} />{" "}
          <span style={{ fontSize: 12 }}>
            {Math.floor((seconds ?? 0) / 60)}:
            {String((seconds ?? 0) % 60).padStart(2, "0")}
          </span>
        </>
      ) : (
        <Mic size={18} />
      )}
    </button>
  );
}
