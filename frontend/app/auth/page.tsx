import type { Metadata } from "next";
import AuthPage from "@/components/auth";

export const metadata: Metadata = {
  title: "Sign in or get started · Nemio",
  robots: { index: false, follow: true },
};

export default async function Page({
  searchParams,
}: {
  searchParams: Promise<{ mode?: string }>;
}) {
  const query = await searchParams;
  return <AuthPage signup={query.mode === "signup"} />;
}
