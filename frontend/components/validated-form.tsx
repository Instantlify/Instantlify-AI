"use client";

import {
  createContext,
  createElement,
  useContext,
  useEffect,
  useId,
  useRef,
  useState,
  type ChangeEvent,
  type ComponentPropsWithRef,
} from "react";
import { fieldLabel, type FieldErrors } from "@/lib/form-errors";

type Control = HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement;
const isControl = (element: EventTarget): element is Control =>
  element instanceof HTMLInputElement ||
  element instanceof HTMLSelectElement ||
  element instanceof HTMLTextAreaElement;

function labelFor(control: Control, forMessage = true) {
  const explicit = control.getAttribute("aria-label");
  if (explicit)
    return forMessage ? explicit.replace(/\s*\*\s*$/, "") : explicit;
  const label = control.labels?.[0]?.cloneNode(true) as HTMLElement | undefined;
  label
    ?.querySelectorAll(
      "input, select, textarea, small, .field-error, .field-required, .field-hint, .hint, [aria-hidden=true]",
    )
    .forEach((node) => node.remove());
  const text =
    label?.textContent?.replace(/\s+/g, " ").trim() ||
    fieldLabel(control.name) ||
    "this field";
  return forMessage ? text.replace(/\s*\*\s*$/, "") : text;
}

function controlError(control: Control) {
  if (!control.willValidate) return "";
  const label = labelFor(control).toLowerCase();
  if (
    control.required &&
    (control.validity.valueMissing ||
      (control.type !== "checkbox" &&
        control.type !== "radio" &&
        !control.value.trim()))
  )
    return control.name === "slug"
      ? "Choose a public address, such as contact-us."
      : control.type === "checkbox"
        ? "Please tick this box to continue."
        : control.tagName === "SELECT"
          ? `Choose ${label}.`
          : `Enter ${label}.`;
  if (control.validity.badInput) return "Enter a valid number.";
  if (!control.value) return "";
  const hint = control.getAttribute("data-validation-hint");
  if (control.validity.typeMismatch)
    return control.type === "email"
      ? "Enter a valid email address, such as name@example.com."
      : "Enter a complete web address starting with https://.";
  const pattern = control.getAttribute("pattern");
  let patternMismatch = control.validity.patternMismatch;
  if (pattern) {
    // Also check legacy patterns that newer browsers may decline to compile.
    try {
      patternMismatch ||= !new RegExp(`^(?:${pattern})$`, "u").test(
        control.value,
      );
    } catch {
      /* Native validity remains authoritative for newer syntax. */
    }
  }
  if (patternMismatch)
    return (
      hint ||
      (control.name === "slug"
        ? "Use lowercase letters, numbers and hyphens, such as my-page."
        : `Check ${label} and use the format shown.`)
    );
  const minimum = Number(control.getAttribute("minlength"));
  const maximum = Number(control.getAttribute("maxlength"));
  if (minimum > 0 && control.value.length < minimum)
    return `Use at least ${minimum} characters for ${label}.`;
  if (maximum > 0 && control.value.length > maximum)
    return `Keep ${label} to ${maximum} characters or fewer.`;
  if (control.validity.rangeUnderflow)
    return `Enter ${control.getAttribute("min")} or more.`;
  if (control.validity.rangeOverflow)
    return `Enter ${control.getAttribute("max")} or less.`;
  if (control.validity.badInput || control.validity.stepMismatch)
    return "Enter a valid number using the amount shown.";
  return control.validity.valid ? "" : hint || `Check ${label} and try again.`;
}

function focusControl(control?: Control) {
  if (!control) return;
  let parent = control.parentElement;
  while (parent) {
    if (parent instanceof HTMLDetailsElement) parent.open = true;
    parent = parent.parentElement;
  }
  control.focus();
}

type Validation = {
  errors: FieldErrors;
  labels: Record<string, string>;
  server: FieldErrors;
  dismissed: Set<string>;
  update: (control: Control) => void;
};
const ValidationContext = createContext<Validation | null>(null);

