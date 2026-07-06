import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "RecallAI — Knowledge Decay Agent",
  description: "An agentic AI system that models user knowledge decay using FSRS and plans optimal revision schedules.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
