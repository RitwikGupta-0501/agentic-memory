"use client";

import React, { useState, useRef, useEffect, useId } from "react";
import { CaretDown, Check } from "@phosphor-icons/react";
import { twMerge } from "tailwind-merge";

export interface DropdownOption {
  value: string;
  label: string;
  badge?: string;
}

export interface PillDropdownProps {
  value: string;
  options: DropdownOption[];
  onChange: (value: string) => void;
  icon?: React.ReactNode;
  label?: string;
  placeholder?: string;
  className?: string;
  containerClassName?: string;
  disabled?: boolean;
}

export function PillDropdown({
  value,
  options,
  onChange,
  icon,
  label,
  placeholder = "Select...",
  className = "",
  containerClassName = "",
  disabled = false,
}: PillDropdownProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [focusedIndex, setFocusedIndex] = useState<number>(-1);
  const containerRef = useRef<HTMLDivElement>(null);
  const listboxRef = useRef<HTMLUListElement>(null);
  const listboxId = useId();

  const selectedOption = options.find((opt) => opt.value === value);
  const displayLabel = selectedOption ? selectedOption.label : placeholder;

  // Close on outside click
  useEffect(() => {
    if (!isOpen) return;

    const handleClickOutside = (e: MouseEvent | TouchEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("touchstart", handleClickOutside);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("touchstart", handleClickOutside);
    };
  }, [isOpen]);

  // Reset keyboard focus index when opened
  useEffect(() => {
    if (isOpen) {
      const idx = options.findIndex((opt) => opt.value === value);
      setFocusedIndex(idx >= 0 ? idx : 0);
    } else {
      setFocusedIndex(-1);
    }
  }, [isOpen, options, value]);

  // Handle keyboard navigation
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (disabled) return;

    if (!isOpen) {
      if (e.key === "ArrowDown" || e.key === "ArrowUp" || e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        setIsOpen(true);
      }
      return;
    }

    switch (e.key) {
      case "Escape":
        e.preventDefault();
        setIsOpen(false);
        break;
      case "ArrowDown":
        e.preventDefault();
        setFocusedIndex((prev) => (prev < options.length - 1 ? prev + 1 : 0));
        break;
      case "ArrowUp":
        e.preventDefault();
        setFocusedIndex((prev) => (prev > 0 ? prev - 1 : options.length - 1));
        break;
      case "Enter":
      case " ":
        e.preventDefault();
        if (focusedIndex >= 0 && focusedIndex < options.length) {
          onChange(options[focusedIndex].value);
          setIsOpen(false);
        }
        break;
      case "Tab":
        setIsOpen(false);
        break;
    }
  };

  // Scroll focused option into view when navigating via keyboard
  useEffect(() => {
    if (isOpen && focusedIndex >= 0 && listboxRef.current) {
      const activeEl = listboxRef.current.children[focusedIndex] as HTMLElement;
      if (activeEl) {
        activeEl.scrollIntoView({ block: "nearest" });
      }
    }
  }, [focusedIndex, isOpen]);

  return (
    <div
      ref={containerRef}
      className={`relative inline-block text-left ${containerClassName}`}
      onKeyDown={handleKeyDown}
    >
      {/* Pill Trigger Button */}
      <button
        type="button"
        disabled={disabled}
        onClick={() => setIsOpen((prev) => !prev)}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        aria-controls={listboxId}
        className={twMerge(
          "group flex items-center justify-between gap-1.5 px-3 py-1.5 rounded-full",
          "bg-m3-surface-container-high/90 hover:bg-m3-surface-container-highest/90",
          "border text-xs text-m3-on-surface cursor-pointer select-none",
          "outline-none focus:outline-none focus-visible:outline-none active:outline-none",
          "ring-0 focus:ring-0 focus-visible:ring-0 shadow-none",
          "transition-colors duration-150",
          "disabled:opacity-40 disabled:cursor-not-allowed",
          isOpen
            ? "border-m3-primary/40 bg-m3-surface-container-highest/90"
            : "border-white/10 hover:border-white/20 focus-visible:border-m3-primary/40",
          className
        )}
      >
        <div className="flex items-center gap-1.5 min-w-0 flex-1">
          {icon && <span className="flex-shrink-0 flex items-center">{icon}</span>}
          {label && (
            <span className="text-m3-on-surface-variant text-[11px] font-medium flex-shrink-0">
              {label}
            </span>
          )}
          <span className="font-medium text-white truncate text-xs" title={displayLabel}>
            {displayLabel}
          </span>
        </div>

        <CaretDown
          size={11}
          className={`flex-shrink-0 text-white/50 group-hover:text-white/80 transition-transform duration-200 ml-1 ${
            isOpen ? "rotate-180 text-m3-primary" : ""
          }`}
        />
      </button>

      {/* Dropdown Menu (Matches exact width of pill and similar color) */}
      {isOpen && (
        <ul
          id={listboxId}
          ref={listboxRef}
          role="listbox"
          tabIndex={-1}
          className="absolute left-0 top-full mt-1.5 w-full z-50 rounded-2xl bg-m3-surface-container-high/95 backdrop-blur-2xl border border-white/10 shadow-2xl p-1 max-h-60 overflow-y-auto outline-none focus:outline-none focus-visible:outline-none ring-0 focus:ring-0"
        >
          {options.length === 0 ? (
            <li className="px-3 py-2 text-xs text-m3-on-surface-variant italic text-center">
              No options
            </li>
          ) : (
            options.map((option, index) => {
              const isSelected = option.value === value;
              const isFocused = index === focusedIndex;

              return (
                <li
                  key={option.value}
                  role="option"
                  aria-selected={isSelected}
                  onClick={() => {
                    onChange(option.value);
                    setIsOpen(false);
                  }}
                  onMouseEnter={() => setFocusedIndex(index)}
                  className={`flex items-center justify-between gap-1.5 w-full px-2.5 py-1.5 rounded-xl text-xs transition-colors cursor-pointer select-none text-left ${
                    isSelected
                      ? "bg-m3-primary/15 text-m3-primary font-semibold"
                      : isFocused
                      ? "bg-white/10 text-white"
                      : "text-m3-on-surface hover:bg-white/5 hover:text-white"
                  }`}
                >
                  <span className="truncate flex-1" title={option.label}>
                    {option.label}
                  </span>
                  {isSelected && (
                    <Check size={12} weight="bold" className="text-m3-primary flex-shrink-0 ml-1" />
                  )}
                  {option.badge && (
                    <span className="text-[10px] px-1 py-0.2 rounded bg-white/10 text-m3-on-surface-variant font-mono flex-shrink-0">
                      {option.badge}
                    </span>
                  )}
                </li>
              );
            })
          )}
        </ul>
      )}
    </div>
  );
}