export function ValidatedForm({
  children,
  onSubmit,
  fieldErrors = {},
  validationTarget,
  onEdit,
  validate,
  ...props
}: ComponentPropsWithRef<"form"> & {
  fieldErrors?: FieldErrors;
  validationTarget?: string;
  onEdit?: () => void;
  validate?: (form: HTMLFormElement) => FieldErrors;
}) {
  const [errors, setErrors] = useState<FieldErrors>({});
  const [labels, setLabels] = useState<Record<string, string>>({});
  const [dismissed, setDismissed] = useState(new Set<string>());
  const [submitted, setSubmitted] = useState(false);
  const lastErrors = useRef(fieldErrors);
  const generatedId = useId();
  const formId = props.id || `form-${generatedId}`;
  const ownsErrors =
    validationTarget === undefined || validationTarget === formId;
  const server = submitted && ownsErrors ? fieldErrors : {};
  useEffect(() => {
    if (!submitted || !ownsErrors || lastErrors.current === fieldErrors) return;
    lastErrors.current = fieldErrors;
    const form = document.getElementById(formId) as HTMLFormElement | null;
    focusControl(
      [...(form?.elements || [])]
        .filter(isControl)
        .find((control) => fieldErrors[control.name]),
    );
  }, [fieldErrors, submitted, formId, ownsErrors]);
  function update(control: Control) {
    const label = labelFor(control, false);
    setLabels((current) => ({ ...current, [control.id]: label }));
    setDismissed((current) => new Set(current).add(control.name));
    setErrors((current) => {
      const next = { ...current };
      const problem = controlError(control);
      if (problem) next[control.id] = problem;
      else delete next[control.id];
      return next;
    });
  }
  function submit(
    event: Parameters<
      NonNullable<ComponentPropsWithRef<"form">["onSubmit"]>
    >[0],
  ) {
    const controls = [...event.currentTarget.elements].filter(isControl);
    setLabels(
      Object.fromEntries(
        controls.map((control) => [control.id, labelFor(control, false)]),
      ),
    );
    const next: FieldErrors = {};
    for (const control of controls) {
      const problem = controlError(control);
      if (problem) next[control.id] = problem;
    }
    for (const [name, problem] of Object.entries(
      validate?.(event.currentTarget) || {},
    )) {
      const control = controls.find(
        (item) => item.name === name || item.id === name,
      );
      next[control?.id || name] = problem;
    }
    setErrors(next);
    setDismissed(new Set());
    setSubmitted(true);
    lastErrors.current = fieldErrors;
    if (Object.keys(next).length) {
      event.preventDefault();
      focusControl(controls.find((control) => next[control.id]));
      return;
    }
    onSubmit?.(event);
  }
  return (
    <ValidationContext.Provider
      value={{ errors, labels, server, dismissed, update }}
    >
      <form
        {...props}
        id={formId}
        noValidate
        onSubmit={submit}
        onChangeCapture={(event) => {
          props.onChangeCapture?.(event);
          onEdit?.();
        }}
        onInvalidCapture={(event) => {
          event.preventDefault();
          if (isControl(event.target)) update(event.target);
        }}
      >
        {Object.keys(errors).length > 0 && (
          <p className="form-validation-summary" role="alert">
            Please check the highlighted fields before continuing.
          </p>
        )}
        {children}
      </form>
    </ValidationContext.Provider>
  );
}

type ControlProps =
  | ComponentPropsWithRef<"input">
  | ComponentPropsWithRef<"select">
  | ComponentPropsWithRef<"textarea">;
function ValidatedControl({
  tag,
  fieldProps,
}: {
  tag: "input" | "select" | "textarea";
  fieldProps: ControlProps;
}) {
  const context = useContext(ValidationContext);
  const generatedId = useId();
  const id = fieldProps.id || `field-${generatedId}`;
  if (!context) return createElement<ControlProps>(tag, fieldProps);
  const name = fieldProps.name || "";
  const error =
    context.errors[id] ||
    (name && !context.dismissed.has(name) ? context.server[name] : "");
  const errorId = `${id}-error`;
  const describedBy = [fieldProps["aria-describedby"], error ? errorId : ""]
    .filter(Boolean)
    .join(" ");
  const change = fieldProps.onChange as
    ((event: ChangeEvent<Control>) => void) | undefined;
  const blur = fieldProps.onBlur as
    ((event: React.FocusEvent<Control>) => void) | undefined;
  const checkbox =
    tag === "input" &&
    ["checkbox", "radio", "hidden"].includes(
      (fieldProps as ComponentPropsWithRef<"input">).type || "",
    );
  return (
    <>
      {fieldProps.required && !checkbox && (
        <span className="field-required" aria-hidden="true" />
      )}
      {createElement(tag as string, {
        ...fieldProps,
        id,
        "aria-label": fieldProps["aria-label"] || context.labels[id],
        "aria-invalid": error ? true : fieldProps["aria-invalid"],
        "aria-describedby": describedBy || undefined,
        onChange: (event: ChangeEvent<Control>) => {
          change?.(event);
          if (error) context.update(event.currentTarget);
        },
        onBlur: (event: React.FocusEvent<Control>) => {
          blur?.(event);
          // Showing a new error during mousedown can move the submit button
          // before mouseup. Validate all fields on submit, then recheck edits.
          if (error) context.update(event.currentTarget);
        },
      })}
      {error && (
        <span className="field-error" id={errorId} aria-hidden="true">
          {error}
        </span>
      )}
    </>
  );
}

export const ValidatedInput = (props: ComponentPropsWithRef<"input">) => (
  <ValidatedControl tag="input" fieldProps={props} />
);
export const ValidatedSelect = (props: ComponentPropsWithRef<"select">) => (
  <ValidatedControl tag="select" fieldProps={props} />
);
export const ValidatedTextarea = (props: ComponentPropsWithRef<"textarea">) => (
  <ValidatedControl tag="textarea" fieldProps={props} />
);

export function ValidationError({ name }: { name: string }) {
  const context = useContext(ValidationContext);
  const error = context?.errors[name] || context?.server[name];
  return error ? (
    <p className="field-error" role="alert">
      {error}
    </p>
  ) : null;
}
