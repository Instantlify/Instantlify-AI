import type { Metadata } from "next";
import "./globals.css";

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
