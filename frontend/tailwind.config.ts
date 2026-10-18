import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  darkMode: "class",
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-sans)", "Plus Jakarta Sans", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "JetBrains Mono", "monospace"],
      },
      colors: {
        m3: {
          surface: "#0D1117",
          "surface-dim": "#080B0F",
          "surface-bright": "#1C212A",
          "surface-container-lowest": "#05070A",
          "surface-container-low": "#10141C",
          "surface-container": "#151B24",
          "surface-container-high": "#1E2532",
          "surface-container-highest": "#283142",
          primary: "#A8C7FA",
          "on-primary": "#042C6A",
          "primary-container": "#0842A0",
          "on-primary-container": "#D3E3FD",
          secondary: "#C2E7FF",
          "on-secondary": "#003355",
          "secondary-container": "#004B75",
          "on-secondary-container": "#C2E7FF",
          tertiary: "#D0BCFF",
          "on-tertiary": "#381E72",
          outline: "#8C9199",
          "outline-variant": "rgba(255, 255, 255, 0.08)",
          "on-surface": "#E3E2E6",
          "on-surface-variant": "#C4C6D0",
        },
        tier: {
          working: "#FDD663",
          episodic: "#78D9EC",
          semantic: "#81C995",
          procedural: "#C58AF9",
        },
      },
      transitionTimingFunction: {
        spring: "cubic-bezier(0.32, 0.72, 0, 1)",
      },
      borderRadius: {
        bezel: "2rem",
        "inner-bezel": "calc(2rem - 0.375rem)",
      },
      boxShadow: {
        "rim-light": "inset 0 1px 1px 0 rgba(255, 255, 255, 0.12)",
        "double-bezel": "0 0 0 1px rgba(255, 255, 255, 0.08), 0 20px 40px -15px rgba(0, 0, 0, 0.7)",
        "glow-primary": "0 0 35px -5px rgba(168, 199, 250, 0.15)",
      },
    },
  },
  plugins: [],
};

export default config;
