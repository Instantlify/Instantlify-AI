import type { FormAnswer, FormField, LeadForm } from "./portal-tools";

export const FORM_TYPES: Record<FormField["type"], string> = {
  text: "Short answer",
  textarea: "Long answer",
  email: "Email address",
  tel: "Phone number",
  select: "Dropdown choices",
  number: "Number",
  date: "Date",
  url: "Website address",
  checkboxes: "Multiple choices",
  yes_no: "Yes or No",
  rating: "Star rating",
  opinion_scale: "Opinion scale",
  file_upload: "File upload",
  signature: "Signature",
  cover_card: "Welcome card",
  calendly: "Calendly booking",
  calcom: "Cal.com booking",
  tidycal: "TidyCal booking",
  contact_block: "Contact details",
  contact_first_name: "Contact first name",
  contact_last_name: "Contact last name",
  contact_full_name: "Contact full name",
  contact_email: "Contact email",
  contact_phone: "Contact phone",
  contact_business: "Contact company",
  contact_instagram: "Contact Instagram",
  contact_linkedin: "Contact LinkedIn",
  contact_x: "Contact X profile",
};
export const NON_INPUT_TYPES = ["cover_card", "calendly", "calcom", "tidycal"];
export const EMAIL_TYPES = ["email", "contact_email", "contact_block"];

export function visibleFormFields(
  form: Pick<LeadForm, "fields" | "branching">,
  answers: Record<string, FormAnswer>,
) {
  const result: FormField[] = [];
  const visited = new Set<string>();
  let index = 0;
  while (index < form.fields.length) {
    const field = form.fields[index];
    if (visited.has(field.id)) break;
    visited.add(field.id);
    result.push(field);
    const branch = form.branching?.find(
      (rule) => rule.field_id === field.id && rule.answer === answers[field.id],
    );
    if (branch) {
      if (branch.next_id === null) break;
      const next = form.fields.findIndex((item) => item.id === branch.next_id);
      if (next <= index) break;
      index = next;
    } else index += 1;
  }
  return result;
}
