"use client";

import React from "react";
import Link from "next/link";
import { Database, ArrowLeft, ArrowUpRight, GithubLogo, BookOpen } from "@phosphor-icons/react";

export function DocsHeader() {
  return (
    <header className="sticky top-4 z-40 mx-auto max-w-6xl px-4 mb-8">
      <div className="flex items-center justify-between gap-4 px-6 py-3 rounded-full bg-m3-surface-container/80 backdrop-blur-2xl border border-white/10 shadow-double-bezel">
        {/* Brand & Badge */}
        <Link href="/" className="flex items-center gap-3 group cursor-pointer">
          <div className="flex items-center justify-center w-8 h-8 rounded-full bg-m3-primary/10 border border-m3-primary/20 text-m3-primary group-hover:scale-105 transition-transform">
            <Database size={18} weight="bold" />
          </div>
          <span className="font-semibold text-sm tracking-tight text-white group-hover:text-m3-primary transition-colors">
            AegisGraph
          </span>
        </Link>

        {/* Quick Nav Links */}
        <nav className="hidden md:flex items-center gap-6 text-xs font-medium text-m3-on-surface-variant">
          <a href="#problem" className="hover:text-white transition-colors">The Problem</a>
          <a href="#memory-tiers" className="hover:text-white transition-colors">4 Memory Tiers</a>
          <a href="#research" className="hover:text-white transition-colors">Research & Math</a>
          <a href="#isolation" className="hover:text-white transition-colors">Enterprise Privacy</a>
        </nav>

        {/* Primary Action Button to Interactive Console */}
        <div className="flex items-center gap-3">
          <a
            href="https://github.com/RitwikGupta-0501/agentic-memory"
            target="_blank"
            rel="noopener noreferrer"
            title="GitHub Repository"
            className="hidden sm:flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-white/5 hover:bg-white/10 text-m3-on-surface text-xs font-medium border border-white/5 transition-all"
          >
            <GithubLogo size={15} />
            <span>GitHub</span>
          </a>

          <Link
            href="/"
            className="group flex items-center gap-2 pl-4 pr-2 py-1.5 rounded-full bg-m3-primary text-m3-on-primary font-semibold text-xs transition-all hover:bg-white active:scale-95 shadow-glow-primary"
          >
            <span>Launch Live Console</span>
            <div className="w-6 h-6 rounded-full bg-m3-on-primary/10 flex items-center justify-center group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform">
              <ArrowUpRight size={13} weight="bold" />
            </div>
          </Link>
        </div>
      </div>
    </header>
  );
}
