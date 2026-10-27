"use client";

import {
  ValidatedForm,
  ValidatedTextarea,
} from "@/components/validated-form";

import { useState, type FormEvent } from "react";
import { api, message } from "@/lib/api";
import { ErrorNotice, Panel } from "@/components/ui";

type Answer = {
  answer: string;
  handoff: boolean;
  sources: string[];
  is_test: boolean;
};

export function AgentPreview({ prefix }: { prefix: string }) {
  const [question, setQuestion] = useState("How much does it cost?");
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function preview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setAnswer(null);
    try {
      setAnswer(
        await api<Answer>(`${prefix}/agent/preview/`, "POST", { question }),
      );
    } catch (err) {
      setError(message(err));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Panel title="Test your assistant">
      <p>
        Preview an answer using your saved settings and ready business
        knowledge. This test does not send messages, make bookings or take
        payments. Live AI previews use your normal AI credits.
      </p>
      <p className="muted-text">
        This checks answers and keyword handoffs, not the full sales workflow.
        Documents listed below were supplied to the assistant; they are not
        verified citations.
      </p>
      <div className="button-row">
        {[
          "How much does it cost?",
          "Can I get a discount?",
          "I want to speak to a human.",
        ].map((text) => (
          <button
            type="button"
            className="button"
            key={text}
            disabled={busy}
            onClick={() => {
              setQuestion(text);
              setAnswer(null);
            }}
          >
            {text}
          </button>
        ))}
      </div>
      <ValidatedForm onSubmit={preview}>
        <label>
          Customer question
          <ValidatedTextarea
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            maxLength={2000}
            required
          />
        </label>
        <button className="button primary" disabled={busy || !question.trim()}>
          {busy ? "Preparing answer…" : "Preview answer"}
        </button>
      </ValidatedForm>
      <ErrorNotice error={error} />
      {answer && (
        <div
          role="status"
          className="channel-box"
          style={{ display: "block", marginTop: 16 }}
        >
          <strong>
            {answer.is_test
              ? "Simulated answer · local test provider"
              : answer.handoff
                ? "Team handoff preview"
                : "Assistant answer"}
          </strong>
          <p style={{ whiteSpace: "pre-wrap" }}>{answer.answer}</p>
          {answer.sources.length > 0 && (
            <p className="muted-text">
              Knowledge supplied: {answer.sources.join(", ")}
            </p>
          )}
        </div>
      )}
    </Panel>
  );
}
