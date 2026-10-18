"use client";

import React, { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Copy, Check, Robot, User, WarningCircle } from "@phosphor-icons/react";
import { ChatMessage } from "@/lib/types";

interface MessageItemProps {
  message: ChatMessage;
}

export function MessageItem({ message }: MessageItemProps) {
  const [copied, setCopied] = useState(false);
  const isUser = message.role === "user";
  const isError = message.role === "error";

  const handleCopy = () => {
    navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (isUser) {
    return (
      <div className="flex justify-end gap-2.5 my-3">
        <div className="max-w-[85%] rounded-[1.25rem] rounded-tr-sm bg-m3-surface-container-high px-4 py-2.5 border border-white/5 shadow-sm text-sm text-white leading-relaxed">
          <p className="whitespace-pre-wrap">{message.content}</p>
        </div>
        <div className="flex-shrink-0 flex items-center justify-center w-7 h-7 rounded-full bg-white/10 text-white text-xs mt-0.5">
          <User size={14} weight="bold" />
        </div>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex justify-start gap-2.5 my-3">
        <div className="flex-shrink-0 flex items-center justify-center w-7 h-7 rounded-full bg-red-500/20 text-red-400 text-xs mt-0.5">
          <WarningCircle size={15} weight="bold" />
        </div>
        <div className="max-w-[85%] rounded-[1.25rem] rounded-tl-sm bg-red-950/30 border border-red-500/30 px-4 py-3 text-sm text-red-200">
          <div className="font-semibold text-xs tracking-wider uppercase mb-1 text-red-400">
            System Notice
          </div>
          <p className="whitespace-pre-wrap leading-relaxed">{message.content}</p>
        </div>
      </div>
    );
  }

  // Agent Turn: Vanguard Double-Bezel Concentric Architecture
  return (
    <div className="flex justify-start gap-2.5 my-3">
      <div className="flex-shrink-0 flex items-center justify-center w-7 h-7 rounded-full bg-m3-primary/10 border border-m3-primary/20 text-m3-primary mt-1">
        <Robot size={15} weight="bold" />
      </div>

      <div className="max-w-[90%] p-1 rounded-[1.75rem] rounded-tl-sm bg-white/[0.025] border border-white/10 shadow-double-bezel">
        <div className="relative px-4 py-3 rounded-[calc(1.75rem-0.25rem)] rounded-tl-none bg-m3-surface-container/90 border border-white/5 shadow-rim-light text-sm text-m3-on-surface">
          {/* Header Action Bar */}
          <div className="flex items-center justify-between gap-2 pb-2 mb-2 border-b border-white/5 text-[11px] text-m3-on-surface-variant font-mono">
            <span className="flex items-center gap-1.5 text-m3-primary font-medium">
              AegisGraph Cognitive Agent
            </span>
            <button
              onClick={handleCopy}
              className="flex items-center gap-1 hover:text-white transition-colors cursor-pointer"
              title="Copy to clipboard"
            >
              {copied ? <Check size={12} className="text-emerald-400" /> : <Copy size={12} />}
              <span>{copied ? "Copied" : "Copy"}</span>
            </button>
          </div>

          {/* Markdown Content */}
          <div className="prose prose-invert prose-sm max-w-none space-y-2 leading-relaxed text-m3-on-surface">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                code({ node, inline, className, children, ...props }: any) {
                  return inline ? (
                    <code className="px-1.5 py-0.5 rounded bg-black/40 text-tier-episodic font-mono text-[12px] border border-white/5" {...props}>
                      {children}
                    </code>
                  ) : (
                    <pre className="p-3 my-2 rounded-xl bg-black/60 border border-white/10 overflow-x-auto text-[12px] font-mono text-white">
                      <code {...props}>{children}</code>
                    </pre>
                  );
                },
                ul({ children }) {
                  return <ul className="list-disc pl-4 space-y-1 my-1.5 text-m3-on-surface">{children}</ul>;
                },
                ol({ children }) {
                  return <ol className="list-decimal pl-4 space-y-1 my-1.5 text-m3-on-surface">{children}</ol>;
                },
                p({ children }) {
                  return <p className="leading-relaxed mb-2 last:mb-0">{children}</p>;
                },
              }}
            >
              {message.content}
            </ReactMarkdown>
          </div>
        </div>
      </div>
    </div>
  );
}
