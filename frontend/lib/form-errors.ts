/** Translate API field names and validation messages into client-facing language. */
export type FieldErrors = Record<string, string>;

const labels: Record<string, string> = {
  slug: "Public address",
  fields: "Questions",
  consent_text: "Permission message",
  success_text: "Thank-you message",
  non_field_errors: "",
  detail: "",
  submission_actions: "Actions after a response",
  integration_id: "Connected service",
  connection_id: "Connected account",
  workspace_id: "Workspace",
  contact_email: "Contact email",
  amount_cents: "Price",
  redirect_url: "Return address",
};

export function fieldLabel(key: string): string {
  if (key in labels) return labels[key];
  const question = key.match(/^fields\.(\d+)\.(.+)$/);
  if (question)
    return `Question ${Number(question[1]) + 1} ${question[2] === "id" ? "answer name" : question[2] === "label" ? "text" : fieldLabel(question[2]).toLowerCase()}`;
  return key
    .replace(/[_\.]+/g, " ")
    .replace(/^./, (char) => char.toUpperCase());
}

export function friendlyError(text: string, field = ""): string {
  const label = fieldLabel(field).toLowerCase();
  if (
    /^(?:This field is required\.?|This field may not be (?:blank|null)\.?|Please provide [\w -]+\.?)$/i.test(
      text,
    )
  )
    return field === "slug"
      ? "Choose a public address, such as contact-us."
      : label
        ? `Enter ${label}.`
        : "Complete the required information.";
  if (/slug/i.test(text) && /already|unique|exists|in use/i.test(text))
    return "This public address is already in use. Please choose another.";
  if (/slug/i.test(text) && /provide|enter|valid/i.test(text))
    return "Choose a public address using letters, numbers and hyphens, such as contact-us.";
  if (/valid (?:integer|number|decimal)/i.test(text))
    return "Enter a valid number.";
  if (/valid email/i.test(text))
    return "Enter a valid email address, such as name@example.com.";
  if (/valid URL/i.test(text))
    return "Enter a complete web address starting with https://.";
  if (/Invalid pk|Invalid UUID|does not exist/i.test(text))
    return `Choose an available ${label || "option"}.`;
  if (/is not a valid choice/i.test(text))
    return "Choose one of the available options.";
  if (
    /STRIPE_|DJANGO_|DATABASE_URL|Traceback|IntegrityError|KeyError|TypeError|\[object Object\]/.test(
      text,
    )
  )
    return "We couldn’t complete this request. Please try again or contact support.";
  if (
    /Include a required email field|including an email field with ID email/i.test(
      text,
    )
  )
    return "Add an Email address question and keep it required so responses can be saved to your contacts.";
  if (/unique lowercase field IDs/i.test(text))
    return "Each question needs a different answer name. Use lowercase letters, numbers and underscores, starting with a letter.";
  if (/unique|already exists/i.test(text) && field)
    return `This ${label} is already in use. Please choose another.`;
  if (/^\w+(?:_\w+)+$/.test(text))
    return "We couldn’t save this change. Check your details and try again.";
  return text
    .replace(/\bslug\b/gi, "public address")
    .replace(/\bfield IDs?\b/gi, "answer names")
    .replace(/\bID email\b/gi, 'answer name "email"')
    .replace(/\bCRM capture\b/gi, "saving responses to your contacts")
    .replace(/\bfield configuration\b/gi, "question settings")
    .replace(/\bnon_field_errors\b/g, "")
    .replace(/\bThis field\b/g, label ? `The ${label}` : "This information");
}

export function validationErrors(data: unknown, prefix = ""): FieldErrors {
  if (typeof data === "string") {
    const field =
      ["detail", "non_field_errors", ""].includes(prefix) &&
      /\bslug\b/i.test(data)
        ? "slug"
        : prefix;
    return { [field]: friendlyError(data, field) };
  }
  if (Array.isArray(data)) {
    if (data.every((item) => typeof item === "string"))
      return {
        [prefix]: data.map((item) => friendlyError(item, prefix)).join(" "),
      };
    return Object.assign(
      {},
      ...data.map((item, index) =>
        validationErrors(item, `${prefix}.${index}`),
      ),
    );
  }
  if (data && typeof data === "object")
    return Object.assign(
      {},
      ...Object.entries(data).map(([key, value]) =>
        validationErrors(value, prefix ? `${prefix}.${key}` : key),
      ),
    );
  return {};
}

export function errorSummary(data: unknown): string {
  const errors = validationErrors(data);
  return (
    Object.entries(errors)
      .map(([key, text]) => {
        const label = fieldLabel(key);
        return label && !text.toLowerCase().includes(label.toLowerCase())
          ? `${label}: ${text}`
          : text;
      })
      .join(" ") || "Something went wrong. Please try again."
  );
}
