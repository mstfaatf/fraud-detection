import type { Metadata } from "next";
import { Fraunces, IBM_Plex_Mono, IBM_Plex_Sans } from "next/font/google";

import { FreeTierBanner } from "@/components/layout/free-tier-banner";
import { Sidebar } from "@/components/layout/sidebar";

import "./globals.css";
import { Providers } from "./providers";

// Fraunces (display serif, headings/wordmark) + IBM Plex Sans (body/UI) +
// IBM Plex Mono (numbers, feature names, anything table-like) -- a
// deliberate pairing, not the default Inter/Geist system-sans stack. See
// CLAUDE.md's frontend-scaffolding phase for the full rationale.
const fraunces = Fraunces({
  subsets: ["latin"],
  variable: "--font-display",
  weight: ["500", "600"],
  style: ["normal", "italic"],
});

const plexSans = IBM_Plex_Sans({
  subsets: ["latin"],
  variable: "--font-sans",
  weight: ["400", "500", "600"],
});

const plexMono = IBM_Plex_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  weight: ["400", "500"],
});

export const metadata: Metadata = {
  title: "Fraud Detection — PaySim / XGBoost dashboard",
  description:
    "A real-time fraud-scoring dashboard over PaySim's simulated transactions: XGBoost for the fraud probability, Isolation Forest as a secondary anomaly signal, and SHAP for why the model called it that way.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${fraunces.variable} ${plexSans.variable} ${plexMono.variable}`}>
      <body className="flex min-h-screen flex-col bg-bg font-sans text-text antialiased">
        <Providers>
          <FreeTierBanner />
          <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
            <Sidebar />
            <main className="flex-1 overflow-y-auto px-4 py-6 lg:px-10 lg:py-8">{children}</main>
          </div>
        </Providers>
      </body>
    </html>
  );
}
