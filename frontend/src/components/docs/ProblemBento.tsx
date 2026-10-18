"use client";

import React from "react";
import { WarningCircle, XCircle, CheckCircle, Question, ArrowsLeftRight, Lightning } from "@phosphor-icons/react";

export function ProblemBento() {
  return (
    <section id="problem" className="relative mx-auto max-w-5xl px-4 py-16 border-t border-white/5">
      {/* Section Eyebrow & Title */}
      <div className="text-center max-w-3xl mx-auto mb-14">
        <span className="text-[11px] font-semibold tracking-widest uppercase text-amber-400">
          The Fundamental Problem
        </span>
        <h2 className="text-2xl sm:text-3xl md:text-4xl font-bold tracking-tight text-white mt-2">
          The Three Fatal Flaws of Traditional Vector RAG
        </h2>
        <p className="mt-3 text-sm sm:text-base text-m3-on-surface-variant leading-relaxed">
          Most modern AI memory frameworks simply chop dialogue into chunks and dump them into a flat vector database. In practice, this creates critical failure modes that prevent autonomous agents from working reliably.
        </p>
      </div>

      {/* 3 Problem Cards (Asymmetrical Bento) */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5 mb-14">
        {/* Flaw 1 */}
        <div className="p-6 sm:p-7 rounded-2xl bg-m3-surface-container-low/70 border border-white/10 shadow-double-bezel flex flex-col justify-between">
          <div>
            <div className="w-11 h-11 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 flex items-center justify-center mb-4">
              <XCircle size={24} weight="bold" />
            </div>
            <h3 className="text-lg font-bold text-white">1. Context Window Amnesia</h3>
            <p className="mt-2.5 text-sm text-m3-on-surface-variant leading-relaxed">
              When a chat session gets long, stuffing the entire history into the prompt makes API calls slow, astronomically expensive, and causes the LLM to lose focus (<em className="text-white/80">"lost-in-the-middle"</em> effect).
            </p>
          </div>
          <div className="mt-6 pt-3.5 border-t border-white/5 text-xs font-mono font-medium text-red-300 bg-red-500/10 px-3.5 py-2.5 rounded-xl">
            Failure: Agent loses thread after ~15 turns
          </div>
        </div>

        {/* Flaw 2 */}
        <div className="p-6 sm:p-7 rounded-2xl bg-m3-surface-container-low/70 border border-white/10 shadow-double-bezel flex flex-col justify-between">
          <div>
            <div className="w-11 h-11 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-400 flex items-center justify-center mb-4">
              <WarningCircle size={24} weight="bold" />
            </div>
            <h3 className="text-lg font-bold text-white">2. The Contradiction Trap</h3>
            <p className="mt-2.5 text-sm text-m3-on-surface-variant leading-relaxed">
              In flat vector databases, memories are static strings. If an engineer says on Monday <span className="text-white">"Deploying on PostgreSQL"</span> and on Friday <span className="text-white">"Migrated to FalkorDB"</span>, similarity search returns <strong>both</strong> chunks. The agent hallucinates or gives conflicting guidance.
            </p>
          </div>
          <div className="mt-6 pt-3.5 border-t border-white/5 text-xs font-mono font-medium text-amber-300 bg-amber-500/10 px-3.5 py-2.5 rounded-xl">
            Failure: Obsolete facts never get invalidated
          </div>
        </div>

        {/* Flaw 3 */}
        <div className="p-6 sm:p-7 rounded-2xl bg-m3-surface-container-low/70 border border-white/10 shadow-double-bezel flex flex-col justify-between">
          <div>
            <div className="w-11 h-11 rounded-xl bg-purple-500/10 border border-purple-500/20 text-purple-400 flex items-center justify-center mb-4">
              <Question size={24} weight="bold" />
            </div>
            <h3 className="text-lg font-bold text-white">3. Blind Multi-Hop Reasoning</h3>
            <p className="mt-2.5 text-sm text-m3-on-surface-variant leading-relaxed">
              Vectors measure surface semantic similarity, not relationships. If <span className="text-white">Alice leads Team Alpha</span> and <span className="text-white">Team Alpha owns the Auth Service</span>, vector search cannot deduce that <span className="text-white">Alice is responsible for Auth Service bugs</span>.
            </p>
          </div>
          <div className="mt-6 pt-3.5 border-t border-white/5 text-xs font-mono font-medium text-purple-300 bg-purple-500/10 px-3.5 py-2.5 rounded-xl">
            Failure: Incapable of connecting indirect dots
          </div>
        </div>
      </div>

      {/* Comparison Matrix Table */}
      <div className="rounded-2xl bg-m3-surface-container-lowest/80 border border-white/10 p-6 shadow-double-bezel overflow-x-auto">
        <div className="flex items-center gap-2 mb-4 text-xs font-semibold text-white tracking-wider uppercase">
          <ArrowsLeftRight size={16} className="text-m3-primary" />
          <span>Architectural Comparison</span>
        </div>

        <table className="w-full text-left text-sm border-collapse">
          <thead>
            <tr className="border-b border-white/10 text-m3-on-surface-variant">
              <th className="py-3 px-3.5 font-semibold">Capability</th>
              <th className="py-3 px-3.5 font-semibold text-red-400/90">Traditional Vector RAG</th>
              <th className="py-3 px-3.5 font-semibold text-tier-semantic">AegisGraph (FalkorDB)</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5 text-m3-on-surface">
            <tr>
              <td className="py-3.5 px-3.5 font-medium text-white">Fact Evolution & Updates</td>
              <td className="py-3.5 px-3.5 text-m3-on-surface-variant">Destructive overwrite or contradictory duplicates</td>
              <td className="py-3.5 px-3.5 text-tier-semantic font-medium flex items-center gap-1.5">
                <CheckCircle size={15} weight="fill" className="text-emerald-400 flex-shrink-0" />
                Bi-temporal invalidation (valid_to = now())
              </td>
            </tr>
            <tr>
              <td className="py-3.5 px-3.5 font-medium text-white">Multi-Hop Reasoning</td>
              <td className="py-3.5 px-3.5 text-m3-on-surface-variant">Fails (blind to graph paths and entity linkages)</td>
              <td className="py-3.5 px-3.5 text-tier-semantic font-medium flex items-center gap-1.5">
                <CheckCircle size={15} weight="fill" className="text-emerald-400 flex-shrink-0" />
                HippoRAG Personalized PageRank graph walks
              </td>
            </tr>
            <tr>
              <td className="py-3.5 px-3.5 font-medium text-white">Learning From Errors</td>
              <td className="py-3.5 px-3.5 text-m3-on-surface-variant">None (agent repeats the exact same tool failure)</td>
              <td className="py-3.5 px-3.5 text-tier-semantic font-medium flex items-center gap-1.5">
                <CheckCircle size={15} weight="fill" className="text-emerald-400 flex-shrink-0" />
                Reflexion guardrails compiled into procedural graph
              </td>
            </tr>
            <tr>
              <td className="py-3.5 px-3.5 font-medium text-white">Enterprise Privacy</td>
              <td className="py-3.5 px-3.5 text-m3-on-surface-variant">All-or-nothing index (all chats leak across users)</td>
              <td className="py-3.5 px-3.5 text-tier-semantic font-medium flex items-center gap-1.5">
                <CheckCircle size={15} weight="fill" className="text-emerald-400 flex-shrink-0" />
                Private user chats, shared company facts
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  );
}
