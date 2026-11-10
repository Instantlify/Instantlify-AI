"use client";

import { useRef, useState, type PointerEvent } from "react";
import type { FormAnswer, FormField } from "@/lib/portal-tools";
import { ValidatedInput } from "./validated-form";
import { useT } from "@/lib/i18n";

export function FormFileQuestion({
  field,
  value,
  onChange,
}: {
  field: FormField;
  value?: FormAnswer;
  onChange: (value: FormAnswer) => void;
}) {
  const t = useT();
  const [error, setError] = useState("");
  const canvas = useRef<HTMLCanvasElement>(null);
  const drawing = useRef(false);
  const hasInk = useRef(false);
  const selectionVersion = useRef(0);
  function point(event: PointerEvent<HTMLCanvasElement>) {
    const bounds = event.currentTarget.getBoundingClientRect();
    return [
      ((event.clientX - bounds.left) * event.currentTarget.width) /
        bounds.width,
      ((event.clientY - bounds.top) * event.currentTarget.height) /
        bounds.height,
    ];
  }
  const selected =
    value && typeof value === "object" && "name" in value ? value : null;
  return (
    <fieldset>
      <legend>
        {field.label}
        {field.required ? " *" : ""}
      </legend>
      {field.type === "file_upload" ? (
        <label>
          Choose file (up to 1 MB)
          <ValidatedInput
            type="file"
            name={`answer:${field.id}`}
            required={field.required}
            onChange={async (event) => {
              const version = ++selectionVersion.current;
              const file = event.target.files?.[0];
              onChange("");
              setError("");
              if (!file) return;
              if (!file.size || file.size > 1024 * 1024) {
                setError("Choose a nonempty file up to 1 MB.");
                event.target.value = "";
                return;
              }
              try {
                const data = await new Promise<string>((resolve, reject) => {
                  const reader = new FileReader();
                  reader.onload = () =>
                    resolve(String(reader.result).split(",")[1]);
                  reader.onerror = () => reject(new Error("Read failed"));
                  reader.readAsDataURL(file);
                });
                if (version === selectionVersion.current)
                  onChange({ name: file.name, data });
              } catch {
                if (version === selectionVersion.current)
                  setError("The file could not be read. Choose it again.");
              }
            }}
          />
        </label>
      ) : (
        <>
          <p>{t("form.signatureHelp")}</p>
          <canvas
            ref={canvas}
            width={600}
            height={180}
            aria-label={`${field.label} signature pad`}
            style={{
              width: "100%",
              height: 180,
              border: "1px solid #8a96a8",
              background: "#fff",
              touchAction: "none",
            }}
            onPointerDown={(event) => {
              if (event.button !== 0) return;
              const context = event.currentTarget.getContext("2d");
              if (!context) return;
              drawing.current = true;
              selectionVersion.current++;
              event.currentTarget.setPointerCapture(event.pointerId);
              const [x, y] = point(event);
              context.beginPath();
              context.moveTo(x, y);
              context.strokeStyle = "#10244a";
              context.lineWidth = 3;
              context.lineCap = "round";
            }}
            onPointerMove={(event) => {
              if (!drawing.current) return;
              const context = event.currentTarget.getContext("2d");
              if (!context) return;
              const [x, y] = point(event);
              context.lineTo(x, y);
              context.stroke();
              hasInk.current = true;
            }}
            onPointerUp={(event) => {
              if (!drawing.current) return;
              drawing.current = false;
              if (hasInk.current)
                onChange({
                  name: "signature.png",
                  data: event.currentTarget
                    .toDataURL("image/png")
                    .split(",")[1],
                });
            }}
            onPointerCancel={() => {
              drawing.current = false;
            }}
          />
          <button
            type="button"
            className="text-button"
            onClick={() => {
              canvas.current?.getContext("2d")?.clearRect(0, 0, 600, 180);
              selectionVersion.current++;
              hasInk.current = false;
              setError("");
              onChange("");
            }}
          >
            Clear signature
          </button>
          <label>
            Upload signature image
            <ValidatedInput
              type="file"
              accept="image/png"
              onChange={async (event) => {
                const version = ++selectionVersion.current;
                const file = event.target.files?.[0];
                if (!file) return;
                if (!file.size || file.size > 1024 * 1024) {
                  setError("Choose a PNG up to 1 MB.");
                  return;
                }
                const bytes = new Uint8Array(await file.arrayBuffer());
                if (version !== selectionVersion.current) return;
                if (
                  ![137, 80, 78, 71, 13, 10, 26, 10].every(
                    (v, i) => bytes[i] === v,
                  )
                ) {
                  setError("Choose a PNG signature image.");
                  return;
                }
                let raw = "";
                for (const byte of bytes) raw += String.fromCharCode(byte);
                setError("");
                onChange({ name: file.name, data: btoa(raw) });
              }}
            />
          </label>
        </>
      )}
      {selected && <p role="status">{selected.name} ready to submit.</p>}
      {error && <p role="alert">{error}</p>}
    </fieldset>
  );
}
