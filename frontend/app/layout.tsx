import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Decision Harness",
  description: "A configurable AI decision council that debates, out loud, with a full audit trail.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
