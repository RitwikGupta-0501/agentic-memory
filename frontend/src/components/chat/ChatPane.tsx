"use client";

import React, { useState, useRef, useEffect } from "react";
import { Trash, PlusCircle, ChatCircleDots } from "@phosphor-icons/react";
import { PillDropdown } from "../ui/PillDropdown";
import { ChatMessage, IsolationMode } from "@/lib/types";
import { MessageItem } from "./MessageItem";
import { PromptInput } from "./PromptInput";
import { streamChatMessage, fetchSessionEpisodes } from "@/lib/api";

interface ChatPaneProps {
  tenantId: string;
  userId: string;
  isolationMode?: IsolationMode;
  sessionId: string;
  sessions: { id: string; label: string }[];
  onSelectSession: (id: string) => void;
  onTurnComplete: () => void;
  onNewSession: () => void;
}

export function ChatPane({
  tenantId,
  userId,
  isolationMode = "tenant_shared",
  sessionId,
  sessions,
  onSelectSession,
  onTurnComplete,
  onNewSession,
}: ChatPaneProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isGenerating, setIsGenerating] = useState(false);
  const [currentThought, setCurrentThought] = useState<string | null>(null);
  const [streamingAnswer, setStreamingAnswer] = useState<string | null>(null);
  const [isLoadingHistory, setIsLoadingHistory] = useState(false);
  const scrollAnchorRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    scrollAnchorRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isGenerating, currentThought, streamingAnswer]);

  // When sessionId changes (e.g. user selected a historical session or created a new one)
  useEffect(() => {
    if (!sessionId) {
      setMessages([]);
      return;
    }

    let isSubscribed = true;
    setIsLoadingHistory(true);

    fetchSessionEpisodes(sessionId, tenantId, userId, isolationMode)
      .then((history) => {
        if (!isSubscribed) return;
        if (history && history.length > 0) {
          setMessages(history);
        } else {
          // Clean empty start for new sessions (no artificial default agent prompt)
          setMessages([]);
        }
      })
      .catch(() => {
        if (isSubscribed) {
          setMessages([]);
        }
      })
      .finally(() => {
        if (isSubscribed) setIsLoadingHistory(false);
      });

    return () => {
      isSubscribed = false;
    };
  }, [sessionId, tenantId, userId, isolationMode]);

  const handleSendMessage = async (text: string) => {
    if (!text.trim() || isGenerating) return;

    const userMsg: ChatMessage = {
      id: `usr_${Date.now()}`,
      role: "user",
      content: text,
      timestamp: Date.now(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setIsGenerating(true);
    setStreamingAnswer(null);
    setCurrentThought("Consulting multi-tier graph memory...");

    let partialAnswer = "";

    await streamChatMessage({
      prompt: text,
      tenantId,
      sessionId,
      userId,
      isolationMode,
      onThought: (thought) => {
        setCurrentThought(thought);
      },
      onAnswer: (answer) => {
        partialAnswer = answer;
        setStreamingAnswer(answer);
      },
      onError: (errMsg) => {
        setMessages((prev) => [
          ...prev,
          {
            id: `err_${Date.now()}`,
            role: "error",
            content: errMsg,
            timestamp: Date.now(),
          },
        ]);
      },
      onDone: () => {
        setIsGenerating(false);
        setCurrentThought(null);
        setStreamingAnswer(null);
        if (partialAnswer) {
          setMessages((prev) => [
            ...prev,
            {
              id: `ag_${Date.now()}`,
              role: "agent",
              content: partialAnswer,
              timestamp: Date.now(),
            },
          ]);
        }
        // Trigger graph refresh in the right pane so newly created nodes appear
        onTurnComplete();
      },
    });
  };

  const handleClearChat = () => {
    setMessages([]);
    setStreamingAnswer(null);
  };

  return (
    <div className="flex flex-col h-full rounded-[2rem] bg-m3-surface-container-lowest/60 border border-white/10 backdrop-blur-xl p-4 shadow-double-bezel overflow-hidden">
      {/* Pane Header */}
      <div className="flex flex-wrap items-center justify-between gap-2 px-2 pb-3 mb-2 border-b border-white/5">
        {/* Left: Title & Styled Session Switcher Dropdown */}
        <div className="flex items-center gap-2.5">
          <div className="flex items-center gap-1.5">
            <ChatCircleDots size={18} className="text-m3-primary" />
            <h2 className="text-sm font-semibold text-white tracking-tight">Chat</h2>
          </div>

          {/* Styled Session Selector Dropdown */}
          <PillDropdown
            value={sessionId}
            options={sessions.map((s) => ({
              value: s.id,
              label: s.label.replace(/^[^\w\s]+/, "").trim(),
            }))}
            onChange={onSelectSession}
            label="Session:"
            className="w-[180px] py-1"
          />
        </div>

        {/* Right: Retained New Session Button & Clear Button */}
        <div className="flex items-center gap-1.5">
          {/* New Session Button */}
          <button
            onClick={onNewSession}
            title="Start new conversation session"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold text-white bg-m3-primary/20 hover:bg-m3-primary/30 border border-m3-primary/35 active:scale-[0.97] transition-all cursor-pointer shadow-sm"
          >
            <PlusCircle size={14} weight="bold" className="text-m3-primary" />
            <span>New Session</span>
          </button>

          {/* Clear Button */}
          <button
            onClick={handleClearChat}
            title="Clear active conversation view"
            className="flex items-center gap-1 px-2.5 py-1.5 rounded-full text-xs text-m3-on-surface-variant hover:text-white hover:bg-white/5 border border-white/5 transition-all cursor-pointer"
          >
            <Trash size={13} />
            <span className="text-[11px]">Clear</span>
          </button>
        </div>
      </div>

      {/* Messages Feed */}
      <div className="flex-1 overflow-y-auto px-1 pr-2 space-y-1">
        {isLoadingHistory && (
          <div className="flex items-center justify-center py-6 text-xs text-m3-on-surface-variant font-mono animate-pulse">
            Loading session history...
          </div>
        )}

        {/* Clean Empty State (No Artificial Default Agent Message) */}
        {messages.length === 0 && !isLoadingHistory && !streamingAnswer && (
          <div className="flex flex-col items-center justify-center h-full text-center p-6 text-m3-on-surface-variant">
            <div className="w-10 h-10 rounded-full bg-white/5 border border-white/10 flex items-center justify-center mb-3 text-m3-primary">
              <ChatCircleDots size={22} />
            </div>
            <p className="text-xs font-medium text-white/80">Fresh Session Started</p>
            <p className="text-[11px] text-white/40 mt-1 max-w-xs leading-relaxed">
              Ask anything to explore or record memories in FalkorDB.
            </p>
          </div>
        )}

        {messages.map((msg) => (
          <MessageItem key={msg.id} message={msg} />
        ))}

        {/* Live Streaming Message Card */}
        {streamingAnswer && (
          <MessageItem
            message={{
              id: "streaming-msg",
              role: "agent",
              content: streamingAnswer,
              timestamp: Date.now(),
            }}
          />
        )}

        {/* Minimalist Thinking State Layer */}
        {isGenerating && !streamingAnswer && (
          <div className="flex items-center gap-2 py-3 px-2 text-xs text-m3-on-surface-variant font-mono animate-pulse">
            <span className="flex h-2 w-2 rounded-full bg-m3-primary"></span>
            <span>{currentThought || "Retrieving memory & reasoning..."}</span>
          </div>
        )}

        <div ref={scrollAnchorRef} />
      </div>

      {/* Fixed Bottom Prompt Input */}
      <div className="pt-2">
        <PromptInput onSendMessage={handleSendMessage} disabled={isGenerating} />
      </div>
    </div>
  );
}
