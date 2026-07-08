import type { Metadata } from "next";
import Script from "next/script";

export const metadata: Metadata = {
  title: "RecallAI — AI-Powered Spaced Repetition for DSA",
  description:
    "An agentic AI system that models memory decay with FSRS, maps topic dependencies, and generates your optimal daily study plan.",
};

export default function LandingLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      {children}
    </>
  );
}
