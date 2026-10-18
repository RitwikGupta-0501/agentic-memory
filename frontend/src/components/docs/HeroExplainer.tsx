"use client";

import React from "react";
import Link from "next/link";
import { ArrowUpRight, Brain, Clock, ShieldCheck, Sparkle } from "@phosphor-icons/react";

export function HeroExplainer() {
  return (
    <section className="relative mx-auto max-w-5xl px-4 pt-12 pb-20 text-center">
      {/* Main Headline */}
      <h1 className="text-4xl sm:text-5xl md:text-6xl font-bold tracking-tight text-white max-w-4xl mx-auto leading-[1.12]">
        Why AI Agents Have Amnesia — <br className="hidden sm:inline" />
        <span className="text-transparent bg-clip-text bg-gradient-to-r from-m3-primary via-m3-secondary to-tier-semantic">
          And How Graph Memory Fixes It
        </span>
      </h1>

      {/* Subtitle / Plain-English Explanation */}
      <p className="mt-6 text-base sm:text-lg text-m3-on-surface-variant max-w-2xl mx-auto leading-relaxed">
        Today's AI agents either forget everything the instant a session ends, or drown in flat vector databases that retrieve obsolete, contradictory text chunks. AegisGraph gives agents an actual brain with <strong className="text-white">4 interconnected memory tiers</strong>, built natively on <strong className="text-white">FalkorDB</strong>.
      </p>

      {/* CTAs */}
      <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
        <Link
          href="/"
          className="group flex items-center gap-2 px-6 py-3 rounded-full bg-m3-primary text-m3-on-primary font-semibold text-sm transition-all hover:bg-white active:scale-95 shadow-glow-primary"
        >
          <span>Try the Interactive App</span>
          <div className="w-6 h-6 rounded-full bg-m3-on-primary/10 flex items-center justify-center group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform">
            <ArrowUpRight size={13} weight="bold" />
          </div>
        </Link>

        <a
          href="#memory-tiers"
          className="px-6 py-3 rounded-full bg-white/5 hover:bg-white/10 text-m3-on-surface font-medium text-sm border border-white/10 transition-all"
        >
          Explore the 4 Tiers
        </a>
      </div>

      {/* 3 Key Breakthrough Stats / Cards */}
      <div className="mt-16 grid grid-cols-1 sm:grid-cols-3 gap-4 text-left">
        <div className="p-5 rounded-2xl bg-m3-surface-container-lowest/80 border border-white/10 shadow-double-bezel backdrop-blur-md">
          <div className="flex items-center gap-2.5 text-tier-episodic mb-2">
            <Brain size={20} weight="duotone" />
            <span className="text-xs font-semibold tracking-wider uppercase">4 Cognitive Tiers</span>
          </div>
          <p className="text-sm text-m3-on-surface-variant leading-relaxed">
            Working, Episodic, Semantic, and Procedural running concurrently.
          </p>
        </div>

        <div className="p-5 rounded-2xl bg-m3-surface-container-lowest/80 border border-white/10 shadow-double-bezel backdrop-blur-md">
          <div className="flex items-center gap-2.5 text-tier-semantic mb-2">
            <Clock size={20} weight="duotone" />
            <span className="text-xs font-semibold tracking-wider uppercase">0 Contradiction Drift</span>
          </div>
          <p className="text-sm text-m3-on-surface-variant leading-relaxed">
            Bi-temporal graph states invalidate superseded facts without deleting history, eliminating hallucinations when world facts change.
          </p>
        </div>

        <div className="p-5 rounded-2xl bg-m3-surface-container-lowest/80 border border-white/10 shadow-double-bezel backdrop-blur-md">
          <div className="flex items-center gap-2.5 text-tier-procedural mb-2">
            <ShieldCheck size={20} weight="duotone" />
            <span className="text-xs font-semibold tracking-wider uppercase">Self-Correcting Reflexion</span>
          </div>
          <p className="text-sm text-m3-on-surface-variant leading-relaxed">
            Tool errors and execution failures automatically compile into permanent procedural guardrails so the agent never repeats mistakes.
          </p>
        </div>
      </div>
    </section>
  );
}
