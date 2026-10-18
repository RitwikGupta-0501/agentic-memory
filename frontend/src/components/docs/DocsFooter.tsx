"use client";

import React from "react";
import Link from "next/link";
import { Database, GithubLogo, Heart } from "@phosphor-icons/react";

export function DocsFooter() {
  return (
    <footer className="mx-auto max-w-5xl px-4 py-12 border-t border-white/5 text-xs text-m3-on-surface-variant flex flex-col sm:flex-row items-center justify-between gap-4">
      <div className="flex items-center gap-2.5">
        <div className="w-6 h-6 rounded-full bg-m3-primary/10 border border-m3-primary/20 text-m3-primary flex items-center justify-center">
          <Database size={13} weight="bold" />
        </div>
        <span className="font-semibold text-white">AegisGraph</span>
        <span>•</span>
        <span>Powered by FalkorDB Graph Database</span>
      </div>

      <div className="flex items-center gap-6">
        <Link href="/" className="hover:text-white transition-colors">
          Interactive Console
        </Link>
        <a
          href="https://github.com/RitwikGupta-0501/agentic-memory"
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-1 hover:text-white transition-colors"
        >
          <GithubLogo size={14} />
          <span>GitHub</span>
        </a>
      </div>
    </footer>
  );
}
