"use client";

import React, { useState, useEffect, useCallback } from "react";
import TenantSwitcher from "@/components/TenantSwitcher";
import GraphCanvas from "@/components/GraphCanvas";
import AgentStream from "@/components/AgentStream";
import CypherInspector from "@/components/CypherInspector";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

export default function Home() {
  const [tenantId, setTenantId] = useState("acme-payments");
  const [userId, setUserId] = useState("alice_sre");
  const [latencyMs, setLatencyMs] = useState(0.8);
  const [includeInvalidated, setIncludeInvalidated] = useState(true);

  const [nodes, setNodes] = useState<any[]>([]);
  const [edges, setEdges] = useState<any[]>([]);
  const [isLoadingGraph, setIsLoadingGraph] = useState(false);

  const [events, setEvents] = useState<any[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [selectedNode, setSelectedNode] = useState<any>(null);
  const [lastCypherQuery, setLastCypherQuery] = useState("");
  const [isConsolidating, setIsConsolidating] = useState(false);

  // Fetch graph elements from backend
  const fetchGraph = useCallback(async () => {
    setIsLoadingGraph(true);
    const startT = performance.now();
    try {
      const res = await fetch(
        `${BACKEND_URL}/api/v1/memory/graph?tenant_id=${tenantId}&include_invalidated=${includeInvalidated}`
      );
      const data = await res.json();
      setNodes(data.nodes || []);
      setEdges(data.edges || []);
      setLatencyMs(performance.now() - startT);
    } catch (err) {
      console.error("Failed to fetch graph:", err);
    } finally {
      setIsLoadingGraph(false);
    }
  }, [tenantId, includeInvalidated]);

  useEffect(() => {
    fetchGraph();
  }, [fetchGraph]);

  // Run multi-agent stream
  const handleRunPrompt = async (prompt: string) => {
    setIsStreaming(true);
    setEvents([]);

    try {
      const response = await fetch(`${BACKEND_URL}/api/v1/agents/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tenant_id: tenantId,
          user_id: userId,
          session_id: `session_${Date.now()}`,
          prompt,
        }),
      });

      if (!response.body) return;

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          const match = line.match(/^data:\s*(.+)$/m);
          if (match) {
            try {
              const eventData = JSON.parse(match[1]);
              setEvents((prev) => [...prev, eventData]);
              if (eventData.cypher) {
                setLastCypherQuery(eventData.cypher);
              }
            } catch (e) {
              console.error("Failed to parse SSE event:", e);
            }
          }
        }
      }
    } catch (err) {
      console.error("Agent streaming error:", err);
    } finally {
      setIsStreaming(false);
      fetchGraph(); // Refresh graph to display new nodes & edges
    }
  };

  // Trigger Slow-Stream Memory Consolidation
  const handleTriggerConsolidation = async () => {
    setIsConsolidating(true);
    try {
      const res = await fetch(`${BACKEND_URL}/api/v1/memory/consolidate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tenant_id: tenantId }),
      });
      const data = await res.json();
      if (data.summary) {
        setEvents((prev) => [
          ...prev,
          {
            type: "consolidation_event",
            agent: "Slow-Stream Consolidation Engine",
            phase: "consolidate",
            message: data.summary,
            cypher: "CREATE (:ConsolidatedInsight)-[:CONSOLIDATES]->(:Episode)",
          },
        ]);
      }
      fetchGraph();
    } catch (err) {
      console.error("Consolidation error:", err);
    } finally {
      setIsConsolidating(false);
    }
  };

  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-[#090d16]">
      {/* Top Bar: Multi-Tenant & Session Switcher */}
      <TenantSwitcher
        tenantId={tenantId}
        setTenantId={setTenantId}
        userId={userId}
        setUserId={setUserId}
        latencyMs={latencyMs}
      />

      {/* Main Single-Screen Split Layout */}
      <main className="flex-1 grid grid-cols-12 gap-3 p-3 overflow-hidden">
        {/* Left Panel: Multi-Agent Chat & Handoff Stream (4 columns) */}
        <section className="col-span-12 lg:col-span-4 h-full overflow-hidden">
          <AgentStream
            onRunPrompt={handleRunPrompt}
            isStreaming={isStreaming}
            events={events}
          />
        </section>

        {/* Center Panel: Live 4-Tier FalkorDB Cytoscape Visualizer (5 columns) */}
        <section className="col-span-12 lg:col-span-5 h-full overflow-hidden">
          <GraphCanvas
            nodes={nodes}
            edges={edges}
            onSelectNode={setSelectedNode}
            onRefresh={fetchGraph}
            isLoading={isLoadingGraph}
          />
        </section>

        {/* Right Panel: Cypher & Provenance Inspector (3 columns) */}
        <section className="col-span-12 lg:col-span-3 h-full overflow-hidden">
          <CypherInspector
            selectedNode={selectedNode}
            includeInvalidated={includeInvalidated}
            setIncludeInvalidated={setIncludeInvalidated}
            onTriggerConsolidation={handleTriggerConsolidation}
            isConsolidating={isConsolidating}
            lastCypherQuery={lastCypherQuery}
          />
        </section>
      </main>
    </div>
  );
}
