import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: "var(--color-bg)",
        surface: "var(--color-surface)",
        "surface-2": "var(--color-surface-2)",
        border: "var(--color-border)",

        text: "var(--color-text)",
        "text-muted": "var(--color-text-muted)",
        "text-faint": "var(--color-text-faint)",

        accent: "var(--color-accent)",
        "accent-soft": "var(--color-accent-soft)",

        "risk-fraud": "var(--color-risk-fraud)",
        "risk-fraud-soft": "var(--color-risk-fraud-soft)",
        "risk-legit": "var(--color-risk-legit)",
        "risk-legit-soft": "var(--color-risk-legit-soft)",
        "risk-anomaly": "var(--color-risk-anomaly)",
      },
      fontFamily: {
        // Fraunces (display serif) for headings/wordmark -- IBM Plex Sans for
        // body/UI text -- IBM Plex Mono for numbers, feature names, and
        // anything table-like. Deliberately not the default Inter/Geist
        // system-sans-everywhere look.
        display: ["var(--font-display)", "serif"],
        sans: ["var(--font-sans)", "sans-serif"],
        mono: ["var(--font-mono)", "monospace"],
      },
      borderRadius: {
        card: "10px",
      },
    },
  },
  plugins: [],
};
export default config;
