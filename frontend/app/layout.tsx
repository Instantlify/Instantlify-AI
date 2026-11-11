import { ConfirmationProvider } from "@/components/confirmation-provider";
import { SupportWidget } from "@/components/support-center";
import { LanguageProvider } from "@/lib/i18n";
import type { Metadata } from "next";
import localFont from "next/font/local";
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

// Official variable fonts and their licenses are bundled for offline builds.
const body = localFont({
  src: "./fonts/dm-sans-variable.ttf",
  weight: "100 1000",
  variable: "--font-body",
  display: "swap",
});
const display = localFont({
  src: "./fonts/manrope-variable.ttf",
  weight: "200 800",
  variable: "--font-display",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Instantlify · Your workspace",
  description: "One workspace for your sales conversations.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className={`${body.variable} ${display.variable}`}>
      <body>
        <LanguageProvider>
          <ConfirmationProvider>
            {children}
            <SupportWidget />
          </ConfirmationProvider>
        </LanguageProvider>
      </body>
    </html>
  );
}
