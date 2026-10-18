import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AegisGraph: 4-Tier Cognitive Graph Memory",
  description: "Autonomous Agent Memory & Coordination Engine powered by FalkorDB",
  icons: {
    icon: [
      { url: "/favicon.ico", sizes: "any" },
      { url: "/icon.svg", type: "image/svg+xml" },
    ],
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen bg-m3-surface-dim bg-ambient-mesh text-m3-on-surface antialiased selection:bg-m3-primary/20 selection:text-m3-primary">
        {children}
      </body>
    </html>
  );
}
