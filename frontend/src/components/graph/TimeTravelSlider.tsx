"use client";

import React, { useState, useEffect } from "react";
import { Clock, ArrowCounterClockwise } from "@phosphor-icons/react";

interface TimeTravelSliderProps {
  asOf: number | null;
  onAsOfChange: (timestamp: number | null) => void;
}

export function TimeTravelSlider({ asOf, onAsOfChange }: TimeTravelSliderProps) {
  const [mounted, setMounted] = useState(false);
  const [minTime, setMinTime] = useState<number>(0);
  const [maxTime, setMaxTime] = useState<number>(100);
  const [sliderVal, setSliderVal] = useState<number>(100);

  useEffect(() => {
    setMounted(true);
    const now = Date.now();
    setMinTime(now - 3600 * 24 * 7 * 1000); // 7 days ago
    setMaxTime(now);
    if (asOf !== null) {
      setSliderVal(asOf * 1000);
    } else {
      setSliderVal(now);
    }
  }, [asOf]);

  const handleSliderChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = Number(e.target.value);
    setSliderVal(val);
    onAsOfChange(val / 1000);
  };

  const handleResetToLive = () => {
    onAsOfChange(null);
  };

  if (!mounted) {
    return (
      <div className="flex items-center gap-3 px-4 py-2 border-t border-white/5 bg-m3-surface-container/60 text-xs">
        <div className="flex items-center gap-1.5 flex-shrink-0">
          <Clock size={14} className="text-emerald-400" />
          <span className="font-medium text-white text-[11px]">Live (Current State)</span>
        </div>
        <div className="flex-1 h-1.5 bg-m3-surface-container-high rounded-lg" />
        <span className="font-mono text-[11px] text-m3-on-surface-variant flex-shrink-0">Live</span>
      </div>
    );
  }

  const isLive = asOf === null || sliderVal >= maxTime - 10000;
  const dateFormatted = new Date(sliderVal).toLocaleString();

  return (
    <div className="flex items-center gap-3 px-4 py-2 border-t border-white/5 bg-m3-surface-container/60 text-xs">
      <div className="flex items-center gap-1.5 flex-shrink-0">
        <Clock size={14} className={isLive ? "text-emerald-400" : "text-amber-400"} />
        <span className="font-medium text-white text-[11px]">
          {isLive ? "Live (Current State)" : "Historical Time-Travel"}
        </span>
      </div>

      <input
        type="range"
        min={minTime}
        max={maxTime}
        value={sliderVal}
        onChange={handleSliderChange}
        className="flex-1 h-1.5 bg-m3-surface-container-high rounded-lg appearance-none cursor-pointer accent-m3-primary"
      />

      <span className="font-mono text-[11px] text-m3-on-surface-variant flex-shrink-0">
        {dateFormatted}
      </span>

      {!isLive && (
        <button
          onClick={handleResetToLive}
          title="Return to live state"
          className="flex items-center gap-1 px-2.5 py-1 rounded-full bg-m3-primary/15 text-m3-primary hover:bg-m3-primary/25 transition-all text-[11px] font-medium cursor-pointer"
        >
          <ArrowCounterClockwise size={12} />
          <span>Live</span>
        </button>
      )}
    </div>
  );
}
