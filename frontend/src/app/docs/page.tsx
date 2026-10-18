import React from "react";
import type { Metadata } from "next";
import { DocsHeader } from "@/components/docs/DocsHeader";
import { HeroExplainer } from "@/components/docs/HeroExplainer";
import { ProblemBento } from "@/components/docs/ProblemBento";
import { MemoryTiersVisual } from "@/components/docs/MemoryTiersVisual";
import { ResearchCitations } from "@/components/docs/ResearchCitations";
import { IsolationExplainer } from "@/components/docs/IsolationExplainer";
import { DocsFooter } from "@/components/docs/DocsFooter";

export const metadata: Metadata = {
  title: "AegisGraph Architecture & Research Guide",
  description: "How 4-Tier Cognitive Graph Memory solves AI amnesia, hallucinations, and privacy leaks using FalkorDB.",
};

export default function DocsPage() {
  return (
    <div className="min-h-screen bg-m3-surface-dim bg-ambient-mesh text-m3-on-surface antialiased selection:bg-m3-primary/20 selection:text-m3-primary pt-4 pb-12">
      <DocsHeader />
      <main>
        <HeroExplainer />
        <ProblemBento />
        <MemoryTiersVisual />
        <ResearchCitations />
        <IsolationExplainer />
      </main>
      <DocsFooter />
    </div>
  );
}
