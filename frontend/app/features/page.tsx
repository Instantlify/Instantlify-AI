import type { Metadata } from "next";
import { LandingPage } from "@/components/landing-page";
import { PublicHelpLinks } from "@/components/public-help-links";

export const metadata: Metadata = {
  title: "Explore the product · Nemio",
  description:
    "Explore Nemio automations, AI assistants, shared inbox and integrations with interactive product previews.",
};

export default function Features() {
  return <LandingPage detailed helpLinks={<PublicHelpLinks />} />;
}
