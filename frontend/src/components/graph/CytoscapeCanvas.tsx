"use client";

import React, { useEffect, useRef } from "react";
import cytoscape from "cytoscape";
import { MemoryTier } from "@/lib/types";

interface CytoscapeCanvasProps {
  elements: { nodes: any[]; edges: any[] };
  selectedTier: MemoryTier;
  selectedSessionFilter?: string;
  includeInvalidated: boolean;
  onSelectElement: (elem: any | null) => void;
  cyRef: React.MutableRefObject<cytoscape.Core | null>;
}

function formatNodeDisplay(data: any): string {
  const props = data.properties || {};
  const labels: string[] = data.labels || [];
  const nid = String(data.id || "");

  const isSession =
    labels.includes("Session") ||
    data.type === "Session" ||
    nid.startsWith("session_") ||
    data.tier === "episodic" && props.episode_count !== undefined;

  const isEpisode =
    labels.includes("Episode") ||
    data.type === "Episode" ||
    nid.startsWith("ep_") ||
    props.role !== undefined;

  const isEntity = labels.includes("Entity") || data.tier === "semantic";
  const isWorking = labels.includes("SubTask") || labels.includes("TaskRun") || data.tier === "working";
  const isProcedural =
    labels.includes("Procedure") ||
    labels.includes("ActionStep") ||
    labels.includes("Guardrail") ||
    data.tier === "procedural";

  if (isSession) {
    const sid = String(props.id || nid || "");
    const shortId = sid.length > 8 ? sid.slice(-6) : sid;
    const count = props.episode_count ?? 0;
    const author = props.user_id || data.user_id;
    const authorTag = author ? ` [${author}]` : "";
    return count > 0 ? `💬 Session ${shortId}${authorTag}\n(${count} turns)` : `💬 Session ${shortId}${authorTag}`;
  }

  if (isEpisode) {
    const rawRole = String(props.role || data.role || (data.label?.toLowerCase().includes("agent") ? "agent" : "user")).toLowerCase();
    const isAgent = rawRole === "agent";
    const icon = isAgent ? "🤖" : "👤";
    const roleTitle = isAgent ? "Agent" : "User";
    const content = String(props.content || data.content || "").replace(/\s+/g, " ").trim();
    const author = props.user_id || data.user_id;
    const authorTag = author ? ` [${author}]` : "";

    if (content) {
      const preview = content.length > 22 ? content.substring(0, 22) + "…" : content;
      return `${icon} ${roleTitle}${authorTag}:\n"${preview}"`;
    }
    const rawLabel = String(data.label || "");
    if (rawLabel && !rawLabel.startsWith("Ep: ep_")) {
      return `${icon} ${rawLabel}${authorTag}`;
    }
    return `${icon} ${roleTitle}${authorTag} Turn`;
  }

  if (isEntity) {
    const name = props.name || props.canonical_name || data.name || data.label || "Entity";
    const type = props.type || data.type;
    const isShared = data.scope === "shared" || (!props.user_id && !data.user_id) || props.scope === "tenant";
    const scopeTag = isShared ? " [Shared]" : ` [${props.user_id || data.user_id}]`;
    return type ? `🏷️ ${name}${scopeTag}\n(${type})` : `🏷️ ${name}${scopeTag}`;
  }

  if (isWorking) {
    const title = props.title || props.goal || data.label || "Task";
    const preview = title.length > 22 ? title.substring(0, 22) + "…" : title;
    const author = props.user_id || data.user_id;
    const authorTag = author ? ` [${author}]` : "";
    return `⚡ ${preview}${authorTag}`;
  }

  if (isProcedural) {
    const name = props.name || props.rule_text || data.label || "Guardrail";
    const preview = name.length > 22 ? name.substring(0, 22) + "…" : name;
    return `🛡️ ${preview} [Shared]`;
  }

  return data.label || "Node";
}

