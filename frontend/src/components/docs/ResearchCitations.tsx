"use client";

import React from "react";
import katex from "katex";

function MathBlock({ math }: { math: string }) {
  const html = React.useMemo(() => {
    try {
      return katex.renderToString(math, { displayMode: true, throwOnError: false });
    } catch {
      return math;
    }
  }, [math]);

  return (
    <div
      className="p-4 sm:p-5 rounded-xl bg-black/60 border border-white/10 my-4 text-center overflow-x-auto text-base sm:text-lg text-white font-medium"
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

export function ResearchCitations() {
  return (
    <section id="research" className="relative mx-auto max-w-5xl px-4 py-16 border-t border-white/5">
      {/* Section Header */}
      <div className="text-center max-w-3xl mx-auto mb-14">
        <span className="text-xs font-semibold tracking-widest uppercase text-tier-episodic">
          Academic Grounding
        </span>
        <h2 className="text-2xl sm:text-3xl md:text-4xl font-bold tracking-tight text-white mt-2">
          The Research Foundations: Equations Explained in Plain English
        </h2>
        <p className="mt-3 text-base sm:text-lg text-m3-on-surface-variant leading-relaxed">
          Every mechanism in AegisGraph directly implements peer-reviewed cognitive research. Here are the exact mathematical models behind the system, translated into clear concepts anyone can follow.
        </p>
      </div>

      <div className="space-y-10">
        {/* Paper 1: Park et al. (Stanford / Google) */}
        <div className="p-6 sm:p-8 rounded-2xl bg-m3-surface-container-low/70 border border-white/10 shadow-double-bezel">
          <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-xl bg-sky-500/10 border border-sky-500/20 text-sky-400 flex items-center justify-center font-bold text-sm">
                1
              </div>
              <div>
                <h3 className="text-lg sm:text-xl font-bold text-white">Generative Agents: 3-Factor Composite Memory</h3>
                <div className="text-sm text-m3-on-surface-variant font-medium">Park et al. • Stanford University & Google Research (2023)</div>
              </div>
            </div>
            <span className="text-xs font-mono px-3 py-1 rounded-full bg-sky-500/10 text-sky-300 border border-sky-500/20">
              Episodic Recall Formula
            </span>
          </div>

          <p className="text-sm sm:text-base text-m3-on-surface-variant leading-relaxed mb-4">
            <strong className="text-white">The Dilemma:</strong> In human life, you don't recall memories randomly. You naturally retrieve events that are either <em>fresh in your mind</em>, <em>deeply significant</em>, or <em>directly relevant</em> to what someone just asked you.
          </p>

          {/* Mathematical Equation in LaTeX */}
          <MathBlock math="\text{Score}(m, q) = \alpha \cdot R(\Delta t) + \beta \cdot I(m) + \gamma \cdot S_{\text{cos}}(q, m)" />
          <MathBlock math="R(\Delta t) = e^{-\lambda \cdot \Delta t} \quad \text{(Ebbinghaus Exponential Forgetting Curve)}" />

          {/* Plain English Variable Breakdown */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mt-5">
            <div className="p-4 rounded-xl bg-white/5 border border-white/5">
              <div className="font-bold text-sm sm:text-base text-white">R(Δt) • Freshness Decay</div>
              <p className="mt-1.5 text-xs sm:text-sm text-m3-on-surface-variant leading-relaxed">
                Like human memory, mundane events fade exponentially as hours pass. If someone mentioned their coffee order 3 days ago, it fades unless reinforced.
              </p>
            </div>
            <div className="p-4 rounded-xl bg-white/5 border border-white/5">
              <div className="font-bold text-sm sm:text-base text-white">I(m) • Significance (1–10)</div>
              <p className="mt-1.5 text-xs sm:text-sm text-m3-on-surface-variant leading-relaxed">
                A score from 1 to 10. Casual greetings ("Hello") score 1. Critical operational changes ("Production database moved") score 9 and remain memorable.
              </p>
            </div>
            <div className="p-4 rounded-xl bg-white/5 border border-white/5">
              <div className="font-bold text-sm sm:text-base text-white">S(q, m) • Question Match</div>
              <p className="mt-1.5 text-xs sm:text-sm text-m3-on-surface-variant leading-relaxed">
                Vector cosine proximity between the user's current question and past memories.
              </p>
            </div>
          </div>
        </div>

        {/* Paper 2: HippoRAG (Ohio State / Stanford) */}
        <div className="p-6 sm:p-8 rounded-2xl bg-m3-surface-container-low/70 border border-white/10 shadow-double-bezel">
          <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 flex items-center justify-center font-bold text-sm">
                2
              </div>
              <div>
                <h3 className="text-lg sm:text-xl font-bold text-white">HippoRAG: Neurobiologically Inspired Associative Memory</h3>
                <div className="text-sm text-m3-on-surface-variant font-medium">Gutiérrez et al. • Ohio State & Stanford University (2024)</div>
              </div>
            </div>
            <span className="text-xs font-mono px-3 py-1 rounded-full bg-emerald-500/10 text-emerald-300 border border-emerald-500/20">
              Hippocampal Graph Walk
            </span>
          </div>

          <p className="text-sm sm:text-base text-m3-on-surface-variant leading-relaxed mb-4">
            <strong className="text-white">The Dilemma:</strong> Traditional vector search fails at <em>multi-hop questions</em>. If you ask "Who approved the database migration?", vector search looks for the exact phrase, but the answer requires hopping from the Database to the Service to the Manager who signed off on it.
          </p>

          {/* Mathematical Equation in LaTeX */}
          <MathBlock math="\mathbf{p} = (1 - d)\,\mathbf{p}_0 + d\,\mathbf{W}\,\mathbf{p}" />

          {/* Plain English Variable Breakdown */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mt-5">
            <div className="p-4 rounded-xl bg-white/5 border border-white/5">
              <div className="font-bold text-sm sm:text-base text-white">p₀ • Memory Seed Clues</div>
              <p className="mt-1.5 text-xs sm:text-sm text-m3-on-surface-variant leading-relaxed">
                The key entities extracted from the question (e.g. "Payment Gateway"). They act as the starting spark in the brain.
              </p>
            </div>
            <div className="p-4 rounded-xl bg-white/5 border border-white/5">
              <div className="font-bold text-sm sm:text-base text-white">W • The Relationship Web</div>
              <p className="mt-1.5 text-xs sm:text-sm text-m3-on-surface-variant leading-relaxed">
                The complete web of connections stored in FalkorDB (services, people, dependencies, tools).
              </p>
            </div>
            <div className="p-4 rounded-xl bg-white/5 border border-white/5">
              <div className="font-bold text-sm sm:text-base text-white">d • Association Damping (0.85)</div>
              <p className="mt-1.5 text-xs sm:text-sm text-m3-on-surface-variant leading-relaxed">
                How far the agent traverses along connected graph pathways to uncover indirect relationships that keyword search completely misses.
              </p>
            </div>
          </div>
        </div>

        {/* Paper 3: Reflexion (MIT / Northeastern) */}
        <div className="p-6 sm:p-8 rounded-2xl bg-m3-surface-container-low/70 border border-white/10 shadow-double-bezel">
          <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-xl bg-purple-500/10 border border-purple-500/20 text-purple-400 flex items-center justify-center font-bold text-sm">
                3
              </div>
              <div>
                <h3 className="text-lg sm:text-xl font-bold text-white">Reflexion: Verbal Reinforcement Learning</h3>
                <div className="text-sm text-m3-on-surface-variant font-medium">Shinn et al. • Northeastern University & MIT (2023)</div>
              </div>
            </div>
            <span className="text-xs font-mono px-3 py-1 rounded-full bg-purple-500/10 text-purple-300 border border-purple-500/20">
              Procedural Self-Correction
            </span>
          </div>

          <p className="text-sm sm:text-base text-m3-on-surface-variant leading-relaxed mb-4">
            <strong className="text-white">The Dilemma:</strong> When a traditional AI agent runs a tool and gets an error (like an invalid parameter or unverified database flag), it usually repeats the exact same blunder on the next attempt.
          </p>

          {/* Mathematical Equation in LaTeX */}
          <MathBlock math="\text{mem}_{t+1} = \text{mem}_t \cup \left\{ \text{Reflect}(\text{Failure\_Trace}_t, \text{Feedback}_t) \right\}" />

          <p className="text-sm sm:text-base text-m3-on-surface-variant leading-relaxed mt-4">
            <strong className="text-white">In Plain English:</strong> When an action fails, AegisGraph executes an automated reflection step. It diagnoses why the tool broke, creates an explicit <span className="text-tier-procedural font-medium">Guardrail rule</span>, and attaches it with a <span className="font-mono text-xs text-purple-200">[:TRIGGERED_BY]</span> relationship to the error episode. In future turns, this guardrail is automatically injected as a high-priority system constraint.
          </p>
        </div>

        {/* Paper 4: Bi-Temporal Graph Theory */}
        <div className="p-6 sm:p-8 rounded-2xl bg-m3-surface-container-low/70 border border-white/10 shadow-double-bezel">
          <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-400 flex items-center justify-center font-bold text-sm">
                4
              </div>
              <div>
                <h3 className="text-lg sm:text-xl font-bold text-white">Bi-Temporal Knowledge State Theory</h3>
                <div className="text-sm text-m3-on-surface-variant font-medium">Snodgrass, Jensen, & Johnston • ACM / VLDB Foundations</div>
              </div>
            </div>
            <span className="text-xs font-mono px-3 py-1 rounded-full bg-amber-500/10 text-amber-300 border border-amber-500/20">
              Valid Time vs. Transaction Time
            </span>
          </div>

          <p className="text-sm sm:text-base text-m3-on-surface-variant leading-relaxed mb-4">
            <strong className="text-white">The Dilemma:</strong> In the real world, truth is time-dependent. You can't just delete old facts, because you often need to ask: <em>"What was our architecture before last Tuesday's update?"</em>
          </p>

          {/* Mathematical Equation in LaTeX */}
          <MathBlock math="\text{Fact}(s, p, o, [T_{\text{valid}}^{\text{start}}, T_{\text{valid}}^{\text{end}}], [T_{\text{record}}^{\text{start}}, T_{\text{record}}^{\text{end}}])" />

          <p className="text-sm sm:text-base text-m3-on-surface-variant leading-relaxed mt-4">
            <strong className="text-white">In Plain English:</strong> AegisGraph never executes destructive updates. When a fact changes, the active graph edge is marked with <span className="font-mono text-xs text-amber-200">valid_to = timestamp</span> (rendered as a dashed edge in the visualizer), and a brand-new edge is created with <span className="font-mono text-xs text-amber-200">valid_from = timestamp</span>. This provides instantaneous historical time-travel without data corruption.
          </p>
        </div>
      </div>
    </section>
  );
}
