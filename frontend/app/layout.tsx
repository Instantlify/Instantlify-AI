import type { Metadata } from "next";
import "./globals.css";
import "./features.css";
import "./refresh.css";
import "./landing.css";
import "./landing-depth.css";
import "@xyflow/react/dist/style.css";

export const metadata: Metadata = {
  title: "Nemio · Your workspace",
  description: "One workspace for your sales conversations.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
