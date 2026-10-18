"use client";

import React, { useState, useEffect, useCallback } from "react";
import { TopNav } from "./TopNav";
import { ChatPane } from "./chat/ChatPane";
import { GraphPane } from "./graph/GraphPane";
import { HealthStatus, IsolationMode } from "@/lib/types";
import { fetchHealth, fetchSessions } from "@/lib/api";
import { ChatCircleDots, Graph } from "@phosphor-icons/react";

export function AppShell() {
  const [tenantId, setTenantId] = useState("tenant-default");
  const [userId, setUserId] = useState("alice");
  const [isolationMode, setIsolationMode] = useState<IsolationMode>("tenant_shared");
  const [sessionId, setSessionId] = useState("");
  const [sessions, setSessions] = useState<{ id: string; label: string }[]>([]);
  const [sessionFilter, setSessionFilter] = useState<string>("all");
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [nodeCount, setNodeCount] = useState(0);
  const [refreshKey, setRefreshKey] = useState(0);
  const [mobileTab, setMobileTab] = useState<"chat" | "graph">("chat");

  // Initialize active session and load known sessions for current tenant/user/mode
  useEffect(() => {
    const initialId = `session_${Math.random().toString(36).substring(2, 9)}`;
    setSessionId(initialId);
    setSessionFilter(initialId); // Default to scoping view to current session
    setSessions([{ id: initialId, label: `Active (${initialId.slice(-6)})` }]);

    fetchHealth().then(setHealth);

    fetchSessions(tenantId, userId, isolationMode).then((apiSessions) => {
      if (apiSessions && apiSessions.length > 0) {
        setSessions((prev) => {
          const map = new Map<string, string>();
          prev.forEach((s) => map.set(s.id, s.label));
          apiSessions.forEach((s) => {
            const short = s.id.length > 8 ? s.id.slice(-6) : s.id;
            const count = s.episode_count ? ` (${s.episode_count} msgs)` : "";
            if (!map.has(s.id)) {
              map.set(s.id, `Session ${short}${count}`);
            }
          });
          return Array.from(map.entries()).map(([id, label]) => ({ id, label }));
        });
      }
    });
  }, [tenantId, userId, isolationMode]);

  const handleNewSession = useCallback(() => {
    const newId = `session_${Math.random().toString(36).substring(2, 9)}`;
    setSessionId(newId);
    setSessionFilter(newId); // Auto-focus graph to new session
    setSessions((prev) => [
      { id: newId, label: `Active (${newId.slice(-6)})` },
      ...prev.map((s) =>
        s.label.startsWith("Active") ? { ...s, label: s.label.replace("Active", "Session") } : s
      ),
    ]);
    setRefreshKey((k) => k + 1);
  }, []);

  const handleSelectSession = useCallback((targetId: string) => {
    setSessionId(targetId);
    setSessionFilter(targetId); // Auto-focus graph to selected session
  }, []);

  const handleSessionsDetected = useCallback(
    (detected: { id: string; label: string }[]) => {
      setSessions((prev) => {
        const existingIds = new Set(prev.map((s) => s.id));
        const toAdd = detected.filter((d) => !existingIds.has(d.id));
        if (toAdd.length === 0) return prev;
        return [...prev, ...toAdd];
      });
    },
    []
  );

  const handleTurnComplete = () => {
    // Automatically trigger graph reload in the right pane
    setRefreshKey((k) => k + 1);
  };

  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden p-2 select-none">
      {/* Floating Island App Bar */}
      <TopNav
        tenantId={tenantId}
        onTenantChange={setTenantId}
        userId={userId}
        onUserChange={setUserId}
        isolationMode={isolationMode}
        onIsolationModeChange={setIsolationMode}
        health={health}
        nodeCount={nodeCount}
        onRefreshGraph={() => setRefreshKey((k) => k + 1)}
      />

      {/* Mobile Tab Switcher (Visible only below lg screens) */}
      <div className="lg:hidden flex items-center justify-center gap-2 mx-4 mb-2">
        <button
          onClick={() => setMobileTab("chat")}
          className={`flex items-center gap-1.5 px-4 py-1.5 rounded-full text-xs font-medium cursor-pointer transition-all ${
            mobileTab === "chat"
              ? "bg-m3-primary text-m3-on-primary font-semibold"
              : "bg-white/5 text-m3-on-surface-variant hover:text-white"
          }`}
        >
          <ChatCircleDots size={15} />
          <span>Agent Chat</span>
        </button>
        <button
          onClick={() => setMobileTab("graph")}
          className={`flex items-center gap-1.5 px-4 py-1.5 rounded-full text-xs font-medium cursor-pointer transition-all ${
            mobileTab === "graph"
              ? "bg-m3-primary text-m3-on-primary font-semibold"
              : "bg-white/5 text-m3-on-surface-variant hover:text-white"
          }`}
        >
          <Graph size={15} />
          <span>Graph Visualizer</span>
        </button>
      </div>

      {/* Split-Screen 50/50 Layout */}
      <main className="flex-1 grid grid-cols-1 lg:grid-cols-2 gap-3 min-h-0 mx-2 mb-2">
        {/* Left Pane: Pure Conversational Chat */}
        <section
          className={`h-full min-h-0 ${
            mobileTab === "chat" ? "flex flex-col" : "hidden lg:flex lg:flex-col"
          }`}
        >
          <ChatPane
            tenantId={tenantId}
            userId={userId}
            isolationMode={isolationMode}
            sessionId={sessionId || "session_default"}
            sessions={sessions}
            onSelectSession={handleSelectSession}
            onTurnComplete={handleTurnComplete}
            onNewSession={handleNewSession}
          />
        </section>

        {/* Right Pane: FalkorDB Graph Visualizer */}
        <section
          className={`h-full min-h-0 ${
            mobileTab === "graph" ? "flex flex-col" : "hidden lg:flex lg:flex-col"
          }`}
        >
          <GraphPane
            tenantId={tenantId}
            userId={userId}
            isolationMode={isolationMode}
            currentSessionId={sessionId}
            sessionFilter={sessionFilter}
            onSessionFilterChange={setSessionFilter}
            refreshKey={refreshKey}
            onNodeCountUpdate={setNodeCount}
            onSessionsDetected={handleSessionsDetected}
          />
        </section>
      </main>
    </div>
  );
}
