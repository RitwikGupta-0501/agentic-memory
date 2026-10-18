"use client";

import React from "react";
import { MemoryTier } from "@/lib/types";
import { ClockCounterClockwise } from "@phosphor-icons/react";
import { PillDropdown } from "../ui/PillDropdown";

interface GraphToolbarProps {
  selectedTier: MemoryTier;
  onTierChange: (tier: MemoryTier) => void;
  sessionFilter: string;
  onSessionFilterChange: (session: string) => void;
  availableSessions: { id: string; label: string }[];
  currentSessionId: string;
  includeInvalidated: boolean;
  onToggleInvalidated: () => void;
}

const TIERS: { id: MemoryTier; label: string; colorClass: string; dotColor: string }[] = [
  { id: "all", label: "All Tiers", colorClass: "text-white", dotColor: "bg-white" },
  { id: "working", label: "Working", colorClass: "text-tier-working", dotColor: "bg-tier-working" },
  { id: "episodic", label: "Episodic", colorClass: "text-tier-episodic", dotColor: "bg-tier-episodic" },
  { id: "semantic", label: "Semantic", colorClass: "text-tier-semantic", dotColor: "bg-tier-semantic" },
  { id: "procedural", label: "Procedural", colorClass: "text-tier-procedural", dotColor: "bg-tier-procedural" },
];

export function GraphToolbar({
  selectedTier,
  onTierChange,
  sessionFilter,
  onSessionFilterChange,
  availableSessions,
  currentSessionId,
  includeInvalidated,
  onToggleInvalidated,
}: GraphToolbarProps) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 border-b border-white/5 bg-m3-surface-container/50">
      {/* Left: Memory Tier Filter Chips */}
      <div className="flex items-center gap-1.5 overflow-x-auto no-scrollbar py-0.5">
        {TIERS.map((tier) => {
          const isSelected = selectedTier === tier.id;
          return (
            <button
              key={tier.id}
              onClick={() => onTierChange(tier.id)}
              className={`flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium transition-all duration-200 cursor-pointer ${
                isSelected
                  ? "bg-m3-surface-container-highest text-white border border-white/20 shadow-sm"
                  : "bg-white/5 text-m3-on-surface-variant hover:text-white hover:bg-white/10 border border-transparent"
              }`}
            >
              <span className={`w-2 h-2 rounded-full ${tier.dotColor}`} />
              <span>{tier.label}</span>
            </button>
          );
        })}
      </div>

      {/* Right: Styled Scope Dropdown & Superseded Toggle (No Emojis) */}
      <div className="flex flex-wrap items-center gap-1.5">
        {/* Styled Session Scoping Dropdown */}
        <PillDropdown
          value={sessionFilter}
          options={[
            { value: "all", label: "All Sessions (Global)" },
            ...(currentSessionId
              ? [{ value: currentSessionId, label: `Current Session (${currentSessionId.slice(-6)})` }]
              : []),
            ...availableSessions
              .filter((s) => s.id !== currentSessionId)
              .map((s) => ({
                value: s.id,
                label: s.label.replace(/^[^\w\s]+/, "").trim(),
              })),
          ]}
          onChange={onSessionFilterChange}
          label="Scope:"
          className="w-[185px] py-1 bg-white/5 hover:bg-white/10"
        />

        {/* Superseded Edges Toggle */}
        <button
          onClick={onToggleInvalidated}
          title="Toggle visibility of bi-temporally superseded historical edges"
          className={`flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-medium transition-all cursor-pointer border ${
            includeInvalidated
              ? "bg-amber-500/15 text-amber-300 border-amber-500/30"
              : "bg-white/5 text-m3-on-surface-variant hover:text-white border-white/5"
          }`}
        >
          <ClockCounterClockwise size={12} />
          <span>Superseded</span>
        </button>
      </div>
    </div>
  );
}
