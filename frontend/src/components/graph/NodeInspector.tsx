"use client";

import React, { useState } from "react";
import { X, Info, Clock, ChatCircleText, Sparkle } from "@phosphor-icons/react";

interface NodeInspectorProps {
  selectedElement: any | null;
  onClose: () => void;
  tenantId: string;
}

export function NodeInspector({ selectedElement, onClose, tenantId }: NodeInspectorProps) {
  const [history, setHistory] = useState<any[] | null>(null);
  const [loadingHistory, setLoadingHistory] = useState(false);

  if (!selectedElement) return null;

  const data = selectedElement.data || {};
  const props = data.properties || {};
  const isNode = !data.source;
  const isEpisode = (data.labels || []).includes("Episode") || (data.id && String(data.id).startsWith("ep_")) || props.role !== undefined;
  const isSession = (data.labels || []).includes("Session") || (data.id && String(data.id).startsWith("session_"));

  const title = isNode
    ? (data.displayLabel || data.name || data.label || data.id)
    : (data.predicate || data.label || "Relationship");

  const fetchHistory = async () => {
    const entityName = props.name || data.name;
    if (!entityName) return;
    setLoadingHistory(true);
    try {
      const res = await fetch(`/api/v1/memory/semantic/history/${encodeURIComponent(entityName)}?tenant_id=${tenantId}`);
      if (res.ok) {
        const body = await res.json();
        setHistory(body.history || []);
      }
    } catch (e) {
      console.error("Failed to load history:", e);
    } finally {
      setLoadingHistory(false);
    }
  };

  return (
    <div className="absolute top-12 right-3 bottom-12 w-84 rounded-[1.75rem] bg-m3-surface-container-high/95 backdrop-blur-2xl border border-white/10 shadow-2xl p-4 flex flex-col z-20 text-xs text-m3-on-surface">
      {/* Header */}
      <div className="flex items-start justify-between gap-2 pb-3 border-b border-white/5">
        <div>
          <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wider bg-white/10 text-white">
            {isNode ? `Node: ${data.tier || "Memory"}` : "Relationship"}
          </span>
          <h3 className="text-sm font-bold text-white mt-1.5 break-words line-clamp-2">{title}</h3>
          <span className="text-[10px] text-m3-on-surface-variant font-mono">ID: {data.id}</span>
        </div>
        <button
          onClick={onClose}
          className="p-1 rounded-full hover:bg-white/10 text-m3-on-surface-variant hover:text-white transition-colors cursor-pointer"
        >
          <X size={16} />
        </button>
      </div>

      {/* Property Details */}
      <div className="flex-1 overflow-y-auto py-3 space-y-3 pr-1">
        {/* Full Turn Content Preview for Episodes */}
        {isEpisode && props.content && (
          <div className="rounded-xl bg-m3-primary/10 border border-m3-primary/20 p-2.5 space-y-1">
            <div className="flex items-center gap-1.5 text-m3-primary text-[11px] font-semibold uppercase tracking-wider">
              <ChatCircleText size={14} />
              <span>Full Message ({props.role || "turn"})</span>
            </div>
            <p className="text-white text-xs leading-relaxed whitespace-pre-wrap font-sans">
              "{props.content}"
            </p>
          </div>
        )}

        {/* Session Details */}
        {isSession && (
          <div className="rounded-xl bg-indigo-500/10 border border-indigo-500/20 p-2.5 space-y-1">
            <div className="text-[10px] font-semibold text-indigo-400 uppercase">
              Conversation Session
            </div>
            <div className="font-mono text-[11px] text-white">
              <div>Turns: {props.episode_count ?? 0}</div>
              <div>Created: {props.created_at ? new Date(props.created_at * 1000).toLocaleString() : "Unknown"}</div>
            </div>
          </div>
        )}

        {/* Attributes Map */}
        <div>
          <h4 className="text-[11px] font-semibold text-m3-primary uppercase tracking-wider mb-1.5 flex items-center gap-1">
            <Info size={13} />
            <span>Node Attributes</span>
          </h4>
          <div className="space-y-1.5 rounded-xl bg-black/30 p-2.5 border border-white/5 font-mono text-[11px]">
            {Object.entries({ ...data, ...props }).map(([key, val]) => {
              if (["id", "name", "label", "displayLabel", "source", "target", "properties", "labels", "content"].includes(key)) return null;
              if (val === undefined || val === null) return null;
              const displayVal = typeof val === "object" ? JSON.stringify(val) : String(val);
              return (
                <div key={key} className="flex flex-col border-b border-white/5 pb-1 last:border-0 last:pb-0">
                  <span className="text-m3-on-surface-variant text-[10px]">{key}</span>
                  <span className="text-white break-all">{displayVal}</span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Bi-Temporal Edge Validity */}
        {!isNode && (
          <div className="rounded-xl bg-black/30 p-2.5 border border-white/5 space-y-1 font-mono text-[11px]">
            <div className="text-[10px] font-semibold text-tier-episodic uppercase mb-1">
              Temporal Validity
            </div>
            <div>Valid From: {data.valid_from ? new Date(data.valid_from * 1000).toLocaleString() : "Genesis"}</div>
            <div>
              Status:{" "}
              {data.is_invalidated ? (
                <span className="text-amber-400 font-semibold">Superseded / Inactive</span>
              ) : (
                <span className="text-emerald-400 font-semibold">Active Belief</span>
              )}
            </div>
          </div>
        )}

        {/* Historical Evolution Timeline Button */}
        {isNode && (props.name || data.name) && (
          <div>
            <button
              onClick={fetchHistory}
              disabled={loadingHistory}
              className="w-full flex items-center justify-center gap-1.5 py-2 px-3 rounded-xl bg-white/5 hover:bg-white/10 active:scale-[0.98] border border-white/10 text-xs font-medium text-white transition-all cursor-pointer"
            >
              <Clock size={14} className="text-m3-primary" />
              <span>{loadingHistory ? "Loading History..." : "View Chronological Evolution"}</span>
            </button>

            {history && (
              <div className="mt-2 space-y-1.5 rounded-xl bg-black/40 p-2 border border-white/5 max-h-40 overflow-y-auto">
                <div className="text-[10px] font-semibold text-m3-primary uppercase mb-1">
                  Evolution ({history.length} events)
                </div>
                {history.map((h, i) => (
                  <div key={i} className="text-[10px] font-mono border-b border-white/5 pb-1">
                    <div>{h.predicate} → <span className="text-white">{h.object}</span></div>
                    <div className="text-m3-on-surface-variant text-[9px]">
                      {h.valid_at ? new Date(h.valid_at * 1000).toLocaleTimeString() : ""}
                      {h.invalid_at ? " (Superseded)" : " (Current)"}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
