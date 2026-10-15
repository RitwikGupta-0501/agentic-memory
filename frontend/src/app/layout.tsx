import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AegisGraph: 4-Tier Cognitive Graph Memory Engine",
  description: "Multi-Tenant Cognitive Memory & Multi-Agent Coordination Engine powered by FalkorDB",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="antialiased min-h-screen bg-[#090d16] text-slate-100">{children}</body>
    </html>
  );
}