export function CytoscapeCanvas({
  elements,
  selectedTier,
  selectedSessionFilter = "all",
  includeInvalidated,
  onSelectElement,
  cyRef,
}: CytoscapeCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    // 1. Filter out internal bookkeeping metadata nodes
    const validNodes = (elements.nodes || []).filter((n) => {
      const data = n.data || {};
      const labels = data.labels || [];
      if (labels.includes("GraphMetadata")) return false;
      if (data.tier === "unknown" && data.label === "Node") return false;
      return true;
    });

    // 2. Session Scoping Filter
    let sessionScopedNodeIds: Set<string> | null = null;

    if (selectedSessionFilter && selectedSessionFilter !== "all") {
      sessionScopedNodeIds = new Set<string>();

      // A: Add session root node
      validNodes.forEach((n) => {
        const d = n.data || {};
        const p = d.properties || {};
        if (d.id === selectedSessionFilter || p.id === selectedSessionFilter) {
          sessionScopedNodeIds!.add(String(d.id));
        }
      });

      // B: Add episodes belonging to this session
      validNodes.forEach((n) => {
        const d = n.data || {};
        const p = d.properties || {};
        if (p.session_id === selectedSessionFilter || d.session_id === selectedSessionFilter) {
          sessionScopedNodeIds!.add(String(d.id));
        }
      });

      // C: Add connected semantic entities, procedures, and tasks linked to these episodes
      (elements.edges || []).forEach((e) => {
        const ed = e.data || {};
        const src = String(ed.source);
        const tgt = String(ed.target);
        if (sessionScopedNodeIds!.has(src)) {
          sessionScopedNodeIds!.add(tgt);
        } else if (sessionScopedNodeIds!.has(tgt)) {
          sessionScopedNodeIds!.add(src);
        }
      });
    }

    // 3. Filter by Tier & Session Scope
    const filteredNodes = validNodes
      .filter((n) => {
        const data = n.data || {};
        const nid = String(data.id || "");

        // If session filtering is active, only include nodes in the active session subgraph
        if (sessionScopedNodeIds && !sessionScopedNodeIds.has(nid)) {
          return false;
        }

        const tier = data.tier || "semantic";
        if (selectedTier === "all") return true;
        if (selectedTier === "working") return tier === "working" || data.type === "TaskRun" || data.type === "SubTask";
        if (selectedTier === "episodic") return tier === "episodic" || data.type === "Episode" || data.type === "Session";
        if (selectedTier === "semantic") return tier === "semantic" || data.type === "Entity" || data.type === "Concept";
        if (selectedTier === "procedural") return tier === "procedural" || data.type === "Procedure" || data.type === "Guardrail";
        return true;
      })
      .map((n) => {
        // Enrich label with human-readable formatting
        const formattedLabel = formatNodeDisplay(n.data);
        return {
          ...n,
          data: {
            ...n.data,
            displayLabel: formattedLabel,
          },
        };
      });

    const nodeIds = new Set(filteredNodes.map((n) => String(n.data.id || n.data.name)));

    const filteredEdges = (elements.edges || []).filter((e) => {
      const data = e.data || {};
      if (!includeInvalidated && data.is_invalidated) return false;
      return nodeIds.has(String(data.source)) && nodeIds.has(String(data.target));
    });

    const cy = cytoscape({
      container: containerRef.current,
      elements: [...filteredNodes, ...filteredEdges],
      style: [
        // Base Node Style
        {
          selector: "node",
          style: {
            "background-color": "#81C995",
            label: "data(displayLabel)",
            color: "#FFFFFF",
            "font-size": "10px",
            "font-family": "Plus Jakarta Sans, sans-serif",
            "font-weight": 600,
            "text-valign": "bottom",
            "text-margin-y": 8,
            "text-wrap": "wrap",
            "text-max-width": "140px",
            "text-background-color": "#090D16",
            "text-background-opacity": 0.92,
            "text-background-padding": "4px",
            "text-background-shape": "roundrectangle",
            "text-border-width": 1,
            "text-border-color": "rgba(255, 255, 255, 0.15)",
            width: 40,
            height: 40,
            "border-width": 2,
            "border-color": "rgba(255, 255, 255, 0.25)",
            "transition-property": "background-color, border-color, width, height",
            "transition-duration": 0.2,
          },
        },
        // Session Root Node (Deep Indigo Hexagon)
        {
          selector: 'node[tier = "episodic"][labels *= "Session"], node[type = "Session"], node[id ^= "session_"]',
          style: {
            "background-color": "#4F46E5",
            "border-color": "#818CF8",
            shape: "hexagon",
            width: 48,
            height: 48,
            "border-width": 3,
          },
        },
        // Episode Turns (User vs Agent)
        {
          selector: 'node[tier = "episodic"][properties.role = "agent"], node[tier = "episodic"][role = "agent"]',
          style: {
            "background-color": "#0EA5E9",
            "border-color": "#7DD3FC",
            shape: "round-rectangle",
            width: 42,
            height: 36,
          },
        },
        {
          selector: 'node[tier = "episodic"][properties.role = "user"], node[tier = "episodic"][role = "user"]',
          style: {
            "background-color": "#38BDF8",
            "border-color": "#BAE6FD",
            shape: "round-rectangle",
            width: 42,
            height: 36,
          },
        },
        // Working Memory Tier (Golden Amber Cut-Rectangle)
        {
          selector: 'node[tier = "working"], node[type = "TaskRun"], node[type = "SubTask"]',
          style: {
            "background-color": "#F59E0B",
            "border-color": "#FDE68A",
            shape: "cut-rectangle",
            width: 40,
            height: 40,
          },
        },
        // Semantic Memory Tier (Vibrant Emerald Ellipse)
        {
          selector: 'node[tier = "semantic"], node[type = "Entity"], node[type = "Concept"]',
          style: {
            "background-color": "#10B981",
            "border-color": "#A7F3D0",
            shape: "ellipse",
            width: 44,
            height: 44,
          },
        },
        // Procedural Memory Tier (Amethyst Purple Diamond)
        {
          selector: 'node[tier = "procedural"], node[type = "Procedure"], node[type = "Guardrail"]',
          style: {
            "background-color": "#A855F7",
            "border-color": "#E9D5FF",
            shape: "diamond",
            width: 42,
            height: 42,
          },
        },
        // Base Edge Style (Active)
        {
          selector: "edge",
          style: {
            width: 2,
            "line-color": "#64748B",
            "target-arrow-color": "#94A3B8",
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
            label: "data(predicate)",
            "font-size": "9px",
            "font-family": "JetBrains Mono, monospace",
            color: "#E2E8F0",
            "text-background-color": "#05070A",
            "text-background-opacity": 0.88,
            "text-background-padding": "2px",
            "text-background-shape": "roundrectangle",
            "arrow-scale": 0.85,
            opacity: 0.85,
          },
        },
        // Special Edge Colors by Relationship Type
        {
          selector: 'edge[label = "NEXT_EPISODE"], edge[predicate = "NEXT_EPISODE"]',
          style: {
            "line-color": "#38BDF8",
            "target-arrow-color": "#38BDF8",
            width: 2.5,
          },
        },
        {
          selector: 'edge[label = "SESSION_HEAD"], edge[label = "SESSION_TAIL"]',
          style: {
            "line-color": "#818CF8",
            "target-arrow-color": "#818CF8",
            "line-style": "dotted",
            width: 2,
          },
        },
        {
          selector: 'edge[label = "DERIVED_FROM"], edge[label = "MENTIONED_IN"]',
          style: {
            "line-color": "#34D399",
            "target-arrow-color": "#34D399",
            width: 2,
          },
        },
        // Superseded Historical Edges (Bi-Temporal)
        {
          selector: "edge[is_invalidated = 1], edge[?is_invalidated]",
          style: {
            "line-style": "dashed",
            "line-color": "#F87171",
            "target-arrow-color": "#F87171",
            opacity: 0.55,
          },
        },
        // Selection Highlighting
        {
          selector: ":selected",
          style: {
            "border-width": 4,
            "border-color": "#FFFFFF",
            "underlay-color": "#FFFFFF",
            "underlay-padding": 5,
            "underlay-opacity": 0.25,
          },
        },
      ],
      layout: {
        name: "cose",
        animate: true,
        animationDuration: 500,
        randomize: false,
        componentSpacing: 120,
        nodeRepulsion: () => 500000,
        nodeOverlap: 25,
        idealEdgeLength: () => 90,
      },
    });

    cy.on("tap", "node, edge", (evt) => {
      const elem = evt.target;
      onSelectElement({ data: elem.data() });
    });

    cy.on("tap", (evt) => {
      if (evt.target === cy) {
        onSelectElement(null);
      }
    });

    cyRef.current = cy;

    return () => {
      cy.destroy();
    };
  }, [elements, selectedTier, selectedSessionFilter, includeInvalidated]);

  return <div ref={containerRef} className="w-full h-full" />;
}
