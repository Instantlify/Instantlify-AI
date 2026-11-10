"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
} from "react";
import { X } from "lucide-react";
import { ApiError, message } from "@/lib/api";
import type { FieldErrors } from "@/lib/form-errors";

export function ErrorNotice({ error }: { error: string }) {
  if (!error) return null;
  return (
    <div role="alert" className="error-notice">
      {error}
    </div>
  );
}

export function SuccessNotice({ notice }: { notice: string }) {
  if (!notice) return null;
  return (
    <p className="success-notice" role="status">
      {notice}
    </p>
  );
}

/** Error + success state with a helper that wraps async actions. */
export function useFeedback() {
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [validationTarget, setValidationTarget] = useState("");
  const run = useCallback(
    async <T,>(
      action: () => Promise<T>,
      success?: string,
    ): Promise<T | undefined> => {
      const formId =
        typeof document === "undefined"
          ? ""
          : document.activeElement?.closest("form")?.id || "";
      setBusy(true);
      setError("");
      setFieldErrors({});
      setNotice("");
      try {
        const result = await action();
        if (success) setNotice(success);
        return result;
      } catch (err) {
        setValidationTarget(formId);
        setFieldErrors(err instanceof ApiError ? err.fieldErrors : {});
        setError(message(err));
        return undefined;
      } finally {
        setBusy(false);
      }
    },
    [],
  );
  return {
    error,
    notice,
    busy,
    run,
    setError,
    setNotice,
    fieldErrors,
    validationTarget,
  };
}

export function PageHeading({
  eyebrow,
  title,
  text,
  action,
}: {
  eyebrow: string;
  title: string;
  text?: string;
  action?: ReactNode;
}) {
  return (
    <div className="page-heading">
      <div>
        <span className="eyebrow">{eyebrow.toUpperCase()}</span>
        <h1>{title}</h1>
        {text && <p>{text}</p>}
      </div>
      {action}
    </div>
  );
}

export function Panel({
  title,
  aside,
  children,
  className = "",
  id,
}: {
  title?: ReactNode;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
  id?: string;
}) {
  return (
    <section className={`panel ${className}`} id={id}>
      {(title || aside) && (
        <div className="panel-title">
          {title && <h2>{title}</h2>}
          {aside && <span className="subtle">{aside}</span>}
        </div>
      )}
      {children}
    </section>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="empty-copy">{children}</p>;
}

export function Pill({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "good" | "warn" | "bad";
}) {
  return <span className={`pill pill-${tone}`}>{children}</span>;
}

export function statusTone(
  status: string,
): "neutral" | "good" | "warn" | "bad" {
  if (
    [
      "sent",
      "published",
      "complete",
      "processed",
      "delivered",
      "active",
      "paid",
      "ready",
      "completed",
      "concluded",
      "running",
    ].includes(status)
  )
    return "good";
  if (
    ["failed", "needs_review", "unknown", "canceled", "past_due"].includes(
      status,
    )
  )
    return "bad";
  if (
    [
      "pending",
      "scheduled",
      "waiting",
      "verifying",
      "needs_human",
      "processing",
    ].includes(status)
  )
    return "warn";
  return "neutral";
}

export function Modal({
  title,
  onClose,
  children,
  role = "dialog",
  descriptionId,
  initialFocusRef,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  role?: "dialog" | "alertdialog";
  descriptionId?: string;
  initialFocusRef?: RefObject<HTMLElement | null>;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = dialogRef.current;
    const opener =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    const overflow = document.body.style.overflow;
    dialog?.showModal();
    initialFocusRef?.current?.focus();
    document.body.style.overflow = "hidden";
    return () => {
      dialog?.close();
      document.body.style.overflow = overflow;
      if (opener?.isConnected) opener.focus();
    };
  }, [initialFocusRef]);
  return (
    <dialog
      ref={dialogRef}
      className="modal-backdrop"
        role={role}
      aria-label={title}
        aria-describedby={descriptionId}
      onKeyDown={(event) => {
        if (event.key !== "Tab") return;
        const controls = Array.from(
          event.currentTarget.querySelectorAll<HTMLElement>(
            "button, a[href], input, select, textarea, [tabindex]",
          ),
        ).filter(
          (element) =>
            element.tabIndex >= 0 &&
            !element.matches(":disabled") &&
            element.getClientRects().length > 0,
        );
        const first = controls[0];
        const last = controls[controls.length - 1];
        if (!first) {
          event.preventDefault();
          event.currentTarget.focus();
          return;
        }
        if (
          event.shiftKey &&
          (document.activeElement === first ||
            document.activeElement === event.currentTarget)
        ) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
    >
      <section className="modal">
        <button
          className="icon-button close-modal"
          aria-label="Close dialog"
          onClick={onClose}
        >
          <X size={20} />
        </button>
        <h2>{title}</h2>
        {children}
      </section>
    </dialog>
  );
}

export function Stat({
  value,
  label,
  detail,
  icon,
}: {
  value: string;
  label: string;
  detail?: string;
  icon?: ReactNode;
}) {
  return (
    <article className="stat-card">
      <div className="stat-top">
        {icon && <span className="stat-icon">{icon}</span>}
        <span>{label}</span>
      </div>
      <strong>{value}</strong>
      {detail && <p>{detail}</p>}
    </article>
  );
}

export function Table({
  head,
  children,
}: {
  head: string[];
  children: ReactNode;
}) {
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            {head.map((label) => (
              <th key={label}>{label}</th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

export function CopyField({ label, value }: { label: string; value: string }) {
  return (
    <label className="copy-field">
      {label}
      <input
        value={value}
        readOnly
        onFocus={(event) => event.currentTarget.select()}
      />
    </label>
  );
}
