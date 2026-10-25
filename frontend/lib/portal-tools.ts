export type FormField = {
  id: string;
  label: string;
  type: "text" | "textarea" | "email" | "tel" | "select";
  required: boolean;
  options?: string[];
};
export type LeadForm = {
  id: string;
  slug: string;
  title: string;
  description: string;
  fields: FormField[];
  consent_text: string;
  success_text: string;
  published: boolean;
  submissions?: number;
};
export type FormResponse = {
  id: string;
  lead_id: string | null;
  created_at: string;
  answers: Record<string, string>;
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
  services: { title: string; description: string }[];
};

export const defaultForm = (): Omit<LeadForm, "id"> => ({
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
