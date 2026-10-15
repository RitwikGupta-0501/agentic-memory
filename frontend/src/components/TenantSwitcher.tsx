"use client";

import React from "react";
import { Database, ShieldCheck, Activity, Users } from "lucide-react";

interface TenantSwitcherProps {
  tenantId: string;
  setTenantId: (tenant: string) => void;
  userId: string;
  setUserId: (user: string) => void;
  latencyMs: number;
}

export default function TenantSwitcher({
  tenantId,
  setTenantId,
  userId,
  setUserId,
  latencyMs,
}: TenantSwitcherProps) {
  const graphKey = `mem_${tenantId.replace("-", "_")}_shared`;

  return (
    <header className="h-14 border-b border-slate-800 bg-slate-900/80 backdrop-blur px-4 flex items-center justify-between text-sm">
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2 font-bold text-base text-cyan-400">
          <Database className="w-5 h-5 text-cyan-400" />
          <span>AegisGraph</span>
        </div>
        <span className="text-xs px-2 py-0.5 rounded bg-cyan-950 text-cyan-400 border border-cyan-800">
          FalkorDB Cognitive Engine
        </span>
      </div>

      <div className="flex items-center gap-6">
        {/* Tenant Selector */}
        <div className="flex items-center gap-2">
          <ShieldCheck className="w-4 h-4 text-slate-400" />
          <span className="text-xs text-slate-400 font-medium">Tenant:</span>
          <select
            value={tenantId}
            onChange={(e) => setTenantId(e.target.value)}
            className="bg-slate-800 border border-slate-700 text-slate-200 text-xs rounded px-2.5 py-1 focus:ring-1 focus:ring-cyan-500 focus:outline-none"
          >
            <option value="acme-payments">acme-payments (Primary)</option>
            <option value="nebula-cloud">nebula-cloud (Isolated)</option>
          </select>
        </div>

        {/* User Selector */}
        <div className="flex items-center gap-2">
          <Users className="w-4 h-4 text-slate-400" />
          <span className="text-xs text-slate-400 font-medium">User:</span>
          <select
            value={userId}
            onChange={(e) => setUserId(e.target.value)}
            className="bg-slate-800 border border-slate-700 text-slate-200 text-xs rounded px-2.5 py-1 focus:ring-1 focus:ring-cyan-500 focus:outline-none"
          >
            <option value="alice_sre">alice_sre (Lead SRE)</option>
            <option value="bob_backend">bob_backend (Backend)</option>
          </select>
        </div>

        {/* Isolated Graph Key Display */}
        <div className="hidden lg:flex items-center gap-2 text-xs bg-slate-950 px-3 py-1 rounded border border-slate-800 font-mono">
          <span className="text-slate-500">Graph:</span>
          <span className="text-emerald-400">{graphKey}</span>
        </div>

        {/* Latency Badge */}
        <div className="flex items-center gap-1.5 text-xs text-emerald-400 bg-emerald-950/60 border border-emerald-800 px-2.5 py-1 rounded">
          <Activity className="w-3.5 h-3.5 animate-pulse" />
          <span>{latencyMs.toFixed(1)} ms</span>
        </div>
      </div>
    </header>
  );
}
