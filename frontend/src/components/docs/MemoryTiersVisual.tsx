"use client";

import React from "react";
import { Lightning, Bookmarks, TreeStructure, ShieldCheck } from "@phosphor-icons/react";

export function MemoryTiersVisual() {
  return (
    <section id="memory-tiers" className="relative mx-auto max-w-5xl px-4 py-16 border-t border-white/5">
      {/* Section Header */}
      <div className="text-center max-w-3xl mx-auto mb-14">
        <span className="text-[11px] font-semibold tracking-widest uppercase text-m3-primary">
          Cognitive Architecture
        </span>
        <h2 className="text-2xl sm:text-3xl md:text-4xl font-bold tracking-tight text-white mt-2">
          The 4 Memory Tiers: An AI Modeled After Human Cognition
        </h2>
        <p className="mt-3 text-sm sm:text-base text-m3-on-surface-variant leading-relaxed">
          Human intelligence doesn't store everything in one disorganized pile. Your brain separates active focus, personal experiences, factual knowledge, and muscle memory. AegisGraph brings this exact four-part architecture to AI agents.
        </p>
      </div>

      {/* 4 Memory Tiers Cards Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Tier 1: Working Memory */}
        <div className="p-6 sm:p-7 rounded-2xl bg-m3-surface-container-low/80 border border-tier-working/20 shadow-double-bezel relative overflow-hidden group hover:border-tier-working/40 transition-colors">
          <div className="absolute top-0 right-0 w-32 h-32 bg-tier-working/5 rounded-full blur-2xl pointer-events-none" />
          <div className="flex items-center gap-3.5 mb-4">
            <div className="w-10 h-10 rounded-xl bg-tier-working/10 border border-tier-working/30 text-tier-working flex items-center justify-center">
              <Lightning size={22} weight="fill" />
            </div>
            <div>
              <div className="text-xs font-mono uppercase tracking-wider text-tier-working">Tier 1 • Active Attention</div>
              <h3 className="text-lg font-bold text-white">Working Memory (The Scratchpad / RAM)</h3>
            </div>
          </div>

          <p className="text-sm sm:text-[15px] text-m3-on-surface-variant leading-relaxed">
            <strong className="text-white">Brain Analogy:</strong> Your conscious focus while solving a problem right now. What you need in mind to finish the task at hand.
          </p>

          <div className="mt-5 p-4 rounded-xl bg-black/40 border border-white/5 text-xs sm:text-sm space-y-2">
            <div className="flex items-start gap-2 text-m3-on-surface">
              <span className="text-tier-working font-mono font-medium">▸ In AegisGraph:</span>
              <span>Task decomposition into a Directed Acyclic Graph (DAG) of subtasks with concurrent claim locks.</span>
            </div>
            <div className="flex items-start gap-2 text-m3-on-surface-variant">
              <span className="text-white/40 font-mono">▸ FalkorDB Nodes:</span>
              <span className="font-mono text-xs text-amber-200/90 font-medium">(:TaskRun)-[:HAS_SUBTASK]&rarr;(:SubTask)-[:PINNED_CONTEXT]&rarr;(m)</span>
            </div>
          </div>
        </div>

        {/* Tier 2: Episodic Memory */}
        <div className="p-6 sm:p-7 rounded-2xl bg-m3-surface-container-low/80 border border-tier-episodic/20 shadow-double-bezel relative overflow-hidden group hover:border-tier-episodic/40 transition-colors">
          <div className="absolute top-0 right-0 w-32 h-32 bg-tier-episodic/5 rounded-full blur-2xl pointer-events-none" />
          <div className="flex items-center gap-3.5 mb-4">
            <div className="w-10 h-10 rounded-xl bg-tier-episodic/10 border border-tier-episodic/30 text-tier-episodic flex items-center justify-center">
              <Bookmarks size={22} weight="fill" />
            </div>
            <div>
              <div className="text-xs font-mono uppercase tracking-wider text-tier-episodic">Tier 2 • Past Experiences</div>
              <h3 className="text-lg font-bold text-white">Episodic Memory (The Personal Diary)</h3>
            </div>
          </div>

          <p className="text-sm sm:text-[15px] text-m3-on-surface-variant leading-relaxed">
            <strong className="text-white">Brain Analogy:</strong> Remembering a conversation you had with a colleague last week, or what you ate for lunch yesterday.
          </p>

          <div className="mt-5 p-4 rounded-xl bg-black/40 border border-white/5 text-xs sm:text-sm space-y-2">
            <div className="flex items-start gap-2 text-m3-on-surface">
              <span className="text-tier-episodic font-mono font-medium">▸ In AegisGraph:</span>
              <span>Chronologically chained dialogue turns ranked dynamically by recency decay and importance.</span>
            </div>
            <div className="flex items-start gap-2 text-m3-on-surface-variant">
              <span className="text-white/40 font-mono">▸ FalkorDB Nodes:</span>
              <span className="font-mono text-xs text-sky-200/90 font-medium">(:Session)-[:SESSION_HEAD]&rarr;(:Episode)-[:NEXT_EPISODE]&rarr;(:Episode)</span>
            </div>
          </div>
        </div>

        {/* Tier 3: Semantic Memory */}
        <div className="p-6 sm:p-7 rounded-2xl bg-m3-surface-container-low/80 border border-tier-semantic/20 shadow-double-bezel relative overflow-hidden group hover:border-tier-semantic/40 transition-colors">
          <div className="absolute top-0 right-0 w-32 h-32 bg-tier-semantic/5 rounded-full blur-2xl pointer-events-none" />
          <div className="flex items-center gap-3.5 mb-4">
            <div className="w-10 h-10 rounded-xl bg-tier-semantic/10 border border-tier-semantic/30 text-tier-semantic flex items-center justify-center">
              <TreeStructure size={22} weight="fill" />
            </div>
            <div>
              <div className="text-xs font-mono uppercase tracking-wider text-tier-semantic">Tier 3 • Facts & Concepts</div>
              <h3 className="text-lg font-bold text-white">Semantic Memory (The Living Encyclopedia)</h3>
            </div>
          </div>

          <p className="text-sm sm:text-[15px] text-m3-on-surface-variant leading-relaxed">
            <strong className="text-white">Brain Analogy:</strong> General facts and world truths (e.g. "Water boils at 100°C"), completely separated from where or when you first learned it.
          </p>

          <div className="mt-5 p-4 rounded-xl bg-black/40 border border-white/5 text-xs sm:text-sm space-y-2">
            <div className="flex items-start gap-2 text-m3-on-surface">
              <span className="text-tier-semantic font-mono font-medium">▸ In AegisGraph:</span>
              <span>A bi-temporal knowledge graph that tracks facts as they evolve over time without data corruption.</span>
            </div>
            <div className="flex items-start gap-2 text-m3-on-surface-variant">
              <span className="text-white/40 font-mono">▸ FalkorDB Nodes:</span>
              <span className="font-mono text-xs text-emerald-200/90 font-medium">(:Entity)-[:RELATES_TO &#123;valid_from, valid_to&#125;]&rarr;(:Entity)</span>
            </div>
          </div>
        </div>

        {/* Tier 4: Procedural Memory */}
        <div className="p-6 sm:p-7 rounded-2xl bg-m3-surface-container-low/80 border border-tier-procedural/20 shadow-double-bezel relative overflow-hidden group hover:border-tier-procedural/40 transition-colors">
          <div className="absolute top-0 right-0 w-32 h-32 bg-tier-procedural/5 rounded-full blur-2xl pointer-events-none" />
          <div className="flex items-center gap-3.5 mb-4">
            <div className="w-10 h-10 rounded-xl bg-tier-procedural/10 border border-tier-procedural/30 text-tier-procedural flex items-center justify-center">
              <ShieldCheck size={22} weight="fill" />
            </div>
            <div>
              <div className="text-xs font-mono uppercase tracking-wider text-tier-procedural">Tier 4 • Learned Skills & Rules</div>
              <h3 className="text-lg font-bold text-white">Procedural Memory (Muscle Memory & Guardrails)</h3>
            </div>
          </div>

          <p className="text-sm sm:text-[15px] text-m3-on-surface-variant leading-relaxed">
            <strong className="text-white">Brain Analogy:</strong> Riding a bicycle, tying shoelaces, or learning never to touch a hot stove twice.
          </p>

          <div className="mt-5 p-4 rounded-xl bg-black/40 border border-white/5 text-xs sm:text-sm space-y-2">
            <div className="flex items-start gap-2 text-m3-on-surface">
              <span className="text-tier-procedural font-mono font-medium">▸ In AegisGraph:</span>
              <span>Self-reflection compiles tool execution mistakes into permanent rules, injected before future actions.</span>
            </div>
            <div className="flex items-start gap-2 text-m3-on-surface-variant">
              <span className="text-white/40 font-mono">▸ FalkorDB Nodes:</span>
              <span className="font-mono text-xs text-purple-200/90 font-medium">(:Guardrail)-[:TRIGGERED_BY]&rarr;(:Episode &#123;status: 'ERROR'&#125;)</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
