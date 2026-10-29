import { SupportWidget } from "@/components/support-center";
import type { Metadata } from "next";
import { DM_Sans, Manrope } from "next/font/google";
import "./globals.css";
import "./features.css";
import "./refresh.css";
import "./landing.css";
import "./landing-depth.css";
import "./landing-motion.css";
import "./meta.css";
import "./sidebar.css";
import "./validation.css";
import "./brand.css";
import "@xyflow/react/dist/style.css";
import "./theme.css";
import "./workspace-theme.css";
import "./mission-control.css";
import "./support.css";

// Self-hosted at build time; meta.css points the shared font tokens at these.
const body = DM_Sans({ subsets: ["latin"], variable: "--font-body" });
const display = Manrope({ subsets: ["latin"], variable: "--font-display" });

export const metadata: Metadata = {
  title: "Nemio · Your workspace",
  description: "One workspace for your sales conversations.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${body.variable} ${display.variable}`}>
      <body>
        {children}
        <SupportWidget />
      </body>
    </html>
  );
}
