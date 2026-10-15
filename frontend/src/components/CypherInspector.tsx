"use client";

import React, { useState } from "react";
import { Terminal, Clock, RefreshCw, Zap, Info, ShieldAlert } from "lucide-react";

interface CypherInspectorProps {
  selectedNode: any;
  includeInvalidated: boolean;
  setIncludeInvalidated: (val: boolean) => void;
  onTriggerConsolidation: () => void;
  isConsolidating: boolean;
  lastCypherQuery: string;
}

export default function CypherInspector({
  selectedNode,
  includeInvalidated,
  setIncludeInvalidated,
  onTriggerConsolidation,
  isConsolidating,
  lastCypherQuery,
}: CypherInspectorProps) {
  const [activeTab, setActiveTab] = useState<"cypher" | "node">("cypher");

  return (
    <div className="w-full h-full flex flex-col bg-[#070b12] border border-slate-800 rounded-lg overflow-hidden text-xs">
      {/* Header with Tabs */}
      <div className="h-10 px-3 bg-slate-900/90 border-b border-slate-800 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Terminal className="w-4 h-4 text-cyan-400" />
          <span className="font-semibold text-slate-300 uppercase tracking-wider">
            Cypher & Provenance Inspector
          </span>
        </div>

        <div className="flex rounded bg-slate-950 p-0.5 border border-slate-800">
          <button
            onClick={() => setActiveTab("cypher")}
            className={`px-2 py-0.5 rounded text-[11px] ${
              activeTab === "cypher" ? "bg-slate-800 text-cyan-400" : "text-slate-400"
            }`}
          >
            Live Cypher
          </button>
          <button
            onClick={() => setActiveTab("node")}
            className={`px-2 py-0.5 rounded text-[11px] ${
              activeTab === "node" ? "bg-slate-800 text-cyan-400" : "text-slate-400"
            }`}
          >
            Node State
          </button>
        </div>
      </div>

      {/* Control Actions Bar */}
      <div className="p-3 bg-slate-950/60 border-b border-slate-800 space-y-2.5">
        {/* Time-Travel Toggle */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5 text-slate-300">
            <Clock className="w-3.5 h-3.5 text-amber-400" />
            <span className="font-medium">Show Historical Invalidations:</span>
          </div>
          <button
            onClick={() => setIncludeInvalidated(!includeInvalidated)}
            className={`px-2.5 py-1 rounded text-[11px] font-medium border transition-colors ${
              includeInvalidated
                ? "bg-red-950/80 border-red-700 text-red-300"
                : "bg-slate-800 border-slate-700 text-slate-300"
            }`}
          >
            {includeInvalidated ? "History Active (Show Valid_To)" : "Current Belief Only"}
          </button>
        </div>

        {/* Memory Consolidation Trigger */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-1.5 text-slate-300">
            <Zap className="w-3.5 h-3.5 text-cyan-400" />
            <span className="font-medium">Slow-Stream Engine:</span>
          </div>
          <button
            onClick={onTriggerConsolidation}
            disabled={isConsolidating}
            className="flex items-center gap-1.5 bg-cyan-950 border border-cyan-800 hover:bg-cyan-900 text-cyan-300 px-2.5 py-1 rounded text-[11px] font-medium transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-3 h-3 ${isConsolidating ? "animate-spin" : ""}`} />
            <span>{isConsolidating ? "Consolidating..." : "Run Consolidation"}</span>
          </button>
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 overflow-y-auto p-3">
        {activeTab === "cypher" ? (
          <div className="space-y-3">
            <div>
              <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-1">
                Last OpenCypher Mutation:
              </div>
              <pre className="p-2.5 rounded bg-slate-950 border border-slate-800 text-emerald-400 font-mono text-[11px] overflow-x-auto whitespace-pre-wrap leading-relaxed">
                {lastCypherQuery ||
                  `// Centralized Bi-Temporal Invalidation & Upsert
MATCH (s:Entity {name: $subject})-[old_r:RELATES_TO {predicate: $predicate}]->(old_o:Entity)
WHERE old_r.valid_to IS NULL AND old_o.name <> $new_object
SET old_r.valid_to = $now, old_r.invalidated_by_episode = $episode_id
WITH count(old_r) AS invalidated_count
MERGE (s:Entity {name: $subject})
MERGE (new_o:Entity {name: $new_object})
MERGE (ep:Episode {id: $episode_id})
CREATE (s)-[new_r:RELATES_TO {
    predicate: $predicate,
    valid_from: $now,
    valid_to: NULL,
    confidence: $confidence,
    source_episode: $episode_id
}]->(new_o)
CREATE (new_o)-[:DERIVED_FROM]->(ep)
RETURN invalidated_count, new_r`}
              </pre>
            </div>

            <div className="p-2 rounded bg-slate-900/50 border border-slate-800 text-slate-400 text-[11px] flex gap-2">
              <Info className="w-4 h-4 text-cyan-400 shrink-0 mt-0.5" />
              <span>
                FalkorDB enforces explicit Cypher mutations with parameter binding, maintaining zero context amnesia and complete audit trails.
              </span>
            </div>
          </div>
        ) : (
          <div>
            {selectedNode ? (
              <div className="space-y-2">
                <div className="flex items-center justify-between pb-2 border-b border-slate-800">
                  <span className="font-bold text-slate-200 text-sm">
                    {selectedNode.label || selectedNode.id}
                  </span>
                  <span className="uppercase text-[10px] px-2 py-0.5 rounded bg-slate-800 text-cyan-400 font-semibold">
                    {selectedNode.tier} Tier
                  </span>
                </div>

                <div className="pt-2">
                  <span className="text-slate-400 text-[11px] font-semibold">Properties:</span>
                  <pre className="mt-1 p-2 rounded bg-slate-950 border border-slate-800 font-mono text-[10px] text-slate-300 overflow-x-auto">
                    {JSON.stringify(selectedNode.properties || {}, null, 2)}
                  </pre>
                </div>
              </div>
            ) : (
              <div className="h-full flex flex-col items-center justify-center text-slate-500 text-center p-4">
                <Info className="w-6 h-6 mb-2 opacity-50" />
                <p>Click any node in the graph canvas to inspect properties and provenance relationships.</p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
