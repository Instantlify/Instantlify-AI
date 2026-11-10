export type FormField = {
  id: string;
  label: string;
  type:
    | "text"
    | "textarea"
    | "email"
    | "tel"
    | "select"
    | "number"
    | "date"
    | "url"
    | "checkboxes"
    | "yes_no"
    | "rating"
    | "opinion_scale"
    | "file_upload"
    | "signature"
    | "cover_card"
    | "calendly"
    | "calcom"
    | "tidycal"
    | "contact_block"
    | "contact_first_name"
    | "contact_last_name"
    | "contact_full_name"
    | "contact_email"
    | "contact_phone"
    | "contact_business"
    | "contact_instagram"
    | "contact_linkedin"
    | "contact_x";
  required: boolean;
  options?: string[];
  min?: number;
  max?: number;
  description?: string;
  booking_url?: string;
  include_phone?: boolean;
};
export type FormAction = {
  integration_id: string;
  operation: "send_email" | "sync_lead" | "notify" | "webhook";
  text?: string;
  subject?: string;
};
export type FormFileAnswer = {
  name: string;
  data?: string;
  size?: number;
  sha256?: string;
  download_url?: string;
};
export type FormContactAnswer = {
  first_name: string;
  last_name: string;
  email: string;
  phone: string;
};
export type FormAnswer = string | string[] | FormFileAnswer | FormContactAnswer;
export type LeadForm = {
  id: string;
  slug: string;
  title: string;
  description: string;
  fields: FormField[];
  branching?: { field_id: string; answer: string; next_id: string | null }[];
  theme?: { primary?: string; background?: string; text?: string };
  redirect_url?: string;
  submission_tags?: string[];
  button_align?: "left" | "center" | "right";
  closed?: boolean;
  capture_contacts?: boolean;
  consent_text: string;
  success_text: string;
  published: boolean;
  submission_actions?: FormAction[];
  submissions?: number;
};
export type FormResponse = {
  actions?: {
    id: string;
    operation: string;
    status: string;
    error: string;
    accepted?: boolean;
  }[];
  action_errors?: { action: number; error: string }[];
  id: string;
  lead_id: string | null;
  created_at: string;
  answers: Record<string, FormAnswer>;
  consent_text: string;
  link_id: string | null;
};
export type CreatorKit = {
  slug: string;
  name: string;
  headline: string;
  bio: string;
  contact_email: string;
  published: boolean;
  links: { label: string; url: string }[];
  statistics: { label: string; value: string }[];
  live_connection_ids?: string[];
  live_statistics?: {
    label: string;
    value: string;
    account: string;
    as_of: string;
  }[];
  live_stats_error?: string;
  live_stats_checked_at?: string | null;
  services: { title: string; description: string }[];
};

export const defaultForm = (): Omit<LeadForm, "id"> => ({
  capture_contacts: true,
  submission_actions: [],
  slug: "",
  title: "Contact us",
  description: "Tell us how we can help.",
  fields: [
    { id: "name", label: "Your name", type: "text", required: true },
    { id: "email", label: "Email address", type: "email", required: true },
    { id: "message", label: "Your message", type: "textarea", required: false },
  ],
  consent_text: "I agree to be contacted about my enquiry.",
  success_text: "Thank you. Your response has been received.",
  published: false,
});
