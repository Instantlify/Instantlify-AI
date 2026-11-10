import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { LandingPage } from "@/components/landing-page";
import { PublicHelpLinks } from "@/components/public-help-links";

export const metadata: Metadata = {
  title: "Instantlify · Turn conversations into customers",
  description:
    "Grow your business with Instantlify: AI sales agents, messaging automation, a unified inbox, CRM, bookings and payments. Explore plans and get started.",
  openGraph: {
    title: "Instantlify · Turn conversations into customers",
    description:
      "Your conversations, team and sales automations. One connected workspace.",
    type: "website",
  },
};

export default async function Home({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const query = await searchParams;
  // Keep previously issued invitation and pricing links working.
  if (query.invite || query.plan) {
    const params = new URLSearchParams();
    for (const key of ["invite", "plan", "interval"]) {
      if (typeof query[key] === "string") params.set(key, query[key]);
    }
    if (query.plan) params.set("mode", "signup");
    redirect(`/auth?${params.toString()}`);
  }
  return <LandingPage helpLinks={<PublicHelpLinks />} />;
}
