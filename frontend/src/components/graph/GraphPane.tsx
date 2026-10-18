"use client";

import React, { useState, useEffect, useRef, useMemo } from "react";
import cytoscape from "cytoscape";
import { MemoryTier, IsolationMode } from "@/lib/types";
import { fetchGraphData, fetchTimeTravelGraph } from "@/lib/api";
import { GraphToolbar } from "./GraphToolbar";
import { CytoscapeCanvas } from "./CytoscapeCanvas";
import { TimeTravelSlider } from "./TimeTravelSlider";
import { NodeInspector } from "./NodeInspector";
import { Graph, ArrowsInSimple, ArrowClockwise } from "@phosphor-icons/react";

interface GraphPaneProps {
  tenantId: string;
  userId: string;
  isolationMode?: IsolationMode;
  currentSessionId: string;
  sessionFilter: string;
  onSessionFilterChange: (session: string) => void;
  refreshKey: number;
  onNodeCountUpdate: (count: number) => void;
  onSessionsDetected?: (sessions: Array<{ id: string; label: string }>) => void;
}

export function GraphPane({
  tenantId,
  userId,
  isolationMode = "tenant_shared",
  currentSessionId,
  sessionFilter,
  onSessionFilterChange,
  refreshKey,
  onNodeCountUpdate,
  onSessionsDetected,
}: GraphPaneProps) {
  const [elements, setElements] = useState<{ nodes: any[]; edges: any[] }>({
    nodes: [],
    edges: [],
  });
  const [selectedTier, setSelectedTier] = useState<MemoryTier>("all");
  const [includeInvalidated, setIncludeInvalidated] = useState(true);
  const [asOf, setAsOf] = useState<number | null>(null);
  const [selectedElement, setSelectedElement] = useState<any | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const cyRef = useRef<cytoscape.Core | null>(null);

  const loadGraph = async () => {
    setIsLoading(true);
    try {
      if (asOf !== null) {
        // Fetch Point-in-Time Snapshot
        const data = await fetchTimeTravelGraph(tenantId, asOf, includeInvalidated, userId);
        if (data && data.elements) {
          setElements(data.elements);
          onNodeCountUpdate((data.elements.nodes || []).length);
        }
      } else {
        // Fetch Live Multi-Tier Graph
        const data = await fetchGraphData(tenantId, userId, includeInvalidated, isolationMode);
        if (data && data.nodes) {
          setElements({ nodes: data.nodes, edges: data.edges });
          onNodeCountUpdate(data.nodes.length);
        }
      }
    } catch (e) {
      console.error("Failed to load graph:", e);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadGraph();
  }, [tenantId, userId, isolationMode, asOf, refreshKey]);

  // Extract all sessions present in the graph nodes
  const availableSessions = useMemo(() => {
    const list: { id: string; label: string }[] = [];
    const seen = new Set<string>();

    // Include current active session first
    if (currentSessionId) {
      seen.add(currentSessionId);
      list.push({
        id: currentSessionId,
        label: `Active (${currentSessionId.slice(-6)})`,
      });
    }

    elements.nodes.forEach((n) => {
      const d = n.data || {};
      const p = d.properties || {};
      const sid = String(p.session_id || (d.id && String(d.id).startsWith("session_") ? d.id : ""));
      if (sid && !seen.has(sid)) {
        seen.add(sid);
        const short = sid.length > 8 ? sid.slice(-6) : sid;
        const count = p.episode_count ? ` (${p.episode_count} msgs)` : "";
        list.push({
          id: sid,
          label: `Session ${short}${count}`,
        });
      }
    });

    return list;
  }, [elements.nodes, currentSessionId]);

  useEffect(() => {
    if (onSessionsDetected && availableSessions.length > 0) {
      onSessionsDetected(availableSessions);
    }
  }, [availableSessions, onSessionsDetected]);

  const handleFit = () => {
    if (cyRef.current) {
      cyRef.current.fit(undefined, 30);
    }
  };

  const handleReLayout = () => {
    if (cyRef.current) {
      cyRef.current.layout({
        name: "cose",
        animate: true,
        animationDuration: 500,
        componentSpacing: 120,
      } as any).run();
    }
  };

  return (
    <div className="relative flex flex-col h-full rounded-[2rem] bg-m3-surface-container-lowest/60 border border-white/10 backdrop-blur-xl shadow-double-bezel overflow-hidden">
      {/* Pane Header (Matches ChatPane) */}
      <div className="flex items-center justify-between px-4 pt-3.5 pb-2.5 border-b border-white/5">
        <div className="flex items-center gap-2">
          <Graph size={18} className="text-m3-primary" />
          <h2 className="text-sm font-semibold text-white tracking-tight">Graph Visualizer</h2>
          <span className="text-[11px] text-m3-on-surface-variant font-mono">
            ({elements.nodes.length} nodes)
          </span>
        </div>

        {/* Action Controls: Fit Canvas, Physics Re-layout */}
        <div className="flex items-center gap-1.5">
          <button
            onClick={handleFit}
            title="Fit graph to view"
            className="flex items-center gap-1 px-2.5 py-1 rounded-full text-xs text-m3-on-surface-variant hover:text-white hover:bg-white/5 border border-white/5 transition-all cursor-pointer"
          >
            <ArrowsInSimple size={13} />
            <span className="text-[11px]">Fit</span>
          </button>

          <button
            onClick={handleReLayout}
            title="Re-run physics layout"
            className="flex items-center gap-1 px-2.5 py-1 rounded-full text-xs text-m3-on-surface-variant hover:text-white hover:bg-white/5 border border-white/5 transition-all cursor-pointer"
          >
            <ArrowClockwise size={13} />
            <span className="text-[11px]">Re-layout</span>
          </button>
        </div>
      </div>

      {/* Toolbar with Filter Chips & Scope Filter */}
      <GraphToolbar
        selectedTier={selectedTier}
        onTierChange={setSelectedTier}
        sessionFilter={sessionFilter}
        onSessionFilterChange={onSessionFilterChange}
        availableSessions={availableSessions}
        currentSessionId={currentSessionId}
        includeInvalidated={includeInvalidated}
        onToggleInvalidated={() => setIncludeInvalidated((prev) => !prev)}
      />

      {/* Main Canvas Area */}
      <div className="relative flex-1 w-full h-full min-h-[300px] overflow-hidden">
        {isLoading && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/40 backdrop-blur-sm z-10 text-xs font-mono text-m3-primary">
            Syncing graph from FalkorDB...
          </div>
        )}

        <CytoscapeCanvas
          elements={elements}
          selectedTier={selectedTier}
          selectedSessionFilter={sessionFilter}
          includeInvalidated={includeInvalidated}
          onSelectElement={setSelectedElement}
          cyRef={cyRef}
        />

        {/* Node & Edge Inspector Side-Sheet */}
        <NodeInspector
          selectedElement={selectedElement}
          onClose={() => setSelectedElement(null)}
          tenantId={tenantId}
        />
      </div>

      {/* Bottom Time-Travel Scrubber */}
      <TimeTravelSlider asOf={asOf} onAsOfChange={setAsOf} />
    </div>
  );
}
