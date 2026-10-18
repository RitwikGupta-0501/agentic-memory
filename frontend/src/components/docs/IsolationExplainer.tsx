"use client";

import React from "react";
import { LockKey, Users, ShieldCheck, UserCheck } from "@phosphor-icons/react";

export function IsolationExplainer() {
  return (
    <section id="isolation" className="relative mx-auto max-w-5xl px-4 py-16 border-t border-white/5">
      {/* Section Header */}
      <div className="text-center max-w-3xl mx-auto mb-14">
        <span className="text-xs font-semibold tracking-widest uppercase text-amber-400">
          Security & Privacy Architecture
        </span>
        <h2 className="text-2xl sm:text-3xl md:text-4xl font-bold tracking-tight text-white mt-2">
          Enterprise Memory Isolation: Privacy & Collective Intelligence
        </h2>
        <p className="mt-3 text-base sm:text-lg text-m3-on-surface-variant leading-relaxed">
          In real enterprise deployments, you cannot have an AI agent leak confidential user discussions. But you also don't want every employee to start from zero with no organizational knowledge. AegisGraph solves this with a multi-layered boundary model.
        </p>
      </div>

      {/* Two Pillars: Private Silo vs Shared Knowledge */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-12">
        <div className="p-6 sm:p-7 rounded-2xl bg-m3-surface-container-low/70 border border-white/10 shadow-double-bezel">
          <div className="flex items-center gap-3 mb-3 text-sky-400">
            <div className="w-9 h-9 rounded-xl bg-sky-500/10 border border-sky-500/20 flex items-center justify-center">
              <LockKey size={20} weight="bold" />
            </div>
            <h3 className="text-lg font-bold text-white">Private Episodic Dialogues</h3>
          </div>
          <p className="text-sm sm:text-[15px] text-m3-on-surface-variant leading-relaxed">
            Every user turn and assistant reply is stamped with <code className="font-mono text-xs text-sky-300">user_id: "alice"</code> and <code className="font-mono text-xs text-sky-300">scope: "private"</code>. When Bob uses the system, vector candidate search and dialogue history strictly exclude Alice's episodes.
          </p>
          <div className="mt-5 p-3 rounded-xl bg-black/40 border border-white/5 text-xs sm:text-sm font-mono text-sky-200/90">
            Rule: Bob cannot recall Alice's past questions
          </div>
        </div>

        <div className="p-6 sm:p-7 rounded-2xl bg-m3-surface-container-low/70 border border-white/10 shadow-double-bezel">
          <div className="flex items-center gap-3 mb-3 text-tier-semantic">
            <div className="w-9 h-9 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center">
              <Users size={20} weight="bold" />
            </div>
            <h3 className="text-lg font-bold text-white">Shared Semantic & Procedural Graph</h3>
          </div>
          <p className="text-sm sm:text-[15px] text-m3-on-surface-variant leading-relaxed">
            Objective facts about company infrastructure, services, and policies (e.g. "Stripe API requires TLS 1.3") are stamped with <code className="font-mono text-xs text-emerald-300">scope: "tenant"</code>. All team members benefit from this collective institutional brain.
          </p>
          <div className="mt-5 p-3 rounded-xl bg-black/40 border border-white/5 text-xs sm:text-sm font-mono text-emerald-200/90">
            Rule: Company knowledge and safety rules protect all users
          </div>
        </div>
      </div>

      {/* The 3 Evaluator Policies */}
      <div className="rounded-2xl bg-m3-surface-container-lowest/80 border border-white/10 p-6 sm:p-7 shadow-double-bezel">
        <h4 className="text-sm sm:text-base font-bold text-white uppercase tracking-wider mb-5 flex items-center gap-2">
          <ShieldCheck size={20} className="text-amber-400" />
          <span>Configurable Isolation Policies (Available in TopNav)</span>
        </h4>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-5">
          <div className="p-4 sm:p-5 rounded-xl bg-white/5 border border-white/5">
            <div className="font-bold text-sm sm:text-base text-white flex items-center justify-between">
              <span>Enterprise Shared</span>
              <span className="text-[11px] px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 font-normal">Default</span>
            </div>
            <p className="mt-2 text-xs sm:text-sm text-m3-on-surface-variant leading-relaxed">
              Private chat history for each user. Shared entities and guardrails across the company.
            </p>
          </div>

          <div className="p-4 sm:p-5 rounded-xl bg-white/5 border border-white/5">
            <div className="font-bold text-sm sm:text-base text-white">Strict User Isolation</div>
            <p className="mt-2 text-xs sm:text-sm text-m3-on-surface-variant leading-relaxed">
              Zero-knowledge sandbox. Every entity, chat, and procedure is 100% isolated to the author.
            </p>
          </div>

          <div className="p-4 sm:p-5 rounded-xl bg-white/5 border border-white/5">
            <div className="font-bold text-sm sm:text-base text-white">Open Team Collaboration</div>
            <p className="mt-2 text-xs sm:text-sm text-m3-on-surface-variant leading-relaxed">
              Communal team workspace. All members can search, view, and recall each other's dialogue turns.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
