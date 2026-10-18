"use client";

import React, { useState } from "react";
import Link from "next/link";
import {
  Database,
  User,
  Buildings,
  ArrowClockwise,
  ShieldCheck,
  CaretDown,
  LockKey,
  BookOpen,
} from "@phosphor-icons/react";
import { HealthStatus, IsolationMode } from "@/lib/types";
import { resetGuardrails } from "@/lib/api";
import { PillDropdown } from "./ui/PillDropdown";

const TENANT_OPTIONS = [
  { value: "tenant-default", label: "default" },
  { value: "tenant-acme", label: "acme-corp" },
  { value: "tenant-globex", label: "globex-cloud" },
];

const USER_OPTIONS = [
  { value: "alice", label: "alice" },
  { value: "bob", label: "bob" },
];

const ISOLATION_OPTIONS = [
  { value: "tenant_shared", label: "Enterprise Shared" },
  { value: "user_strict", label: "Strict User Isolation" },
  { value: "team_open", label: "Open Team Collaboration" },
];

interface TopNavProps {
  tenantId: string;
  onTenantChange: (tenant: string) => void;
  userId: string;
  onUserChange: (user: string) => void;
  isolationMode?: IsolationMode;
  onIsolationModeChange?: (mode: IsolationMode) => void;
  health: HealthStatus | null;
  nodeCount: number;
  onRefreshGraph: () => void;
}

export function TopNav({
  tenantId,
  onTenantChange,
  userId,
  onUserChange,
  isolationMode,
  onIsolationModeChange,
  health,
  nodeCount,
  onRefreshGraph,
}: TopNavProps) {
  const [isResetting, setIsResetting] = useState(false);
  const [resetFeedback, setResetFeedback] = useState<string | null>(null);

  const handleResetGuardrails = async () => {
    setIsResetting(true);
    const ok = await resetGuardrails(tenantId);
    setIsResetting(false);
    if (ok) {
      setResetFeedback("Guardrails reset");
      setTimeout(() => setResetFeedback(null), 2500);
      onRefreshGraph();
    }
  };

  const isConnected = health?.falkordb_connected ?? false;

  return (
    <header className="relative z-30 mx-4 mt-3 mb-2">
      <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-2.5 rounded-full bg-m3-surface-container/70 backdrop-blur-2xl border border-white/10 shadow-double-bezel">
        {/* Brand & Core Taxonomy Badge */}
        <div className="flex items-center gap-3">
          <div className="flex items-center justify-center w-8 h-8 rounded-full bg-m3-primary/10 border border-m3-primary/20 text-m3-primary">
            <Database size={18} weight="bold" />
          </div>
          <div className="flex items-center gap-2">
            <span className="font-semibold text-sm tracking-tight text-white">AegisGraph</span>
            <span className="px-2 py-0.5 text-[10px] font-medium tracking-wider uppercase rounded-full bg-m3-primary-container text-m3-on-primary-container">
              4-Tier Memory
            </span>
          </div>

          <Link
            href="/docs"
            title="Read system architecture and research foundations"
            className="hidden sm:flex items-center gap-1.5 ml-2 px-3 py-1.5 rounded-full bg-white/5 hover:bg-white/10 text-m3-on-surface hover:text-white active:scale-[0.97] transition-all text-xs font-medium border border-white/10 cursor-pointer"
          >
            <BookOpen size={14} className="text-m3-primary" />
            <span>Architecture & Research</span>
          </Link>
        </div>

        {/* Global Controls & Status */}
        <div className="flex flex-wrap items-center gap-2.5">
          {/* Tenant Selector Dropdown */}
          <PillDropdown
            value={tenantId}
            options={TENANT_OPTIONS}
            onChange={onTenantChange}
            icon={<Buildings size={14} className="text-m3-primary flex-shrink-0" />}
            label="Tenant:"
            className="min-w-[155px]"
          />

          {/* User Selector Dropdown */}
          <PillDropdown
            value={userId}
            options={USER_OPTIONS}
            onChange={onUserChange}
            icon={<User size={14} className="text-tier-semantic flex-shrink-0" />}
            label="User:"
            className="min-w-[115px]"
          />

          {/* Judge Testing Console: Isolation Policy Dropdown */}
          {isolationMode && onIsolationModeChange && (
            <PillDropdown
              value={isolationMode}
              options={ISOLATION_OPTIONS}
              onChange={(val) => onIsolationModeChange(val as IsolationMode)}
              icon={<LockKey size={14} className="text-amber-400 flex-shrink-0" />}
              label="Policy:"
              className="min-w-[215px] border-amber-400/30 hover:border-amber-400/60"
            />
          )}

          {/* FalkorDB Connection Status */}
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-m3-surface-container-high/80 border border-white/5 text-xs">
            <span className="relative flex h-2 w-2">
              {isConnected ? (
                <>
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                </>
              ) : (
                <span className="relative inline-flex rounded-full h-2 w-2 bg-red-500"></span>
              )}
            </span>
            <span className="text-white font-medium text-[11px]">
              {isConnected ? "FalkorDB Online" : "Offline"}
            </span>
            <span className="text-[10px] text-m3-on-surface-variant px-1.5 py-0.2 rounded bg-black/30 font-mono">
              {nodeCount} nodes
            </span>
          </div>

          {/* Reset Guardrails Action */}
          <button
            onClick={handleResetGuardrails}
            disabled={isResetting}
            title="Reset compiled procedural guardrails to test Reflexion"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-white/5 hover:bg-white/10 active:scale-[0.97] transition-all text-xs font-medium text-m3-on-surface border border-white/5 cursor-pointer"
          >
            <ShieldCheck size={14} className="text-tier-procedural" />
            <span>{resetFeedback ? resetFeedback : "Reset Guardrails"}</span>
          </button>

          {/* Refresh Graph Button */}
          <button
            onClick={onRefreshGraph}
            title="Reload latest graph from FalkorDB"
            className="p-2 rounded-full bg-white/5 hover:bg-white/10 text-m3-on-surface active:scale-95 transition-all cursor-pointer border border-white/5"
          >
            <ArrowClockwise size={14} />
          </button>
        </div>
      </div>
    </header>
  );
}
