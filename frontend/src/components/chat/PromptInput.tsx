"use client";

import React, { useState, useRef, useEffect } from "react";
import { ArrowUp, Sparkle } from "@phosphor-icons/react";

interface PromptInputProps {
  onSendMessage: (text: string) => void;
  disabled?: boolean;
}

const STARTER_PROMPTS = [
  "What is our primary database configuration?",
  "Run database migration to FalkorDB and verify precautions",
  "What services connect to our core infrastructure?",
];

export function PromptInput({ onSendMessage, disabled = false }: PromptInputProps) {
  const [input, setInput] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleSubmit = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!input.trim() || disabled) return;
    onSendMessage(input.trim());
    setInput("");
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleSelectStarter = (prompt: string) => {
    if (disabled) return;
    onSendMessage(prompt);
  };

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 140)}px`;
    }
  }, [input]);

  return (
    <div className="flex flex-col gap-2 pt-2">
      {/* Starter Suggestion Chips */}
      <div className="flex items-center gap-1.5 overflow-x-auto pb-1 px-1 no-scrollbar text-xs">
        <Sparkle size={13} className="text-m3-primary flex-shrink-0" />
        {STARTER_PROMPTS.map((prompt, idx) => (
          <button
            key={idx}
            onClick={() => handleSelectStarter(prompt)}
            disabled={disabled}
            className="flex-shrink-0 px-3 py-1 rounded-full bg-white/5 hover:bg-white/10 active:scale-[0.98] transition-all text-[11px] text-m3-on-surface-variant hover:text-white border border-white/5 cursor-pointer disabled:opacity-40"
          >
            {prompt}
          </button>
        ))}
      </div>

      {/* Double-Bezel Nested Composer */}
      <div className="p-1.5 rounded-[1.75rem] bg-white/[0.03] border border-white/10 shadow-double-bezel">
        <div className="flex items-end gap-2 px-3 py-2 rounded-[calc(1.75rem-0.375rem)] bg-m3-surface-container-high/90 border border-white/5 shadow-rim-light focus-within:border-m3-primary/30 transition-all">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={disabled}
            placeholder="Ask a question or issue an operational command..."
            rows={1}
            className="w-full bg-transparent resize-none focus:outline-none text-sm text-white placeholder-m3-on-surface-variant/60 max-h-36 py-1 leading-relaxed"
          />

          {/* Button-in-Button Trailing Action Pill */}
          <button
            type="button"
            onClick={() => handleSubmit()}
            disabled={!input.trim() || disabled}
            aria-label="Send Message"
            className="group flex-shrink-0 flex items-center justify-center w-8 h-8 rounded-full bg-m3-primary text-m3-on-primary font-medium hover:bg-white active:scale-95 disabled:opacity-30 disabled:hover:bg-m3-primary cursor-pointer transition-all duration-300"
          >
            <ArrowUp
              size={16}
              weight="bold"
              className="group-hover:translate-y-[-1px] transition-transform duration-200"
            />
          </button>
        </div>
      </div>
    </div>
  );
}
