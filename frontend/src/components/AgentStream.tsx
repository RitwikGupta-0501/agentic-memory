"use client";

import React, { useState } from "react";
import { Send, Bot, Play, Compass, Search, Wrench, CheckCircle, AlertTriangle } from "lucide-react";

interface AgentStreamProps {
  onRunPrompt: (prompt: string) => void;
  isStreaming: boolean;
  events: any[];
}

export default function AgentStream({
  onRunPrompt,
  isStreaming,
  events,
}: AgentStreamProps) {
  const [prompt, setPrompt] = useState(
    "Migrate Prod_DB from PostgreSQL to FalkorDB for real-time memory."
  );

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!prompt.trim() || isStreaming) return;
    onRunPrompt(prompt);
  };

  return (
    <div className="w-full h-full flex flex-col bg-[#070b12] border border-slate-800 rounded-lg overflow-hidden">
      {/* Agents Header */}
      <div className="p-3 bg-slate-900/90 border-b border-slate-800 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Bot className="w-4 h-4 text-cyan-400" />
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-300">
            Multi-Agent Blackboard Stream
          </span>
        </div>
      </div>

      {/* Agents Status Badges */}
      <div className="grid grid-cols-3 gap-1 p-2 bg-slate-950/80 border-b border-slate-800 text-[11px]">
        <div className="flex items-center gap-1.5 p-1.5 rounded bg-slate-900/60 border border-slate-800">
          <Compass className="w-3.5 h-3.5 text-yellow-400" />
          <span className="truncate text-slate-300">Orchestrator</span>
        </div>
        <div className="flex items-center gap-1.5 p-1.5 rounded bg-slate-900/60 border border-slate-800">
          <Search className="w-3.5 h-3.5 text-blue-400" />
          <span className="truncate text-slate-300">Triage & Context</span>
        </div>
        <div className="flex items-center gap-1.5 p-1.5 rounded bg-slate-900/60 border border-slate-800">
          <Wrench className="w-3.5 h-3.5 text-purple-400" />
          <span className="truncate text-slate-300">Executor & Reflexion</span>
        </div>
      </div>

      {/* Event Stream Log */}
      <div className="flex-1 overflow-y-auto p-3 space-y-3 font-sans text-xs">
        {events.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-slate-500 text-center px-4">
            <Bot className="w-8 h-8 mb-2 opacity-40 text-slate-400" />
            <p>Ready to coordinate agents.</p>
            <p className="text-[11px] text-slate-600 mt-1">
              Enter a task to watch the agents decompose, claim subtasks atomically, and mutate FalkorDB memory.
            </p>
          </div>
        ) : (
          events.map((ev, idx) => {
            const isReflexion = ev.type === "reflexion_event";
            const isCompleted = ev.type === "task_completed";

            return (
              <div
                key={idx}
                className={`p-2.5 rounded border ${
                  isReflexion
                    ? "bg-amber-950/30 border-amber-800/60 text-amber-200"
                    : isCompleted
                    ? "bg-emerald-950/30 border-emerald-800/60 text-emerald-200"
                    : "bg-slate-900/70 border-slate-800 text-slate-300"
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="font-semibold text-[11px] text-cyan-400">
                    {ev.agent || "System"}
                  </span>
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 uppercase">
                    {ev.phase || ev.type}
                  </span>
                </div>
                <p className="leading-relaxed">{ev.message}</p>
                {ev.cypher && (
                  <div className="mt-1.5 pt-1.5 border-t border-slate-800/60 font-mono text-[10px] text-slate-400 truncate">
                    Cypher: {ev.cypher}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      {/* Input Box */}
      <form onSubmit={handleSubmit} className="p-3 bg-slate-900/90 border-t border-slate-800 flex gap-2">
        <input
          type="text"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="Enter goal or migration request..."
          disabled={isStreaming}
          className="flex-1 bg-slate-950 border border-slate-700 text-slate-200 text-xs rounded px-3 py-2 focus:ring-1 focus:ring-cyan-500 focus:outline-none"
        />
        <button
          type="submit"
          disabled={isStreaming || !prompt.trim()}
          className="bg-cyan-600 hover:bg-cyan-500 disabled:bg-slate-800 text-white text-xs px-3.5 py-2 rounded font-medium flex items-center gap-1.5 transition-colors"
        >
          {isStreaming ? (
            <span className="animate-pulse">Running...</span>
          ) : (
            <>
              <Play className="w-3.5 h-3.5" />
              <span>Run</span>
            </>
          )}
        </button>
      </form>
    </div>
  );
}
