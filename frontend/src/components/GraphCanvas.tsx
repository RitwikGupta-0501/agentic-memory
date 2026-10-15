"use client";

import React, { useEffect, useRef } from "react";
import cytoscape, { Core } from "cytoscape";
import { ZoomIn, ZoomOut, RefreshCw, Layers } from "lucide-react";

interface GraphCanvasProps {
  nodes: any[];
  edges: any[];
  onSelectNode: (nodeData: any) => void;
  onRefresh: () => void;
  isLoading: boolean;
}

export default function GraphCanvas({
  nodes,
  edges,
  onSelectNode,
  onRefresh,
  isLoading,
}: GraphCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    // Initialize Cytoscape core
    const cy = cytoscape({
      container: containerRef.current,
      style: [
        {
          selector: "node",
          style: {
            label: "data(label)",
            color: "#ffffff",
            "text-valign": "center",
            "text-halign": "center",
            "font-size": "10px",
            "text-wrap": "ellipsis",
            "text-max-width": "80px",
            width: 44,
            height: 44,
            "border-width": 2,
            "border-color": "#ffffff",
          },
        },
        // Tier 1: Working Memory (Yellow)
        {
          selector: 'node[tier = "working"]',
          style: {
            "background-color": "#eab308",
            "border-color": "#fef08a",
          },
        },
        // Tier 2: Episodic Memory (Blue)
        {
          selector: 'node[tier = "episodic"]',
          style: {
            "background-color": "#2563eb",
            "border-color": "#93c5fd",
          },
        },
        // Tier 3: Semantic Memory (Green)
        {
          selector: 'node[tier = "semantic"]',
          style: {
            "background-color": "#16a34a",
            "border-color": "#86efac",
          },
        },
        // Tier 4: Procedural Memory (Purple)
        {
          selector: 'node[tier = "procedural"]',
          style: {
            "background-color": "#9333ea",
            "border-color": "#d8b4fe",
          },
        },
        // Consolidated Insight (Cyan)
        {
          selector: 'node[tier = "consolidated"]',
          style: {
            "background-color": "#0891b2",
            "border-color": "#67e8f9",
          },
        },
        // Active Edge Styles
        {
          selector: "edge",
          style: {
            width: 2,
            "line-color": "#475569",
            "target-arrow-color": "#475569",
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
            label: "data(label)",
            "font-size": "8px",
            color: "#94a3b8",
            "text-rotation": "autorotate",
            "text-margin-y": -8,
          },
        },
        // Superseded Historical Edges (Red Dashed)
        {
          selector: "edge[?is_superseded]",
          style: {
            "line-color": "#ef4444",
            "target-arrow-color": "#ef4444",
            "line-style": "dashed",
            width: 2.5,
            label: "data(label) [INVALIDATED]",
            color: "#f87171",
          },
        },
      ],
      elements: {
        nodes: nodes,
        edges: edges,
      },
      layout: {
        name: "cose",
        animate: false,
        nodeRepulsion: () => 4500,
        idealEdgeLength: () => 90,
      },
    });

    cy.on("tap", "node", (evt) => {
      const node = evt.target;
      onSelectNode(node.data());
    });

    cyRef.current = cy;

    return () => {
      cy.destroy();
    };
  }, [nodes, edges, onSelectNode]);

  const handleZoomIn = () => cyRef.current?.zoom(cyRef.current.zoom() * 1.2);
  const handleZoomOut = () => cyRef.current?.zoom(cyRef.current.zoom() * 0.8);
  const handleFit = () => cyRef.current?.fit();

  return (
    <div className="relative w-full h-full bg-[#070b12] border border-slate-800 rounded-lg overflow-hidden flex flex-col">
      {/* Top Legend Bar */}
      <div className="h-10 px-3 bg-slate-900/90 border-b border-slate-800 flex items-center justify-between text-xs z-10">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-yellow-500 inline-block"></span>
            <span className="text-slate-300">Working</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-blue-600 inline-block"></span>
            <span className="text-slate-300">Episodic</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-600 inline-block"></span>
            <span className="text-slate-300">Semantic</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-purple-600 inline-block"></span>
            <span className="text-slate-300">Procedural</span>
          </div>
          <div className="flex items-center gap-1.5">
            <span className="w-4 h-0.5 border-t-2 border-dashed border-red-500 inline-block"></span>
            <span className="text-slate-400">Invalidated (Historic)</span>
          </div>
        </div>

        <div className="flex items-center gap-1">
          <button
            onClick={handleZoomIn}
            className="p-1 hover:bg-slate-800 rounded text-slate-300"
            title="Zoom In"
          >
            <ZoomIn className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={handleZoomOut}
            className="p-1 hover:bg-slate-800 rounded text-slate-300"
            title="Zoom Out"
          >
            <ZoomOut className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={handleFit}
            className="p-1 hover:bg-slate-800 rounded text-slate-300"
            title="Fit to Canvas"
          >
            <Layers className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={onRefresh}
            disabled={isLoading}
            className={`p-1 hover:bg-slate-800 rounded text-slate-300 ${
              isLoading ? "animate-spin" : ""
            }`}
            title="Refresh Graph"
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Cytoscape Container */}
      <div ref={containerRef} className="flex-1 w-full h-full" />
    </div>
  );
}
